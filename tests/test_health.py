from fastapi.testclient import TestClient

from app import main


def _setup_main_mocks(monkeypatch, ping_raises=None):
    class FakeAdmin:
        @staticmethod
        def command(cmd):
            if ping_raises:
                raise ping_raises
            return {"ok": 1}

    class FakeClient:
        admin = FakeAdmin()

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


def test_health_endpoint_returns_expected_response(monkeypatch):
    _setup_main_mocks(monkeypatch)

    with TestClient(main.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "application": "attendance-management-api",
    }
    # Verify request ID middleware attached header
    assert "x-request-id" in response.headers


def test_health_live_endpoint(monkeypatch):
    _setup_main_mocks(monkeypatch)

    with TestClient(main.app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "alive",
        "application": "attendance-management-api",
    }


def test_health_ready_success(monkeypatch):
    _setup_main_mocks(monkeypatch)

    with TestClient(main.app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["database"] == "connected"


def test_health_ready_failure_returns_503(monkeypatch):
    _setup_main_mocks(monkeypatch)

    with TestClient(main.app) as client:

        def _failing_command(cmd):
            raise ConnectionError("MongoDB down")

        monkeypatch.setattr(main.client.admin, "command", _failing_command)
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["database"] == "disconnected"


def test_request_id_preserved_when_provided(monkeypatch):
    _setup_main_mocks(monkeypatch)

    custom_id = "custom-uuid-12345"
    with TestClient(main.app) as client:
        response = client.get("/health", headers={"X-Request-ID": custom_id})

    assert response.headers.get("x-request-id") == custom_id
