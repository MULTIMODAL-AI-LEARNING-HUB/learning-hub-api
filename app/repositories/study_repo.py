"""Study repository."""

from uuid import UUID

from sqlalchemy import func, select

from app.models.essay import EssaySubmission
from app.models.flashcard import Flashcard, FlashcardItem
from app.models.quiz_set import QuizQuestion, QuizSet
from app.repositories.base import BaseRepository


class StudyRepository(BaseRepository):
    async def create_quiz_set(self, quiz_set: QuizSet) -> QuizSet:
        self.db.add(quiz_set)
        await self.db.commit()
        await self.db.refresh(quiz_set)
        return quiz_set

    async def add_quiz_questions(self, items: list[QuizQuestion]) -> list[QuizQuestion]:
        self.db.add_all(items)
        await self.db.commit()
        return items

    async def get_quiz_set_by_job(self, job_id: str) -> QuizSet | None:
        result = await self.db.execute(select(QuizSet).where(QuizSet.job_id == job_id))
        return result.scalar_one_or_none()

    async def get_quiz_set(self, quiz_set_id: UUID) -> QuizSet | None:
        from sqlalchemy.orm import selectinload
        result = await self.db.execute(
            select(QuizSet)
            .where(QuizSet.id == quiz_set_id)
            .options(selectinload(QuizSet.questions))
        )
        return result.scalar_one_or_none()

    async def list_quiz_sets(self, user_id: UUID, document_id: UUID | None = None, offset: int = 0, limit: int = 20) -> tuple[list[QuizSet], int]:
        q = select(QuizSet).where(QuizSet.user_id == user_id)
        cq = select(func.count()).select_from(QuizSet).where(QuizSet.user_id == user_id)
        if document_id is not None:
            q = q.where(QuizSet.document_id == document_id)
            cq = cq.where(QuizSet.document_id == document_id)
        q = q.order_by(QuizSet.created_at.desc()).offset(offset).limit(limit)
        rows = (await self.db.execute(q)).scalars().all()
        total = (await self.db.execute(cq)).scalar_one()
        return list(rows), int(total or 0)

    async def delete_quiz_set(self, quiz_set_id: UUID, user_id: UUID) -> bool:
        obj = await self.db.get(QuizSet, quiz_set_id)
        if obj is not None and obj.user_id == user_id:
            await self.db.delete(obj)
            await self.db.commit()
            return True
        return False

    async def list_flashcards(self, user_id: UUID, document_id: UUID | None = None, offset: int = 0, limit: int = 20):
        stmt = (
            select(Flashcard, func.count(FlashcardItem.id).label("item_count"))
            .outerjoin(FlashcardItem, Flashcard.id == FlashcardItem.flashcard_id)
            .where(Flashcard.user_id == user_id)
        )
        c_stmt = select(func.count()).select_from(Flashcard).where(Flashcard.user_id == user_id)
        if document_id is not None:
            stmt = stmt.where(Flashcard.document_id == document_id)
            c_stmt = c_stmt.where(Flashcard.document_id == document_id)
        stmt = stmt.group_by(Flashcard.id).order_by(Flashcard.created_at.desc()).offset(offset).limit(limit)
        rows = (await self.db.execute(stmt)).all()
        total = (await self.db.execute(c_stmt)).scalar_one()
        return rows, int(total or 0)

    async def delete_flashcard(self, flashcard_id: UUID, user_id: UUID) -> bool:
        obj = await self.db.get(Flashcard, flashcard_id)
        if obj is not None and obj.user_id == user_id:
            await self.db.delete(obj)
            await self.db.commit()
            return True
        return False
    async def create_flashcard(self, flashcard: Flashcard) -> Flashcard:
        self.db.add(flashcard)
        await self.db.commit()
        await self.db.refresh(flashcard)
        return flashcard

    async def add_flashcard_items(self, items: list[FlashcardItem]) -> list[FlashcardItem]:
        self.db.add_all(items)
        await self.db.commit()
        return items

    async def get_flashcard(self, flashcard_id: UUID) -> Flashcard | None:
        from sqlalchemy.orm import selectinload
        result = await self.db.execute(
            select(Flashcard)
            .where(Flashcard.id == flashcard_id)
            .options(selectinload(Flashcard.items))
        )
        return result.scalar_one_or_none()

    async def create_essay_submission(self, submission: EssaySubmission) -> EssaySubmission:
        self.db.add(submission)
        await self.db.commit()
        await self.db.refresh(submission)
        return submission

    async def get_essay_submission(self, submission_id: UUID) -> EssaySubmission | None:
        result = await self.db.execute(
            select(EssaySubmission).where(EssaySubmission.id == submission_id)
        )
        return result.scalar_one_or_none()
