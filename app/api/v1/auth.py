"""Auth API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import RedisCache
from app.core.config import settings
from app.core.limiter import limiter
from app.core.security import decode_token
from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas import (
    AuthResponse,
    AuthUserResponse,
    ChangePasswordRequest,
    FacebookLoginRequest,
    ForgotPasswordRequest,
    GoogleLoginRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UpdateProfileRequest,
)
from app.services.auth_service import AuthService

router = APIRouter()
REFRESH_COOKIE_NAME = "refresh_token"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        secure=not settings.DEBUG,
        # The deployed web and API may be on different registrable domains;
        # cross-site cookies are safe here because CORS is an explicit allowlist
        # and the token is HttpOnly.
        samesite="none" if not settings.DEBUG else "lax",
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/v1/auth")


def _enforce_cookie_csrf(request: Request) -> None:
    """Reject cross-origin browser requests that authenticate via cookies."""
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in settings.CORS_ORIGINS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-origin request rejected")


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
        oauth_provider=user.oauth_provider,
        created_at=user.created_at,
        quota=quota_resp,
    )


@router.post("/register", response_model=AuthResponse, status_code=201)
@limiter.limit(settings.RATE_LIMIT_REGISTER)
async def register(
    request: Request,
    payload: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Register a new user, automatically provisioning a default quota."""
    service = AuthService(UserRepository(db))
    user = await service.register(payload.email, payload.password, payload.full_name, payload.role)
    access_token = service.build_access_token(user.id, user.token_version or 0)
    refresh_token = service.build_refresh_token(user.id, user.token_version or 0)
    result = AuthResponse(
        user=_build_user_response(user),
        token=TokenResponse(access_token=access_token)
    )
    _set_refresh_cookie(response, refresh_token)
    return result


@router.post("/login", response_model=AuthResponse)
@limiter.limit(settings.RATE_LIMIT_LOGIN)
async def login(
    request: Request,
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Authenticate credentials and return JWT tokens."""
    service = AuthService(UserRepository(db))
    user = await service.authenticate(payload.email, payload.password)
    access_token = service.build_access_token(user.id, user.token_version or 0)
    refresh_token = service.build_refresh_token(user.id, user.token_version or 0)
    result = AuthResponse(
        user=_build_user_response(user),
        token=TokenResponse(access_token=access_token)
    )
    _set_refresh_cookie(response, refresh_token)
    return result


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    payload: LogoutRequest = LogoutRequest(),
) -> MessageResponse:
    """Invalidate refresh token and log user out."""
    _enforce_cookie_csrf(request)
    refresh_token = (payload.refresh_token if payload else None) or request.cookies.get(REFRESH_COOKIE_NAME)
    if refresh_token:
        token_payload = decode_token(refresh_token)
        if token_payload and token_payload.get("type") == "refresh":
            jti = token_payload.get("jti")
            if jti:
                await AuthService.invalidate_refresh_token(jti)
    _clear_refresh_cookie(response)
    return MessageResponse(message="Successfully logged out")


@router.post("/google", response_model=AuthResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def google_login(
    request: Request,
    payload: GoogleLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Authenticate via Google ID token, creating or updating user, and returning JWT tokens."""
    service = AuthService(UserRepository(db))
    user = await service.google_login(payload.id_token)
    access_token = service.build_access_token(user.id, user.token_version or 0)
    refresh_token = service.build_refresh_token(user.id, user.token_version or 0)
    result = AuthResponse(
        user=_build_user_response(user),
        token=TokenResponse(access_token=access_token)
    )
    _set_refresh_cookie(response, refresh_token)
    return result


@router.post("/facebook", response_model=AuthResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def facebook_login(
    request: Request,
    payload: FacebookLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Authenticate via Facebook access token, creating or updating user, and returning JWT tokens."""
    service = AuthService(UserRepository(db))
    user = await service.facebook_login(payload.access_token)
    access_token = service.build_access_token(user.id, user.token_version or 0)
    refresh_token = service.build_refresh_token(user.id, user.token_version or 0)
    result = AuthResponse(
        user=_build_user_response(user),
        token=TokenResponse(access_token=access_token)
    )
    _set_refresh_cookie(response, refresh_token)
    return result


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def refresh(
    request: Request,
    payload: RefreshRequest,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    """Exchange a valid refresh token for a new pair of access and refresh tokens."""
    _enforce_cookie_csrf(request)
    refresh_token = payload.refresh_token or request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token required")
    token_payload = decode_token(refresh_token)
    if not token_payload or token_payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    # Check if token was revoked
    jti = token_payload.get("jti")
    if jti:
        try:
            from app.core.cache import get_redis_client
            r = get_redis_client()
            is_revoked = await r.get(f"revoked_token:{jti}")
            if is_revoked:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has been revoked")
        except HTTPException:
            raise
        except Exception:
            import logging
            logging.exception("Redis error checking refresh-token revocation")
            raise HTTPException(status_code=503, detail="Authentication service temporarily unavailable")

    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    repo = UserRepository(db)
    try:
        refresh_user_id = UUID(user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    user = await repo.get_by_id(refresh_user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Check token version matches (prevents use after password reset)
    token_version = token_payload.get("ver", 0)
    if token_version != (user.token_version or 0):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalidated. Please login again.")

    # Revoke the old refresh token
    if jti:
        if not await AuthService.invalidate_refresh_token(jti):
            raise HTTPException(status_code=503, detail="Authentication service temporarily unavailable")

    service = AuthService(repo)
    access_token = service.build_access_token(user.id, user.token_version or 0)
    refresh_token = service.build_refresh_token(user.id, user.token_version or 0)
    _set_refresh_cookie(response, refresh_token)
    return TokenResponse(access_token=access_token)


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


@router.post("/change-password", response_model=MessageResponse)
@limiter.limit("5/minute")
async def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Change password for the currently authenticated user.

    Verifies the current password, hashes the new password, bumps
    token_version (invalidating stale sessions), issues fresh tokens to
    preserve the current session, and clears the cached profile.
    """
    from app.core.security import hash_password, verify_password
    from app.services.auth_service import AuthService

    if not current_user.password_hash or not verify_password(
        payload.current_password, current_user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mật khẩu hiện tại không đúng",
        )
    if verify_password(payload.new_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mật khẩu mới phải khác mật khẩu hiện tại",
        )

    service = AuthService(UserRepository(db))
    new_version = (current_user.token_version or 0) + 1
    await service.repo.update_password(
        current_user.id, hash_password(payload.new_password), token_version=new_version
    )
    access_token = service.build_access_token(current_user.id, new_version)
    refresh_token = service.build_refresh_token(current_user.id, new_version)
    _set_refresh_cookie(response, refresh_token)

    cache = RedisCache()
    await cache.delete(RedisCache.cache_key_profile(current_user.id))
    return MessageResponse(message="Đổi mật khẩu thành công")


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
