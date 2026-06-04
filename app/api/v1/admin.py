"""Admin API endpoints."""

from fastapi import APIRouter, Depends, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.dependencies.auth import require_admin
from app.dependencies.db import get_db
from app.models.user import User
from app.models.document import Document
from app.repositories.user_repo import UserRepository

# Caching & limiters
from app.core.limiter import limiter
from app.core.config import settings
from app.core.cache import RedisCache, get_redis_client
from app.clients.ai_client import get_ai_client

router = APIRouter()


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

    overall = "healthy" if all(v == "healthy" for v in services.values()) else "degraded"

    return {"status": overall, "services": services}
