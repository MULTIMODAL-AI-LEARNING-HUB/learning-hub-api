"""Course API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user, require_lecturer
from app.dependencies.db import get_db
from app.models.user import User
from app.repositories.course_repo import CourseRepository
from app.repositories.course_material_repo import CourseMaterialRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.schemas import (
    CourseCreate,
    CourseDetailResponse,
    CourseListResponse,
    CourseResponse,
    CourseUpdate,
)
from app.services.course_service import CourseService
from app.utils.pagination import build_pagination
from app.core.cache import RedisCache
from app.core.config import settings

router = APIRouter()


def _to_response(course) -> CourseResponse:
    return CourseResponse(
        id=course.id,
        lecturer_id=course.lecturer_id,
        category_id=course.category_id,
        title=course.title,
        description=course.description,
        thumbnail_url=course.thumbnail_url,
        price_vnd=course.price_vnd,
        price=course.price_vnd,
        status=course.status,
        level=course.level,
        language=course.language,
        requirements=course.requirements,
        learning_outcomes=course.learning_outcomes,
        tags=course.tags,
        view_count=course.view_count,
        rating_avg=float(course.rating_avg) if course.rating_avg else 0,
        rating_count=course.rating_count,
        enrollment_count=0,
        created_at=course.created_at,
        updated_at=course.updated_at,
        lecturer=course.lecturer,
        category=course.category,
    )


@router.get("", response_model=CourseListResponse)
async def list_courses(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = None,
    category_id: UUID | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CourseListResponse:
    """List published courses with search and filters."""
    cache = RedisCache()
    cache_key = RedisCache.cache_key_courses_list(page, page_size, search, category_id, min_price, max_price, sort_by, sort_order)
    cached = await cache.get(cache_key)
    if cached:
        return CourseListResponse(**cached)

    repo = CourseRepository(db)
    service = CourseService(repo)

    courses, total = await service.list_published(
        offset=(page - 1) * page_size,
        limit=page_size,
        search=search,
        category_id=category_id,
        min_price=min_price,
        max_price=max_price,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    pagination = build_pagination(total, page, page_size)

    response = CourseListResponse(
        items=[_to_response(c) for c in courses],
        total=pagination["total"],
        page=pagination["page"],
        page_size=pagination["page_size"],
    )
    await cache.set(cache_key, response.model_dump(mode="json"), ttl=settings.REDIS_CACHE_TTL_COURSES)
    return response


@router.get("/lecturer", response_model=CourseListResponse)
async def list_my_courses(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer),
) -> CourseListResponse:
    """List lecturer's own courses."""
    repo = CourseRepository(db)
    service = CourseService(repo)

    courses, total = await service.list_by_lecturer(
        lecturer_id=current_user.id,
        offset=(page - 1) * page_size,
        limit=page_size,
    )

    pagination = build_pagination(total, page, page_size)

    return CourseListResponse(
        items=[_to_response(c) for c in courses],
        total=pagination["total"],
        page=pagination["page"],
        page_size=pagination["page_size"],
    )


@router.get("/{course_id}", response_model=CourseDetailResponse)
async def get_course(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CourseDetailResponse:
    """Get course details with materials and enrollment counts."""
    cache = RedisCache()
    cache_key = RedisCache.cache_key_course_detail(course_id)
    cached = await cache.get(cache_key)
    if cached:
        return CourseDetailResponse(**cached)

    repo = CourseRepository(db)
    service = CourseService(repo)

    course = await service.get_by_id_with_materials(course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    material_repo = CourseMaterialRepository(db)
    enrollment_repo = EnrollmentRepository(db)

    materials_count = await material_repo.count_by_course(course_id)
    enrolled_count = await enrollment_repo.count_by_course(course_id)

    response = CourseDetailResponse(
        id=course.id,
        lecturer_id=course.lecturer_id,
        category_id=course.category_id,
        title=course.title,
        description=course.description,
        thumbnail_url=course.thumbnail_url,
        price_vnd=course.price_vnd,
        status=course.status,
        created_at=course.created_at,
        updated_at=course.updated_at,
        lecturer=course.lecturer,
        category=course.category,
        materials_count=materials_count,
        enrolled_count=enrolled_count,
    )
    await cache.set(cache_key, response.model_dump(mode="json"), ttl=settings.REDIS_CACHE_TTL_COURSES)
    return response


@router.post("", response_model=CourseResponse, status_code=201)
async def create_course(
    payload: CourseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer),
) -> CourseResponse:
    """Create a new course. Lecturer or Admin only."""
    repo = CourseRepository(db)
    service = CourseService(repo)

    course = await service.create(
        lecturer_id=current_user.id,
        title=payload.title,
        description=payload.description,
        category_id=payload.category_id,
        price_vnd=payload.price_vnd,
        thumbnail_url=payload.thumbnail_url,
    )
    await RedisCache().delete_pattern("cache:courses:*")
    return _to_response(course)


@router.put("/{course_id}", response_model=CourseResponse)
async def update_course(
    course_id: UUID,
    payload: CourseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer),
) -> CourseResponse:
    """Update a course. Owner or Admin only."""
    repo = CourseRepository(db)
    service = CourseService(repo)

    course = await service.get_by_id(course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    if course.lecturer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this course")

    updated = await service.update(
        course_id=course_id,
        title=payload.title,
        description=payload.description,
        category_id=payload.category_id,
        price_vnd=payload.price_vnd,
        thumbnail_url=payload.thumbnail_url,
    )
    await RedisCache().delete_pattern("cache:courses:*")
    return _to_response(updated)


@router.post("/{course_id}/publish", response_model=CourseResponse)
async def publish_course(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer),
) -> CourseResponse:
    """Publish a course. Owner or Admin only."""
    repo = CourseRepository(db)
    service = CourseService(repo)

    course = await service.get_by_id(course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    if course.lecturer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    updated = await service.publish(course_id)
    await RedisCache().delete_pattern("cache:courses:*")
    return _to_response(updated)


@router.post("/{course_id}/archive", response_model=CourseResponse)
async def archive_course(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer),
) -> CourseResponse:
    """Archive a course. Owner or Admin only."""
    repo = CourseRepository(db)
    service = CourseService(repo)

    course = await service.get_by_id(course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    if course.lecturer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    updated = await service.archive(course_id)
    await RedisCache().delete_pattern("cache:courses:*")
    return _to_response(updated)


@router.delete("/{course_id}", status_code=204)
async def delete_course(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lecturer),
) -> None:
    """Delete a course. Owner or Admin only."""
    repo = CourseRepository(db)
    service = CourseService(repo)

    course = await service.get_by_id(course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    if course.lecturer_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    await service.delete(course_id)
    await RedisCache().delete_pattern("cache:courses:*")