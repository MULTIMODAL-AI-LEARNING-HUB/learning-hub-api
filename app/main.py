"""Learning Hub API - Main FastAPI Entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

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
    
    yield
    
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


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if not settings.DEBUG:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:"
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
    except Exception as e:
        checks["redis"] = f"unhealthy: {str(e)}"

    # Check Database
    try:
        from sqlalchemy import text
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception as e:
        checks["database"] = f"unhealthy: {str(e)}"

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
            "details": exc.errors()
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
