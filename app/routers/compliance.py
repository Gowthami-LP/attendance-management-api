from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.routers.auth import get_current_admin
from app.schemas.compliance import WeeklyComplianceResponse
from app.services.compliance_service import evaluate_weekly_compliance

router = APIRouter(
    prefix="/api/v1/compliance",
    tags=["Attendance Compliance"],
    dependencies=[Depends(get_current_admin)],
)


@router.get(
    "/weekly",
    response_model=WeeklyComplianceResponse,
)
def get_weekly_compliance(
    week_start: Annotated[date | None, Query()] = None,
) -> WeeklyComplianceResponse:
    return evaluate_weekly_compliance(week_start)
