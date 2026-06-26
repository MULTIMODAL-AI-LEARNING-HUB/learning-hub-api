"""Course material repository."""

from uuid import UUID

from sqlalchemy import select, delete, func

from app.models.course_material import CourseMaterial
from app.repositories.base import BaseRepository


class CourseMaterialRepository(BaseRepository):
    async def create(self, material: CourseMaterial) -> CourseMaterial:
        self.db.add(material)
        await self.db.commit()
        await self.db.refresh(material)
        return material

    async def get_by_id(self, material_id: UUID) -> CourseMaterial | None:
        result = await self.db.execute(
            select(CourseMaterial).where(CourseMaterial.id == material_id)
        )
        return result.scalar_one_or_none()

    async def list_by_course(self, course_id: UUID) -> list[CourseMaterial]:
        result = await self.db.execute(
            select(CourseMaterial)
            .where(CourseMaterial.course_id == course_id)
            .order_by(CourseMaterial.created_at.asc())
        )
        return list(result.scalars().all())

    async def count_by_course(self, course_id: UUID) -> int:
        result = await self.db.execute(
            select(func.count(CourseMaterial.id)).where(CourseMaterial.course_id == course_id)
        )
        return result.scalar() or 0

    async def update_status(self, material_id: UUID, status: str, file_metadata: dict | None = None) -> CourseMaterial | None:
        material = await self.get_by_id(material_id)
        if material:
            material.status = status
            if file_metadata is not None:
                material.file_metadata = file_metadata
            await self.db.commit()
            await self.db.refresh(material)
        return material

    async def mark_indexed(self, material_id: UUID) -> None:
        material = await self.get_by_id(material_id)
        if material:
            material.is_indexed = True
            await self.db.commit()

    async def delete(self, material_id: UUID) -> None:
        await self.db.execute(delete(CourseMaterial).where(CourseMaterial.id == material_id))
        await self.db.commit()