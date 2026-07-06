from fastapi import APIRouter, Depends, HTTPException, Query, status
from uuid import UUID
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.models import Course, Enrollment, Review
from app.schemas.course_content import ReviewCreate, ReviewUpdate, ReviewResponse, LecturerReply
from app.dependencies.auth import get_current_user, require_lecturer, require_active_user
from app.models.user import User

router = APIRouter(prefix="/{course_id}/reviews", tags=["Reviews"])


async def get_course_or_404(db: AsyncSession, course_id: UUID) -> Course:
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


async def verify_course_ownership(course: Course, current_user: User) -> None:
    if course.lecturer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")


@router.get("")
async def list_reviews(
    course_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    course = await get_course_or_404(db, course_id)

    # Count total for pagination
    count_result = await db.execute(
        select(func.count(Review.id))
        .join(Enrollment)
        .where(Enrollment.course_id == course_id)
    )
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(
        select(Review)
        .join(Enrollment)
        .where(Enrollment.course_id == course_id)
        .order_by(Review.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    reviews = result.scalars().all()

    items = []
    for r in reviews:
        enrollment_result = await db.execute(select(Enrollment).where(Enrollment.id == r.enrollment_id))
        enrollment = enrollment_result.scalar_one_or_none()
        if enrollment:
            student_result = await db.execute(select(User).where(User.id == enrollment.student_id))
            student = student_result.scalar_one_or_none()
            items.append({
                "id": r.id,
                "enrollment_id": r.enrollment_id,
                "rating": r.rating,
                "comment": r.comment,
                "lecturer_reply": r.lecturer_reply,
                "replied_at": r.replied_at,
                "created_at": r.created_at,
                "student_name": student.full_name if student else None,
                "course_title": course.title
            })
    return {"items": items, "total": total}


@router.post("", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
async def create_review(
    course_id: UUID,
    review_data: ReviewCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user)
):
    course = await get_course_or_404(db, course_id)

    enrollment_result = await db.execute(
        select(Enrollment).where(
            Enrollment.student_id == current_user.id,
            Enrollment.course_id == course_id,
            Enrollment.status.in_(["active", "completed"])
        )
    )
    enrollment = enrollment_result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=403, detail="Must be enrolled to review")

    existing = await db.execute(
        select(Review).where(Review.enrollment_id == enrollment.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already reviewed this course")

    review = Review(
        enrollment_id=enrollment.id,
        rating=review_data.rating,
        comment=review_data.comment
    )
    db.add(review)

    total_result = await db.execute(
        select(Review)
        .join(Enrollment)
        .where(Enrollment.course_id == course_id)
    )
    all_reviews = total_result.scalars().all()
    total_reviews = len(all_reviews) + 1
    avg_rating = sum([r.rating for r in all_reviews]) / total_reviews if total_reviews > 0 else 0

    course.rating_count = total_reviews
    course.rating_avg = round(avg_rating, 1)

    await db.commit()
    await db.refresh(review)

    return {
        "id": review.id,
        "enrollment_id": review.enrollment_id,
        "rating": review.rating,
        "comment": review.comment,
        "lecturer_reply": review.lecturer_reply,
        "replied_at": review.replied_at,
        "created_at": review.created_at,
        "student_name": current_user.full_name,
        "course_title": course.title
    }


@router.get("/my-review", response_model=ReviewResponse)
async def get_my_review(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user)
):
    course = await get_course_or_404(db, course_id)

    enrollment_result = await db.execute(
        select(Enrollment).where(
            Enrollment.student_id == current_user.id,
            Enrollment.course_id == course_id
        )
    )
    enrollment = enrollment_result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Not enrolled")

    result = await db.execute(select(Review).where(Review.enrollment_id == enrollment.id))
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    return {
        "id": review.id,
        "enrollment_id": review.enrollment_id,
        "rating": review.rating,
        "comment": review.comment,
        "lecturer_reply": review.lecturer_reply,
        "replied_at": review.replied_at,
        "created_at": review.created_at,
        "student_name": current_user.full_name,
        "course_title": course.title
    }


@router.put("/my-review", response_model=ReviewResponse)
async def update_my_review(
    course_id: UUID,
    review_data: ReviewUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user)
):
    course = await get_course_or_404(db, course_id)

    enrollment_result = await db.execute(
        select(Enrollment).where(
            Enrollment.student_id == current_user.id,
            Enrollment.course_id == course_id
        )
    )
    enrollment = enrollment_result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Not enrolled")

    result = await db.execute(select(Review).where(Review.enrollment_id == enrollment.id))
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    for key, value in review_data.model_dump(exclude_unset=True).items():
        setattr(review, key, value)

    await db.commit()
    await db.refresh(review)

    return {
        "id": review.id,
        "enrollment_id": review.enrollment_id,
        "rating": review.rating,
        "comment": review.comment,
        "lecturer_reply": review.lecturer_reply,
        "replied_at": review.replied_at,
        "created_at": review.created_at,
        "student_name": current_user.full_name,
        "course_title": course.title
    }


@router.post("/{review_id}/reply", response_model=ReviewResponse)
async def lecturer_reply_review(
    course_id: UUID,
    review_id: UUID,
    reply_data: LecturerReply,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    course = await get_course_or_404(db, course_id)
    await verify_course_ownership(course, current_user)

    result = await db.execute(select(Review).where(Review.id == review_id))
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    review.lecturer_reply = reply_data.reply
    review.replied_at = datetime.now()

    await db.commit()
    await db.refresh(review)

    enrollment_result = await db.execute(select(Enrollment).where(Enrollment.id == review.enrollment_id))
    enrollment = enrollment_result.scalar_one_or_none()
    student = None
    if enrollment:
        student_result = await db.execute(select(User).where(User.id == enrollment.student_id))
        student = student_result.scalar_one_or_none()

    return {
        "id": review.id,
        "enrollment_id": review.enrollment_id,
        "rating": review.rating,
        "comment": review.comment,
        "lecturer_reply": review.lecturer_reply,
        "replied_at": review.replied_at,
        "created_at": review.created_at,
        "student_name": student.full_name if student else None,
        "course_title": course.title
    }