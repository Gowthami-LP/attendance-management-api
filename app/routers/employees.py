from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status

from app.routers.auth import get_current_admin
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeResponse,
    EmployeeStatus,
    EmployeeUpdate,
)
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
    dependencies=[Depends(get_current_admin)],
)
def create_employee_endpoint(employee: EmployeeCreate) -> EmployeeResponse:
    return create_employee(employee)


@router.get("", response_model=list[EmployeeResponse], dependencies=[Depends(get_current_admin)])
def list_employees(
    department: str | None = None,
    employee_status: Annotated[
        EmployeeStatus | None,
        Query(alias="status"),
    ] = None,
) -> list[EmployeeResponse]:
    is_active = None if employee_status is None else employee_status == "active"
    return get_employees(department=department, is_active=is_active)


# Retrieve one employee by employee ID.
@router.get("/{employee_id}", response_model=EmployeeResponse, dependencies=[Depends(get_current_admin)])
def read_employee(employee_id: str) -> EmployeeResponse:
    return get_employee_by_id(employee_id)


# Update only the supplied employee fields.
@router.patch("/{employee_id}", response_model=EmployeeResponse, dependencies=[Depends(get_current_admin)])
def edit_employee(
    employee_id: str,
    employee: EmployeeUpdate,
) -> EmployeeResponse:
    return update_employee(employee_id, employee)


# Deactivate an employee while preserving their history.
@router.patch("/{employee_id}/deactivate", response_model=EmployeeResponse, dependencies=[Depends(get_current_admin)])
def disable_employee(employee_id: str) -> EmployeeResponse:
    return deactivate_employee(employee_id)
