"""Dashboard API endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.user import User
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.course_material_repo import CourseMaterialRepository
from app.repositories.progress_repo import ProgressRepository
from app.schemas.dashboard import (
    DashboardResponse,
    DashboardCourseProgress,
    DashboardStats,
    DashboardActivity,
)
from app.services.progress_service import ProgressService

router = APIRouter(tags=["dashboard"])


@router.get("/my-dashboard", response_model=DashboardResponse)
async def get_my_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardResponse:
    """Get student dashboard data with enrollments, stats, and recent activity."""
    enrollment_repo = EnrollmentRepository(db)
    material_repo = CourseMaterialRepository(db)
    progress_repo = ProgressRepository(db)
    progress_service = ProgressService(progress_repo, material_repo, enrollment_repo)

    enrollments = await enrollment_repo.list_by_student(current_user.id, status=None)

    courses = []
    total_materials = 0
    total_completed = 0
    total_progress = 0.0

    for enrollment in enrollments:
        course = enrollment.course
        total_mat = await material_repo.count_by_course(course.id) if course else 0
        completed_mat = await progress_repo.count_completed(enrollment.id)
        completion_pct = await progress_service.get_course_completion_percent(enrollment.id)

        courses.append(DashboardCourseProgress(
            id=enrollment.id,
            course_id=enrollment.course_id,
            course_title=course.title if course else "Unknown",
            course_thumbnail=course.thumbnail_url if course else None,
            lecturer_name=course.lecturer.full_name if course and course.lecturer else None,
            enrolled_at=enrollment.enrolled_at,
            completion_percent=completion_pct,
            total_materials=total_mat,
            completed_materials=completed_mat,
        ))

        total_materials += total_mat
        total_completed += completed_mat
        total_progress += completion_pct

    num_courses = len(courses) if courses else 1
    avg_progress = total_progress / num_courses if courses else 0.0

    stats = DashboardStats(
        total_enrolled=len(enrollments),
        total_materials=total_materials,
        total_completed=total_completed,
        avg_progress=round(avg_progress, 1),
    )

    return DashboardResponse(
        courses=courses,
        stats=stats,
        recent_activity=[],
    )