import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from starlette.concurrency import run_in_threadpool

from app.schemas.attendance import (
    AttendanceResponse,
    CheckInRequest,
    CheckOutRequest,
)
from app.security.tenant_context import TenantContext, get_current_tenant
from app.services.attendance_service import (
    check_in,
    check_out,
    get_employee_attendance,
)
from app.services.cache_service import invalidate_tenant_reports

router = APIRouter(
    prefix="/api/v1/attendance",
    tags=["Attendance"],
)


@router.post(
    "/check-in",
    response_model=AttendanceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def employee_check_in(
    request: CheckInRequest,
    tenant: Annotated[TenantContext, Depends(get_current_tenant)],
) -> AttendanceResponse:
    attendance = await run_in_threadpool(
        check_in, request.employee_id, tenant_id=tenant.id
    )
    try:
        await invalidate_tenant_reports(tenant.id)
    except Exception:
        logging.getLogger(__name__).warning(
            "Could not invalidate attendance report cache", exc_info=True
        )
    return attendance


@router.post(
    "/check-out",
    response_model=AttendanceResponse,
)
async def employee_check_out(
    request: CheckOutRequest,
    tenant: Annotated[TenantContext, Depends(get_current_tenant)],
) -> AttendanceResponse:
    attendance = await run_in_threadpool(
        check_out, request.employee_id, tenant_id=tenant.id
    )
    try:
        await invalidate_tenant_reports(tenant.id)
    except Exception:
        logging.getLogger(__name__).warning(
            "Could not invalidate attendance report cache", exc_info=True
        )
    return attendance


@router.get(
    "/{employee_id}",
    response_model=list[AttendanceResponse],
)
async def read_employee_attendance(
    employee_id: str,
    tenant: Annotated[TenantContext, Depends(get_current_tenant)],
) -> list[AttendanceResponse]:
    return await run_in_threadpool(
        get_employee_attendance, employee_id, tenant_id=tenant.id
    )
