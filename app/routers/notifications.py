from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database.mongodb import notifications_collection
from app.routers.auth import get_current_admin
from app.schemas.notification import (
    NotificationResponse,
    NotificationRetryResponse,
    NotificationStatus,
    NotificationTriggerResponse,
)
from app.services.attendance_service import OFFICE_TIMEZONE
from app.services.notification_service import (
    process_weekly_violations,
    retry_failed_notification,
)

router = APIRouter(
    prefix="/api/v1/notifications",
    tags=["Notifications"],
    dependencies=[Depends(get_current_admin)],
)


@router.post(
    "/weekly-violations",
    response_model=NotificationTriggerResponse,
)
def trigger_weekly_notifications(
    week_start: Annotated[date | None, Query()] = None,
) -> NotificationTriggerResponse:
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
        result = process_weekly_violations(selected_week)
        return NotificationTriggerResponse(**result)
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error


@router.get(
    "",
    response_model=list[NotificationResponse],
)
def list_notifications(
    notification_status: Annotated[
        NotificationStatus | None,
        Query(alias="status"),
    ] = None,
) -> list[NotificationResponse]:
    query: dict[str, str] = {}
    if notification_status is not None:
        query["status"] = notification_status

    records = (
        notifications_collection.find(query, {"_id": 0})
        .sort("created_at", -1)
        .limit(100)
    )
    return [NotificationResponse(**record) for record in records]


@router.post(
    "/{notification_id}/retry",
    response_model=NotificationRetryResponse,
)
def retry_notification(notification_id: str) -> NotificationRetryResponse:
    result = retry_failed_notification(notification_id)

    if result["status"] == "not_found":
        raise HTTPException(
            status_code=404,
            detail="Notification not found",
        )

    return NotificationRetryResponse(**result)
