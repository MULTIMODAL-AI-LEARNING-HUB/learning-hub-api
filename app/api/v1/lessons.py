from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from uuid import UUID
import uuid
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import Section, Lesson, Attachment, Course
from app.schemas.course_content import (
    LessonCreate, LessonUpdate, LessonResponse, LessonWithContent,
    AttachmentResponse, AttachmentCreate, ReorderLessons
)
from app.dependencies.auth import get_current_user, require_lecturer
from app.models.user import User
from app.core.cache import RedisCache
from app.core.config import settings
from app.clients.minio_client import MinioClient

router = APIRouter(prefix="/sections/{section_id}/lessons", tags=["Lessons"])


async def get_section_with_course(db: AsyncSession, section_id: UUID) -> tuple[Section, Course]:
    result = await db.execute(
        select(Section).where(Section.id == section_id).options(selectinload(Section.course))
    )
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    return section, section.course


async def verify_course_ownership(course: Course, current_user: User) -> None:
    if course.lecturer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to modify this course")


@router.get("", response_model=List[LessonResponse])
async def list_lessons(
    section_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    section, course = await get_section_with_course(db, section_id)

    result = await db.execute(
        select(Lesson)
        .where(Lesson.section_id == section_id)
        .options(
            selectinload(Lesson.quiz),
            selectinload(Lesson.assignment),
            selectinload(Lesson.attachments)
        )
        .order_by(Lesson.order_index)
    )
    lessons = result.scalars().all()

    response = []
    for lesson in lessons:
        lesson_dict = {
            "id": lesson.id,
            "section_id": lesson.section_id,
            "title": lesson.title,
            "description": lesson.description,
            "type": lesson.type,
            "video_url": lesson.video_url,
            "video_duration": lesson.video_duration,
            "content": lesson.content,
            "order_index": lesson.order_index,
            "is_preview": lesson.is_preview,
            "is_active": lesson.is_active,
            "has_quiz": lesson.quiz is not None,
            "has_assignment": lesson.assignment is not None,
            "attachment_count": len(lesson.attachments) if lesson.attachments else 0,
            "created_at": lesson.created_at,
            "updated_at": lesson.updated_at
        }
        response.append(lesson_dict)
    return response


@router.post("", response_model=LessonResponse, status_code=status.HTTP_201_CREATED)
async def create_lesson(
    section_id: UUID,
    lesson_data: LessonCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    section, course = await get_section_with_course(db, section_id)
    await verify_course_ownership(course, current_user)

    result = await db.execute(
        select(Lesson).where(Lesson.section_id == section_id).order_by(Lesson.order_index.desc()).limit(1)
    )
    last_lesson = result.scalar_one_or_none()
    next_order = (last_lesson.order_index + 1) if last_lesson else 0

    lesson = Lesson(
        section_id=section_id,
        title=lesson_data.title,
        description=lesson_data.description,
        type=lesson_data.type,
        video_url=lesson_data.video_url,
        video_duration=lesson_data.video_duration,
        content=lesson_data.content,
        order_index=lesson_data.order_index or next_order,
        is_preview=lesson_data.is_preview
    )
    db.add(lesson)
    await db.commit()
    await db.refresh(lesson)
    await RedisCache().delete(f"cache:lessons:{lesson.id}")

    if lesson.content:
        from app.tasks.lesson_tasks import dispatch_process_lesson_content
        dispatch_process_lesson_content(str(lesson.id), str(course.id))

    return lesson


@router.get("/{lesson_id}", response_model=LessonWithContent)
async def get_lesson(
    section_id: UUID,
    lesson_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    cache = RedisCache()
    cache_key = RedisCache.cache_key_lesson(lesson_id)
    cached = await cache.get(cache_key)
    if cached:
        return LessonWithContent(**cached)

    section, course = await get_section_with_course(db, section_id)

    result = await db.execute(
        select(Lesson)
        .where(Lesson.id == lesson_id, Lesson.section_id == section_id)
        .options(
            selectinload(Lesson.quiz).selectinload(Lesson.questions).selectinload(Lesson.answers),
            selectinload(Lesson.assignment),
            selectinload(Lesson.attachments)
        )
    )
    lesson = result.scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    # Generate presigned URLs for video_url and attachments
    if lesson.video_url and lesson.video_url.startswith("s3://"):
        try:
            lesson.video_url = MinioClient().get_presigned_url(lesson.video_url)
        except Exception:
            pass

    if lesson.attachments:
        for att in lesson.attachments:
            if att.file_url and att.file_url.startswith("s3://"):
                try:
                    att.file_url = MinioClient().get_presigned_url(att.file_url)
                except Exception:
                    pass

    from fastapi.encoders import jsonable_encoder
    lesson_data = jsonable_encoder(lesson)
    await cache.set(cache_key, lesson_data, ttl=settings.REDIS_CACHE_TTL_LESSONS)
    return lesson


@router.put("/{lesson_id}", response_model=LessonResponse)
async def update_lesson(
    section_id: UUID,
    lesson_id: UUID,
    lesson_data: LessonUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    section, course = await get_section_with_course(db, section_id)
    await verify_course_ownership(course, current_user)

    result = await db.execute(
        select(Lesson).where(Lesson.id == lesson_id, Lesson.section_id == section_id)
    )
    lesson = result.scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    for key, value in lesson_data.model_dump(exclude_unset=True).items():
        setattr(lesson, key, value)

    await db.commit()
    await db.refresh(lesson)
    await RedisCache().delete(f"cache:lessons:{lesson.id}")

    if lesson_data.content is not None and lesson.content:
        from app.tasks.lesson_tasks import dispatch_process_lesson_content
        dispatch_process_lesson_content(str(lesson.id), str(course.id))

    return lesson


@router.delete("/{lesson_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lesson(
    section_id: UUID,
    lesson_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    section, course = await get_section_with_course(db, section_id)
    await verify_course_ownership(course, current_user)

    result = await db.execute(
        select(Lesson).where(Lesson.id == lesson_id, Lesson.section_id == section_id)
    )
    lesson = result.scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    await db.delete(lesson)
    await db.commit()
    await RedisCache().delete(f"cache:lessons:{lesson_id}")


@router.put("/{lesson_id}/reorder", response_model=List[LessonResponse])
async def reorder_lessons(
    section_id: UUID,
    lesson_id: UUID,
    reorder_data: ReorderLessons,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    section, course = await get_section_with_course(db, section_id)
    await verify_course_ownership(course, current_user)

    for idx, lid in enumerate(reorder_data.lesson_ids):
        result = await db.execute(
            select(Lesson).where(Lesson.id == lid, Lesson.section_id == section_id)
        )
        lesson = result.scalar_one_or_none()
        if lesson:
            lesson.order_index = idx

    await db.commit()
    await RedisCache().delete_pattern("cache:lessons:*")

    result = await db.execute(
        select(Lesson).where(Lesson.section_id == section_id).order_by(Lesson.order_index)
    )
    lessons = result.scalars().all()
    return lessons


# Attachment routes
@router.get("/{lesson_id}/attachments", response_model=List[AttachmentResponse])
async def list_attachments(
    section_id: UUID,
    lesson_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    section, course = await get_section_with_course(db, section_id)

    result = await db.execute(
        select(Attachment).where(Attachment.lesson_id == lesson_id).order_by(Attachment.uploaded_at.desc())
    )
    attachments = result.scalars().all()
    
    # Generate presigned URLs
    for att in attachments:
        if att.file_url and att.file_url.startswith("s3://"):
            try:
                att.file_url = MinioClient().get_presigned_url(att.file_url)
            except Exception:
                pass
                
    return attachments


@router.post("/{lesson_id}/attachments", response_model=AttachmentResponse, status_code=status.HTTP_201_CREATED)
async def create_attachment(
    section_id: UUID,
    lesson_id: UUID,
    attachment_data: AttachmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    section, course = await get_section_with_course(db, section_id)
    await verify_course_ownership(course, current_user)

    attachment = Attachment(
        lesson_id=lesson_id,
        file_name=attachment_data.file_name,
        file_url=attachment_data.file_url,
        file_type=attachment_data.file_type,
        file_size=attachment_data.file_size
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)
    
    # Generate presigned URL for response
    if attachment.file_url and attachment.file_url.startswith("s3://"):
        try:
            attachment.file_url = MinioClient().get_presigned_url(attachment.file_url)
        except Exception:
            pass

    if attachment.file_type == "pdf" and attachment.file_url:
        from app.tasks.lesson_tasks import dispatch_process_course_file
        dispatch_process_course_file(
            storage_key=attachment.file_url,
            course_id=str(course.id),
            lesson_id=str(lesson_id),
            source_type="lesson_attachment",
            file_name=attachment_data.file_name,
        )

    return attachment


@router.post("/{lesson_id}/attachments/upload", response_model=AttachmentResponse, status_code=status.HTTP_201_CREATED)
async def upload_lesson_attachment(
    section_id: UUID,
    lesson_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    section, course = await get_section_with_course(db, section_id)
    await verify_course_ownership(course, current_user)

    content = await file.read()
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "bin"

    # Security: validate file type and size
    allowed_exts = {"pdf", "doc", "docx", "png", "jpg", "jpeg", "mp4", "webm", "mp3", "txt", "zip"}
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail=f"File type '.{ext}' not allowed. Allowed: {', '.join(sorted(allowed_exts))}")
    max_size = 50 * 1024 * 1024  # 50MB
    if len(content) > max_size:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 50MB")
    
    # Structured key: materials/{course_id}/{lesson_id}/{uuid}.{ext}
    minio_key = f"materials/{course.id}/{lesson_id}/{uuid.uuid4()}.{ext}"
    
    # Upload file
    minio_client = MinioClient()
    storage_uri = minio_client.upload_file(content, minio_key, file.content_type)

    attachment = Attachment(
        lesson_id=lesson_id,
        file_name=file.filename,
        file_url=storage_uri,
        file_type=file.content_type,
        file_size=len(content)
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)
    
    # Generate presigned URL for output response
    if attachment.file_url and attachment.file_url.startswith("s3://"):
        try:
            attachment.file_url = minio_client.get_presigned_url(attachment.file_url)
        except Exception:
            pass

    # Dispatch vectorization task for supported file types
    if ext == "pdf":
        from app.tasks.lesson_tasks import dispatch_process_course_file
        dispatch_process_course_file(
            storage_key=minio_key,
            course_id=str(course.id),
            lesson_id=str(lesson_id),
            source_type="lesson_attachment",
            file_name=file.filename,
        )

    return attachment


@router.delete("/{lesson_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    section_id: UUID,
    lesson_id: UUID,
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer)
):
    section, course = await get_section_with_course(db, section_id)
    await verify_course_ownership(course, current_user)

    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id, Attachment.lesson_id == lesson_id)
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    # Delete physical file from MinIO
    if attachment.file_url and attachment.file_url.startswith("s3://"):
        try:
            MinioClient().delete_file(attachment.file_url)
        except Exception as e:
            print(f"Failed to delete file from MinIO: {e}")

    await db.delete(attachment)
    await db.commit()