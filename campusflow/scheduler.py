"""Deterministic CSP search with dynamic MRV and forward checking."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .conflicts import detect_conflict
from .models import Lecture, Weekday
from .scheduling import SchedulingProblem, available, covers, sessions
from .validation import validate_timetable


@dataclass(frozen=True)
class ScheduleResult:
    success: bool
    lectures: tuple[Lecture, ...] = ()
    reason: str = ""


def generate_timetable(problem: SchedulingProblem, *, accept_assignment=None) -> ScheduleResult:
    """Return a complete valid schedule, or failure with no partial timetable.

    Starts are slot boundaries; sessions may span adjacent slots, but never gaps.
    All ordering is stable. MRV ties follow requirement/session input order.
    """
    required = sessions(problem)
    domains: dict[str, tuple[Lecture, ...]] = {}
    for session_id, req in required.items():
        candidates = []
        for day in sorted(problem.working_days, key=list(Weekday).index):
            for start in sorted({slot.start for slot in problem.time_slots}):
                # Reject durations extending into another day before constructing Lecture.
                if req.duration_minutes >= 1440:
                    continue
                begin = datetime.combine(date(2000, 1, 1), start)
                finish = begin + timedelta(minutes=req.duration_minutes)
                if finish.date() != begin.date():
                    continue
                end = finish.time()
                if not covers(start, end, problem.time_slots):
                    continue
                if not available(problem.faculty_availability, req.faculty, day, start, end):
                    continue
                for room in sorted(problem.classrooms):
                    if available(problem.classroom_availability, room, day, start, end):
                        candidate = Lecture(session_id, req.subject, req.faculty, room, req.batch, day, start, end)
                        if accept_assignment is None or accept_assignment((candidate,)):
                            candidates.append(candidate)
        if not candidates:
            return ScheduleResult(False, reason=f"No valid assignment for session {session_id}")
        domains[session_id] = tuple(candidates)

    # An explicit DFS stack avoids Python's recursion limit on larger inputs.
    stack = [({}, domains)]
    while stack:
        assigned, remaining = stack.pop()
        if not remaining:
            lectures = tuple(assigned[key] for key in required)
            validation = validate_timetable(problem, lectures)
            if not validation.valid:
                return ScheduleResult(False, reason="Validation failed: " + "; ".join(validation.errors))
            return ScheduleResult(True, lectures)
        chosen = min(remaining, key=lambda key: len(remaining[key]))
        # Reverse push order so the earliest candidate is explored first.
        for candidate in reversed(remaining[chosen]):
            if accept_assignment is not None and not accept_assignment((*assigned.values(), candidate)):
                continue
            next_domains = {}
            for key, values in remaining.items():
                if key == chosen:
                    continue
                legal = tuple(value for value in values if detect_conflict(candidate, value) is None)
                if not legal:
                    break
                next_domains[key] = legal
            else:
                stack.append(({**assigned, chosen: candidate}, next_domains))
    return ScheduleResult(False, reason="No valid timetable satisfies all requirements and availability constraints")
