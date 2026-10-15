from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.routers.auth import get_current_admin
from app.schemas.report import AttendanceReportResponse
from app.services.report_service import generate_attendance_report

router = APIRouter(
    prefix="/api/v1/reports",
    tags=["Attendance Reports"],
    dependencies=[Depends(get_current_admin)],
)


@router.get(
    "/attendance",
    response_model=AttendanceReportResponse,
)
def get_attendance_report(
    period: Annotated[
        Literal["daily", "weekly", "monthly", "yearly", "custom"],
        Query(),
    ] = "daily",
    reference_date: Annotated[date | None, Query()] = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
) -> AttendanceReportResponse:
    return generate_attendance_report(
        period=period,
        reference_date=reference_date,
        start_date=start_date,
        end_date=end_date,
    )
