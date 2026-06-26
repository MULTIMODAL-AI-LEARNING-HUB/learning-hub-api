"""Chat API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.ai_client import AiClient
from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.user import User
from app.models.chat import ChatSession, ChatMessage
from app.repositories.chat_repo import ChatRepository
from app.repositories.course_repo import CourseRepository
from app.repositories.enrollment_repo import EnrollmentRepository
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


def _session_to_response(session: ChatSession) -> ChatSessionResponse:
    return ChatSessionResponse(
        id=session.id,
        course_id=session.course_id,
        title=session.title,
        context_type=session.context_type,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _session_to_list_item(session: ChatSession, last_message: str | None = None) -> ChatSessionListItem:
    return ChatSessionListItem(
        id=session.id,
        course_id=session.course_id,
        title=session.title,
        context_type=session.context_type,
        updated_at=session.updated_at,
        last_message=last_message,
    )


@router.post("/sessions", response_model=ChatSessionResponse, status_code=201)
async def create_session(
    payload: ChatSessionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatSessionResponse:
    """Create a new chat session with optional course context."""
    if payload.course_id:
        course_repo = CourseRepository(db)
        course = await course_repo.get_by_id(payload.course_id)
        if not course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

        if course.status != "published" and course.lecturer_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Course not available")

        if current_user.role == "student":
            enrollment_repo = EnrollmentRepository(db)
            enrollment = await enrollment_repo.get_active_enrollment(current_user.id, payload.course_id)
            if not enrollment and course.lecturer_id != current_user.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enrolled in this course")

    service = ChatService(ChatRepository(db))
    session = ChatSession(
        user_id=current_user.id,
        course_id=payload.course_id,
        title=payload.title,
        context_type=payload.context_type,
    )
    session = await service.repo.create_session(session)

    await RedisCache().delete_pattern(f"cache:sessions:{current_user.id}:*")

    return _session_to_response(session)


@router.get("/sessions", response_model=ChatSessionListResponse)
async def list_sessions(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatSessionListResponse:
    """List paginated chat sessions."""
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
        items.append(_session_to_list_item(s, last_msg))

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
    """Delete chat session."""
    repo = ChatRepository(db)
    session = await repo.get_session(session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    await repo.delete_session(session_id)
    await RedisCache().delete_pattern(f"cache:sessions:{current_user.id}:*")


@router.post("/ask")
@limiter.limit(settings.RATE_LIMIT_CHAT)
async def ask(
    request: Request,
    payload: ChatAskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ask a question with optional course context for AI."""
    repo = ChatRepository(db)
    session = await repo.get_session(payload.session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    course_id = payload.course_id or session.course_id

    if course_id:
        course_repo = CourseRepository(db)
        course = await course_repo.get_by_id(course_id)
        if not course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

        if course.status != "published" and course.lecturer_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Course not available")

        if current_user.role == "student":
            enrollment_repo = EnrollmentRepository(db)
            enrollment = await enrollment_repo.get_active_enrollment(current_user.id, course_id)
            if not enrollment and course.lecturer_id != current_user.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enrolled in this course")

    service = ChatService(repo)
    await service.add_user_message(session.id, payload.query, payload.course_id)

    ai_response = await AiClient().ask({
        "session_id": str(session.id),
        "user_id": str(current_user.id),
        "query": payload.query,
        "course_id": str(course_id) if course_id else None,
        "document_ids": [str(d) for d in payload.document_ids or []],
    })

    answer = ai_response.get("answer", "")
    citations = ai_response.get("citations")
    await service.add_ai_message(session.id, answer, citations, payload.course_id)

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
    """Retrieve message history for a session."""
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
                context_type=m.context_type,
                citations=m.citations,
                created_at=m.created_at,
            )
            for m in messages
        ],
        total=pagination["total"],
        page=pagination["page"],
        page_size=pagination["page_size"],
    )