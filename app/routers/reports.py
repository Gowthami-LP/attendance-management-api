import logging
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from starlette.concurrency import run_in_threadpool

from app.schemas.report import AttendanceReportResponse
from app.security.tenant_context import TenantContext, get_current_tenant
from app.services.attendance_service import OFFICE_TIMEZONE
from app.services.cache_service import get_cached_data, set_cached_data
from app.services.report_service import generate_attendance_report

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/reports",
    tags=["Attendance Reports"],
)


@router.get(
    "/attendance",
    response_model=AttendanceReportResponse,
)
async def get_attendance_report(
    tenant: Annotated[TenantContext, Depends(get_current_tenant)],
    period: Annotated[
        Literal["daily", "weekly", "monthly", "yearly", "custom"],
        Query(),
    ] = "daily",
    reference_date: Annotated[date | None, Query()] = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
) -> AttendanceReportResponse:
    effective_reference_date = reference_date or datetime.now(OFFICE_TIMEZONE).date()
    cache_key = (
        f"attendance:{tenant.id}:report:{period}:"
        f"{effective_reference_date.isoformat()}:{start_date}:{end_date}"
    )
    try:
        cached = await get_cached_data(cache_key)
        if cached is not None:
            return AttendanceReportResponse.model_validate(cached)
    except Exception:
        logger.warning("Could not read attendance report cache", exc_info=True)

    report = await run_in_threadpool(
        generate_attendance_report,
        period=period,
        reference_date=reference_date,
        start_date=start_date,
        end_date=end_date,
        tenant_id=tenant.id,
    )
    try:
        await set_cached_data(cache_key, report.model_dump(mode="json"), ttl_seconds=60)
    except Exception:
        logger.warning("Could not write attendance report cache", exc_info=True)
    return report
