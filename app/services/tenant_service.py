from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.database.mongodb import tenant_memberships_collection, tenants_collection
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


def create_tenant(
    data: TenantCreate,
    creator_email: str | None = None,
) -> TenantResponse:
    normalized_slug = data.slug.strip().lower()
    tenant_id = f"tenant_{normalized_slug.replace('-', '_')}"

    # Verify if tenant slug or ID already exists
    existing = tenants_collection.find_one(
        {"$or": [{"slug": normalized_slug}, {"id": tenant_id}, {"_id": tenant_id}]}
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tenant with this slug already exists",
        )

    now = datetime.now(UTC).isoformat()
    tenant_document = {
        "_id": tenant_id,
        "id": tenant_id,
        "name": data.name.strip(),
        "slug": normalized_slug,
        "status": "active",
        "policy": data.policy.model_dump(),
        "created_at": now,
    }

    try:
        tenants_collection.insert_one(tenant_document)
    except DuplicateKeyError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tenant with this slug or ID already exists",
        ) from error

    # Provision initial tenant administrator membership
    initial_admin = data.admin_email or creator_email
    if initial_admin:
        admin_user_id = str(initial_admin).lower()
        membership_id = str(uuid4())
        membership_doc = {
            "_id": membership_id,
            "id": membership_id,
            "tenant_id": tenant_id,
            "user_id": admin_user_id,
            "role": "admin",
            "status": "active",
            "created_at": now,
        }
        try:
            tenant_memberships_collection.insert_one(membership_doc)
        except DuplicateKeyError:
            pass

    return TenantResponse(
        id=tenant_document["id"],
        name=tenant_document["name"],
        slug=tenant_document["slug"],
        status=tenant_document["status"],
        policy=tenant_document["policy"],
        created_at=tenant_document["created_at"],
    )


def get_tenant_by_id(tenant_id: str) -> TenantResponse:
    tenant = tenants_collection.find_one(
        {
            "$or": [{"id": tenant_id}, {"_id": tenant_id}],
        }
    )
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    return TenantResponse(
        id=tenant.get("id") or str(tenant.get("_id")),
        name=tenant["name"],
        slug=tenant["slug"],
        status=tenant.get("status", "active"),
        policy=tenant.get("policy", {}),
        created_at=tenant.get("created_at"),
    )


def get_tenant_by_slug(slug: str) -> TenantResponse:
    tenant = tenants_collection.find_one({"slug": slug.strip().lower()})
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    return TenantResponse(
        id=tenant.get("id") or str(tenant.get("_id")),
        name=tenant["name"],
        slug=tenant["slug"],
        status=tenant.get("status", "active"),
        policy=tenant.get("policy", {}),
        created_at=tenant.get("created_at"),
    )


def list_tenants(user_id: str | None = None) -> list[TenantResponse]:
    if user_id is not None:
        user_id_clean = user_id.strip().lower()
        memberships = list(
            tenant_memberships_collection.find(
                {"user_id": user_id_clean, "status": "active"},
                {"_id": 0, "tenant_id": 1},
            )
        )
        accessible_tenant_ids = [m["tenant_id"] for m in memberships]
        tenants = list(
            tenants_collection.find(
                {
                    "$or": [
                        {"id": {"$in": accessible_tenant_ids}},
                        {"_id": {"$in": accessible_tenant_ids}},
                    ]
                }
            )
        )
    else:
        tenants = list(tenants_collection.find({}))

    return [
        TenantResponse(
            id=t.get("id") or str(t.get("_id")),
            name=t["name"],
            slug=t["slug"],
            status=t.get("status", "active"),
            policy=t.get("policy", {}),
            created_at=t.get("created_at"),
        )
        for t in tenants
    ]


def update_tenant(tenant_id: str, update_in: TenantUpdate) -> TenantResponse:
    updates: dict[str, Any] = {}
    if update_in.name is not None:
        updates["name"] = update_in.name.strip()
    if update_in.status is not None:
        updates["status"] = update_in.status
    if update_in.policy is not None:
        updates["policy"] = update_in.policy.model_dump()

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one field to update",
        )

    updated = tenants_collection.find_one_and_update(
        {"$or": [{"id": tenant_id}, {"_id": tenant_id}]},
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    return TenantResponse(
        id=updated.get("id") or str(updated.get("_id")),
        name=updated["name"],
        slug=updated["slug"],
        status=updated.get("status", "active"),
        policy=updated.get("policy", {}),
        created_at=updated.get("created_at"),
    )


def add_tenant_membership(
    tenant_id: str,
    data: MembershipCreate,
) -> MembershipResponse:
    # Verify tenant exists
    tenant = tenants_collection.find_one(
        {
            "$or": [{"id": tenant_id}, {"_id": tenant_id}],
        }
    )
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    clean_user = data.user_id.strip().lower()
    membership_id = str(uuid4())
    now = datetime.now(UTC).isoformat()
    membership_doc = {
        "_id": membership_id,
        "id": membership_id,
        "tenant_id": tenant_id,
        "user_id": clean_user,
        "role": data.role,
        "status": "active",
        "created_at": now,
    }

    try:
        tenant_memberships_collection.insert_one(membership_doc)
    except DuplicateKeyError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this tenant",
        ) from error

    return MembershipResponse(
        id=membership_id,
        tenant_id=tenant_id,
        user_id=clean_user,
        role=data.role,
        status="active",
        created_at=now,
    )


def list_tenant_memberships(tenant_id: str) -> list[MembershipResponse]:
    members = list(tenant_memberships_collection.find({"tenant_id": tenant_id}))
    return [
        MembershipResponse(
            id=m.get("id") or str(m.get("_id")),
            tenant_id=m["tenant_id"],
            user_id=m["user_id"],
            role=m.get("role", "member"),
            status=m.get("status", "active"),
            created_at=m.get("created_at"),
        )
        for m in members
    ]


def update_tenant_membership(
    tenant_id: str,
    user_id: str,
    data: MembershipUpdate,
) -> MembershipResponse:
    clean_user = user_id.strip().lower()
    updates: dict[str, Any] = {}
    if data.role is not None:
        updates["role"] = data.role
    if data.status is not None:
        updates["status"] = data.status

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one field to update",
        )

    current = tenant_memberships_collection.find_one(
        {"tenant_id": tenant_id, "user_id": clean_user}
    )
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Membership not found",
        )

    remains_admin = (
        updates.get("role", current.get("role", "member")) == "admin"
        and updates.get("status", current.get("status", "active")) == "active"
    )
    if (
        current.get("role") == "admin"
        and current.get("status") == "active"
        and not remains_admin
    ):
        other_active_admins = list(
            tenant_memberships_collection.find(
                {
                    "tenant_id": tenant_id,
                    "role": "admin",
                    "status": "active",
                    "user_id": {"$ne": clean_user},
                }
            ).limit(1)
        )
        if not other_active_admins:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A tenant must retain at least one active administrator",
            )

    updated = tenant_memberships_collection.find_one_and_update(
        {"tenant_id": tenant_id, "user_id": clean_user},
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Membership not found",
        )

    return MembershipResponse(
        id=updated.get("id") or str(updated.get("_id")),
        tenant_id=updated["tenant_id"],
        user_id=updated["user_id"],
        role=updated["role"],
        status=updated["status"],
        created_at=updated.get("created_at"),
    )


def remove_tenant_membership(tenant_id: str, user_id: str) -> None:
    clean_user = user_id.strip().lower()
    current = tenant_memberships_collection.find_one(
        {"tenant_id": tenant_id, "user_id": clean_user}
    )
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Membership not found",
        )
    if current.get("role") == "admin" and current.get("status") == "active":
        other_active_admins = list(
            tenant_memberships_collection.find(
                {
                    "tenant_id": tenant_id,
                    "role": "admin",
                    "status": "active",
                    "user_id": {"$ne": clean_user},
                }
            ).limit(1)
        )
        if not other_active_admins:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A tenant must retain at least one active administrator",
            )
    result = tenant_memberships_collection.find_one_and_update(
        {"tenant_id": tenant_id, "user_id": clean_user},
        {"$set": {"status": "deactivated"}},
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Membership not found",
        )
