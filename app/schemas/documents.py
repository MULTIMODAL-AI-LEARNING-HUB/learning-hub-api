from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    id: UUID
    file_name: str
    file_type: str
    file_url: str
    file_size: int | None = None
    status: str
    metadata: dict | None = None
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int


class DocumentUploadResponse(BaseModel):
    id: UUID
    file_name: str
    file_type: str
    file_size: int | None = None
    status: str
    created_at: datetime


class DocumentUploadRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)
