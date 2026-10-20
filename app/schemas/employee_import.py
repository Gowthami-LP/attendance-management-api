from typing import Literal

from pydantic import BaseModel

ImportStatus = Literal[
    "queued",
    "processing",
    "retrying",
    "completed",
    "completed_with_errors",
    "failed",
]


class EmployeeImportAccepted(BaseModel):
    job_id: str
    status: ImportStatus
    message: str


class EmployeeImportStatusResponse(BaseModel):
    job_id: str
    status: ImportStatus
    total_rows: int | None = None
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    error: str | None = None
    created_at: str | None = None
    completed_at: str | None = None
