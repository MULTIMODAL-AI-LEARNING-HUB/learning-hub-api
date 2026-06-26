"""Enrollment service."""

from uuid import UUID
from datetime import datetime, timezone

from app.models.enrollment import Enrollment
from app.models.payment import Payment
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.payment_repo import PaymentRepository
from app.repositories.course_repo import CourseRepository


class EnrollmentService:
    def __init__(
        self,
        enrollment_repo: EnrollmentRepository,
        payment_repo: PaymentRepository,
        course_repo: CourseRepository
    ):
        self.enrollment_repo = enrollment_repo
        self.payment_repo = payment_repo
        self.course_repo = course_repo

    async def create_enrollment_with_payment(
        self,
        student_id: UUID,
        course_id: UUID,
        payment_method: str,
        transaction_id: str,
        amount_vnd: int
    ) -> tuple[Enrollment, Payment]:
        enrollment = Enrollment(
            student_id=student_id,
            course_id=course_id,
            payment_amount_vnd=amount_vnd,
            payment_status="pending",
            payment_method=payment_method,
            transaction_id=transaction_id,
            status="active"
        )
        enrollment = await self.enrollment_repo.create(enrollment)

        payment = Payment(
            student_id=student_id,
            course_id=course_id,
            enrollment_id=enrollment.id,
            amount_vnd=amount_vnd,
            payment_method=payment_method,
            transaction_id=transaction_id,
            payment_status="pending"
        )
        payment = await self.payment_repo.create(payment)

        return enrollment, payment

    async def confirm_payment(
        self,
        transaction_id: str,
        payment_status: str = "completed"
    ) -> tuple[Enrollment | None, Payment | None]:
        paid_at = datetime.now(timezone.utc).replace(tzinfo=None) if payment_status == "completed" else None
        payment = await self.payment_repo.update_status(transaction_id, payment_status, paid_at)

        if not payment:
            return None, None

        enrollment = None
        if payment.enrollment_id and payment_status == "completed":
            await self.enrollment_repo.update_payment(
                payment.enrollment_id,
                payment_status="paid",
                payment_method=payment.payment_method,
                transaction_id=payment.transaction_id
            )
            enrollment = await self.enrollment_repo.get_by_id(payment.enrollment_id)

        return enrollment, payment

    async def get_enrollment(self, enrollment_id: UUID) -> Enrollment | None:
        return await self.enrollment_repo.get_by_id(enrollment_id)

    async def get_active_enrollment(self, student_id: UUID, course_id: UUID) -> Enrollment | None:
        return await self.enrollment_repo.get_active_enrollment(student_id, course_id)

    async def list_student_enrollments(self, student_id: UUID, status: str | None = None) -> list[Enrollment]:
        return await self.enrollment_repo.list_by_student(student_id, status)

    async def list_course_enrollments(self, course_id: UUID) -> list[Enrollment]:
        return await self.enrollment_repo.list_by_course(course_id)

    async def complete_enrollment(self, enrollment_id: UUID) -> Enrollment | None:
        return await self.enrollment_repo.update_status(enrollment_id, "completed")