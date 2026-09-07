"""Payments API endpoints."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import RedisCache
from app.core.config import settings
from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.user import User
from app.repositories.course_repo import CourseRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.payment_repo import PaymentRepository
from app.services.enrollment_service import EnrollmentService
from app.services.payment_gateway_service import verify_mock_payment_token

router = APIRouter()
logger = logging.getLogger(__name__)


class MockPaymentConfirmRequest(BaseModel):
    transaction_id: str = Field(..., description="Transaction ID of the payment")
    action: str = Field(..., description="Action: 'success', 'cancel', or 'fail'")
    mock_token: str = Field(..., description="HMAC token for verification")


class PaymentStatusResponse(BaseModel):
    status: str
    enrollment_id: str | None = None
    transaction_id: str | None = None
    amount_vnd: int | None = None


class MockPaymentConfirmResponse(BaseModel):
    success: bool
    status: str
    course_id: str | None = None


@router.get("/{payment_identifier}/status", response_model=PaymentStatusResponse)
async def get_payment_status(
    payment_identifier: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaymentStatusResponse:
    """Get payment status by transaction ID or payment UUID."""
    payment_repo = PaymentRepository(db)

    # First attempt lookup by transaction_id
    payment = await payment_repo.get_by_transaction_id(payment_identifier)

    # Fallback lookup by UUID if identifier looks like UUID
    if not payment:
        try:
            payment_uuid = UUID(payment_identifier)
            payment = await payment_repo.get_by_id(payment_uuid)
        except (ValueError, TypeError):
            pass

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    # Only student owner or admin can view status
    if payment.student_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this payment",
        )

    # Return normalized status ('paid' for 'completed' for frontend compatibility)
    normalized_status = "paid" if payment.payment_status == "completed" else payment.payment_status

    return PaymentStatusResponse(
        status=normalized_status,
        enrollment_id=str(payment.enrollment_id) if payment.enrollment_id else None,
        transaction_id=payment.transaction_id,
        amount_vnd=payment.amount_vnd,
    )


@router.post("/mock/confirm", response_model=MockPaymentConfirmResponse)
async def confirm_mock_payment(
    payload: MockPaymentConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MockPaymentConfirmResponse:
    """Confirm or simulate failure/cancellation of a mock payment transaction."""
    if not settings.ENABLE_MOCK_PAYMENT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mock payment simulator is disabled",
        )

    payment_repo = PaymentRepository(db)
    payment = await payment_repo.get_by_transaction_id(payload.transaction_id)
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment transaction not found",
        )

    if payment.student_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to confirm this payment",
        )

    # Validate HMAC signature
    is_valid_token = verify_mock_payment_token(
        transaction_id=payment.transaction_id,
        amount=payment.amount_vnd,
        token=payload.mock_token,
    )
    if not is_valid_token:
        logger.warning("Invalid mock payment token for txn %s", payload.transaction_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid mock payment token signature",
        )

    enrollment_repo = EnrollmentRepository(db)
    course_repo = CourseRepository(db)
    enrollment_service = EnrollmentService(enrollment_repo, payment_repo, course_repo)

    if payload.action == "success":
        target_status = "completed"
    else:
        target_status = "failed"

    enrollment, updated_payment = await enrollment_service.confirm_payment(
        transaction_id=payload.transaction_id,
        payment_status=target_status,
    )

    await RedisCache().delete(f"cache:enrollments:{current_user.id}")

    return MockPaymentConfirmResponse(
        success=(target_status == "completed"),
        status=target_status,
        course_id=str(payment.course_id),
    )
