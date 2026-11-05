# Phase 2.5 benchmark

Reproduce from the repository root:

```powershell
.venv\Scripts\python -m campusflow.benchmark --timeout 15
.venv\Scripts\python -m pytest -q
```

Raw measurements and environment metadata: `benchmarks/results.json`.
Each case runs once in a fresh subprocess. Its 15-second wall deadline includes
startup, dataset construction, witness validation, generation, and external
validation. Timed-out workers are killed and reaped. Generation timing includes
the scheduler's internal validation; external validation is timed separately.
Numbers are single-run observations, not statistical performance guarantees.

| Case | Status | Generation (s) | Generated schedule validation (s) | Worker wall time (s) | Feasible witness validation (s) |
|---|---|---:|---:|---:|---:|
| Demo: 10 | Completed, valid | 0.018840 | 0.000644 | 0.391625 | — |
| 50 | Completed, valid | 2.141419 | 0.003828 | 2.633703 | 0.002200 |
| 100 | Timed out during generation | — | — | 15.024172 | 0.004618 |
| 200 | Timed out during generation | — | — | 15.031125 | 0.033123 |
| 500 | Timed out during generation | — | — | 15.029532 | 0.119202 |
| Impossible: 3 | Unsuccessful, as expected | 0.000472 | — | 0.234734 | — |

No crashes or invalid successful schedules occurred. All 77 existing tests passed.
The tests ran while a benchmark worker was active; timings reflect this local
machine run and should not be interpreted as isolated-system measurements.

## Workload

Deterministic datasets contain 50/100/200/500 sessions across 5/10/20/50 batches,
15/25/50/125 faculty, and 3/5/10/25 rooms. Each batch has four theory subjects
twice weekly (60 minutes each) and two 120-minute programming lab sessions.
Two batches share five faculty and a room in the known feasible witness.
Daily slots are 09:00–12:00 and 13:00–16:00, Monday through Friday; resource
availability restricts teaching to Monday through Thursday. Sessions cannot
cross lunch. Room names include labs, but the engine cannot enforce room types.

Each scaled dataset has a complete witness independently validated before
generation. These witness timings measure validator scaling even when generation
times out; they are not validation times for generated results. A timeout does
not imply infeasibility. The impossible case has three sessions sharing a batch
and only two hours; every session has candidates, so it exercises joint search.

## Bottlenecks and recommendation

Source inspection identifies the following costs (no profiler measurements):

- Candidate creation scales with sessions × working days × slot starts × rooms.
- The search eagerly computes and stores every viable sibling state before
  descending, copying domain dictionaries and filtering candidate tuples.
- Each sibling checks its assignment against candidates of every remaining
  session, repeatedly invoking pairwise conflict detection. MRV does not avoid
  this filtering cost. Equivalent rooms and repeated sessions add symmetry.
- Independent validation checks all lecture pairs, O(n²), but remained fast
  through the 500-session witness in this run.

The current scheduler is suitable for prototypes and small workloads like the
tested 50-session case. It is not yet demonstrated suitable for larger college
timetables: all tested 100–500-session cases exceeded the chosen deadline despite
known feasible solutions. Before production use, evaluate an advanced constraint
solver against this benchmark, or optimize lazy branching, occupancy indexes,
and symmetry handling in a separately authorized milestone. No scheduler changes
or Phase 3 implementation were made.
