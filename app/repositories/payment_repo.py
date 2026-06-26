"""Payment repository."""

from uuid import UUID
from datetime import datetime

from sqlalchemy import select, func

from app.models.payment import Payment
from app.repositories.base import BaseRepository


class PaymentRepository(BaseRepository):
    async def create(self, payment: Payment) -> Payment:
        self.db.add(payment)
        await self.db.commit()
        await self.db.refresh(payment)
        return payment

    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        result = await self.db.execute(
            select(Payment).where(Payment.id == payment_id)
        )
        return result.scalar_one_or_none()

    async def get_by_transaction_id(self, transaction_id: str) -> Payment | None:
        result = await self.db.execute(
            select(Payment).where(Payment.transaction_id == transaction_id)
        )
        return result.scalar_one_or_none()

    async def list_by_student(self, student_id: UUID) -> list[Payment]:
        result = await self.db.execute(
            select(Payment)
            .where(Payment.student_id == student_id)
            .order_by(Payment.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_course(self, course_id: UUID) -> list[Payment]:
        result = await self.db.execute(
            select(Payment)
            .where(Payment.course_id == course_id)
            .order_by(Payment.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        transaction_id: str,
        status: str,
        paid_at: datetime | None = None
    ) -> Payment | None:
        payment = await self.get_by_transaction_id(transaction_id)
        if payment:
            payment.payment_status = status
            if paid_at:
                payment.paid_at = paid_at
            await self.db.commit()
            await self.db.refresh(payment)
        return payment

    async def get_course_revenue(self, course_id: UUID) -> int:
        result = await self.db.execute(
            select(func.sum(Payment.amount_vnd)).where(
                Payment.course_id == course_id,
                Payment.payment_status == "completed"
            )
        )
        return result.scalar() or 0