from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MembershipRole = Literal["admin", "member"]
MembershipStatus = Literal["active", "suspended", "deactivated"]


class MembershipCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=120)
    role: MembershipRole = "member"


class MembershipUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: MembershipRole | None = None
    status: MembershipStatus | None = None


class MembershipResponse(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    role: MembershipRole
    status: MembershipStatus
    created_at: str | None = None
