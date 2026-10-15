from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr

NotificationStatus = Literal["pending", "sending", "sent", "failed"]


class NotificationResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    notification_id: str
    employee_id: str
    recipient_email: EmailStr
    week_start: str
    week_end: str
    subject: str
    body: str
    status: NotificationStatus
    attempts: int = 0
    created_at: str
    sent_at: str | None = None
    last_error: str | None = None


class NotificationTriggerResponse(BaseModel):
    week_start: str
    week_end: str
    created: int
    sent: int
    failed: int
    skipped: int


class NotificationRetryResponse(BaseModel):
    notification_id: str
    status: str
    message: str | None = None
