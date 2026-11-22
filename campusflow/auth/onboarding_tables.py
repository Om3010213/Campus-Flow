"""Pending identities are deliberately separate from application users."""
from sqlalchemy import Table, Column, String, Float, ForeignKey, CheckConstraint
from campusflow.product.database import metadata

registrations = Table("college_registrations", metadata,
    Column("id", String, primary_key=True),
    Column("email", String, nullable=False, unique=True),
    Column("name", String, nullable=False),
    Column("college_name", String, nullable=False),
    Column("institution_name", String, nullable=False, server_default=""),
    Column("institution_type", String, CheckConstraint("institution_type IN ('SCHOOL','COLLEGE')"), nullable=False, server_default="COLLEGE"),
    Column("password_hash", String, nullable=False),
    Column("created_at", Float, nullable=False),
    Column("verified_at", Float))

verification_tokens = Table("email_verification_tokens", metadata,
    Column("digest", String, primary_key=True),
    Column("registration_id", ForeignKey("college_registrations.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("expires_at", Float, nullable=False),
    Column("used_at", Float))

# Institutions are the shared-database tenant boundary.
institutions = Table("institutions", metadata,
    Column("institution_id", String, primary_key=True),
    Column("institution_name", String, nullable=False),
    Column("institution_type", String, nullable=False),
    Column("created_at", Float, nullable=False),
    Column("status", String, nullable=False),
    CheckConstraint("institution_type IN ('SCHOOL','COLLEGE')"),
    CheckConstraint("status IN ('PENDING','ACTIVE','SUSPENDED')"))
