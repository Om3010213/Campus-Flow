from sqlalchemy import Table, Column, String, Integer, Float, JSON, ForeignKey, CheckConstraint, ForeignKeyConstraint
from campusflow.product.database import metadata

users = Table("auth_users", metadata,
    Column("id", String, primary_key=True), Column("username", String, unique=True, nullable=False),
    Column("password_hash", String, nullable=False), Column("role", String, nullable=False),
    Column("scopes", JSON, nullable=False), Column("active", Integer, nullable=False, default=1),
    Column("must_change_password", Integer, nullable=False, default=0),
    CheckConstraint("role IN ('administrator','planner','viewer')"))
sessions = Table("auth_sessions", metadata,
    Column("digest", String, primary_key=True), Column("user_id", ForeignKey("auth_users.id", ondelete="CASCADE")),
    Column("created_at", Float, nullable=False), Column("last_seen", Float, nullable=False),
    Column("expires_at", Float, nullable=False, index=True))
attempts = Table("auth_login_attempts", metadata,
    Column("key", String, primary_key=True), Column("count", Integer, nullable=False),
    Column("until", Float, nullable=False))

memberships = Table("institution_memberships", metadata,
    Column("user_id", ForeignKey("auth_users.id", ondelete="CASCADE"), primary_key=True),
    Column("institution_id", ForeignKey("institutions.institution_id"), nullable=False),
    Column("role", String, nullable=False), Column("scopes", JSON, nullable=False),
    Column("active", Integer, nullable=False, default=1),
    Column("faculty_id", String), Column("batch_ids", JSON, nullable=False, default=list),
    CheckConstraint("role IN ('administrator','planner','viewer','teacher','student','platform_super_admin')"),
    ForeignKeyConstraint(["institution_id", "faculty_id"], ["faculty.institution_id", "faculty.id"]))

invitations = Table("institution_invitations", metadata,
    Column("id", String, primary_key=True), Column("institution_id", ForeignKey("institutions.institution_id"), nullable=False),
    Column("email", String, nullable=False), Column("role", String, nullable=False),
    Column("scopes", JSON, nullable=False), Column("faculty_id", String), Column("batch_ids", JSON, nullable=False),
    Column("digest", String, unique=True, nullable=False), Column("expires_at", Float, nullable=False),
    Column("used_at", Float), Column("revoked_at", Float), Column("inviter_id", ForeignKey("auth_users.id"), nullable=False),
    CheckConstraint("role IN ('planner','teacher','student','viewer')"),
    ForeignKeyConstraint(["institution_id", "faculty_id"], ["faculty.institution_id", "faculty.id"]))

# Public accounts can authenticate before choosing an institution.
profiles = Table("auth_profiles", metadata,
    Column("user_id", ForeignKey("auth_users.id", ondelete="CASCADE"), primary_key=True),
    Column("name", String, nullable=False))
