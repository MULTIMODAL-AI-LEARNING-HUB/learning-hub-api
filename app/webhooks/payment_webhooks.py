"""Payment webhook handlers."""

import logging

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


@router.api_route("/vnpay/ipn", methods=["GET", "POST"])
async def vnpay_ipn(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle VNPay IPN (Instant Payment Notification) - server-to-server callback."""
    if request.method == "POST":
        try:
            params = dict(await request.form())
        except Exception:
            params = dict(request.query_params)
    else:
        params = dict(request.query_params)

    if not params:
        return {"RspCode": "99", "Message": "Input data required"}

    vnpay = get_vnpay_service()
    result = vnpay.verify_return(params)

    if not result["is_valid"]:
        logger.warning("VNPay IPN: invalid signature")
        return {"RspCode": "97", "Message": "Invalid signature"}

    transaction_id = result["transaction_id"]
    enrollment_repo = EnrollmentRepository(db)
    payment_repo = PaymentRepository(db)
    course_repo = CourseRepository(db)

    # Check if transaction exists
    payment = await payment_repo.get_by_transaction_id(transaction_id)
    if not payment:
        logger.warning(f"VNPay IPN: transaction {transaction_id} not found")
        return {"RspCode": "01", "Message": "Order not found"}

    # Check if order is already confirmed to avoid repeating processes
    if payment.status in {"completed", "failed"}:
        return {"RspCode": "02", "Message": "Order already confirmed"}

    enrollment_service = EnrollmentService(enrollment_repo, payment_repo, course_repo)
    payment_status = "completed" if result["is_success"] else "failed"
    await enrollment_service.confirm_payment(transaction_id, payment_status)

    return {"RspCode": "00", "Message": "Confirm success"}


@router.api_route("/momo/return", methods=["GET", "POST"])
async def momo_return(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle MoMo return URL callback (user redirected back after payment)."""
    if request.method == "POST":
        try:
            params = dict(await request.form())
        except Exception:
            params = dict(request.query_params)
    else:
        params = dict(request.query_params)

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
    try:
        params = await request.json()
    except Exception:
        try:
            params = dict(await request.form())
        except Exception:
            params = dict(request.query_params)

    if not params:
        return {"resultCode": 99, "message": "Input data required"}

    momo = get_momo_service()
    result = momo.verify_callback(params)

    if not result["is_valid"]:
        logger.warning("MoMo IPN: invalid signature")
        return {"resultCode": 1002, "message": "Invalid signature"}

    transaction_id = result.get("order_id", "")
    enrollment_repo = EnrollmentRepository(db)
    payment_repo = PaymentRepository(db)
    course_repo = CourseRepository(db)

    # Check if transaction exists
    payment = await payment_repo.get_by_transaction_id(transaction_id)
    if not payment:
        logger.warning(f"MoMo IPN: transaction {transaction_id} not found")
        return {"resultCode": 1001, "message": "Order not found"}

    # Check if order is already confirmed
    if payment.status in {"completed", "failed"}:
        return {"resultCode": 0, "message": "Order already confirmed"}

    enrollment_service = EnrollmentService(enrollment_repo, payment_repo, course_repo)
    payment_status = "completed" if result["is_success"] else "failed"
    await enrollment_service.confirm_payment(transaction_id, payment_status)

    return {"resultCode": 0, "message": "Success"}