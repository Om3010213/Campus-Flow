"""Validated inputs for the weekly scheduling engine (local campus times)."""

from dataclasses import dataclass, field
from datetime import time
from types import MappingProxyType
from typing import Iterable, Mapping

from .models import Weekday


def _name(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Identifiers must be non-empty strings")
    return value.strip()


def _positive(value: int, label: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{label} must be a positive integer")


def seconds(value: time) -> float:
    return value.hour * 3600 + value.minute * 60 + value.second + value.microsecond / 1e6


@dataclass(frozen=True)
class TimeSlot:
    start: time
    end: time

    def __post_init__(self) -> None:
        if any(not isinstance(t, time) or t.tzinfo is not None for t in (self.start, self.end)):
            raise ValueError("Slots require timezone-free datetime.time values")
        if self.start >= self.end:
            raise ValueError("Slot start must precede end on the same day")


@dataclass(frozen=True)
class Availability:
    day: Weekday
    start: time
    end: time

    def __post_init__(self) -> None:
        object.__setattr__(self, "day", Weekday(self.day))
        TimeSlot(self.start, self.end)


@dataclass(frozen=True)
class Faculty:
    name: str
    subjects: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _name(self.name))
        object.__setattr__(self, "subjects", tuple(_name(s) for s in self.subjects))


@dataclass(frozen=True)
class LectureRequirement:
    id: str
    subject: str
    faculty: str
    batch: str
    weekly_sessions: int
    duration_minutes: int

    def __post_init__(self) -> None:
        for key in ("id", "subject", "faculty", "batch"):
            object.__setattr__(self, key, _name(getattr(self, key)))
        _positive(self.weekly_sessions, "weekly_sessions")
        _positive(self.duration_minutes, "duration_minutes")


@dataclass(frozen=True)
class SchedulingProblem:
    faculty: tuple[Faculty, ...]
    batches: tuple[str, ...]
    classrooms: tuple[str, ...]
    working_days: tuple[Weekday, ...]
    time_slots: tuple[TimeSlot, ...]
    requirements: tuple[LectureRequirement, ...]
    faculty_availability: Mapping[str, tuple[Availability, ...]] = field(default_factory=dict)
    classroom_availability: Mapping[str, tuple[Availability, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for key in ("faculty", "time_slots", "requirements"):
            object.__setattr__(self, key, tuple(getattr(self, key)))
        for values, kind in ((self.faculty, Faculty), (self.time_slots, TimeSlot),
                             (self.requirements, LectureRequirement)):
            if any(not isinstance(value, kind) for value in values):
                raise ValueError(f"Expected {kind.__name__} objects")
        for key in ("batches", "classrooms"):
            object.__setattr__(self, key, tuple(_name(v) for v in getattr(self, key)))
        object.__setattr__(self, "working_days", tuple(Weekday(d) for d in self.working_days))
        for values, label in (
            ([f.name for f in self.faculty], "faculty"), (self.batches, "batches"),
            (self.classrooms, "classrooms"), (self.working_days, "working days"),
            ([r.id for r in self.requirements], "requirement IDs"),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"Duplicate {label}")
        faculty = {f.name: f for f in self.faculty}
        for req in self.requirements:
            if req.faculty not in faculty or req.subject not in faculty[req.faculty].subjects:
                raise ValueError(f"Requirement {req.id}: subject is not assigned to faculty")
            if req.batch not in self.batches:
                raise ValueError(f"Requirement {req.id}: unknown batch")
        for key, known in (("faculty_availability", faculty),
                           ("classroom_availability", self.classrooms)):
            availability = getattr(self, key)
            if any(resource not in known for resource in availability):
                raise ValueError(f"Unknown resource in {key}")
            copied = {resource: tuple(windows) for resource, windows in availability.items()}
            if any(not isinstance(w, Availability) for windows in copied.values() for w in windows):
                raise ValueError("Availability entries must be Availability objects")
            object.__setattr__(self, key, MappingProxyType(copied))


def covers(start: time, end: time, windows: Iterable[TimeSlot | Availability]) -> bool:
    """Whether a union of windows continuously covers the entire interval."""
    cursor = start
    for window in sorted(windows, key=lambda w: (w.start, w.end)):
        if window.start > cursor:
            break
        cursor = max(cursor, window.end)
        if cursor >= end:
            return True
    return False


def available(mapping: Mapping[str, tuple[Availability, ...]], resource: str,
              day: Weekday, start: time, end: time) -> bool:
    # Omitted resources are unrestricted; an explicit empty tuple means unavailable.
    return resource not in mapping or covers(
        start, end, (w for w in mapping[resource] if w.day == day)
    )


def sessions(problem: SchedulingProblem) -> dict[str, LectureRequirement]:
    return {f"{req.id}:{number}": req for req in problem.requirements
            for number in range(1, req.weekly_sessions + 1)}
