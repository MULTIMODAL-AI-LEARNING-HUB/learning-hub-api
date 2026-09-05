from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, ConfigDict


class AdminUserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str | None = Field(default=None, max_length=255)
    role: str = Field(default="student", pattern="^(admin|lecturer|student)$")


class AdminUserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, pattern="^(admin|lecturer|student)$")
    is_active: bool | None = None


class AdminUserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str | None = None
    role: str
    is_active: bool
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AdminUserListResponse(BaseModel):
    items: list[AdminUserResponse]
    total: int
    page: int
    page_size: int


class AdminCourseResponse(BaseModel):
    id: UUID
    lecturer_id: UUID
    category_id: UUID | None
    title: str
    description: str | None
    thumbnail_url: str | None
    price_vnd: int
    status: str
    level: str
    language: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    lecturer_name: str | None = None
    category_name: str | None = None
    enrollment_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class AdminCourseListResponse(BaseModel):
    items: list[AdminCourseResponse]
    total: int
    page: int
    page_size: int


class AiApiKeyCreate(BaseModel):
    api_key: str = Field(..., min_length=10)
    key_name: str = Field(..., min_length=1, max_length=100)
    provider: str = Field(default="gemini", max_length=50)


class AiApiKeyResponse(BaseModel):
    id: UUID
    provider: str
    key_name: str
    masked_key: str
    is_active: bool
    usage_count: int
    last_used_at: datetime | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AiApiKeyListResponse(BaseModel):
    items: list[AiApiKeyResponse]
    total: int