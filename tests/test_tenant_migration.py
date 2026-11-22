"""Synthetic legacy schema: preservation, composite FKs and transactional rollback."""
import pytest
from sqlalchemy import create_engine,event,text,select
from campusflow.product import database as db
from campusflow.product.migrations import upgrade
from campusflow.tenancy import LEGACY


def legacy(engine):
    # Independent old DDL: do not accidentally test current metadata as an old schema.
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE schema_versions (version INTEGER PRIMARY KEY)')
        conn.exec_driver_sql('INSERT INTO schema_versions VALUES (1)')
        conn.exec_driver_sql('CREATE TABLE faculty (id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, department VARCHAR NOT NULL, max_daily_minutes INTEGER NOT NULL, preferred_start VARCHAR NOT NULL, preferred_end VARCHAR NOT NULL, restricted INTEGER NOT NULL)')
        conn.exec_driver_sql("INSERT INTO faculty VALUES ('F1','Preserved','Science',240,'09:00','16:00',0)")
    from campusflow.product.migrations import _upgrade_legacy
    _upgrade_legacy(engine)


def test_rehearsal_and_rollback(tmp_path):
    engine=create_engine('sqlite:///'+(tmp_path/'migration.db').as_posix())
    legacy(engine)
    def fail(conn,cursor,statement,parameters,context,many):
        if statement.startswith('INSERT INTO schema_versions') and parameters==(5,):
            raise RuntimeError('Injected cutover failure')
    event.listen(engine,'before_cursor_execute',fail)
    with pytest.raises(RuntimeError,match='Injected'):
        upgrade(engine,allow_tenant_upgrade=True)
    event.remove(engine,'before_cursor_execute',fail)
    with engine.connect() as conn:
        assert conn.exec_driver_sql('SELECT * FROM faculty').one()==('F1','Preserved','Science',240,'09:00','16:00',0)
        assert 5 not in conn.exec_driver_sql('SELECT version FROM schema_versions').scalars()
        assert 'institution_id' not in [r[1] for r in conn.exec_driver_sql('PRAGMA table_info(faculty)')]
    upgrade(engine,allow_tenant_upgrade=True)
    upgrade(engine)
    with engine.connect() as conn:
        assert conn.execute(select(db.faculty.c.institution_id)).scalar_one()==LEGACY
        assert conn.exec_driver_sql('PRAGMA foreign_key_check').fetchall()==[]
    engine.dispose()


def test_v6_additive_profile_migration_preserves_v5_accounts(tmp_path):
    from campusflow.auth.tables import users,memberships,profiles,sessions
    from campusflow.auth.service import create_user
    engine=create_engine('sqlite:///'+(tmp_path/'v5.db').as_posix())
    upgrade(engine)
    with engine.begin() as conn:
        account=create_user(conn,'legacy-owner','Legacy migration passphrase!','administrator',must_change=False,tenant=LEGACY)
        conn.execute(sessions.insert().values(digest='preserved-digest',user_id=account['id'],created_at=1,last_seen=1,expires_at=9999999999))
        profiles.drop(conn)
        conn.execute(db.schema_versions.delete().where(db.schema_versions.c.version==6))
        before=[dict(r) for r in conn.execute(select(users)).mappings()]
    upgrade(engine)
    upgrade(engine)
    with engine.connect() as conn:
        assert [dict(r) for r in conn.execute(select(users)).mappings()]==before
        assert conn.execute(select(memberships.c.user_id)).scalar_one()==account['id']
        assert conn.execute(select(sessions.c.digest)).scalar_one()=='preserved-digest'
        assert conn.execute(select(profiles)).all()==[]
        assert conn.exec_driver_sql('PRAGMA foreign_key_check').fetchall()==[]
    engine.dispose()
