"""Course repository."""

from uuid import UUID

from sqlalchemy import select, delete, func, or_
from sqlalchemy.orm import selectinload

from app.models.course import Course
from app.repositories.base import BaseRepository


class CourseRepository(BaseRepository):
    async def create(self, course: Course) -> Course:
        self.db.add(course)
        await self.db.commit()
        await self.db.refresh(course)
        return course

    async def get_by_id(self, course_id: UUID) -> Course | None:
        result = await self.db.execute(
            select(Course)
            .where(Course.id == course_id)
            .options(selectinload(Course.lecturer), selectinload(Course.category))
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_materials(self, course_id: UUID) -> Course | None:
        result = await self.db.execute(
            select(Course)
            .where(Course.id == course_id)
            .options(
                selectinload(Course.lecturer),
                selectinload(Course.category),
                selectinload(Course.materials)
            )
        )
        return result.scalar_one_or_none()

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
    ) -> list[Course]:
        query = select(Course).where(Course.status == "published").options(selectinload(Course.lecturer), selectinload(Course.category))

        if search:
            query = query.where(
                or_(
                    Course.title.ilike(f"%{search}%"),
                    Course.description.ilike(f"%{search}%")
                )
            )

        if category_id:
            query = query.where(Course.category_id == category_id)

        if min_price is not None:
            query = query.where(Course.price_vnd >= min_price)

        if max_price is not None:
            query = query.where(Course.price_vnd <= max_price)

        sort_column = getattr(Course, sort_by, Course.created_at)
        if sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        query = query.offset(offset).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_published(
        self,
        search: str | None = None,
        category_id: UUID | None = None,
        min_price: int | None = None,
        max_price: int | None = None
    ) -> int:
        query = select(func.count(Course.id)).where(Course.status == "published")

        if search:
            query = query.where(
                or_(
                    Course.title.ilike(f"%{search}%"),
                    Course.description.ilike(f"%{search}%")
                )
            )

        if category_id:
            query = query.where(Course.category_id == category_id)

        if min_price is not None:
            query = query.where(Course.price_vnd >= min_price)

        if max_price is not None:
            query = query.where(Course.price_vnd <= max_price)

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def list_by_lecturer(self, lecturer_id: UUID, offset: int = 0, limit: int = 20) -> list[Course]:
        result = await self.db.execute(
            select(Course)
            .where(Course.lecturer_id == lecturer_id)
            .options(selectinload(Course.lecturer), selectinload(Course.category))
            .order_by(Course.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_lecturer(self, lecturer_id: UUID) -> int:
        result = await self.db.execute(
            select(func.count(Course.id)).where(Course.lecturer_id == lecturer_id)
        )
        return result.scalar() or 0

    async def update(self, course: Course) -> Course:
        await self.db.commit()
        await self.db.refresh(course)
        return course

    async def delete(self, course_id: UUID) -> None:
        await self.db.execute(delete(Course).where(Course.id == course_id))
        await self.db.commit()

    async def list_all(
        self,
        offset: int = 0,
        limit: int = 20,
        search: str | None = None,
        status: str | None = None,
        lecturer_id: UUID | None = None,
    ) -> list[Course]:
        query = select(Course).options(selectinload(Course.lecturer), selectinload(Course.category))

        if status:
            query = query.where(Course.status == status)
        if lecturer_id:
            query = query.where(Course.lecturer_id == lecturer_id)
        if search:
            query = query.where(
                or_(
                    Course.title.ilike(f"%{search}%"),
                    Course.description.ilike(f"%{search}%")
                )
            )

        query = query.order_by(Course.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_all(
        self,
        search: str | None = None,
        status: str | None = None,
        lecturer_id: UUID | None = None,
    ) -> int:
        query = select(func.count(Course.id))
        if status:
            query = query.where(Course.status == status)
        if lecturer_id:
            query = query.where(Course.lecturer_id == lecturer_id)
        if search:
            query = query.where(
                or_(
                    Course.title.ilike(f"%{search}%"),
                    Course.description.ilike(f"%{search}%")
                )
            )
        result = await self.db.execute(query)
        return result.scalar() or 0