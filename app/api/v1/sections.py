from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.dependencies.auth import get_current_user, require_lecturer
from app.models import Course, Section
from app.models.user import User
from app.schemas.course_content import (
    ReorderSections,
    SectionCreate,
    SectionResponse,
    SectionUpdate,
    SectionWithLessons,
)

router = APIRouter(prefix="/courses/{course_id}/sections", tags=["Sections"])


async def get_course_or_404(db: AsyncSession, course_id: UUID) -> Course:
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


async def verify_course_ownership(course: Course, current_user: User) -> None:
    if course.lecturer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to modify this course")


@router.get("", response_model=List[SectionWithLessons])
async def list_sections(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    await get_course_or_404(db, course_id)
    result = await db.execute(
        select(Section)
        .where(Section.course_id == course_id)
        .options(selectinload(Section.lessons))
        .order_by(Section.order_index)
    )
    sections = result.scalars().all()
    return sections


@router.post("", response_model=SectionResponse, status_code=status.HTTP_201_CREATED)
async def create_section(
    course_id: UUID,
    section_data: SectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    course = await get_course_or_404(db, course_id)
    await verify_course_ownership(course, current_user)

    result = await db.execute(
        select(Section).where(Section.course_id == course_id).order_by(Section.order_index.desc()).limit(1).with_for_update()
    )
    last_section = result.scalar_one_or_none()
    next_order = (last_section.order_index + 1) if last_section else 0

    section = Section(
        course_id=course_id,
        title=section_data.title,
        description=section_data.description,
        order_index=section_data.order_index or next_order
    )
    db.add(section)
    await db.commit()
    await db.refresh(section)
    return section


@router.get("/{section_id}", response_model=SectionWithLessons)
async def get_section(
    course_id: UUID,
    section_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    await get_course_or_404(db, course_id)
    result = await db.execute(
        select(Section)
        .where(Section.id == section_id, Section.course_id == course_id)
        .options(selectinload(Section.lessons))
    )
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    return section


@router.put("/{section_id}", response_model=SectionResponse)
async def update_section(
    course_id: UUID,
    section_id: UUID,
    section_data: SectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    course = await get_course_or_404(db, course_id)
    await verify_course_ownership(course, current_user)

    result = await db.execute(
        select(Section).where(Section.id == section_id, Section.course_id == course_id)
    )
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    for key, value in section_data.model_dump(exclude_unset=True).items():
        setattr(section, key, value)

    await db.commit()
    await db.refresh(section)
    return section


@router.delete("/{section_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_section(
    course_id: UUID,
    section_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    course = await get_course_or_404(db, course_id)
    await verify_course_ownership(course, current_user)

    result = await db.execute(
        select(Section).where(Section.id == section_id, Section.course_id == course_id)
    )
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    await db.delete(section)
    await db.commit()


@router.put("/reorder", response_model=List[SectionResponse])
async def reorder_sections(
    course_id: UUID,
    reorder_data: ReorderSections,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    course = await get_course_or_404(db, course_id)
    await verify_course_ownership(course, current_user)

    for idx, section_id in enumerate(reorder_data.section_ids):
        result = await db.execute(
            select(Section).where(Section.id == section_id, Section.course_id == course_id)
        )
        section = result.scalar_one_or_none()
        if section:
            section.order_index = idx

    await db.commit()

    result = await db.execute(
        select(Section).where(Section.course_id == course_id).order_by(Section.order_index)
    )
    sections = result.scalars().all()
    return sections