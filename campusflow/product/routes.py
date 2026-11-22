from copy import deepcopy

from fastapi import APIRouter, Body, Response, Request
from pydantic import ValidationError
from sqlalchemy import select, delete, update

from campusflow.api.schemas import LectureInput
from . import database as db, catalog, jobs, versions, reports
from .catalog import ProductError, transaction
from campusflow.auth.permissions import require_scope
from campusflow.auth.visibility import personal
from .schemas import AcademicSettings, JobRequest, EditRequest, RevisionRequest, RescheduleRequest

router = APIRouter(prefix="/api/product", tags=["Persistent campus management"])


def ok(data):
    return {"status": "success", "data": data}


@router.get("/catalog")
def all_records():
    with db.connection() as conn:
        return ok(catalog.catalog(conn))


@router.get("/records/{kind}")
def list_records(kind: str, q: str = "", department: str = "", semester: int | None = None):
    with db.connection() as conn:
        rows = catalog.records(conn, kind)
    return ok([row for row in rows if (not q or q.casefold() in " ".join(str(v) for v in row.values()).casefold())
               and (not department or row.get("department") == department)
               and (semester is None or row.get("semester") == semester)])


@router.post("/records/{kind}", status_code=201)
def add_record(kind: str, body: dict = Body(...)):
    try:
        with transaction() as conn:
            return ok(catalog.save_record(conn, kind, body))
    except ValidationError as exc:
        raise ProductError("Invalid academic record", errors=[e["msg"] for e in exc.errors()]) from exc


@router.put("/records/{kind}/{identifier}")
def update_record(kind: str, identifier: str, body: dict = Body(...)):
    try:
        with transaction() as conn:
            return ok(catalog.save_record(conn, kind, body, identifier))
    except ValidationError as exc:
        raise ProductError("Invalid academic record", errors=[e["msg"] for e in exc.errors()]) from exc


@router.delete("/records/{kind}/{identifier}")
def delete_record(kind: str, identifier: str):
    with transaction() as conn:
        catalog.delete_record(conn, kind, identifier)
    return ok(None)


@router.get("/settings")
def get_settings():
    with db.connection() as conn:
        return ok(catalog.settings(conn))


@router.put("/settings")
def put_settings(body: AcademicSettings):
    with transaction() as conn:
        return ok(catalog.save_settings(conn, body.model_dump(mode="json")))


@router.post("/seed")
def seed_data():
    from .seed import seed
    with transaction() as conn:
        seed(conn)
    return ok({"message": "Fictional catalog loaded"})


@router.post("/jobs", status_code=202)
def generate(request: JobRequest, http: Request):
    require_scope(http.state.user, request.scope)
    try:
        with db.connection() as conn:
            payload = catalog.snapshot(conn)
    except ValidationError as exc:
        raise ProductError("Academic configuration exceeds engine limits or has invalid references.",
                           errors=[e["msg"] for e in exc.errors()]) from exc
    payload.update(request.model_dump())
    payload["solver"] = jobs.select_solver(request, sum(r["weekly_sessions"] for r in payload["problem"]["requirements"]))
    return ok({"id": jobs.start(payload, request.name, request.scope)})


@router.get("/jobs")
def job_list(http: Request):
    with db.connection() as conn:
        ids = conn.execute(select(db.jobs.c.id).order_by(db.jobs.c.created_at.desc()).limit(30)).scalars()
        return ok([j for identifier in ids if (j := jobs.get(conn, identifier)) and (http.state.user["role"] == "administrator" or j["scope"] in http.state.user["scopes"])])


@router.get("/jobs/{identifier}")
def job_status(identifier: str):
    with db.connection() as conn:
        return ok(jobs.get(conn, identifier))


@router.post("/jobs/{identifier}/save")
def save_job(identifier: str):
    with transaction() as conn:
        job = jobs.get(conn, identifier, full=True)
        if job["saved_version"]:
            return ok(versions.get(conn, job["saved_version"]))
        if job["state"] != "success":
            raise ProductError("Only successful, independently validated jobs can be saved.", 409)
        payload = job["payload"]
        version = versions.create(conn, job["name"], job["scope"], payload["problem"], payload["policy"],
            job["result"]["lectures"], source_id=payload.get("source_id"))
        conn.execute(update(db.jobs).where(db.jobs.c.id == identifier).values(saved_version=version["id"]))
        return ok(version)


@router.delete("/jobs/{identifier}")
def discard_job(identifier: str):
    with transaction() as conn:
        job = jobs.get(conn, identifier)
        if job["state"] in ("queued", "running"):
            raise ProductError("Wait for this job to finish before discarding it.", 409)
        conn.execute(delete(db.jobs).where(db.jobs.c.id == identifier))
    return ok(None)


@router.get("/versions")
def version_list(http: Request):
    with db.connection() as conn:
        columns = [db.versions.c[k] for k in ("id", "name", "scope", "state", "revision", "created_at", "source_id")]
        user = http.state.user
        if user["role"] in ("viewer", "teacher", "student"):
            columns = [column for column in columns if column.name != "source_id"]
        query = select(*columns).order_by(db.versions.c.created_at.desc())
        if user["role"] not in ("administrator", "teacher", "student"):
            query = query.where(db.versions.c.scope.in_(user["scopes"]))
        if user["role"] in ("viewer", "teacher", "student"):
            query = query.where(db.versions.c.state == "published")
        if user["role"] in ("teacher", "student"):
            owned = select(db.sessions.c.version_id)
            owned = owned.where(db.sessions.c.faculty == user["faculty_id"]) if user["role"] == "teacher" else owned.where(db.sessions.c.batch.in_(user["batch_ids"]))
            query = query.where(db.versions.c.id.in_(set(conn.execute(owned).scalars())))
        return ok([dict(r) for r in conn.execute(query).mappings()])


@router.get("/versions/{identifier}")
def version_detail(identifier: str, http: Request):
    with db.connection() as conn:
        version = personal(http.state.user, versions.get(conn, identifier))
        if http.state.user["role"] in ("viewer", "teacher", "student"):
            used = {field: {l[field] for l in version["lectures"]} for field in ("subject", "faculty", "batch", "classroom")}
            spec = {"subjects": ("subject", ("id", "name", "kind")), "faculty": ("faculty", ("id", "name")),
                    "batches": ("batch", ("id", "department", "semester")), "rooms": ("classroom", ("id", "name", "kind", "capacity"))}
            version["policy"] = {kind: [{k: row[k] for k in keys} for row in version["policy"][kind] if row["id"] in used[field]]
                                 for kind, (field, keys) in spec.items()}
            version.pop("changes", None)
            version.pop("source_id", None)
            version["problem"] = {k: version["problem"][k] for k in ("requirements", "working_days", "time_slots")}
        return ok(version)


@router.put("/versions/{identifier}")
def edit_version(identifier: str, body: EditRequest):
    with transaction() as conn:
        return ok(versions.edit(conn, identifier, body))


@router.post("/versions/{identifier}/validate")
def validate_version(identifier: str, body: EditRequest):
    with db.connection() as conn:
        return ok(versions.edit(conn, identifier, body, save=False))


@router.post("/versions/{identifier}/duplicate")
def duplicate_version(identifier: str):
    with transaction() as conn:
        original = versions.get(conn, identifier)
        return ok(versions.create(conn, original["name"] + " — draft", original["scope"], original["problem"],
                                  original["policy"], original["lectures"], state="draft", source_id=identifier))


@router.post("/versions/{identifier}/publish")
def publish_version(identifier: str, body: RevisionRequest):
    with transaction() as conn:
        return ok(versions.publish(conn, identifier, body.revision))


@router.post("/versions/{identifier}/archive")
def archive_version(identifier: str, body: RevisionRequest):
    with transaction() as conn:
        version = versions.get(conn, identifier)
        if version["revision"] != body.revision:
            raise ProductError("Version changed; reload first.", 409)
        conn.execute(update(db.versions).where(db.versions.c.id == identifier).values(state="archived", revision=body.revision + 1))
        return ok(versions.get(conn, identifier))


@router.delete("/versions/{identifier}")
def delete_version(identifier: str):
    with transaction() as conn:
        version = versions.get(conn, identifier)
        if version["state"] == "published":
            raise ProductError("Archive the published version before deleting it.", 409)
        conn.execute(update(db.jobs).where(db.jobs.c.saved_version == identifier).values(saved_version=None))
        conn.execute(delete(db.versions).where(db.versions.c.id == identifier))
    return ok(None)


@router.post("/versions/{identifier}/reschedule", status_code=202)
def reschedule(identifier: str, body: RescheduleRequest):
    with db.connection() as conn:
        version = versions.get(conn, identifier)
    problem = deepcopy(version["problem"])
    if body.faculty_id not in {f["name"] for f in problem["faculty"]}:
        raise ProductError("Faculty is not part of this timetable.")
    affected = [l["id"] for l in version["lectures"] if l["faculty"] == body.faculty_id and l["day"] == body.day.value]
    if not affected:
        raise ProductError("No sessions are affected by this absence.")
    windows = problem["faculty_availability"].get(body.faculty_id)
    if windows is None:
        windows = [{"day": d, **slot} for d in problem["working_days"] for slot in problem["time_slots"]]
    problem["faculty_availability"][body.faculty_id] = [w for w in windows if w["day"] != body.day.value]
    use_cp = jobs.cp_sat_available()
    original = {l["id"]: l for l in version["lectures"]}
    payload = {"problem": problem, "policy": version["policy"], "source_id": identifier,
               "solver": "cp-sat" if use_cp else "csp", "time_limit_seconds": body.time_limit_seconds,
               "original": original, "affected": affected}
    # CP-SAT minimizes moved sessions globally; CSP preserves unaffected sessions strictly.
    if not use_cp:
        payload["fixed"] = {key: value for key, value in original.items() if key not in affected}
    return ok({"id": jobs.start(payload, version["name"] + " — rescheduled", version["scope"]), "affected": affected})


@router.post("/versions/{identifier}/regenerate", status_code=202)
def regenerate(identifier: str, body: JobRequest):
    with db.connection() as conn:
        version = versions.get(conn, identifier)
    if version["state"] not in ("draft", "generated"):
        raise ProductError("Duplicate the protected version to a draft before regenerating.", 409)
    payload = {"problem": version["problem"], "policy": version["policy"], "source_id": identifier,
               "time_limit_seconds": body.time_limit_seconds, "optimize": body.optimize}
    payload["solver"] = jobs.select_solver(body, sum(r["weekly_sessions"] for r in payload["problem"]["requirements"]))
    return ok({"id": jobs.start(payload, body.name, version["scope"])})


@router.get("/versions/{identifier}/reports")
def version_reports(identifier: str, http: Request):
    with db.connection() as conn:
        version = versions.get(conn, identifier)
        version = personal(http.state.user, version)
        result = reports.report(version)
        if http.state.user["role"] in ("viewer", "teacher", "student"):
            for key, field in (("faculty", "faculty"), ("rooms", "classroom")):
                used = {lecture[field] for lecture in version["lectures"]}
                result[key] = [row for row in result[key] if row["id"] in used]
        return ok(result)


@router.get("/versions/{identifier}/export/{format}")
def export_version(identifier: str, format: str, http: Request):
    with db.connection() as conn:
        version = versions.get(conn, identifier)
    version = personal(http.state.user, version)
    if format not in ("pdf", "csv"):
        raise ProductError("Choose PDF or CSV", 404)
    content = reports.pdf_export(version) if format == "pdf" else reports.csv_export(version)
    return Response(content, media_type="application/pdf" if format == "pdf" else "text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="campusflow-{identifier}.{format}"'})
