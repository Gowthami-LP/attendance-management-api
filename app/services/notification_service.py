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
)
from app.services.attendance_service import OFFICE_TIMEZONE
from app.services.compliance_service import evaluate_weekly_compliance


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
        raise RuntimeError(
            "SMTP configuration is incomplete. Check the .env file."
        )

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


def deliver_notification(notification_id: str) -> dict[str, str]:
    notification = notifications_collection.find_one(
        {"notification_id": notification_id},
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

    claimed_notification = notifications_collection.find_one_and_update(
        {
            "notification_id": notification_id,
            "status": {"$in": ["pending", "failed"]},
        },
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

    try:
        send_notification_email(
            recipient=claimed_notification["recipient_email"],
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


def process_weekly_violations(week_start: date) -> dict[str, Any]:
    report = evaluate_weekly_compliance(week_start)

    if report.evaluation_status != "completed":
        raise ValueError(
            "Notifications can only be processed for a completed week."
        )

    created = 0
    sent = 0
    failed = 0
    skipped = 0

    for employee_result in report.employees:
        if employee_result.compliance_status != "violation":
            continue

        employee = employees_collection.find_one(
            {"employee_id": employee_result.employee_id},
            {"_id": 0, "email": 1},
        )

        if not employee or not employee.get("email"):
            skipped += 1
            continue

        subject = (
            "Office Attendance Policy Violation - "
            f"Week of {report.week_start}"
        )
        body = (
            f"Hello {employee_result.employee_name},\n\n"
            "Our attendance records indicate that you did not meet "
            "the office attendance policy for the following week:\n\n"
            f"Week: {report.week_start} to {report.week_end}\n"
            f"Qualifying office days: {employee_result.qualifying_days} "
            "(minimum required: 3)\n"
            f"Completed working hours: {employee_result.total_hours} "
            "(minimum required: 15)\n\n"
            f"Reason: {employee_result.reason}\n\n"
            "Please contact your manager or HR team if you believe "
            "these records are incorrect.\n\n"
            "This is an automatically generated notification."
        )

        notification_id = str(uuid4())
        notification_document = {
            "notification_id": notification_id,
            "employee_id": employee_result.employee_id,
            "recipient_email": employee["email"],
            "week_start": report.week_start,
            "week_end": report.week_end,
            "subject": subject,
            "body": body,
            "status": "pending",
            "attempts": 0,
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

        delivery_result = deliver_notification(notification_id)
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


def retry_failed_notification(notification_id: str) -> dict[str, str]:
    notification = notifications_collection.find_one(
        {"notification_id": notification_id},
        {"_id": 0, "status": 1},
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

    return deliver_notification(notification_id)
