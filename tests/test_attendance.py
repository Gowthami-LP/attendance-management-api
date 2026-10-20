from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI, HTTPException

from app.routers.attendance import router as attendance_router
from app.services import attendance_service


@pytest.fixture
def attendance_db(monkeypatch, fake_collection, fixed_datetime):
    employee = fake_collection(
        [
            {
                "employee_id": "EMP001",
                "name": "Taylor Example",
                "is_active": True,
            }
        ]
    )
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
    records.insert_one(
        {
            "employee_id": "EMP001",
            "date": "2026-10-11",
            "entry_time": entry.isoformat(),
            "exit_time": None,
            "duration_minutes": None,
        }
    )

    attendance = attendance_service.check_out("EMP001")

    assert attendance.duration_minutes == 450
    assert (
        datetime.fromisoformat(attendance.exit_time).utcoffset().total_seconds()
        == 19800
    )
    assert records.documents[0]["duration_minutes"] == 450


def test_check_in_rejects_inactive_employee(attendance_db):
    employee, _ = attendance_db
    employee.documents[0]["is_active"] = False

    with pytest.raises(HTTPException) as error:
        attendance_service.check_in("EMP001")

    assert error.value.status_code == 409


def test_check_in_recovers_same_idempotent_request(attendance_db):
    _, records = attendance_db

    first = attendance_service.check_in(
        "EMP001",
        idempotency_key_hash="key-hash",
        request_fingerprint="request-fingerprint",
    )
    recovered = attendance_service.check_in(
        "EMP001",
        idempotency_key_hash="key-hash",
        request_fingerprint="request-fingerprint",
    )

    assert recovered == first
    assert len(records.documents) == 1


def test_check_in_rejects_reused_key_with_different_payload(attendance_db):
    attendance_service.check_in(
        "EMP001",
        idempotency_key_hash="key-hash",
        request_fingerprint="original-fingerprint",
    )

    with pytest.raises(HTTPException) as error:
        attendance_service.check_in(
            "EMP001",
            idempotency_key_hash="key-hash",
            request_fingerprint="different-fingerprint",
        )

    assert error.value.status_code == 422


def test_check_out_recovers_same_idempotent_request(attendance_db, fixed_datetime):
    _, records = attendance_db
    attendance_service.check_in("EMP001")

    first = attendance_service.check_out(
        "EMP001",
        idempotency_key_hash="checkout-key-hash",
        request_fingerprint="checkout-fingerprint",
    )
    fixed_datetime.fixed_now += timedelta(minutes=15)
    recovered = attendance_service.check_out(
        "EMP001",
        idempotency_key_hash="checkout-key-hash",
        request_fingerprint="checkout-fingerprint",
    )

    assert recovered == first
    assert recovered.exit_time == first.exit_time
    assert len(records.documents) == 1


def test_check_out_with_new_key_does_not_overwrite_existing_checkout(
    attendance_db,
):
    _, records = attendance_db
    attendance_service.check_in("EMP001")
    first = attendance_service.check_out("EMP001")
    fixed_exit_time = records.documents[0]["exit_time"]

    with pytest.raises(HTTPException) as error:
        attendance_service.check_out("EMP001")

    assert error.value.status_code == 409
    assert records.documents[0]["exit_time"] == fixed_exit_time
    assert first.exit_time == fixed_exit_time


def test_check_out_requires_check_in(attendance_db):
    with pytest.raises(HTTPException) as error:
        attendance_service.check_out("EMP001")

    assert error.value.status_code == 404


def test_attendance_write_routes_expose_idempotency_header():
    app = FastAPI()
    app.include_router(attendance_router)
    schema = app.openapi()

    for path in (
        "/api/v1/attendance/check-in",
        "/api/v1/attendance/check-out",
    ):
        parameters = schema["paths"][path]["post"]["parameters"]
        header = next(
            parameter
            for parameter in parameters
            if parameter["name"] == "Idempotency-Key"
        )
        assert header["in"] == "header"
        assert header["required"] is True
        assert header["schema"]["minLength"] == 1
        assert header["schema"]["maxLength"] == 200
