from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User

class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    related_id: Mapped[UUID | None] = mapped_column(nullable=True)
    related_type: Mapped[str | None] = mapped_column(String(50))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user: Mapped["User"] = relationship(back_populates="notifications")
