from unittest.mock import MagicMock

from app.workers import notification_worker


def test_process_pending_notifications(monkeypatch, fake_collection):
    notifications = fake_collection(
        [
            {
                "notification_id": "notif-1",
                "status": "pending",
                "created_at": "2026-10-15T09:00:00+05:30",
            },
            {
                "notification_id": "notif-2",
                "status": "pending",
                "created_at": "2026-10-15T09:05:00+05:30",
            },
            {
                "notification_id": "notif-3",
                "status": "sent",
                "created_at": "2026-10-15T08:00:00+05:30",
            },
        ]
    )
    monkeypatch.setattr(notification_worker, "notifications_collection", notifications)

    deliver_mock = MagicMock(
        side_effect=[
            {"notification_id": "notif-1", "status": "sent"},
            {"notification_id": "notif-2", "status": "failed"},
        ]
    )
    monkeypatch.setattr(notification_worker, "deliver_notification", deliver_mock)

    stats = notification_worker.process_pending_notifications(batch_size=10)

    assert stats == {"processed": 2, "sent": 1, "failed": 1}
    assert deliver_mock.call_count == 2


def test_retry_eligible_failed_notifications(monkeypatch, fake_collection):
    notifications = fake_collection(
        [
            {
                "notification_id": "notif-failed-1",
                "status": "failed",
                "attempts": 1,
                "created_at": "2026-10-15T09:00:00+05:30",
            },
            {
                "notification_id": "notif-exhausted",
                "status": "failed",
                "attempts": 3,
                "created_at": "2026-10-15T08:00:00+05:30",
            },
        ]
    )
    monkeypatch.setattr(notification_worker, "notifications_collection", notifications)

    deliver_mock = MagicMock(
        return_value={"notification_id": "notif-failed-1", "status": "sent"}
    )
    monkeypatch.setattr(notification_worker, "deliver_notification", deliver_mock)

    stats = notification_worker.retry_eligible_failed_notifications(
        max_attempts=3, batch_size=10
    )

    assert stats == {"retried": 1, "sent": 1, "failed": 0}
    deliver_mock.assert_called_once_with("notif-failed-1")


def test_run_worker_cycle(monkeypatch):
    monkeypatch.setattr(
        notification_worker,
        "process_pending_notifications",
        lambda batch_size, tenant_id=None: {
            "processed": 2,
            "sent": 2,
            "failed": 0,
        },
    )
    monkeypatch.setattr(
        notification_worker,
        "retry_eligible_failed_notifications",
        lambda max_attempts, batch_size, tenant_id=None: {
            "retried": 1,
            "sent": 1,
            "failed": 0,
        },
    )

    cycle_stats = notification_worker.run_worker_cycle()

    assert cycle_stats == {
        "pending": {"processed": 2, "sent": 2, "failed": 0},
        "retried": {"retried": 1, "sent": 1, "failed": 0},
    }
