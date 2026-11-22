"""Rehearse tenant migration on a NEW copy. Source is opened read-only."""
import argparse
import json
import sqlite3
from pathlib import Path
from sqlalchemy import create_engine
from campusflow.product.migrations import upgrade


def snapshot(conn):
    result={}
    for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        quoted='"'+name.replace('"','""')+'"'
        columns=[r[1] for r in conn.execute('PRAGMA table_info('+quoted+')')]
        result[name]=(columns,conn.execute('SELECT * FROM '+quoted).fetchall())
    return result


def rehearse(source,target):
    source=Path(source).resolve();target=Path(target).resolve()
    if source==target or target.exists(): raise ValueError('Destination must be a new disposable copy')
    target.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as original:
        before=snapshot(original)
        with sqlite3.connect(target) as copy: original.backup(copy)
    engine=create_engine('sqlite:///'+target.as_posix())
    try: upgrade(engine,allow_tenant_upgrade=True)
    finally: engine.dispose()
    preserved={}
    with sqlite3.connect(target) as conn:
        for table,(columns,rows) in before.items():
            if table in ('auth_sessions','schema_versions'): continue
            names=','.join('"'+c.replace('"','""')+'"' for c in columns)
            actual=conn.execute('SELECT '+names+' FROM "'+table+'"').fetchall()
            # Additive legacy institution is expected; original records must survive exactly.
            assert all(row in actual for row in rows),table+' changed existing records'
            preserved[table]=len(rows)
        integrity=conn.execute('PRAGMA integrity_check').fetchone()[0]
        violations=conn.execute('PRAGMA foreign_key_check').fetchall()
        assert integrity=='ok' and not violations
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as original:
        assert snapshot(original)==before,'Source changed during rehearsal'
    return {'source_unchanged':True,'integrity':integrity,'foreign_key_violations':len(violations),'preserved_counts':preserved,'copy':str(target),'session_policy':'Legacy sessions revoked in copy; sign in again','rollback':'Source remains unchanged. Stop application and restore a verified pre-cutover SQLite backup if an approved future cutover fails.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('copy',type=Path)
    args=parser.parse_args()
    print(json.dumps(rehearse(args.source,args.copy),indent=2))
