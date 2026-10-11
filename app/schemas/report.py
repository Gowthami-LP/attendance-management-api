from pydantic import BaseModel


class AttendanceReportRow(BaseModel):
    employee_id: str
    employee_name: str
    department: str
    is_active: bool

    date: str
    entry_time: str | None = None
    exit_time: str | None = None
    working_hours: float | None = None
    attendance_status: str


class AttendanceReportSummary(BaseModel):
    total_records: int
    present: int
    incomplete: int
    not_attended: int
    not_recorded_yet: int


class AttendanceReportResponse(BaseModel):
    period: str
    start_date: str
    end_date: str
    summary: AttendanceReportSummary
    records: list[AttendanceReportRow]
