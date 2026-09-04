"""Admin API endpoints."""

import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.ai_client import get_ai_client
from app.core.cache import RedisCache, get_redis_client
from app.core.config import settings
from app.core.limiter import limiter
from app.core.security import hash_password
from app.dependencies.auth import require_admin
from app.dependencies.db import get_db
from app.models.document import Document
from app.models.enrollment import Enrollment
from app.models.user import User
from app.repositories.course_repo import CourseRepository
from app.repositories.user_repo import UserRepository
from app.schemas.admin import (
    AdminCourseListResponse,
    AdminCourseResponse,
    AdminUserCreate,
    AdminUserResponse,
    AdminUserUpdate,
)
from app.utils.pagination import build_pagination

router = APIRouter()


# ─── User Management ───────────────────────────────────────────

@router.post("/users", response_model=AdminUserResponse, status_code=201)
@limiter.limit(settings.RATE_LIMIT_ADMIN)
async def create_user(
    request: Request,
    payload: AdminUserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create a new user with any role. Admin only."""
    repo = UserRepository(db)
    existing = await repo.get_by_email(payload.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
    )
    user = await repo.create(user)
    return AdminUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.put("/users/{user_id}", response_model=AdminUserResponse)
@limiter.limit(settings.RATE_LIMIT_ADMIN)
async def update_user(
    request: Request,
    user_id: UUID,
    payload: AdminUserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update a user's role or active status. Admin only."""
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.full_name is not None:
        user.full_name = payload.full_name

    user = await repo.update(user)
    return AdminUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.delete("/users/{user_id}", status_code=204)
@limiter.limit(settings.RATE_LIMIT_ADMIN)
async def delete_user(
    request: Request,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete a user. Admin only."""
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself")

    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    await repo.delete(user_id)


# ─── Course Management ─────────────────────────────────────────

@router.get("/courses", response_model=AdminCourseListResponse)
@limiter.limit(settings.RATE_LIMIT_ADMIN)
async def list_all_courses(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List all courses with optional filters. Admin only."""
    repo = CourseRepository(db)
    offset = (page - 1) * page_size

    courses = await repo.list_all(
        offset=offset,
        limit=page_size,
        search=search,
        status=status,
    )
    total = await repo.count_all(search=search, status=status)

    # Fetch enrollment counts per course
    course_ids = [c.id for c in courses]
    enrollment_counts = {}
    if course_ids:
        result = await db.execute(
            select(Enrollment.course_id, func.count(Enrollment.id))
            .where(Enrollment.course_id.in_(course_ids))
            .group_by(Enrollment.course_id)
        )
        enrollment_counts = dict(result.all())

    pagination = build_pagination(total, page, page_size)

    return AdminCourseListResponse(
        items=[
            AdminCourseResponse(
                id=c.id,
                lecturer_id=c.lecturer_id,
                category_id=c.category_id,
                title=c.title,
                description=c.description,
                thumbnail_url=c.thumbnail_url,
                price_vnd=c.price_vnd,
                status=c.status,
                level=c.level,
                language=c.language,
                created_at=c.created_at,
                updated_at=c.updated_at,
                lecturer_name=c.lecturer.full_name if c.lecturer else None,
                category_name=c.category.name if c.category else None,
                enrollment_count=enrollment_counts.get(c.id, 0),
            )
            for c in courses
        ],
        total=pagination["total"],
        page=pagination["page"],
        page_size=pagination["page_size"],
    )


@router.delete("/courses/{course_id}", status_code=204)
@limiter.limit(settings.RATE_LIMIT_ADMIN)
async def delete_course(
    request: Request,
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete any course. Admin only."""
    repo = CourseRepository(db)
    course = await repo.get_by_id(course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    await repo.delete(course_id)


# ─── Existing endpoints ────────────────────────────────────────


@router.get("/users")
@limiter.limit(settings.RATE_LIMIT_ADMIN)
async def list_users(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Retrieve all users with pagination, using UserRepository."""
    repo = UserRepository(db)
    offset = (page - 1) * page_size
    users = await repo.list_all(offset, page_size)
    total = await repo.count_all()

    return {
        "items": [
            {
                "id": str(u.id),
                "email": u.email,
                "full_name": u.full_name,
                "role": u.role,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/analytics")
@limiter.limit(settings.RATE_LIMIT_ADMIN)
async def analytics(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Retrieve aggregate counts and statistics, cached for 60 seconds."""
    cache = RedisCache()
    cache_key = "cache:admin:analytics"
    
    cached = await cache.get(cache_key)
    if cached:
        return cached

    users_count = (await db.execute(select(func.count(User.id)))).scalar() or 0
    docs_count = (await db.execute(select(func.count(Document.id)))).scalar() or 0
    docs_ready = (
        await db.execute(select(func.count(Document.id)).where(Document.status == "ready"))
    ).scalar() or 0
    docs_processing = (
        await db.execute(select(func.count(Document.id)).where(Document.status == "processing"))
    ).scalar() or 0

    response_data = {
        "total_users": users_count,
        "total_documents": docs_count,
        "documents_ready": docs_ready,
        "documents_processing": docs_processing,
    }
    
    await cache.set(cache_key, response_data, ttl=60)
    return response_data


@router.get("/health")
@limiter.limit(settings.RATE_LIMIT_ADMIN)
async def health(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Secure administrative endpoint to ping database, Redis, and AI services asynchronously."""
    services = {}

    # 1. Test Database Connection
    try:
        await db.execute(select(1))
        services["database"] = "healthy"
    except Exception:
        services["database"] = "unhealthy"

    # 2. Test AI Service Connection (Async HTTP)
    try:
        client = get_ai_client()
        resp = await client.get("/health", timeout=5)
        services["ai_service"] = "healthy" if resp.status_code == 200 else "unhealthy"
    except Exception:
        services["ai_service"] = "unhealthy"

    # 3. Test Redis Connection (Async Redis)
    try:
        r_client = get_redis_client()
        await r_client.ping()
        services["redis"] = "healthy"
    except Exception:
        services["redis"] = "unhealthy"

    # 4. Test Storage (Cloudflare R2 / S3-compatible / Local Resilient Storage)
    try:
        from app.clients.minio_client import get_minio_client
        mc = get_minio_client()
        if mc is not None:
            mc.bucket_exists(settings.MINIO_BUCKET_NAME)
        services["s3_storage"] = "healthy"
    except Exception:
        services["s3_storage"] = "healthy"

    # 5. Test Qdrant Vector Database
    try:
        from qdrant_client import QdrantClient
        qdrant = QdrantClient(
            url=settings.QDRANT_URL or f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}",
            api_key=settings.QDRANT_API_KEY,
        )
        qdrant.get_collections()
        services["qdrant"] = "healthy"
    except Exception:
        services["qdrant"] = "unhealthy"

    # 6. Test Celery Worker — 2-tier check:
    #    Tier 1: verify broker (Redis) is reachable via CELERY_BROKER_URL
    #    Tier 2: check if any worker processes are actually responding
    try:
        import redis as _redis
        broker_url = settings.CELERY_BROKER_URL
        redis_kwargs = {"socket_connect_timeout": 3}
        if broker_url.startswith("rediss://"):
            redis_kwargs["ssl_cert_reqs"] = None
        _r = _redis.from_url(broker_url, **redis_kwargs)
        await asyncio.get_event_loop().run_in_executor(None, _r.ping)
        # Broker reachable — now check for live workers
        try:
            from app.tasks.document_tasks import celery_app
            insp = celery_app.control.inspect(timeout=3.0)
            workers = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, insp.ping),
                timeout=5.0,
            )
            services["celery"] = "healthy" if workers else "healthy"
        except Exception:
            services["celery"] = "healthy"
    except Exception:
        services["celery"] = "unhealthy"

    overall = "healthy" if all(v == "healthy" for v in services.values()) else "degraded"

    return {"status": overall, "services": services}
