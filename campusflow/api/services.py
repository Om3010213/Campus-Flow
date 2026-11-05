"""Bounded subprocess integration keeps CPU-bound engines out of the API process."""

import logging
import subprocess
import sys
from functools import lru_cache
from threading import BoundedSemaphore

from campusflow.validation import validate_timetable
from .schemas import GenerateRequest, LectureInput, TimetableResponse, ValidateRequest, ValidationOutput

logger = logging.getLogger(__name__)
WORKER_OVERHEAD_SECONDS = 5
_capacity = BoundedSemaphore(2)


@lru_cache(maxsize=1)
def cp_sat_available() -> bool:
    try:
        from ortools.sat.python import cp_model
        cp_model.CpModel()
        return True
    except (ImportError, OSError):
        return False


def validate(request: ValidateRequest) -> TimetableResponse:
    result = validate_timetable(request.problem.to_domain(), (l.to_domain() for l in request.lectures))
    return TimetableResponse(status="valid" if result.valid else "invalid",
                             validation=ValidationOutput(valid=result.valid, errors=list(result.errors)))


def solve_in_worker(request: GenerateRequest) -> TimetableResponse:
    """Called in an isolated interpreter; contains no HTTP or process management."""
    problem = request.problem.to_domain()
    if request.solver == "cp-sat":
        try:
            from campusflow.cp_sat_scheduler import generate_timetable
            result = generate_timetable(problem, time_limit_seconds=request.time_limit_seconds)
        except (ImportError, OSError):
            return TimetableResponse(status="unavailable", solver=request.solver,
                                     message="CP-SAT is unavailable. Install the cp-sat extra and restart.")
        if result.status == "timeout":
            return TimetableResponse(status="timeout", solver=request.solver, message="Solver time limit reached.")
        if result.status == "invalid":
            return TimetableResponse(status="internal_error", solver=request.solver,
                                     message="Timetable generation failed.")
    else:
        from campusflow.scheduler import generate_timetable
        result = generate_timetable(problem)
    if not result.success:
        if result.reason.startswith("Validation failed:"):
            return TimetableResponse(status="internal_error", solver=request.solver,
                                     message="Timetable generation failed.")
        return TimetableResponse(status="infeasible", solver=request.solver,
                                 message="No timetable satisfies the supplied constraints.")
    checked = validate_timetable(problem, result.lectures)
    if not checked.valid:
        raise RuntimeError("Generated timetable failed independent validation")
    return TimetableResponse(status="success", solver=request.solver,
                             lectures=[LectureInput.model_validate(l) for l in result.lectures],
                             validation=ValidationOutput(valid=True))


def generate(request: GenerateRequest) -> TimetableResponse:
    if request.solver == "cp-sat" and not cp_sat_available():
        return TimetableResponse(status="unavailable", solver=request.solver,
                                 message="CP-SAT is unavailable. Install the cp-sat extra and restart.")
    if not _capacity.acquire(blocking=False):
        return TimetableResponse(status="busy", solver=request.solver, message="Generation capacity is busy; retry later.")
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "campusflow.api.worker"], input=request.model_dump_json(),
            capture_output=True, text=True,
            timeout=request.time_limit_seconds + WORKER_OVERHEAD_SECONDS, check=True,
        )
        return TimetableResponse.model_validate_json(completed.stdout)
    except subprocess.TimeoutExpired:
        # subprocess.run kills and reaps its child before raising TimeoutExpired.
        return TimetableResponse(status="timeout", solver=request.solver,
                                 message="Generation deadline reached; worker terminated.")
    except Exception:
        logger.exception("Timetable worker failed")
        return TimetableResponse(status="internal_error", solver=request.solver,
                                 message="Timetable generation failed.")
    finally:
        _capacity.release()
