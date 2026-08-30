from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models import Course, Discussion, Lesson, Section
from app.models.user import User
from app.schemas.course_content import (
    DiscussionCreate,
    DiscussionResponse,
    DiscussionUpdate,
)

router = APIRouter(prefix="/lessons/{lesson_id}/discussions", tags=["Discussions"])


async def get_lesson_with_course(db: AsyncSession, lesson_id: UUID) -> tuple[Lesson, Course]:
    result = await db.execute(
        select(Lesson).where(Lesson.id == lesson_id).options(selectinload(Lesson.section).selectinload(Section.course))
    )
    lesson = result.scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson, lesson.section.course


@router.get("", response_model=List[DiscussionResponse])
async def list_discussions(
    lesson_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Discussion)
        .where(Discussion.lesson_id == lesson_id, Discussion.parent_id.is_(None))
        .options(selectinload(Discussion.replies))
        .order_by(Discussion.is_pinned.desc(), Discussion.created_at.desc())
    )
    discussions = result.scalars().all()

    response = []
    for d in discussions:
        user_result = await db.execute(select(User).where(User.id == d.user_id))
        user = user_result.scalar_one_or_none()
        reply_count = len(d.replies) if d.replies else 0

        replies_response = []
        if d.replies:
            for r in d.replies:
                reply_user_result = await db.execute(select(User).where(User.id == r.user_id))
                reply_user = reply_user_result.scalar_one_or_none()
                replies_response.append({
                    "id": r.id,
                    "lesson_id": r.lesson_id,
                    "user_id": r.user_id,
                    "user_name": reply_user.full_name if reply_user else None,
                    "user_avatar": reply_user.avatar_url if reply_user else None,
                    "parent_id": r.parent_id,
                    "content": r.content,
                    "is_pinned": r.is_pinned,
                    "is_answer": r.is_answer,
                    "upvotes": r.upvotes,
                    "reply_count": 0,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                    "replies": []
                })

        response.append({
            "id": d.id,
            "lesson_id": d.lesson_id,
            "user_id": d.user_id,
            "user_name": user.full_name if user else None,
            "user_avatar": user.avatar_url if user else None,
            "parent_id": d.parent_id,
            "content": d.content,
            "is_pinned": d.is_pinned,
            "is_answer": d.is_answer,
            "upvotes": d.upvotes,
            "reply_count": reply_count,
            "created_at": d.created_at,
            "updated_at": d.updated_at,
            "replies": replies_response
        })
    return response


@router.post("", response_model=DiscussionResponse, status_code=status.HTTP_201_CREATED)
async def create_discussion(
    lesson_id: UUID,
    discussion_data: DiscussionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    lesson, course = await get_lesson_with_course(db, lesson_id)

    discussion = Discussion(
        lesson_id=lesson_id,
        user_id=current_user.id,
        parent_id=discussion_data.parent_id,
        content=discussion_data.content
    )
    db.add(discussion)
    await db.commit()
    await db.refresh(discussion)

    return {
        "id": discussion.id,
        "lesson_id": discussion.lesson_id,
        "user_id": discussion.user_id,
        "user_name": current_user.full_name,
        "user_avatar": current_user.avatar_url,
        "parent_id": discussion.parent_id,
        "content": discussion.content,
        "is_pinned": discussion.is_pinned,
        "is_answer": discussion.is_answer,
        "upvotes": discussion.upvotes,
        "reply_count": 0,
        "created_at": discussion.created_at,
        "updated_at": discussion.updated_at,
        "replies": []
    }


@router.put("/posts/{post_id}", response_model=DiscussionResponse)
async def update_discussion(
    lesson_id: UUID,
    post_id: UUID,
    discussion_data: DiscussionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Discussion).where(Discussion.id == post_id))
    discussion = result.scalar_one_or_none()
    if not discussion:
        raise HTTPException(status_code=404, detail="Discussion not found")

    if discussion.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    if discussion_data.content is not None:
        discussion.content = discussion_data.content

    await db.commit()
    await db.refresh(discussion)

    user_result = await db.execute(select(User).where(User.id == discussion.user_id))
    user = user_result.scalar_one_or_none()

    return {
        "id": discussion.id,
        "lesson_id": discussion.lesson_id,
        "user_id": discussion.user_id,
        "user_name": user.full_name if user else None,
        "user_avatar": user.avatar_url if user else None,
        "parent_id": discussion.parent_id,
        "content": discussion.content,
        "is_pinned": discussion.is_pinned,
        "is_answer": discussion.is_answer,
        "upvotes": discussion.upvotes,
        "reply_count": 0,
        "created_at": discussion.created_at,
        "updated_at": discussion.updated_at,
        "replies": []
    }


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_discussion(
    lesson_id: UUID,
    post_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Discussion).where(Discussion.id == post_id))
    discussion = result.scalar_one_or_none()
    if not discussion:
        raise HTTPException(status_code=404, detail="Discussion not found")

    if discussion.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    await db.delete(discussion)
    await db.commit()


@router.post("/posts/{post_id}/upvote", response_model=DiscussionResponse)
async def upvote_discussion(
    lesson_id: UUID,
    post_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Discussion).where(Discussion.id == post_id))
    discussion = result.scalar_one_or_none()
    if not discussion:
        raise HTTPException(status_code=404, detail="Discussion not found")

    discussion.upvotes += 1
    await db.commit()
    await db.refresh(discussion)

    user_result = await db.execute(select(User).where(User.id == discussion.user_id))
    user = user_result.scalar_one_or_none()

    return {
        "id": discussion.id,
        "lesson_id": discussion.lesson_id,
        "user_id": discussion.user_id,
        "user_name": user.full_name if user else None,
        "user_avatar": user.avatar_url if user else None,
        "parent_id": discussion.parent_id,
        "content": discussion.content,
        "is_pinned": discussion.is_pinned,
        "is_answer": discussion.is_answer,
        "upvotes": discussion.upvotes,
        "reply_count": 0,
        "created_at": discussion.created_at,
        "updated_at": discussion.updated_at,
        "replies": []
    }