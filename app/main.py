"""Learning Hub API - Main FastAPI Entrypoint."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.api.v1 import api_router

# Lifespan singletons
from app.core.cache import get_redis_client, close_redis
from app.clients.ai_client import get_ai_client, close_ai_client

# Rate limiting
from app.core.limiter import limiter, rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events to manage shared resource connection pools"""
    # 1. Initialize Redis Pool
    get_redis_client()
    # 2. Initialize AI Service Async Client Pool
    get_ai_client()
    
    yield
    
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
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health():
    """Simple ping health endpoint."""
    return {"status": "healthy"}


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
async def generic_exception_handler(request, exc: Exception):
    """Custom handler to catch unhandled errors and prevent server detail leakage."""
    # Note: In production you would log this exception with traceback
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred on the server.",
        }
    )
