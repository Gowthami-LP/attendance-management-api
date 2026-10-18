from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.schemas.compliance import WeeklyComplianceResponse
from app.security.tenant_context import TenantContext, get_current_tenant
from app.services.compliance_service import evaluate_weekly_compliance

router = APIRouter(
    prefix="/api/v1/compliance",
    tags=["Attendance Compliance"],
)


@router.get(
    "/weekly",
    response_model=WeeklyComplianceResponse,
)
def get_weekly_compliance(
    tenant: Annotated[TenantContext, Depends(get_current_tenant)],
    week_start: Annotated[date | None, Query()] = None,
) -> WeeklyComplianceResponse:
    return evaluate_weekly_compliance(
        week_start=week_start,
        tenant_id=tenant.id,
        policy=tenant.policy,
    )
