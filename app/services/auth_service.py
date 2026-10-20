from fastapi import HTTPException, status

from app.database.mongodb import (
    admins_collection,
    tenant_memberships_collection,
    tenants_collection,
)
from app.security.auth_utils import create_access_token, verify_password


def login_admin(
    email: str | None,
    password: str,
    tenant_id: str | None = None,
) -> dict:
    if email is None and tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide an email address or tenant_id",
        )

    membership = None
    if email is None and tenant_id is not None:
        tenant = tenants_collection.find_one(
            {"$or": [{"id": tenant_id}, {"_id": tenant_id}]}
        )
        if tenant is None or tenant.get("status") != "active":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid tenant ID or password",
            )

        tenant_admins = list(
            tenant_memberships_collection.find(
                {
                    "tenant_id": tenant_id,
                    "status": "active",
                    "role": "admin",
                }
            )
        )
        if len(tenant_admins) != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Log in with email and password because this tenant does not "
                    "have exactly one active administrator"
                ),
            )
        membership = tenant_admins[0]
        email = str(membership.get("user_id") or "").strip().lower()

    admin = admins_collection.find_one({"email": email.lower()}) if email else None

    if (
        not admin
        or not admin.get("is_active", True)
        or not verify_password(password, admin["password_hash"])
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if tenant_id is not None:
        tenant = tenants_collection.find_one(
            {"$or": [{"id": tenant_id}, {"_id": tenant_id}]}
        )
        if membership is None:
            membership = tenant_memberships_collection.find_one(
                {
                    "user_id": admin["email"].lower(),
                    "tenant_id": tenant_id,
                    "status": "active",
                }
            )
        if tenant is None or tenant.get("status") != "active" or membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This account is not authorized for the requested tenant",
            )

    token = create_access_token(admin["email"], tenant_id=tenant_id)
    return {
        "access_token": token,
        "token_type": "bearer",  # nosec B105
    }
