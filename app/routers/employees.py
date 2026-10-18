from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status

from app.schemas.employee import (
    EmployeeCreate,
    EmployeeResponse,
    EmployeeStatus,
    EmployeeUpdate,
)
from app.security.tenant_context import TenantContext, get_current_tenant
from app.services.employee_service import (
    create_employee,
    deactivate_employee,
    get_employee_by_id,
    get_employees,
    update_employee,
)

router = APIRouter(prefix="/employees", tags=["employees"])


@router.post(
    "",
    response_model=EmployeeResponse,
    status_code=http_status.HTTP_201_CREATED,
)
def create_employee_endpoint(
    employee: EmployeeCreate,
    tenant: Annotated[TenantContext, Depends(get_current_tenant)],
) -> EmployeeResponse:
    return create_employee(employee, tenant_id=tenant.id)


@router.get(
    "",
    response_model=list[EmployeeResponse],
)
def list_employees(
    tenant: Annotated[TenantContext, Depends(get_current_tenant)],
    department: str | None = None,
    employee_status: Annotated[
        EmployeeStatus | None,
        Query(alias="status"),
    ] = None,
) -> list[EmployeeResponse]:
    is_active = None if employee_status is None else employee_status == "active"
    return get_employees(
        department=department, is_active=is_active, tenant_id=tenant.id
    )


# Retrieve one employee by employee ID within the tenant.
@router.get(
    "/{employee_id}",
    response_model=EmployeeResponse,
)
def read_employee(
    employee_id: str,
    tenant: Annotated[TenantContext, Depends(get_current_tenant)],
) -> EmployeeResponse:
    return get_employee_by_id(employee_id, tenant_id=tenant.id)


# Update only the supplied employee fields within the tenant.
@router.patch(
    "/{employee_id}",
    response_model=EmployeeResponse,
)
def edit_employee(
    employee_id: str,
    employee: EmployeeUpdate,
    tenant: Annotated[TenantContext, Depends(get_current_tenant)],
) -> EmployeeResponse:
    return update_employee(employee_id, employee, tenant_id=tenant.id)


# Deactivate a tenant-owned employee while preserving their history.
@router.patch(
    "/{employee_id}/deactivate",
    response_model=EmployeeResponse,
)
def disable_employee(
    employee_id: str,
    tenant: Annotated[TenantContext, Depends(get_current_tenant)],
) -> EmployeeResponse:
    return deactivate_employee(employee_id, tenant_id=tenant.id)
