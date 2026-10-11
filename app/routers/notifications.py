from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.database.mongodb import notifications_collection
from app.services.attendance_service import OFFICE_TIMEZONE
from app.services.notification_service import (
    process_weekly_violations,
    retry_failed_notification,
)

router = APIRouter(
    prefix="/api/v1/notifications",
    tags=["Notifications"],
)


@router.post("/weekly-violations")
def trigger_weekly_notifications(
    week_start: Annotated[date | None, Query()] = None,
) -> dict[str, int | str]:
    today = datetime.now(OFFICE_TIMEZONE).date()
    current_monday = today - timedelta(days=today.weekday())
    previous_monday = current_monday - timedelta(days=7)
    selected_week = week_start or previous_monday

    if selected_week.weekday() != 0:
        raise HTTPException(
            status_code=400,
            detail="week_start must be a Monday",
        )

    if selected_week >= current_monday:
        raise HTTPException(
            status_code=400,
            detail="Select a completed week",
        )

    try:
        return process_weekly_violations(selected_week)
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error


@router.get("")
def list_notifications(
    notification_status: Annotated[
        str | None,
        Query(alias="status"),
    ] = None,
) -> list[dict]:
    allowed_statuses = {
        "pending",
        "sending",
        "sent",
        "failed",
    }

    if (
        notification_status is not None
        and notification_status not in allowed_statuses
    ):
        raise HTTPException(
            status_code=400,
            detail="Unsupported notification status",
        )

    query: dict[str, str] = {}
    if notification_status is not None:
        query["status"] = notification_status

    records = (
        notifications_collection.find(query, {"_id": 0})
        .sort("created_at", -1)
        .limit(100)
    )
    return list(records)


@router.post("/{notification_id}/retry")
def retry_notification(notification_id: str) -> dict[str, str]:
    result = retry_failed_notification(notification_id)

    if result["status"] == "not_found":
        raise HTTPException(
            status_code=404,
            detail="Notification not found",
        )

    return result
