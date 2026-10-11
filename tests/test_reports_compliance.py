from datetime import date

import pytest
from fastapi import HTTPException

from app.services import compliance_service, report_service


@pytest.fixture
def report_db(monkeypatch, fake_collection, fixed_datetime):
    employees = fake_collection(
        [
            {
                "employee_id": "EMP001",
                "name": "Taylor Example",
                "department": "Engineering",
                "is_active": True,
            }
        ]
    )
    attendance = fake_collection(
        [
            {
                "employee_id": "EMP001",
                "date": "2026-10-06",
                "entry_time": "2026-10-06T09:00:00+05:30",
                "exit_time": "2026-10-06T15:00:00+05:30",
                "duration_minutes": 360,
            }
        ]
    )
    monkeypatch.setattr(report_service, "employees_collection", employees)
    monkeypatch.setattr(report_service, "attendance_collection", attendance)
    monkeypatch.setattr(compliance_service, "employees_collection", employees)
    monkeypatch.setattr(compliance_service, "attendance_collection", attendance)
    monkeypatch.setattr(report_service, "datetime", fixed_datetime)
    monkeypatch.setattr(compliance_service, "datetime", fixed_datetime)
    return employees, attendance


@pytest.mark.parametrize(
    ("period", "expected_start", "expected_end"),
    [
        ("daily", date(2026, 10, 6), date(2026, 10, 6)),
        ("weekly", date(2026, 10, 5), date(2026, 10, 11)),
        ("monthly", date(2026, 10, 1), date(2026, 10, 31)),
        ("yearly", date(2026, 1, 1), date(2026, 12, 31)),
        ("custom", date(2026, 10, 1), date(2026, 10, 7)),
    ],
)
def test_report_period_date_ranges(period, expected_start, expected_end):
    result = report_service.calculate_report_dates(
        period,
        date(2026, 10, 6),
        date(2026, 10, 1) if period == "custom" else None,
        date(2026, 10, 7) if period == "custom" else None,
    )
    assert result == (expected_start, expected_end)


def test_custom_report_requires_valid_dates():
    with pytest.raises(HTTPException) as missing_dates:
        report_service.calculate_report_dates("custom", None, None, None)
    assert missing_dates.value.status_code == 400

    with pytest.raises(HTTPException) as reversed_dates:
        report_service.calculate_report_dates(
            "custom", None, date(2026, 10, 2), date(2026, 10, 1)
        )
    assert reversed_dates.value.status_code == 400


def test_report_contains_working_hour_calculation(report_db):
    report = report_service.generate_attendance_report(
        "daily",
        reference_date=date(2026, 10, 6),
    )

    assert report.summary.present == 1
    assert report.summary.total_records == 1
    assert report.records[0].working_hours == 6
    assert report.records[0].attendance_status == "Present"


def test_compliance_requires_three_days_and_fifteen_hours(
    monkeypatch,
    fake_collection,
    fixed_datetime,
):
    employees = fake_collection(
        [
            {
                "employee_id": "EMP001",
                "name": "Taylor Example",
                "department": "Engineering",
                "is_active": True,
            }
        ]
    )
    attendance = fake_collection(
        [
            {
                "employee_id": "EMP001",
                "date": day,
                "entry_time": f"{day}T09:00:00+05:30",
                "exit_time": f"{day}T14:00:00+05:30",
                "duration_minutes": 300,
            }
            for day in ("2026-09-28", "2026-09-29", "2026-09-30")
        ]
    )
    monkeypatch.setattr(compliance_service, "employees_collection", employees)
    monkeypatch.setattr(compliance_service, "attendance_collection", attendance)
    monkeypatch.setattr(compliance_service, "datetime", fixed_datetime)

    result = compliance_service.evaluate_weekly_compliance(date(2026, 9, 28))

    assert result.evaluation_status == "completed"
    assert result.compliant_employees == 1
    assert result.employees[0].qualifying_days == 3
    assert result.employees[0].total_hours == 15
    assert result.employees[0].compliance_status == "compliant"

    attendance.documents.pop()
    result = compliance_service.evaluate_weekly_compliance(date(2026, 9, 28))
    assert result.violating_employees == 1
    assert result.employees[0].compliance_status == "violation"


def test_compliance_marks_incomplete_sessions_for_review(
    monkeypatch,
    fake_collection,
    fixed_datetime,
):
    monkeypatch.setattr(
        compliance_service,
        "employees_collection",
        fake_collection(
            [
                {
                    "employee_id": "EMP001",
                    "name": "Taylor Example",
                    "department": "Engineering",
                    "is_active": True,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        compliance_service,
        "attendance_collection",
        fake_collection(
            [
                {
                    "employee_id": "EMP001",
                    "date": "2026-09-28",
                    "entry_time": "2026-09-28T09:00:00+05:30",
                    "exit_time": None,
                    "duration_minutes": None,
                }
            ]
        ),
    )
    monkeypatch.setattr(compliance_service, "datetime", fixed_datetime)

    result = compliance_service.evaluate_weekly_compliance(date(2026, 9, 28))

    assert result.employees_needing_review == 1
    assert result.employees[0].compliance_status == "needs_review"
