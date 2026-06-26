"""Category service."""

from uuid import UUID

from app.models.category import Category
from app.repositories.category_repo import CategoryRepository


class CategoryService:
    def __init__(self, repo: CategoryRepository):
        self.repo = repo

    async def create(self, name: str, slug: str, description: str | None = None, icon: str | None = None) -> Category:
        category = Category(
            name=name,
            slug=slug,
            description=description,
            icon=icon
        )
        return await self.repo.create(category)

    async def get_by_id(self, category_id: UUID) -> Category | None:
        return await self.repo.get_by_id(category_id)

    async def get_by_slug(self, slug: str) -> Category | None:
        return await self.repo.get_by_slug(slug)

    async def get_all(self) -> list[Category]:
        return await self.repo.get_all()

    async def get_tree(self) -> list[Category]:
        return await self.repo.get_with_children()

    async def update(
        self,
        category_id: UUID,
        name: str | None = None,
        description: str | None = None,
        icon: str | None = None
    ) -> Category | None:
        category = await self.repo.get_by_id(category_id)
        if not category:
            return None

        if name is not None:
            category.name = name
        if description is not None:
            category.description = description
        if icon is not None:
            category.icon = icon

        return await self.repo.update(category)

    async def delete(self, category_id: UUID) -> None:
        await self.repo.delete(category_id)