from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from app.models.chat import ChatMessage, ChatSession
from app.repositories.base import BaseRepository


class ChatRepository(BaseRepository):
    async def create_session(self, session: ChatSession) -> ChatSession:
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def list_sessions(self, user_id: UUID, offset: int, limit: int) -> list[ChatSession]:
        result = await self.db.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .options(selectinload(ChatSession.messages))
            .order_by(ChatSession.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_session(self, session_id: UUID) -> ChatSession | None:
        result = await self.db.execute(
            select(ChatSession)
            .where(ChatSession.id == session_id)
            .options(selectinload(ChatSession.messages))
        )
        return result.scalar_one_or_none()

    async def count_sessions(self, user_id: UUID) -> int:
        result = await self.db.execute(
            select(func.count(ChatSession.id)).where(ChatSession.user_id == user_id)
        )
        return result.scalar() or 0

    async def delete_session(self, session_id: UUID) -> None:
        await self.db.execute(delete(ChatSession).where(ChatSession.id == session_id))
        await self.db.commit()

    async def add_message(self, message: ChatMessage) -> ChatMessage:
        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def list_messages(self, session_id: UUID, offset: int, limit: int) -> list[ChatMessage]:
        result = await self.db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_messages(self, session_id: UUID) -> int:
        result = await self.db.execute(
            select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session_id)
        )
        return result.scalar() or 0
