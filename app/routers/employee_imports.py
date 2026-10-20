import os
import uuid
from datetime import UTC, datetime
from tempfile import NamedTemporaryFile
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.database.mongodb import employee_import_jobs_collection
from app.schemas.employee_import import (
    EmployeeImportAccepted,
    EmployeeImportStatusResponse,
)
from app.security.tenant_context import TenantContext, get_current_tenant
from app.tasks.celery_app import celery_app

router = APIRouter(prefix="/api/v1", tags=["employee-imports"])


def _job_collection():
    return employee_import_jobs_collection


@router.post(
    "/employees/import",
    include_in_schema=False,
    response_model=EmployeeImportAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
@router.post(
    "/employee-imports",
    response_model=EmployeeImportAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def queue_employee_import(
    tenant: Annotated[TenantContext, Depends(get_current_tenant)],
    file: UploadFile = File(...),  # noqa: B008
) -> EmployeeImportAccepted:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A file is required",
        )

    extension = os.path.splitext(file.filename)[1].lower()
    if extension != ".xlsx":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .xlsx Excel files are supported",
        )

    job_id = str(uuid.uuid4())
    job_collection = _job_collection()
    now = datetime.now(UTC).isoformat()

    temp_directory = os.getenv("EMPLOYEE_IMPORT_TEMP_DIR")
    if temp_directory:
        os.makedirs(temp_directory, exist_ok=True)

    with NamedTemporaryFile(
        delete=False,
        suffix=extension,
        dir=temp_directory,
    ) as temp_file:
        contents = await file.read()
        temp_file.write(contents)
        temp_path = temp_file.name

    job_collection.insert_one(
        {
            "_id": job_id,
            "tenant_id": tenant.id,
            "filename": file.filename,
            "status": "queued",
            "total_rows": None,
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "errors": [],
            "created_at": now,
            "completed_at": None,
        }
    )

    celery_app.send_task(
        "employee_import.process",
        args=[job_id, tenant.id, temp_path],
    )

    return EmployeeImportAccepted(
        job_id=job_id,
        status="queued",
        message="Employee import has been queued for processing",
    )


@router.get(
    "/employees/import/{job_id}",
    include_in_schema=False,
    response_model=EmployeeImportStatusResponse,
)
@router.get(
    "/employee-imports/{job_id}",
    response_model=EmployeeImportStatusResponse,
)
async def get_employee_import_status(
    tenant: Annotated[TenantContext, Depends(get_current_tenant)],
    job_id: str,
) -> EmployeeImportStatusResponse:
    job = _job_collection().find_one({"_id": job_id, "tenant_id": tenant.id})
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import job not found",
        )

    return EmployeeImportStatusResponse(
        job_id=str(job["_id"]),
        status=job.get("status", "queued"),
        total_rows=job.get("total_rows"),
        processed=job.get("processed", 0),
        succeeded=job.get("succeeded", 0),
        failed=job.get("failed", 0),
        error=job.get("error"),
        created_at=job.get("created_at"),
        completed_at=job.get("completed_at"),
    )
