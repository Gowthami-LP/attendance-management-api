from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AttendancePolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_qualifying_days: int = Field(default=3, ge=1, le=7)
    min_hours_per_day: float = Field(default=5.0, ge=0.5, le=24.0)
    min_weekly_hours: float = Field(default=15.0, ge=1.0, le=168.0)


TenantStatus = Literal["active", "suspended", "deactivated"]


class TenantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Company name shown in the application.
    name: str = Field(min_length=2, max_length=120)
    # URL-friendly identifier for the company.
    slug: str = Field(
        min_length=2,
        max_length=60,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    # Optional custom attendance policy configuration.
    policy: AttendancePolicyConfig = Field(default_factory=AttendancePolicyConfig)
    # Optional initial administrator email to grant admin membership.
    admin_email: EmailStr | None = None


class TenantUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=120)
    status: TenantStatus | None = None
    policy: AttendancePolicyConfig | None = None


class TenantResponse(BaseModel):
    # Unique identifier for this tenant.
    id: str
    # Human-readable company name.
    name: str
    # Unique URL-friendly identifier.
    slug: str
    # Whether this tenant is allowed to use the application.
    status: TenantStatus
    # Configured attendance policy.
    policy: AttendancePolicyConfig = Field(default_factory=AttendancePolicyConfig)
    # Creation timestamp in ISO format.
    created_at: str | None = None
