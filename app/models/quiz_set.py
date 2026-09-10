"""Persisted quiz sets generated from documents.

Quiz generation itself runs on Celery (ephemeral result backend), so without
a DB record the questions vanish on tab switch / TTL expiry. QuizSet stores
the header; QuizQuestion stores each question so students can review history.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.user import User


class QuizSet(Base):
    __tablename__ = "quiz_sets"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), index=True)
    job_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    quiz_type: Mapped[str] = mapped_column(String(20), default="quick")
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user: Mapped["User"] = relationship(back_populates="quiz_sets")
    document: Mapped["Document"] = relationship(back_populates="quiz_sets")
    questions: Mapped[list["QuizQuestion"]] = relationship(back_populates="quiz_set", cascade="all, delete-orphan")


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    quiz_set_id: Mapped[UUID] = mapped_column(ForeignKey("quiz_sets.id", ondelete="CASCADE"), nullable=False, index=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    correct_answer: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)

    quiz_set: Mapped["QuizSet"] = relationship(back_populates="questions")
