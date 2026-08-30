"""Category repository."""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.repositories.base import BaseRepository


class CategoryRepository(BaseRepository):
    async def create(self, category: Category) -> Category:
        self.db.add(category)
        await self.db.commit()
        await self.db.refresh(category)
        return category

    async def get_by_id(self, category_id: UUID) -> Category | None:
        result = await self.db.execute(select(Category).where(Category.id == category_id))
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Category | None:
        result = await self.db.execute(select(Category).where(Category.slug == slug))
        return result.scalar_one_or_none()

    async def get_all(self) -> list[Category]:
        result = await self.db.execute(
            select(Category)
            .order_by(Category.name)
        )
        return list(result.scalars().all())

    async def get_with_children(self) -> list[Category]:
        result = await self.db.execute(
            select(Category)
            .options(selectinload(Category.children))
            .where(Category.parent_id.is_(None))
            .order_by(Category.name)
        )
        return list(result.scalars().all())

    async def update(self, category: Category) -> Category:
        await self.db.commit()
        await self.db.refresh(category)
        return category

    async def delete(self, category_id: UUID) -> None:
        await self.db.execute(delete(Category).where(Category.id == category_id))
        await self.db.commit()