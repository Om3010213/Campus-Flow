"""School period example using the existing scheduling engine, not a new solver."""
from datetime import time

from .models import Weekday
from .scheduler import generate_timetable
from .scheduling import Availability, Faculty, LectureRequirement, SchedulingProblem, TimeSlot

DAYS = (Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY, Weekday.THURSDAY, Weekday.FRIDAY)
SCHOOL_PROBLEM = SchedulingProblem(
    faculty=(Faculty("T-MATH", ("Mathematics",)), Faculty("T-ENG", ("English",)),
             Faculty("T-SCI", ("Science practical", "Activity"))),
    batches=("Class-7-A", "Class-7-B"), classrooms=("Room-7A", "Room-7B"),
    working_days=DAYS,
    # Recess 10:20–10:40 and lunch 12:00–12:40 are excluded from teachable slots.
    time_slots=(TimeSlot(time(9), time(9, 40)), TimeSlot(time(9, 40), time(10, 20)),
                TimeSlot(time(10, 40), time(11, 20)), TimeSlot(time(11, 20), time(12)),
                TimeSlot(time(12, 40), time(13, 20))),
    requirements=tuple(
        LectureRequirement(f"{code}-{section}", subject, teacher, f"Class-7-{section}", count, duration)
        for section in ("A", "B") for code, subject, teacher, count, duration in (
            ("MATH", "Mathematics", "T-MATH", 3, 40), ("ENG", "English", "T-ENG", 2, 40),
            ("SCI", "Science practical", "T-SCI", 1, 80), ("ACT", "Activity", "T-SCI", 1, 40))),
    faculty_availability={"T-MATH": tuple(Availability(day, time(9), time(12)) for day in DAYS)},
)


def main():
    result = generate_timetable(SCHOOL_PROBLEM)
    if not result.success:
        raise SystemExit(result.reason)
    for lecture in sorted(result.lectures, key=lambda item: (DAYS.index(item.day), item.start, item.batch)):
        print(f"{lecture.day.value:10} {lecture.start:%H:%M}–{lecture.end:%H:%M} "
              f"{lecture.batch:10} {lecture.subject:18} {lecture.faculty:8} {lecture.classroom}")


if __name__ == "__main__":
    main()
