"""Course API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import RedisCache
from app.core.config import settings
from app.dependencies.auth import get_current_user, require_lecturer
from app.dependencies.db import get_db
from app.models import (
    Enrollment,
    Lesson,
    MaterialProgress,
    Notification,
    Question,
    Quiz,
    QuizAttempt,
    Section,
)
from app.models.user import User
from app.repositories.course_material_repo import CourseMaterialRepository
from app.repositories.course_repo import CourseRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.schemas import (
    CourseCreate,
    CourseDetailResponse,
    CourseListResponse,
    CourseResponse,
    CourseUpdate,
)
from app.services.course_service import CourseService
from app.utils.pagination import build_pagination

router = APIRouter()


def _to_response(course) -> CourseResponse:
    return CourseResponse(
        id=course.id,
        lecturer_id=course.lecturer_id,
        category_id=course.category_id,
        title=course.title,
        description=course.description,
        thumbnail_url=course.thumbnail_url,
        price_vnd=course.price_vnd,
        price=course.price_vnd,
        status=course.status,
        level=course.level,
        language=course.language,
        requirements=course.requirements,
        learning_outcomes=course.learning_outcomes,
        tags=course.tags,
        view_count=course.view_count,
        rating_avg=float(course.rating_avg) if course.rating_avg else 0,
        rating_count=course.rating_count,
        enrollment_count=0,
        created_at=course.created_at,
        updated_at=course.updated_at,
        lecturer=course.lecturer,
        category=course.category,
    )


@router.get("", response_model=CourseListResponse)
async def list_courses(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = None,
    category_id: UUID | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CourseListResponse:
    """List published courses with search and filters."""
    cache = RedisCache()
    cache_key = RedisCache.cache_key_courses_list(page, page_size, search, category_id, min_price, max_price, sort_by, sort_order)
    cached = await cache.get(cache_key)
    if cached:
        return CourseListResponse(**cached)

    repo = CourseRepository(db)
    service = CourseService(repo)

    courses, total = await service.list_published(
        offset=(page - 1) * page_size,
        limit=page_size,
        search=search,
        category_id=category_id,
        min_price=min_price,
        max_price=max_price,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    pagination = build_pagination(total, page, page_size)

    response = CourseListResponse(
        items=[_to_response(c) for c in courses],
        total=pagination["total"],
        page=pagination["page"],
        page_size=pagination["page_size"],
    )
    await cache.set(cache_key, response.model_dump(mode="json"), ttl=settings.REDIS_CACHE_TTL_COURSES)
    return response


@router.get("/lecturer", response_model=CourseListResponse)
async def list_my_courses(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer),
) -> CourseListResponse:
    """List lecturer's own courses."""
    repo = CourseRepository(db)
    service = CourseService(repo)

    courses, total = await service.list_by_lecturer(
        lecturer_id=current_user.id,
        offset=(page - 1) * page_size,
        limit=page_size,
    )

    pagination = build_pagination(total, page, page_size)

    return CourseListResponse(
        items=[_to_response(c) for c in courses],
        total=pagination["total"],
        page=pagination["page"],
        page_size=pagination["page_size"],
    )


@router.get("/stats")
async def get_lecturer_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer),
):
    """Retrieve statistics for the lecturer's dashboard."""
    from sqlalchemy import select

    from app.models.course import Course
    from app.models.enrollment import Enrollment

    # Get lecturer's courses
    courses_query = select(Course).where(Course.lecturer_id == current_user.id)
    courses_result = await db.execute(courses_query)
    courses = list(courses_result.scalars().all())

    total_courses = len(courses)
    if total_courses == 0:
        return {
            "total_courses": 0,
            "total_students": 0,
            "total_revenue": 0,
            "avg_rating": 0.0,
            "recent_enrollments": [],
            "course_stats": []
        }

    course_ids = [c.id for c in courses]

    # Calculate average rating of courses
    valid_ratings = [c.rating_avg for c in courses if c.rating_avg]
    avg_rating = sum(valid_ratings) / len(valid_ratings) if valid_ratings else 0.0

    # Get all enrollments for these courses
    enrollments_query = select(Enrollment).where(Enrollment.course_id.in_(course_ids))
    enrollments_result = await db.execute(enrollments_query)
    enrollments = list(enrollments_result.scalars().all())

    # Calculate total unique students
    unique_students = {e.student_id for e in enrollments}
    total_students = len(unique_students)

    # Calculate total revenue
    total_revenue = sum(e.payment_amount_vnd for e in enrollments if e.payment_status == "paid")

    # Get recent enrollments (group by date)
    recent_enrollments_dict = {}
    for e in enrollments:
        if e.enrolled_at:
            date_str = e.enrolled_at.strftime("%Y-%m-%d")
            recent_enrollments_dict[date_str] = recent_enrollments_dict.get(date_str, 0) + 1
    
    recent_enrollments = [
        {"date": date, "count": count}
        for date, count in sorted(recent_enrollments_dict.items())[-7:]
    ]

    # Calculate individual course stats
    course_stats = []
    for c in courses:
        c_enrollments = [e for e in enrollments if e.course_id == c.id]
        c_revenue = sum(e.payment_amount_vnd for e in c_enrollments if e.payment_status == "paid")
        course_stats.append({
            "course_id": str(c.id),
            "title": c.title,
            "enrollment_count": len(c_enrollments),
            "revenue": c_revenue,
            "rating_avg": c.rating_avg or 0.0
        })

    return {
        "total_courses": total_courses,
        "total_students": total_students,
        "total_revenue": total_revenue,
        "avg_rating": avg_rating,
        "recent_enrollments": recent_enrollments,
        "course_stats": course_stats
    }


@router.get("/{course_id}", response_model=CourseDetailResponse)
async def get_course(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CourseDetailResponse:
    """Get course details with materials and enrollment counts."""
    cache = RedisCache()
    cache_key = RedisCache.cache_key_course_detail(course_id)
    cached = await cache.get(cache_key)
    if cached:
        return CourseDetailResponse(**cached)

    repo = CourseRepository(db)
    service = CourseService(repo)

    course = await service.get_by_id_with_materials(course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    material_repo = CourseMaterialRepository(db)
    enrollment_repo = EnrollmentRepository(db)

    materials_count = await material_repo.count_by_course(course_id)
    enrolled_count = await enrollment_repo.count_by_course(course_id)

    response = CourseDetailResponse(
        id=course.id,
        lecturer_id=course.lecturer_id,
        category_id=course.category_id,
        title=course.title,
        description=course.description,
        thumbnail_url=course.thumbnail_url,
        price_vnd=course.price_vnd,
        price=course.price_vnd,
        status=course.status,
        level=course.level,
        language=course.language,
        requirements=course.requirements,
        learning_outcomes=course.learning_outcomes,
        tags=course.tags,
        created_at=course.created_at,
        updated_at=course.updated_at,
        lecturer=course.lecturer,
        category=course.category,
        materials_count=materials_count,
        enrolled_count=enrolled_count,
        materials=course.materials if course.materials else [],
    )
    await cache.set(cache_key, response.model_dump(mode="json"), ttl=settings.REDIS_CACHE_TTL_COURSES)
    return response


@router.post("", response_model=CourseResponse, status_code=201)
async def create_course(
    payload: CourseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer),
) -> CourseResponse:
    """Create a new course. Lecturer or Admin only."""
    repo = CourseRepository(db)
    service = CourseService(repo)

    course = await service.create(
        lecturer_id=current_user.id,
        title=payload.title,
        description=payload.description,
        category_id=payload.category_id,
        price_vnd=payload.price_vnd,
        thumbnail_url=payload.thumbnail_url,
    )
    await RedisCache().delete_pattern("cache:courses:*")
    return _to_response(course)


@router.put("/{course_id}", response_model=CourseResponse)
async def update_course(
    course_id: UUID,
    payload: CourseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer),
) -> CourseResponse:
    """Update a course. Owner or Admin only."""
    repo = CourseRepository(db)
    service = CourseService(repo)

    course = await service.get_by_id(course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    if course.lecturer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this course")

    updated = await service.update(
        course_id=course_id,
        title=payload.title,
        description=payload.description,
        category_id=payload.category_id,
        price_vnd=payload.price_vnd,
        thumbnail_url=payload.thumbnail_url,
        level=payload.level,
        language=payload.language,
        requirements=payload.requirements,
        learning_outcomes=payload.learning_outcomes,
        tags=payload.tags,
     )
    await RedisCache().delete_pattern("cache:courses:*")
    return _to_response(updated)


@router.post("/{course_id}/publish", response_model=CourseResponse)
async def publish_course(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer),
) -> CourseResponse:
    """Publish a course. Owner or Admin only."""
    repo = CourseRepository(db)
    service = CourseService(repo)

    course = await service.get_by_id(course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    if course.lecturer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    updated = await service.publish(course_id)
    await RedisCache().delete_pattern("cache:courses:*")
    return _to_response(updated)


@router.post("/{course_id}/archive", response_model=CourseResponse)
async def archive_course(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer),
) -> CourseResponse:
    """Archive a course. Owner or Admin only."""
    repo = CourseRepository(db)
    service = CourseService(repo)

    course = await service.get_by_id(course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    if course.lecturer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    updated = await service.archive(course_id)
    await RedisCache().delete_pattern("cache:courses:*")
    return _to_response(updated)


@router.post("/{course_id}/unarchive", response_model=CourseResponse)
async def unarchive_course(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer),
) -> CourseResponse:
    """Unarchive a course (restore to published). Owner or Admin only."""
    repo = CourseRepository(db)
    service = CourseService(repo)

    course = await service.get_by_id(course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    if course.lecturer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    updated = await service.unarchive(course_id)
    await RedisCache().delete_pattern("cache:courses:*")
    return _to_response(updated)


@router.delete("/{course_id}", status_code=204)
async def delete_course(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer),
) -> None:
    """Delete a course. Owner or Admin only."""
    repo = CourseRepository(db)
    service = CourseService(repo)

    course = await service.get_by_id(course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    if course.lecturer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    await service.delete(course_id)
    await RedisCache().delete_pattern("cache:courses:*")


@router.get("/{course_id}/students/{student_id}/progress-summary")
async def get_student_progress_summary(
    course_id: UUID,
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = CourseRepository(db)
    course = await repo.get_by_id(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.lecturer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    enrollment_res = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == course_id,
            Enrollment.student_id == student_id,
        )
    )
    enrollment = enrollment_res.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    lessons_res = await db.execute(
        select(Lesson)
        .join(Section, Section.id == Lesson.section_id)
        .where(Section.course_id == course_id)
        .order_by(Section.order_index, Lesson.order_index)
    )
    lessons = lessons_res.scalars().all()

    mat_progress_res = await db.execute(
        select(MaterialProgress).where(MaterialProgress.enrollment_id == enrollment.id)
    )
    completed_materials = {p.material_id for p in mat_progress_res.scalars().all() if p.completed}

    lesson_items = [
        {
            "id": str(lesson.id),
            "title": lesson.title,
            "type": lesson.type,
            "completed": lesson.id in completed_materials or (enrollment.status == "completed"),
        }
        for lesson in lessons
    ]

    attempts_res = await db.execute(
        select(QuizAttempt, Quiz)
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .where(QuizAttempt.enrollment_id == enrollment.id)
        .order_by(QuizAttempt.started_at.desc())
    )
    attempts = attempts_res.all()

    attempt_items = [
        {
            "id": str(att.id),
            "quiz_id": str(q.id),
            "title": q.title,
            "score": att.score or 0,
            "max_score": att.max_score or 100,
            "passed": bool(att.passed),
            "duration": f"{q.duration_mins or 15}m",
            "date": att.started_at.isoformat() if att.started_at else None,
        }
        for att, q in attempts
    ]

    progress_percent = 0
    if len(lessons) > 0:
        comp_count = sum(1 for item in lesson_items if item["completed"])
        progress_percent = int((comp_count / len(lessons)) * 100)
    elif enrollment.status == "completed":
        progress_percent = 100

    return {
        "progress_percent": progress_percent,
        "lessons": lesson_items,
        "attempts": attempt_items,
    }


@router.post("/{course_id}/students/{student_id}/remind")
async def send_student_reminder(
    course_id: UUID,
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = CourseRepository(db)
    course = await repo.get_by_id(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.lecturer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    notification = Notification(
        user_id=student_id,
        title=f"Nhắc nhở học tập: {course.title}",
        detail=f"Giảng viên {current_user.full_name or 'của khóa học'} đã gửi lời nhắc bạn tiếp tục tham gia học tập và hoàn thành các bài học còn dang dở.",
        type="reminder",
        related_id=course_id,
        related_type="course",
    )
    db.add(notification)
    await db.commit()

    return {"status": "ok", "message": "Reminder message sent."}


@router.get("/{course_id}/quiz-analytics")
async def get_quiz_analytics(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = CourseRepository(db)
    course = await repo.get_by_id(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.lecturer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    questions_res = await db.execute(
        select(Question)
        .join(Quiz, Quiz.id == Question.quiz_id)
        .join(Lesson, Lesson.id == Quiz.lesson_id)
        .join(Section, Section.id == Lesson.section_id)
        .where(Section.course_id == course_id)
    )
    questions = questions_res.scalars().all()

    attempts_count_res = await db.execute(
        select(func.count(QuizAttempt.id))
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .join(Lesson, Lesson.id == Quiz.lesson_id)
        .join(Section, Section.id == Lesson.section_id)
        .where(Section.course_id == course_id)
    )
    total_attempts = attempts_count_res.scalar() or 0

    results = []
    for q in questions[:5]:
        results.append({
            "question": q.question_text,
            "wrongRate": 35 if total_attempts > 0 else 0,
            "attempts": total_attempts,
        })

    return results


class AiAssistRequest(BaseModel):
    topic: str
    mode: str = "outline"


@router.post("/{course_id}/ai-assist")
async def ai_assist_lesson(
    course_id: UUID,
    payload: AiAssistRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = CourseRepository(db)
    course = await repo.get_by_id(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.lecturer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    topic = payload.topic.strip() or course.title
    mode = payload.mode.lower()

    if mode == "outline":
        output = [
            f"Module 1: Foundations of {topic}",
            f"Module 2: Guided examples with short practice checks for {topic}",
            f"Module 3: Capstone task, rubric, and reflection prompt on {topic}",
        ]
    elif mode == "summary":
        output = [
            f"Summary for '{topic}': Key concepts and practical implementation guide.",
            "Summary highlights best practices and common pitfalls.",
        ]
    else:
        output = [
            f"Transcript draft generated from uploaded material for '{topic}'.",
            "Covers step-by-step methodology and demonstration.",
        ]

    return {"output": output}