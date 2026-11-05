"""Run with python -m campusflow.generation_demo."""

from datetime import time

from .models import Weekday
from .scheduler import generate_timetable
from .scheduling import Availability, Faculty, LectureRequirement, SchedulingProblem, TimeSlot


DEMO_PROBLEM = SchedulingProblem(
    faculty=(Faculty("Dr. Mehta", ("Data Structures",)),
             Faculty("Dr. Rao", ("Mathematics",)),
             Faculty("Dr. Shah", ("Database Lab",))),
    batches=("CSE-2A", "CSE-2B"),
    classrooms=("C-101", "C-102"),
    working_days=(Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY),
    time_slots=tuple(TimeSlot(time(hour), time(hour + 1)) for hour in range(9, 12)),
    requirements=(
        LectureRequirement("DS-A", "Data Structures", "Dr. Mehta", "CSE-2A", 2, 60),
        LectureRequirement("DS-B", "Data Structures", "Dr. Mehta", "CSE-2B", 2, 60),
        LectureRequirement("MA-A", "Mathematics", "Dr. Rao", "CSE-2A", 2, 60),
        LectureRequirement("MA-B", "Mathematics", "Dr. Rao", "CSE-2B", 2, 60),
        LectureRequirement("DB-A", "Database Lab", "Dr. Shah", "CSE-2A", 1, 120),
        LectureRequirement("DB-B", "Database Lab", "Dr. Shah", "CSE-2B", 1, 120),
    ),
    faculty_availability={"Dr. Shah": (
        Availability(Weekday.TUESDAY, time(9), time(12)),
        Availability(Weekday.WEDNESDAY, time(9), time(12)),
    )},
    classroom_availability={"C-102": tuple(
        Availability(day, time(10), time(12)) for day in
        (Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY)
    )},
)


def main() -> None:
    result = generate_timetable(DEMO_PROBLEM)
    if not result.success:
        print(f"Scheduling failed: {result.reason}")
        return
    print(f"Generated {len(result.lectures)} sessions\n")
    print(f"{'Day':<10} {'Time':<12} {'Room':<7} {'Batch':<8} {'Faculty':<12} Subject")
    for lecture in sorted(result.lectures, key=lambda l: (list(Weekday).index(l.day), l.start, l.classroom)):
        print(f"{lecture.day.value:<10} {lecture.start:%H:%M}-{lecture.end:%H:%M}  "
              f"{lecture.classroom:<7} {lecture.batch:<8} {lecture.faculty:<12} {lecture.subject}")


if __name__ == "__main__":
    main()
