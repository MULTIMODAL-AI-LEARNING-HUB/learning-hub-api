from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field
from typing import Optional


class AnnouncementCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)


class AnnouncementUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    content: Optional[str] = Field(None, min_length=1)


class AnnouncementResponse(BaseModel):
    id: UUID
    course_id: UUID
    lecturer_id: UUID
    lecturer_name: str | None = None
    title: str
    content: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
