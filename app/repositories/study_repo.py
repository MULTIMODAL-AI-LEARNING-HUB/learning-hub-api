"""Study repository."""

from uuid import UUID

from sqlalchemy import select

from app.models.essay import EssaySubmission
from app.models.flashcard import Flashcard, FlashcardItem
from app.repositories.base import BaseRepository


class StudyRepository(BaseRepository):
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
