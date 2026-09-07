import pytest

from app.services.payment_gateway_service import (
    generate_mock_payment_token,
    verify_mock_payment_token,
    VNPayService,
    MoMoService,
)


def test_mock_payment_token_generation_and_verification():
    """Verify mock payment HMAC signature generation and tamper rejection."""
    transaction_id = "vnpay_12345678"
    amount = 500000

    token = generate_mock_payment_token(transaction_id, amount)
    assert token is not None
    assert len(token) == 64

    # Valid token verification
    assert verify_mock_payment_token(transaction_id, amount, token) is True

    # Tampered amount
    assert verify_mock_payment_token(transaction_id, 1000, token) is False

    # Tampered transaction_id
    assert verify_mock_payment_token("vnpay_fake", amount, token) is False

    # Tampered token
    assert verify_mock_payment_token(transaction_id, amount, "bad_token") is False

    # Empty token
    assert verify_mock_payment_token(transaction_id, amount, "") is False


@pytest.mark.asyncio
async def test_vnpay_and_momo_mock_url_fallback():
    """Verify VNPay and MoMo generate valid mock URLs containing method names when unconfigured."""
    vnpay = VNPayService()
    vnpay.merchant_id = ""
    vnpay.hash_secret = ""

    vnpay_url = vnpay.create_payment_url(
        amount=250000,
        transaction_id="vnpay_test_abc",
        order_info="Test course enrollment",
        ip_address="127.0.0.1",
    )
    assert "mock-gateway" in vnpay_url
    assert "vnpay" in vnpay_url
    assert "token=" in vnpay_url
    assert "amount=250000" in vnpay_url

    momo = MoMoService()
    momo.partner_code = ""
    momo.access_key = ""
    momo.secret_key = ""

    momo_url = await momo.create_payment_url(
        amount=300000,
        transaction_id="momo_test_xyz",
        order_info="Test MoMo course enrollment",
        ip_address="127.0.0.1",
    )
    assert "mock-gateway" in momo_url
    assert "momo" in momo_url
    assert "token=" in momo_url
    assert "amount=300000" in momo_url


@pytest.mark.asyncio
async def test_enrollment_service_confirm_payment_with_kwargs():
    """Verify confirm_payment accepts payment_status keyword argument properly."""
    from unittest.mock import AsyncMock, MagicMock
    from uuid import uuid4
    from app.services.enrollment_service import EnrollmentService
    from app.models.payment import Payment

    enrollment_repo = MagicMock()
    payment_repo = MagicMock()
    course_repo = MagicMock()
    service = EnrollmentService(enrollment_repo, payment_repo, course_repo)

    txn = "mock_test_123"
    fake_payment = Payment(
        student_id=uuid4(),
        course_id=uuid4(),
        enrollment_id=uuid4(),
        amount_vnd=199000,
        payment_method="vnpay",
        transaction_id=txn,
        payment_status="pending",
    )
    payment_repo.get_by_transaction_id = AsyncMock(return_value=fake_payment)
    payment_repo.update_status = AsyncMock(return_value=fake_payment)
    enrollment_repo.update_payment = AsyncMock()
    enrollment_repo.update_status = AsyncMock()
    enrollment_repo.get_by_id = AsyncMock(return_value=None)

    # Calling with payment_status keyword argument MUST succeed without TypeError
    await service.confirm_payment(transaction_id=txn, payment_status="completed")
    payment_repo.update_status.assert_awaited_once()
