from dataclasses import replace
from datetime import time

import pytest

pytest.importorskip("ortools", reason="Install the optional cp-sat extra")

from campusflow.benchmark import impossible_problem
from campusflow.cp_sat_scheduler import generate_timetable
from campusflow.generation_demo import DEMO_PROBLEM
from campusflow.scheduler import generate_timetable as generate_csp
from campusflow.scheduling import Availability, TimeSlot
from campusflow.validation import validate_timetable


@pytest.mark.parametrize("problem", [DEMO_PROBLEM, impossible_problem()])
def test_engines_agree(problem):
    csp, sat = generate_csp(problem), generate_timetable(problem)
    assert csp.success == sat.success
    if sat.success:
        assert len(sat.lectures) == sum(r.weekly_sessions for r in problem.requirements)
        assert validate_timetable(problem, sat.lectures).valid
    else:
        assert sat.status == "infeasible" and not sat.lectures


def test_deterministic():
    first, second = generate_timetable(DEMO_PROBLEM), generate_timetable(DEMO_PROBLEM)
    assert first.success and second.success and first.lectures == second.lectures


@pytest.mark.parametrize("resource", ["faculty", "batch", "classroom"])
def test_resource_conflicts(resource):
    p = impossible_problem()
    reqs = tuple(replace(r, batch=f"B{i}") for i, r in enumerate(p.requirements[:2]))
    if resource == "batch":
        reqs = tuple(replace(r, batch="B0") for r in reqs)
    if resource == "faculty":
        reqs = tuple(replace(r, faculty="F0", subject="S0") for r in reqs)
    p = replace(p, requirements=reqs, batches=("B0", "B1"),
                classrooms=("R1",) if resource == "classroom" else p.classrooms)
    assert generate_timetable(p).success
    p = replace(p, time_slots=p.time_slots[:1])
    assert not generate_csp(p).success
    assert generate_timetable(p).status == "infeasible"


@pytest.mark.parametrize("duration", [30, 60, 90, 120, 1440])
def test_durations_and_gaps(duration):
    p = impossible_problem()
    p = replace(p, requirements=(replace(p.requirements[0], duration_minutes=duration),))
    for slots in (p.time_slots, (TimeSlot(time(9), time(10)), TimeSlot(time(10, 30), time(11, 30)))):
        problem = replace(p, time_slots=slots)
        result = generate_timetable(problem)
        assert result.success == generate_csp(problem).success
        if result.success:
            assert validate_timetable(problem, result.lectures).valid


@pytest.mark.parametrize("field,resource", [("faculty_availability", "F0"), ("classroom_availability", "R1")])
def test_availability(field, resource):
    p = impossible_problem()
    p = replace(p, requirements=p.requirements[:1], classrooms=("R1",))
    for windows in ((), (Availability(p.working_days[0], time(10), time(11)),),
                    (Availability(p.working_days[0], time(9), time(9, 30)),)):
        problem = replace(p, **{field: {resource: windows}})
        result = generate_timetable(problem)
        assert result.success == generate_csp(problem).success
        if result.success:
            assert result.lectures[0].start == time(10)


def test_empty_and_missing_resources():
    assert generate_timetable(replace(DEMO_PROBLEM, requirements=())).success
    assert generate_timetable(replace(DEMO_PROBLEM, time_slots=())).status == "infeasible"


@pytest.mark.parametrize("limit", [0, -1, float("inf"), float("nan")])
def test_invalid_time_limit(limit):
    with pytest.raises(ValueError):
        generate_timetable(DEMO_PROBLEM, time_limit_seconds=limit)


def test_timeout_does_not_claim_infeasibility():
    result = generate_timetable(DEMO_PROBLEM, time_limit_seconds=1e-9)
    assert result.status == "timeout" and result.solver_status == "UNKNOWN"
    assert not result.success and not result.lectures


def test_room_availability_depends_on_selected_room():
    p = impossible_problem()
    p = replace(p, requirements=p.requirements[:1], classroom_availability={
        "R1": (), "Lab1": (Availability(p.working_days[0], time(10), time(11)),)})
    result = generate_timetable(p)
    assert result.success and result.lectures[0].classroom == "Lab1"
    assert result.lectures[0].start == time(10)
