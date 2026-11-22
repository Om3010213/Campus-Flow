> Current flow (2026-11-11): direct Name/Email/Password signup, immediate login and explicit
> School/College workspace creation. No OTP, SMTP or email verification. Accounts start
> unassigned with no academic privileges. See ONBOARDING.md for current instructions.
> Existing hashing, sessions, CSRF, throttling and tenant/role checks remain enforced.

# Current multi-institution authentication

Schema v5 resolves authorization from active institution memberships on every request.
Administrators manage only their own institution; planners manage requirements/drafts;
teacher and student accounts receive personal published views; viewers retain explicit
published-scope grants. Platform operators are local-only and have no academic access.
Use [verified onboarding](ONBOARDING.md) for School/College registration and invitations,
[architecture](INSTITUTION_SCHEMA.md) for tenant boundaries and [operations](OPERATIONS.md)
for provisioning/recovery and production gates. Earlier single-workspace role descriptions
below are historical; v5 membership and institution constraints also apply.

# Authentication and authorization

This describes the existing **single-college** application. The newer
[registration preview](ONBOARDING.md) verifies pending email addresses but cannot
create login accounts until shared-database college isolation is implemented.

## Local setup (PowerShell, repository root)

```powershell
.venv\Scripts\python -m pip install -e ".[api,product,dev,api-test]"
.venv\Scripts\python -m campusflow.auth.cli create-admin admin
.venv\Scripts\python -m uvicorn campusflow.api.main:app --host 127.0.0.1 --port 8000
```

The setup command prompts twice for a 12–128 character password without echoing it
or placing it in shell history. It refuses to create another initial administrator.
There are no default credentials or public registration endpoints. Add `cp-sat` to
the installation extras if wanted; authentication does not change either solver.

In another terminal:

```powershell
pnpm.cmd --dir frontend install --frozen-lockfile
pnpm.cmd --dir frontend dev
```

Open http://127.0.0.1:5173 and sign in. Use **Users & access** to create users,
set roles and exact academic scope grants (for example `College`), or disable
accounts. Newly provisioned accounts must replace their temporary password before
accessing the workspace. Deliver temporary passwords privately. All users can
change their own password under Settings and sign out from the header.

Use the same hostname for frontend and backend when opening administrator-only
Swagger documentation at http://127.0.0.1:8000/docs. State-changing API calls require
the session cookie and `X-CSRF-Token`; Swagger does not automatically add this header.

## Permissions

| Capability | Administrator | Planner | Viewer |
|---|---|---|---|
| Manage users, roles, faculty, subjects, rooms, batches, calendar | Yes | No | No |
| Read catalog and manage weekly requirements | Yes | Yes | No |
| Generate, edit, validate, duplicate and reschedule drafts | All scopes | Granted scopes | No |
| Publish, archive and delete protected versions | Yes | No | No |
| View published timetables and exports/reports | All scopes | Granted scopes | Granted scopes |
| View drafts and scheduling jobs | All scopes | Granted scopes | No |
| Change own password and sign out | Yes | Yes | Yes |

The backend denies unauthorized requests independently of navigation. Unauthenticated
requests receive 401; insufficient role, scope or CSRF receives 403. Scope grants are
case-sensitive names, with no wildcard. Empty grants expose no saved schedules.
Viewers receive only published versions and relevant display records, without
faculty availability or preferred working hours. Planners cannot manage any users.
The last active administrator cannot be disabled or demoted through the API.

**Scope boundary:** the current academic catalog and weekly requirements are global
to this single college. Planners may edit all weekly requirements and can run the
stateless solver on supplied data. Grants restrict persisted timetable/job access,
not departments within the catalog. This is not a multi-tenant isolation model.

## Sessions and API flow

```mermaid
sequenceDiagram
    participant B as Browser
    participant A as FastAPI
    participant D as SQLite
    B->>A: GET /api/auth/session
    A->>D: Store anonymous session digest
    A-->>B: HttpOnly cookie + CSRF token
    B->>A: POST /api/auth/login + cookie + CSRF
    A->>D: Reserve throttle attempt; verify Argon2id hash
    A-->>B: Rotated session cookie + new CSRF token + role
    B->>A: Protected request (+ CSRF for mutations)
    A->>D: Check expiry, active account, role and scope
    A-->>B: Authorized result or 401/403
    B->>A: POST /api/auth/logout + CSRF
    A->>D: Delete session digest
    A-->>B: Clear cookie
```

Endpoints: `GET /api/auth/session`, `POST /api/auth/login`, `POST /api/auth/logout`,
`POST /api/auth/password`, administrator-only `GET/POST /api/auth/users` and
`PUT /api/auth/users/{id}`. Password changes require `current_password` and
`new_password`. Bootstrap and login are public but login still requires CSRF.
Health is public; other APIs and documentation require authentication.

Passwords use Argon2id (64 MiB, three iterations, one lane). Session cookies contain
random 256-bit tokens; SQLite stores only HMAC digests. CSRF tokens are bound to
the session and held in frontend memory. Sessions expire after eight hours absolute
or thirty minutes idle (activity updates have up to one minute granularity).
Login rotates the session. Password changes/reset and role/scope/active changes
revoke existing sessions. Logout revokes the current session.

Login attempts are reserved atomically in SQLite before expensive hashing: five
per normalized username and thirty per client IP in fifteen minutes, including
successful logins. Password verification for changes has separate counters.
Throttled requests return 429 and `Retry-After: 900`. Counters expire automatically;
unknown users receive the same login error and dummy password verification.

## Database and recovery

Startup/setup applies additive migration 2: `auth_users`, `auth_sessions`, and
`auth_login_attempts`. Existing academic tables and data are not rebuilt. Keep a
backup before upgrades; stop the service before copying SQLite files, or use the
SQLite backup API. Default database remains `data/campusflow.db`; an existing
`CAMPUSFLOW_DATABASE_URL` is respected by both server and CLI.

Lost-password recovery requires trusted local access to the server:

```powershell
.venv\Scripts\python -m campusflow.auth.cli reset-password USERNAME
```

This prompts for a temporary password, revokes all sessions, and forces replacement
at next login. It does not reactivate disabled accounts. There is no public reset
token endpoint or email service yet. Restrict operating-system access to the database,
backups and CLI; anyone who can modify the database is already a trusted operator.

## Environment and deployment preparation

Development defaults allow loopback origins only, HttpOnly `SameSite=Strict` cookies,
and plain HTTP exclusively for local use. Keep Uvicorn bound to `127.0.0.1`. A random
development secret is generated at startup, so restarting signs users out unless
`CAMPUSFLOW_SESSION_SECRET` is explicitly set. Do not commit secrets; `.env` files
are ignored, and the application does not automatically load them.

Production configuration must supply:

- `CAMPUSFLOW_ENV=production`.
- `CAMPUSFLOW_SESSION_SECRET`: a securely generated random secret of at least 32
  characters (for example, `python -c "import secrets; print(secrets.token_hex(32))"`).
- `CAMPUSFLOW_ALLOWED_ORIGINS`: explicit comma-separated HTTPS origins, no wildcards
  or URL paths, including the actual frontend origin.

Production refuses HTTP, uses `__Host-campusflow` Secure/HttpOnly/SameSite=Strict
cookies and HSTS. CSRF protects every mutation, including login and logout, with
additional Origin checks. Deploy frontend and `/api` behind the same HTTPS origin;
the current frontend uses same-origin fetch and Strict cookies. Only trust forwarded
headers from the known reverse proxy, never arbitrary clients. Start one Uvicorn
worker and protect SQLite/backups with filesystem permissions.

No public deployment is performed by this phase. Before deployment, configure and
test TLS/proxy forwarding, backups/restores, secret storage, request/body limits,
edge rate limits and monitoring. Application throttling alone does not prevent
distributed denial of service or deliberate account lockouts; anonymous bootstrap
requests can create database rows. There is no MFA, audit trail, breached-password
screening, or cross-tenant row isolation. Already-running requests/jobs are not
cancelled when a session is revoked. Session revocation applies to subsequent checks.

Next optional phase: verified email enrollment and recovery using expiring,
single-use hashed tokens, generic account responses, resend limits and trusted
delivery. It must never grant administrator privileges from public registration.
Then perform a deployment security review and staging tests before public release.

## Verification

```powershell
.venv\Scripts\python -m pytest -q
pnpm.cmd --dir frontend test
pnpm.cmd --dir frontend run build
pnpm.cmd --dir frontend test:e2e
```

The browser test provisions a disposable account only inside its temporary database;
it never creates test credentials in the real workspace. It requires local Chrome.

Design references: [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
and [CSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
