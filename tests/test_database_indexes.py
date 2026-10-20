from unittest.mock import MagicMock

from app.database import mongodb


def test_employee_indexes_replace_legacy_global_uniqueness(monkeypatch):
    employees = MagicMock()
    employees.index_information.return_value = {
        "_id_": {},
        "employee_id_1": {},
        "email_1": {},
    }
    monkeypatch.setattr(mongodb, "employees_collection", employees)

    mongodb.create_database_indexes()

    assert [call.args[0] for call in employees.drop_index.call_args_list] == [
        "employee_id_1",
        "email_1",
    ]
    employees.create_index.assert_any_call(
        [("tenant_id", 1), ("employee_id", 1)],
        unique=True,
    )
    employees.create_index.assert_any_call(
        [("tenant_id", 1), ("email", 1)],
        unique=True,
    )


def test_attendance_indexes_replace_legacy_global_uniqueness(monkeypatch):
    attendance = MagicMock()
    attendance.index_information.return_value = {
        "_id_": {},
        "employee_id_1_date_1": {},
    }
    monkeypatch.setattr(mongodb, "attendance_collection", attendance)

    mongodb.create_attendance_indexes()

    attendance.drop_index.assert_called_once_with("employee_id_1_date_1")
    attendance.create_index.assert_any_call(
        [("tenant_id", 1), ("employee_id", 1), ("date", 1)],
        unique=True,
    )
    attendance.create_index.assert_any_call(
        [("tenant_id", 1), ("check_in_idempotency_key_hash", 1)],
        unique=True,
        partialFilterExpression={"check_in_idempotency_key_hash": {"$type": "string"}},
    )
    attendance.create_index.assert_any_call(
        [("tenant_id", 1), ("check_out_idempotency_key_hash", 1)],
        unique=True,
        partialFilterExpression={"check_out_idempotency_key_hash": {"$type": "string"}},
    )


def test_notification_indexes_replace_legacy_global_uniqueness(monkeypatch):
    notifications = MagicMock()
    notifications.index_information.return_value = {
        "_id_": {},
        "employee_id_1_week_start_1": {},
    }
    monkeypatch.setattr(mongodb, "notifications_collection", notifications)

    mongodb.create_notification_indexes()

    notifications.drop_index.assert_called_once_with("employee_id_1_week_start_1")
    notifications.create_index.assert_any_call(
        [("tenant_id", 1), ("employee_id", 1), ("week_start", 1)],
        unique=True,
    )
