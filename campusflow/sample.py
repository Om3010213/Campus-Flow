"""Run with python -m campusflow.sample for a small example timetable."""

from datetime import time

from .conflicts import check_timetable
from .models import Lecture, Weekday


SAMPLE_LECTURES = (
    Lecture("L1", "Data Structures", "Dr. Mehta", "C-101", "CSE-2A",
            Weekday.MONDAY, time(9), time(10)),
    Lecture("L2", "Algorithms", "Dr. Mehta", "C-102", "CSE-2B",
            Weekday.MONDAY, time(9, 30), time(10, 30)),
    Lecture("L3", "Discrete Mathematics", "Dr. Rao", "C-101", "CSE-2C",
            Weekday.MONDAY, time(9, 45), time(10, 45)),
    Lecture("L4", "Database Systems", "Dr. Shah", "Lab-1", "CSE-2A",
            Weekday.MONDAY, time(9, 15), time(9, 45)),
    Lecture("L5", "Computer Networks", "Dr. Sen", "C-101", "CSE-2A",
            Weekday.MONDAY, time(11), time(12)),
    Lecture("L6", "Data Structures", "Dr. Mehta", "C-101", "CSE-2A",
            Weekday.TUESDAY, time(9), time(10)),
)


if __name__ == "__main__":
    for conflict in check_timetable(SAMPLE_LECTURES):
        resources = ", ".join(resource.value for resource in conflict.resources)
        print(f"{conflict.first.id} / {conflict.second.id}: {resources}")
