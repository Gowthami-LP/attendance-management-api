import pytest
from fastapi import HTTPException

from app.schemas.employee import EmployeeCreate, EmployeeUpdate
from app.services import employee_service


@pytest.fixture
def employees(monkeypatch, fake_collection):
    collection = fake_collection(unique_fields=("employee_id", "email"))
    monkeypatch.setattr(employee_service, "employees_collection", collection)
    return collection


def test_employee_create_retrieve_update_and_deactivate(employees):
    created = employee_service.create_employee(EmployeeCreate(
        employee_id="EMP001",
        name="Taylor Example",
        email="Taylor@example.com",
        department="Engineering",
    ))
    assert created.email == "taylor@example.com"
    assert created.is_active is True

    retrieved = employee_service.get_employee_by_id("EMP001")
    assert retrieved.name == "Taylor Example"
    assert employee_service.get_employees(department="engineering")[0].employee_id == "EMP001"

    updated = employee_service.update_employee(
        "EMP001",
        EmployeeUpdate(name="Taylor Updated"),
    )
    assert updated.name == "Taylor Updated"
    assert updated.email == "taylor@example.com"

    deactivated = employee_service.deactivate_employee("EMP001")
    assert deactivated.is_active is False
    assert employee_service.get_employees(is_active=False)[0].employee_id == "EMP001"


def test_employee_update_rejects_empty_update(employees):
    with pytest.raises(HTTPException) as error:
        employee_service.update_employee("EMP001", EmployeeUpdate())

    assert error.value.status_code == 400
    assert error.value.detail == "Provide at least one field to update"


def test_missing_employee_returns_not_found(employees):
    with pytest.raises(HTTPException) as error:
        employee_service.get_employee_by_id("missing")

    assert error.value.status_code == 404
