import calendar
from datetime import date, datetime, timedelta

from fastapi import HTTPException, status

from app.database.mongodb import attendance_collection, employees_collection
from app.schemas.report import (
    AttendanceReportResponse,
    AttendanceReportRow,
    AttendanceReportSummary,
)
from app.services.attendance_service import OFFICE_TIMEZONE


def calculate_report_dates(
    period: str,
    reference_date: date | None,
    start_date: date | None,
    end_date: date | None,
) -> tuple[date, date]:
    anchor = reference_date or datetime.now(OFFICE_TIMEZONE).date()

    if period == "daily":
        return anchor, anchor

    if period == "weekly":
        week_start = anchor - timedelta(days=anchor.weekday())
        return week_start, week_start + timedelta(days=6)

    if period == "monthly":
        month_start = anchor.replace(day=1)
        last_day = calendar.monthrange(anchor.year, anchor.month)[1]
        return month_start, anchor.replace(day=last_day)

    if period == "yearly":
        return date(anchor.year, 1, 1), date(anchor.year, 12, 31)

    if period == "custom":
        if start_date is None or end_date is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Custom reports require start_date and end_date",
            )

        if start_date > end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_date must be on or before end_date",
            )

        return start_date, end_date

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Unsupported report period",
    )


def generate_attendance_report(
    period: str,
    reference_date: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> AttendanceReportResponse:
    report_start, report_end = calculate_report_dates(
        period,
        reference_date,
        start_date,
        end_date,
    )

    today = datetime.now(OFFICE_TIMEZONE).date()
    effective_end = min(report_end, today)

    if report_start > today:
        effective_end = report_start - timedelta(days=1)

    employee_documents = list(
        employees_collection.find(
            {},
            {
                "_id": 0,
                "employee_id": 1,
                "name": 1,
                "department": 1,
                "is_active": 1,
            },
        ).sort("employee_id", 1)
    )

    if effective_end >= report_start:
        attendance_documents = list(
            attendance_collection.find(
                {
                    "date": {
                        "$gte": report_start.isoformat(),
                        "$lte": effective_end.isoformat(),
                    }
                },
                {"_id": 0},
            )
        )
    else:
        attendance_documents = []

    attendance_by_employee_date = {
        (record["employee_id"], record["date"]): record
        for record in attendance_documents
    }

    rows: list[AttendanceReportRow] = []
    present = 0
    incomplete = 0
    not_attended = 0
    not_recorded_yet = 0
    current_date = report_start

    while current_date <= effective_end:
        date_text = current_date.isoformat()

        for employee in employee_documents:
            employee_id = employee["employee_id"]
            attendance = attendance_by_employee_date.get(
                (employee_id, date_text)
            )

            entry_time = None
            exit_time = None
            working_hours = None

            if attendance is not None:
                entry_time = attendance.get("entry_time")
                exit_time = attendance.get("exit_time")

                if entry_time and not exit_time:
                    attendance_status = "Incomplete"
                    incomplete += 1
                elif entry_time and exit_time:
                    duration_minutes = attendance.get("duration_minutes")
                    if duration_minutes is None:
                        entry_datetime = datetime.fromisoformat(entry_time)
                        exit_datetime = datetime.fromisoformat(exit_time)
                        duration_minutes = int(
                            (exit_datetime - entry_datetime).total_seconds()
                            // 60
                        )

                    working_hours = round(duration_minutes / 60, 2)
                    attendance_status = "Present"
                    present += 1
                else:
                    attendance_status = "Incomplete"
                    incomplete += 1
            elif current_date == today:
                attendance_status = "Not recorded yet"
                not_recorded_yet += 1
            else:
                attendance_status = "Not attended office"
                not_attended += 1

            rows.append(
                AttendanceReportRow(
                    employee_id=employee_id,
                    employee_name=employee["name"],
                    department=employee.get("department", ""),
                    is_active=employee.get("is_active", True),
                    date=date_text,
                    entry_time=entry_time,
                    exit_time=exit_time,
                    working_hours=working_hours,
                    attendance_status=attendance_status,
                )
            )

        current_date += timedelta(days=1)

    return AttendanceReportResponse(
        period=period,
        start_date=report_start.isoformat(),
        end_date=report_end.isoformat(),
        summary=AttendanceReportSummary(
            total_records=len(rows),
            present=present,
            incomplete=incomplete,
            not_attended=not_attended,
            not_recorded_yet=not_recorded_yet,
        ),
        records=rows,
    )
