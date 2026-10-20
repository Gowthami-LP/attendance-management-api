from openpyxl import Workbook

from app.tasks import employee_import_tasks


def test_import_task_accepts_employees_workbook_without_department(
    tmp_path,
    fake_collection,
    monkeypatch,
):
    jobs = fake_collection([{"_id": "job-1", "status": "queued"}])
    employees = fake_collection(
        unique_fields=(("tenant_id", "employee_id"), ("tenant_id", "email"))
    )
    monkeypatch.setattr(employee_import_tasks, "employee_import_jobs_collection", jobs)
    monkeypatch.setattr(employee_import_tasks, "employees_collection", employees)

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["employee_id", "name", "email"])
    sheet.append(["EMP1001", "Rahul Kumar", "rahul@example.com"])
    sheet.append(["EMP1002", "Priya Sharma", "priya@example.com"])
    file_path = tmp_path / "employees.xlsx"
    workbook.save(file_path)

    result = employee_import_tasks.import_employees_from_excel.run(
        "job-1",
        "tenant-example",
        str(file_path),
    )

    assert result == {
        "job_id": "job-1",
        "status": "completed",
        "processed": 2,
        "succeeded": 2,
        "failed": 0,
    }
    assert jobs.documents[0]["total_rows"] == 2
    assert [employee["department"] for employee in employees.documents] == [
        "Unassigned",
        "Unassigned",
    ]
    assert all(
        employee["tenant_id"] == "tenant-example" for employee in employees.documents
    )
