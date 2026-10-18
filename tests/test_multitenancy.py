import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import main
from app.database import mongodb
from app.routers import (
    attendance,
    auth,
    compliance,
    employees,
    notifications,
    reports,
    tenants,
)
from app.schemas.employee import EmployeeCreate
from app.schemas.membership import MembershipCreate, MembershipUpdate
from app.schemas.tenant import AttendancePolicyConfig, TenantCreate, TenantUpdate
from app.security import tenant_context
from app.security.auth_utils import create_access_token, hash_password
from app.services import (
    attendance_service,
    auth_service,
    compliance_service,
    employee_service,
    notification_service,
    report_service,
    tenant_service,
)
from app.workers import notification_worker


@pytest.fixture
def mock_mt_db(monkeypatch, fake_collection):
    tenants_col = fake_collection(unique_fields=("slug", "id"))
    memberships_col = fake_collection(unique_fields=(("tenant_id", "user_id"),))
    employees_col = fake_collection(
        unique_fields=(("tenant_id", "employee_id"), ("tenant_id", "email"))
    )
    admins_col = fake_collection(unique_fields=("email",))
    attendance_col = fake_collection(
        unique_fields=(("tenant_id", "employee_id", "date"),)
    )
    notifications_col = fake_collection(
        unique_fields=("notification_id", ("tenant_id", "employee_id", "week_start"))
    )

    for module in (
        mongodb,
        main,
        tenants,
        tenant_service,
        tenant_context,
        employees,
        employee_service,
        attendance,
        attendance_service,
        compliance,
        compliance_service,
        reports,
        report_service,
        notifications,
        notification_service,
        notification_worker,
        auth,
        auth_service,
    ):
        if hasattr(module, "tenants_collection"):
            monkeypatch.setattr(module, "tenants_collection", tenants_col)
        if hasattr(module, "tenant_memberships_collection"):
            monkeypatch.setattr(
                module, "tenant_memberships_collection", memberships_col
            )
        if hasattr(module, "employees_collection"):
            monkeypatch.setattr(module, "employees_collection", employees_col)
        if hasattr(module, "admins_collection"):
            monkeypatch.setattr(module, "admins_collection", admins_col)
        if hasattr(module, "attendance_collection"):
            monkeypatch.setattr(module, "attendance_collection", attendance_col)
        if hasattr(module, "notifications_collection"):
            monkeypatch.setattr(module, "notifications_collection", notifications_col)

    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-32-chars-long-minimum")

    class FakeClient:
        admin = type("Admin", (), {"command": staticmethod(lambda cmd: {"ok": 1})})()

        @staticmethod
        def close():
            pass

    monkeypatch.setattr(main, "client", FakeClient())
    monkeypatch.setattr(main, "create_database_indexes", lambda: None)
    monkeypatch.setattr(main, "create_tenant_indexes", lambda: None)
    monkeypatch.setattr(main, "create_admin_indexes", lambda: None)
    monkeypatch.setattr(main, "create_attendance_indexes", lambda: None)
    monkeypatch.setattr(main, "create_notification_indexes", lambda: None)
    monkeypatch.setattr(main, "start_scheduler", lambda: None)
    monkeypatch.setattr(main, "stop_scheduler", lambda: None)

    # Seed an admin account
    admins_col.insert_one(
        {
            "email": "admin@example.com",
            "password_hash": hash_password("AdminPass123"),
            "role": "admin",
            "is_active": True,
        }
    )
    admins_col.insert_one(
        {
            "email": "other_admin@example.com",
            "password_hash": hash_password("OtherPass123"),
            "role": "admin",
            "is_active": True,
        }
    )

    return {
        "tenants": tenants_col,
        "memberships": memberships_col,
        "employees": employees_col,
        "admins": admins_col,
        "attendance": attendance_col,
        "notifications": notifications_col,
    }


def test_tenant_creation_and_slug_validation(mock_mt_db):
    # Valid tenant creation
    tenant = tenant_service.create_tenant(
        TenantCreate(
            name="Acme Corporation",
            slug="acme-corp",
            policy=AttendancePolicyConfig(
                min_qualifying_days=3, min_hours_per_day=5.0, min_weekly_hours=15.0
            ),
        ),
        creator_email="admin@example.com",
    )
    assert tenant.slug == "acme-corp"
    assert tenant.status == "active"
    assert tenant.id == "tenant_acme_corp"

    # Verify admin membership was provisioned
    memberships = mock_mt_db["memberships"].documents
    assert any(
        m["tenant_id"] == "tenant_acme_corp"
        and m["user_id"] == "admin@example.com"
        and m["role"] == "admin"
        for m in memberships
    )

    # Duplicate slug raises 409 Conflict
    with pytest.raises(HTTPException) as conflict_err:
        tenant_service.create_tenant(
            TenantCreate(name="Duplicate Acme", slug="acme-corp"),
            creator_email="admin@example.com",
        )
    assert conflict_err.value.status_code == 409


def test_tenant_membership_management(mock_mt_db):
    tenant = tenant_service.create_tenant(
        TenantCreate(name="Beta Industries", slug="beta-ind"),
        creator_email="admin@example.com",
    )
    tenant_id = tenant.id

    # Add member
    member = tenant_service.add_tenant_membership(
        tenant_id,
        MembershipCreate(user_id="user1@example.com", role="member"),
    )
    assert member.user_id == "user1@example.com"
    assert member.role == "member"

    # Do not allow the only tenant administrator to be demoted.
    with pytest.raises(HTTPException) as last_admin_error:
        tenant_service.update_tenant_membership(
            tenant_id,
            "admin@example.com",
            MembershipUpdate(role="member"),
        )
    assert last_admin_error.value.status_code == 409

    # Duplicate membership raises 409
    with pytest.raises(HTTPException) as dup_err:
        tenant_service.add_tenant_membership(
            tenant_id,
            MembershipCreate(user_id="user1@example.com", role="member"),
        )
    assert dup_err.value.status_code == 409

    # List members
    members = tenant_service.list_tenant_memberships(tenant_id)
    assert len(members) == 2  # creator admin + user1

    # Update member role
    updated = tenant_service.update_tenant_membership(
        tenant_id,
        "user1@example.com",
        MembershipUpdate(role="admin"),
    )
    assert updated.role == "admin"

    # Deactivate member
    tenant_service.remove_tenant_membership(tenant_id, "user1@example.com")
    membership_doc = mock_mt_db["memberships"].find_one(
        {"tenant_id": tenant_id, "user_id": "user1@example.com"}
    )
    assert membership_doc["status"] == "deactivated"


def test_tenant_resolution_and_access_control(mock_mt_db):
    # Setup Tenant ABC and Tenant XYZ
    t_abc = tenant_service.create_tenant(
        TenantCreate(name="ABC Corp", slug="abc"), creator_email="admin@example.com"
    )
    t_xyz = tenant_service.create_tenant(
        TenantCreate(name="XYZ Corp", slug="xyz"),
        creator_email="other_admin@example.com",
    )

    token_abc = create_access_token("admin@example.com")
    token_xyz = create_access_token("other_admin@example.com")

    with TestClient(main.app) as client:
        # 1. Unauthenticated request -> 401
        res = client.get("/employees", headers={"X-Tenant-ID": t_abc.id})
        assert res.status_code == 401

        # 2. Authenticated user for ABC accessing ABC with header -> 200
        res = client.get(
            "/employees",
            headers={"Authorization": f"Bearer {token_abc}", "X-Tenant-ID": t_abc.id},
        )
        assert res.status_code == 200

        # Authenticated user for XYZ accessing XYZ with header -> 200
        res_xyz = client.get(
            "/employees",
            headers={"Authorization": f"Bearer {token_xyz}", "X-Tenant-ID": t_xyz.id},
        )
        assert res_xyz.status_code == 200

        # 3. User with membership only in ABC attempting to access XYZ -> 403 Forbidden
        res = client.get(
            "/employees",
            headers={"Authorization": f"Bearer {token_abc}", "X-Tenant-ID": t_xyz.id},
        )
        assert res.status_code == 403
        assert "Not authorized for this tenant" in res.json()["detail"]

        # 4. Accessing a suspended tenant -> 403 Forbidden
        tenant_service.update_tenant(t_abc.id, TenantUpdate(status="suspended"))
        res = client.get(
            "/employees",
            headers={"Authorization": f"Bearer {token_abc}", "X-Tenant-ID": t_abc.id},
        )
        assert res.status_code == 403
        assert "suspended" in res.json()["detail"]

        # An active tenant administrator can restore a suspended tenant.
        restore = client.patch(
            f"/api/v1/tenants/{t_abc.id}",
            headers={"Authorization": f"Bearer {token_abc}"},
            json={"status": "active"},
        )
        assert restore.status_code == 200
        assert restore.json()["status"] == "active"


def test_tenant_management_is_scoped_to_active_tenant_admin_membership(mock_mt_db):
    tenant_a = tenant_service.create_tenant(
        TenantCreate(name="Tenant A", slug="tenant-a"),
        creator_email="admin@example.com",
    )
    tenant_b = tenant_service.create_tenant(
        TenantCreate(name="Tenant B", slug="tenant-b"),
        creator_email="other_admin@example.com",
    )
    tenant_service.add_tenant_membership(
        tenant_a.id,
        MembershipCreate(user_id="other_admin@example.com", role="member"),
    )
    token_a = create_access_token("admin@example.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    with TestClient(main.app) as client:
        listed = client.get("/api/v1/tenants", headers=headers_a)
        assert listed.status_code == 200
        assert [tenant["id"] for tenant in listed.json()] == [tenant_a.id]

        denied_read = client.get(f"/api/v1/tenants/{tenant_b.id}", headers=headers_a)
        assert denied_read.status_code == 403

        denied_update = client.patch(
            f"/api/v1/tenants/{tenant_b.id}",
            headers=headers_a,
            json={"name": "Unauthorized update"},
        )
        assert denied_update.status_code == 403

        denied_member_list = client.get(
            f"/api/v1/tenants/{tenant_b.id}/members", headers=headers_a
        )
        assert denied_member_list.status_code == 403

        member_token = create_access_token("other_admin@example.com")
        member_headers = {"Authorization": f"Bearer {member_token}"}
        can_read_own_tenant = client.get(
            f"/api/v1/tenants/{tenant_a.id}",
            headers=member_headers,
        )
        assert can_read_own_tenant.status_code == 200
        denied_as_member = client.get(
            f"/api/v1/tenants/{tenant_a.id}/members",
            headers=member_headers,
        )
        assert denied_as_member.status_code == 403


def test_tenant_login_scopes_token_and_selects_tenant_automatically(mock_mt_db):
    tenant_a = tenant_service.create_tenant(
        TenantCreate(name="Tenant A", slug="tenant-a"),
        creator_email="admin@example.com",
    )
    tenant_b = tenant_service.create_tenant(
        TenantCreate(name="Tenant B", slug="tenant-b"),
        creator_email="other_admin@example.com",
    )

    with TestClient(main.app) as client:
        login = client.post(
            "/api/v1/auth/admin/login",
            json={
                "email": "admin@example.com",
                "password": "AdminPass123",
                "tenant_id": tenant_a.id,
            },
        )
        assert login.status_code == 200
        tenant_token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {tenant_token}"}

        # The token selects its tenant, so callers do not need X-Tenant-ID.
        assert client.get("/employees", headers=headers).status_code == 200
        assert (
            client.get(f"/api/v1/tenants/{tenant_a.id}", headers=headers).status_code
            == 200
        )
        assert [
            item["id"] for item in client.get("/api/v1/tenants", headers=headers).json()
        ] == [tenant_a.id]
        assert (
            client.post(
                "/api/v1/tenants",
                headers=headers,
                json={"name": "Tenant C", "slug": "tenant-c"},
            ).status_code
            == 403
        )

        # The same tenant token cannot be redirected to a different tenant.
        other_tenant = client.get(
            "/employees",
            headers={**headers, "X-Tenant-ID": tenant_b.id},
        )
        assert other_tenant.status_code == 403
        assert (
            client.get(f"/api/v1/tenants/{tenant_b.id}", headers=headers).status_code
            == 403
        )

        # An account without membership cannot obtain a token for that tenant.
        denied_login = client.post(
            "/api/v1/auth/admin/login",
            json={
                "email": "admin@example.com",
                "password": "AdminPass123",
                "tenant_id": tenant_b.id,
            },
        )
        assert denied_login.status_code == 403


def test_cross_tenant_employee_isolation(mock_mt_db):
    t_abc = tenant_service.create_tenant(
        TenantCreate(name="ABC Corp", slug="abc"), creator_email="admin@example.com"
    )
    t_xyz = tenant_service.create_tenant(
        TenantCreate(name="XYZ Corp", slug="xyz"),
        creator_email="other_admin@example.com",
    )

    token_abc = create_access_token("admin@example.com")
    token_xyz = create_access_token("other_admin@example.com")

    with TestClient(main.app) as client:
        # Create EMP101 in tenant_abc
        res_abc = client.post(
            "/employees",
            headers={"Authorization": f"Bearer {token_abc}", "X-Tenant-ID": t_abc.id},
            json={
                "employee_id": "EMP101",
                "name": "Alice in ABC",
                "email": "alice@abc.example.com",
                "department": "Engineering",
            },
        )
        assert res_abc.status_code == 201

        # Create EMP101 in tenant_xyz (same employee ID in different tenant should succeed!)
        res_xyz = client.post(
            "/employees",
            headers={"Authorization": f"Bearer {token_xyz}", "X-Tenant-ID": t_xyz.id},
            json={
                "employee_id": "EMP101",
                "name": "Alice in XYZ",
                "email": "alice@xyz.example.com",
                "department": "Sales",
            },
        )
        assert res_xyz.status_code == 201

        # List employees for ABC -> returns only ABC's employee
        list_abc = client.get(
            "/employees",
            headers={"Authorization": f"Bearer {token_abc}", "X-Tenant-ID": t_abc.id},
        ).json()
        assert len(list_abc) == 1
        assert list_abc[0]["name"] == "Alice in ABC"
        assert list_abc[0]["department"] == "Engineering"

        # List employees for XYZ -> returns only XYZ's employee
        list_xyz = client.get(
            "/employees",
            headers={"Authorization": f"Bearer {token_xyz}", "X-Tenant-ID": t_xyz.id},
        ).json()
        assert len(list_xyz) == 1
        assert list_xyz[0]["name"] == "Alice in XYZ"
        assert list_xyz[0]["department"] == "Sales"

        # Update EMP101 in ABC
        client.patch(
            "/employees/EMP101",
            headers={"Authorization": f"Bearer {token_abc}", "X-Tenant-ID": t_abc.id},
            json={"name": "Alice ABC Updated"},
        )
        get_abc = client.get(
            "/employees/EMP101",
            headers={"Authorization": f"Bearer {token_abc}", "X-Tenant-ID": t_abc.id},
        ).json()
        assert get_abc["name"] == "Alice ABC Updated"

        # XYZ EMP101 remains untouched
        get_xyz = client.get(
            "/employees/EMP101",
            headers={"Authorization": f"Bearer {token_xyz}", "X-Tenant-ID": t_xyz.id},
        ).json()
        assert get_xyz["name"] == "Alice in XYZ"

        # Deactivate in ABC
        client.patch(
            "/employees/EMP101/deactivate",
            headers={"Authorization": f"Bearer {token_abc}", "X-Tenant-ID": t_abc.id},
        )
        get_abc_deact = client.get(
            "/employees/EMP101",
            headers={"Authorization": f"Bearer {token_abc}", "X-Tenant-ID": t_abc.id},
        ).json()
        assert get_abc_deact["is_active"] is False

        # XYZ EMP101 remains active
        get_xyz_act = client.get(
            "/employees/EMP101",
            headers={"Authorization": f"Bearer {token_xyz}", "X-Tenant-ID": t_xyz.id},
        ).json()
        assert get_xyz_act["is_active"] is True


def test_cross_tenant_attendance_isolation(mock_mt_db, monkeypatch, fixed_datetime):
    monkeypatch.setattr(attendance_service, "datetime", fixed_datetime)

    t_abc = tenant_service.create_tenant(
        TenantCreate(name="ABC Corp", slug="abc"), creator_email="admin@example.com"
    )
    t_xyz = tenant_service.create_tenant(
        TenantCreate(name="XYZ Corp", slug="xyz"),
        creator_email="other_admin@example.com",
    )

    token_abc = create_access_token("admin@example.com")
    token_xyz = create_access_token("other_admin@example.com")

    # Create employee EMP101 in both tenants
    employee_service.create_employee(
        EmployeeCreate(
            employee_id="EMP101",
            name="Alice ABC",
            email="alice@abc.example.com",
            department="IT",
        ),
        tenant_id=t_abc.id,
    )
    employee_service.create_employee(
        EmployeeCreate(
            employee_id="EMP101",
            name="Alice XYZ",
            email="alice@xyz.example.com",
            department="HR",
        ),
        tenant_id=t_xyz.id,
    )

    with TestClient(main.app) as client:
        # Check-in EMP101 in ABC
        cin_abc = client.post(
            "/api/v1/attendance/check-in",
            headers={"Authorization": f"Bearer {token_abc}", "X-Tenant-ID": t_abc.id},
            json={"employee_id": "EMP101"},
        )
        assert cin_abc.status_code == 201
        assert cin_abc.json()["employee_id"] == "EMP101"

        # Check-in EMP101 in XYZ succeeds independently without conflict
        cin_xyz = client.post(
            "/api/v1/attendance/check-in",
            headers={"Authorization": f"Bearer {token_xyz}", "X-Tenant-ID": t_xyz.id},
            json={"employee_id": "EMP101"},
        )
        assert cin_xyz.status_code == 201

        # Duplicate check-in within ABC fails with 409
        dup_cin = client.post(
            "/api/v1/attendance/check-in",
            headers={"Authorization": f"Bearer {token_abc}", "X-Tenant-ID": t_abc.id},
            json={"employee_id": "EMP101"},
        )
        assert dup_cin.status_code == 409

        # Check-out in ABC
        cout_abc = client.post(
            "/api/v1/attendance/check-out",
            headers={"Authorization": f"Bearer {token_abc}", "X-Tenant-ID": t_abc.id},
            json={"employee_id": "EMP101"},
        )
        assert cout_abc.status_code == 200

        # Retrieve attendance for EMP101 in ABC
        att_abc = client.get(
            "/api/v1/attendance/EMP101",
            headers={"Authorization": f"Bearer {token_abc}", "X-Tenant-ID": t_abc.id},
        ).json()
        assert len(att_abc) == 1
        assert att_abc[0]["exit_time"] is not None

        # Retrieve attendance in XYZ has its own distinct session (exit_time still None)
        att_xyz = client.get(
            "/api/v1/attendance/EMP101",
            headers={"Authorization": f"Bearer {token_xyz}", "X-Tenant-ID": t_xyz.id},
        ).json()
        assert len(att_xyz) == 1
        assert att_xyz[0]["exit_time"] is None

        # Changing header to XYZ with ABC's token is blocked with 403
        cross_res = client.get(
            "/api/v1/attendance/EMP101",
            headers={"Authorization": f"Bearer {token_abc}", "X-Tenant-ID": t_xyz.id},
        )
        assert cross_res.status_code == 403


def test_tenant_compliance_with_custom_policy(mock_mt_db, monkeypatch, fixed_datetime):
    monkeypatch.setattr(compliance_service, "datetime", fixed_datetime)

    # Tenant 1: Strict policy (3 days, 15 hours)
    t_strict = tenant_service.create_tenant(
        TenantCreate(
            name="Strict Co",
            slug="strict-co",
            policy=AttendancePolicyConfig(
                min_qualifying_days=3, min_hours_per_day=5.0, min_weekly_hours=15.0
            ),
        ),
        creator_email="admin@example.com",
    )

    # Tenant 2: Flexible policy (2 days, 10 hours)
    t_flex = tenant_service.create_tenant(
        TenantCreate(
            name="Flex Co",
            slug="flex-co",
            policy=AttendancePolicyConfig(
                min_qualifying_days=2, min_hours_per_day=5.0, min_weekly_hours=10.0
            ),
        ),
        creator_email="admin@example.com",
    )

    employee_service.create_employee(
        EmployeeCreate(
            employee_id="EMP_STRICT",
            name="Sam Strict",
            email="sam@strict.example.com",
            department="Dev",
        ),
        tenant_id=t_strict.id,
    )
    employee_service.create_employee(
        EmployeeCreate(
            employee_id="EMP_FLEX",
            name="Sam Flex",
            email="sam@flex.example.com",
            department="Dev",
        ),
        tenant_id=t_flex.id,
    )

    # Both employees attend 2 days for 5 hours each (total 10 hours) in week 2026-09-28
    for t_id, emp_id in [(t_strict.id, "EMP_STRICT"), (t_flex.id, "EMP_FLEX")]:
        for day in ("2026-09-28", "2026-09-29"):
            mock_mt_db["attendance"].insert_one(
                {
                    "tenant_id": t_id,
                    "employee_id": emp_id,
                    "date": day,
                    "entry_time": f"{day}T09:00:00+05:30",
                    "exit_time": f"{day}T14:00:00+05:30",
                    "duration_minutes": 300,
                }
            )

    token = create_access_token("admin@example.com")
    with TestClient(main.app) as client:
        # Strict Co: 2 days / 10 hours is a violation
        res_strict = client.get(
            "/api/v1/compliance/weekly?week_start=2026-09-28",
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": t_strict.id},
        ).json()
        assert res_strict["violating_employees"] == 1
        assert res_strict["employees"][0]["compliance_status"] == "violation"

        # Flex Co: 2 days / 10 hours meets the custom policy and is compliant!
        res_flex = client.get(
            "/api/v1/compliance/weekly?week_start=2026-09-28",
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": t_flex.id},
        ).json()
        assert res_flex["compliant_employees"] == 1
        assert res_flex["employees"][0]["compliance_status"] == "compliant"


def test_tenant_aware_reports(mock_mt_db, monkeypatch, fixed_datetime):
    monkeypatch.setattr(report_service, "datetime", fixed_datetime)

    t_abc = tenant_service.create_tenant(
        TenantCreate(name="ABC Corp", slug="abc"), creator_email="admin@example.com"
    )
    t_xyz = tenant_service.create_tenant(
        TenantCreate(name="XYZ Corp", slug="xyz"), creator_email="admin@example.com"
    )

    employee_service.create_employee(
        EmployeeCreate(
            employee_id="EMP_A",
            name="Adam ABC",
            email="adam@abc.example.com",
            department="HR",
        ),
        tenant_id=t_abc.id,
    )
    employee_service.create_employee(
        EmployeeCreate(
            employee_id="EMP_X",
            name="Xavier XYZ",
            email="xavier@xyz.example.com",
            department="Finance",
        ),
        tenant_id=t_xyz.id,
    )

    mock_mt_db["attendance"].insert_one(
        {
            "tenant_id": t_abc.id,
            "employee_id": "EMP_A",
            "date": "2026-10-06",
            "entry_time": "2026-10-06T09:00:00+05:30",
            "exit_time": "2026-10-06T17:00:00+05:30",
            "duration_minutes": 480,
        }
    )

    token = create_access_token("admin@example.com")
    with TestClient(main.app) as client:
        # Report for ABC should only contain Adam ABC
        report_abc = client.get(
            "/api/v1/reports/attendance?period=daily&reference_date=2026-10-06",
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": t_abc.id},
        ).json()
        assert report_abc["summary"]["total_records"] == 1
        assert report_abc["records"][0]["employee_id"] == "EMP_A"
        assert report_abc["records"][0]["attendance_status"] == "Present"

        # Report for XYZ should only contain Xavier XYZ (Not attended)
        report_xyz = client.get(
            "/api/v1/reports/attendance?period=daily&reference_date=2026-10-06",
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": t_xyz.id},
        ).json()
        assert report_xyz["summary"]["total_records"] == 1
        assert report_xyz["records"][0]["employee_id"] == "EMP_X"
        assert report_xyz["records"][0]["attendance_status"] == "Not attended office"


def test_tenant_aware_notifications_and_worker(mock_mt_db, monkeypatch, fixed_datetime):
    monkeypatch.setattr(notification_service, "datetime", fixed_datetime)

    t_abc = tenant_service.create_tenant(
        TenantCreate(name="ABC Corp", slug="abc"), creator_email="admin@example.com"
    )
    t_xyz = tenant_service.create_tenant(
        TenantCreate(name="XYZ Corp", slug="xyz"), creator_email="admin@example.com"
    )

    # Create violating employee in ABC
    employee_service.create_employee(
        EmployeeCreate(
            employee_id="EMP_A",
            name="Adam ABC",
            email="adam@abc.example.com",
            department="HR",
        ),
        tenant_id=t_abc.id,
    )

    # Mock email sending
    monkeypatch.setattr(
        notification_service, "send_notification_email", lambda **kwargs: None
    )

    token = create_access_token("admin@example.com")
    with TestClient(main.app) as client:
        # Trigger notifications for ABC
        res = client.post(
            "/api/v1/notifications/weekly-violations?week_start=2026-09-28",
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": t_abc.id},
        )
        assert res.status_code == 200
        assert res.json()["created"] == 1

        # Check notification persisted with tenant_id
        persisted = mock_mt_db["notifications"].documents[0]
        assert persisted["tenant_id"] == t_abc.id
        assert persisted["employee_id"] == "EMP_A"

        # List notifications for ABC
        notifs_abc = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": t_abc.id},
        ).json()
        assert len(notifs_abc) == 1
        assert notifs_abc[0]["tenant_id"] == t_abc.id

        # List notifications for XYZ -> empty!
        notifs_xyz = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": t_xyz.id},
        ).json()
        assert len(notifs_xyz) == 0

        # Attempting to retry ABC's notification under XYZ tenant context -> 404
        retry_cross = client.post(
            f"/api/v1/notifications/{persisted['notification_id']}/retry",
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": t_xyz.id},
        )
        assert retry_cross.status_code == 404


def test_notification_worker_tenant_validation_and_claiming(mock_mt_db, monkeypatch):
    t_abc = tenant_service.create_tenant(
        TenantCreate(name="ABC Corp", slug="abc"), creator_email="admin@example.com"
    )
    t_id = t_abc.id

    employee_service.create_employee(
        EmployeeCreate(
            employee_id="EMP_01",
            name="Emp 01",
            email="emp01@abc.example.com",
            department="Ops",
        ),
        tenant_id=t_id,
    )

    # Queue a notification
    mock_mt_db["notifications"].insert_one(
        {
            "notification_id": "notif-abc-1",
            "tenant_id": t_id,
            "employee_id": "EMP_01",
            "recipient_email": "old_emp@abc.example.com",
            "subject": "Notice",
            "body": "Body",
            "status": "pending",
            "attempts": 0,
            "created_at": "2026-10-15T09:00:00+05:30",
        }
    )

    sent_emails = []
    monkeypatch.setattr(
        notification_service,
        "send_notification_email",
        lambda recipient, subject, body: sent_emails.append((recipient, subject, body)),
    )

    # Run worker cycle
    stats = notification_worker.run_worker_cycle()
    assert stats["pending"]["processed"] == 1
    assert stats["pending"]["sent"] == 1
    assert len(sent_emails) == 1
    # Verify employee email within tenant was used
    assert sent_emails[0][0] == "emp01@abc.example.com"

    # Now test suspended tenant handling: suspended tenant notifications must fail
    mock_mt_db["notifications"].insert_one(
        {
            "notification_id": "notif-abc-2",
            "tenant_id": t_id,
            "employee_id": "EMP_02",
            "recipient_email": "emp02@abc.example.com",
            "subject": "Notice",
            "body": "Body",
            "status": "pending",
            "attempts": 0,
            "created_at": "2026-10-15T09:05:00+05:30",
        }
    )
    tenant_service.update_tenant(t_id, TenantUpdate(status="suspended"))

    stats_suspended = notification_worker.run_worker_cycle()
    assert stats_suspended["pending"]["failed"] == 1
    failed_doc = mock_mt_db["notifications"].find_one(
        {"notification_id": "notif-abc-2"}
    )
    assert failed_doc["status"] == "failed"
    assert "suspended" in failed_doc["last_error"]
