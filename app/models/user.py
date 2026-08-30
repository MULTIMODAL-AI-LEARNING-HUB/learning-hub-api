from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.chat import ChatSession
    from app.models.course import Course
    from app.models.course_content import AssignmentSubmission, Discussion
    from app.models.document import Document
    from app.models.enrollment import Enrollment
    from app.models.essay import EssaySubmission
    from app.models.flashcard import Flashcard
    from app.models.notification import Notification
    from app.models.quota import Quota

class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    role: Mapped[str] = mapped_column(String(50), default="student")
    oauth_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    facebook_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(default=0)
    reset_token: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    reset_token_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    # Relationships
    documents: Mapped[list["Document"]] = relationship(back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    chat_sessions: Mapped[list["ChatSession"]] = relationship(back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    flashcards: Mapped[list["Flashcard"]] = relationship(back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    essay_submissions: Mapped[list["EssaySubmission"]] = relationship(back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    quota: Mapped["Quota"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    courses: Mapped[list["Course"]] = relationship(back_populates="lecturer", cascade="all, delete-orphan", passive_deletes=True)
    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="student", cascade="all, delete-orphan", passive_deletes=True)
    assignment_submissions: Mapped[list["AssignmentSubmission"]] = relationship(back_populates="student", cascade="all, delete-orphan", passive_deletes=True)
    discussions: Mapped[list["Discussion"]] = relationship(back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    notifications: Mapped[list["Notification"]] = relationship(back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
