"""Enrollment repository."""

from uuid import UUID

from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import selectinload

from app.models.course import Course
from app.models.enrollment import Enrollment
from app.repositories.base import BaseRepository


class EnrollmentRepository(BaseRepository):
    async def create(self, enrollment: Enrollment) -> Enrollment:
        self.db.add(enrollment)
        await self.db.commit()
        await self.db.refresh(enrollment)
        return enrollment

    async def get_by_id(self, enrollment_id: UUID) -> Enrollment | None:
        result = await self.db.execute(
            select(Enrollment)
            .where(Enrollment.id == enrollment_id)
            .options(selectinload(Enrollment.course), selectinload(Enrollment.student))
        )
        return result.scalar_one_or_none()

    async def get_active_enrollment(self, student_id: UUID, course_id: UUID) -> Enrollment | None:
        result = await self.db.execute(
            select(Enrollment).where(
                and_(
                    Enrollment.student_id == student_id,
                    Enrollment.course_id == course_id,
                    Enrollment.status == "active"
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_student(self, student_id: UUID, status: str | None = None) -> list[Enrollment]:
        query = select(Enrollment).where(Enrollment.student_id == student_id)
        if status:
            query = query.where(Enrollment.status == status)
        query = query.options(
            selectinload(Enrollment.course).selectinload(Course.lecturer),
            selectinload(Enrollment.student)
        ).order_by(Enrollment.enrolled_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_by_course(self, course_id: UUID) -> list[Enrollment]:
        result = await self.db.execute(
            select(Enrollment)
            .where(Enrollment.course_id == course_id)
            .options(selectinload(Enrollment.student))
            .order_by(Enrollment.enrolled_at.desc())
        )
        return list(result.scalars().all())

    async def count_by_course(self, course_id: UUID) -> int:
        result = await self.db.execute(
            select(func.count(Enrollment.id)).where(Enrollment.course_id == course_id)
        )
        return result.scalar() or 0

    async def update_payment(
        self,
        enrollment_id: UUID,
        payment_status: str,
        payment_method: str | None = None,
        transaction_id: str | None = None
    ) -> Enrollment | None:
        enrollment = await self.get_by_id(enrollment_id)
        if enrollment:
            enrollment.payment_status = payment_status
            if payment_method:
                enrollment.payment_method = payment_method
            if transaction_id:
                enrollment.transaction_id = transaction_id
            await self.db.commit()
            await self.db.refresh(enrollment)
        return enrollment

    async def update_status(self, enrollment_id: UUID, status: str) -> Enrollment | None:
        enrollment = await self.get_by_id(enrollment_id)
        if enrollment:
            enrollment.status = status
            await self.db.commit()
            await self.db.refresh(enrollment)
        return enrollment

    async def delete(self, enrollment_id: UUID) -> None:
        await self.db.execute(delete(Enrollment).where(Enrollment.id == enrollment_id))
        await self.db.commit()