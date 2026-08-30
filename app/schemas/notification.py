from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    detail: str | None = None
    type: str
    related_id: UUID | None = None
    related_type: str | None = None
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    unread_count: int
