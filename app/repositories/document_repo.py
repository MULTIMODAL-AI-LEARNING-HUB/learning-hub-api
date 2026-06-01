"""Document repository."""

from uuid import UUID

from sqlalchemy import select, delete

from app.models.document import Document
from app.repositories.base import BaseRepository


class DocumentRepository(BaseRepository):
    async def create(self, document: Document) -> Document:
        self.db.add(document)
        await self.db.commit()
        await self.db.refresh(document)
        return document

    async def get_by_id(self, doc_id: UUID) -> Document | None:
        result = await self.db.execute(select(Document).where(Document.id == doc_id))
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: UUID, offset: int, limit: int) -> list[Document]:
        result = await self.db.execute(
            select(Document)
            .where(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_user(self, user_id: UUID) -> int:
        result = await self.db.execute(select(Document).where(Document.user_id == user_id))
        return len(result.scalars().all())

    async def delete(self, doc_id: UUID) -> None:
        await self.db.execute(delete(Document).where(Document.id == doc_id))
        await self.db.commit()
