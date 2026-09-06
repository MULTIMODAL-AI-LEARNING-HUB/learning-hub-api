"""Rate limiting configuration using slowapi."""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from app.core.config import settings


def _get_real_ip(request: Request) -> str:
    """Use the proxy-normalized peer address; never trust a client-supplied XFF."""
    return request.client.host if request.client else "unknown"


limiter = Limiter(
    key_func=_get_real_ip,
    default_limits=["100/minute"],
    storage_uri=settings.REDIS_URL,
    # Never silently fall back to per-process limits; that multiplies the
    # effective brute-force/quota budget across workers.
    in_memory_fallback_enabled=False,
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom response handler for rate limit exceeded errors."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": "Too many requests. Please try again later.",
        },
    )
