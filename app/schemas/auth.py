from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class AdminLoginRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "tenant_id": "tenant_lpg_technologies",
                    "password": "your-password",
                },
                {
                    "email": "admin@example.com",
                    "password": "your-password",
                    "tenant_id": "tenant_lpg_technologies",
                },
            ]
        },
    )

    email: EmailStr | None = Field(
        default=None,
        description=("Optional when tenant_id has exactly one active administrator."),
    )
    password: str = Field(min_length=1)
    tenant_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        description="Optional tenant ID to scope the access token to.",
    )

    @model_validator(mode="after")
    def require_email_or_tenant_id(self):
        if self.email is None and self.tenant_id is None:
            raise ValueError("Provide an email address or tenant_id.")
        return self


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminResponse(BaseModel):
    email: EmailStr
    role: str
