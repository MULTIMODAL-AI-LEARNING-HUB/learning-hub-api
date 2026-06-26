"""Payment webhook handlers."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.db import get_db
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.payment_repo import PaymentRepository
from app.repositories.course_repo import CourseRepository
from app.services.enrollment_service import EnrollmentService
from app.services.payment_gateway_service import get_vnpay_service, get_momo_service

router = APIRouter(prefix="/webhooks/payment", tags=["payment-webhooks"])
logger = logging.getLogger(__name__)


@router.post("/vnpay/return")
async def vnpay_return(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle VNPay return URL callback (user redirected back after payment)."""
    params = dict(request.query_params)

    vnpay = get_vnpay_service()
    result = vnpay.verify_return(params)

    if not result["is_valid"]:
        logger.warning(f"VNPay invalid signature for txn {result.get('transaction_id')}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    transaction_id = result["transaction_id"]
    enrollment_repo = EnrollmentRepository(db)
    payment_repo = PaymentRepository(db)
    course_repo = CourseRepository(db)
    enrollment_service = EnrollmentService(enrollment_repo, payment_repo, course_repo)

    payment_status = "completed" if result["is_success"] else "failed"
    enrollment, _ = await enrollment_service.confirm_payment(transaction_id, payment_status)

    if not enrollment:
        logger.error(f"VNPay: enrollment not found for txn {transaction_id}")

    return {
        "success": result["is_success"],
        "message": result["message"],
        "transaction_id": transaction_id,
    }


@router.post("/vnpay/ipn")
async def vnpay_ipn(
    request: Request,
    x_vnpay_checksum: str | None = Header(None, alias="X-VNPay-Checksum"),
    db: AsyncSession = Depends(get_db),
):
    """Handle VNPay IPN (Instant Payment Notification) - server-to-server callback."""
    params = await request.form()
    params = dict(params)

    vnpay = get_vnpay_service()
    result = vnpay.verify_return(params)

    transaction_id = result["transaction_id"]
    enrollment_repo = EnrollmentRepository(db)
    payment_repo = PaymentRepository(db)
    course_repo = CourseRepository(db)
    enrollment_service = EnrollmentService(enrollment_repo, payment_repo, course_repo)

    payment_status = "completed" if result["is_success"] else "failed"
    await enrollment_service.confirm_payment(transaction_id, payment_status)

    return {"success": True, "message": "OK"}


@router.post("/momo/return")
async def momo_return(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle MoMo return URL callback (user redirected back after payment)."""
    params = await request.form()
    params = dict(params)

    momo = get_momo_service()
    result = momo.verify_callback(params)

    if not result["is_valid"]:
        logger.warning(f"MoMo invalid signature for txn {result.get('transaction_id')}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    transaction_id = result.get("order_id", "")
    enrollment_repo = EnrollmentRepository(db)
    payment_repo = PaymentRepository(db)
    course_repo = CourseRepository(db)
    enrollment_service = EnrollmentService(enrollment_repo, payment_repo, course_repo)

    payment_status = "completed" if result["is_success"] else "failed"
    enrollment, _ = await enrollment_service.confirm_payment(transaction_id, payment_status)

    return {
        "success": result["is_success"],
        "message": result["message"],
        "transaction_id": transaction_id,
    }


@router.post("/momo/ipn")
async def momo_ipn(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle MoMo IPN (Instant Payment Notification) - server-to-server callback."""
    params = await request.form()
    params = dict(params)

    momo = get_momo_service()
    result = momo.verify_callback(params)

    transaction_id = result.get("order_id", "")
    enrollment_repo = EnrollmentRepository(db)
    payment_repo = PaymentRepository(db)
    course_repo = CourseRepository(db)
    enrollment_service = EnrollmentService(enrollment_repo, payment_repo, course_repo)

    payment_status = "completed" if result["is_success"] else "failed"
    await enrollment_service.confirm_payment(transaction_id, payment_status)

    return {"success": True, "message": "OK"}