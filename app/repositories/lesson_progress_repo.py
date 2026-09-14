"""Lesson progress repository."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, func, select

from app.models.lesson_progress import LessonProgress
from app.repositories.base import BaseRepository


class LessonProgressRepository(BaseRepository):
    async def get_by_enrollment_and_lesson(
        self, enrollment_id: UUID, lesson_id: UUID
    ) -> Optional[LessonProgress]:
        result = await self.db.execute(
            select(LessonProgress).where(
                and_(
                    LessonProgress.enrollment_id == enrollment_id,
                    LessonProgress.lesson_id == lesson_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_completed_lesson_ids(self, enrollment_id: UUID) -> list[UUID]:
        result = await self.db.execute(
            select(LessonProgress.lesson_id).where(
                and_(
                    LessonProgress.enrollment_id == enrollment_id,
                    LessonProgress.completed == True,  # noqa: E712
                )
            )
        )
        return list(result.scalars().all())

    async def update_or_create(
        self, enrollment_id: UUID, lesson_id: UUID, completed: bool
    ) -> LessonProgress:
        lp = await self.get_by_enrollment_and_lesson(enrollment_id, lesson_id)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if lp is None:
            lp = LessonProgress(
                enrollment_id=enrollment_id,
                lesson_id=lesson_id,
                completed=completed,
                completed_at=now if completed else None,
            )
            self.db.add(lp)
        else:
            lp.completed = completed
            lp.completed_at = now if completed else None
        await self.db.commit()
        await self.db.refresh(lp)
        return lp

    async def count_completed(self, enrollment_id: UUID) -> int:
        result = await self.db.execute(
            select(func.count(LessonProgress.id)).where(
                and_(
                    LessonProgress.enrollment_id == enrollment_id,
                    LessonProgress.completed == True,  # noqa: E712
                )
            )
        )
        return result.scalar() or 0
