# Phase 2.6 CP-SAT results

Reproduce: `.venv\Scripts\python -m campusflow.benchmark --engine cp-sat --solver-limit 15 --timeout 30`

Raw results: `cp_sat_results.json`; historical Phase 2.5 CSP results: `results.json`.
Same deterministic datasets, fresh subprocesses, one run per case, no witness
schedule supplied as a solver hint. Each feasible scaled dataset's witness was
independently validated. OR-Tools 9.15.6755, one search worker, seed 0.

| Sessions | Historical CSP generation (s) | CP-SAT status | CP-SAT generation (s) | Solver only (s) | External validation (s) | Scheduled |
|---|---:|---|---:|---:|---:|---:|
| 10 | 0.018840 | OPTIMAL | 1.496562 | 0.042316 | 0.001041 | 10 |
| 50 | 2.141419 | OPTIMAL | 1.663763 | 0.453564 | 0.003047 | 50 |
| 100 | Timeout | OPTIMAL | 15.190813 | 13.948799 | 0.007736 | 100 |
| 200 | Timeout | UNKNOWN / timeout | 16.148801 | 15.005542 | — | 0 |
| 500 | Timeout | UNKNOWN / timeout | 18.856015 | 15.037215 | — | 0 |
| 3 impossible | 0.000472 | INFEASIBLE | 0.915965 | 0.009279 | — | 0 |

All successful schedules passed independent validation. Timeouts returned no
partial timetable and do not imply infeasibility. OPTIMAL denotes feasibility
here; the model has no quality objective. No process crashes or invalid outputs.

## Interpretation

- CP-SAT generation includes cold optional-library import, model construction,
  solving, and internal validation. External validation is a separate second check.
- CP-SAT has a 15-second **solver** limit and 30-second whole-process cap. Historical
  CSP had a 15-second **whole-process** cap. Thus the 100-session completion is
  useful evidence, but not a like-for-like speedup under the original deadline.
- The 50-session generation observation is lower than the historical CSP result;
  tiny cases are slower because of library/model overhead. These are single runs,
  not controlled statistical speedup claims.
- All five requested sizes were measured. No benchmarks remain unfinished.
- Tests: 97 passed, including all 77 existing tests; `pip check` found no broken
  dependencies. No existing CSP implementation or public interface was changed.

This first CP-SAT formulation is correct and reaches 100 sessions, but is not yet
proven adequate for 200–500-session production timetables under the requested
limit. The next solver-focused milestone should profile presolve/search and tune
room symmetry and the assignment formulation using the same datasets. Parallel
search could be evaluated separately, with its determinism tradeoff documented.
No frontend, persistence, API, optimization preferences, or Phase 3 work was added.
