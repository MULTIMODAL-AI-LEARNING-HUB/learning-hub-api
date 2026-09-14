from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class NoteCreate(BaseModel):
    course_id: UUID
    lesson_id: Optional[UUID] = None
    content: str = Field(..., min_length=1, max_length=5000)


class NoteUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


class NoteResponse(BaseModel):
    id: UUID
    user_id: UUID
    course_id: UUID
    lesson_id: Optional[UUID] = None
    content: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
