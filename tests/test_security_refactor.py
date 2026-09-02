"""Security and Refactoring Verification Tests.

Tests privilege escalation prevention, BOLA/IDOR access controls,
anti-cheating quiz schemas, payment cryptographic validation, and upload safety.
"""

import hashlib
import hmac
import io
import urllib.parse
from uuid import uuid4

import pytest
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError

from app.dependencies.course_auth import verify_course_ownership
from app.models.course import Course
from app.models.user import User
from app.schemas.auth import RegisterRequest
from app.schemas.course_content import (
    AnswerStudentResponse,
    QuestionStudentResponse,
    QuizStudentResponse,
)
from app.services.auth_service import AuthService
from app.services.payment_gateway_service import MoMoService, VNPayService
from app.utils.upload import read_upload_file_safely, sanitize_filename


def test_register_schema_prevents_admin_self_assignment():
    """Verify that registering with role='admin' is rejected by schema validation."""
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="hacker@example.com",
            password="StrongPassword123!",
            full_name="Attacker",
            role="admin",
        )

    # Valid roles should pass
    req_student = RegisterRequest(
        email="student@example.com",
        password="StrongPassword123!",
        full_name="Student",
        role="student",
    )
    assert req_student.role == "student"

    req_lecturer = RegisterRequest(
        email="lecturer@example.com",
        password="StrongPassword123!",
        full_name="Lecturer",
        role="lecturer",
    )
    assert req_lecturer.role == "lecturer"


@pytest.mark.asyncio
async def test_auth_service_rejects_admin_registration():
    """Verify AuthService.register raises 400 if admin role is passed."""
    service = AuthService(repo=None)
    with pytest.raises(HTTPException) as exc_info:
        await service.register(
            email="hacker2@example.com",
            password="StrongPassword123!",
            full_name="Attacker",
            role="admin",
        )
    assert exc_info.value.status_code == 400


def test_sanitize_filename():
    """Verify path traversal characters and dangerous control bytes are sanitized."""
    assert sanitize_filename("../../../secret.txt") == "secret.txt"
    assert sanitize_filename("..\\..\\windows\\system32\\cmd.exe") == "cmd.exe"
    assert sanitize_filename("foo\0bar.pdf") == "foobar.pdf"
    assert sanitize_filename("my:file*name?.pdf") == "my_file_name_.pdf"
    assert sanitize_filename("") == "uploaded_file"
    assert sanitize_filename(None) == "uploaded_file"


@pytest.mark.asyncio
async def test_read_upload_file_safely_size_bounding():
    """Verify read_upload_file_safely raises HTTP 413 when size exceeds limit."""
    # 1KB content with 500 byte limit
    data = b"A" * 1024
    upload = UploadFile(filename="test.dat", file=io.BytesIO(data))
    with pytest.raises(HTTPException) as exc_info:
        await read_upload_file_safely(upload, max_size_bytes=500)
    assert exc_info.value.status_code == 413

    # Within limit
    upload_ok = UploadFile(filename="test.dat", file=io.BytesIO(data))
    content = await read_upload_file_safely(upload_ok, max_size_bytes=2048)
    assert len(content) == 1024


def test_vnpay_cryptographic_verification():
    """Verify VNPay checksum signature validation and forgery rejection."""
    vnpay = VNPayService()
    vnpay.hash_secret = "secret_key_123"

    params = {
        "vnp_Amount": "10000000",
        "vnp_BankCode": "NCB",
        "vnp_ResponseCode": "00",
        "vnp_TxnRef": "TX123",
    }
    sorted_params = dict(sorted(params.items()))
    query = urllib.parse.urlencode(sorted_params)
    valid_hash = hmac.new(b"secret_key_123", query.encode(), hashlib.sha256).hexdigest()

    # Valid signature
    params_valid = dict(params)
    params_valid["vnp_SecureHash"] = valid_hash
    res = vnpay.verify_return(params_valid)
    assert res["is_valid"] is True
    assert res["is_success"] is True

    # Forged signature
    params_forged = dict(params)
    params_forged["vnp_SecureHash"] = "tampered_hash_value"
    res_forged = vnpay.verify_return(params_forged)
    assert res_forged["is_valid"] is False


def test_momo_cryptographic_verification():
    """Verify MoMo signature validation and forgery rejection."""
    momo = MoMoService()
    momo.access_key = "test_access_key"
    momo.partner_code = "MOMO"
    momo.secret_key = "test_secret_key"

    params = {
        "amount": 100000,
        "extraData": "",
        "message": "Successful",
        "orderId": "ORDER_1",
        "orderInfo": "Course payment",
        "partnerCode": "MOMO",
        "requestId": "REQ_1",
        "responseTime": 1700000000,
        "resultCode": 0,
        "transId": 999999,
    }
    raw_data = (
        f"access_key={momo.access_key}&amount={params['amount']}&"
        f"extraData={params['extraData']}&message={params['message']}&"
        f"orderId={params['orderId']}&orderInfo={params['orderInfo']}&"
        f"partnerCode={params['partnerCode']}&requestId={params['requestId']}&"
        f"responseTime={params['responseTime']}&resultCode={params['resultCode']}&"
        f"transId={params['transId']}"
    )
    valid_sig = hmac.new(b"test_secret_key", raw_data.encode(), hashlib.sha256).hexdigest()

    # Valid
    params_valid = dict(params)
    params_valid["signature"] = valid_sig
    res = momo.verify_callback(params_valid)
    assert res["is_valid"] is True
    assert res["is_success"] is True

    # Tampered amount
    params_tampered = dict(params)
    params_tampered["amount"] = 1000  # Hacker modified amount
    params_tampered["signature"] = valid_sig
    res_tampered = momo.verify_callback(params_tampered)
    assert res_tampered["is_valid"] is False


@pytest.mark.asyncio
async def test_course_ownership_authorization():
    """Verify verify_course_ownership rejects non-owners and allows owner or admin."""
    lecturer_id = uuid4()
    other_lecturer_id = uuid4()
    course = Course(id=uuid4(), lecturer_id=lecturer_id, title="Test Course")

    owner_user = User(id=lecturer_id, role="lecturer")
    admin_user = User(id=uuid4(), role="admin")
    attacker_user = User(id=other_lecturer_id, role="lecturer")
    student_user = User(id=uuid4(), role="student")

    # Owner and admin must pass without exception
    await verify_course_ownership(course, owner_user)
    await verify_course_ownership(course, admin_user)

    # Other lecturer and student must be forbidden (HTTP 403)
    with pytest.raises(HTTPException) as exc_info:
        await verify_course_ownership(course, attacker_user)
    assert exc_info.value.status_code == 403

    with pytest.raises(HTTPException) as exc_info:
        await verify_course_ownership(course, student_user)
    assert exc_info.value.status_code == 403


def test_student_quiz_schema_does_not_leak_correct_answer():
    """Verify that student quiz schemas do not contain is_correct field."""
    from datetime import datetime

    answer_student = AnswerStudentResponse(
        id=uuid4(),
        question_id=uuid4(),
        answer_text="Option A",
        order_index=0,
        created_at=datetime.now(),
    )
    dumped = answer_student.model_dump()
    assert "is_correct" not in dumped

    question_student = QuestionStudentResponse(
        id=uuid4(),
        quiz_id=uuid4(),
        question_text="What is 2+2?",
        type="SINGLE_CHOICE",
        points=1,
        order_index=0,
        created_at=datetime.now(),
        answers=[answer_student],
    )
    dumped_q = question_student.model_dump()
    assert "explanation" not in dumped_q
    assert "is_correct" not in dumped_q["answers"][0]
