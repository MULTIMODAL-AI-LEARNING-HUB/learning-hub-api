"""Interactive Knowledge Mindmap API endpoints."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.ai_client import AiClient
from app.dependencies.auth import get_current_user
from app.dependencies.course_auth import get_lesson_with_course, verify_lesson_access
from app.dependencies.db import get_db
from app.models.user import User
from app.schemas.mindmap import (
    LessonMindmapResponse,
    TextMindmapRequest,
    TextMindmapResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/lessons/{lesson_id}/mindmap", response_model=LessonMindmapResponse)
async def get_lesson_mindmap(
    lesson_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LessonMindmapResponse:
    """Get or generate the interactive knowledge mindmap for a lesson.

    Results are cached in the database (0ms latency, zero redundant AI token cost).
    """
    lesson, course = await get_lesson_with_course(db, lesson_id)
    await verify_lesson_access(lesson, course, current_user, db)

    # Return cached mindmap if already generated
    if lesson.mindmap_markdown and lesson.mindmap_markdown.strip():
        return LessonMindmapResponse(
            lesson_id=lesson.id,
            lesson_title=lesson.title,
            markdown_tree=lesson.mindmap_markdown,
            is_cached=True,
        )

    # Build context from lesson content or metadata
    content_parts = [f"Bài học: {lesson.title}"]
    if lesson.description:
        content_parts.append(f"Mô tả: {lesson.description}")
    if lesson.content:
        content_parts.append(lesson.content)

    full_content = "\n\n".join(content_parts)

    ai_client = AiClient()
    try:
        res = await ai_client.generate_mindmap(content=full_content, title=lesson.title)
        tree = res.get("markdown_tree", "")
    except Exception as exc:
        logger.error("Failed to generate mindmap via AI: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Không thể tạo sơ đồ tư duy vào lúc này. Vui lòng thử lại sau.",
        )

    # Cache markdown tree in DB
    lesson.mindmap_markdown = tree
    await db.commit()
    await db.refresh(lesson)

    return LessonMindmapResponse(
        lesson_id=lesson.id,
        lesson_title=lesson.title,
        markdown_tree=tree,
        is_cached=False,
    )


@router.post("/lessons/{lesson_id}/mindmap/regenerate", response_model=LessonMindmapResponse)
async def regenerate_lesson_mindmap(
    lesson_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LessonMindmapResponse:
    """Force regenerate the mindmap markdown tree for a lesson."""
    lesson, course = await get_lesson_with_course(db, lesson_id)
    await verify_lesson_access(lesson, course, current_user, db)

    content_parts = [f"Bài học: {lesson.title}"]
    if lesson.description:
        content_parts.append(f"Mô tả: {lesson.description}")
    if lesson.content:
        content_parts.append(lesson.content)

    full_content = "\n\n".join(content_parts)

    ai_client = AiClient()
    try:
        res = await ai_client.generate_mindmap(content=full_content, title=lesson.title)
        tree = res.get("markdown_tree", "")
    except Exception as exc:
        logger.error("Failed to regenerate mindmap via AI: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Không thể tạo lại sơ đồ tư duy vào lúc này. Vui lòng thử lại sau.",
        )

    lesson.mindmap_markdown = tree
    await db.commit()
    await db.refresh(lesson)

    return LessonMindmapResponse(
        lesson_id=lesson.id,
        lesson_title=lesson.title,
        markdown_tree=tree,
        is_cached=False,
    )


@router.post("/study/mindmap/generate", response_model=TextMindmapResponse)
async def generate_text_mindmap(
    payload: TextMindmapRequest,
    current_user: User = Depends(get_current_user),
) -> TextMindmapResponse:
    """Generate a mindmap markdown tree from arbitrary text or document extract."""
    ai_client = AiClient()
    try:
        res = await ai_client.generate_mindmap(content=payload.content, title=payload.title)
        tree = res.get("markdown_tree", "")
    except Exception as exc:
        logger.error("Failed to generate text mindmap via AI: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Không thể tạo sơ đồ tư duy vào lúc này.",
        )

    return TextMindmapResponse(markdown_tree=tree)
