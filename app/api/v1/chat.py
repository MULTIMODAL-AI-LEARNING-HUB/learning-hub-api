"""Chat API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.ai_client import AiClient
from app.core.cache import RedisCache
from app.core.config import settings
from app.core.limiter import limiter
from app.dependencies.auth import get_current_user
from app.dependencies.course_auth import get_lesson_with_course, verify_course_access
from app.dependencies.db import get_db
from app.models.chat import ChatSession
from app.models.user import User
from app.repositories.chat_repo import ChatRepository
from app.repositories.course_repo import CourseRepository
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


def _session_to_response(session: ChatSession) -> ChatSessionResponse:
    return ChatSessionResponse(
        id=session.id,
        course_id=session.course_id,
        lesson_id=session.lesson_id,
        title=session.title,
        context_type=session.context_type,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _session_to_list_item(session: ChatSession, last_message: str | None = None) -> ChatSessionListItem:
    return ChatSessionListItem(
        id=session.id,
        course_id=session.course_id,
        lesson_id=session.lesson_id,
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
    course_id = payload.course_id
    if course_id:
        course_repo = CourseRepository(db)
        course = await course_repo.get_by_id(course_id)
        if not course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

        if course.status != "published" and course.lecturer_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Course not available")

        if not await verify_course_access(course, current_user, db):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enrolled in this course")
    if payload.lesson_id:
        lesson, lesson_course = await get_lesson_with_course(db, payload.lesson_id)
        if course_id and lesson_course.id != course_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")
        if not await verify_course_access(lesson_course, current_user, db):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enrolled in this course")
        course_id = lesson_course.id

    service = ChatService(ChatRepository(db))
    session = ChatSession(
        user_id=current_user.id,
        course_id=course_id,
        lesson_id=payload.lesson_id,
        title=payload.title,
        context_type=payload.context_type,
    )
    session = await service.repo.create_session(session)

    await RedisCache().delete_pattern(f"cache:sessions:{current_user.id}:*")

    return _session_to_response(session)


@router.get("/sessions", response_model=ChatSessionListResponse)
async def list_sessions(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
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
    lesson_id = payload.lesson_id or session.lesson_id

    if session.course_id and course_id and session.course_id != course_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session course cannot be changed")
    if session.lesson_id and lesson_id and session.lesson_id != lesson_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session lesson cannot be changed")

    if course_id:
        course_repo = CourseRepository(db)
        course = await course_repo.get_by_id(course_id)
        if not course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

        if course.status != "published" and course.lecturer_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Course not available")

        if not await verify_course_access(course, current_user, db):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enrolled in this course")

    if lesson_id:
        lesson, lesson_course = await get_lesson_with_course(db, lesson_id)
        if course_id and lesson_course.id != course_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")
        if not course_id:
            if not await verify_course_access(lesson_course, current_user, db):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enrolled in this course")
            course_id = lesson_course.id

    service = ChatService(repo)
    await service.add_user_message(session.id, payload.query, course_id)

    ai_response = await AiClient().ask({
        "session_id": str(session.id),
        "user_id": str(current_user.id),
        "query": payload.query,
        "course_id": str(course_id) if course_id else None,
        "lesson_id": str(lesson_id) if lesson_id else None,
        "document_ids": [str(d) for d in payload.document_ids or []],
    })

    answer = ai_response.get("answer", "")
    citations = ai_response.get("citations")
    await service.add_ai_message(session.id, answer, citations, course_id)

    await RedisCache().delete_pattern(f"cache:sessions:{current_user.id}:*")

    return ai_response


@router.get("/sessions/{session_id}/messages", response_model=ChatMessagesResponse)
async def list_messages(
    session_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
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
