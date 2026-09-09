"""Document API endpoints."""

import logging
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.minio_client import LOCAL_STORAGE_DIR, MinioClient
from app.core.cache import RedisCache
from app.core.config import settings

# Core/Client integrations
from app.core.limiter import limiter
from app.dependencies.auth import get_current_user
from app.dependencies.course_auth import verify_course_access
from app.dependencies.db import get_db
from app.models.course import Course
from app.models.course_content import Attachment, Lesson, Section
from app.models.course_material import CourseMaterial
from app.models.document import Document
from app.models.user import User
from app.repositories.document_repo import DocumentRepository
from app.schemas import DocumentListResponse, DocumentResponse, DocumentUploadResponse
from app.tasks.document_tasks import dispatch_process_document
from app.utils.pagination import build_pagination
from app.utils.upload import (
    read_upload_file_safely,
    sanitize_filename,
    validate_file_magic_bytes,
)

router = APIRouter()


def _to_response(doc: Document) -> DocumentResponse:
    """Helper to format Document model to schema, generating presigned MinIO URLs if stored."""
    file_url = doc.file_url
    if doc.storage_key:
        try:
            file_url = MinioClient().get_presigned_url(doc.storage_key)
        except Exception:
            pass  # Fall back to raw file_url if MinIO is not reachable
            
    return DocumentResponse(
        id=doc.id,
        file_name=doc.file_name,
        file_type=doc.file_type,
        file_url=file_url,
        file_size=doc.file_size,
        status=doc.status,
        metadata=doc.file_metadata,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.post("/upload", response_model=DocumentUploadResponse, status_code=202)
@limiter.limit(settings.RATE_LIMIT_UPLOAD)
async def upload(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentUploadResponse:
    """Upload a document to MinIO and trigger processing worker."""
    # 1. Extension & Format validation (aligned with worker-supported formats)
    filename = sanitize_filename(file.filename)
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    allowed_exts = {"pdf", "mp4", "mp3", "webm", "wav", "txt", "doc", "docx"}
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format: .{ext}. Allowed: PDF, MP4, MP3, WebM, WAV, TXT, DOC, DOCX."
        )

    # 2. File size calculation & Quota validation (100MB hard limit per file)
    content = await read_upload_file_safely(file, max_size_bytes=100 * 1024 * 1024)
    if not validate_file_magic_bytes(content, ext):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Uploaded file content does not match expected signature for extension .{ext}."
        )
    file_size_bytes = len(content)
    file_size_mb = file_size_bytes / (1024 * 1024)

    # Verify quota presence and space limit
    if current_user.quota:
        used = current_user.quota.storage_used_mb or 0
        limit = current_user.quota.storage_limit_mb or 1024
        if used + file_size_mb > limit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Storage quota exceeded. Remaining: {max(0.0, limit - used):.2f} MB. File: {file_size_mb:.2f} MB."
            )
    else:
        # Fail safe if quota record is missing
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User quota configuration is missing."
        )

    # 3. Store in MinIO
    minio_key = f"{uuid.uuid4()}.{ext}"
    try:
        minio_client = MinioClient()
        storage_uri = minio_client.upload_file(content, minio_key, file.content_type)
    except Exception:
        logging.exception("MinIO upload failed for user %s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store file in object storage"
        )

    # 4. Save to Database
    repo = DocumentRepository(db)
    document = Document(
        id=UUID(minio_key.split(".")[0]),
        user_id=current_user.id,
        file_name=filename,
        file_type=ext,
        file_url=storage_uri,
        storage_key=minio_key,
        file_size=file_size_bytes,
        status="processing",
    )
    document = await repo.create(document)

    # Update quota usages
    if current_user.quota:
        current_user.quota.storage_used_mb = (current_user.quota.storage_used_mb or 0.0) + file_size_mb
    await db.commit()

    # 5. Invalidate document caches
    await RedisCache().delete_pattern(f"cache:docs:{current_user.id}:*")

    # 6. Dispatch processing task to Celery
    dispatch_process_document(str(document.id))

    return DocumentUploadResponse(
        id=document.id,
        file_name=document.file_name,
        file_type=document.file_type,
        file_size=document.file_size,
        status=document.status,
        created_at=document.created_at,
    )


@router.get("", response_model=DocumentListResponse)
@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentListResponse:
    """List documents for the current user, utilizing Redis cache."""
    cache = RedisCache()
    cache_key = f"cache:docs:{current_user.id}:{page}:{page_size}"
    
    cached = await cache.get(cache_key)
    if cached:
        return DocumentListResponse(**cached)

    repo = DocumentRepository(db)
    offset = (page - 1) * page_size
    docs = await repo.list_by_user(current_user.id, offset, page_size)
    total = await repo.count_by_user(current_user.id)
    pagination = build_pagination(total, page, page_size)
    
    response_data = DocumentListResponse(
        items=[_to_response(d) for d in docs],
        total=pagination["total"],
        page=pagination["page"],
        page_size=pagination["page_size"],
    )
    
    await cache.set(cache_key, response_data.model_dump(mode="json"), ttl=settings.REDIS_CACHE_TTL_DOCS)
    return response_data


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentResponse:
    """Retrieve document details by ID."""
    repo = DocumentRepository(db)
    doc = await repo.get_by_id(doc_id)
    if not doc or doc.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return _to_response(doc)


@router.post("/{doc_id}/retry", response_model=DocumentResponse)
async def retry_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentResponse:
    """Re-queue a failed (or stuck processing) document for worker processing.

    Frontend 'Thử lại' previously only flipped local UI state without
    re-dispatching the Celery task, so retry never actually reprocessed.
    This endpoint resets status to processing, clears the previous error,
    invalidates the list cache, and dispatches a new worker task.
    """
    repo = DocumentRepository(db)
    doc = await repo.get_by_id(doc_id)
    if not doc or doc.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if doc.status not in ("failed", "processing"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only failed or processing documents can be retried (current: {doc.status}).",
        )
    doc.status = "processing"
    doc.file_metadata = None
    await db.commit()
    await db.refresh(doc)
    await RedisCache().delete_pattern(f"cache:docs:{current_user.id}:*")
    dispatch_process_document(str(doc.id))
    return _to_response(doc)


@router.delete("/{doc_id}", status_code=204)
async def delete_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete document from database, object storage, and update quota."""
    repo = DocumentRepository(db)
    doc = await repo.get_by_id(doc_id)
    if not doc or doc.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # 1. Delete from MinIO
    if doc.storage_key:
        try:
            MinioClient().delete_file(doc.storage_key)
        except Exception:
            pass  # Fail silent if object doesn't exist or MinIO is down

    # 2. Release storage quota
    file_size_mb = (doc.file_size or 0) / (1024 * 1024)
    if current_user.quota:
        current_user.quota.storage_used_mb = max(0.0, current_user.quota.storage_used_mb - file_size_mb)

    # 3. Delete from DB
    await repo.delete(doc_id)
    await db.commit()

    # 4. Invalidate document caches
    await RedisCache().delete_pattern(f"cache:docs:{current_user.id}:*")


@router.get("/raw/{filename:path}")
async def get_raw_storage_file(
    filename: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Serve a local fallback object only after ownership/access verification."""
    clean_key = filename.lstrip("/")
    storage_root = LOCAL_STORAGE_DIR.resolve()
    file_path = (storage_root / clean_key).resolve()
    if not file_path.is_relative_to(storage_root) or not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    storage_values = (clean_key, f"file://{clean_key}", f"s3://{settings.MINIO_BUCKET_NAME}/{clean_key}")
    document = (await db.execute(
        select(Document).where(
            Document.user_id == current_user.id,
            (Document.storage_key.in_(storage_values) | Document.file_url.in_(storage_values)),
        )
    )).scalar_one_or_none()
    if document:
        return FileResponse(file_path, filename=document.file_name, media_type="application/octet-stream")

    material_result = await db.execute(
        select(CourseMaterial, Course)
        .join(Course, Course.id == CourseMaterial.course_id)
        .where(
            CourseMaterial.storage_key.in_(storage_values) | CourseMaterial.file_url.in_(storage_values)
        )
    )
    material_row = material_result.first()
    if material_row:
        material, course = material_row
        if await verify_course_access(course, current_user, db):
            return FileResponse(file_path, filename=material.file_name, media_type="application/octet-stream")

    attachment_result = await db.execute(
        select(Attachment, Course)
        .join(Lesson, Lesson.id == Attachment.lesson_id)
        .join(Section, Section.id == Lesson.section_id)
        .join(Course, Course.id == Section.course_id)
        .where(Attachment.file_url.in_(storage_values))
    )
    attachment_row = attachment_result.first()
    if attachment_row:
        attachment, course = attachment_row
        if await verify_course_access(course, current_user, db):
            return FileResponse(file_path, filename=attachment.file_name, media_type="application/octet-stream")

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

