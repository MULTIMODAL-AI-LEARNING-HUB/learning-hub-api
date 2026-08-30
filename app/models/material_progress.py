from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.course_material import CourseMaterial
    from app.models.enrollment import Enrollment


class MaterialProgress(Base):
    __tablename__ = "material_progress"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    enrollment_id: Mapped[UUID] = mapped_column(ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id: Mapped[UUID] = mapped_column(ForeignKey("course_materials.id", ondelete="CASCADE"), nullable=False, index=True)

    completion_percent: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    last_position: Mapped[dict | None] = mapped_column(JSONB)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    enrollment: Mapped["Enrollment"] = relationship("Enrollment", back_populates="progress")
    material: Mapped["CourseMaterial"] = relationship("CourseMaterial")