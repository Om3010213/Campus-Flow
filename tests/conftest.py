import pytest


@pytest.fixture
def authenticate_client():
    """Exercise real login/CSRF for existing workflow tests; no auth bypass."""
    def login(client, role="administrator", username="test-admin", scopes=None, password="Test passphrase 123!"):
        from campusflow.product.catalog import transaction
        from campusflow.auth.service import create_user
        with transaction() as conn:
            user = create_user(conn, username, password, role, ["College"] if scopes is None else scopes, must_change=False)
        bootstrap = client.get("/api/auth/session").json()["data"]
        response = client.post("/api/auth/login", json={"username": username, "password": password},
                               headers={"X-CSRF-Token": bootstrap["csrf_token"]})
        assert response.status_code == 200, response.text
        client.headers["X-CSRF-Token"] = response.json()["data"]["csrf_token"]
        return user
    return login
