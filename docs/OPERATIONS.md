# Operations and deployment gates

## Local verification

```powershell
.venv\Scripts\python -m pytest -q
pnpm.cmd --dir frontend test
pnpm.cmd --dir frontend run build
pnpm.cmd --dir frontend test:e2e
```

Browser tests use temporary SQLite databases, Chrome, API port 8001 and Vite 5174, with
no SMTP dependency. They never use `data/campusflow.db`. Test artifacts and screenshots
are under `frontend/test-results`. The regular local launcher is documented in ONBOARDING.md.

Optional local provisioning on the chosen v5 database:

```powershell
$env:CAMPUSFLOW_DATABASE_URL = 'sqlite:///D:/My_Codex/CampusFlow/data/development-v5.db'
.venv\Scripts\python -m campusflow.auth.cli create-admin initial-admin
# Only a trusted local operator may provision a platform role:
.venv\Scripts\python -m campusflow.auth.cli create-platform-admin platform-operator
.venv\Scripts\python -m campusflow.auth.cli reset-password account-name
```

Passwords are prompted privately, never command arguments. Public signup cannot create
platform operators. Platform directory/status endpoints are `/api/platform/institutions`
and `PUT /api/platform/institutions/{id}/status`. Platform accounts cannot access academic
records. Institution administrators cannot edit platform memberships.

## Free deployment on Render and Vercel

1. Import `main` into a Vercel Hobby workspace, select `frontend` as the root directory and reserve
   the production domain. The project uses Node 22, pnpm from `packageManager`,
   `pnpm run build` and the Vite `dist` directory.
2. Create a Render Blueprint from `render.yaml` in a workspace without a payment
   method so exceeding usage limits cannot incur overage charges. Enter the full
   Vercel HTTPS origin as `CAMPUSFLOW_ALLOWED_ORIGINS`. Render generates the
   session secret and injects the internal database URL. If Render provides
   narrower load balancer addresses, use them for `FORWARDED_ALLOW_IPS`.
3. Set `CAMPUSFLOW_API_ORIGIN` in Vercel to the Render HTTPS origin without a
   trailing slash, then deploy. Vercel routes `/api/*` to Render and serves
   direct visits to React routes from `index.html`. Browser API requests stay on
   the Vercel origin so the host-only Secure session cookie works. If the
   production domain changes, update the Render origin allowlist as well.
4. Confirm `/api/ready` on Render and through Vercel. In a fresh browser session,
   verify signup, sign-in, workspace creation, scheduling and sign-out. Reopen
   the app after a restart to verify the workspace and session persist.

Startup initializes an empty PostgreSQL database and applies schema updates.
SQLite remains the local default. Deployments require an explicit database URL
in production mode. For an existing SQLite installation, use the separate
[legacy migration procedure](MULTI_COLLEGE_MIGRATION.md) on a backup before
planning any data transfer. The Blueprint starts with a fresh database.

The free web service sleeps after 15 minutes of inactivity and its local filesystem
is ephemeral. Its separate 1 GB PostgreSQL database survives web-service restarts,
expires after 30 days, and has no managed backups. Export any needed hosted data
with `pg_dump` before expiration. Render deletes an expired database after a
14-day grace period. Invitation links are shared privately and signup requires no
SMTP. Render Free does not include a shell for operator-led password recovery.

## Current limits

Single API process; two concurrent solver jobs globally, maximum 500 requested sessions
and 30-second solver limit. Jobs are marked interrupted after restart. No distributed
queue, per-institution fair-use quota or horizontally scaled session/throttle service.
Invitations are manually shared single-use links; no mail delivery service is needed. One institution per login
identity; no membership switching. Student batch assignments are validated JSON lists;
department/year names retain compatible free-text fields. MFA, public email password recovery,
durable security audit trails and independent penetration testing remain future work.
