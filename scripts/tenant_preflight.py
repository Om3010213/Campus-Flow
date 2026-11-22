"""Read-only inventory for the proposed shared-database tenant migration."""
import argparse
import json
import sqlite3
from pathlib import Path


def inspect(path: Path) -> dict:
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        counts = {}
        for name in tables:
            quoted = '"' + name.replace('"', '""') + '"'
            counts[name] = conn.execute(f"SELECT count(*) FROM {quoted}").fetchone()[0]
        return {"read_only": True, "schema_versions": [r[0] for r in conn.execute("SELECT version FROM schema_versions ORDER BY version")],
                "row_counts": counts, "integrity": conn.execute("PRAGMA integrity_check").fetchone()[0],
                "foreign_key_violations": len(conn.execute("PRAGMA foreign_key_check").fetchall()),
                "tenant_schema_present": 5 in [r[0] for r in conn.execute("SELECT version FROM schema_versions")],
                "required_review": "docs/MULTI_COLLEGE_MIGRATION.md"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, nargs="?", default=Path("data/campusflow.db"))
    print(json.dumps(inspect(parser.parse_args().database), indent=2))
