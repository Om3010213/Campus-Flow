from datetime import time
import pytest

from campusflow.generation_demo import DEMO_PROBLEM
from campusflow.school_demo import SCHOOL_PROBLEM
from campusflow.scheduler import generate_timetable
from campusflow.validation import validate_timetable


@pytest.mark.parametrize("engine", ["csp", "cp-sat"])
@pytest.mark.parametrize("kind,problem", [("SCHOOL", SCHOOL_PROBLEM), ("COLLEGE", DEMO_PROBLEM)])
def test_shared_engines_support_both_institution_types(engine, kind, problem):
    generate = generate_timetable
    if engine == "cp-sat":
        pytest.importorskip("ortools")
        from campusflow.cp_sat_scheduler import generate_timetable as generate
    result = generate(problem)
    assert result.success
    assert len(result.lectures) == sum(r.weekly_sessions for r in problem.requirements)
    assert validate_timetable(problem, result.lectures).valid
    if kind == "SCHOOL":
        for lecture in result.lectures:
            for start, end in ((time(10, 20), time(10, 40)), (time(12), time(12, 40))):
                assert not (lecture.start < end and start < lecture.end)
            if lecture.faculty == "T-MATH":
                assert lecture.end <= time(12)
