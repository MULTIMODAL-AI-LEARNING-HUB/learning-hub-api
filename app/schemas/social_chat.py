from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SocialChatRoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    member_ids: list[UUID] = Field(default_factory=list)


class SocialChatMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class SocialChatUserResponse(BaseModel):
    id: UUID
    full_name: str | None
    email: str
    avatar_url: str | None
    role: str


class SocialChatMessageResponse(BaseModel):
    id: UUID
    room_id: UUID
    sender_id: UUID
    sender_name: str | None
    sender_avatar_url: str | None
    sender_role: str
    content: str
    created_at: datetime


class SocialChatRoomResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    kind: str
    member_count: int
    last_message: str | None
    updated_at: datetime


class SocialChatRoomsResponse(BaseModel):
    items: list[SocialChatRoomResponse]
    total: int


class SocialChatMessagesResponse(BaseModel):
    items: list[SocialChatMessageResponse]
    total: int
