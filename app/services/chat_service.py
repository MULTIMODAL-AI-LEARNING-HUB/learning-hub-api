from uuid import UUID

from app.models.chat import ChatMessage, ChatSession
from app.repositories.chat_repo import ChatRepository


class ChatService:
    def __init__(self, repo: ChatRepository):
        self.repo = repo

    async def create_session(
        self,
        user_id: UUID,
        course_id: UUID | None = None,
        title: str | None = None,
        context_type: str = "general"
    ) -> ChatSession:
        session = ChatSession(
            user_id=user_id,
            course_id=course_id,
            title=title,
            context_type=context_type,
        )
        return await self.repo.create_session(session)

    async def add_user_message(
        self,
        session_id: UUID,
        content: str,
        course_id: UUID | None = None,
        context_type: str = "general"
    ) -> ChatMessage:
        message = ChatMessage(
            session_id=session_id,
            role="user",
            content=content,
            context_type=context_type,
        )
        return await self.repo.add_message(message)

    async def add_ai_message(
        self,
        session_id: UUID,
        content: str,
        citations: list[dict] | None,
        course_id: UUID | None = None,
        context_type: str = "general"
    ) -> ChatMessage:
        message = ChatMessage(
            session_id=session_id,
            role="assistant",
            content=content,
            citations=citations,
            context_type=context_type,
        )
        return await self.repo.add_message(message)