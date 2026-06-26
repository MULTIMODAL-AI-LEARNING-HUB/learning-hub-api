"""Course service."""

from uuid import UUID

from app.models.course import Course
from app.repositories.course_repo import CourseRepository


class CourseService:
    def __init__(self, repo: CourseRepository):
        self.repo = repo

    async def create(
        self,
        lecturer_id: UUID,
        title: str,
        description: str | None = None,
        category_id: UUID | None = None,
        price_vnd: int = 0,
        thumbnail_url: str | None = None
    ) -> Course:
        course = Course(
            lecturer_id=lecturer_id,
            title=title,
            description=description,
            category_id=category_id,
            price_vnd=price_vnd,
            thumbnail_url=thumbnail_url,
            status="draft"
        )
        return await self.repo.create(course)

    async def get_by_id(self, course_id: UUID) -> Course | None:
        return await self.repo.get_by_id(course_id)

    async def get_by_id_with_materials(self, course_id: UUID) -> Course | None:
        return await self.repo.get_by_id_with_materials(course_id)

    async def list_published(
        self,
        offset: int = 0,
        limit: int = 20,
        search: str | None = None,
        category_id: UUID | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> tuple[list[Course], int]:
        courses = await self.repo.list_published(
            offset=offset,
            limit=limit,
            search=search,
            category_id=category_id,
            min_price=min_price,
            max_price=max_price,
            sort_by=sort_by,
            sort_order=sort_order
        )
        total = await self.repo.count_published(
            search=search,
            category_id=category_id,
            min_price=min_price,
            max_price=max_price
        )
        return courses, total

    async def list_by_lecturer(self, lecturer_id: UUID, offset: int = 0, limit: int = 20) -> tuple[list[Course], int]:
        courses = await self.repo.list_by_lecturer(lecturer_id, offset, limit)
        total = await self.repo.count_by_lecturer(lecturer_id)
        return courses, total

    async def update(
        self,
        course_id: UUID,
        title: str | None = None,
        description: str | None = None,
        category_id: UUID | None = None,
        price_vnd: int | None = None,
        thumbnail_url: str | None = None
    ) -> Course | None:
        course = await self.repo.get_by_id(course_id)
        if not course:
            return None

        if title is not None:
            course.title = title
        if description is not None:
            course.description = description
        if category_id is not None:
            course.category_id = category_id
        if price_vnd is not None:
            course.price_vnd = price_vnd
        if thumbnail_url is not None:
            course.thumbnail_url = thumbnail_url

        return await self.repo.update(course)

    async def publish(self, course_id: UUID) -> Course | None:
        course = await self.repo.get_by_id(course_id)
        if not course:
            return None
        course.status = "published"
        return await self.repo.update(course)

    async def archive(self, course_id: UUID) -> Course | None:
        course = await self.repo.get_by_id(course_id)
        if not course:
            return None
        course.status = "archived"
        return await self.repo.update(course)

    async def delete(self, course_id: UUID) -> None:
        await self.repo.delete(course_id)