"""Bounded job subprocess: reuses the engines with opt-in product constraints."""
import json
import sys
from time import perf_counter

from campusflow.api.schemas import ProblemInput, LectureInput
from .constraints import accept, configure, validate_snapshot


def solve(payload):
    problem = ProblemInput.model_validate(payload["problem"]).to_domain()
    policy = payload["policy"]
    fixed = payload.get("fixed")
    started = perf_counter()
    if payload["solver"] == "cp-sat":
        from campusflow.cp_sat_scheduler import generate_timetable
        result = generate_timetable(problem, time_limit_seconds=payload["time_limit_seconds"],
            configure_model=configure(policy, problem, optimize=payload.get("optimize", False),
                                      fixed=fixed, original=payload.get("original")),
            order_sessions=not bool(payload.get("original")))
        status = "success" if result.success else result.status
        if status == "invalid":
            status = "internal_error"
    else:
        from campusflow.scheduler import generate_timetable
        result = generate_timetable(problem, accept_assignment=lambda entries: accept(policy, entries, fixed))
        status = "success" if result.success else "infeasible"
        if result.reason.startswith("Validation failed:"):
            status = "internal_error"
    output = {"status": status, "solver": payload["solver"], "lectures": [],
              "message": result.reason, "duration_seconds": perf_counter() - started,
              "optimal": getattr(result, "status", "") == "optimal"}
    if result.success:
        output["lectures"] = [LectureInput.model_validate(l).model_dump(mode="json") for l in result.lectures]
        output["validation"] = validate_snapshot(payload["problem"], policy, output["lectures"])
        if payload.get("original"):
            output["changes"] = [{"id": l["id"], "before": payload["original"].get(l["id"]), "after": l}
                                 for l in output["lectures"] if payload["original"].get(l["id"]) != l]
        if not output["validation"]["valid"]:
            output.update(status="internal_error", lectures=[], message="Independent validation failed")
    return output


if __name__ == "__main__":
    print(json.dumps(solve(json.load(sys.stdin))))
