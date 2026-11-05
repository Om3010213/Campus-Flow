"""Independent validation of generated or externally supplied timetables."""

from dataclasses import dataclass, replace
from typing import Iterable

from .conflicts import check_timetable
from .models import Lecture
from .scheduling import SchedulingProblem, available, covers, seconds, sessions


@dataclass(frozen=True)
class ValidationResult:
    errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.errors


def validate_timetable(problem: SchedulingProblem, lectures: Iterable[Lecture]) -> ValidationResult:
    """Check completeness, assignment rules, duration, availability, and conflicts.

    Session IDs follow '<requirement ID>:<1-based session number>'.
    Validation does not depend on the scheduler or its candidate generation.
    """
    entries = list(lectures)
    expected = sessions(problem)
    errors: list[str] = []
    ids = {lecture.id for lecture in entries}
    if len(ids) != len(entries):
        errors.append("Duplicate lecture IDs")
    for missing in sorted(expected.keys() - ids):
        errors.append(f"Missing session: {missing}")
    for lecture in entries:
        req = expected.get(lecture.id)
        if req is None:
            errors.append(f"Unexpected session: {lecture.id}")
        else:
            if (lecture.subject, lecture.faculty, lecture.batch) != (req.subject, req.faculty, req.batch):
                errors.append(f"{lecture.id}: subject/faculty/batch does not match requirement")
            if seconds(lecture.end) - seconds(lecture.start) != req.duration_minutes * 60:
                errors.append(f"{lecture.id}: invalid duration")
        if lecture.day not in problem.working_days:
            errors.append(f"{lecture.id}: invalid working day")
        if (lecture.start not in {s.start for s in problem.time_slots}
                or not covers(lecture.start, lecture.end, problem.time_slots)):
            errors.append(f"{lecture.id}: invalid time slot")
        if lecture.classroom not in problem.classrooms:
            errors.append(f"{lecture.id}: unknown classroom")
        if not available(problem.faculty_availability, lecture.faculty, lecture.day, lecture.start, lecture.end):
            errors.append(f"{lecture.id}: faculty unavailable")
        if not available(problem.classroom_availability, lecture.classroom, lecture.day, lecture.start, lecture.end):
            errors.append(f"{lecture.id}: classroom unavailable")
    # Unique temporary IDs allow Phase 1 to check conflicts even for malformed IDs.
    for conflict in check_timetable(replace(lecture, id=str(i)) for i, lecture in enumerate(entries)):
        resources = ", ".join(r.value for r in conflict.resources)
        errors.append(f"Conflict between entries {conflict.first.id} and {conflict.second.id}: {resources}")
    return ValidationResult(tuple(errors))
