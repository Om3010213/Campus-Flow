"""Transactional academic record access and engine input translation."""
from contextlib import contextmanager
from datetime import date, datetime, timedelta

from sqlalchemy import select, delete, update
from sqlalchemy.exc import IntegrityError

from campusflow.api.schemas import ProblemInput
from . import database as db
from .schemas import AcademicSettings, RECORDS


class ProductError(Exception):
    def __init__(self, message: str, code: int = 422, errors=None):
        self.message, self.code, self.errors = message, code, errors or []


@contextmanager
def transaction():
    try:
        with db.database().begin() as conn:
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            yield conn
    except IntegrityError as exc:
        raise ProductError("Duplicate identifier or record still referenced by academic data or timetables.", 409) from exc


def records(conn, kind: str) -> list[dict]:
    if kind not in db.TABLES:
        raise ProductError("Unknown academic entity", 404)
    rows = [dict(row) for row in conn.execute(select(db.TABLES[kind]).order_by(db.TABLES[kind].c.id)).mappings()]
    if kind in ("faculty", "rooms"):
        windows = db.faculty_windows if kind == "faculty" else db.room_windows
        key = "faculty_id" if kind == "faculty" else "room_id"
        all_windows = list(conn.execute(select(windows)).mappings())
        pairs = list(conn.execute(select(db.assignments)).mappings()) if kind == "faculty" else []
        for row in rows:
            row["restricted"] = bool(row["restricted"])
            row["availability"] = [{k: w[k] for k in ("day", "start", "end")} for w in all_windows if w[key] == row["id"]]
            if kind == "faculty":
                row["subject_ids"] = [p["subject_id"] for p in pairs if p["faculty_id"] == row["id"]]
    return rows


def catalog(conn) -> dict:
    return {kind: records(conn, kind) for kind in db.TABLES}


def save_record(conn, kind: str, body: dict, editing: str | None = None) -> dict:
    if kind not in RECORDS:
        raise ProductError("Unknown academic entity", 404)
    item = RECORDS[kind].model_validate(body).model_dump(mode="json")
    table = db.TABLES[kind]
    if editing is not None:
        if editing != item["id"]:
            raise ProductError("Identifiers cannot be changed; create a new record instead.")
        if not conn.execute(select(table.c.id).where(table.c.id == editing)).first():
            raise ProductError("Record not found", 404)
    if kind == "requirements":
        match = conn.execute(select(db.assignments).where(
            db.assignments.c.faculty_id == item["faculty_id"], db.assignments.c.subject_id == item["subject_id"])).first()
        if not match:
            raise ProductError("Assign this subject to the faculty member first.")
    if kind == "faculty" and editing:
        used = conn.execute(select(db.requirements.c.subject_id).where(db.requirements.c.faculty_id == editing)).scalars()
        if set(used) - set(item["subject_ids"]):
            raise ProductError("Cannot remove subject assignments used by weekly requirements.", 409)
    fields = {key: value for key, value in item.items() if key in table.c}
    if editing:
        conn.execute(update(table).where(table.c.id == editing).values(**fields))
    else:
        conn.execute(table.insert().values(**fields))
    if kind in ("faculty", "rooms"):
        windows = db.faculty_windows if kind == "faculty" else db.room_windows
        key = "faculty_id" if kind == "faculty" else "room_id"
        conn.execute(delete(windows).where(windows.c[key] == item["id"]))
        for window in item["availability"]:
            conn.execute(windows.insert().values(**{key: item["id"]}, **window))
        if kind == "faculty":
            conn.execute(delete(db.assignments).where(db.assignments.c.faculty_id == item["id"]))
            for subject in item["subject_ids"]:
                conn.execute(db.assignments.insert().values(faculty_id=item["id"], subject_id=subject))
    return item


def delete_record(conn, kind: str, identifier: str):
    if kind not in db.TABLES:
        raise ProductError("Unknown academic entity", 404)
    # Snapshots include unscheduled requirements too: protect even empty drafts.
    key = {"subjects": "subject", "faculty": "faculty", "batches": "batch", "requirements": "id"}.get(kind)
    for version in conn.execute(select(db.versions.c.problem)).scalars():
        if (kind == "rooms" and identifier in version["classrooms"]) or (
                key and any(r[key] == identifier for r in version["requirements"])):
            raise ProductError("This record is referenced by a timetable version. Delete the draft/archive first.", 409)
    result = conn.execute(delete(db.TABLES[kind]).where(db.TABLES[kind].c.id == identifier))
    if not result.rowcount:
        raise ProductError("Record not found", 404)


def settings(conn) -> dict:
    value = conn.execute(select(db.settings.c.value).where(db.settings.c.id == 1)).scalar_one_or_none()
    return value or AcademicSettings().model_dump(mode="json")


def save_settings(conn, body):
    value = AcademicSettings.model_validate(body).model_dump(mode="json")
    conn.execute(delete(db.settings).where(db.settings.c.id == 1))
    conn.execute(db.settings.insert().values(id=1, value=value))
    return value


def snapshot(conn) -> dict:
    data = catalog(conn)
    config = AcademicSettings.model_validate(settings(conn))
    if not data["requirements"]:
        raise ProductError("Add at least one weekly requirement before generating.")
    # Construct starts independently inside each uninterrupted teaching window.
    ordered = sorted(config.breaks, key=lambda b: b.start)
    boundaries = []
    cursor = config.start
    for pause in ordered:
        boundaries.append((cursor, pause.start))
        cursor = pause.end
    boundaries.append((cursor, config.end))
    slots = []
    for begin, end in boundaries:
        current = datetime.combine(date(2000, 1, 1), begin)
        finish = datetime.combine(date(2000, 1, 1), end)
        while current < finish:
            after = min(current + timedelta(minutes=config.slot_minutes), finish)
            slots.append({"start": current.time(), "end": after.time()})
            current = after
    problem = ProblemInput.model_validate({
        "faculty": [{"name": f["id"], "subjects": f["subject_ids"]} for f in data["faculty"]],
        "batches": [b["id"] for b in data["batches"]], "classrooms": [r["id"] for r in data["rooms"]],
        "working_days": config.working_days, "time_slots": slots,
        "requirements": [{"id": r["id"], "subject": r["subject_id"], "faculty": r["faculty_id"],
                          "batch": r["batch_id"], "weekly_sessions": r["weekly_sessions"],
                          "duration_minutes": r["duration_minutes"]} for r in data["requirements"]],
        "faculty_availability": {f["id"]: f["availability"] for f in data["faculty"] if f["restricted"]},
        "classroom_availability": {r["id"]: r["availability"] for r in data["rooms"] if r["restricted"]},
    }).model_dump(mode="json")
    return {"problem": problem, "policy": data}
