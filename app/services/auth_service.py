import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status

from app.core.security import create_access_token, create_refresh_token, hash_password, verify_password
from app.core.cache import get_redis_client
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.services.email_service import EmailService


RESET_TOKEN_EXPIRE_MINUTES = 30
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 15


class AuthService:
    def __init__(self, repo: UserRepository):
        self.repo = repo

    async def register(self, email: str, password: str, full_name: str | None, role: str = "student") -> User:
        existing = await self.repo.get_by_email(email)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

        from app.models.quota import Quota
        quota = Quota(
            storage_limit_mb=1024,
            storage_used_mb=0,
            video_limit=5,
            video_used=0,
            token_limit=50000,
            token_used=0
        )
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            role=role,
            quota=quota,
        )
        user = await self.repo.create(user)
        return user

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.repo.get_by_email(email)

        # Check brute-force lockout
        if user:
            try:
                redis = get_redis_client()
                lockout_key = f"login_lockout:{user.id}"
                is_locked = await redis.get(lockout_key)
                if is_locked:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=f"Account locked due to too many failed attempts. Try again in {LOGIN_LOCKOUT_MINUTES} minutes."
                    )
            except HTTPException:
                raise
            except Exception as e:
                # Do not crash the app if Redis limit is exceeded or offline
                import logging
                logging.error(f"Redis error checking lockout for {email}: {e}")

        if not user or not user.password_hash or not verify_password(password, user.password_hash):
            # Track failed attempt
            if user:
                try:
                    redis = get_redis_client()
                    fail_key = f"login_fails:{user.id}"
                    attempts = await redis.incr(fail_key)
                    await redis.expire(fail_key, LOGIN_LOCKOUT_MINUTES * 60)
                    if attempts >= MAX_LOGIN_ATTEMPTS:
                        lockout_key = f"login_lockout:{user.id}"
                        await redis.set(lockout_key, "1", ex=LOGIN_LOCKOUT_MINUTES * 60)
                        raise HTTPException(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"Account locked due to too many failed attempts. Try again in {LOGIN_LOCKOUT_MINUTES} minutes."
                        )
                except HTTPException:
                    raise
                except Exception as e:
                    import logging
                    logging.error(f"Redis error tracking login failure for {email}: {e}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        # Clear failed attempts on successful login
        try:
            redis = get_redis_client()
            await redis.delete(f"login_fails:{user.id}")
        except Exception as e:
            import logging
            logging.error(f"Redis error clearing login fails for {email}: {e}")

        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
        return user

    async def google_login(self, token_str: str) -> User:
        import httpx
        from app.core.config import settings

        email = None
        google_id = None
        full_name = None
        avatar_url = None

        # 1. Try decoding as Google ID token (JWT)
        if "." in token_str and not token_str.startswith("ya29."):
            try:
                from google.oauth2 import id_token
                from google.auth.transport import requests as google_requests

                audience = settings.GOOGLE_CLIENT_ID if settings.GOOGLE_CLIENT_ID else None
                id_info = id_token.verify_oauth2_token(
                    token_str,
                    google_requests.Request(),
                    audience=audience
                )
                email = id_info.get("email")
                google_id = id_info.get("sub")
                full_name = id_info.get("name")
                avatar_url = id_info.get("picture")
            except Exception as e:
                import logging
                logging.warning(f"Google ID token verification failed, trying userinfo endpoint: {e}")

        # 2. Fallback: try Google Userinfo API (for Google OAuth Access Token)
        if not email:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        "https://www.googleapis.com/oauth2/v3/userinfo",
                        headers={"Authorization": f"Bearer {token_str}"},
                        timeout=10.0
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        email = data.get("email")
                        google_id = data.get("sub")
                        full_name = data.get("name")
                        avatar_url = data.get("picture")
            except Exception as e:
                import logging
                logging.error(f"Google Userinfo API request failed: {e}")

        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Google token or email not available"
            )

        user = await self.repo.find_or_create_social_user(
            email=email,
            oauth_provider="google",
            google_id=google_id,
            full_name=full_name,
            avatar_url=avatar_url,
        )

        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
        return user

    async def facebook_login(self, access_token: str) -> User:
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://graph.facebook.com/me",
                    params={
                        "fields": "id,name,email,picture.type(large)",
                        "access_token": access_token
                    },
                    timeout=10.0
                )
                if resp.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid Facebook access token"
                    )
                fb_data = resp.json()
        except HTTPException:
            raise
        except Exception as e:
            import logging
            logging.error(f"Facebook Graph API request failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to verify Facebook token"
            )

        facebook_id = fb_data.get("id")
        email = fb_data.get("email")
        # If email is missing (e.g. registered with phone number on Facebook), fallback to pseudo email
        if not email:
            email = f"fb_{facebook_id}@facebook.user"

        full_name = fb_data.get("name")
        avatar_url = None
        picture_data = fb_data.get("picture", {}).get("data", {})
        if isinstance(picture_data, dict):
            avatar_url = picture_data.get("url")

        user = await self.repo.find_or_create_social_user(
            email=email,
            oauth_provider="facebook",
            facebook_id=facebook_id,
            full_name=full_name,
            avatar_url=avatar_url,
        )

        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
        return user

    async def forgot_password(self, email: str) -> None:
        user = await self.repo.get_by_email(email)
        if not user:
            return

        token = secrets.token_urlsafe(32)
        expiry = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
        await self.repo.set_reset_token(user.id, token, expiry)
        await EmailService.send_password_reset(user.email, token, user.full_name)

    async def reset_password(self, token: str, new_password: str) -> None:
        user = await self.repo.get_user_by_reset_token(token)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token"
            )
        # Invalidate all existing tokens by incrementing version
        new_version = (user.token_version or 0) + 1
        await self.repo.update_password(user.id, hash_password(new_password), token_version=new_version)

    @staticmethod
    def build_access_token(user_id: UUID, token_version: int = 0) -> str:
        return create_access_token({"sub": str(user_id), "ver": token_version})

    @staticmethod
    def build_refresh_token(user_id: UUID, token_version: int = 0) -> str:
        return create_refresh_token({"sub": str(user_id), "ver": token_version})

    @staticmethod
    async def invalidate_refresh_token(jti: str) -> None:
        """Blacklist a refresh token by its jti claim."""
        try:
            redis = get_redis_client()
            await redis.set(f"revoked_token:{jti}", "1", ex=LOGIN_LOCKOUT_MINUTES * 60)
        except Exception as e:
            import logging
            logging.error(f"Redis error invalidating refresh token {jti}: {e}")
