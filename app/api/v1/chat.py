"""Chat API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.ai_client import AiClient
from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.user import User
from app.repositories.chat_repo import ChatRepository
from app.repositories.document_repo import DocumentRepository
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
from app.core.limiter import limiter
from app.core.cache import RedisCache
from app.core.config import settings

router = APIRouter()


@router.post("/sessions", response_model=ChatSessionResponse, status_code=201)
async def create_session(
    payload: ChatSessionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatSessionResponse:
    """Create a new chat session and invalidate session caches."""
    service = ChatService(ChatRepository(db))
    session = await service.create_session(current_user.id, payload.document_id, payload.title)
    
    # Invalidate session caches
    await RedisCache().delete_pattern(f"cache:sessions:{current_user.id}:*")
    
    return ChatSessionResponse(
        id=session.id,
        title=session.title,
        document_id=session.document_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.get("/sessions", response_model=ChatSessionListResponse)
async def list_sessions(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatSessionListResponse:
    """List paginated chat sessions using cache."""
    cache = RedisCache()
    cache_key = f"cache:sessions:{current_user.id}:{page}:{page_size}"
    
    cached = await cache.get(cache_key)
    if cached:
        return ChatSessionListResponse(**cached)

    repo = ChatRepository(db)
    offset = (page - 1) * page_size
    sessions = await repo.list_sessions(current_user.id, offset, page_size)
    total = await repo.count_sessions(current_user.id)
    pagination = build_pagination(total, page, page_size)
    
    items = []
    for s in sessions:
        try:
            last_msg = s.messages[-1].content if s.messages else None
        except Exception:
            last_msg = None
        items.append(
            ChatSessionListItem(
                id=s.id,
                title=s.title,
                document_id=s.document_id,
                updated_at=s.updated_at,
                last_message=last_msg,
            )
        )
    response_data = ChatSessionListResponse(
        items=items,
        total=pagination["total"],
        page=pagination["page"],
        page_size=pagination["page_size"],
    )
    
    await cache.set(cache_key, response_data.model_dump(mode="json"), ttl=settings.REDIS_CACHE_TTL_DOCS)
    return response_data


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete chat session and invalidate session caches."""
    repo = ChatRepository(db)
    session = await repo.get_session(session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    
    await repo.delete_session(session_id)
    
    # Invalidate session caches
    await RedisCache().delete_pattern(f"cache:sessions:{current_user.id}:*")


@router.post("/ask")
@limiter.limit(settings.RATE_LIMIT_CHAT)
async def ask(
    request: Request,
    payload: ChatAskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ask a question using session context and call async AI service client."""
    repo = ChatRepository(db)
    session = await repo.get_session(payload.session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    service = ChatService(repo)
    # Save the user query to the database
    await service.add_user_message(session.id, payload.query)

    # Verify ownership of requested document IDs (batch query)
    doc_repo = DocumentRepository(db)
    docs = await doc_repo.get_by_ids(payload.document_ids or [])
    owned_ids = {d.id for d in docs if d.user_id == current_user.id}
    for doc_id in payload.document_ids or []:
        if doc_id not in owned_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied for document ID: {doc_id}"
            )

    # Call AI service with our singleton HTTP client
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
    # Save the AI answer to the database
    await service.add_ai_message(session.id, answer, citations)
    
    # Invalidate sessions list cache since last_message and updated_at change
    await RedisCache().delete_pattern(f"cache:sessions:{current_user.id}:*")
    
    return ai_response


@router.get("/sessions/{session_id}/messages", response_model=ChatMessagesResponse)
async def list_messages(
    session_id: UUID,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatMessagesResponse:
    """Retrieve message history for a session with correct total-based pagination."""
    repo = ChatRepository(db)
    session = await repo.get_session(session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    offset = (page - 1) * page_size
    messages = await repo.list_messages(session_id, offset, page_size)
    total = await repo.count_messages(session_id)
    pagination = build_pagination(total, page, page_size)
    
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
