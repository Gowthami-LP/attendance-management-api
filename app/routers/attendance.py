from fastapi import APIRouter, status

from app.schemas.attendance import (
    AttendanceResponse,
    CheckInRequest,
    CheckOutRequest,
)
from app.services.attendance_service import (
    check_in,
    check_out,
    get_employee_attendance,
)

router = APIRouter(
    prefix="/api/v1/attendance",
    tags=["Attendance"],
)


@router.post(
    "/check-in",
    response_model=AttendanceResponse,
    status_code=status.HTTP_201_CREATED,
)
def employee_check_in(request: CheckInRequest) -> AttendanceResponse:
    return check_in(request.employee_id)


@router.post(
    "/check-out",
    response_model=AttendanceResponse,
)
def employee_check_out(request: CheckOutRequest) -> AttendanceResponse:
    return check_out(request.employee_id)


@router.get(
    "/{employee_id}",
    response_model=list[AttendanceResponse],
)
def read_employee_attendance(
    employee_id: str,
) -> list[AttendanceResponse]:
    return get_employee_attendance(employee_id)
