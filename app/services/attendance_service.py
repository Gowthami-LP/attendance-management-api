import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.database.mongodb import attendance_collection, employees_collection
from app.schemas.attendance import AttendanceResponse

OFFICE_TIMEZONE = ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Kolkata"))


def _tenant_filter(tenant_id: str) -> dict[str, Any] | str:
    if tenant_id == "default":
        return {"$in": ["default", None]}
    return tenant_id


def _get_idempotent_attendance(
    tenant_id: str,
    idempotency_key_hash: str,
    request_fingerprint: str,
    key_field: str,
    fingerprint_field: str,
) -> AttendanceResponse | None:
    existing = attendance_collection.find_one(
        {
            "tenant_id": tenant_id,
            key_field: idempotency_key_hash,
        },
        {"_id": 0},
    )
    if existing is None:
        return None
    if existing.get(fingerprint_field) != request_fingerprint:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Idempotency-Key was already used for a different request",
        )
    return AttendanceResponse(**existing)


def check_in(
    employee_id: str,
    tenant_id: str = "default",
    idempotency_key_hash: str | None = None,
    request_fingerprint: str | None = None,
) -> AttendanceResponse:
    if (idempotency_key_hash is None) != (request_fingerprint is None):
        raise ValueError(
            "Idempotency key hash and request fingerprint must be provided together"
        )
    if idempotency_key_hash is not None and request_fingerprint is not None:
        recovered = _get_idempotent_attendance(
            tenant_id,
            idempotency_key_hash,
            request_fingerprint,
            "check_in_idempotency_key_hash",
            "check_in_request_fingerprint",
        )
        if recovered is not None:
            return recovered

    employee = employees_collection.find_one(
        {
            "tenant_id": _tenant_filter(tenant_id),
            "employee_id": employee_id,
        },
        {"_id": 0},
    )

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    if not employee.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Inactive employees cannot check in",
        )

    current_time = datetime.now(OFFICE_TIMEZONE)
    local_date = current_time.date().isoformat()
    attendance_document = {
        "tenant_id": tenant_id,
        "employee_id": employee_id,
        "date": local_date,
        "entry_time": current_time.isoformat(),
        "exit_time": None,
        "duration_minutes": None,
    }
    if idempotency_key_hash is not None and request_fingerprint is not None:
        attendance_document["check_in_idempotency_key_hash"] = idempotency_key_hash
        attendance_document["check_in_request_fingerprint"] = request_fingerprint

    try:
        attendance_collection.insert_one(attendance_document)
    except DuplicateKeyError as error:
        if idempotency_key_hash is not None and request_fingerprint is not None:
            recovered = _get_idempotent_attendance(
                tenant_id,
                idempotency_key_hash,
                request_fingerprint,
                "check_in_idempotency_key_hash",
                "check_in_request_fingerprint",
            )
            if recovered is not None:
                return recovered
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attendance already exists for this employee today",
        ) from error

    return AttendanceResponse(**attendance_document)


def check_out(
    employee_id: str,
    tenant_id: str = "default",
    idempotency_key_hash: str | None = None,
    request_fingerprint: str | None = None,
) -> AttendanceResponse:
    if (idempotency_key_hash is None) != (request_fingerprint is None):
        raise ValueError(
            "Idempotency key hash and request fingerprint must be provided together"
        )
    if idempotency_key_hash is not None and request_fingerprint is not None:
        recovered = _get_idempotent_attendance(
            tenant_id,
            idempotency_key_hash,
            request_fingerprint,
            "check_out_idempotency_key_hash",
            "check_out_request_fingerprint",
        )
        if recovered is not None:
            return recovered

    current_time = datetime.now(OFFICE_TIMEZONE)
    local_date = current_time.date().isoformat()
    attendance_filter: dict[str, Any] = {
        "tenant_id": _tenant_filter(tenant_id),
        "employee_id": employee_id,
        "date": local_date,
    }

    attendance = attendance_collection.find_one(attendance_filter)
    if attendance is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No check-in record found for today",
        )

    if attendance.get("exit_time") is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Employee has already checked out today",
        )

    entry_time = datetime.fromisoformat(attendance["entry_time"])
    duration_seconds = (current_time - entry_time).total_seconds()
    duration_minutes = int(duration_seconds // 60)
    update_fields: dict[str, Any] = {
        "exit_time": current_time.isoformat(),
        "duration_minutes": duration_minutes,
    }
    if idempotency_key_hash is not None and request_fingerprint is not None:
        update_fields["check_out_idempotency_key_hash"] = idempotency_key_hash
        update_fields["check_out_request_fingerprint"] = request_fingerprint

    updated_attendance = attendance_collection.find_one_and_update(
        {**attendance_filter, "exit_time": None},
        {"$set": update_fields},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )

    if updated_attendance is None:
        if idempotency_key_hash is not None and request_fingerprint is not None:
            recovered = _get_idempotent_attendance(
                tenant_id,
                idempotency_key_hash,
                request_fingerprint,
                "check_out_idempotency_key_hash",
                "check_out_request_fingerprint",
            )
            if recovered is not None:
                return recovered
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Employee has already checked out today",
        )

    return AttendanceResponse(**updated_attendance)


def get_employee_attendance(
    employee_id: str,
    tenant_id: str = "default",
) -> list[AttendanceResponse]:
    employee = employees_collection.find_one(
        {
            "tenant_id": _tenant_filter(tenant_id),
            "employee_id": employee_id,
        },
        {"_id": 0, "employee_id": 1},
    )

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    records = attendance_collection.find(
        {
            "tenant_id": _tenant_filter(tenant_id),
            "employee_id": employee_id,
        },
        {"_id": 0},
    ).sort("date", -1)

    return [AttendanceResponse(**record) for record in records]
