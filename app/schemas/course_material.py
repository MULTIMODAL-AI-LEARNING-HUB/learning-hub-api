from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CourseMaterialBase(BaseModel):
    file_name: str | None = None
    file_type: str
    external_url: str | None = None
    material_type: str = "lecture"


class CourseMaterialCreate(CourseMaterialBase):
    pass


class CourseMaterialUpdate(BaseModel):
    file_name: str | None = None
    material_type: str | None = None


class CourseMaterialResponse(BaseModel):
    id: UUID
    course_id: UUID
    lecturer_id: UUID
    file_name: str | None = None
    title: str | None = None
    file_type: str
    file_url: str | None = None
    file_size: int | None = None
    external_url: str | None = None
    status: str
    file_metadata: dict | None = None
    is_indexed: bool
    material_type: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CourseMaterialListResponse(BaseModel):
    items: list[CourseMaterialResponse]
    total: int