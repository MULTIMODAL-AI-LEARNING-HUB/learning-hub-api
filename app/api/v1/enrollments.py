"""Enrollment API endpoints."""

import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.user import User
from app.models.enrollment import Enrollment
from app.repositories.course_repo import CourseRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.payment_repo import PaymentRepository
from app.schemas import (
    EnrollmentListResponse,
    EnrollmentResponse,
    EnrollmentWithCourseResponse,
    PaymentIntentRequest,
    PaymentIntentResponse,
    PaymentConfirmRequest,
)
from app.services.course_service import CourseService
from app.services.enrollment_service import EnrollmentService
from app.services.payment_gateway_service import get_vnpay_service, get_momo_service
from app.core.cache import RedisCache
from app.core.config import settings

router = APIRouter(tags=["enrollments"])


def _to_response(enrollment: Enrollment) -> EnrollmentResponse:
    return EnrollmentResponse(
        id=enrollment.id,
        student_id=enrollment.student_id,
        course_id=enrollment.course_id,
        payment_amount_vnd=enrollment.payment_amount_vnd,
        payment_status=enrollment.payment_status,
        payment_method=enrollment.payment_method,
        transaction_id=enrollment.transaction_id,
        status=enrollment.status,
        enrolled_at=enrollment.enrolled_at,
        completed_at=enrollment.completed_at,
    )


def _to_enrollment_with_course(enrollment: Enrollment) -> EnrollmentWithCourseResponse:
    return EnrollmentWithCourseResponse(
        id=enrollment.id,
        student_id=enrollment.student_id,
        course_id=enrollment.course_id,
        payment_amount_vnd=enrollment.payment_amount_vnd,
        payment_status=enrollment.payment_status,
        payment_method=enrollment.payment_method,
        transaction_id=enrollment.transaction_id,
        status=enrollment.status,
        enrolled_at=enrollment.enrolled_at,
        completed_at=enrollment.completed_at,
        course_title=enrollment.course.title if enrollment.course else None,
        course_thumbnail=enrollment.course.thumbnail_url if enrollment.course else None,
        lecturer_name=enrollment.course.lecturer.full_name if enrollment.course and enrollment.course.lecturer else None,
    )


@router.post("/courses/{course_id}/enroll/payment-intent", response_model=PaymentIntentResponse)
async def create_payment_intent(
    request: Request,
    course_id: UUID,
    payload: PaymentIntentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaymentIntentResponse:
    """Create a payment intent for course enrollment."""
    course_repo = CourseRepository(db)
    course_service = CourseService(course_repo)

    course = await course_service.get_by_id(course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    if course.status != "published":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Course is not available for enrollment")

    enrollment_repo = EnrollmentRepository(db)
    existing = await enrollment_repo.get_active_enrollment(current_user.id, course_id)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already enrolled in this course")

    transaction_id = f"{payload.payment_method}_{uuid.uuid4()}"
    client_host = request.client.host if request.client else "127.0.0.1"

    if course.price_vnd == 0:
        enrollment_service = EnrollmentService(enrollment_repo, PaymentRepository(db), course_repo)
        await enrollment_service.create_enrollment_with_payment(
            student_id=current_user.id,
            course_id=course_id,
            payment_method=payload.payment_method,
            transaction_id=transaction_id,
            amount_vnd=0,
        )
        await enrollment_service.confirm_payment(transaction_id, "completed")
        await RedisCache().delete(f"cache:enrollments:{current_user.id}")
        return PaymentIntentResponse(
            payment_url="",
            transaction_id=transaction_id,
            amount_vnd=0,
        )

    order_info = f"Enrollment for course: {course.title}"

    if payload.payment_method == "vnpay":
        vnpay = get_vnpay_service()
        payment_url = vnpay.create_payment_url(
            amount=course.price_vnd,
            transaction_id=transaction_id,
            order_info=order_info,
            ip_address=client_host,
        )
    elif payload.payment_method == "momo":
        momo = get_momo_service()
        payment_url = momo.create_payment_url(
            amount=course.price_vnd,
            transaction_id=transaction_id,
            order_info=order_info,
            ip_address=client_host,
        )
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payment method")

    enrollment_service = EnrollmentService(enrollment_repo, PaymentRepository(db), course_repo)
    await enrollment_service.create_enrollment_with_payment(
        student_id=current_user.id,
        course_id=course_id,
        payment_method=payload.payment_method,
        transaction_id=transaction_id,
        amount_vnd=course.price_vnd,
    )

    return PaymentIntentResponse(
        payment_url=payment_url,
        transaction_id=transaction_id,
        amount_vnd=course.price_vnd,
    )


@router.post("/courses/{course_id}/enroll/confirm", response_model=EnrollmentResponse)
async def confirm_payment(
    course_id: UUID,
    payload: PaymentConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EnrollmentResponse:
    """Confirm payment and activate enrollment."""
    course_repo = CourseRepository(db)
    enrollment_repo = EnrollmentRepository(db)
    payment_repo = PaymentRepository(db)

    enrollment_service = EnrollmentService(enrollment_repo, payment_repo, course_repo)

    payment = await payment_repo.get_by_transaction_id(payload.transaction_id)
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    if payment.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    payment_status = "completed"
    if payload.payment_data:
        response_code = payload.payment_data.get("vnp_ResponseCode") or payload.payment_data.get("resultCode")
        if response_code != "0" and str(response_code) != "0":
            payment_status = "failed"

    enrollment, _ = await enrollment_service.confirm_payment(payload.transaction_id, payment_status)

    if not enrollment:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment confirmation failed")

    await RedisCache().delete(f"cache:enrollments:{current_user.id}")
    return _to_response(enrollment)


@router.get("/courses/{course_id}/enrollment-status")
async def check_enrollment_status(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Check if current user is enrolled in a course."""
    enrollment_repo = EnrollmentRepository(db)
    enrollment = await enrollment_repo.get_active_enrollment(current_user.id, course_id)

    return {
        "is_enrolled": enrollment is not None,
        "enrollment_id": enrollment.id if enrollment else None,
        "status": enrollment.status if enrollment else None,
    }


@router.get("/my-enrollments", response_model=EnrollmentListResponse)
async def list_my_enrollments(
    status_filter: str | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EnrollmentListResponse:
    """List current user's enrollments."""
    cache = RedisCache()
    cache_key = RedisCache.cache_key_enrollments(current_user.id)
    if not status_filter:
        cached = await cache.get(cache_key)
        if cached:
            return EnrollmentListResponse(**cached)

    enrollment_repo = EnrollmentRepository(db)
    enrollments = await enrollment_repo.list_by_student(current_user.id, status_filter)

    response = EnrollmentListResponse(
        items=[_to_enrollment_with_course(e) for e in enrollments],
        total=len(enrollments),
    )
    if not status_filter:
        await cache.set(cache_key, response.model_dump(mode="json"), ttl=settings.REDIS_CACHE_TTL_ENROLLMENTS)
    return response


@router.get("/courses/{course_id}/enrolled-students", response_model=EnrollmentListResponse)
async def list_enrolled_students(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EnrollmentListResponse:
    """List students enrolled in a course. Owner or Admin only."""
    course_repo = CourseRepository(db)
    course_service = CourseService(course_repo)

    course = await course_service.get_by_id(course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    if course.lecturer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    enrollment_repo = EnrollmentRepository(db)
    enrollments = await enrollment_repo.list_by_course(course_id)

    return EnrollmentListResponse(
        items=[_to_enrollment_with_course(e) for e in enrollments],
        total=len(enrollments),
    )