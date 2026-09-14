from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import Note


async def get_notes(
    db: AsyncSession,
    user_id: UUID,
    course_id: UUID,
    lesson_id: Optional[UUID] = None,
) -> list[Note]:
    stmt = select(Note).where(Note.user_id == user_id, Note.course_id == course_id)
    if lesson_id is not None:
        stmt = stmt.where(Note.lesson_id == lesson_id)
    stmt = stmt.order_by(Note.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_by_id(db: AsyncSession, note_id: UUID) -> Optional[Note]:
    result = await db.execute(select(Note).where(Note.id == note_id))
    return result.scalar_one_or_none()


async def create_note(db: AsyncSession, note: Note) -> Note:
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


async def update_note(db: AsyncSession, note: Note, content: str) -> Note:
    note.content = content
    await db.commit()
    await db.refresh(note)
    return note


async def delete_note(db: AsyncSession, note: Note) -> None:
    await db.delete(note)
    await db.commit()
