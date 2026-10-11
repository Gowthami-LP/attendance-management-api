# Import Literal to restrict a field to specific values
from typing import Literal

# Import BaseModel to define and validate request data
from pydantic import BaseModel, ConfigDict, EmailStr, Field


# Define the structure of employee data submitted by the admin
class EmployeeCreate(BaseModel):
    # Reject unexpected fields in the incoming request
    model_config = ConfigDict(extra="forbid")

    # Employee ID must contain between 3 and 20 characters
    employee_id: str = Field(min_length=3, max_length=20)

    # Employee name must contain between 2 and 100 characters
    name: str = Field(min_length=2, max_length=100)

    # Validate that the email has a valid email format
    email: EmailStr

    # Department must not be empty
    department: str = Field(min_length=2, max_length=50)

# Define the employee structure returned by the API
class EmployeeResponse(BaseModel):
    # Employee's unique company ID
    employee_id: str

    # Employee's full name
    name: str

    # Employee's email address
    email: EmailStr

    # Employee's department
    department: str

    # Indicates whether the employee is active
    is_active: bool = True

# Restrict the optional active-status filter to supported values
EmployeeStatus = Literal["active", "inactive"]


class EmployeeUpdate(BaseModel):
    # Reject fields that are not part of this schema.
    model_config = ConfigDict(extra="forbid")

    # Every field is optional because PATCH updates only supplied fields.
    name: str | None = Field(default=None, min_length=2, max_length=100)
    email: EmailStr | None = None
    department: str | None = Field(default=None, min_length=2, max_length=50)
