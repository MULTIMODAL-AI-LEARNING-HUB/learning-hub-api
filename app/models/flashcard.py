from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.user import User

class Flashcard(Base):
    __tablename__ = "flashcards"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), index=True)
    set_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    # Relationships
    user: Mapped["User"] = relationship(back_populates="flashcards")
    document: Mapped["Document"] = relationship(back_populates="flashcards")
    items: Mapped[list["FlashcardItem"]] = relationship(back_populates="flashcard", cascade="all, delete-orphan")

class FlashcardItem(Base):
    __tablename__ = "flashcard_items"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    flashcard_id: Mapped[UUID] = mapped_column(ForeignKey("flashcards.id", ondelete="CASCADE"), nullable=False, index=True)
    front_text: Mapped[str] = mapped_column(Text, nullable=False)
    back_text: Mapped[str] = mapped_column(Text, nullable=False)
    last_reviewed: Mapped[datetime | None] = mapped_column(DateTime)

    # Relationships
    flashcard: Mapped["Flashcard"] = relationship(back_populates="items")
