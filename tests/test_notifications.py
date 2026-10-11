from datetime import date
from unittest.mock import MagicMock

import pytest
from pymongo.errors import DuplicateKeyError

from app.schemas.compliance import EmployeeCompliance, WeeklyComplianceResponse
from app.services import notification_service


def test_send_notification_email_uses_configured_smtp(monkeypatch):
    smtp = MagicMock()
    smtp_context = MagicMock()
    smtp_context.__enter__.return_value = smtp
    monkeypatch.setattr(
        notification_service.smtplib, "SMTP", MagicMock(return_value=smtp_context)
    )
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "sender")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "noreply@example.test")

    notification_service.send_notification_email(
        "employee@example.test", "Policy notice", "Please review."
    )

    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("sender", "secret")
    smtp.send_message.assert_called_once()
    assert smtp.send_message.call_args.args[0]["To"] == "employee@example.test"


def test_send_notification_email_requires_configuration(monkeypatch):
    for variable in (
        "SMTP_HOST",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM_EMAIL",
    ):
        monkeypatch.delenv(variable, raising=False)

    with pytest.raises(RuntimeError, match="SMTP configuration is incomplete"):
        notification_service.send_notification_email(
            "employee@example.test", "Policy notice", "Please review."
        )


def test_duplicate_weekly_notification_is_skipped(
    monkeypatch,
    fake_collection,
    fixed_datetime,
):
    employees = fake_collection(
        [
            {
                "employee_id": "EMP001",
                "email": "employee@example.test",
            }
        ]
    )
    notifications = fake_collection(unique_fields=("employee_id", "week_start"))
    employee = EmployeeCompliance(
        employee_id="EMP001",
        employee_name="Taylor Example",
        department="Engineering",
        qualifying_days=1,
        total_hours=5,
        hours_shortfall=10,
        incomplete_sessions=0,
        compliance_status="violation",
        reason="Attendance requirements not met",
    )
    report = WeeklyComplianceResponse(
        week_start="2026-09-28",
        week_end="2026-10-04",
        evaluation_status="completed",
        total_employees=1,
        compliant_employees=0,
        violating_employees=1,
        employees_in_progress=0,
        employees_needing_review=0,
        employees=[employee],
    )
    monkeypatch.setattr(notification_service, "employees_collection", employees)
    monkeypatch.setattr(notification_service, "notifications_collection", notifications)
    monkeypatch.setattr(
        notification_service, "evaluate_weekly_compliance", lambda week: report
    )
    monkeypatch.setattr(
        notification_service, "send_notification_email", lambda **kwargs: None
    )
    monkeypatch.setattr(notification_service, "datetime", fixed_datetime)

    first = notification_service.process_weekly_violations(date(2026, 9, 28))
    second = notification_service.process_weekly_violations(date(2026, 9, 28))

    assert first == {
        "week_start": "2026-09-28",
        "week_end": "2026-10-04",
        "created": 1,
        "sent": 1,
        "failed": 0,
        "skipped": 0,
    }
    assert second["created"] == 0
    assert second["skipped"] == 1
    assert len(notifications.documents) == 1
    assert notifications.documents[0]["status"] == "sent"


def test_delivery_failure_is_recorded_and_retryable(
    monkeypatch,
    fake_collection,
    fixed_datetime,
):
    notifications = fake_collection(
        [
            {
                "notification_id": "notification-1",
                "recipient_email": "employee@example.test",
                "subject": "Policy notice",
                "body": "Please review.",
                "status": "pending",
                "attempts": 0,
                "last_error": None,
            }
        ]
    )
    monkeypatch.setattr(notification_service, "notifications_collection", notifications)
    monkeypatch.setattr(notification_service, "datetime", fixed_datetime)
    monkeypatch.setattr(
        notification_service,
        "send_notification_email",
        lambda **kwargs: (_ for _ in ()).throw(OSError("SMTP unavailable")),
    )

    result = notification_service.deliver_notification("notification-1")

    assert result["status"] == "failed"
    assert notifications.documents[0]["status"] == "failed"
    assert notifications.documents[0]["attempts"] == 1
    assert "SMTP unavailable" in notifications.documents[0]["last_error"]
    assert (
        notification_service.retry_failed_notification("notification-1")["status"]
        == "failed"
    )


def test_notification_duplicate_index_is_simulated_by_test_store(fake_collection):
    notifications = fake_collection(unique_fields=("employee_id", "week_start"))
    document = {"employee_id": "EMP001", "week_start": "2026-09-28"}
    notifications.insert_one(document)

    with pytest.raises(DuplicateKeyError):
        notifications.insert_one(document)
