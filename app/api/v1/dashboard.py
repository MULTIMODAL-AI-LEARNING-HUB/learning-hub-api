"""Dashboard API endpoints."""

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.course_content import Quiz, QuizAttempt
from app.models.course_material import CourseMaterial
from app.models.material_progress import MaterialProgress
from app.models.user import User
from app.repositories.course_material_repo import CourseMaterialRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.progress_repo import ProgressRepository
from app.schemas.dashboard import (
    DashboardActivity,
    DashboardCourseProgress,
    DashboardResponse,
    DashboardStats,
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

    # Collect student activities
    activities: list[DashboardActivity] = []
    enrollment_ids = [e.id for e in enrollments]

    if enrollment_ids:
        # 1. Quiz attempts
        quiz_res = await db.execute(
            select(QuizAttempt, Quiz)
            .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
            .where(QuizAttempt.enrollment_id.in_(enrollment_ids))
            .order_by(QuizAttempt.started_at.desc())
            .limit(10)
        )
        for attempt, quiz in quiz_res.all():
            activities.append(
                DashboardActivity(
                    id=attempt.id,
                    activity_type="quiz",
                    title=f"Làm trắc nghiệm: {quiz.title}",
                    score=int(attempt.score) if attempt.score is not None else None,
                    created_at=attempt.completed_at or attempt.started_at,
                )
            )

        # 2. Material progress
        prog_res = await db.execute(
            select(MaterialProgress, CourseMaterial)
            .join(CourseMaterial, CourseMaterial.id == MaterialProgress.material_id)
            .where(
                MaterialProgress.enrollment_id.in_(enrollment_ids),
                MaterialProgress.completion_percent > 0,
            )
            .order_by(MaterialProgress.updated_at.desc())
            .limit(10)
        )
        for prog, mat in prog_res.all():
            activities.append(
                DashboardActivity(
                    id=prog.id,
                    activity_type="lesson",
                    title=f"Học bài: {mat.file_name or 'Bài học'}",
                    score=None,
                    created_at=prog.completed_at or prog.updated_at or prog.created_at,
                )
            )

        # 3. Course enrollments
        for enrollment in enrollments:
            if enrollment.course:
                activities.append(
                    DashboardActivity(
                        id=enrollment.id,
                        activity_type="course",
                        title=f"Tham gia khóa học: {enrollment.course.title}",
                        score=None,
                        created_at=enrollment.enrolled_at,
                    )
                )

    activities.sort(key=lambda a: a.created_at, reverse=True)
    recent_activity = activities[:10]

    # Calculate streak days and daily goal percent
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today_date = now.date()
    activity_dates = {a.created_at.date() for a in activities}
    today_completed_count = sum(1 for a in activities if a.created_at.date() == today_date)

    streak_days = 0
    check_date = today_date
    if check_date in activity_dates:
        while check_date in activity_dates:
            streak_days += 1
            check_date -= timedelta(days=1)
    elif (check_date - timedelta(days=1)) in activity_dates:
        check_date -= timedelta(days=1)
        while check_date in activity_dates:
            streak_days += 1
            check_date -= timedelta(days=1)
    else:
        streak_days = 1 if len(enrollments) > 0 else 0

    if today_completed_count >= 2:
        daily_goal_percent = 100
    elif today_completed_count == 1:
        daily_goal_percent = 50
    else:
        daily_goal_percent = 25 if total_completed > 0 else (10 if len(enrollments) > 0 else 0)

    stats = DashboardStats(
        total_enrolled=len(enrollments),
        total_materials=total_materials,
        total_completed=total_completed,
        avg_progress=round(avg_progress, 1),
        streak_days=streak_days,
        daily_goal_percent=daily_goal_percent,
    )

    return DashboardResponse(
        courses=courses,
        stats=stats,
        recent_activity=recent_activity,
    )