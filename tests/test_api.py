from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi", reason="Install the api extra")
pytest.importorskip("httpx", reason="Install the api-test extra")

from fastapi.testclient import TestClient

from campusflow.api.main import app
from campusflow.api import services
from campusflow.api.schemas import GenerateRequest


@pytest.fixture
def client(tmp_path, monkeypatch, authenticate_client):
    monkeypatch.setenv("CAMPUSFLOW_DATABASE_URL", f"sqlite:///{(tmp_path / 'api.db').as_posix()}")
    with TestClient(app, raise_server_exceptions=False) as client:
        authenticate_client(client)
        yield client


@pytest.fixture
def payload():
    return {"solver": "csp", "problem": {
        "faculty": [{"name": "Dr. Rao", "subjects": ["Mathematics"]}],
        "batches": ["CSE-2A"], "classrooms": ["C-101"], "working_days": ["Monday"],
        "time_slots": [{"start": "09:00", "end": "10:00"}, {"start": "10:00", "end": "11:00"}],
        "requirements": [{"id": "MATH", "subject": "Mathematics", "faculty": "Dr. Rao",
                          "batch": "CSE-2A", "weekly_sessions": 2, "duration_minutes": 60}],
    }}


def test_health_and_docs(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_solvers(client, monkeypatch):
    monkeypatch.setattr(services, "cp_sat_available", lambda: False)
    result = client.get("/api/solvers")
    assert result.status_code == 200
    assert result.json()["solvers"] == [
        {"name": "csp", "available": True}, {"name": "cp-sat", "available": False}]


@pytest.mark.parametrize("solver", ["csp", "cp-sat"])
def test_real_generation_and_validation(client, payload, solver):
    if solver == "cp-sat":
        pytest.importorskip("ortools")
    payload["solver"] = solver
    response = client.post("/api/timetables/generate", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "success" and result["solver"] == solver
    assert len(result["lectures"]) == 2 and result["validation"]["valid"]
    validated = client.post("/api/timetables/validate", json={
        "problem": payload["problem"], "lectures": result["lectures"]})
    assert validated.status_code == 200 and validated.json()["status"] == "valid"


@pytest.mark.parametrize("change", ["unknown_faculty", "duration", "boolean_count", "timezone", "extra", "solver", "limit", "capacity"])
def test_invalid_input(client, payload, change):
    req = payload["problem"]["requirements"][0]
    if change == "unknown_faculty":
        req["faculty"] = "Unknown"
    elif change == "duration":
        req["duration_minutes"] = 0
    elif change == "boolean_count":
        req["weekly_sessions"] = True
    elif change == "timezone":
        payload["problem"]["time_slots"][0]["start"] = "09:00:00+00:00"
    elif change == "extra":
        payload["unexpected"] = 1
    elif change == "solver":
        payload["solver"] = "unknown"
    elif change == "limit":
        payload["time_limit_seconds"] = 31
    else:
        req["weekly_sessions"] = 501
    response = client.post("/api/timetables/generate", json=payload)
    assert response.status_code == 422
    assert response.json()["status"] == "invalid_input" and response.json()["errors"]


def test_impossible(client, payload):
    payload["problem"]["requirements"][0]["weekly_sessions"] = 3
    response = client.post("/api/timetables/generate", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "infeasible" and response.json()["lectures"] == []


def test_validation_reports_conflicts_and_missing_sessions(client, payload):
    lectures = [{"id": "MATH:1", "subject": "Mathematics", "faculty": "Dr. Rao", "batch": "CSE-2A",
                 "classroom": "C-101", "day": "Monday", "start": "09:00", "end": "10:00"}]
    missing = client.post("/api/timetables/validate", json={"problem": payload["problem"], "lectures": lectures})
    assert missing.json()["status"] == "invalid"
    assert any("Missing session" in e for e in missing.json()["validation"]["errors"])
    lectures.append({**lectures[0], "id": "MATH:2", "start": "09:30", "end": "10:30"})
    conflict = client.post("/api/timetables/validate", json={"problem": payload["problem"], "lectures": lectures})
    assert conflict.status_code == 200 and not conflict.json()["validation"]["valid"]
    assert any("faculty, classroom, batch" in e for e in conflict.json()["validation"]["errors"])


def test_cp_sat_missing(client, payload, monkeypatch):
    monkeypatch.setattr(services, "cp_sat_available", lambda: False)
    payload["solver"] = "cp-sat"
    result = client.post("/api/timetables/generate", json=payload)
    assert result.status_code == 503 and result.json()["status"] == "unavailable"


def test_real_worker_timeout(client, payload, monkeypatch):
    monkeypatch.setattr(services, "WORKER_OVERHEAD_SECONDS", 0)
    payload["time_limit_seconds"] = 0.001
    result = client.post("/api/timetables/generate", json=payload)
    assert result.status_code == 504
    assert result.json()["status"] == "timeout" and result.json()["lectures"] == []
    # A timed-out request must release its capacity permit.
    payload["time_limit_seconds"] = 15
    assert client.post("/api/timetables/generate", json=payload).json()["status"] == "success"


def test_cp_sat_timeout_mapping(payload, monkeypatch):
    pytest.importorskip("ortools")
    from campusflow import cp_sat_scheduler
    monkeypatch.setattr(cp_sat_scheduler, "generate_timetable", lambda *a, **kw: SimpleNamespace(status="timeout"))
    payload["solver"] = "cp-sat"
    result = services.solve_in_worker(GenerateRequest.model_validate(payload))
    assert result.status == "timeout" and not result.lectures


def test_internal_error_is_redacted(client, payload, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("secret internal filesystem information")
    monkeypatch.setattr(services, "validate", broken)
    response = client.post("/api/timetables/validate", json={"problem": payload["problem"], "lectures": []})
    assert response.status_code == 500 and response.json()["status"] == "internal_error"
    assert "secret" not in response.text


def test_worker_error_is_redacted(client, payload, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("secret internal filesystem information")
    monkeypatch.setattr(services.subprocess, "run", broken)
    result = client.post("/api/timetables/generate", json=payload)
    assert result.status_code == 500 and "secret" not in result.text


def test_capacity_limit(client, payload):
    assert services._capacity.acquire(False) and services._capacity.acquire(False)
    try:
        response = client.post("/api/timetables/generate", json=payload)
        assert response.status_code == 503 and response.json()["status"] == "busy"
    finally:
        services._capacity.release()
        services._capacity.release()


def test_long_requirement_id(payload):
    payload["problem"]["requirements"][0]["id"] = "R" * 200
    result = services.solve_in_worker(GenerateRequest.model_validate(payload))
    assert result.status == "success" and len(result.lectures[0].id) == 202


def test_engine_validation_failure_is_internal(payload, monkeypatch):
    from campusflow import scheduler
    monkeypatch.setattr(scheduler, "generate_timetable", lambda *a: SimpleNamespace(
        success=False, reason="Validation failed: internal details"))
    result = services.solve_in_worker(GenerateRequest.model_validate(payload))
    assert result.status == "internal_error" and "details" not in result.message


def test_local_cors_only(client):
    for origin, allowed in [("http://localhost:5173", True), ("https://example.com", False)]:
        response = client.options("/api/timetables/generate", headers={
            "Origin": origin, "Access-Control-Request-Method": "POST"})
        assert (response.headers.get("access-control-allow-origin") == origin) == allowed
