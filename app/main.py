"""Learning Hub API - Main FastAPI Entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api.v1 import api_router
from app.clients.ai_client import close_ai_client, get_ai_client

# Lifespan singletons
from app.core.cache import close_redis, get_redis_client
from app.core.config import settings

# Rate limiting
from app.core.limiter import limiter, rate_limit_exceeded_handler


from app.core.logging import configure_logging, get_logger

logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events to manage shared resource connection pools"""
    configure_logging(settings.DEBUG)
    logger.info("Initializing connection pools...")
    # 1. Initialize Redis Pool
    get_redis_client()
    # 2. Initialize AI Service Async Client Pool
    get_ai_client()
    # Encrypt any AI keys created by versions that stored plaintext values.
    try:
        from app.core.database import AsyncSessionLocal
        from app.core.secret_store import migrate_legacy_ai_keys

        async with AsyncSessionLocal() as db:
            migrated = await migrate_legacy_ai_keys(db)
            if migrated:
                logger.info("Encrypted %d legacy AI API key(s)", migrated)
    except Exception:
        logger.exception("Could not migrate legacy AI API keys")

    # Synchronize AI keys to AI service on startup
    try:
        from app.api.v1.admin import _sync_active_keys_to_ai_service
        async with AsyncSessionLocal() as db:
            await _sync_active_keys_to_ai_service(db)
            logger.info("Synchronized active AI API keys to AI service on startup")
    except Exception as exc:
        logger.warning("Could not sync active AI API keys on startup: %s", exc)

    # Safe schema evolution for quiz_attempts.answers_detail and lesson multimodal fields
    try:
        from sqlalchemy import text
        async with AsyncSessionLocal() as db:
            await db.execute(text("ALTER TABLE quiz_attempts ADD COLUMN IF NOT EXISTS answers_detail JSONB DEFAULT '[]'::jsonb;"))
            await db.execute(text("ALTER TABLE lessons ADD COLUMN IF NOT EXISTS mindmap_markdown TEXT NULL;"))
            await db.execute(text("ALTER TABLE lessons ADD COLUMN IF NOT EXISTS audio_summary_url VARCHAR(500) NULL;"))
            await db.commit()
    except Exception as exc:
        logger.debug("Schema evolution notice: %s", exc)

    # Periodic background task to persist AI key usage metrics to DB
    import asyncio
    async def _periodic_key_usage_sync():
        while True:
            try:
                await asyncio.sleep(60)
                from app.api.v1.admin import sync_ai_key_usage_to_db
                async with AsyncSessionLocal() as db:
                    await sync_ai_key_usage_to_db(db)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("Periodic AI key usage sync skipped: %s", exc)

    key_sync_task = asyncio.create_task(_periodic_key_usage_sync())

    yield

    if key_sync_task and not key_sync_task.done():
        key_sync_task.cancel()
        try:
            await key_sync_task
        except asyncio.CancelledError:
            pass

    logger.info("Closing connection pools...")
    # 3. Clean up Redis Pool
    await close_redis()
    # 4. Clean up HTTP Client Pool
    await close_ai_client()


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan,
)

# Rate Limiter setup
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Middlewares
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Internal-API-Key"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
trusted_proxy_hosts = [host.strip() for host in settings.TRUSTED_PROXY_IPS.split(",") if host.strip()]
app.add_middleware(
    ProxyHeadersMiddleware,
    trusted_hosts=trusted_proxy_hosts or ["127.0.0.1", "::1"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    is_viewer_content = request.url.path.startswith("/api/v1/documents/") and (
        request.url.path.endswith("/content") or "/raw/" in request.url.path
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Allow the SPA to embed same-origin document bytes in <iframe>;
    # default DENY would block every inline PDF preview.
    response.headers["X-Frame-Options"] = "SAMEORIGIN" if is_viewer_content else "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if not settings.DEBUG:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if is_viewer_content:
            # PDF bytes are embedded in an <iframe> by the SPA (blob: or same-origin).
            # frame-ancestors 'none' + object-src 'none' would force the grey/blank
            # viewer even when bytes stream fine — allow the SPA origins instead.
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; base-uri 'self'; form-action 'self'; "
                "frame-ancestors 'self' https://learninghubs.tech https://www.learninghubs.tech; "
                "object-src 'self' blob:; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob: https:; font-src 'self' data:"
            )
        else:
            response.headers["Content-Security-Policy"] = "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:"
    return response

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health():
    """Simple ping health endpoint."""
    return {"status": "healthy"}


@app.get("/health/ready")
async def readiness():
    """Enterprise readiness probe verifying critical infrastructure dependencies."""
    checks = {"database": "unknown", "redis": "unknown"}

    # Check Redis
    try:
        redis = get_redis_client()
        if await redis.ping():
            checks["redis"] = "healthy"
    except Exception:
        checks["redis"] = "unhealthy"

    # Check Database
    try:
        from sqlalchemy import text
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception:
        checks["database"] = "unhealthy"

    is_ready = all(v == "healthy" for v in checks.values())
    status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=status_code, content={"status": "ready" if is_ready else "degraded", "dependencies": checks})


# Global Exception Handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """Custom handler to output JSON format for HTTPExceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "http_error",
            "message": exc.detail,
            "details": getattr(exc, "headers", None)
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    """Custom handler to output structured JSON for validation failures."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "validation_error",
            "message": "Invalid request payload",
            "details": jsonable_encoder(exc.errors())
        }
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Custom handler to catch unhandled errors and prevent server detail leakage."""
    logging.exception("Unhandled exception: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred on the server.",
        }
    )
