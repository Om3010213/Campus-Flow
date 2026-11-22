# Email + Password authentication — 2026-11-11

This section supersedes earlier mandatory email-verification milestones below.

## Approved database reset

The owner approved resetting ONLY `D:\My_Codex\CampusFlow\data\development-v5.db`.
No development API process/listener was running before reset. The existing backup
`data/backups/development-v5-before-email-password-20261111.db` matched the database
logically and passed integrity verification immediately before deletion. The approved
file was recreated using existing initialization/migrations and upgraded additively to v6.
Final checks: 0 users, 0 pending registrations, 0 timetables; integrity ok; 0 FK violations.
All other existing databases/backups were compared by SHA-256 and remain byte-for-byte
unchanged. The original data/campusflow.db remains untouched. No deployment or push.
Audit hashes and paths: ignored local `data/email-password-reset-audit.json`.

## Implementation

- Name/Email/Password public signup, Argon2id hashing and immediate password login.
- No SMTP, OTP or verification email dependency. Old verification endpoints retired;
  old frontend verification links lead to sign-in. Historical tables/code retained.
- New `auth_profiles` table in additive migration 6 stores signup names. Public accounts
  have no membership or administrative rights; computed role is unassigned.
- Explicit authenticated School/College creation atomically grants administrator rights
  only in the newly created institution. Existing membership and injected institution IDs
  are rejected. Disabled memberships cannot fall back to unassigned access.
- Cookie sessions, CSRF, throttling, RBAC, personal timetable views and tenant isolation
  retained. Session rotation/revocation occurs on workspace activation.
- Private single-use invitation links replace automatic mail delivery. Existing accounts
  must authenticate as the invited identity; acceptance revokes old sessions.
- Login routes to dashboard/onboarding; authenticated signup/sign-in routes return home;
  logout goes to sign-in. Explicit waits in browser tests avoid aborted login requests.
- Local launcher uses only selected development DB + API; no email receiver. Browser
  tests use disposable databases and no SMTP server.

## Final stabilization verification — 2026-11-11

- Full backend suite: **185 passed, 0 failed**, 256.31 seconds.
- Frontend unit tests: **15 passed, 0 failed**.
- Playwright Chrome workflows: **3 passed, 0 failed** in 1.3 minutes. Both School
  and College cover direct signup, login, explicit workspace creation, dashboard,
  scheduling/publication, invitations, role restrictions and logout. The legacy
  workflow verifies password-change completion before navigating, plus editing,
  publishing, reports, exports and viewer permissions.
- Production frontend build passed; Git diff whitespace check passed.
- Security and migration tests cover Argon2id, revocable/expiring sessions, CSRF,
  throttling, unprivileged signup, role checks, tenant isolation and additive v6
  preservation. No OTP, SMTP service or verification email is required.
- All seven existing SQLite databases/backups are byte-for-byte unchanged during
  this continuation. No database reset, migration of user databases, deployment,
  commit or push was performed.
- The password-change wait was already present in the recovered uncommitted files;
  no application or test code required further changes. Only this stale progress
  checkpoint was updated after verification.
- Git remains on main at 713b08e with the prior modified/untracked work retained.
- One upstream Starlette TestClient/httpx deprecation warning remains; no failing tests.

## Startup / first administrator

From repository root:
`.venv\Scripts\python scripts/dev_onboarding.py --database data/development-v5.db`
In another terminal: `pnpm.cmd --dir frontend dev`.
Open http://127.0.0.1:5173/sign-up, register, sign in, select School/College and its name,
then click Create workspace. This grants institution admin rights only in your new workspace.
See docs/ONBOARDING.md for details; no SMTP settings or paid services are needed.

## Remaining limits

Email addresses are unverified identifiers. Invite links must be shared securely. One
institution per identity; local password recovery command; no public email recovery.
Single API process/SQLite with two concurrent solver jobs. Production still requires
HTTPS, private stable secrets, explicit origins and operational/security review.
No further database reset or live cutover is necessary for this development workflow.

## Historical record

# Current progress — 2026-11-08

This section supersedes historical preview-only milestones below.

## Recovered versus completed now

Recovered unfinished v5 tenant SQL boundary, composite academic foreign keys,
trusted background-job context, membership/activation/invitation backend code and
partially adapted frontend. The recovered frontend did not build and tests still
expected verification without activation.

Completed this session: catalog TypeScript/encoding and school-default fixes; actual
School/College activation regression tests; teacher/student invitation UI and acceptance;
personal published timetable/report/export checks; platform operator directory/status
and local provisioning; protected platform membership management; school period-change
validation; safe separate development DB default; SQL alias scoping and nested-query
fail-closed behavior; migration rehearsal tooling and rollback tests; updated onboarding,
architecture, schema, operations and cutover documentation.

## Final executed verification

- **190 backend tests passed, 0 failed** (full suite, 257.28 seconds).
- **15 frontend tests passed, 0 failed**.
- **3 real Chrome browser workflows passed, 0 failed** (55.4 seconds): School and
  College signup -> local SMTP verification -> login -> adaptive catalog -> generation
  -> publication -> invitation acceptance -> teacher/student restricted published view;
  plus legacy administrator editing, validation, publishing, reporting, PDF export,
  responsive layout, viewer permissions and password change.
- Production frontend build passed. Git diff whitespace check passed.
- Both existing CSP and CP-SAT engines passed School/College scheduling tests.
- Security coverage includes cross-institution catalog/job/version/report/export/user/
  invitation denial, duplicate academic IDs across institutions, personal teacher/student
  views, token replay/rotation/expiry/revocation, role injection, platform operator restrictions,
  trusted SQL alias scoping, rejected nested queries and composite foreign-key enforcement.
- Initial stale-preview assertions, frontend typing/encoding errors, browser dropdown
  selector and login-navigation timing failures were fixed; no known remaining test failures.
- One upstream Starlette TestClient/httpx deprecation warning remains.
- Rehearsal `data/campusflow.db` -> `data/rehearsal-20261108.db`: all original columns
  preserved, 2 versions/31 sessions retained, integrity ok, 0 FK violations, source unchanged.
- Injected migration failure rolled back the tenant table rebuild on a synthetic legacy copy.
- Final read-only live preflight confirms versions 1-4 and unchanged counts, integrity ok,
  0 FK violations. No live database cutover, production deployment or GitHub push occurred.

## Remaining gates and limitations

Safe implementation and local verification are complete. Next action requires the owner's
explicit approval: create a fresh verified migration copy and switch the local backend to
it while retaining the original database for rollback. Do not apply this automatically.
Production/staging exposure additionally needs deployment approval, HTTPS/origin/secrets,
real SMTP inbox-delivery verification, backup/restore operations and security/load review.
See docs/OPERATIONS.md for known limits: single API process/two jobs, synchronous SMTP,
one institution per identity, application-enforced tenancy, JSON batch assignments and
compatible free-text department/year labels. PostgreSQL and public password-recovery email
remain unimplemented future work. No claim of production readiness is made.

## Files changed in this continuation

Backend: tenancy boundary; auth onboarding/invitations/memberships/permissions/personal
views/platform router/local CLI; API router integration; product catalog/settings/routes/
seed; migration tests. Frontend: Catalog, Dashboard, App, Users, Onboarding, new Invitations
and Platform components, updated onboarding unit/browser tests. Tooling: separate-DB local
launcher, tenant preflight, new rehearse_tenant_migration script. Tests: new test_tenancy.py
and test_tenant_migration.py, updated old migration/preview expectations. Documentation:
README, PROGRESS, ONBOARDING, INSTITUTION_SCHEMA, MULTI_COLLEGE_MIGRATION, AUTHENTICATION,
MASTER_REQUIREMENTS and new OPERATIONS. All earlier unfinished changes are retained.

## Startup

`.venv\Scripts\python scripts/dev_onboarding.py --database data/development-v5.db`
then in a second terminal `pnpm.cmd --dir frontend dev`. Open `/sign-up` at
http://127.0.0.1:5173. Read local email links in `data/mail-capture`.

## Historical record (superseded by current section)

# Product implementation

## School + college amendment — 2026-11-06

- Integrated the amendment into `docs/MASTER_REQUIREMENTS.md`: one platform, equal
  SCHOOL/COLLEGE support, reusable UI and solvers, institution-neutral isolation,
  adaptive academic models, roles, invitations, and explicit release acceptance gates.
- Registration now offers School/College, Institution Name, Administrator Full Name,
  Official Email, Password and Confirm Password. API validates type and supplied
  confirmation; legacy college_name requests remain compatible and default to COLLEGE.
- Additive migration 4 introduces the `institutions` schema foundation and pending
  registration institution_name/type columns. Legacy registrations are backfilled
  as COLLEGE. No existing academic IDs, values or credentials were changed. Backup:
  `data/backups/pre-institution-20261106-134455.db`. Integrity and FK checks passed.
- Both existing engines were tested with school 40-minute periods, recess/lunch
  gaps, teacher availability, weekly requirements and an 80-minute practical, as
  well as the existing variable-duration college example. No solver was replaced.
- Latest executed verification: **184 backend tests passed**, **15 frontend unit
  tests passed**, **3 browser workflows passed**, production frontend build passed.
  Browser coverage includes actual loopback SMTP verification for SCHOOL and COLLEGE
  plus existing administrator/viewer scheduling, publication and exports.
- Documentation: `MASTER_REQUIREMENTS.md`, `INSTITUTION_SCHEMA.md`, README, onboarding
  and migration review now describe the shared institution architecture. Migration 5
  is reserved for the reviewed tenant-key/membership migration; not executed.
- New files: `campusflow/school_demo.py`, `tests/test_institution_scheduling.py`, the
  master requirements and institution schema/API documents. Existing onboarding,
  mail text, frontend form/tests, migration code and legacy regression expectations
  were updated; all previous work is retained.
- **Still incomplete:** institution activation, tenant-scoped academic relationships,
  membership enforcement, school class/section/class-teacher CRUD, adaptive dashboards,
  invitations, platform super-admin and teacher/student role ownership. The institutions
  table remains an unpopulated foundation, not a security boundary. Neither full school
  nor multi-college workspace E2E completion is claimed. Not staging-ready.
- Local preview launcher remains `.venv\Scripts\python scripts/dev_onboarding.py`;
  frontend `pnpm.cmd --dir frontend dev`. Backend restarted after the migration.
  Development links/sessions without a persistent secret must be reissued after restart.
  No deployment, GitHub push, destructive table rebuild, or registration privilege grant.

## Previous verification milestones

## Local registration configuration fix — 2026-11-06

- Confirmed the live API returned `registration_enabled: false` because the
  development feature flag was off; it was not a missing frontend dependency.
- Added explicit readiness reasons and a frontend loading state. Missing SMTP
  configuration now disables signup with an accurate explanation.
- Added `scripts/dev_onboarding.py`: loopback SMTP capture and FastAPI launcher;
  verifies real SMTP capture before enabling the local email-verification preview.
  It refuses production mode/occupied ports and never resets a database.
- Restarted the identified local backend (no active jobs) and verified through
  Vite on port 5173 that registration is now enabled. Workspace activation is still
  false. The existing database remains intact with 2 versions and 31 sessions;
  integrity check passed with no foreign-key violations.
- Latest executed results: **173 backend tests**, **15 frontend tests**, **2 real
  browser workflows passed**; production frontend build passed. Browser tests
  cover local SMTP verification and existing-account login/logout/scheduling.
- New-college login, workspace creation, invitations and tenant isolation are
  still not implemented. Pending registrations are denied existing-college access;
  this is not a two-college isolation test. **Not ready for multi-college staging.**
- Restart commands: `.venv\Scripts\python scripts/dev_onboarding.py` and, separately,
  `pnpm.cmd --dir frontend dev`. Full configuration is in `docs/ONBOARDING.md`.
  No deployment, push, destructive migration, or email-verification bypass occurred.

## Earlier milestones

- Stage 1 verified: existing APIs and engines present; 120 tests pass. One upstream HTTPX warning. No Git repository configured.
- Stage 2: normalized SQLite tables, versioned migration, catalog CRUD, protected references, seed data implemented. Eight new product tests passed.
- Stage 3: React/TypeScript/Tailwind workspace, responsive navigation, CRUD forms, configuration, dark theme implemented. Production build and five component tests passed.
- Stages 4–6: persistent bounded generation jobs, snapshot versions, weekly grid, validated editing, publication, rescheduling proposals, weighted optimization, reports, CSV/PDF implemented. Full backend suite: 128 passing at this milestone.
- Optimization benchmark: 16 sessions, 1.664s feasibility vs 1.866s optimized; valid in both cases; weighted score 510 → 120 (lower is better). Historical scalability benchmarks retained.
- Stage 7 in progress: real browser workflow, PDF visual QA, final tests and Windows instructions.

## Recovered development status — 2026-11-06

Earlier entries above are historical milestones. The repository is now configured
with Git; all authentication/onboarding work remains uncommitted and has not been pushed.

- Existing architecture: Python scheduling engines; FastAPI; SQLAlchemy Core and
  SQLite; bounded background jobs; React/Vite frontend. Academic records are still
  **single-college/global**. Publication `scope` is not a college boundary.
- Completed before interruption: Argon2id passwords, local administrator provisioning,
  opaque revocable sessions, CSRF, throttling, role checks, user management, protected
  frontend routes. Verified baseline: 156 backend tests, 10 frontend tests and the
  administrator/viewer browser workflow.
- Interrupted work recovered: pending registration tables/migration 3, SMTP adapter,
  signup/resend/verification endpoints, Sign Up/Sign In UI. Recovered test output was
  10 passed / 6 failed for onboarding; its production build had passed.
- Completed on resume: corrected verification error status and test fixtures; added
  frontend onboarding tests, real SMTP/browser verification coverage, a loopback
  mail capture utility, read-only tenant preflight and shared-schema migration review.
- Latest executed checks: **172 backend tests passed**, **15 frontend unit tests
  passed**, **2 Playwright workflows passed**, and **production frontend build passed**.
  No remaining test failures. One upstream Starlette/HTTPX deprecation warning remains.
- Real SMTP transport was tested against loopback receivers. Registration, email
  parsing, verification, replay prevention and denial of academic access were checked.
  External provider/inbox delivery has not been tested or configured.
- Existing database has migrations 1–3, integrity `ok`, and zero FK violations.
  Additive migration verification compared every pre-existing row without changes.
  Backup: `data/backups/pre-onboarding-20261106-124947.db`. Existing 2 timetable
  versions and 31 sessions are preserved. No user accounts were provisioned by tests.

### Current onboarding boundary

Name/college/email/password → pending registration → SMTP link → explicit password
confirmation → atomic single-use verification → **awaiting workspace stage**.
`college_registrations` has no membership in the application; its tokens are keyed
digests with 30-minute expiry. Resends rotate tokens and are rate limited.
Unverified AND verified pending registrations cannot sign in or access academic data.
Registration is development-only and disabled by default.

### Not completed — do not claim multi-college readiness

- No `colleges` or membership tables, no college-aware academic keys or queries.
- No workspace creation/activation, faculty/student invitations or invitation acceptance.
- No cross-college isolation claim or passing isolation suite: there are not yet two
  active colleges to test. Current tests prove pending registrants cannot enter the
  existing workspace; that is not equivalent to tenant isolation.
- Selected design is a **shared database**, with composite college-scoped foreign keys,
  college-aware permissions/jobs/reports and a legacy-college backfill. Proposed SQLite
  primary-key changes require table rebuilds. No destructive cutover has been executed;
  user approval is required before that operation. Review `docs/MULTI_COLLEGE_MIGRATION.md`.

### Files and local setup

- Authentication implementation: `campusflow/auth/` (config, tables, service,
  middleware, permissions, routes, CLI, onboarding, onboarding_tables, mail).
- Integration: `campusflow/api/main.py`, `campusflow/product/{database,migrations,routes}.py`.
- Frontend: `Auth.tsx`, `Onboarding.tsx`, `Users.tsx`, API helper, App and role-aware
  Configuration/Timetable controls; auth/onboarding/workspace tests.
- Tests/tooling: `tests/{conftest,test_auth,test_onboarding,test_api,test_product}.py`,
  browser workflows/config, `scripts/{e2e_backend,local_mail,tenant_preflight}.py`.
- Documentation/dependencies: README, PROGRESS, `.gitignore`, `pyproject.toml`,
  `docs/{AUTHENTICATION,ONBOARDING,MULTI_COLLEGE_MIGRATION}.md`.

Exact local commands and required environment variables are in
[`docs/ONBOARDING.md`](docs/ONBOARDING.md#local-startup-powershell). Start the loopback
SMTP receiver, backend with the preview environment, and Vite in separate terminals.
Use a disposable preview database, not production data. Existing single-college login
instructions remain in `docs/AUTHENTICATION.md`.

Next: implement/rehearse the reviewed shared-schema migration on a copy, approve
the destructive cutover before applying it, enforce tenant context throughout the
backend, and pass the documented cross-college test matrix. Only then enable workspace
activation and invitations. Production also needs tested SMTP delivery, TLS/proxy
configuration, stable secret storage, backup recovery, audit and retention policies.
