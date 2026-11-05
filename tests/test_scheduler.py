from dataclasses import replace
from datetime import time
from itertools import product

import pytest

from campusflow import Lecture, Weekday, check_timetable
from campusflow.generation_demo import DEMO_PROBLEM
from campusflow.scheduler import generate_timetable
from campusflow.scheduling import Availability, Faculty, LectureRequirement, SchedulingProblem, TimeSlot
from campusflow.validation import validate_timetable


@pytest.fixture
def problem():
    return SchedulingProblem(
        faculty=(Faculty("F1", ("S1",)), Faculty("F2", ("S2",))),
        batches=("B1", "B2"), classrooms=("R1", "R2"),
        working_days=(Weekday.MONDAY,),
        time_slots=(TimeSlot(time(9), time(10)), TimeSlot(time(10), time(11))),
        requirements=(LectureRequirement("A", "S1", "F1", "B1", 1, 60),),
    )


def test_demo_complete_valid_and_deterministic():
    result = generate_timetable(DEMO_PROBLEM)
    assert result.success, result.reason
    assert len(result.lectures) == 10
    assert validate_timetable(DEMO_PROBLEM, result.lectures).valid
    assert not check_timetable(result.lectures)
    assert result == generate_timetable(DEMO_PROBLEM)


@pytest.mark.parametrize("resource", ["faculty", "classroom", "batch"])
def test_resource_double_booking_prevented(problem, resource):
    second = LectureRequirement("B", "S2", "F2", "B2", 1, 60)
    if resource == "faculty":
        second = replace(second, subject="S1", faculty="F1")
    if resource == "batch":
        second = replace(second, batch="B1")
    p = replace(problem, requirements=problem.requirements + (second,),
                classrooms=("R1",) if resource == "classroom" else problem.classrooms)
    result = generate_timetable(p)
    assert result.success
    assert result.lectures[0].start != result.lectures[1].start
    assert validate_timetable(p, result.lectures).valid
    impossible = replace(p, time_slots=p.time_slots[:1])
    failure = generate_timetable(impossible)
    assert not failure.success and not failure.lectures and failure.reason


def test_parallel_lectures_with_distinct_resources(problem):
    p = replace(problem, time_slots=problem.time_slots[:1], requirements=problem.requirements + (
        LectureRequirement("B", "S2", "F2", "B2", 1, 60),))
    result = generate_timetable(p)
    assert result.success
    assert len({lecture.classroom for lecture in result.lectures}) == 2


@pytest.mark.parametrize("field,resource", [("faculty_availability", "F1"), ("classroom_availability", "R1")])
def test_availability_is_respected(problem, field, resource):
    p = replace(problem, classrooms=("R1",), **{field: {
        resource: (Availability(Weekday.MONDAY, time(10), time(11)),)}})
    result = generate_timetable(p)
    assert result.success and result.lectures[0].start == time(10)
    assert not generate_timetable(replace(p, **{field: {resource: ()}})).success


def test_availability_must_cover_entire_duration_and_day(problem):
    for window in (Availability(Weekday.MONDAY, time(9), time(9, 30)),
                   Availability(Weekday.TUESDAY, time(9), time(11))):
        assert not generate_timetable(replace(problem, faculty_availability={"F1": (window,)})).success


@pytest.mark.parametrize("duration", [30, 60, 90, 120])
def test_different_durations(problem, duration):
    p = replace(problem, requirements=(replace(problem.requirements[0], duration_minutes=duration),))
    result = generate_timetable(p)
    assert result.success
    assert validate_timetable(p, result.lectures).valid


def test_mixed_durations_do_not_overlap(problem):
    p = replace(problem, requirements=(replace(problem.requirements[0], duration_minutes=90),
                                      LectureRequirement("B", "S1", "F1", "B2", 1, 30)))
    # 10:30 isn't a permitted start, so this requires a third slot.
    assert not generate_timetable(p).success
    p = replace(p, time_slots=p.time_slots + (TimeSlot(time(11), time(12)),))
    result = generate_timetable(p)
    assert result.success and validate_timetable(p, result.lectures).valid


def test_cannot_cross_slot_gap(problem):
    p = replace(problem, requirements=(replace(problem.requirements[0], duration_minutes=90),),
                time_slots=(TimeSlot(time(9), time(10)), TimeSlot(time(10, 30), time(11, 30))))
    assert not generate_timetable(p).success


def test_adjacent_availability_windows_cover_long_session(problem):
    p = replace(problem, requirements=(replace(problem.requirements[0], duration_minutes=120),),
                faculty_availability={"F1": (
                    Availability(Weekday.MONDAY, time(9), time(10)),
                    Availability(Weekday.MONDAY, time(10), time(11)))})
    assert generate_timetable(p).success


@pytest.mark.parametrize("changes", [{"working_days": ()}, {"classrooms": ()}, {"time_slots": ()}])
def test_no_scheduling_capacity(problem, changes):
    result = generate_timetable(replace(problem, **changes))
    assert not result.success and result.lectures == () and result.reason


def test_weekly_count_and_insufficient_slots(problem):
    p = replace(problem, requirements=(replace(problem.requirements[0], weekly_sessions=2),))
    result = generate_timetable(p)
    assert result.success and {l.id for l in result.lectures} == {"A:1", "A:2"}
    assert not generate_timetable(replace(p, requirements=(replace(p.requirements[0], weekly_sessions=3),))).success


def test_empty_requirements(problem):
    result = generate_timetable(replace(problem, requirements=()))
    assert result.success and result.lectures == ()


@pytest.mark.parametrize("duration", [1440, 10**10])
def test_oversized_duration_fails_cleanly(problem, duration):
    assert not generate_timetable(replace(problem, requirements=(
        replace(problem.requirements[0], duration_minutes=duration),))).success


@pytest.mark.parametrize("changes", [
    {"weekly_sessions": 0}, {"weekly_sessions": True}, {"weekly_sessions": 1.5},
    {"duration_minutes": -1}, {"duration_minutes": 0}, {"id": " "},
])
def test_invalid_requirement(problem, changes):
    with pytest.raises(ValueError):
        replace(problem.requirements[0], **changes)


@pytest.mark.parametrize("changes", [
    {"classrooms": ("R1", "R1")}, {"working_days": ("Funday",)},
    {"faculty_availability": {"Unknown": ()}}, {"classroom_availability": {"Unknown": ()}},
    {"time_slots": ("09:00",)},
])
def test_invalid_problem(problem, changes):
    with pytest.raises(ValueError):
        replace(problem, **changes)


@pytest.mark.parametrize("changes", [{"subject": "Unknown"}, {"faculty": "Unknown"}, {"batch": "Unknown"}])
def test_unknown_requirement_references(problem, changes):
    with pytest.raises(ValueError):
        replace(problem, requirements=(replace(problem.requirements[0], **changes),))


def test_duplicate_requirements(problem):
    with pytest.raises(ValueError):
        replace(problem, requirements=problem.requirements * 2)


@pytest.mark.parametrize("changes,message", [
    ({"id": "extra"}, "Unexpected session"),
    ({"subject": "Wrong"}, "does not match"),
    ({"faculty": "F2"}, "does not match"),
    ({"batch": "B2"}, "does not match"),
    ({"day": Weekday.TUESDAY}, "working day"),
    ({"end": time(9, 30)}, "duration"),
    ({"start": time(9, 15), "end": time(10, 15)}, "time slot"),
    ({"start": time(11), "end": time(12)}, "time slot"),
    ({"classroom": "Unknown"}, "unknown classroom"),
])
def test_independent_validator_rejects_invalid_lectures(problem, changes, message):
    lecture = Lecture("A:1", "S1", "F1", "R1", "B1", Weekday.MONDAY, time(9), time(10))
    validation = validate_timetable(problem, [replace(lecture, **changes)])
    assert not validation.valid
    assert any(message in error for error in validation.errors)


def test_validator_missing_duplicates_conflicts_and_availability(problem):
    lecture = generate_timetable(problem).lectures[0]
    assert not validate_timetable(problem, []).valid
    errors = validate_timetable(problem, [lecture, lecture]).errors
    assert any("Duplicate" in error for error in errors)
    assert any("faculty, classroom, batch" in error for error in errors)
    p = replace(problem, faculty_availability={"F1": ()}, classroom_availability={"R1": ()})
    errors = validate_timetable(p, [replace(lecture, classroom="R1")]).errors
    assert any("faculty unavailable" in error for error in errors)
    assert any("classroom unavailable" in error for error in errors)


def test_search_agrees_with_exhaustive_small_oracle(problem):
    # Vary domains of three mutually exclusive sessions. Includes cases where
    # every individual domain is nonempty but the joint problem is impossible.
    requirements = (problem.requirements[0],
                    LectureRequirement("B", "S2", "F2", "B1", 1, 60),
                    LectureRequirement("C", "S3", "F3", "B1", 1, 60))
    choices = ((9,), (10,), (9, 10), (10, 11), (9, 10, 11))
    for domains in product(choices, repeat=3):
        p = replace(problem, faculty=problem.faculty + (Faculty("F3", ("S3",)),),
                    requirements=requirements,
                    time_slots=tuple(TimeSlot(time(h), time(h + 1)) for h in (9, 10, 11)),
                    faculty_availability={f"F{i + 1}": tuple(
                        Availability(Weekday.MONDAY, time(h), time(h + 1)) for h in hours)
                        for i, hours in enumerate(domains)})
        feasible = any(len(set(starts)) == 3 for starts in product(*domains))
        result = generate_timetable(p)
        assert result.success == feasible, domains
        if result.success:
            assert validate_timetable(p, result.lectures).valid
