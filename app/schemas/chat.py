from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ChatSessionCreateRequest(BaseModel):
    course_id: UUID | None = None
    lesson_id: UUID | None = None
    title: str | None = Field(default=None, max_length=255)
    context_type: str = "general"


class ChatSessionResponse(BaseModel):
    id: UUID
    course_id: UUID | None = None
    lesson_id: UUID | None = None
    title: str | None = None
    context_type: str
    created_at: datetime
    updated_at: datetime


class ChatSessionListItem(BaseModel):
    id: UUID
    course_id: UUID | None = None
    lesson_id: UUID | None = None
    title: str | None = None
    context_type: str
    updated_at: datetime
    last_message: str | None = None


class ChatSessionListResponse(BaseModel):
    items: list[ChatSessionListItem]
    total: int
    page: int
    page_size: int


class ChatAskRequest(BaseModel):
    session_id: UUID
    query: str = Field(min_length=1, max_length=5000)
    course_id: UUID | None = None
    lesson_id: UUID | None = None
    document_ids: list[UUID] | None = None


class ChatMessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    context_type: str
    citations: list[dict] | None = None
    created_at: datetime


class ChatMessagesResponse(BaseModel):
    items: list[ChatMessageResponse]
    total: int
    page: int
    page_size: int