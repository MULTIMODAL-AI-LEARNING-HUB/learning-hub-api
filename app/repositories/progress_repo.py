"""Material progress repository."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, delete, func, select

from app.models.material_progress import MaterialProgress
from app.repositories.base import BaseRepository


class ProgressRepository(BaseRepository):
    async def get_or_create(
        self,
        enrollment_id: UUID,
        material_id: UUID
    ) -> MaterialProgress:
        result = await self.db.execute(
            select(MaterialProgress).where(
                and_(
                    MaterialProgress.enrollment_id == enrollment_id,
                    MaterialProgress.material_id == material_id
                )
            )
        )
        progress = result.scalar_one_or_none()

        if not progress:
            progress = MaterialProgress(
                enrollment_id=enrollment_id,
                material_id=material_id,
                completion_percent=0,
                completed=False
            )
            self.db.add(progress)
            await self.db.commit()
            await self.db.refresh(progress)

        return progress

    async def update_progress(
        self,
        enrollment_id: UUID,
        material_id: UUID,
        completion_percent: int,
        last_position: dict | None = None
    ) -> MaterialProgress:
        progress = await self.get_or_create(enrollment_id, material_id)

        progress.completion_percent = min(completion_percent, 100)
        progress.last_position = last_position

        if completion_percent >= 80 and not progress.completed:
            progress.completed = True
            progress.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        elif completion_percent < 80:
            progress.completed = False
            progress.completed_at = None

        await self.db.commit()
        await self.db.refresh(progress)
        return progress

    async def get_enrollment_progress(self, enrollment_id: UUID) -> list[MaterialProgress]:
        result = await self.db.execute(
            select(MaterialProgress)
            .where(MaterialProgress.enrollment_id == enrollment_id)
        )
        return list(result.scalars().all())

    async def get_material_progress(self, enrollment_id: UUID, material_id: UUID) -> MaterialProgress | None:
        result = await self.db.execute(
            select(MaterialProgress).where(
                and_(
                    MaterialProgress.enrollment_id == enrollment_id,
                    MaterialProgress.material_id == material_id
                )
            )
        )
        return result.scalar_one_or_none()

    async def count_completed(self, enrollment_id: UUID) -> int:
        result = await self.db.execute(
            select(func.count(MaterialProgress.id)).where(
                and_(
                    MaterialProgress.enrollment_id == enrollment_id,
                    MaterialProgress.completed
                )
            )
        )
        return result.scalar() or 0

    async def delete_by_enrollment(self, enrollment_id: UUID) -> None:
        await self.db.execute(
            delete(MaterialProgress).where(MaterialProgress.enrollment_id == enrollment_id)
        )
        await self.db.commit()