from typing import Literal

from pydantic import BaseModel


class EmployeeCompliance(BaseModel):
    employee_id: str
    employee_name: str
    department: str
    qualifying_days: int
    total_hours: float
    hours_shortfall: float
    incomplete_sessions: int
    compliance_status: Literal[
        "compliant",
        "violation",
        "in_progress",
        "needs_review",
    ]
    reason: str


class WeeklyComplianceResponse(BaseModel):
    week_start: str
    week_end: str
    evaluation_status: Literal["completed", "in_progress"]
    total_employees: int
    compliant_employees: int
    violating_employees: int
    employees_in_progress: int
    employees_needing_review: int
    employees: list[EmployeeCompliance]
