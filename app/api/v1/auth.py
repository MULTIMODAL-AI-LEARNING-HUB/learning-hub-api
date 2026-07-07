"""Auth API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.core.security import decode_token
from app.schemas import (
    AuthResponse,
    AuthUserResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UpdateProfileRequest,
)
from app.services.auth_service import AuthService

from app.core.limiter import limiter
from app.core.config import settings
from app.core.cache import RedisCache

router = APIRouter()


def _build_user_response(user: User) -> AuthUserResponse:
    from app.schemas.auth import QuotaResponse
    quota_resp = None
    if user.quota:
        quota_resp = QuotaResponse(
            storage_limit_mb=user.quota.storage_limit_mb,
            storage_used_mb=float(user.quota.storage_used_mb),
            video_limit=user.quota.video_limit,
            video_used=user.quota.video_used,
            token_limit=user.quota.token_limit,
            token_used=user.quota.token_used
        )
    return AuthUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        role=user.role,
        created_at=user.created_at,
        quota=quota_resp,
    )


@router.post("/register", response_model=AuthResponse, status_code=201)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def register(
    request: Request,
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db)
) -> AuthResponse:
    """Register a new user, automatically provisioning a default quota."""
    service = AuthService(UserRepository(db))
    user = await service.register(payload.email, payload.password, payload.full_name)
    access_token = service.build_access_token(user.id, user.token_version or 0)
    refresh_token = service.build_refresh_token(user.id, user.token_version or 0)
    return AuthResponse(
        user=_build_user_response(user),
        token=TokenResponse(access_token=access_token, refresh_token=refresh_token)
    )


@router.post("/login", response_model=AuthResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def login(
    request: Request,
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db)
) -> AuthResponse:
    """Authenticate credentials and return JWT tokens."""
    service = AuthService(UserRepository(db))
    user = await service.authenticate(payload.email, payload.password)
    access_token = service.build_access_token(user.id, user.token_version or 0)
    refresh_token = service.build_refresh_token(user.id, user.token_version or 0)
    return AuthResponse(
        user=_build_user_response(user),
        token=TokenResponse(access_token=access_token, refresh_token=refresh_token)
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def refresh(
    request: Request,
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    """Exchange a valid refresh token for a new pair of access and refresh tokens."""
    token_payload = decode_token(payload.refresh_token)
    if not token_payload or token_payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    # Check if token was revoked
    jti = token_payload.get("jti")
    if jti:
        redis = RedisCache()
        from app.core.cache import get_redis_client
        r = get_redis_client()
        is_revoked = await r.get(f"revoked_token:{jti}")
        if is_revoked:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has been revoked")

    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    repo = UserRepository(db)
    user = await repo.get_by_id(UUID(user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Check token version matches (prevents use after password reset)
    token_version = token_payload.get("ver", 0)
    if token_version != (user.token_version or 0):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalidated. Please login again.")

    # Revoke the old refresh token
    if jti:
        await AuthService.invalidate_refresh_token(jti)

    service = AuthService(repo)
    access_token = service.build_access_token(user.id, user.token_version or 0)
    refresh_token = service.build_refresh_token(user.id, user.token_version or 0)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.get("/me", response_model=AuthUserResponse)
async def me(current_user: User = Depends(get_current_user)) -> AuthUserResponse:
    """Get current authenticated user profile details."""
    cache = RedisCache()
    cache_key = RedisCache.cache_key_profile(current_user.id)
    cached = await cache.get(cache_key)
    if cached:
        return AuthUserResponse(**cached)

    response = _build_user_response(current_user)
    await cache.set(cache_key, response.model_dump(mode="json"), ttl=settings.REDIS_CACHE_TTL_PROFILE)
    return response


@router.put("/me", response_model=AuthUserResponse)
async def update_me(
    payload: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuthUserResponse:
    """Update current authenticated user's profile."""
    repo = UserRepository(db)
    updated = await repo.update_profile(current_user.id, full_name=payload.full_name, avatar_url=payload.avatar_url)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    cache = RedisCache()
    await cache.delete(RedisCache.cache_key_profile(current_user.id))

    return _build_user_response(updated)


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("2/minute")
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    """Send a password reset email if the email exists in the system."""
    service = AuthService(UserRepository(db))
    await service.forgot_password(payload.email)
    return MessageResponse(
        message="If the email exists, a reset link has been sent. Please check your inbox."
    )


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    """Reset password using a valid reset token."""
    service = AuthService(UserRepository(db))
    await service.reset_password(payload.token, payload.password)
    return MessageResponse(message="Password has been reset successfully.")