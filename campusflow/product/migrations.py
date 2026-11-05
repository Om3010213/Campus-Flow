"""Ordered schema migrations. Add new numbered upgrades; never rebuild user data."""
from sqlalchemy import select


def upgrade(engine):
    from .database import metadata, schema_versions
    with engine.begin() as conn:
        schema_versions.create(conn, checkfirst=True)
        versions = set(conn.execute(select(schema_versions.c.version)).scalars())
        if versions - {1}:
            raise RuntimeError("Database schema is newer than this application")
        if 1 not in versions:
            metadata.create_all(conn)
            conn.execute(schema_versions.insert().values(version=1))
