from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.routers.auth import get_current_admin
from app.schemas.membership import (
    MembershipCreate,
    MembershipResponse,
    MembershipUpdate,
)
from app.schemas.tenant import (
    TenantCreate,
    TenantResponse,
    TenantUpdate,
)
from app.security.tenant_context import TenantContext, resolve_tenant
from app.services.tenant_service import (
    add_tenant_membership,
    create_tenant,
    get_tenant_by_id,
    list_tenant_memberships,
    list_tenants,
    remove_tenant_membership,
    update_tenant,
    update_tenant_membership,
)

router = APIRouter(
    prefix="/api/v1/tenants",
    tags=["Tenants"],
    dependencies=[Depends(get_current_admin)],
)


def require_tenant_admin(
    tenant_id: str,
    current_admin: Annotated[dict, Depends(get_current_admin)],
) -> TenantContext:
    """Require active administrator membership in the requested tenant."""
    token_tenant_id = current_admin.get("token_tenant_id")
    if token_tenant_id and token_tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The access token is scoped to a different tenant",
        )
    # Tenant administrators must be able to manage membership and reactivate a
    # suspended tenant; data endpoints still require the tenant to be active.
    tenant = resolve_tenant(
        current_admin,
        tenant_id,
        allow_inactive_tenant=True,
    )
    if tenant.user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant administrator access required",
        )
    return tenant


def require_tenant_member(
    tenant_id: str,
    current_admin: Annotated[dict, Depends(get_current_admin)],
) -> TenantContext:
    """Require active membership to view this tenant's details."""
    token_tenant_id = current_admin.get("token_tenant_id")
    if token_tenant_id and token_tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The access token is scoped to a different tenant",
        )
    return resolve_tenant(current_admin, tenant_id)


@router.post(
    "",
    response_model=TenantResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_tenant_endpoint(
    tenant_in: TenantCreate,
    current_admin: Annotated[dict, Depends(get_current_admin)],
) -> TenantResponse:
    if current_admin.get("token_tenant_id"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A tenant-scoped token cannot create another tenant",
        )
    creator_email = str(current_admin.get("email") or "").lower()
    return create_tenant(tenant_in, creator_email=creator_email)


@router.get(
    "",
    response_model=list[TenantResponse],
)
def list_tenants_endpoint(
    current_admin: Annotated[dict, Depends(get_current_admin)],
) -> list[TenantResponse]:
    token_tenant_id = current_admin.get("token_tenant_id")
    if token_tenant_id:
        tenant = resolve_tenant(current_admin, token_tenant_id)
        return [get_tenant_by_id(tenant.id)]
    user_id = str(current_admin.get("email") or current_admin.get("id") or "").lower()
    return list_tenants(user_id=user_id)


@router.get(
    "/{tenant_id}",
    response_model=TenantResponse,
)
def get_tenant_endpoint(
    tenant_id: str,
    _tenant: Annotated[TenantContext, Depends(require_tenant_member)],
) -> TenantResponse:
    return get_tenant_by_id(tenant_id)


@router.patch(
    "/{tenant_id}",
    response_model=TenantResponse,
)
def update_tenant_endpoint(
    tenant_id: str,
    update_in: TenantUpdate,
    _tenant: Annotated[TenantContext, Depends(require_tenant_admin)],
) -> TenantResponse:
    return update_tenant(tenant_id, update_in)


@router.post(
    "/{tenant_id}/members",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_member_endpoint(
    tenant_id: str,
    member_in: MembershipCreate,
    _tenant: Annotated[TenantContext, Depends(require_tenant_admin)],
) -> MembershipResponse:
    return add_tenant_membership(tenant_id, member_in)


@router.get(
    "/{tenant_id}/members",
    response_model=list[MembershipResponse],
)
def list_members_endpoint(
    tenant_id: str,
    _tenant: Annotated[TenantContext, Depends(require_tenant_admin)],
) -> list[MembershipResponse]:
    return list_tenant_memberships(tenant_id)


@router.patch(
    "/{tenant_id}/members/{user_id}",
    response_model=MembershipResponse,
)
def update_member_endpoint(
    tenant_id: str,
    user_id: str,
    update_in: MembershipUpdate,
    _tenant: Annotated[TenantContext, Depends(require_tenant_admin)],
) -> MembershipResponse:
    return update_tenant_membership(tenant_id, user_id, update_in)


@router.delete(
    "/{tenant_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_member_endpoint(
    tenant_id: str,
    user_id: str,
    _tenant: Annotated[TenantContext, Depends(require_tenant_admin)],
) -> None:
    remove_tenant_membership(tenant_id, user_id)
