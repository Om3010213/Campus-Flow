"""Optional CP-SAT engine; importing CampusFlow does not require OR-Tools."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from math import isfinite

from .models import Lecture, Weekday
from .scheduling import SchedulingProblem, available, covers, sessions
from .validation import validate_timetable

DAY = 86_400_000_000  # Integer microseconds preserve all Phase 1 time precision.


def _ticks(value: time) -> int:
    return ((value.hour * 60 + value.minute) * 60 + value.second) * 1_000_000 + value.microsecond


@dataclass(frozen=True)
class CpSatResult:
    status: str
    lectures: tuple[Lecture, ...] = ()
    reason: str = ""
    solver_status: str = "NOT_RUN"
    solver_seconds: float = 0.0

    @property
    def success(self) -> bool:
        return self.status in ("optimal", "feasible")


def generate_timetable(problem: SchedulingProblem, *, time_limit_seconds: float = 15.0,
                       configure_model=None, order_sessions: bool = True) -> CpSatResult:
    """Generate a complete schedule with one worker and a fixed random seed.

    The limit applies to CP-SAT solving, not model building or validation.
    UNKNOWN under this bounded solve is reported as timeout, never infeasible.
    No partial timetable is returned. Determinism is best effort near deadlines
    and across OR-Tools versions/hardware.
    """
    if not isfinite(time_limit_seconds) or time_limit_seconds <= 0:
        raise ValueError("time_limit_seconds must be finite and positive")
    try:
        from ortools.sat.python import cp_model
    except ImportError as exc:
        raise ImportError('CP-SAT requires the optional dependency: pip install ".[cp-sat]"') from exc

    model = cp_model.CpModel()
    required = sessions(problem)
    rooms = sorted(problem.classrooms)
    weekdays = list(Weekday)
    resource_intervals = defaultdict(list)
    assignments = {}
    previous = {}
    # Requirements share the same static candidate domains across weekly sessions.
    domains = {}
    for req in problem.requirements:
        room_starts = {room: [] for room in rooms}
        if req.duration_minutes < 1440:
            for day in sorted(problem.working_days, key=weekdays.index):
                for start in sorted({slot.start for slot in problem.time_slots}):
                    begin = datetime.combine(date(2000, 1, 1), start)
                    finish = begin + timedelta(minutes=req.duration_minutes)
                    if finish.date() != begin.date():
                        continue
                    end = finish.time()
                    if not covers(start, end, problem.time_slots):
                        continue
                    if not available(problem.faculty_availability, req.faculty, day, start, end):
                        continue
                    for room in rooms:
                        if available(problem.classroom_availability, room, day, start, end):
                            room_starts[room].append(weekdays.index(day) * DAY + _ticks(start))
        domains[req.id] = {room: starts for room, starts in room_starts.items() if starts}
        if not domains[req.id]:
            return CpSatResult("infeasible", reason=f"No valid assignment for requirement {req.id}")

    for session_id, req in required.items():
        legal = domains[req.id]
        start = model.new_int_var_from_domain(
            cp_model.Domain.from_values(sorted({s for starts in legal.values() for s in starts})),
            f"start:{session_id}",
        )
        duration = req.duration_minutes * 60_000_000
        interval = model.new_fixed_size_interval_var(start, duration, session_id)
        resource_intervals[("faculty", req.faculty)].append(interval)
        resource_intervals[("batch", req.batch)].append(interval)
        choices = {}
        for room, starts in legal.items():
            present = model.new_bool_var(f"{session_id}:{room}")
            model.add_linear_expression_in_domain(start, cp_model.Domain.from_values(starts)).only_enforce_if(present)
            room_interval = model.new_optional_fixed_size_interval_var(start, duration, present,
                                                                       f"room:{session_id}:{room}")
            resource_intervals[("room", room)].append(room_interval)
            choices[room] = present
        model.add_exactly_one(choices.values())
        # Identical sessions are interchangeable; order them to remove symmetry.
        if order_sessions and req.id in previous:
            model.add(start > previous[req.id])
        previous[req.id] = start
        assignments[session_id] = (start, choices)
    for intervals in resource_intervals.values():
        model.add_no_overlap(intervals)

    if configure_model is not None:
        configure_model(model, assignments, required)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    status = solver.solve(model)
    name = solver.status_name(status)
    elapsed = solver.wall_time
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        outcome = {cp_model.INFEASIBLE: "infeasible", cp_model.UNKNOWN: "timeout"}.get(status, "invalid")
        return CpSatResult(outcome, reason=f"CP-SAT returned {name}", solver_status=name, solver_seconds=elapsed)
    lectures = []
    for session_id, req in required.items():
        start_var, choices = assignments[session_id]
        day_index, local_ticks = divmod(solver.value(start_var), DAY)
        begin = datetime(2000, 1, 1) + timedelta(microseconds=local_ticks)
        room = next(room for room, present in choices.items() if solver.boolean_value(present))
        lectures.append(Lecture(session_id, req.subject, req.faculty, room, req.batch,
                                weekdays[day_index], begin.time(),
                                (begin + timedelta(minutes=req.duration_minutes)).time()))
    validation = validate_timetable(problem, lectures)
    if not validation.valid:
        return CpSatResult("invalid", reason="; ".join(validation.errors), solver_status=name, solver_seconds=elapsed)
    return CpSatResult("optimal" if status == cp_model.OPTIMAL else "feasible", tuple(lectures),
                       solver_status=name, solver_seconds=elapsed)
