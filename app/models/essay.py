from uuid import UUID, uuid4
from datetime import datetime
from sqlalchemy import Text, Numeric, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class EssaySubmission(Base):
    __tablename__ = "essay_submissions"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), index=True)
    submission_text: Mapped[str] = mapped_column(Text, nullable=False)
    ai_grade: Mapped[float | None] = mapped_column(Numeric(5, 2))
    ai_feedback: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="essay_submissions")
    document: Mapped["Document"] = relationship(back_populates="essay_submissions")
