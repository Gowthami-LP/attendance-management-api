from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from app.services import attendance_service


@pytest.fixture
def attendance_db(monkeypatch, fake_collection, fixed_datetime):
    employee = fake_collection([{
        "employee_id": "EMP001",
        "name": "Taylor Example",
        "is_active": True,
    }])
    records = fake_collection(unique_fields=("employee_id", "date"))
    monkeypatch.setattr(attendance_service, "employees_collection", employee)
    monkeypatch.setattr(attendance_service, "attendance_collection", records)
    monkeypatch.setattr(attendance_service, "datetime", fixed_datetime)
    return employee, records


def test_check_in_records_employee_and_prevents_duplicate(attendance_db):
    _, records = attendance_db

    attendance = attendance_service.check_in("EMP001")
    assert attendance.employee_id == "EMP001"
    assert attendance.date == "2026-10-11"
    assert attendance.exit_time is None
    assert attendance.duration_minutes is None

    with pytest.raises(HTTPException) as error:
        attendance_service.check_in("EMP001")

    assert error.value.status_code == 409
    assert len(records.documents) == 1


def test_check_out_calculates_working_minutes(attendance_db, fixed_datetime):
    _, records = attendance_db
    entry = fixed_datetime.fixed_now - timedelta(hours=7, minutes=30)
    records.insert_one({
        "employee_id": "EMP001",
        "date": "2026-10-11",
        "entry_time": entry.isoformat(),
        "exit_time": None,
        "duration_minutes": None,
    })

    attendance = attendance_service.check_out("EMP001")

    assert attendance.duration_minutes == 450
    assert datetime.fromisoformat(attendance.exit_time).utcoffset().total_seconds() == 19800
    assert records.documents[0]["duration_minutes"] == 450


def test_check_in_rejects_inactive_employee(attendance_db):
    employee, _ = attendance_db
    employee.documents[0]["is_active"] = False

    with pytest.raises(HTTPException) as error:
        attendance_service.check_in("EMP001")

    assert error.value.status_code == 409


def test_check_out_requires_check_in(attendance_db):
    with pytest.raises(HTTPException) as error:
        attendance_service.check_out("EMP001")

    assert error.value.status_code == 404
