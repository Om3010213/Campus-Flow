"""Reproduce with python -m campusflow.benchmark --timeout 15.

Each case runs in a fresh subprocess with a wall-clock deadline. Generation
includes the scheduler's built-in validation; external validation is timed again
separately. A known feasible witness is also validated for every scaled dataset,
so a timeout is never mistaken for infeasibility. No scheduler instrumentation.
"""

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, time, timezone
from pathlib import Path
from time import perf_counter

from .generation_demo import DEMO_PROBLEM
from .models import Lecture, Weekday
from .scheduler import generate_timetable
from .scheduling import Availability, Faculty, LectureRequirement, SchedulingProblem, TimeSlot
from .validation import validate_timetable


def build_dataset(count: int) -> tuple[SchedulingProblem, tuple[Lecture, ...]]:
    """Ten weekly sessions per batch: four subjects twice, two 120-minute labs.

    Two batches share five faculty and one room (24 teaching hours per week).
    Rooms include named labs, but room-type suitability is not supported by the
    engine. The witness uses four days, leaving Friday as spare room capacity.
    """
    if count not in (50, 100, 200, 500):
        raise ValueError("Supported session counts: 50, 100, 200, 500")
    batches = count // 10
    groups = (batches + 1) // 2
    days = tuple(Weekday)[:5]
    hours = (9, 10, 11, 13, 14, 15)
    subjects = ("Mathematics", "Algorithms", "Networks", "Databases", "Programming Lab")
    rooms = tuple(f"{'Lab' if g % 3 == 0 else 'Room'}-{g + 1:02}" for g in range(groups))
    faculty = tuple(Faculty(f"F-{g:02}-{s}", (subject,))
                    for g in range(groups) for s, subject in enumerate(subjects))
    requirements = []
    witness = []
    for batch in range(batches):
        group = batch // 2
        batch_id = f"CSE-{batch + 1:02}"
        for s, subject in enumerate(subjects):
            req_id = f"B{batch + 1}-S{s}"
            faculty_id = f"F-{group:02}-{s}"
            duration = 120 if s == 4 else 60
            requirements.append(LectureRequirement(req_id, subject, faculty_id, batch_id, 2, duration))
            for occurrence in range(2):
                day_index = (batch % 2) * 2 + (occurrence if s == 4 else s // 2)
                hour = 14 if s == 4 else ((9, 10) if s % 2 == 0 else (11, 13))[occurrence]
                witness.append(Lecture(f"{req_id}:{occurrence + 1}", subject, faculty_id,
                                       rooms[group], batch_id, days[day_index],
                                       time(hour), time(hour + duration // 60)))
    windows = tuple(Availability(day, time(start), time(end))
                    for day in days[:4] for start, end in ((9, 12), (13, 16)))
    problem = SchedulingProblem(
        faculty=faculty, batches=tuple(f"CSE-{i + 1:02}" for i in range(batches)),
        classrooms=rooms, working_days=days,
        time_slots=tuple(TimeSlot(time(h), time(h + 1)) for h in hours),
        requirements=tuple(requirements),
        faculty_availability={f.name: windows for f in faculty},
        classroom_availability={room: windows for room in rooms},
    )
    return problem, tuple(witness)


def impossible_problem() -> SchedulingProblem:
    # Every session individually has two options, but three sessions sharing a
    # batch cannot fit into two hours. This requires joint constraint search.
    return SchedulingProblem(
        faculty=tuple(Faculty(f"F{i}", (f"S{i}",)) for i in range(3)),
        batches=("B1",), classrooms=("R1", "Lab1"),
        working_days=(Weekday.MONDAY,),
        time_slots=(TimeSlot(time(9), time(10)), TimeSlot(time(10), time(11))),
        requirements=tuple(LectureRequirement(f"Q{i}", f"S{i}", f"F{i}", "B1", 1, 60)
                           for i in range(3)),
    )


def emit(**event) -> None:
    print(json.dumps(event), flush=True)


def worker(case: str, engine: str = "csp", solver_limit: float = 15.0) -> None:
    if case == "demo":
        problem, witness = DEMO_PROBLEM, ()
    elif case == "impossible":
        problem, witness = impossible_problem(), ()
    else:
        problem, witness = build_dataset(int(case))
    emit(stage="dataset", sessions=sum(r.weekly_sessions for r in problem.requirements),
         faculty=len(problem.faculty), batches=len(problem.batches), rooms=len(problem.classrooms))
    if witness:
        started = perf_counter()
        checked = validate_timetable(problem, witness)
        emit(stage="witness", witness_validation_seconds=perf_counter() - started,
             witness_valid=checked.valid)
        if not checked.valid:
            raise RuntimeError(f"Invalid benchmark witness: {checked.errors}")
    emit(stage="generation_started")
    started = perf_counter()
    if engine == "cp-sat":
        from .cp_sat_scheduler import generate_timetable as generate_cp_sat
        result = generate_cp_sat(problem, time_limit_seconds=solver_limit)
        emit(cp_sat_status=result.status, solver_status=result.solver_status,
             solver_seconds=result.solver_seconds)
    else:
        result = generate_timetable(problem)
    emit(stage="generation_finished", generation_seconds=perf_counter() - started,
         success=result.success, reason=result.reason, generated_sessions=len(result.lectures))
    if result.success:
        started = perf_counter()
        checked = validate_timetable(problem, result.lectures)
        emit(stage="finished", validation_seconds=perf_counter() - started,
             valid=checked.valid, status="completed" if checked.valid else "invalid",
             errors=checked.errors)
    else:
        status = "unsuccessful"
        if engine == "cp-sat" and result.status in ("timeout", "invalid"):
            status = "timed_out" if result.status == "timeout" else "invalid"
        emit(stage="finished", status=status)


def run_case(case: str, timeout: float, engine: str = "csp", solver_limit: float = 15.0) -> dict:
    started = perf_counter()
    process = subprocess.Popen([sys.executable, "-m", "campusflow.benchmark", "--worker", case,
                                "--engine", engine, "--solver-limit", str(solver_limit)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    timed_out = False
    try:
        output, error = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        output, error = process.communicate()
    row = {"case": case, "wall_seconds": perf_counter() - started,
           "timeout_seconds": timeout, "generation_seconds": None, "validation_seconds": None}
    for line in output.splitlines():
        row.update(json.loads(line))
    if timed_out:
        row["status"] = "timed_out"
        row["timeout_source"] = "process_deadline"
    elif process.returncode != 0:
        row["status"] = "error"
        row["error"] = error[-3000:]
    row["expected_outcome"] = "unsuccessful" if case == "impossible" else "completed"
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=15, help="Whole-worker deadline in seconds")
    parser.add_argument("--engine", choices=("csp", "cp-sat"), default="csp")
    parser.add_argument("--solver-limit", type=float, default=15, help="CP-SAT solver-only time limit")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", choices=("demo", "50", "100", "200", "500", "impossible"),
                        help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 0 < args.solver_limit < float("inf"):
        parser.error("--solver-limit must be finite and positive")
    if args.worker:
        worker(args.worker, args.engine, args.solver_limit)
        return
    if not 0 < args.timeout < float("inf"):
        parser.error("--timeout must be finite and positive")
    report = {
        "engine": args.engine, "solver_limit_seconds": args.solver_limit if args.engine == "cp-sat" else None,
        "utc_timestamp": datetime.now(timezone.utc).isoformat(),
        "python": sys.version, "platform": platform.platform(),
        "processor": platform.processor(), "logical_cpus": os.cpu_count(),
        "notes": "One run per case; generation includes internal validation. "
                 "External validation timed separately. Deadline includes startup and witness checking. "
                 "Timeout is not proof of infeasibility. Room types are labels only.",
        "results": [],
    }
    if args.engine == "cp-sat":
        from importlib.metadata import version
        report["ortools_version"] = version("ortools")
    if args.output is None:
        args.output = Path("benchmarks/cp_sat_results.json" if args.engine == "cp-sat" else "benchmarks/results.json")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for case in ("demo", "50", "100", "200", "500", "impossible"):
        row = run_case(case, args.timeout, args.engine, args.solver_limit)
        report["results"].append(row)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(row), flush=True)
    if any(r["status"] not in (r["expected_outcome"], "timed_out") for r in report["results"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
