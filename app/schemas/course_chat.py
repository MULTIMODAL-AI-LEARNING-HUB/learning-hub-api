from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CourseChatMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class CourseChatMessageResponse(BaseModel):
    id: UUID
    course_id: UUID
    sender_id: UUID
    sender_name: str | None
    sender_role: str
    content: str
    created_at: datetime


class CourseChatMessagesResponse(BaseModel):
    items: list[CourseChatMessageResponse]
    total: int
