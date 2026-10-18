import os
import smtplib
from datetime import date, datetime
from email.message import EmailMessage
from typing import Any
from uuid import uuid4

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.database.mongodb import (
    employees_collection,
    notifications_collection,
    tenants_collection,
)
from app.services.attendance_service import OFFICE_TIMEZONE
from app.services.compliance_service import evaluate_weekly_compliance


def _tenant_filter(tenant_id: str) -> dict[str, Any] | str:
    if tenant_id == "default":
        return {"$in": ["default", None]}
    return tenant_id


def send_notification_email(
    recipient: str,
    subject: str,
    body: str,
) -> None:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM_EMAIL")

    if not all((smtp_host, sender, smtp_username, smtp_password)):
        raise RuntimeError("SMTP configuration is incomplete. Check the .env file.")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_username, smtp_password)
        server.send_message(message)


def deliver_notification(
    notification_id: str,
    tenant_id: str | None = None,
) -> dict[str, str]:
    query: dict[str, Any] = {"notification_id": notification_id}
    if tenant_id:
        query["tenant_id"] = _tenant_filter(tenant_id)

    notification = notifications_collection.find_one(
        query,
        {"_id": 0},
    )

    if notification is None:
        return {
            "notification_id": notification_id,
            "status": "not_found",
        }

    if notification["status"] == "sent":
        return {
            "notification_id": notification_id,
            "status": "sent",
            "message": "Notification has already been sent.",
        }

    if notification["status"] not in ("pending", "failed"):
        return {
            "notification_id": notification_id,
            "status": notification["status"],
        }

    # Atomically claim the notification job
    claim_query: dict[str, Any] = {
        "notification_id": notification_id,
        "status": {"$in": ["pending", "failed"]},
    }
    if tenant_id:
        claim_query["tenant_id"] = _tenant_filter(tenant_id)

    claimed_notification = notifications_collection.find_one_and_update(
        claim_query,
        {
            "$set": {
                "status": "sending",
                "last_error": None,
            },
            "$inc": {"attempts": 1},
        },
        projection={"_id": 0},
        return_document=ReturnDocument.BEFORE,
    )

    if claimed_notification is None:
        current_notification = notifications_collection.find_one(
            {"notification_id": notification_id},
            {"_id": 0, "status": 1},
        )
        if current_notification is None:
            return {
                "notification_id": notification_id,
                "status": "not_found",
            }
        return {
            "notification_id": notification_id,
            "status": current_notification["status"],
        }

    job_tenant_id = claimed_notification.get("tenant_id")

    # Validate tenant if job is tenant-scoped
    if job_tenant_id and job_tenant_id != "default":
        tenant = tenants_collection.find_one(
            {
                "$or": [{"id": job_tenant_id}, {"_id": job_tenant_id}],
            }
        )
        if tenant is None or tenant.get("status") != "active":
            tenant_status = tenant.get("status") if tenant else "missing"
            error_msg = f"Tenant {job_tenant_id} is {tenant_status}"
            notifications_collection.update_one(
                {"notification_id": notification_id},
                {
                    "$set": {
                        "status": "failed",
                        "last_error": error_msg,
                    }
                },
            )
            return {
                "notification_id": notification_id,
                "status": "failed",
                "message": error_msg,
            }

    # Load employee within the specific tenant to ensure latest recipient email
    recipient_email = claimed_notification["recipient_email"]
    emp_id = claimed_notification.get("employee_id")
    if job_tenant_id and emp_id:
        employee = employees_collection.find_one(
            {
                "tenant_id": _tenant_filter(job_tenant_id),
                "employee_id": emp_id,
            },
            {"_id": 0, "email": 1, "is_active": 1},
        )
        if employee and employee.get("email"):
            recipient_email = employee["email"]

    try:
        send_notification_email(
            recipient=recipient_email,
            subject=claimed_notification["subject"],
            body=claimed_notification["body"],
        )
    except (OSError, RuntimeError, smtplib.SMTPException, ValueError) as error:
        notifications_collection.update_one(
            {
                "notification_id": notification_id,
                "status": "sending",
            },
            {
                "$set": {
                    "status": "failed",
                    "last_error": f"{type(error).__name__}: {error}"[:500],
                }
            },
        )
        return {
            "notification_id": notification_id,
            "status": "failed",
            "message": "Email delivery failed. Check notification history.",
        }

    notifications_collection.update_one(
        {
            "notification_id": notification_id,
            "status": "sending",
        },
        {
            "$set": {
                "status": "sent",
                "sent_at": datetime.now(OFFICE_TIMEZONE).isoformat(),
                "last_error": None,
            }
        },
    )
    return {
        "notification_id": notification_id,
        "status": "sent",
        "message": "Email submitted successfully to the SMTP server.",
    }


def process_weekly_violations(
    week_start: date,
    tenant_id: str = "default",
) -> dict[str, Any]:
    report = evaluate_weekly_compliance(week_start, tenant_id=tenant_id)

    if report.evaluation_status != "completed":
        raise ValueError("Notifications can only be processed for a completed week.")

    created = 0
    sent = 0
    failed = 0
    skipped = 0

    tenant = (
        tenants_collection.find_one(
            {"$or": [{"id": tenant_id}, {"_id": tenant_id}]},
            {"_id": 0, "policy": 1},
        )
        if tenant_id != "default"
        else None
    )
    policy = (tenant or {}).get("policy") or {}
    min_qualifying_days = int(policy.get("min_qualifying_days", 3))
    min_weekly_hours = float(policy.get("min_weekly_hours", 15))

    for employee_result in report.employees:
        if employee_result.compliance_status != "violation":
            continue

        employee = employees_collection.find_one(
            {
                "tenant_id": _tenant_filter(tenant_id),
                "employee_id": employee_result.employee_id,
            },
            {"_id": 0, "email": 1},
        )

        if not employee or not employee.get("email"):
            skipped += 1
            continue

        subject = f"Office Attendance Policy Violation - Week of {report.week_start}"
        body = (
            f"Hello {employee_result.employee_name},\n\n"
            "Our attendance records indicate that you did not meet "
            "the office attendance policy for the following week:\n\n"
            f"Week: {report.week_start} to {report.week_end}\n"
            f"Qualifying office days: {employee_result.qualifying_days} "
            f"(minimum required: {min_qualifying_days})\n"
            f"Completed working hours: {employee_result.total_hours} "
            f"(minimum required: {min_weekly_hours:g})\n\n"
            f"Reason: {employee_result.reason}\n\n"
            "Please contact your manager or HR team if you believe "
            "these records are incorrect.\n\n"
            "This is an automatically generated notification."
        )

        notification_id = str(uuid4())
        notification_document = {
            "_id": notification_id,
            "notification_id": notification_id,
            "tenant_id": tenant_id,
            "employee_id": employee_result.employee_id,
            "recipient_email": employee["email"],
            "week_start": report.week_start,
            "week_end": report.week_end,
            "subject": subject,
            "body": body,
            "status": "pending",
            "attempts": 0,
            "max_attempts": 3,
            "created_at": datetime.now(OFFICE_TIMEZONE).isoformat(),
            "sent_at": None,
            "last_error": None,
        }

        try:
            notifications_collection.insert_one(notification_document)
            created += 1
        except DuplicateKeyError:
            skipped += 1
            continue

        delivery_result = deliver_notification(notification_id, tenant_id=tenant_id)
        if delivery_result["status"] == "sent":
            sent += 1
        else:
            failed += 1

    return {
        "week_start": report.week_start,
        "week_end": report.week_end,
        "created": created,
        "sent": sent,
        "failed": failed,
        "skipped": skipped,
    }


def retry_failed_notification(
    notification_id: str,
    tenant_id: str | None = None,
) -> dict[str, str]:
    query: dict[str, Any] = {"notification_id": notification_id}
    if tenant_id:
        query["tenant_id"] = _tenant_filter(tenant_id)

    notification = notifications_collection.find_one(
        query,
        {"_id": 0, "status": 1, "attempts": 1, "max_attempts": 1},
    )

    if notification is None:
        return {
            "notification_id": notification_id,
            "status": "not_found",
        }

    if notification["status"] == "sent":
        return {
            "notification_id": notification_id,
            "status": "sent",
            "message": "This notification was already sent.",
        }

    if notification["status"] != "failed":
        return {
            "notification_id": notification_id,
            "status": notification["status"],
            "message": "Only failed notifications can be retried.",
        }

    if notification.get("attempts", 0) >= notification.get("max_attempts", 3):
        return {
            "notification_id": notification_id,
            "status": "failed",
            "message": "The notification retry limit has been reached.",
        }

    return deliver_notification(notification_id, tenant_id=tenant_id)
