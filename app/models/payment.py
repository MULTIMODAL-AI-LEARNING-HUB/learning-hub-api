from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.enrollment import Enrollment
    from app.models.user import User


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    enrollment_id: Mapped[UUID | None] = mapped_column(ForeignKey("enrollments.id", ondelete="SET NULL"), nullable=True, index=True)
    student_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id: Mapped[UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)

    amount_vnd: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(50), nullable=False)
    transaction_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    payment_status: Mapped[str] = mapped_column(String(50), default="pending")
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    student: Mapped["User"] = relationship("User")
    course: Mapped["Course"] = relationship("Course")
    enrollment: Mapped["Enrollment | None"] = relationship("Enrollment")