from fastapi.testclient import TestClient

from app import main
from app.routers import auth
from app.security.auth_utils import create_access_token, hash_password
from app.services import auth_service


def _setup_security_mocks(monkeypatch, fake_collection):
    admins = fake_collection(
        [
            {
                "email": "admin@example.com",
                "password_hash": hash_password("ValidPassword123"),
                "role": "admin",
                "is_active": True,
            }
        ]
    )

    class FakeClient:
        admin = type("Admin", (), {"command": staticmethod(lambda cmd: None)})()

        @staticmethod
        def close():
            pass

    monkeypatch.setattr(main, "client", FakeClient())
    monkeypatch.setattr(main, "create_database_indexes", lambda: None)
    monkeypatch.setattr(main, "create_tenant_indexes", lambda: None)
    monkeypatch.setattr(main, "create_admin_indexes", lambda: None)
    monkeypatch.setattr(main, "create_attendance_indexes", lambda: None)
    monkeypatch.setattr(main, "create_notification_indexes", lambda: None)
    monkeypatch.setattr(main, "start_scheduler", lambda: None)
    monkeypatch.setattr(main, "stop_scheduler", lambda: None)
    monkeypatch.setattr(auth, "admins_collection", admins)
    monkeypatch.setattr(auth_service, "admins_collection", admins)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-32-chars-long-minimum")

    return admins


def test_admin_login_and_access_protected_endpoints(monkeypatch, fake_collection):
    _setup_security_mocks(monkeypatch, fake_collection)

    with TestClient(main.app) as client:
        # Step 1: Protected endpoints reject unauthenticated requests with 401
        for endpoint in (
            "/api/v1/compliance/weekly",
            "/api/v1/reports/attendance",
            "/api/v1/notifications",
        ):
            response = client.get(endpoint)
            assert response.status_code == 401, f"{endpoint} should require auth"

        # Step 2: Login with valid credentials succeeds
        login_res = client.post(
            "/api/v1/auth/admin/login",
            json={"email": "admin@example.com", "password": "ValidPassword123"},
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        assert token

        # Step 3: Login with invalid password returns 401
        bad_login = client.post(
            "/api/v1/auth/admin/login",
            json={"email": "admin@example.com", "password": "WrongPassword"},
        )
        assert bad_login.status_code == 401

        # Step 4: Access me endpoint with token
        headers = {"Authorization": f"Bearer {token}"}
        me_res = client.get("/api/v1/auth/admin/me", headers=headers)
        assert me_res.status_code == 200
        assert me_res.json()["email"] == "admin@example.com"
        assert me_res.json()["role"] == "admin"


def test_invalid_or_expired_jwt_rejected(monkeypatch, fake_collection):
    _setup_security_mocks(monkeypatch, fake_collection)

    with TestClient(main.app) as client:
        # Request with bogus token
        response = client.get(
            "/api/v1/auth/admin/me",
            headers={"Authorization": "Bearer not-a-valid-jwt-token"},
        )
        assert response.status_code == 401


def test_inactive_admin_cannot_login_or_reuse_an_existing_token(
    monkeypatch,
    fake_collection,
):
    admins = _setup_security_mocks(monkeypatch, fake_collection)
    existing_token = create_access_token("admin@example.com")
    admins.documents[0]["is_active"] = False

    with TestClient(main.app) as client:
        login_response = client.post(
            "/api/v1/auth/admin/login",
            json={"email": "admin@example.com", "password": "ValidPassword123"},
        )
        assert login_response.status_code == 401

        protected_response = client.get(
            "/api/v1/auth/admin/me",
            headers={"Authorization": f"Bearer {existing_token}"},
        )
        assert protected_response.status_code == 401
