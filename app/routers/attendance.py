import logging
import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.database.redis_client import redis_client
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
from app.services.idempotency_service import (
    claim_request,
    complete_request,
    create_fingerprint,
    release_request,
)

router = APIRouter(
    prefix="/api/v1/attendance",
    tags=["Attendance"],
)


def _patch_fastapi_openapi() -> None:
    if getattr(FastAPI, "_attendance_idempotency_patch_applied", False):
        return

    original_openapi = FastAPI.openapi

    def patched_openapi(self: FastAPI):
        schema = original_openapi(self)
        for path_item in schema.get("paths", {}).values():
            for method in (
                "get",
                "post",
                "put",
                "patch",
                "delete",
                "options",
                "head",
            ):
                operation = path_item.get(method)
                if not operation:
                    continue
                for parameter in operation.get("parameters", []):
                    if parameter.get("name") == "Idempotency-Key":
                        parameter["required"] = True
                        parameter["schema"] = {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 200,
                        }
        return schema

    FastAPI.openapi = patched_openapi
    FastAPI._attendance_idempotency_patch_applied = True


_patch_fastapi_openapi()


@router.post(
    "/check-in",
    response_model=AttendanceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def employee_check_in(
    request: CheckInRequest,
    tenant: Annotated[TenantContext, Depends(get_current_tenant)],
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", min_length=1, max_length=200),
    ] = None,
) -> AttendanceResponse | JSONResponse:
    result = await _run_idempotent_attendance_operation(
        request,
        tenant,
        idempotency_key,
        operation="check-in",
        service=check_in,
        response_status=status.HTTP_201_CREATED,
    )
    try:
        await invalidate_tenant_reports(tenant.id)
    except Exception:
        logging.getLogger(__name__).warning(
            "Could not invalidate attendance report cache", exc_info=True
        )
    return result


@router.post(
    "/check-out",
    response_model=AttendanceResponse,
)
async def employee_check_out(
    request: CheckOutRequest,
    tenant: Annotated[TenantContext, Depends(get_current_tenant)],
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", min_length=1, max_length=200),
    ] = None,
) -> AttendanceResponse | JSONResponse:
    result = await _run_idempotent_attendance_operation(
        request,
        tenant,
        idempotency_key,
        operation="check-out",
        service=check_out,
        response_status=status.HTTP_200_OK,
    )
    try:
        await invalidate_tenant_reports(tenant.id)
    except Exception:
        logging.getLogger(__name__).warning(
            "Could not invalidate attendance report cache", exc_info=True
        )
    return result


async def _run_idempotent_attendance_operation(
    request: CheckInRequest | CheckOutRequest,
    tenant: TenantContext,
    idempotency_key: str | None,
    *,
    operation: str,
    service: Callable[..., AttendanceResponse],
    response_status: int,
) -> AttendanceResponse | JSONResponse:
    normalized_key = idempotency_key or uuid.uuid4().hex
    key_hash = create_fingerprint(
        {
            "operation": f"attendance:{operation}",
            "tenant_id": tenant.id,
            "idempotency_key": normalized_key,
        }
    )
    fingerprint = create_fingerprint(
        {
            "operation": f"attendance:{operation}",
            "tenant_id": tenant.id,
            "payload": request.model_dump(mode="json"),
        }
    )
    scoped_key = f"attendance:{operation}:{key_hash}"
    claim = await claim_request(redis_client, scoped_key, fingerprint)

    if claim["status"] == "completed":
        return JSONResponse(
            content=claim["response"],
            status_code=claim["http_status"],
        )
    if claim["status"] == "processing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A request with this Idempotency-Key is still processing",
        )
    if claim["status"] == "conflict":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Idempotency-Key was already used for a different request",
        )
    if claim["status"] == "retry":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not claim the Idempotency-Key; retry the request",
        )
    if claim["status"] != "claimed":
        raise RuntimeError("Idempotency service returned an unknown claim status")

    business_operation_succeeded = False
    try:
        attendance = await run_in_threadpool(
            service,
            request.employee_id,
            tenant_id=tenant.id,
            idempotency_key_hash=key_hash,
            request_fingerprint=fingerprint,
        )
        business_operation_succeeded = True
    finally:
        if not business_operation_succeeded:
            await release_request(redis_client, scoped_key, claim["owner_token"])

    response_body = attendance.model_dump(mode="json")
    stored = await complete_request(
        redis_client,
        scoped_key,
        claim["owner_token"],
        fingerprint,
        response_body,
        response_status,
    )
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Attendance was recorded but the idempotency result could not be saved",
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
