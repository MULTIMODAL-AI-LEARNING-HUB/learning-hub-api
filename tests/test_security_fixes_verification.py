"""Comprehensive tests for security fixes and regression prevention."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.enrollment import Enrollment
from app.models.payment import Payment
from app.services.enrollment_service import EnrollmentService
from app.utils.upload import validate_file_magic_bytes
from app.api.v1.course_materials import _validate_external_url, _is_private_or_loopback_host


# ─── 1. Enrollment Service Activation on Confirmed Payment ───────

@pytest.mark.asyncio
async def test_confirm_payment_activates_enrollment():
    """Verify that confirming a completed payment activates the enrollment status."""
    enrollment_repo = MagicMock()
    payment_repo = MagicMock()
    course_repo = MagicMock()

    service = EnrollmentService(enrollment_repo, payment_repo, course_repo)

    student_id = uuid4()
    course_id = uuid4()
    enrollment_id = uuid4()
    txn_id = "TXN_TEST_12345"

    initial_payment = Payment(
        student_id=student_id,
        course_id=course_id,
        enrollment_id=enrollment_id,
        amount_vnd=500000,
        payment_method="vnpay",
        transaction_id=txn_id,
        payment_status="pending",
    )

    payment_repo.get_by_transaction_id = AsyncMock(return_value=initial_payment)

    updated_payment = Payment(
        student_id=student_id,
        course_id=course_id,
        enrollment_id=enrollment_id,
        amount_vnd=500000,
        payment_method="vnpay",
        transaction_id=txn_id,
        payment_status="completed",
    )
    payment_repo.update_status = AsyncMock(return_value=updated_payment)

    active_enrollment = Enrollment(
        id=enrollment_id,
        student_id=student_id,
        course_id=course_id,
        status="active",
        payment_status="paid",
    )
    enrollment_repo.update_payment = AsyncMock(return_value=active_enrollment)
    enrollment_repo.update_status = AsyncMock(return_value=active_enrollment)
    enrollment_repo.get_by_id = AsyncMock(return_value=active_enrollment)

    enrollment, payment = await service.confirm_payment(txn_id, "completed")

    enrollment_repo.update_payment.assert_awaited_once_with(
        enrollment_id,
        payment_status="paid",
        payment_method="vnpay",
        transaction_id=txn_id,
    )
    enrollment_repo.update_status.assert_awaited_once_with(enrollment_id, "active")
    assert enrollment.status == "active"
    assert payment.payment_status == "completed"


# ─── 2. Magic Bytes Upload Validation ────────────────────────────

def test_magic_bytes_pdf_validation():
    """Verify PDF magic bytes sniffing rejects forged non-PDF files."""
    valid_pdf = b"%PDF-1.5\n%trailer..."
    fake_pdf = b"<html><script>alert(1)</script></html>"
    empty = b""

    assert validate_file_magic_bytes(valid_pdf, "pdf") is True
    assert validate_file_magic_bytes(fake_pdf, "pdf") is False
    assert validate_file_magic_bytes(empty, "pdf") is False


def test_magic_bytes_image_and_media_validation():
    """Verify image and media header signatures."""
    valid_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    fake_png = b"GIF89a"
    assert validate_file_magic_bytes(valid_png, "png") is True
    assert validate_file_magic_bytes(fake_png, "png") is False

    valid_jpg = b"\xff\xd8\xff\xe0\x00\x10JFIF"
    fake_jpg = b"PNG..."
    assert validate_file_magic_bytes(valid_jpg, "jpg") is True
    assert validate_file_magic_bytes(valid_jpg, "jpeg") is True
    assert validate_file_magic_bytes(fake_jpg, "jpg") is False

    valid_mp4 = b"\x00\x00\x00\x18ftypmp42"
    fake_mp4 = b"RIFF...."
    assert validate_file_magic_bytes(valid_mp4, "mp4") is True
    assert validate_file_magic_bytes(fake_mp4, "mp4") is False

    valid_webm = b"\x1a\x45\xdf\xa3\x93\x42\x86"
    assert validate_file_magic_bytes(valid_webm, "webm") is True
    assert validate_file_magic_bytes(b"not webm", "webm") is False

    valid_mp3 = b"ID3\x03\x00\x00"
    assert validate_file_magic_bytes(valid_mp3, "mp3") is True
    assert validate_file_magic_bytes(b"bad mp3", "mp3") is False


# ─── 3. SSRF & Private IP Detection in External URLs ─────────────

def test_ssrf_and_private_ip_detection():
    """Verify _is_private_or_loopback_host detects private/internal/loopback addresses."""
    assert _is_private_or_loopback_host("localhost") is True
    assert _is_private_or_loopback_host("sub.localhost") is True
    assert _is_private_or_loopback_host("server.local") is True
    assert _is_private_or_loopback_host("api.internal") is True
    assert _is_private_or_loopback_host("127.0.0.1") is True
    assert _is_private_or_loopback_host("10.0.0.1") is True
    assert _is_private_or_loopback_host("192.168.1.100") is True
    assert _is_private_or_loopback_host("172.16.0.5") is True
    assert _is_private_or_loopback_host("169.254.169.254") is True
    assert _is_private_or_loopback_host("::1") is True

    # Public hosts should pass
    assert _is_private_or_loopback_host("example.com") is False
    assert _is_private_or_loopback_host("google.com") is False
    assert _is_private_or_loopback_host("8.8.8.8") is False


def test_validate_external_url_rejects_dangerous_urls():
    """Verify _validate_external_url rejects HTTP, internal IPs, and non-HTTPS."""
    with pytest.raises(HTTPException) as exc_http:
        _validate_external_url("http://example.com/test.pdf")
    assert exc_http.value.status_code == 400

    with pytest.raises(HTTPException) as exc_local:
        _validate_external_url("https://localhost/secret.pdf")
    assert exc_local.value.status_code == 400

    with pytest.raises(HTTPException) as exc_ssrf:
        _validate_external_url("https://169.254.169.254/latest/meta-data/")
    assert exc_ssrf.value.status_code == 400

    with pytest.raises(HTTPException) as exc_private:
        _validate_external_url("https://192.168.1.1/admin")
    assert exc_private.value.status_code == 400

    valid = _validate_external_url("https://raw.githubusercontent.com/user/repo/main/doc.pdf")
    assert valid.startswith("https://")
