"""Database schema, connections and versioned migration entry point."""
import os
from pathlib import Path
from functools import lru_cache

from sqlalchemy import (Column, Integer, String, Float, JSON, ForeignKey, Table, MetaData,
                        CheckConstraint, Index, create_engine, event, text, ForeignKeyConstraint, UniqueConstraint)
from sqlalchemy.engine import make_url
from contextlib import contextmanager
from campusflow.tenancy import institution_id, AcademicConnection

metadata = MetaData()
faculty = Table("faculty", metadata,
    Column("id", String, primary_key=True), Column("name", String, nullable=False),
    Column("department", String, nullable=False), Column("max_daily_minutes", Integer, nullable=False),
    Column("preferred_start", String, nullable=False), Column("preferred_end", String, nullable=False),
    Column("restricted", Integer, nullable=False, default=0), CheckConstraint("max_daily_minutes > 0"))
subjects = Table("subjects", metadata,
    Column("id", String, primary_key=True), Column("name", String, nullable=False),
    Column("department", String, nullable=False), Column("semester", Integer, nullable=False),
    Column("weekly_sessions", Integer, nullable=False), Column("duration_minutes", Integer, nullable=False),
    Column("kind", String, nullable=False), CheckConstraint("semester > 0 AND weekly_sessions > 0 AND duration_minutes > 0"),
    CheckConstraint("kind IN ('theory','lab','activity')"))
rooms = Table("rooms", metadata,
    Column("id", String, primary_key=True), Column("name", String, nullable=False),
    Column("kind", String, nullable=False), Column("capacity", Integer, nullable=False),
    Column("restricted", Integer, nullable=False, default=0), CheckConstraint("capacity > 0"),
    CheckConstraint("kind IN ('theory','lab')"))
batches = Table("batches", metadata,
    Column("id", String, primary_key=True), Column("department", String, nullable=False),
    Column("semester", Integer, nullable=False), Column("division", String, nullable=False),
    Column("student_count", Integer, nullable=False), CheckConstraint("semester > 0 AND student_count > 0"))
assignments = Table("subject_assignments", metadata,
    Column("faculty_id", String, primary_key=True),
    Column("subject_id", String, primary_key=True))
faculty_windows = Table("faculty_availability", metadata,
    Column("id", Integer, primary_key=True), Column("faculty_id", String, nullable=False),
    Column("day", String, nullable=False), Column("start", String, nullable=False), Column("end", String, nullable=False))
room_windows = Table("room_availability", metadata,
    Column("id", Integer, primary_key=True), Column("room_id", String, nullable=False),
    Column("day", String, nullable=False), Column("start", String, nullable=False), Column("end", String, nullable=False))
requirements = Table("requirements", metadata,
    Column("id", String, primary_key=True), Column("subject_id", String, nullable=False),
    Column("faculty_id", String, nullable=False), Column("batch_id", String, nullable=False),
    Column("weekly_sessions", Integer, nullable=False), Column("duration_minutes", Integer, nullable=False),
    CheckConstraint("weekly_sessions > 0 AND duration_minutes > 0"))
settings = Table("academic_settings", metadata,
    Column("id", Integer, primary_key=True), Column("value", JSON, nullable=False))
jobs = Table("generation_jobs", metadata,
    Column("id", String, primary_key=True), Column("state", String, nullable=False),
    Column("name", String, nullable=False), Column("scope", String, nullable=False), Column("solver", String, nullable=False),
    Column("created_at", String, nullable=False), Column("duration_seconds", Float),
    Column("payload", JSON, nullable=False), Column("result", JSON), Column("saved_version", String))
versions = Table("timetable_versions", metadata,
    Column("id", String, primary_key=True), Column("name", String, nullable=False), Column("scope", String, nullable=False),
    Column("state", String, nullable=False), Column("revision", Integer, nullable=False, default=1),
    Column("created_at", String, nullable=False), Column("problem", JSON, nullable=False),
    Column("policy", JSON, nullable=False), Column("source_id", String), Column("changes", JSON, nullable=False, default=list),
    CheckConstraint("state IN ('draft','generated','published','archived')"))

sessions = Table("scheduled_sessions", metadata,
    Column("version_id", String, primary_key=True),
    Column("id", String, primary_key=True), Column("subject", String, nullable=False),
    Column("faculty", String, nullable=False), Column("batch", String, nullable=False),
    Column("classroom", String, nullable=False), Column("day", String, nullable=False),
    Column("start", String, nullable=False), Column("end", String, nullable=False))
# Tenant keys preserve local academic identifiers across institutions.
departments = Table("departments", metadata, Column("id", String, primary_key=True), Column("name", String, nullable=False))
academic_years = Table("academic_years", metadata, Column("id", String, primary_key=True), Column("name", String, nullable=False))
batches.append_column(Column("class_number", Integer))
batches.append_column(Column("class_teacher_id", String))
batches.append_column(Column("academic_year", String, nullable=False, server_default=""))
TENANT_TABLES = {t.name: t for t in (faculty, subjects, rooms, batches, assignments, faculty_windows, room_windows, requirements, settings, jobs, versions, sessions, departments, academic_years)}
for table in TENANT_TABLES.values():
    table.append_column(Column("institution_id", ForeignKey("institutions.institution_id"), nullable=False,
        primary_key=table not in (faculty_windows, room_windows), default=institution_id))
    if table in (faculty_windows, room_windows):
        table.append_constraint(UniqueConstraint("institution_id", "id"))
for table, column, target, cascade in (
    (assignments,"faculty_id",faculty,True),(assignments,"subject_id",subjects,False),
    (faculty_windows,"faculty_id",faculty,True),(room_windows,"room_id",rooms,True),
    (requirements,"subject_id",subjects,False),(requirements,"faculty_id",faculty,False),(requirements,"batch_id",batches,False),
    (sessions,"version_id",versions,True),(sessions,"subject",subjects,False),(sessions,"faculty",faculty,False),
    (sessions,"batch",batches,False),(sessions,"classroom",rooms,False),(batches,"class_teacher_id",faculty,False)):
    table.append_constraint(ForeignKeyConstraint(["institution_id",column], [target.name+".institution_id",target.name+".id"], ondelete="CASCADE" if cascade else "RESTRICT"))
Index("one_published_per_scope", versions.c.institution_id, versions.c.scope, unique=True,
    sqlite_where=text("state = 'published'"), postgresql_where=text("state = 'published'"))

schema_versions = Table("schema_versions", metadata, Column("version", Integer, primary_key=True))
TABLES = {t.name: t for t in (faculty, subjects, rooms, batches, requirements, departments, academic_years)}


@lru_cache(maxsize=4)
def engine_for(url: str):
    if url.startswith("postgres://"):
        url = "postgresql://" + url.removeprefix("postgres://")
    parsed = make_url(url)
    if parsed.drivername == "postgresql":
        parsed = parsed.set(drivername="postgresql+psycopg")
    if parsed.get_backend_name() == "postgresql":
        return create_engine(parsed, pool_pre_ping=True, pool_timeout=10,
                             connect_args={"connect_timeout": 5}, hide_parameters=True)
    engine = create_engine(parsed, connect_args={"check_same_thread": False, "timeout": 15},
                           hide_parameters=True)
    @event.listens_for(engine, "connect")
    def configure(dbapi, _):
        dbapi.execute("PRAGMA foreign_keys=ON")
        dbapi.execute("PRAGMA busy_timeout=15000")
    return engine


def lock_transaction(conn):
    """Serialize write transactions that check invariants before updating rows."""
    if conn.dialect.name == "postgresql":
        conn.exec_driver_sql("SELECT pg_advisory_xact_lock(672613520001)")
    else:
        conn.exec_driver_sql("BEGIN IMMEDIATE")


def database():
    default = Path(__file__).resolve().parents[2] / "data" / "campusflow.db"
    url = os.environ.get("CAMPUSFLOW_DATABASE_URL")
    if not url:
        if os.getenv("CAMPUSFLOW_ENV") == "production":
            raise RuntimeError("Production requires CAMPUSFLOW_DATABASE_URL")
        default.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{default.as_posix()}"
    return engine_for(url)


@contextmanager
def connection():
    with database().connect() as conn:
        yield AcademicConnection(conn)


def migrate(engine=None, *, allow_tenant_upgrade=False):
    from .migrations import upgrade
    upgrade(engine or database(), allow_tenant_upgrade=allow_tenant_upgrade)


if __name__ == "__main__":
    migrate()
    print("CampusFlow database migrated to version 6.")
