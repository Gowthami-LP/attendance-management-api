from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.database.mongodb import admins_collection
from app.schemas.auth import AdminLoginRequest, AdminLoginResponse, AdminResponse
from app.security.auth_utils import decode_access_token
from app.services.auth_service import login_admin

router = APIRouter(prefix="/api/v1/auth/admin", tags=["Admin Authentication"])

bearer_scheme = HTTPBearer(auto_error=False)


@router.post(
    "/login",
    response_model=AdminLoginResponse,
    summary="Log in, optionally scoped to a tenant",
    description=(
        "Provide tenant_id to receive a token scoped to that tenant. "
        "The account must have an active membership in the requested tenant."
    ),
)
def admin_login(request: AdminLoginRequest):
    return login_admin(
        request.email.lower(),
        request.password,
        tenant_id=request.tenant_id,
    )


def get_current_admin(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(credentials.credentials)
    except (jwt.InvalidTokenError, RuntimeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("role") != "admin" or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    admin = admins_collection.find_one({"email": payload["sub"].lower()})
    if not admin or not admin.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin account is unavailable",
        )
    if admin.get("role", "admin") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    admin["token_tenant_id"] = payload.get("tenant_id")
    return admin


@router.get("/me", response_model=AdminResponse)
def read_current_admin(
    admin: Annotated[dict, Depends(get_current_admin)],
):
    return {
        "email": admin["email"],
        "role": admin.get("role", "admin"),
    }
