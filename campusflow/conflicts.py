"""Pairwise and whole-timetable conflict detection."""

from dataclasses import dataclass
from enum import Enum
from itertools import combinations
from typing import Iterable

from .models import Lecture


class Resource(str, Enum):
    FACULTY = "faculty"
    CLASSROOM = "classroom"
    BATCH = "batch"


@dataclass(frozen=True)
class Conflict:
    first: Lecture
    second: Lecture
    resources: tuple[Resource, ...]


def detect_conflict(first: Lecture, second: Lecture) -> Conflict | None:
    """Return all shared resources when two same-day intervals overlap."""
    if first.day != second.day:
        return None
    if not (first.start < second.end and second.start < first.end):
        return None
    resources = tuple(
        resource for resource in Resource
        if getattr(first, resource.value) == getattr(second, resource.value)
    )
    return Conflict(first, second, resources) if resources else None


def check_timetable(lectures: Iterable[Lecture]) -> list[Conflict]:
    """Check every unordered pair once, preserving input order.

    Lecture IDs must be unique. The O(n²) implementation is intended for
    small campus timetables and accepts lists as well as generators.
    """
    entries = list(lectures)
    if len({lecture.id for lecture in entries}) != len(entries):
        raise ValueError("Lecture IDs must be unique within a timetable")
    return [
        conflict
        for first, second in combinations(entries, 2)
        if (conflict := detect_conflict(first, second)) is not None
    ]
