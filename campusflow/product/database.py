"""SQLite schema and versioned migration entry point."""
import os
from pathlib import Path
from functools import lru_cache

from sqlalchemy import (Column, Integer, String, Float, JSON, ForeignKey, Table, MetaData,
                        CheckConstraint, Index, create_engine, event, text)

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
    CheckConstraint("kind IN ('theory','lab')"))
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
    Column("faculty_id", ForeignKey("faculty.id", ondelete="CASCADE"), primary_key=True),
    Column("subject_id", ForeignKey("subjects.id", ondelete="RESTRICT"), primary_key=True))
faculty_windows = Table("faculty_availability", metadata,
    Column("id", Integer, primary_key=True), Column("faculty_id", ForeignKey("faculty.id", ondelete="CASCADE"), nullable=False),
    Column("day", String, nullable=False), Column("start", String, nullable=False), Column("end", String, nullable=False))
room_windows = Table("room_availability", metadata,
    Column("id", Integer, primary_key=True), Column("room_id", ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
    Column("day", String, nullable=False), Column("start", String, nullable=False), Column("end", String, nullable=False))
requirements = Table("requirements", metadata,
    Column("id", String, primary_key=True), Column("subject_id", ForeignKey("subjects.id"), nullable=False),
    Column("faculty_id", ForeignKey("faculty.id"), nullable=False), Column("batch_id", ForeignKey("batches.id"), nullable=False),
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
Index("one_published_per_scope", versions.c.scope, unique=True, sqlite_where=text("state = 'published'"))
sessions = Table("scheduled_sessions", metadata,
    Column("version_id", ForeignKey("timetable_versions.id", ondelete="CASCADE"), primary_key=True),
    Column("id", String, primary_key=True), Column("subject", ForeignKey("subjects.id"), nullable=False),
    Column("faculty", ForeignKey("faculty.id"), nullable=False), Column("batch", ForeignKey("batches.id"), nullable=False),
    Column("classroom", ForeignKey("rooms.id"), nullable=False), Column("day", String, nullable=False),
    Column("start", String, nullable=False), Column("end", String, nullable=False))
schema_versions = Table("schema_versions", metadata, Column("version", Integer, primary_key=True))
TABLES = {t.name: t for t in (faculty, subjects, rooms, batches, requirements)}


@lru_cache(maxsize=4)
def engine_for(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 15})
    @event.listens_for(engine, "connect")
    def configure(dbapi, _):
        dbapi.execute("PRAGMA foreign_keys=ON")
        dbapi.execute("PRAGMA busy_timeout=15000")
    return engine


def database():
    default = Path(__file__).resolve().parents[2] / "data" / "campusflow.db"
    url = os.environ.get("CAMPUSFLOW_DATABASE_URL")
    if not url:
        default.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{default.as_posix()}"
    return engine_for(url)


def migrate(engine=None):
    from .migrations import upgrade
    upgrade(engine or database())


if __name__ == "__main__":
    migrate()
    print("CampusFlow database migrated to version 1.")
