"""Ordered schema migrations. Add new numbered upgrades; never rebuild user data."""
from sqlalchemy import select, inspect, text


def _create_tenant_schema(conn):
    import time
    from .database import metadata, schema_versions
    from campusflow.auth import tables  # Register the authentication tables on metadata.
    from campusflow.auth.onboarding_tables import institutions
    from campusflow.tenancy import LEGACY

    metadata.create_all(conn)
    conn.execute(institutions.insert().values(institution_id=LEGACY, institution_name="Legacy College",
        institution_type="COLLEGE", created_at=time.time(), status="ACTIVE"))
    conn.execute(schema_versions.insert(), [{"version": version} for version in range(1, 6)])


def _upgrade_v5(engine, *, allow_tenant_upgrade=False):
    """Fresh databases use v5. Existing databases require explicit offline approval.

    No automatic live cutover: ordinary API startup refuses a pre-v5 database.
    All table rebuilds are inside an explicit SQLite transaction with rollback.
    """
    import json
    import time
    from sqlalchemy import JSON
    from .database import metadata, schema_versions, TENANT_TABLES
    from campusflow.auth.tables import users, memberships, sessions
    from campusflow.auth.onboarding_tables import institutions
    from campusflow.tenancy import LEGACY
    existing = inspect(engine).get_table_names()
    if not existing:
        with engine.begin() as conn:
            _create_tenant_schema(conn)
        return
    with engine.connect() as conn:
        versions = set(conn.execute(select(schema_versions.c.version)).scalars())
    if versions - set(range(1, 7)):
        raise RuntimeError("Database schema is newer than this application")
    if 5 in versions:
        return
    if not allow_tenant_upgrade:
        raise RuntimeError("Institution migration required. Live cutover is disabled; rehearse on a copy and obtain approval before running the migration command.")
    if engine.dialect.name != "sqlite":
        raise RuntimeError("Legacy cutover currently supports SQLite; new schemas are database-portable")
    _upgrade_legacy(engine)
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        conn.commit()
        try:
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            available = set(inspect(conn).get_table_names())
            old = {name: [dict(r) for r in conn.exec_driver_sql(f'SELECT * FROM "{name}"').mappings()]
                   for name in TENANT_TABLES if name in available}
            if not conn.execute(select(institutions.c.institution_id).where(institutions.c.institution_id == LEGACY)).first():
                conn.execute(institutions.insert().values(institution_id=LEGACY, institution_name="Legacy College",
                    institution_type="COLLEGE", created_at=time.time(), status="ACTIVE"))
            ordered = [t for t in metadata.sorted_tables if t.name in TENANT_TABLES]
            for table in reversed(ordered):
                if table.name in available:
                    table.drop(conn)
            for table in ordered:
                table.create(conn)
                for row in old.get(table.name, []):
                    values = dict(row, institution_id=LEGACY)
                    for key, value in list(values.items()):
                        if isinstance(table.c[key].type, JSON) and isinstance(value, str):
                            values[key] = json.loads(value)
                    conn.execute(table.insert().values(**values))
            memberships.create(conn, checkfirst=True)
            from campusflow.auth.tables import invitations
            invitations.create(conn, checkfirst=True)
            for user in conn.execute(select(users)).mappings():
                conn.execute(memberships.insert().values(user_id=user["id"], institution_id=LEGACY,
                    role=user["role"], scopes=user["scopes"], active=user["active"], batch_ids=[]))
            # Pre-membership sessions cannot carry an approved institution context.
            conn.execute(sessions.delete())
            if conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("Migration failed referential-integrity verification")
            conn.execute(schema_versions.insert().values(version=5))
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")
            conn.commit()


def _upgrade_legacy(engine):
    from .database import metadata, schema_versions
    with engine.begin() as conn:
        schema_versions.create(conn, checkfirst=True)
        versions = set(conn.execute(select(schema_versions.c.version)).scalars())
        if versions - {1, 2, 3, 4}:
            raise RuntimeError("Database schema is newer than this application")
        if 1 not in versions:
            metadata.create_all(conn)
            conn.execute(schema_versions.insert().values(version=1))
        if 2 not in versions:
            from campusflow.auth.tables import users, sessions, attempts
            for table in (users, sessions, attempts):
                table.create(conn, checkfirst=True)
            conn.execute(schema_versions.insert().values(version=2))
        if 3 not in versions:
            from campusflow.auth.onboarding_tables import registrations, verification_tokens
            for table in (registrations, verification_tokens):
                table.create(conn, checkfirst=True)
            conn.execute(schema_versions.insert().values(version=3))
        if 4 not in versions:
            from campusflow.auth.onboarding_tables import institutions
            institutions.create(conn, checkfirst=True)
            columns = {column["name"] for column in inspect(conn).get_columns("college_registrations")}
            if "institution_name" not in columns:
                conn.execute(text("ALTER TABLE college_registrations ADD COLUMN institution_name VARCHAR NOT NULL DEFAULT ''"))
            if "institution_type" not in columns:
                conn.execute(text("ALTER TABLE college_registrations ADD COLUMN institution_type VARCHAR NOT NULL DEFAULT 'COLLEGE' CHECK (institution_type IN ('SCHOOL','COLLEGE'))"))
            conn.execute(text("UPDATE college_registrations SET institution_name = college_name WHERE institution_name = ''"))
            conn.execute(schema_versions.insert().values(version=4))


def _upgrade_v6(conn):
    from campusflow.auth.tables import profiles
    from .database import schema_versions
    if not conn.execute(select(schema_versions.c.version).where(schema_versions.c.version == 6)).first():
        profiles.create(conn, checkfirst=True)
        conn.execute(schema_versions.insert().values(version=6))


def _upgrade_postgres(engine):
    from .database import lock_transaction, schema_versions

    with engine.begin() as conn:
        lock_transaction(conn)
        existing = inspect(conn).get_table_names()
        if not existing:
            _create_tenant_schema(conn)
        else:
            if schema_versions.name not in existing:
                raise RuntimeError("PostgreSQL target must be empty or contain a CampusFlow schema")
            versions = set(conn.execute(select(schema_versions.c.version)).scalars())
            if versions - set(range(1, 7)):
                raise RuntimeError("Database schema is newer than this application")
            if 5 not in versions:
                raise RuntimeError("Legacy schema cutover must be completed on SQLite before import")
        _upgrade_v6(conn)


def upgrade(engine, *, allow_tenant_upgrade=False):
    """Additive v6 account profiles; pre-tenant cutover still requires approval."""
    if engine.dialect.name == "postgresql":
        _upgrade_postgres(engine)
        return
    _upgrade_v5(engine, allow_tenant_upgrade=allow_tenant_upgrade)
    with engine.begin() as conn:
        _upgrade_v6(conn)
