from fastapi.testclient import TestClient

from app import main


def test_health_endpoint_returns_expected_response(monkeypatch):
    class FakeClient:
        admin = type("Admin", (), {"command": staticmethod(lambda command: None)})()

        @staticmethod
        def close():
            pass

    monkeypatch.setattr(main, "client", FakeClient())
    monkeypatch.setattr(main, "create_database_indexes", lambda: None)
    monkeypatch.setattr(main, "create_admin_indexes", lambda: None)
    monkeypatch.setattr(main, "create_attendance_indexes", lambda: None)
    monkeypatch.setattr(main, "create_notification_indexes", lambda: None)
    monkeypatch.setattr(main, "start_scheduler", lambda: None)
    monkeypatch.setattr(main, "stop_scheduler", lambda: None)

    with TestClient(main.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "application": "attendance-management-api",
    }
