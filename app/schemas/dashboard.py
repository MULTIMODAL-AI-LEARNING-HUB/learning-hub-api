from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DashboardCourseProgress(BaseModel):
    id: UUID
    course_id: UUID
    course_title: str
    course_thumbnail: str | None
    lecturer_name: str | None
    enrolled_at: datetime
    completion_percent: float
    total_materials: int
    completed_materials: int

    model_config = ConfigDict(from_attributes=True)


class DashboardStats(BaseModel):
    total_enrolled: int
    total_materials: int
    total_completed: int
    avg_progress: float


class DashboardActivity(BaseModel):
    id: UUID
    activity_type: str
    title: str
    score: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DashboardResponse(BaseModel):
    courses: list[DashboardCourseProgress]
    stats: DashboardStats
    recent_activity: list[DashboardActivity]