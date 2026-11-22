# Shared-database migration v5

Live cutover requires explicit owner approval. API startup refuses databases below v5;
it never rebuilds existing academic tables automatically. New empty development/test
databases initialize directly at v5. Never point development tests at the live database.

## Rehearsal performed 2026-11-08

Read-only source: `data/campusflow.db`. New disposable output:
`data/rehearsal-20261108.db`. All original column values were compared after migration.
Preserved: 3 faculty, 3 subjects, 3 rooms, 2 batches, 4 assignments, 6 requirements,
1 academic settings row, 3 jobs, 2 versions, 31 sessions, 1 pending registration,
1 verification token and 2 throttle rows. Source had no auth users or institutions.
SQLite integrity check: `ok`; foreign-key violations: 0; source snapshot unchanged.

A synthetic v1 fixture also verifies preserved faculty IDs/values, guarded startup,
idempotency and FK integrity. An injected failure at the final v5 marker demonstrates
transactional rollback of tenant table rebuilding, restoring the original columns and rows.

## Reproduce on a new copy

```powershell
.venv\Scripts\python -m scripts.rehearse_tenant_migration data/campusflow.db data/rehearsal-new.db
```

The destination must not exist. SQLite's backup API reads the source in read-only mode
and makes a consistent copy. Rehearsal compares original records and checks foreign keys.
It never applies the migration to its source. Keep copies private: they contain data,
password hashes and tokens. User IDs and academic IDs are unchanged. Existing accounts
receive an active legacy COLLEGE membership. Legacy sessions are revoked in the copy.

## Future approved cutover / rollback procedure

1. Obtain explicit approval and stop all API/job writers. Record application revision.
2. Use SQLite backup to create a new timestamped pre-cutover backup; verify integrity.
3. Rehearse again on a fresh copy of that exact backup and compare every original column.
4. Only after approval, configure the application to use the verified migrated copy.
   Keep the original database untouched; do not delete or overwrite it.
5. Start one API process, sign in, verify counts, roles, scheduling and exports before
   admitting writes. Existing sessions must sign in again.
6. For rollback before new writes, stop API and point its database URL back to the
   original with the compatible pre-v5 application revision. If new writes occurred,
   preserve both files and reconcile new records; never silently discard post-cutover work.

Legacy migration steps below v4 may commit their additive schema upgrades separately;
the tested atomic rollback covers the v4-to-v5 tenant rebuild. Use copy-and-switch for
all versions so the original is always available. PostgreSQL cutover is not implemented.
