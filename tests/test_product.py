import time
from copy import deepcopy

import pytest
pytest.importorskip("sqlalchemy")
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from campusflow.api.main import app
from campusflow.product import database as db, catalog, versions
from campusflow.product.seed import seed
from campusflow.product.worker import solve


@pytest.fixture
def client(tmp_path, monkeypatch, authenticate_client):
    monkeypatch.setenv("CAMPUSFLOW_DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    with TestClient(app, raise_server_exceptions=False) as client:
        authenticate_client(client)
        yield client


def data(response):
    assert response.status_code < 300, response.text
    return response.json()["data"]


def seed_and_save(client):
    data(client.post("/api/product/seed"))
    with db.database().connect() as conn:
        payload = catalog.snapshot(conn)
    payload.update(solver="csp", time_limit_seconds=5)
    result = solve(payload)
    assert result["status"] == "success"
    with catalog.transaction() as conn:
        return versions.create(conn, "Autumn timetable", "College", payload["problem"], payload["policy"], result["lectures"])


def test_catalog_crud_validation_integrity(client):
    subject = {"id": "S1", "name": "Networks", "department": "CSE", "semester": 3}
    assert client.post("/api/product/records/subjects", json=subject).status_code == 201
    assert client.post("/api/product/records/subjects", json=subject).status_code == 409
    faculty = {"id": "F1", "name": "Dr Rao", "department": "CSE", "subject_ids": ["S1"]}
    data(client.post("/api/product/records/faculty", json=faculty))
    assert client.delete("/api/product/records/subjects/S1").status_code == 409
    changed = data(client.put("/api/product/records/faculty/F1", json={**faculty, "name": "Dr A Rao"}))
    assert changed["name"] == "Dr A Rao"
    assert len(data(client.get("/api/product/records/faculty?q=rao&department=CSE"))) == 1
    assert not data(client.get("/api/product/records/faculty?q=missing"))
    assert client.post("/api/product/records/rooms", json={"id": "R1", "name": "Room", "capacity": -1}).status_code == 422
    assert client.post("/api/product/records/faculty", json={**faculty, "id": "F2", "subject_ids": ["Missing"]}).status_code == 409
    data(client.delete("/api/product/records/faculty/F1"))
    data(client.delete("/api/product/records/subjects/S1"))
    with db.database().connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert set(conn.execute(select(db.schema_versions.c.version)).scalars()) == {1, 2, 3, 4, 5, 6}
    db.migrate()  # migration is idempotent


def test_settings_breaks_and_seed_safety(client):
    data(client.post("/api/product/seed"))
    assert client.post("/api/product/seed").status_code == 409
    settings = data(client.get("/api/product/settings"))
    settings["breaks"] = [{"start": "11:00", "end": "13:00"}, {"start": "12:00", "end": "14:00"}]
    assert client.put("/api/product/settings", json=settings).status_code == 422
    with db.database().connect() as conn:
        snapshot = catalog.snapshot(conn)
    assert not any(s["start"] == "12:00:00" for s in snapshot["problem"]["time_slots"])


def test_full_job_save_publish_export_workflow(client):
    data(client.post("/api/product/seed"))
    identifier = data(client.post("/api/product/jobs", json={"solver": "csp", "name": "Test", "time_limit_seconds": 10}))["id"]
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        job = data(client.get(f"/api/product/jobs/{identifier}"))
        if job["state"] not in ("queued", "running"):
            break
        time.sleep(0.1)
    assert job["state"] == "success", job
    version = data(client.post(f"/api/product/jobs/{identifier}/save"))
    assert len(version["lectures"]) == 16 and version["validation"]["valid"]
    assert data(client.post(f"/api/product/jobs/{identifier}/save"))["id"] == version["id"]
    url = f"/api/product/versions/{version['id']}"
    published = data(client.post(url + "/publish", json={"revision": 1}))
    assert published["state"] == "published"
    assert client.put(url, json={"revision": 2, "lectures": version["lectures"]}).status_code == 409
    assert client.delete("/api/product/records/faculty/F101").status_code == 409
    assert client.delete(url).status_code == 409
    report = data(client.get(url + "/reports"))
    assert report["scheduled_sessions"] == 16 and not report["warnings"]
    assert sum(f["minutes"] for f in report["faculty"]) == 1200
    csv = client.get(url + "/export/csv")
    assert csv.status_code == 200 and "Data Structures" in csv.text
    pdf = client.get(url + "/export/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_edits_publishing_versions_and_stale_revision(client):
    version = seed_and_save(client)
    url = f"/api/product/versions/{version['id']}"
    missing = version["lectures"][:-1]
    edited = data(client.put(url, json={"revision": 1, "lectures": missing}))
    assert edited["state"] == "draft" and not edited["validation"]["valid"]
    assert client.post(url + "/publish", json={"revision": 2}).status_code == 422
    assert client.put(url, json={"revision": 1, "lectures": version["lectures"]}).status_code == 409
    restored = data(client.put(url, json={"revision": 2, "lectures": version["lectures"]}))
    published = data(client.post(url + "/publish", json={"revision": restored["revision"]}))
    copy = data(client.post(url + "/duplicate"))
    assert copy["state"] == "draft" and copy["source_id"] == version["id"]
    data(client.post(f"/api/product/versions/{copy['id']}/publish", json={"revision": 1}))
    assert data(client.get(url))["state"] == "archived"
    assert sum(v["state"] == "published" for v in data(client.get("/api/product/versions"))) == 1


def test_invalid_room_and_conflicts_rejected(client):
    version = seed_and_save(client)
    url = f"/api/product/versions/{version['id']}"
    lectures = deepcopy(version["lectures"])
    lab = next(l for l in lectures if l["subject"] == "CS205L")
    lab["classroom"] = "C101"
    response = client.put(url, json={"revision": 1, "lectures": lectures})
    assert response.status_code == 422
    assert any("subject type" in e for e in response.json()["errors"])
    assert data(client.get(url))["revision"] == 1


@pytest.mark.parametrize("optimize", [False, True])
def test_product_cp_constraints(client, optimize):
    pytest.importorskip("ortools")
    data(client.post("/api/product/seed"))
    with db.database().connect() as conn:
        payload = catalog.snapshot(conn)
    payload.update(solver="cp-sat", time_limit_seconds=3, optimize=optimize)
    result = solve(payload)
    assert result["status"] == "success", result
    assert result["validation"]["valid"]
    assert all(l["classroom"] == "LAB1" for l in result["lectures"] if l["subject"] == "CS205L")


def test_rescheduling_does_not_modify_source(client):
    pytest.importorskip("ortools")
    version = seed_and_save(client)
    original = deepcopy(version["lectures"])
    lecture = original[0]
    url = f"/api/product/versions/{version['id']}"
    job_id = data(client.post(url + "/reschedule", json={"faculty_id": lecture["faculty"], "day": lecture["day"],
                                                         "time_limit_seconds": 5}))["id"]
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        job = data(client.get(f"/api/product/jobs/{job_id}"))
        if job["state"] not in ("queued", "running"):
            break
        time.sleep(0.1)
    assert job["state"] == "success", job
    assert all(l["day"] != lecture["day"] for l in job["result"]["lectures"] if l["faculty"] == lecture["faculty"])
    assert data(client.get(url))["lectures"] == original
    changed = data(client.post(f"/api/product/jobs/{job_id}/save"))
    assert changed["source_id"] == version["id"] and changed["validation"]["valid"]
