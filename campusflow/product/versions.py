"""Immutable published snapshots and optimistic draft editing."""
from copy import deepcopy
from uuid import uuid4

from sqlalchemy import select, update, delete

from campusflow.api.schemas import ProblemInput, LectureInput
from campusflow.conflicts import detect_conflict
from . import database as db
from .catalog import ProductError
from .constraints import validate_snapshot
from .jobs import now


def get(conn, identifier):
    row = conn.execute(select(db.versions).where(db.versions.c.id == identifier)).mappings().first()
    if not row:
        raise ProductError("Timetable not found", 404)
    result = dict(row)
    result["lectures"] = [{k: v for k, v in dict(row).items() if k not in ("version_id", "institution_id")} for row in
                          conn.execute(select(db.sessions).where(db.sessions.c.version_id == identifier)
                                       .order_by(db.sessions.c.id)).mappings()]
    result["validation"] = validate_snapshot(result["problem"], result["policy"], result["lectures"])
    return result


def write_sessions(conn, identifier, lectures):
    conn.execute(delete(db.sessions).where(db.sessions.c.version_id == identifier))
    for lecture in lectures:
        conn.execute(db.sessions.insert().values(version_id=identifier, **lecture))


def create(conn, name, scope, problem, policy, lectures, state="generated", source_id=None):
    checked = validate_snapshot(problem, policy, lectures)
    if not checked["valid"] and state != "draft":
        raise ProductError("Timetable did not pass validation", 422, checked["errors"])
    identifier = uuid4().hex
    history = []
    if source_id:
        before = {l["id"]: l for l in get(conn, source_id)["lectures"]}
        changes = [{"id": l["id"], "before": before.get(l["id"]), "after": l}
                   for l in lectures if before.get(l["id"]) != l]
        if changes:
            history = [{"at": now(), "changes": changes}]
    conn.execute(db.versions.insert().values(id=identifier, name=name, scope=scope, problem=problem,
        policy=policy, state=state, revision=1, created_at=now(), source_id=source_id, changes=history))
    write_sessions(conn, identifier, lectures)
    return get(conn, identifier)


def editable(version, revision):
    if version["state"] not in ("draft", "generated"):
        raise ProductError("Duplicate this timetable to edit a draft. Published and archived versions are immutable.", 409)
    if version["revision"] != revision:
        raise ProductError("This timetable changed in another tab. Reload before saving.", 409)


def prepare_edit(version, lectures):
    problem = deepcopy(version["problem"])
    qualified = {f["name"]: f["subjects"] for f in problem["faculty"]}
    for req in problem["requirements"]:
        ids = {f"{req['id']}:{i}" for i in range(1, req["weekly_sessions"] + 1)}
        assigned = {l["faculty"] for l in lectures if l["id"] in ids}
        if len(assigned) > 1:
            raise ProductError(f"All sessions of requirement {req['id']} must use the same faculty member.")
        if assigned:
            person = next(iter(assigned))
            if req["subject"] not in qualified.get(person, []):
                raise ProductError(f"Faculty {person} is not qualified for subject {req['subject']}.")
            req["faculty"] = person
    ProblemInput.model_validate(problem)
    return problem, validate_snapshot(problem, version["policy"], lectures)


def edit(conn, identifier, request, save=True):
    version = get(conn, identifier)
    editable(version, request.revision)
    lectures = [l.model_dump(mode="json") for l in request.lectures]
    problem, checked = prepare_edit(version, lectures)
    if not save:
        return checked
    hard_errors = [error for error in checked["errors"] if not error.startswith("Missing session:")]
    if hard_errors:
        raise ProductError("Draft edits conflict with scheduling constraints.", 422, hard_errors)
    old = {l["id"]: l for l in version["lectures"]}
    changes = [{"id": l["id"], "before": old.get(l["id"]), "after": l} for l in lectures if old.get(l["id"]) != l]
    changes += [{"id": key, "before": value, "after": None} for key, value in old.items()
                if key not in {l["id"] for l in lectures}]
    conn.execute(update(db.versions).where(db.versions.c.id == identifier).values(
        problem=problem, state="draft", revision=version["revision"] + 1,
        changes=version["changes"] + [{"at": now(), "changes": changes}]))
    write_sessions(conn, identifier, lectures)
    return get(conn, identifier)


def publish(conn, identifier, revision):
    version = get(conn, identifier)
    editable(version, revision)
    if not version["validation"]["valid"]:
        raise ProductError("Only complete, valid timetables can be published.", 422, version["validation"]["errors"])
    other_ids = conn.execute(select(db.versions.c.id).where(db.versions.c.state == "published",
                                                          db.versions.c.scope != version["scope"])).scalars()
    for other_id in other_ids:
        other = get(conn, other_id)
        for a in version["lectures"]:
            for b in other["lectures"]:
                if detect_conflict(LectureInput.model_validate(a).to_domain(), LectureInput.model_validate(b).to_domain()):
                    raise ProductError(f"Conflicts with published scope {other['scope']}. Archive it or revise this draft.", 409)
    conn.execute(update(db.versions).where(db.versions.c.scope == version["scope"],
        db.versions.c.state == "published").values(state="archived", revision=db.versions.c.revision + 1))
    conn.execute(update(db.versions).where(db.versions.c.id == identifier).values(state="published", revision=revision + 1))
    return get(conn, identifier)
