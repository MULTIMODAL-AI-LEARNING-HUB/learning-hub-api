import uuid
from typing import List
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.clients.minio_client import MinioClient
from app.core.cache import RedisCache
from app.core.config import settings
from app.core.database import get_db
from app.dependencies.auth import (
    get_current_user,
    get_current_user_flexible,
    require_lecturer,
)
from app.dependencies.course_auth import (
    get_section_with_course,
    verify_course_access,
    verify_course_ownership,
    verify_lesson_access,
)
from app.models import Attachment, Lesson
from app.models.user import User
from app.schemas.course_content import (
    AttachmentCreate,
    AttachmentResponse,
    LessonCreate,
    LessonResponse,
    LessonUpdate,
    LessonWithContent,
    ReorderLessons,
)
from app.utils.upload import read_upload_file_safely, sanitize_filename

router = APIRouter(prefix="/sections/{section_id}/lessons", tags=["Lessons"])


async def _get_lesson_in_section(db: AsyncSession, section_id: UUID, lesson_id: UUID) -> Lesson:
    """Resolve a lesson only when it belongs to the section in the URL."""
    result = await db.execute(
        select(Lesson).where(Lesson.id == lesson_id, Lesson.section_id == section_id)
    )
    lesson = result.scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson


def _validate_attachment_uri(file_url: str, course_id: UUID, lesson_id: UUID) -> str:
    """Accept only object-storage URIs inside this course/lesson namespace."""
    value = file_url.strip()
    parsed = urlparse(value)
    if parsed.scheme != "s3" or parsed.netloc != settings.MINIO_BUCKET_NAME:
        raise HTTPException(status_code=400, detail="Attachments must use the configured private object storage")

    key = parsed.path.lstrip("/")
    if ".." in key.split("/") or "\\" in key:
        raise HTTPException(status_code=400, detail="Invalid attachment storage key")
    allowed_prefixes = (
        f"materials/{course_id}/{lesson_id}/",
        f"course_materials/{course_id}/",
    )
    if not key.startswith(allowed_prefixes):
        raise HTTPException(status_code=400, detail="Attachment is outside the course storage namespace")
    return value


@router.get("", response_model=List[LessonResponse])
async def list_lessons(
    section_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    section, course = await get_section_with_course(db, section_id)
    if not await verify_course_access(course, current_user, db):
        raise HTTPException(status_code=403, detail="Enrollment required to access this course")

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
    section, course = await get_section_with_course(db, section_id)

    result = await db.execute(
        select(Lesson)
        .where(Lesson.id == lesson_id, Lesson.section_id == section_id)
        .options(
            selectinload(Lesson.quiz),
            selectinload(Lesson.assignment),
            selectinload(Lesson.attachments)
        )
    )
    lesson = result.scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    # Enforce access control (preview or active course enrollment)
    await verify_lesson_access(lesson, course, current_user, db)

    # Generate presigned URLs for video_url and attachments
    if lesson.video_url:
        try:
            # Repair legacy rows where an expired presigned URL was persisted
            # directly (see _normalize_video_url): parse it back to s3:// first.
            storage_uri = lesson.video_url
            if storage_uri.startswith("http://") or storage_uri.startswith("https://"):
                try:
                    normalized = _normalize_video_url(storage_uri)
                    if normalized and normalized.startswith("s3://"):
                        storage_uri = normalized
                        lesson.video_url = normalized
                except HTTPException:
                    pass  # external embed link — serve as-is
            if storage_uri.startswith("s3://"):
                lesson.video_url = MinioClient().get_presigned_url(storage_uri)
        except Exception:
            pass

    if lesson.attachments:
        for att in lesson.attachments:
            if att.file_url and att.file_url.startswith("s3://"):
                try:
                    att.file_url = MinioClient().get_presigned_url(att.file_url)
                except Exception:
                    pass

    return lesson


def _normalize_video_url(value: str | None) -> str | None:
    """Normalize a lesson video_url to a stable storage URI before persisting.

    The frontend may pass back a presigned (temporary) URL produced by the
    attachment-upload response. Those URLs expire, so storing them directly
    breaks playback. Convert presigned URLs back to the ``s3://`` storage
    URI so ``get_lesson`` can mint a fresh presigned URL on every read.
    YouTube/Vimeo embeds and ``s3://`` values pass through unchanged.
    """
    if not value:
        return value
    value = value.strip()
    if value.startswith("s3://") or value.startswith("file://"):
        return value
    bucket = settings.MINIO_BUCKET_NAME
    if value.startswith("/api/v1/documents/raw/"):
        clean = value[len("/api/v1/documents/raw/"):].lstrip("/")
        return f"s3://{bucket}/{clean}"
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        # Check if local backend raw document path
        if "/api/v1/documents/raw/" in parsed.path:
            idx = parsed.path.find("/api/v1/documents/raw/") + len("/api/v1/documents/raw/")
            clean = parsed.path[idx:].lstrip("/")
            return f"s3://{bucket}/{clean}"
        query = parsed.query or ""
        # An internal presigned S3/MinIO URL always carries the query
        # signature parameters — rebuild the canonical storage URI from it.
        if "X-Amz-Signature" in query or "X-Amz-Expires" in query or "signature" in query.lower() or "materials/" in parsed.path:
            if "materials/" in parsed.path:
                idx = parsed.path.find("materials/")
                key = parsed.path[idx:]
                return f"s3://{bucket}/{key}"
            path_parts = parsed.path.lstrip("/").split("/", 1)
            if path_parts and path_parts[0] == bucket and len(path_parts) == 2:
                return f"s3://{bucket}/{path_parts[1]}"
            if parsed.hostname and parsed.hostname.startswith(f"{bucket}.") and parsed.path:
                return f"s3://{bucket}/{parsed.path.lstrip('/')}"
            if len(path_parts) >= 1 and path_parts[-1]:
                return f"s3://{bucket}/{parsed.path.lstrip('/')}"
            raise HTTPException(
                status_code=400,
                detail="video_url must be an s3:// storage URI or a public video link",
            )
    return value


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

    payload = lesson_data.model_dump(exclude_unset=True)
    if "video_url" in payload:
        payload["video_url"] = _normalize_video_url(payload["video_url"])

    for key, value in payload.items():
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
    lesson = await _get_lesson_in_section(db, section_id, lesson_id)
    await verify_lesson_access(lesson, course, current_user, db)

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
    lesson = await _get_lesson_in_section(db, section_id, lesson_id)
    clean_file_url = _validate_attachment_uri(attachment_data.file_url, course.id, lesson.id)

    attachment = Attachment(
        lesson_id=lesson_id,
        file_name=sanitize_filename(attachment_data.file_name),
        file_url=clean_file_url,
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

    if attachment.file_type == "pdf":
        from app.tasks.lesson_tasks import dispatch_process_course_file
        dispatch_process_course_file(
            storage_key=clean_file_url,
            course_id=str(course.id),
            lesson_id=str(lesson_id),
            source_type="lesson_attachment",
            file_name=attachment.file_name,
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
    await _get_lesson_in_section(db, section_id, lesson_id)

    filename = sanitize_filename(file.filename)
    ext = filename.split(".")[-1].lower() if "." in filename else "bin"

    # Security: validate file type and size
    allowed_exts = {"pdf", "doc", "docx", "png", "jpg", "jpeg", "mp4", "webm", "mp3", "txt", "zip"}
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail=f"File type '.{ext}' not allowed. Allowed: {', '.join(sorted(allowed_exts))}")
    content = await read_upload_file_safely(file, max_size_bytes=50 * 1024 * 1024)
    
    # Structured key: materials/{course_id}/{lesson_id}/{uuid}.{ext}
    minio_key = f"materials/{course.id}/{lesson_id}/{uuid.uuid4()}.{ext}"
    
    # Upload file
    minio_client = MinioClient()
    storage_uri = minio_client.upload_file(content, minio_key, file.content_type)

    attachment = Attachment(
        lesson_id=lesson_id,
        file_name=filename,
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
            file_name=filename,
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
    await _get_lesson_in_section(db, section_id, lesson_id)

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



_VIDEO_CONTENT_TYPES = {
    "mp4": "video/mp4",
    "webm": "video/webm",
    "mov": "video/quicktime",
    "m4v": "video/x-m4v",
}


def _resolve_video_storage(file_url: str) -> str:
    """Resolve a persisted lesson/attachment video URL to an s3:// URI.

    Raises 404 when the value is an external embed link or cannot be
    mapped to object storage.
    """
    value = (file_url or "").strip()
    if value.startswith("s3://") or value.startswith("file://"):
        return value
    try:
        normalized = _normalize_video_url(value)
        if normalized and (normalized.startswith("s3://") or normalized.startswith("file://")):
            return normalized
    except HTTPException:
        pass
    raise HTTPException(status_code=404, detail="Video stream not available")


async def _resolve_video_lesson(
    db: AsyncSession, section_id: UUID, lesson_id: UUID
) -> tuple[Lesson, str]:
    """Load a lesson and resolve its playable video to an s3:// URI."""
    result = await db.execute(
        select(Lesson)
        .where(Lesson.id == lesson_id, Lesson.section_id == section_id)
        .options(selectinload(Lesson.attachments))
    )
    lesson = result.scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    candidates: list[str] = []
    if lesson.video_url:
        candidates.append(lesson.video_url)
    for att in lesson.attachments or []:
        if att.file_url and _looks_like_video(att.file_name, att.file_type):
            candidates.append(att.file_url)

    for candidate in candidates:
        try:
            return lesson, _resolve_video_storage(candidate)
        except HTTPException:
            continue
    raise HTTPException(status_code=404, detail="Lesson has no playable video")


def _looks_like_video(file_name: str | None, file_type: str | None) -> bool:
    if file_type and file_type.lower().startswith("video/"):
        return True
    ext = (file_name or "").split(".")[-1].lower() if file_name and "." in file_name else ""
    return ext in _VIDEO_CONTENT_TYPES


def _content_type_for(file_name: str | None, file_type: str | None) -> str:
    if file_type and file_type.lower().startswith("video/"):
        return file_type
    ext = (file_name or "").split(".")[-1].lower() if file_name and "." in file_name else ""
    return _VIDEO_CONTENT_TYPES.get(ext, "video/mp4")


@router.get("/{lesson_id}/stream")
async def stream_lesson_video(
    section_id: UUID,
    lesson_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Stream a lesson video with HTTP Range support for inline playback.

    Auth is flexible (Bearer header or ``?token=`` query param) because
    <video> elements cannot send custom Authorization headers. Access is
    gated by enrollment, and bytes are proxied through the API so no
    object-storage CORS configuration is required on the client.
    """
    section, course = await get_section_with_course(db, section_id)
    lesson, storage_uri = await _resolve_video_lesson(db, section_id, lesson_id)
    await verify_lesson_access(lesson, course, current_user, db)

    storage = MinioClient()
    file_name = lesson.title
    file_type = None
    if lesson.video_url == storage_uri or not lesson.attachments:
        file_name = f"{lesson.title}.mp4"
    else:
        for att in lesson.attachments or []:
            if att.file_url == storage_uri or (
                att.file_url and storage_uri.endswith(att.file_url.split("/")[-1])
            ):
                file_name = att.file_name
                file_type = att.file_type
                break

    media_type = _content_type_for(file_name, file_type)
    total_size = storage.get_object_size(storage_uri)
    range_header = request.headers.get("range")

    if range_header and total_size:
        try:
            unit, _, value = range_header.partition("=")
            start_str, _, end_str = value.partition("-")
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else total_size - 1
            end = min(end, total_size - 1)
            if start > end or start >= total_size:
                return Response(status_code=416, headers={"Content-Range": f"bytes */{total_size}"})
            length = end - start + 1
            # Cap a single range response to 32MB to bound memory per request.
            length = min(length, 32 * 1024 * 1024)
            end = start + length - 1
            data, _ = storage.get_object_range(storage_uri, start, length)
            if data is None:
                raise HTTPException(status_code=404, detail="Video stream not available")
            return Response(
                content=data,
                status_code=206,
                media_type=media_type,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{total_size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(len(data)),
                    "Content-Disposition": f'inline; filename="{file_name}"',
                },
            )
        except (ValueError, TypeError):
            pass  # fall through to full-body streaming

    async def _iter_chunks():
        chunk_size = 1024 * 1024  # 1MB per chunk keeps Heroku memory usage low
        offset = 0
        while True:
            import asyncio

            data, _ = await asyncio.to_thread(
                storage.get_object_range, storage_uri, offset, chunk_size
            )
            if not data:
                break
            offset += len(data)
            yield data
            if len(data) < chunk_size:
                break

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'inline; filename="{file_name}"',
    }
    if total_size:
        headers["Content-Length"] = str(total_size)
    return StreamingResponse(_iter_chunks(), media_type=media_type, headers=headers)
