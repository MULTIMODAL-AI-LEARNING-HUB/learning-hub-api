from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.course_auth import verify_course_access
from app.models import Course, User
from app.models.course_chat import CourseChatMessage
from app.schemas.course_chat import (
    CourseChatMessageCreate,
    CourseChatMessageResponse,
    CourseChatMessagesResponse,
)

router = APIRouter(prefix="/courses/{course_id}/chat", tags=["course-chat"])


async def ensure_member(course_id: UUID, user: User, db: AsyncSession) -> Course:
    course = (await db.execute(select(Course).where(Course.id == course_id))).scalar_one_or_none()
    if not course:
        raise HTTPException(404, "Course not found")
    if not await verify_course_access(course, user, db):
        raise HTTPException(403, "Active enrollment required")
    return course


def serialize(message: CourseChatMessage, sender: User) -> CourseChatMessageResponse:
    return CourseChatMessageResponse(id=message.id, course_id=message.course_id, sender_id=message.sender_id, sender_name=sender.full_name, sender_role=sender.role, content=message.content, created_at=message.created_at)


@router.get("/messages", response_model=CourseChatMessagesResponse)
async def list_messages(course_id: UUID, limit: int = Query(50, ge=1, le=100), before: UUID | None = None, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await ensure_member(course_id, current_user, db)
    query = select(CourseChatMessage, User).join(User, User.id == CourseChatMessage.sender_id).where(CourseChatMessage.course_id == course_id).order_by(CourseChatMessage.created_at.desc()).limit(min(limit, 100))
    if before:
        pivot = await db.get(CourseChatMessage, before)
        if pivot:
            query = query.where(CourseChatMessage.created_at < pivot.created_at)
    rows = (await db.execute(query)).all()
    total = (await db.execute(select(func.count(CourseChatMessage.id)).where(CourseChatMessage.course_id == course_id))).scalar_one()
    return CourseChatMessagesResponse(items=[serialize(m, u) for m, u in reversed(rows)], total=total)


@router.post("/messages", response_model=CourseChatMessageResponse, status_code=status.HTTP_201_CREATED)
async def create_message(course_id: UUID, payload: CourseChatMessageCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await ensure_member(course_id, current_user, db)
    message = CourseChatMessage(course_id=course_id, sender_id=current_user.id, content=payload.content.strip())
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return serialize(message, current_user)
