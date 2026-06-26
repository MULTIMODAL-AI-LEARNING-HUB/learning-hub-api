from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MaterialProgressBase(BaseModel):
    pass


class MaterialProgressUpdate(BaseModel):
    completion_percent: int = Field(ge=0, le=100)
    last_position: dict | None = None


class MaterialProgressResponse(BaseModel):
    id: UUID
    enrollment_id: UUID
    material_id: UUID
    completion_percent: int
    completed: bool
    last_position: dict | None = None
    completed_at: datetime | None = None

    class Config:
        from_attributes = True


class EnrollmentProgressResponse(BaseModel):
    enrollment_id: UUID
    course_id: UUID
    total_materials: int
    completed_materials: int
    completion_percent: float
    materials: list[MaterialProgressResponse]