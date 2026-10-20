from fastapi.testclient import TestClient

from app import main
from app.routers import auth
from app.security.auth_utils import decode_access_token, hash_password
from app.services import auth_service


def _configure_tenant_admin_login(monkeypatch, fake_collection):
    email = "admin@example.com"
    tenant_id = "tenant_acme"
    admins = fake_collection(
        [
            {
                "email": email,
                "password_hash": hash_password("ValidPassword123"),
                "role": "admin",
                "is_active": True,
            }
        ]
    )
    tenants = fake_collection([{"id": tenant_id, "status": "active"}])
    memberships = fake_collection(
        [
            {
                "user_id": email,
                "tenant_id": tenant_id,
                "status": "active",
                "role": "admin",
            }
        ]
    )

    monkeypatch.setattr(
        main,
        "client",
        type(
            "FakeClient",
            (),
            {
                "admin": type(
                    "FakeAdmin", (), {"command": staticmethod(lambda _: None)}
                )(),
                "close": staticmethod(lambda: None),
            },
        )(),
    )
    for name in (
        "create_database_indexes",
        "create_tenant_indexes",
        "create_admin_indexes",
        "create_attendance_indexes",
        "create_notification_indexes",
        "start_scheduler",
        "stop_scheduler",
    ):
        monkeypatch.setattr(main, name, lambda: None)

    monkeypatch.setattr(auth, "admins_collection", admins)
    monkeypatch.setattr(auth_service, "admins_collection", admins)
    monkeypatch.setattr(auth_service, "tenants_collection", tenants)
    monkeypatch.setattr(auth_service, "tenant_memberships_collection", memberships)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-32-chars-long-minimum")
    return tenant_id


def test_login_with_tenant_id_and_password(monkeypatch, fake_collection):
    tenant_id = _configure_tenant_admin_login(monkeypatch, fake_collection)

    with TestClient(main.app) as client:
        response = client.post(
            "/api/v1/auth/admin/login",
            json={"tenant_id": tenant_id, "password": "ValidPassword123"},
        )

    assert response.status_code == 200
    token = response.json()["access_token"]
    assert decode_access_token(token)["tenant_id"] == tenant_id


def test_tenant_id_login_rejects_wrong_password(monkeypatch, fake_collection):
    tenant_id = _configure_tenant_admin_login(monkeypatch, fake_collection)

    with TestClient(main.app) as client:
        response = client.post(
            "/api/v1/auth/admin/login",
            json={"tenant_id": tenant_id, "password": "WrongPassword123"},
        )

    assert response.status_code == 401


def test_tenant_id_login_requires_email_when_tenant_has_multiple_admins(
    monkeypatch,
    fake_collection,
):
    tenant_id = _configure_tenant_admin_login(monkeypatch, fake_collection)
    auth_service.tenant_memberships_collection.insert_one(
        {
            "user_id": "second-admin@example.com",
            "tenant_id": tenant_id,
            "status": "active",
            "role": "admin",
        }
    )

    with TestClient(main.app) as client:
        response = client.post(
            "/api/v1/auth/admin/login",
            json={"tenant_id": tenant_id, "password": "ValidPassword123"},
        )

    assert response.status_code == 400
    assert "Log in with email and password" in response.json()["detail"]
