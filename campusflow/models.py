"""Models for a recurring weekly timetable."""

from dataclasses import dataclass
from datetime import time
from enum import Enum


class Weekday(str, Enum):
    MONDAY = "Monday"
    TUESDAY = "Tuesday"
    WEDNESDAY = "Wednesday"
    THURSDAY = "Thursday"
    FRIDAY = "Friday"
    SATURDAY = "Saturday"
    SUNDAY = "Sunday"


@dataclass(frozen=True)
class Lecture:
    """A same-day lecture with one faculty member, classroom, and batch.

    Resource strings are case-sensitive identifiers. Times are local campus
    times; intervals include the start and exclude the end.
    """

    id: str
    subject: str
    faculty: str
    classroom: str
    batch: str
    day: Weekday
    start: time
    end: time

    def __post_init__(self) -> None:
        for field in ("id", "subject", "faculty", "classroom", "batch"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be a non-empty string")
            object.__setattr__(self, field, value.strip())
        object.__setattr__(self, "day", Weekday(self.day))
        for value in (self.start, self.end):
            if not isinstance(value, time) or value.tzinfo is not None:
                raise ValueError("start and end must be timezone-free datetime.time values")
        if self.start >= self.end:
            raise ValueError("start must be before end on the same day")
