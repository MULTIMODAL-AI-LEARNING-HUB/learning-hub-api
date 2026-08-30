"""Document API endpoints."""

import logging
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.minio_client import MinioClient
from app.core.cache import RedisCache
from app.core.config import settings

# Core/Client integrations
from app.core.limiter import limiter
from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.document import Document
from app.models.user import User
from app.repositories.document_repo import DocumentRepository
from app.schemas import DocumentListResponse, DocumentResponse, DocumentUploadResponse
from app.tasks.document_tasks import dispatch_process_document
from app.utils.pagination import build_pagination

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
    # 1. Extension & Format validation
    filename = file.filename or "uploaded_file"
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    allowed_exts = {"pdf", "mp4", "mp3", "webm"}
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format: .{ext}. Allowed: PDF, MP4, MP3, WebM."
        )

    # 2. File size calculation & Quota validation
    content = await file.read()
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
