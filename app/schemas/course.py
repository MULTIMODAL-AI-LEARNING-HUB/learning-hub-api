from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CourseBase(BaseModel):
    title: str = Field(max_length=255)
    description: str | None = None
    category_id: UUID | None = None
    price_vnd: int = Field(default=0, ge=0)
    thumbnail_url: str | None = None


class CourseCreate(CourseBase):
    pass


class CourseUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    category_id: UUID | None = None
    price_vnd: int | None = Field(default=None, ge=0)
    thumbnail_url: str | None = None


class LecturerResponse(BaseModel):
    id: UUID
    full_name: str | None = None
    avatar_url: str | None = None

    class Config:
        from_attributes = True


class CategoryBasicResponse(BaseModel):
    id: UUID
    name: str
    slug: str

    class Config:
        from_attributes = True


class CourseResponse(BaseModel):
    id: UUID
    lecturer_id: UUID
    category_id: UUID | None = None
    title: str
    description: str | None = None
    thumbnail_url: str | None = None
    price_vnd: int
    price: int
    status: str
    created_at: datetime
    updated_at: datetime
    lecturer: LecturerResponse | None = None
    category: CategoryBasicResponse | None = None

    class Config:
        from_attributes = True


class CourseListResponse(BaseModel):
    items: list[CourseResponse]
    total: int
    page: int
    page_size: int


class CourseDetailResponse(CourseResponse):
    materials_count: int = 0
    enrolled_count: int = 0

    class Config:
        from_attributes = True