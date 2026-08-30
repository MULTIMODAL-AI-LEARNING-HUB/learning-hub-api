import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.enrollment import Enrollment
    from app.models.user import User


class LessonType(str, enum.Enum):
    VIDEO = "VIDEO"
    ARTICLE = "ARTICLE"
    QUIZ = "QUIZ"
    ASSIGNMENT = "ASSIGNMENT"


class QuestionType(str, enum.Enum):
    SINGLE_CHOICE = "SINGLE_CHOICE"
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    TRUE_FALSE = "TRUE_FALSE"
    FILL_BLANK = "FILL_BLANK"


class Section(Base):
    __tablename__ = "sections"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    course_id: Mapped[UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    course: Mapped["Course"] = relationship("Course", back_populates="sections")
    lessons: Mapped[List["Lesson"]] = relationship("Lesson", back_populates="section", cascade="all, delete-orphan", order_by="Lesson.order_index")


class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    section_id: Mapped[UUID] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(50), default=LessonType.ARTICLE.value)
    video_url: Mapped[Optional[str]] = mapped_column(String(500))
    video_duration: Mapped[Optional[int]] = mapped_column(Integer)  # seconds
    content: Mapped[Optional[str]] = mapped_column(Text)  # HTML or Markdown
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    is_preview: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    section: Mapped["Section"] = relationship("Section", back_populates="lessons")
    quiz: Mapped[Optional["Quiz"]] = relationship("Quiz", back_populates="lesson", uselist=False, cascade="all, delete-orphan")
    assignment: Mapped[Optional["Assignment"]] = relationship("Assignment", back_populates="lesson", uselist=False, cascade="all, delete-orphan")
    attachments: Mapped[List["Attachment"]] = relationship("Attachment", back_populates="lesson", cascade="all, delete-orphan")
    discussions: Mapped[List["Discussion"]] = relationship("Discussion", back_populates="lesson", cascade="all, delete-orphan")


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    lesson_id: Mapped[UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[Optional[str]] = mapped_column(String(50))
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger)  # bytes
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    lesson: Mapped["Lesson"] = relationship("Lesson", back_populates="attachments")


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    lesson_id: Mapped[UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    passing_score: Mapped[int] = mapped_column(Integer, default=70)
    duration_mins: Mapped[Optional[int]] = mapped_column(Integer)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    lesson: Mapped["Lesson"] = relationship("Lesson", back_populates="quiz")
    questions: Mapped[List["Question"]] = relationship("Question", back_populates="quiz", cascade="all, delete-orphan", order_by="Question.order_index")
    attempts: Mapped[List["QuizAttempt"]] = relationship("QuizAttempt", back_populates="quiz", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    quiz_id: Mapped[UUID] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(50), default=QuestionType.SINGLE_CHOICE.value)
    points: Mapped[int] = mapped_column(Integer, default=1)
    explanation: Mapped[Optional[str]] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    quiz: Mapped["Quiz"] = relationship("Quiz", back_populates="questions")
    answers: Mapped[List["Answer"]] = relationship("Answer", back_populates="question", cascade="all, delete-orphan", order_by="Answer.order_index")


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    question_id: Mapped[UUID] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    question: Mapped["Question"] = relationship("Question", back_populates="answers")


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    enrollment_id: Mapped[UUID] = mapped_column(ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False, index=True)
    quiz_id: Mapped[UUID] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    score: Mapped[Optional[float]] = mapped_column(Integer)
    max_score: Mapped[Optional[float]] = mapped_column(Integer)
    passed: Mapped[Optional[bool]] = mapped_column(Boolean)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    enrollment: Mapped["Enrollment"] = relationship("Enrollment", back_populates="quiz_attempts")
    quiz: Mapped["Quiz"] = relationship("Quiz", back_populates="attempts")


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    lesson_id: Mapped[UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    instructions: Mapped[Optional[str]] = mapped_column(Text)
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime)
    max_score: Mapped[int] = mapped_column(Integer, default=100)
    allow_resubmit: Mapped[bool] = mapped_column(Boolean, default=True)
    max_resubmits: Mapped[int] = mapped_column(Integer, default=3)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    lesson: Mapped["Lesson"] = relationship("Lesson", back_populates="assignment")
    submissions: Mapped[List["AssignmentSubmission"]] = relationship("AssignmentSubmission", back_populates="assignment", cascade="all, delete-orphan")


class AssignmentSubmission(Base):
    __tablename__ = "assignment_submissions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    assignment_id: Mapped[UUID] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    submission_text: Mapped[Optional[str]] = mapped_column(Text)
    attachments: Mapped[Optional[str]] = mapped_column(Text)  # JSON string
    score: Mapped[Optional[int]] = mapped_column(Integer)
    feedback: Mapped[Optional[str]] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    graded_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    is_late: Mapped[bool] = mapped_column(Boolean, default=False)

    assignment: Mapped["Assignment"] = relationship("Assignment", back_populates="submissions")
    student: Mapped["User"] = relationship("User")


class Discussion(Base):
    __tablename__ = "discussions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    lesson_id: Mapped[UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("discussions.id", ondelete="CASCADE"), nullable=True, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_answer: Mapped[bool] = mapped_column(Boolean, default=False)
    upvotes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    lesson: Mapped["Lesson"] = relationship("Lesson", back_populates="discussions")
    user: Mapped["User"] = relationship("User")
    parent: Mapped[Optional["Discussion"]] = relationship("Discussion", remote_side=[id], back_populates="replies")
    replies: Mapped[List["Discussion"]] = relationship("Discussion", back_populates="parent")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    enrollment_id: Mapped[UUID] = mapped_column(ForeignKey("enrollments.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text)
    lecturer_reply: Mapped[Optional[str]] = mapped_column(Text)
    replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    enrollment: Mapped["Enrollment"] = relationship("Enrollment", back_populates="review")