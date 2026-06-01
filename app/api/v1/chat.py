from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.ai_client import AiClient
from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.user import User
from app.repositories.chat_repo import ChatRepository
from app.schemas import (
    ChatAskRequest,
    ChatMessageResponse,
    ChatMessagesResponse,
    ChatSessionCreateRequest,
    ChatSessionListItem,
    ChatSessionListResponse,
    ChatSessionResponse,
)
from app.services.chat_service import ChatService
from app.utils.pagination import build_pagination

router = APIRouter()


@router.post("/sessions", response_model=ChatSessionResponse, status_code=201)
async def create_session(
    payload: ChatSessionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatSessionResponse:
    service = ChatService(ChatRepository(db))
    session = await service.create_session(current_user.id, payload.document_id, payload.title)
    return ChatSessionResponse(
        id=session.id,
        title=session.title,
        document_id=session.document_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.get("/sessions", response_model=ChatSessionListResponse)
async def list_sessions(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatSessionListResponse:
    repo = ChatRepository(db)
    offset = (page - 1) * page_size
    sessions = await repo.list_sessions(current_user.id, offset, page_size)
    items = [
        ChatSessionListItem(
            id=s.id,
            title=s.title,
            document_id=s.document_id,
            updated_at=s.updated_at,
            last_message=s.messages[-1].content if s.messages else None,
        )
        for s in sessions
    ]
    total = len(items)
    pagination = build_pagination(total, page, page_size)
    return ChatSessionListResponse(
        items=items,
        total=pagination["total"],
        page=pagination["page"],
        page_size=pagination["page_size"],
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    repo = ChatRepository(db)
    session = await repo.get_session(session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    await repo.delete_session(session_id)


@router.post("/ask")
async def ask(
    payload: ChatAskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = ChatRepository(db)
    session = await repo.get_session(payload.session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    service = ChatService(repo)
    await service.add_user_message(session.id, payload.query)

    ai_response = await AiClient().ask(
        {
            "session_id": str(session.id),
            "user_id": str(current_user.id),
            "query": payload.query,
            "document_ids": [str(d) for d in payload.document_ids or []],
        }
    )

    answer = ai_response.get("answer", "")
    citations = ai_response.get("citations")
    await service.add_ai_message(session.id, answer, citations)
    return ai_response


@router.get("/sessions/{session_id}/messages", response_model=ChatMessagesResponse)
async def list_messages(
    session_id: UUID,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatMessagesResponse:
    repo = ChatRepository(db)
    session = await repo.get_session(session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    offset = (page - 1) * page_size
    messages = await repo.list_messages(session_id, offset, page_size)
    pagination = build_pagination(len(messages), page, page_size)
    return ChatMessagesResponse(
        items=[
            ChatMessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                citations=m.citations,
                created_at=m.created_at,
            )
            for m in messages
        ],
        total=pagination["total"],
        page=pagination["page"],
        page_size=pagination["page_size"],
    )
