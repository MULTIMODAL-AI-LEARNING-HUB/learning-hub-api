from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.user import User


class CourseMaterial(Base):
    __tablename__ = "course_materials"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    course_id: Mapped[UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    lecturer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    file_name: Mapped[str | None] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_url: Mapped[str | None] = mapped_column(String(500))
    storage_key: Mapped[str | None] = mapped_column(String(500))
    file_size: Mapped[int | None] = mapped_column(BigInteger)

    external_url: Mapped[str | None] = mapped_column(String(500))

    status: Mapped[str] = mapped_column(String(50), default="pending")
    file_metadata: Mapped[dict | None] = mapped_column(JSONB)

    is_indexed: Mapped[bool] = mapped_column(default=False)

    material_type: Mapped[str] = mapped_column(String(50), default="lecture")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    course: Mapped["Course"] = relationship("Course", back_populates="materials")
    lecturer: Mapped["User"] = relationship("User")