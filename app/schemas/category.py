from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class CategoryBase(BaseModel):
    name: str = Field(max_length=100)
    slug: str = Field(max_length=100)
    description: str | None = None
    icon: str | None = None
    image_url: str | None = None
    parent_id: UUID | None = None


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    description: str | None = None
    icon: str | None = None
    image_url: str | None = None


class CategoryResponse(CategoryBase):
    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CategoryTreeResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    description: str | None = None
    icon: str | None = None
    image_url: str | None = None
    children: list["CategoryTreeResponse"] = []

    model_config = ConfigDict(from_attributes=True)