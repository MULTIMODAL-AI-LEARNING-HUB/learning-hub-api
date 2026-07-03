from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class EnrollmentBase(BaseModel):
    pass


class PaymentIntentRequest(BaseModel):
    payment_method: str = Field(pattern="^(vnpay|momo)$")


class PaymentIntentResponse(BaseModel):
    payment_url: str
    transaction_id: str
    amount_vnd: int


class PaymentConfirmRequest(BaseModel):
    transaction_id: str
    payment_method: str
    payment_data: dict | None = None


class EnrollmentResponse(BaseModel):
    id: UUID
    student_id: UUID
    course_id: UUID
    payment_amount_vnd: int
    payment_status: str
    payment_method: str | None = None
    transaction_id: str | None = None
    status: str
    enrolled_at: datetime
    completed_at: datetime | None = None

    class Config:
        from_attributes = True


class EnrollmentWithCourseResponse(EnrollmentResponse):
    course_title: str | None = None
    course_thumbnail: str | None = None
    lecturer_name: str | None = None
    student_name: str | None = None
    student_email: str | None = None
    student_avatar_url: str | None = None

    class Config:
        from_attributes = True


class EnrollmentListResponse(BaseModel):
    items: list[EnrollmentWithCourseResponse]
    total: int