from dataclasses import dataclass, field
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, status

from app.database.mongodb import tenant_memberships_collection, tenants_collection
from app.routers.auth import get_current_admin


@dataclass
class TenantContext:
    id: str
    name: str
    slug: str
    status: str
    policy: dict[str, Any] = field(default_factory=dict)
    user_id: str = ""
    user_role: str = "member"
    raw_tenant: dict[str, Any] = field(default_factory=dict)


def resolve_tenant(
    user: dict[str, Any] | None,
    requested_tenant_id: str,
    *,
    allow_inactive_tenant: bool = False,
) -> TenantContext:
    # The user must already be authenticated.
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = str(user.get("email") or user.get("id") or user.get("_id") or "").lower()
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User identity could not be verified",
        )

    # Find an active membership for this user and tenant.
    membership = tenant_memberships_collection.find_one(
        {
            "user_id": user_id,
            "tenant_id": requested_tenant_id,
            "status": "active",
        }
    )

    # A missing membership means access is not authorized.
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized for this tenant",
        )

    # A suspended or missing tenant must not be accessed.
    tenant = tenants_collection.find_one(
        {
            "$or": [{"id": requested_tenant_id}, {"_id": requested_tenant_id}],
        }
    )

    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant not found or access denied",
        )

    if tenant.get("status") != "active" and not allow_inactive_tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant is suspended or deactivated",
        )

    tenant_id = str(tenant.get("id") or tenant.get("_id") or requested_tenant_id)
    return TenantContext(
        id=tenant_id,
        name=str(tenant.get("name", "")),
        slug=str(tenant.get("slug", "")),
        status=str(tenant.get("status", "active")),
        policy=dict(tenant.get("policy") or {}),
        user_id=user_id,
        user_role=str(membership.get("role", "member")),
        raw_tenant=tenant,
    )


def get_current_tenant(
    admin: Annotated[dict, Depends(get_current_admin)],
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
) -> TenantContext:
    user_id = str(
        admin.get("email") or admin.get("id") or admin.get("_id") or ""
    ).lower()

    token_tenant_id = admin.get("token_tenant_id")
    if token_tenant_id and x_tenant_id and x_tenant_id.strip() != token_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The access token is scoped to a different tenant",
        )

    if token_tenant_id:
        requested_tenant_id = token_tenant_id
    elif x_tenant_id:
        requested_tenant_id = x_tenant_id.strip()
    else:
        # Determine accessible tenants for the authenticated user
        memberships = list(
            tenant_memberships_collection.find(
                {"user_id": user_id, "status": "active"},
                {"_id": 0, "tenant_id": 1},
            ).limit(2)
        )
        if len(memberships) == 1:
            requested_tenant_id = memberships[0]["tenant_id"]
        elif len(memberships) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-Tenant-ID header is required",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-Tenant-ID header is required when user has multiple tenants",
            )

    return resolve_tenant(user=admin, requested_tenant_id=requested_tenant_id)
