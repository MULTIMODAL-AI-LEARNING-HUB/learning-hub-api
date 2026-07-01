from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from sqlalchemy import String, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.course import Course
    from app.models.material_progress import MaterialProgress
    from app.models.course_content import QuizAttempt, Review


class Enrollment(Base):
    __tablename__ = "enrollments"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id: Mapped[UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)

    payment_amount_vnd: Mapped[int] = mapped_column(Integer, default=0)
    payment_status: Mapped[str] = mapped_column(String(50), default="pending")
    payment_method: Mapped[Optional[str]] = mapped_column(String(50))
    transaction_id: Mapped[Optional[str]] = mapped_column(String(255))

    status: Mapped[str] = mapped_column(String(50), default="active")
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    student: Mapped["User"] = relationship("User", back_populates="enrollments")
    course: Mapped["Course"] = relationship("Course", back_populates="enrollments")
    progress: Mapped[list["MaterialProgress"]] = relationship("MaterialProgress", back_populates="enrollment", cascade="all, delete-orphan")
    quiz_attempts: Mapped[list["QuizAttempt"]] = relationship("QuizAttempt", back_populates="enrollment", cascade="all, delete-orphan")
    review: Mapped[Optional["Review"]] = relationship("Review", back_populates="enrollment", uselist=False, cascade="all, delete-orphan")