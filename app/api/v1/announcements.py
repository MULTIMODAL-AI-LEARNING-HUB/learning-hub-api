from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import RedisCache
from app.core.config import settings
from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.course_auth import (
    get_course_or_404,
    verify_course_access,
    verify_course_ownership,
)
from app.models import Announcement, Course, User
from app.schemas.announcement import (
    AnnouncementCreate,
    AnnouncementResponse,
    AnnouncementUpdate,
)

router = APIRouter(prefix="/courses/{course_id}/announcements", tags=["announcements"])


@router.get("", response_model=List[AnnouncementResponse])
async def list_announcements(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    course = await get_course_or_404(db, course_id)
    has_access = await verify_course_access(course, current_user, db)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active enrollment required to access course announcements"
        )

    # Eager load lecturer to eliminate N+1 queries
    query = (
        select(Announcement)
        .where(Announcement.course_id == course_id)
        .options(selectinload(Announcement.lecturer))
        .order_by(Announcement.created_at.desc())
    )
    result = await db.execute(query)
    announcements = result.scalars().all()

    response = [
        AnnouncementResponse(
            id=a.id,
            course_id=a.course_id,
            lecturer_id=a.lecturer_id,
            lecturer_name=a.lecturer.full_name if a.lecturer else None,
            title=a.title,
            content=a.content,
            created_at=a.created_at,
            updated_at=a.updated_at,
        )
        for a in announcements
    ]
    return response


@router.post("", response_model=AnnouncementResponse, status_code=status.HTTP_201_CREATED)
async def create_announcement(
    course_id: UUID,
    data: AnnouncementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    course = await get_course_or_404(db, course_id)
    await verify_course_ownership(course, current_user)

    announcement = Announcement(
        course_id=course_id,
        lecturer_id=current_user.id,
        title=data.title,
        content=data.content,
    )
    db.add(announcement)
    await db.commit()
    await db.refresh(announcement)

    await RedisCache().delete_pattern(f"cache:announcements:{course_id}")
    return AnnouncementResponse(
        id=announcement.id,
        course_id=announcement.course_id,
        lecturer_id=announcement.lecturer_id,
        lecturer_name=current_user.full_name,
        title=announcement.title,
        content=announcement.content,
        created_at=announcement.created_at,
        updated_at=announcement.updated_at,
    )


@router.put("/{announcement_id}", response_model=AnnouncementResponse)
async def update_announcement(
    course_id: UUID,
    announcement_id: UUID,
    data: AnnouncementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    course = await get_course_or_404(db, course_id)
    await verify_course_ownership(course, current_user)

    result = await db.execute(
        select(Announcement)
        .where(Announcement.id == announcement_id, Announcement.course_id == course_id)
        .options(selectinload(Announcement.lecturer))
    )
    announcement = result.scalar_one_or_none()
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    if data.title is not None:
        announcement.title = data.title
    if data.content is not None:
        announcement.content = data.content

    await db.commit()
    await db.refresh(announcement)

    await RedisCache().delete_pattern(f"cache:announcements:{course_id}")
    return AnnouncementResponse(
        id=announcement.id,
        course_id=announcement.course_id,
        lecturer_id=announcement.lecturer_id,
        lecturer_name=announcement.lecturer.full_name if announcement.lecturer else current_user.full_name,
        title=announcement.title,
        content=announcement.content,
        created_at=announcement.created_at,
        updated_at=announcement.updated_at,
    )


@router.delete("/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_announcement(
    course_id: UUID,
    announcement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    course = await get_course_or_404(db, course_id)
    await verify_course_ownership(course, current_user)

    result = await db.execute(
        select(Announcement).where(Announcement.id == announcement_id, Announcement.course_id == course_id)
    )
    announcement = result.scalar_one_or_none()
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    await db.delete(announcement)
    await db.commit()
    await RedisCache().delete_pattern(f"cache:announcements:{course_id}")
