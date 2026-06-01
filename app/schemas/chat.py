from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ChatSessionCreateRequest(BaseModel):
    document_id: UUID | None = None
    title: str | None = Field(default=None, max_length=255)


class ChatSessionResponse(BaseModel):
    id: UUID
    title: str | None = None
    document_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class ChatSessionListItem(BaseModel):
    id: UUID
    title: str | None = None
    document_id: UUID | None = None
    updated_at: datetime
    last_message: str | None = None


class ChatSessionListResponse(BaseModel):
    items: list[ChatSessionListItem]
    total: int
    page: int
    page_size: int


class ChatAskRequest(BaseModel):
    session_id: UUID
    query: str
    document_ids: list[UUID] | None = None


class ChatMessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    citations: list[dict] | None = None
    created_at: datetime


class ChatMessagesResponse(BaseModel):
    items: list[ChatMessageResponse]
    total: int
    page: int
    page_size: int
