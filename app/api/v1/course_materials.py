"""Course Material API endpoints."""

import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.minio_client import MinioClient
from app.dependencies.auth import get_current_user, require_lecturer
from app.dependencies.course_auth import (
    get_course_or_404,
    verify_course_access,
    verify_course_ownership,
)
from app.dependencies.db import get_db
from app.models.course_material import CourseMaterial
from app.models.user import User
from app.repositories.course_material_repo import CourseMaterialRepository
from app.repositories.course_repo import CourseRepository
from app.schemas import (
    CourseMaterialListResponse,
    CourseMaterialResponse,
    CourseMaterialUpdate,
)
from app.services.course_service import CourseService
from app.utils.upload import read_upload_file_safely, sanitize_filename

router = APIRouter(prefix="/{course_id}/materials", tags=["course-materials"])


def _to_response(material: CourseMaterial) -> CourseMaterialResponse:
    file_url = material.file_url
    if material.storage_key:
        try:
            file_url = MinioClient().get_presigned_url(material.storage_key)
        except Exception:
            pass

    return CourseMaterialResponse(
        id=material.id,
        course_id=material.course_id,
        lecturer_id=material.lecturer_id,
        file_name=material.file_name,
        title=material.file_name,
        file_type=material.file_type,
        file_url=file_url,
        file_size=material.file_size,
        external_url=material.external_url,
        status=material.status,
        file_metadata=material.file_metadata,
        is_indexed=material.is_indexed,
        material_type=material.material_type,
        created_at=material.created_at,
        updated_at=material.updated_at,
    )


@router.get("", response_model=CourseMaterialListResponse)
async def list_materials(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CourseMaterialListResponse:
    """List all materials for a course. Requires enrollment or ownership for paid courses."""
    course = await get_course_or_404(db, course_id)
    has_access = await verify_course_access(course, current_user, db)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active enrollment required to access course materials"
        )

    repo = CourseMaterialRepository(db)
    materials = await repo.list_by_course(course_id)

    return CourseMaterialListResponse(
        items=[_to_response(m) for m in materials],
        total=len(materials),
    )


@router.post("", response_model=CourseMaterialResponse, status_code=201)
async def upload_material(
    course_id: UUID,
    file: UploadFile = File(...),
    material_type: str = Query(default="lecture"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer),
) -> CourseMaterialResponse:
    """Upload a material to a course. Lecturer or Admin only."""
    course = await get_course_or_404(db, course_id)
    await verify_course_ownership(course, current_user)

    filename = sanitize_filename(file.filename)
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    allowed_exts = {"pdf", "doc", "docx", "png", "jpg", "jpeg", "mp4", "webm"}
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format: .{ext}. Allowed: PDF, DOC, DOCX, PNG, JPG, MP4, WebM."
        )

    content = await read_upload_file_safely(file, max_size_bytes=100 * 1024 * 1024)
    file_size_bytes = len(content)

    minio_key = f"course_materials/{course_id}/{uuid.uuid4()}.{ext}"
    try:
        minio_client = MinioClient()
        storage_uri = minio_client.upload_file(content, minio_key, file.content_type)
    except Exception:
        import logging
        logging.exception("MinIO upload failed for course %s", course_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store file"
        )

    repo = CourseMaterialRepository(db)
    material = CourseMaterial(
        course_id=course_id,
        lecturer_id=current_user.id,
        file_name=filename,
        file_type=ext,
        file_url=storage_uri,
        storage_key=minio_key,
        file_size=file_size_bytes,
        status="processing",
        material_type=material_type,
    )
    material = await repo.create(material)

    if ext == "pdf":
        from app.tasks.lesson_tasks import dispatch_process_course_file
        dispatch_process_course_file(
            storage_key=minio_key,
            course_id=str(course_id),
            material_id=str(material.id),
            source_type="course_material",
            file_name=filename,
        )

    return _to_response(material)


@router.post("/external", response_model=CourseMaterialResponse, status_code=201)
async def add_external_url(
    course_id: UUID,
    url: str = Query(...),
    material_type: str = Query(default="reference"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer),
) -> CourseMaterialResponse:
    """Add an external URL as course material. Lecturer or Admin only."""
    course = await get_course_or_404(db, course_id)
    await verify_course_ownership(course, current_user)

    repo = CourseMaterialRepository(db)
    material = CourseMaterial(
        course_id=course_id,
        lecturer_id=current_user.id,
        file_type="url",
        external_url=url,
        status="ready",
        material_type=material_type,
    )
    material = await repo.create(material)

    return _to_response(material)


@router.put("/{material_id}", response_model=CourseMaterialResponse)
async def update_material(
    course_id: UUID,
    material_id: UUID,
    payload: CourseMaterialUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer),
) -> CourseMaterialResponse:
    """Update a material. Lecturer or Admin only."""
    course = await get_course_or_404(db, course_id)
    await verify_course_ownership(course, current_user)

    repo = CourseMaterialRepository(db)
    material = await repo.get_by_id(material_id)
    if not material or material.course_id != course_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found")

    if payload.file_name is not None:
        material.file_name = payload.file_name
    if payload.material_type is not None:
        material.material_type = payload.material_type

    await db.commit()
    await db.refresh(material)

    return _to_response(material)


@router.delete("/{material_id}", status_code=204)
async def delete_material(
    course_id: UUID,
    material_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer),
) -> None:
    """Delete a material. Lecturer or Admin only."""
    course = await get_course_or_404(db, course_id)
    await verify_course_ownership(course, current_user)

    repo = CourseMaterialRepository(db)
    material = await repo.get_by_id(material_id)
    if not material or material.course_id != course_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found")

    if material.storage_key:
        try:
            MinioClient().delete_file(material.storage_key)
        except Exception:
            pass

    await repo.delete(material_id)