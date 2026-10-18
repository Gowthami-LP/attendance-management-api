from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AdminLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1)
    tenant_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        description="Optional tenant ID to scope the access token to.",
    )


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminResponse(BaseModel):
    email: EmailStr
    role: str
