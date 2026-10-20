from fastapi import FastAPI

from app.routers.employee_imports import router as employee_import_router


def test_employee_import_routes_are_exposed_in_openapi():
    app = FastAPI()
    app.include_router(employee_import_router)

    paths = app.openapi()["paths"]

    assert "post" in paths["/api/v1/employee-imports"]
    assert "get" in paths["/api/v1/employee-imports/{job_id}"]
    assert (
        paths["/api/v1/employee-imports"]["post"]["requestBody"]["content"].get(
            "multipart/form-data"
        )
        is not None
    )


def test_legacy_employee_import_routes_remain_available():
    paths = {route.path for route in employee_import_router.routes}

    assert "/api/v1/employees/import" in paths
    assert "/api/v1/employees/import/{job_id}" in paths
