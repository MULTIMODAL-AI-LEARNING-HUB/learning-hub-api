"""Shared Course Authorization and Access Verification Dependencies.

Centralizes course ownership, enrollment checks, and lesson access logic
to prevent BOLA (Broken Object Level Authorization) and enforce DRY (Rule R10).
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.course import Course
from app.models.course_content import Lesson, Section
from app.models.enrollment import Enrollment
from app.models.user import User


async def get_course_or_404(db: AsyncSession, course_id: UUID) -> Course:
    """Retrieve course by ID or raise 404."""
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found"
        )
    return course


async def get_section_with_course(db: AsyncSession, section_id: UUID) -> tuple[Section, Course]:
    """Retrieve section and its parent course or raise 404."""
    result = await db.execute(
        select(Section)
        .where(Section.id == section_id)
        .options(selectinload(Section.course))
    )
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Section not found"
        )
    return section, section.course


async def get_lesson_with_course(db: AsyncSession, lesson_id: UUID) -> tuple[Lesson, Course]:
    """Retrieve lesson, its section, and its course or raise 404."""
    result = await db.execute(
        select(Lesson)
        .where(Lesson.id == lesson_id)
        .options(
            selectinload(Lesson.section).selectinload(Section.course)
        )
    )
    lesson = result.scalar_one_or_none()
    if not lesson or not lesson.section:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lesson not found"
        )
    return lesson, lesson.section.course


async def verify_course_ownership(course: Course, current_user: User) -> None:
    """Verify that current user is the course lecturer or an admin."""
    if current_user.role == "admin":
        return
    if course.lecturer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to manage this course"
        )


async def has_active_enrollment(db: AsyncSession, student_id: UUID, course_id: UUID) -> bool:
    """Check if student has an active or completed enrollment in the course."""
    result = await db.execute(
        select(Enrollment.id).where(
            Enrollment.student_id == student_id,
            Enrollment.course_id == course_id,
            Enrollment.status.in_(["active", "completed"])
        )
    )
    return result.scalar_one_or_none() is not None


async def verify_course_access(course: Course, current_user: User, db: AsyncSession) -> bool:
    """Check if current user has legitimate access to course materials.
    
    Access is granted if:
    1. User is admin
    2. User is the lecturer who owns the course
    3. Course is free (price_vnd == 0) and published
    4. User has an active/completed enrollment
    """
    if current_user.role == "admin":
        return True
    if course.lecturer_id == current_user.id:
        return True
    if course.price_vnd == 0 and course.status == "published":
        return True
    return await has_active_enrollment(db, current_user.id, course.id)


async def verify_lesson_access(
    lesson: Lesson,
    course: Course,
    current_user: User,
    db: AsyncSession
) -> None:
    """Enforce paywall/enrollment access control for a lesson.
    
    If lesson is preview, anyone logged in can view it.
    Otherwise, full course access is required.
    """
    if lesson.is_preview:
        return

    can_access = await verify_course_access(course, current_user, db)
    if not can_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Enrollment required to access this lesson content"
        )
