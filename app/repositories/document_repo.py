"""Document repository."""

from uuid import UUID

from sqlalchemy import delete, select

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

    async def get_by_ids(self, doc_ids: list[UUID]) -> list[Document]:
        result = await self.db.execute(
            select(Document).where(Document.id.in_(doc_ids))
        )
        return list(result.scalars().all())

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
        from sqlalchemy import func
        result = await self.db.execute(
            select(func.count(Document.id)).where(Document.user_id == user_id)
        )
        return result.scalar() or 0

    async def update_status(self, doc_id: UUID, status: str, metadata: dict | None = None) -> Document | None:
        doc = await self.get_by_id(doc_id)
        if doc:
            doc.status = status
            if metadata is not None:
                doc.file_metadata = metadata
            await self.db.commit()
            await self.db.refresh(doc)
        return doc

    async def delete(self, doc_id: UUID) -> None:
        await self.db.execute(delete(Document).where(Document.id == doc_id))
        await self.db.commit()
