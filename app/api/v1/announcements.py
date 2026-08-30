from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import RedisCache
from app.core.config import settings
from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models import Announcement, Course, User
from app.schemas.announcement import (
    AnnouncementCreate,
    AnnouncementResponse,
    AnnouncementUpdate,
)

router = APIRouter(prefix="/courses/{course_id}/announcements", tags=["announcements"])


async def get_course_or_404(db: AsyncSession, course_id: UUID) -> Course:
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.get("", response_model=List[AnnouncementResponse])
async def list_announcements(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cache = RedisCache()
    cache_key = RedisCache.cache_key_announcements(course_id)
    cached = await cache.get(cache_key)
    if cached:
        return [AnnouncementResponse(**a) for a in cached]

    await get_course_or_404(db, course_id)
    query = (
        select(Announcement)
        .where(Announcement.course_id == course_id)
        .order_by(Announcement.created_at.desc())
    )
    result = await db.execute(query)
    announcements = result.scalars().all()

    response = []
    for a in announcements:
        user_result = await db.execute(select(User).where(User.id == a.lecturer_id))
        lecturer = user_result.scalar_one_or_none()
        response.append(AnnouncementResponse(
            id=a.id,
            course_id=a.course_id,
            lecturer_id=a.lecturer_id,
            lecturer_name=lecturer.full_name if lecturer else None,
            title=a.title,
            content=a.content,
            created_at=a.created_at,
            updated_at=a.updated_at,
        ))
    await cache.set(cache_key, [r.model_dump(mode="json") for r in response], ttl=settings.REDIS_CACHE_TTL_ANNOUNCEMENTS)
    return response


@router.post("", response_model=AnnouncementResponse, status_code=status.HTTP_201_CREATED)
async def create_announcement(
    course_id: UUID,
    data: AnnouncementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    course = await get_course_or_404(db, course_id)
    if course.lecturer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only the course lecturer can create announcements")

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
    result = await db.execute(
        select(Announcement).where(Announcement.id == announcement_id, Announcement.course_id == course_id)
    )
    announcement = result.scalar_one_or_none()
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    if announcement.lecturer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    if data.title is not None:
        announcement.title = data.title
    if data.content is not None:
        announcement.content = data.content

    await db.commit()
    await db.refresh(announcement)

    user_result = await db.execute(select(User).where(User.id == announcement.lecturer_id))
    lecturer = user_result.scalar_one_or_none()

    await RedisCache().delete_pattern(f"cache:announcements:{course_id}")
    return AnnouncementResponse(
        id=announcement.id,
        course_id=announcement.course_id,
        lecturer_id=announcement.lecturer_id,
        lecturer_name=lecturer.full_name if lecturer else None,
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
    result = await db.execute(
        select(Announcement).where(Announcement.id == announcement_id, Announcement.course_id == course_id)
    )
    announcement = result.scalar_one_or_none()
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    if announcement.lecturer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    await db.delete(announcement)
    await db.commit()
    await RedisCache().delete_pattern(f"cache:announcements:{course_id}")
