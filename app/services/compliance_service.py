from datetime import date, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status

from app.database.mongodb import attendance_collection, employees_collection
from app.schemas.compliance import (
    EmployeeCompliance,
    WeeklyComplianceResponse,
)
from app.services.attendance_service import OFFICE_TIMEZONE

MIN_QUALIFYING_DAYS = 3
MIN_HOURS_PER_DAY = 5
MIN_WEEKLY_HOURS = 15


def evaluate_weekly_compliance(
    week_start: date | None = None,
) -> WeeklyComplianceResponse:
    today = datetime.now(OFFICE_TIMEZONE).date()

    if week_start is None:
        week_start = today - timedelta(days=today.weekday())

    if week_start.weekday() != 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="week_start must be a Monday",
        )

    week_end = week_start + timedelta(days=6)

    if week_start > today:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot evaluate a future week",
        )

    week_is_complete = today > week_end
    evaluation_status = "completed" if week_is_complete else "in_progress"

    employees = list(
        employees_collection.find(
            {"is_active": True},
            {
                "_id": 0,
                "employee_id": 1,
                "name": 1,
                "department": 1,
            },
        ).sort("employee_id", 1)
    )

    attendance_records = list(
        attendance_collection.find(
            {
                "date": {
                    "$gte": week_start.isoformat(),
                    "$lte": min(week_end, today).isoformat(),
                }
            },
            {"_id": 0},
        )
    )

    records_by_employee: dict[str, list[dict[str, Any]]] = {}
    for record in attendance_records:
        employee_id = record["employee_id"]
        records_by_employee.setdefault(employee_id, []).append(record)

    results: list[EmployeeCompliance] = []
    compliant_count = 0
    violating_count = 0
    in_progress_count = 0
    needs_review_count = 0

    for employee in employees:
        employee_id = employee["employee_id"]
        employee_records = records_by_employee.get(employee_id, [])

        qualifying_days = 0
        total_minutes = 0
        incomplete_sessions = 0

        for record in employee_records:
            entry_time = record.get("entry_time")
            exit_time = record.get("exit_time")
            duration_minutes = record.get("duration_minutes")

            if not entry_time or not exit_time:
                incomplete_sessions += 1
                continue

            if duration_minutes is None:
                entry_datetime = datetime.fromisoformat(entry_time)
                exit_datetime = datetime.fromisoformat(exit_time)
                duration_minutes = int(
                    (exit_datetime - entry_datetime).total_seconds() // 60
                )

            if duration_minutes < 0:
                incomplete_sessions += 1
                continue

            total_minutes += duration_minutes
            if duration_minutes >= MIN_HOURS_PER_DAY * 60:
                qualifying_days += 1

        total_hours = round(total_minutes / 60, 2)
        hours_shortfall = round(
            max(0, MIN_WEEKLY_HOURS - total_hours),
            2,
        )

        if not week_is_complete:
            compliance_status = "in_progress"
            reason = "The week has not ended. This result is provisional."
            in_progress_count += 1
        elif incomplete_sessions > 0:
            compliance_status = "needs_review"
            reason = (
                "Incomplete attendance sessions must be resolved "
                "before final compliance can be determined."
            )
            needs_review_count += 1
        elif (
            qualifying_days >= MIN_QUALIFYING_DAYS
            and total_minutes >= MIN_WEEKLY_HOURS * 60
        ):
            compliance_status = "compliant"
            reason = (
                "The employee met both the qualifying-day "
                "and weekly-hours requirements."
            )
            compliant_count += 1
        else:
            compliance_status = "violation"
            reasons = []

            if qualifying_days < MIN_QUALIFYING_DAYS:
                reasons.append(
                    f"Only {qualifying_days} qualifying days; "
                    f"{MIN_QUALIFYING_DAYS} required"
                )

            if total_minutes < MIN_WEEKLY_HOURS * 60:
                reasons.append(
                    f"Only {total_hours} hours; "
                    f"{MIN_WEEKLY_HOURS} required"
                )

            reason = "; ".join(reasons)
            violating_count += 1

        results.append(
            EmployeeCompliance(
                employee_id=employee_id,
                employee_name=employee["name"],
                department=employee.get("department", ""),
                qualifying_days=qualifying_days,
                total_hours=total_hours,
                hours_shortfall=hours_shortfall,
                incomplete_sessions=incomplete_sessions,
                compliance_status=compliance_status,
                reason=reason,
            )
        )

    return WeeklyComplianceResponse(
        week_start=week_start.isoformat(),
        week_end=week_end.isoformat(),
        evaluation_status=evaluation_status,
        total_employees=len(employees),
        compliant_employees=compliant_count,
        violating_employees=violating_count,
        employees_in_progress=in_progress_count,
        employees_needing_review=needs_review_count,
        employees=results,
    )
