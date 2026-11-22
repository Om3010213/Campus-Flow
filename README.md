# CampusFlow

CampusFlow supports **School and College institution workspaces** in one application.
Direct Email + Password signup creates unprivileged accounts. Explicit School/College
onboarding creates isolated workspaces; administrators invite planners,
teachers/faculty and students. Shared CSP/CP-SAT engines schedule school periods and
college lectures with availability, breaks, room types and weekly requirements.

See [local onboarding](docs/ONBOARDING.md), [architecture and schema](docs/INSTITUTION_SCHEMA.md),
[migration rehearsal](docs/MULTI_COLLEGE_MIGRATION.md) and [operations](docs/OPERATIONS.md).
The master requirements remain in [MASTER_REQUIREMENTS.md](docs/MASTER_REQUIREMENTS.md).

**Existing pre-tenant databases refuse automatic migration.** The live database has not
been cut over. Start a separate development workspace safely:

```powershell
.venv\Scripts\python scripts/dev_onboarding.py --database data/development-v5.db
# Another terminal:
pnpm.cmd --dir frontend dev
```

Open http://127.0.0.1:5173/sign-up. No OTP, email verification or SMTP is required. After signup, sign in and explicitly
create your institution workspace. Administrators share private invitation links. Full dependencies, environment variables and
onboarding instructions are in the linked guide. No deployment or GitHub push was made.

The following sections document the underlying library and previous phases. Current
application authentication, institution isolation and startup instructions above take
precedence over historical single-workspace examples.

Minimal Python 3.10+ library for weekly lecture timetables. No runtime dependencies.

## Setup and verification

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
.venv\Scripts\python -m campusflow.sample
```

## Usage

```python
from campusflow import check_timetable
from campusflow.sample import SAMPLE_LECTURES

for conflict in check_timetable(SAMPLE_LECTURES):
    print(conflict.first.id, conflict.second.id, conflict.resources)
```

`Lecture` stores an ID, subject, faculty, classroom, batch, weekday, start, and end.
Use `datetime.time` for local campus times and `Weekday` for recurring weekdays.
`detect_conflict(first, second)` checks one pair; `check_timetable(lectures)` checks
every unordered pair and returns a list of conflicts with all shared resources.
The sample intentionally contains one faculty, one classroom, and one batch conflict.

Intervals overlap when `first.start < second.end and second.start < first.end`
on the same weekday. Back-to-back lectures are allowed. Zero-length and overnight
lectures are rejected. Resource identifiers are trimmed and case-sensitive;
each lecture has one faculty member, classroom, and batch. Timetable IDs must be
unique. Whole-timetable checking takes O(n²) time.

Files: `campusflow/models.py` contains models, `campusflow/conflicts.py` contains
detection, `campusflow/sample.py` contains example data, and `tests/` contains pytest tests.

## Phase 2: automatic generation

Run `.venv\Scripts\python -m campusflow.generation_demo` for a ten-session example.
Import `generate_timetable` from `campusflow.scheduler`, input dataclasses from
`campusflow.scheduling`, and `validate_timetable` from `campusflow.validation`.
See `DEMO_PROBLEM` in `campusflow/generation_demo.py` for a complete input example.

`SchedulingProblem` declares faculty and assigned subjects, batches, classrooms,
working days, daily slots, weekly requirements, and resource availability.
Each `LectureRequirement` fixes subject, faculty, batch, weekly session count,
and duration in positive integer minutes. Invalid inputs raise `ValueError`.
Session IDs are `<requirement ID>:<1-based session number>`.

The deterministic backtracking CSP solver uses dynamic MRV selection and forward
checking. A successful `ScheduleResult` contains every required lecture; failure
contains an explanation and no partial timetable. The independent validator
checks completeness, requirement matching, duration, slots, availability, and
Phase 1 conflicts, returning a `ValidationResult` with `valid` and `errors`.

Lectures start at declared slot start times. They may span adjacent/overlapping
slots, but cannot cross gaps or midnight. Availability must cover the full lecture:
omitted resource keys mean unrestricted availability; empty sequences mean unavailable.
Slots are shared across all working days. Faculty and rooms use case-sensitive IDs.

Limitations: search is exponential in the worst case and intended for small
timetables; no optimality, daily spreading, room capacity/type, or fairness rules.
Multiple sessions of a subject may occur on one day. No new runtime dependencies.
Persistence, API, frontend, and AI/ML features remain outside this phase.

## Phase 2.6: optional OR-Tools CP-SAT engine

The existing CSP engine and public interfaces are unchanged. Install the optional
extra only when using CP-SAT (verified here on Windows x64, Python 3.13.15):

```powershell
.venv\Scripts\python -m pip install -e ".[dev,cp-sat]"
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m campusflow.benchmark --engine cp-sat --solver-limit 15 --timeout 30
```

OR-Tools is pinned to `9.15.6755` for repeatability and brings its own transitive
dependencies. Base CampusFlow still has no mandatory runtime dependencies;
CP-SAT tests skip if the extra is absent. Compatible wheels are listed on
[PyPI](https://pypi.org/project/ortools/9.15.6755/).

```python
from campusflow.cp_sat_scheduler import generate_timetable
from campusflow.generation_demo import DEMO_PROBLEM

result = generate_timetable(DEMO_PROBLEM, time_limit_seconds=15)
if result.success:
    for lecture in result.lectures:
        print(lecture)
else:
    print(result.status, result.reason)
```

`CpSatResult` exposes `status`, `success`, `lectures`, `reason`, `solver_status`,
and `solver_seconds`. Status is `optimal`, `feasible`, `infeasible`, `timeout`,
or `invalid`. In this feasibility-only model, `optimal` does not imply timetable
quality optimization. No partial results are returned; every success passes the
existing independent validator. Missing optional dependencies raise an actionable
`ImportError`; nonpositive/nonfinite time limits raise `ValueError`.

The model uses integer microsecond starts, allowed start domains, mandatory
faculty/batch intervals, and optional intervals for exactly one selected room.
No-overlap constraints protect all resources. Availability restricts entire
intervals, and slot gaps/midnight cannot be crossed. Identical weekly sessions
are ordered to reduce symmetry. A fixed seed and one worker make results
repeatable in ordinary runs; wall deadlines and solver versions can affect them.

The 15-second solver limit excludes import, model construction, and validation.
The benchmark adds a separate 30-second process deadline, preserves the original
CSP results, and writes `benchmarks/cp_sat_results.json`. Generation timing
includes cold OR-Tools import and internal validation; external validation is
measured separately. Use the default `--engine csp --timeout 15` to rerun the old
benchmark. Room types/capacities and optimization preferences remain unsupported.

## Phase 3.1: FastAPI backend

Install and start from the repository root (append `cp-sat` to the extras to enable
OR-Tools; it is not required to run the API with CSP):

```powershell
.venv\Scripts\python -m pip install -e ".[api,api-test,dev]"
.venv\Scripts\python -m uvicorn campusflow.api.main:app --host 127.0.0.1 --port 8000
```

Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).
Run tests with `.venv\Scripts\python -m pytest -q`. API tests skip when API/test
extras are not installed. Tested with FastAPI 0.162.0, Pydantic 2.14.2,
Uvicorn 0.54.0, and HTTPX 0.28.1 on Python 3.13.15.

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Application liveness (`status: ok`) |
| `GET /api/solvers` | CSP availability and whether CP-SAT imports successfully |
| `POST /api/timetables/generate` | Generate and independently validate a complete schedule |
| `POST /api/timetables/validate` | Check supplied lectures against a scheduling problem |

Example generation request (authenticated requests also need a CSRF header):

```json
{
  "solver": "csp",
  "time_limit_seconds": 15,
  "problem": {
    "faculty": [{"name": "Dr. Rao", "subjects": ["Mathematics"]}],
    "batches": ["CSE-2A"],
    "classrooms": ["C-101"],
    "working_days": ["Monday", "Tuesday"],
    "time_slots": [
      {"start": "09:00", "end": "10:00"},
      {"start": "10:00", "end": "11:00"}
    ],
    "requirements": [{
      "id": "MATH", "subject": "Mathematics", "faculty": "Dr. Rao",
      "batch": "CSE-2A", "weekly_sessions": 2, "duration_minutes": 60
    }],
    "faculty_availability": {
      "Dr. Rao": [{"day": "Monday", "start": "09:00", "end": "11:00"}]
    },
    "classroom_availability": {}
  }
}
```

Change `solver` to `cp-sat` to use OR-Tools. Subject assignments are declared
within faculty and requirements. Availability uses the existing semantics:
omitted keys are unrestricted; empty window lists mean unavailable.

Generation responds with `status`, `solver`, `lectures`, `validation`, `message`,
and `errors`. A successful response has `status: success` and
`validation: {"valid": true, "errors": []}`. For validation, send
`{"problem": <same problem>, "lectures": <generated lectures array>}`;
the response has `status: valid` or `invalid` and descriptive validation errors,
including missing sessions and faculty/classroom/batch conflicts. No solver is
used during validation (`solver: null`).

| HTTP status | Meaning |
|---|---|
| 200 | Success, validation result, or proven infeasibility (`status: infeasible`) |
| 422 | Invalid request (`invalid_input`, with field errors) |
| 504 | Solver or worker deadline (`timeout`, never reported as infeasible) |
| 503 | Optional solver unavailable, or generation capacity busy |
| 500 | Internal error; exception details are logged server-side only |

The API uses synchronous handlers in FastAPI's thread pool and separate,
killable solver subprocesses. Default time limit is 15 seconds, maximum 30.
CP-SAT receives this solver limit; both engines have a hard whole-worker limit
of the requested time plus five seconds for startup/model/validation overhead.
Timed-out workers are killed and reaped. Two simultaneous generation requests
per API process are allowed; excess requests receive 503 without queuing.

API requests are limited to 500 sessions, 200 faculty, 100 batches, 50 classrooms,
48 daily slots, and 96 availability windows per resource. These are input limits,
not guarantees of feasibility or completion. Unknown fields are rejected.
The optional solver availability check is cached until application restart.

Current authentication, local CORS, persistence and deployment requirements are
documented in [Authentication setup](docs/AUTHENTICATION.md). Use one Uvicorn worker:
background job recovery and concurrency control remain process-local.
