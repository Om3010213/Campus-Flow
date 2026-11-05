from dataclasses import replace
from datetime import time, timezone

import pytest

from campusflow import Lecture, Resource, Weekday, check_timetable, detect_conflict
from campusflow.sample import SAMPLE_LECTURES


@pytest.fixture
def lecture():
    return Lecture("L1", "Data Structures", "Dr. Mehta", "C-101", "CSE-2A",
                   Weekday.MONDAY, time(9), time(10))


@pytest.mark.parametrize("resource", list(Resource))
def test_each_resource_conflicts_independently(lecture, resource):
    changes = dict(id="L2", faculty="Dr. Rao", classroom="C-102", batch="CSE-2B",
                   start=time(9, 30), end=time(10, 30))
    changes[resource.value] = getattr(lecture, resource.value)
    other = replace(lecture, **changes)
    assert detect_conflict(lecture, other).resources == (resource,)


@pytest.mark.parametrize("start,end", [
    (time(9), time(10)),       # identical intervals
    (time(9, 30), time(11)),   # partial overlap
    (time(8), time(9, 30)),   # overlap from the other direction
    (time(9, 15), time(9, 45)),  # contained interval
    (time(8), time(11)),       # containing interval
])
def test_overlap_and_all_shared_resources(lecture, start, end):
    other = replace(lecture, id="L2", start=start, end=end)
    assert detect_conflict(lecture, other).resources == tuple(Resource)
    assert detect_conflict(other, lecture).resources == tuple(Resource)


@pytest.mark.parametrize("start,end", [
    (time(10), time(11)), (time(8), time(9)), (time(12), time(13)),
])
def test_adjacent_and_disjoint_intervals_are_allowed(lecture, start, end):
    other = replace(lecture, id="L2", start=start, end=end)
    assert detect_conflict(lecture, other) is None
    assert detect_conflict(other, lecture) is None


def test_different_days_are_allowed(lecture):
    assert detect_conflict(lecture, replace(lecture, day=Weekday.TUESDAY)) is None


def test_overlap_without_shared_resources_is_allowed(lecture):
    other = replace(lecture, faculty="Dr. Rao", classroom="C-102", batch="CSE-2B")
    assert detect_conflict(lecture, other) is None


@pytest.mark.parametrize("changes", [
    {"start": time(10)}, {"end": time(8)},
    {"start": time(23), "end": time(1)},
    {"start": time(9, tzinfo=timezone.utc)}, {"end": "10:00"},
    {"day": "Funday"}, {"faculty": " "}, {"classroom": ""},
    {"batch": ""}, {"id": ""}, {"subject": ""},
])
def test_invalid_lectures_are_rejected(lecture, changes):
    with pytest.raises(ValueError):
        replace(lecture, **changes)


def test_resource_whitespace_is_normalized(lecture):
    assert replace(lecture, faculty=" Dr. Mehta ").faculty == lecture.faculty


def test_whole_timetable_checks_every_pair_once(lecture):
    entries = [replace(lecture, id=f"L{i}") for i in range(3)]
    conflicts = check_timetable(iter(entries))
    assert [(c.first.id, c.second.id) for c in conflicts] == [
        ("L0", "L1"), ("L0", "L2"), ("L1", "L2")
    ]


def test_empty_single_and_conflict_free_timetables(lecture):
    assert check_timetable([]) == []
    assert check_timetable([lecture]) == []
    assert check_timetable([lecture, replace(lecture, id="L2", day=Weekday.TUESDAY)]) == []


def test_duplicate_ids_are_rejected(lecture):
    with pytest.raises(ValueError, match="unique"):
        check_timetable([lecture, lecture])


def test_realistic_sample():
    assert [(c.first.id, c.second.id, c.resources) for c in check_timetable(SAMPLE_LECTURES)] == [
        ("L1", "L2", (Resource.FACULTY,)),
        ("L1", "L3", (Resource.CLASSROOM,)),
        ("L1", "L4", (Resource.BATCH,)),
    ]
