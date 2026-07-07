from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class AdminUserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12)
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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


class AdminCourseListResponse(BaseModel):
    items: list[AdminCourseResponse]
    total: int
    page: int
    page_size: int