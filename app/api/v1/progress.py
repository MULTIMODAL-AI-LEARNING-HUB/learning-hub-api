"""Progress API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import func, select

from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.course_content import Lesson, Section
from app.models.user import User
from app.repositories.course_material_repo import CourseMaterialRepository
from app.repositories.course_repo import CourseRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.lesson_progress_repo import LessonProgressRepository
from app.repositories.progress_repo import ProgressRepository
from app.schemas import (
    EnrollmentProgressResponse,
    LessonProgressResponse,
    LessonProgressUpdate,
    MaterialProgressResponse,
    MaterialProgressUpdate,
)
from app.services.progress_service import ProgressService

router = APIRouter(tags=["progress"])


async def _count_lessons_by_course(db, course_id) -> int:
    result = await db.execute(
        select(func.count(Lesson.id))
        .join(Section, Section.id == Lesson.section_id)
        .where(Section.course_id == course_id)
    )
    return result.scalar() or 0


def _to_progress_response(material_progress) -> MaterialProgressResponse:
    return MaterialProgressResponse(
        id=material_progress.id,
        enrollment_id=material_progress.enrollment_id,
        material_id=material_progress.material_id,
        completion_percent=material_progress.completion_percent,
        completed=material_progress.completed,
        last_position=material_progress.last_position,
        completed_at=material_progress.completed_at,
    )


@router.get("/enrollments/{enrollment_id}/progress", response_model=EnrollmentProgressResponse)
async def get_enrollment_progress(
    enrollment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EnrollmentProgressResponse:
    """Get progress for an enrollment."""
    enrollment_repo = EnrollmentRepository(db)
    enrollment = await enrollment_repo.get_by_id(enrollment_id)

    if not enrollment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found")

    if current_user.role == "lecturer":
        course_repo = CourseRepository(db)
        course = await course_repo.get_by_id(enrollment.course_id)
        if not course or course.lecturer_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view progress for this course")
    elif current_user.role != "admin":
        if enrollment.student_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        if enrollment.status not in {"active", "completed"} or enrollment.payment_status != "paid":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active enrollment required")

    progress_repo = ProgressRepository(db)
    material_repo = CourseMaterialRepository(db)
    lesson_progress_repo = LessonProgressRepository(db)

    progress_service = ProgressService(progress_repo, material_repo, enrollment_repo)

    materials_progress = await progress_repo.get_enrollment_progress(enrollment_id)
    total_materials = await material_repo.count_by_course(enrollment.course_id)
    completed_materials = await progress_repo.count_completed(enrollment_id)
    total_lessons = await _count_lessons_by_course(db, enrollment.course_id)
    completed_lesson_ids = await lesson_progress_repo.get_completed_lesson_ids(enrollment_id)
    completed_lessons = len(completed_lesson_ids)
    completion_percent = await progress_service.get_course_completion_percent(
        enrollment_id, total_lessons, completed_lessons
    )

    return EnrollmentProgressResponse(
        enrollment_id=enrollment_id,
        course_id=enrollment.course_id,
        total_materials=total_materials,
        completed_materials=completed_materials,
        total_lessons=total_lessons,
        completed_lessons=completed_lessons,
        completed_lesson_ids=completed_lesson_ids,
        completion_percent=completion_percent,
        materials=[_to_progress_response(p) for p in materials_progress],
    )


@router.post(
    "/enrollments/{enrollment_id}/lessons/{lesson_id}/progress",
    response_model=LessonProgressResponse,
)
async def update_lesson_progress(
    enrollment_id: UUID,
    lesson_id: UUID,
    payload: LessonProgressUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LessonProgressResponse:
    """Mark a lesson as completed or uncompleted for the enrolled student."""
    enrollment_repo = EnrollmentRepository(db)
    enrollment = await enrollment_repo.get_by_id(enrollment_id)

    if not enrollment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found")

    if enrollment.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    if enrollment.status not in {"active", "completed"} or enrollment.payment_status != "paid":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Enrollment is not active")

    lesson_progress_repo = LessonProgressRepository(db)
    lp = await lesson_progress_repo.update_or_create(enrollment_id, lesson_id, payload.completed)

    # Recalculate overall progress and persist it
    material_repo = CourseMaterialRepository(db)
    progress_repo = ProgressRepository(db)
    progress_service = ProgressService(progress_repo, material_repo, enrollment_repo)
    total_lessons = await _count_lessons_by_course(db, enrollment.course_id)
    completed_lesson_ids = await lesson_progress_repo.get_completed_lesson_ids(enrollment_id)
    completed_lessons = len(completed_lesson_ids)
    await progress_service.get_course_completion_percent(enrollment_id, total_lessons, completed_lessons)

    return LessonProgressResponse.model_validate(lp)


@router.post("/enrollments/{enrollment_id}/materials/{material_id}/progress", response_model=MaterialProgressResponse)
async def update_material_progress(
    enrollment_id: UUID,
    material_id: UUID,
    payload: MaterialProgressUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MaterialProgressResponse:
    """Update progress for a specific material."""
    enrollment_repo = EnrollmentRepository(db)
    enrollment = await enrollment_repo.get_by_id(enrollment_id)

    if not enrollment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found")

    if enrollment.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    if enrollment.status not in {"active", "completed"} or enrollment.payment_status != "paid":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Enrollment is not active")

    material_repo = CourseMaterialRepository(db)
    progress_repo = ProgressRepository(db)

    progress_service = ProgressService(progress_repo, material_repo, enrollment_repo)

    material = await material_repo.get_by_id(material_id)
    if not material or material.course_id != enrollment.course_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found")

    progress = await progress_service.update_material_progress(
        enrollment_id=enrollment_id,
        material_id=material_id,
        completion_percent=payload.completion_percent,
        last_position=payload.last_position,
    )

    return _to_progress_response(progress)
