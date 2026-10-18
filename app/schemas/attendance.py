from pydantic import BaseModel, ConfigDict, Field


class CheckInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: str = Field(min_length=3, max_length=20)


class CheckOutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: str = Field(min_length=3, max_length=20)


class AttendanceResponse(BaseModel):
    employee_id: str
    date: str
    entry_time: str
    exit_time: str | None = None
    duration_minutes: int | None = None
    tenant_id: str | None = None
