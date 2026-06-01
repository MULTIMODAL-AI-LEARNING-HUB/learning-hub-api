from uuid import UUID

from app.models.chat import ChatMessage, ChatSession
from app.repositories.chat_repo import ChatRepository


class ChatService:
    def __init__(self, repo: ChatRepository):
        self.repo = repo

    async def create_session(self, user_id: UUID, document_id: UUID | None, title: str | None) -> ChatSession:
        session = ChatSession(user_id=user_id, document_id=document_id, title=title)
        return await self.repo.create_session(session)

    async def add_user_message(self, session_id: UUID, content: str) -> ChatMessage:
        message = ChatMessage(session_id=session_id, role="user", content=content)
        return await self.repo.add_message(message)

    async def add_ai_message(self, session_id: UUID, content: str, citations: list[dict] | None) -> ChatMessage:
        message = ChatMessage(session_id=session_id, role="assistant", content=content, citations=citations)
        return await self.repo.add_message(message)
