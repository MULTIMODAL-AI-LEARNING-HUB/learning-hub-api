"""Admin endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.dependencies.auth import require_admin
from app.dependencies.db import get_db
from app.models.user import User
from app.models.document import Document

router = APIRouter()


@router.get("/users")
async def list_users(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    offset = (page - 1) * page_size
    result = await db.execute(select(User).offset(offset).limit(page_size))
    users = result.scalars().all()

    total_result = await db.execute(select(func.count(User.id)))
    total = total_result.scalar()

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
async def analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    users_count = (await db.execute(select(func.count(User.id)))).scalar()
    docs_count = (await db.execute(select(func.count(Document.id)))).scalar()
    docs_ready = (
        await db.execute(select(func.count(Document.id)).where(Document.status == "ready"))
    ).scalar()
    docs_processing = (
        await db.execute(select(func.count(Document.id)).where(Document.status == "processing"))
    ).scalar()

    return {
        "total_users": users_count,
        "total_documents": docs_count,
        "documents_ready": docs_ready,
        "documents_processing": docs_processing,
    }


@router.get("/health")
async def health(
    db: AsyncSession = Depends(get_db),
):
    services = {}

    try:
        await db.execute(select(func.count(User.id)))
        services["database"] = "healthy"
    except Exception:
        services["database"] = "unhealthy"

    import httpx
    from app.core.config import settings

    try:
        resp = httpx.get(f"{settings.AI_SERVICE_URL}/health", timeout=5)
        services["ai_service"] = "healthy" if resp.status_code == 200 else "unhealthy"
    except Exception:
        services["ai_service"] = "unhealthy"

    import redis as r
    try:
        r_client = r.from_url(settings.REDIS_URL)
        r_client.ping()
        services["redis"] = "healthy"
    except Exception:
        services["redis"] = "unhealthy"

    overall = "healthy" if all(v == "healthy" for v in services.values()) else "degraded"

    return {"status": overall, "services": services}
