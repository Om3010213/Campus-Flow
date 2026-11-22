import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from campusflow.api.main import app
from campusflow.auth import service
from campusflow.auth.tables import users, sessions
from campusflow.auth.config import settings
from campusflow.product import database as db, catalog, versions
from campusflow.product.seed import seed
from campusflow.product.worker import solve


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CAMPUSFLOW_DATABASE_URL", f"sqlite:///{(tmp_path / 'auth.db').as_posix()}")
    monkeypatch.setenv("CAMPUSFLOW_ENV", "development")
    monkeypatch.setenv("CAMPUSFLOW_SESSION_SECRET", "test-only-secret-for-local-auth-tests-123456")
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def bootstrap(client):
    token = client.get("/api/auth/session").json()["data"]["csrf_token"]
    client.headers["X-CSRF-Token"] = token


def test_login_hash_cookie_logout_and_replay(client, authenticate_client):
    user = authenticate_client(client)
    assert user["password_hash"].startswith("$argon2id$")
    assert "Test passphrase" not in user["password_hash"]
    cookie = client.cookies.get("campusflow_session")
    result = client.get("/api/auth/session")
    assert "HttpOnly" in result.headers["set-cookie"] and "SameSite=strict" in result.headers["set-cookie"]
    assert "password_hash" not in result.text
    with db.database().connect() as conn:
        assert cookie not in str(list(conn.execute(select(sessions)).mappings()))
    assert client.post("/api/auth/logout").status_code == 200
    client.cookies.set("campusflow_session", cookie)
    assert client.get("/api/product/catalog").status_code == 401


def test_invalid_login_throttling_and_csrf(client):
    bootstrap(client)
    body = {"username": "unknown", "password": "wrong"}
    for _ in range(5):
        assert client.post("/api/auth/login", json=body).status_code == 401
    response = client.post("/api/auth/login", json=body)
    assert response.status_code == 429 and response.headers["retry-after"] == "900"
    assert client.post("/api/auth/login", json=body, headers={"X-CSRF-Token": ""}).status_code == 403


@pytest.mark.parametrize("field,value", [("expires_at", 0), ("last_seen", 0)])
def test_expiration(client, authenticate_client, field, value):
    authenticate_client(client)
    with catalog.transaction() as conn:
        conn.execute(update(sessions).values(**{field: value}))
    assert client.get("/api/product/catalog").status_code == 401


@pytest.mark.parametrize("path,method", [("/api/product/catalog", "GET"), ("/api/solvers", "GET"),
    ("/api/timetables/generate", "POST"), ("/api/product/seed", "POST"), ("/api/auth/users", "GET")])
def test_anonymous_denied(client, path, method):
    assert client.request(method, path).status_code == 401


def test_csrf_origin_and_rotation(client, authenticate_client):
    bootstrap(client)
    old = client.headers["X-CSRF-Token"]
    authenticate_client(client)
    assert old != client.headers["X-CSRF-Token"]
    for token in ("", old, "bad"):
        assert client.post("/api/product/seed", headers={"X-CSRF-Token": token}).status_code == 403
    assert client.post("/api/product/seed", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/product/seed", headers={"Origin": "http://localhost:5173"}).status_code == 200


def test_password_change_revokes_other_sessions(client, authenticate_client):
    user = authenticate_client(client)
    old_cookie, old_csrf = client.cookies.get("campusflow_session"), client.headers["X-CSRF-Token"]
    changed = client.post("/api/auth/password", json={"current_password": "Test passphrase 123!", "new_password": "Another safe phrase 456!"})
    assert changed.status_code == 200
    assert changed.json()["data"]["csrf_token"] != old_csrf
    with db.database().connect() as conn:
        stored = conn.execute(select(users.c.password_hash).where(users.c.id == user["id"])).scalar_one()
        assert service.verify(stored, "Another safe phrase 456!")
    client.cookies.clear()
    client.cookies.set("campusflow_session", old_cookie)
    assert client.get("/api/solvers").status_code == 401


@pytest.mark.parametrize("role,path,method,expected", [
    ("viewer", "/api/product/catalog", "GET", 403),
    ("viewer", "/api/product/jobs", "POST", 403),
    ("viewer", "/api/timetables/validate", "POST", 403),
    ("viewer", "/api/auth/users", "GET", 403),
    ("planner", "/api/product/catalog", "GET", 200),
    ("planner", "/api/product/seed", "POST", 403),
    ("planner", "/api/product/records/faculty", "POST", 403),
    ("planner", "/api/product/settings", "PUT", 403),
    ("planner", "/api/auth/users", "POST", 403),
    ("planner", "/api/product/records/requirements", "POST", 422),
])
def test_role_matrix(client, authenticate_client, role, path, method, expected):
    authenticate_client(client, role=role)
    response = client.request(method, path, json={} if method != "GET" else None)
    assert response.status_code == expected, response.text


def test_scoped_published_access(client, authenticate_client):
    with catalog.transaction() as conn:
        seed(conn)
        payload = catalog.snapshot(conn)
    result = solve({**payload, "solver": "csp", "time_limit_seconds": 5})
    with catalog.transaction() as conn:
        draft = versions.create(conn, "Draft", "College", payload["problem"], payload["policy"], result["lectures"])
        public = versions.create(conn, "Published", "College", payload["problem"], payload["policy"], result["lectures"], state="published")
        other = versions.create(conn, "Private", "Other", payload["problem"], payload["policy"], result["lectures"], state="published")
    authenticate_client(client, role="viewer")
    visible = client.get("/api/product/versions").json()["data"]
    assert [v["id"] for v in visible] == [public["id"]]
    for v in (draft, other):
        for suffix in ("", "/reports", "/export/csv", "/export/pdf"):
            assert client.get(f"/api/product/versions/{v['id']}{suffix}").status_code == 403
    detail = client.get(f"/api/product/versions/{public['id']}")
    assert detail.status_code == 200 and "preferred_start" not in detail.text and "faculty_availability" not in detail.text
    assert client.get(f"/api/product/versions/{public['id']}/export/csv").status_code == 200
    assert client.post(f"/api/product/versions/{public['id']}/duplicate").status_code == 403
    authenticate_client(client, role="planner", username="planner")
    assert client.post(f"/api/product/versions/{draft['id']}/publish", json={"revision": 1}).status_code == 403
    assert client.post(f"/api/product/versions/{draft['id']}/duplicate").status_code == 200
    assert client.post("/api/product/jobs", json={"scope": "Other"}).status_code == 403


def test_manage_users_and_last_admin(client, authenticate_client):
    admin = authenticate_client(client)
    blocked = client.put(f"/api/auth/users/{admin['id']}", json={"role": "viewer", "active": True, "scopes": []})
    assert blocked.status_code == 409
    created = client.post("/api/auth/users", json={"username": "planner", "password": "Temporary secret 123!", "role": "planner", "scopes": ["College"]})
    assert created.status_code == 201 and created.json()["data"]["must_change_password"]
    assert "password_hash" not in created.text
    assert client.post("/api/auth/users", json={"username": "bad", "password": "short"}).status_code == 422
    assert client.get("/api/auth/users").status_code == 200
    edited = client.put(f"/api/auth/users/{admin['id']}", json={"role": "administrator", "active": True, "scopes": []})
    assert edited.status_code == 200
    assert client.get("/api/auth/users").status_code == 401


def test_temporary_password_forces_change(client):
    with catalog.transaction() as conn:
        service.create_user(conn, "newuser", "Temporary secret 123!", "viewer", ["College"])
    bootstrap(client)
    response = client.post("/api/auth/login", json={"username": "newuser", "password": "Temporary secret 123!"})
    client.headers["X-CSRF-Token"] = response.json()["data"]["csrf_token"]
    assert client.get("/api/product/versions").status_code == 403
    assert client.post("/api/auth/password", json={"current_password": "Temporary secret 123!", "new_password": "My own long passphrase!"}).status_code == 200
    assert client.get("/api/product/versions").status_code == 200


def test_production_settings_and_https(client, monkeypatch):
    monkeypatch.setenv("CAMPUSFLOW_ENV", "production")
    monkeypatch.delenv("CAMPUSFLOW_SESSION_SECRET", raising=False)
    with pytest.raises(RuntimeError): settings()
    monkeypatch.setenv("CAMPUSFLOW_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("CAMPUSFLOW_ALLOWED_ORIGINS", "http://example.com")
    with pytest.raises(RuntimeError): settings()
    monkeypatch.setenv("CAMPUSFLOW_ALLOWED_ORIGINS", "https://campus.example.com")
    app.state.security = settings()
    assert client.get("/api/auth/session").status_code == 400
    ready = client.get("/api/ready")
    assert ready.status_code == 200 and ready.headers["cache-control"] == "no-store"
    secure = TestClient(app, base_url="https://campus.example.com")
    response = secure.get("/api/auth/session")
    assert "__Host-campusflow=" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"] and "HttpOnly" in response.headers["set-cookie"]


def test_local_provisioning_and_recovery(client, monkeypatch):
    from campusflow.auth import cli
    monkeypatch.setattr(cli, "getpass", lambda _: "Local setup passphrase!")
    monkeypatch.setattr("sys.argv", ["auth", "create-admin", "initial-admin"])
    cli.main()
    bootstrap(client)
    login = client.post("/api/auth/login", json={"username": "initial-admin", "password": "Local setup passphrase!"})
    assert login.status_code == 200 and not login.json()["data"]["user"]["must_change_password"]
    with pytest.raises(SystemExit):
        cli.main()  # Never creates another administrator through initial setup.
    monkeypatch.setattr(cli, "getpass", lambda _: "Temporary recovery phrase!")
    monkeypatch.setattr("sys.argv", ["auth", "reset-password", "initial-admin"])
    cli.main()
    assert client.get("/api/solvers").status_code == 401
    bootstrap(client)
    assert client.post("/api/auth/login", json={"username": "initial-admin", "password": "Local setup passphrase!"}).status_code == 401
    recovered = client.post("/api/auth/login", json={"username": "initial-admin", "password": "Temporary recovery phrase!"})
    assert recovered.status_code == 200 and recovered.json()["data"]["user"]["must_change_password"]


def test_disabled_account_and_changed_role_revoke_sessions(client, authenticate_client):
    user = authenticate_client(client, role="planner")
    with catalog.transaction() as conn:
        conn.execute(update(users).where(users.c.id == user["id"]).values(active=0))
    assert client.get("/api/product/catalog").status_code == 401
    bootstrap(client)
    assert client.post("/api/auth/login", json={"username": user["username"], "password": "Test passphrase 123!"}).status_code == 401


def test_upgrade_preserves_v1_data(tmp_path):
    from sqlalchemy import create_engine, inspect, text
    from campusflow.product.migrations import upgrade
    engine = create_engine(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE schema_versions (version INTEGER PRIMARY KEY)"))
        conn.execute(text("INSERT INTO schema_versions VALUES (1)"))
        conn.execute(text("CREATE TABLE faculty (id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, department VARCHAR NOT NULL, max_daily_minutes INTEGER NOT NULL, preferred_start VARCHAR NOT NULL, preferred_end VARCHAR NOT NULL, restricted INTEGER NOT NULL)"))
        conn.execute(text("INSERT INTO faculty VALUES ('F1','Legacy Faculty','Science',240,'09:00','16:00',0)"))
    with pytest.raises(RuntimeError, match="migration required"):
        upgrade(engine)
    upgrade(engine, allow_tenant_upgrade=True)
    upgrade(engine)
    with engine.connect() as conn:
        row=conn.execute(select(db.faculty)).mappings().one()
        assert row['id']=='F1' and row['name']=='Legacy Faculty'
        assert set(conn.execute(select(db.schema_versions.c.version)).scalars()) == {1,2,3,4,5,6}
        assert conn.exec_driver_sql('PRAGMA foreign_key_check').fetchall()==[]
    assert {"auth_users", "auth_sessions", "auth_login_attempts"} <= set(inspect(engine).get_table_names())
    engine.dispose()
