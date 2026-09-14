from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.note import Note
from app.models.user import User
from app.repositories import note_repo
from app.schemas.note import NoteCreate, NoteResponse, NoteUpdate

router = APIRouter(prefix="/notes", tags=["Notes"])


@router.get("", response_model=list[NoteResponse])
async def list_notes(
    course_id: UUID,
    lesson_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List notes for the current user filtered by course (and optionally lesson)."""
    notes = await note_repo.get_notes(
        db, user_id=current_user.id, course_id=course_id, lesson_id=lesson_id
    )
    return notes


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    data: NoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new note attached to a course (and optionally a lesson)."""
    note = Note(
        user_id=current_user.id,
        course_id=data.course_id,
        lesson_id=data.lesson_id,
        content=data.content,
    )
    created = await note_repo.create_note(db, note)
    return created


@router.put("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: UUID,
    data: NoteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update note content. Only the owner may update."""
    note = await note_repo.get_by_id(db, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    if note.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    updated = await note_repo.update_note(db, note, data.content)
    return updated


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a note. Only the owner may delete."""
    note = await note_repo.get_by_id(db, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    if note.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    await note_repo.delete_note(db, note)
