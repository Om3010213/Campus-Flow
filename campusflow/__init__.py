"""CampusFlow's public timetable interface."""

from .conflicts import Conflict, Resource, check_timetable, detect_conflict
from .models import Lecture, Weekday

__all__ = [
    "Lecture", "Weekday", "Conflict", "Resource", "detect_conflict", "check_timetable"
]
