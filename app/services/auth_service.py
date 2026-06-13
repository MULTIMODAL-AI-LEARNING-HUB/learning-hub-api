import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status

from app.core.security import create_access_token, create_refresh_token, hash_password, verify_password
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.services.email_service import EmailService


RESET_TOKEN_EXPIRE_MINUTES = 30


class AuthService:
    def __init__(self, repo: UserRepository):
        self.repo = repo

    async def register(self, email: str, password: str, full_name: str | None) -> User:
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
            quota=quota,
        )
        user = await self.repo.create(user)
        return user

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.repo.get_by_email(email)
        if not user or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
        return user

    async def forgot_password(self, email: str) -> None:
        user = await self.repo.get_by_email(email)
        if not user:
            return

        token = secrets.token_urlsafe(32)
        expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
        await self.repo.set_reset_token(user.id, token, expiry)
        await EmailService.send_password_reset(user.email, token, user.full_name)

    async def reset_password(self, token: str, new_password: str) -> None:
        user = await self.repo.get_user_by_reset_token(token)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token"
            )
        await self.repo.update_password(user.id, hash_password(new_password))

    @staticmethod
    def build_access_token(user_id: UUID) -> str:
        return create_access_token({"sub": str(user_id)})

    @staticmethod
    def build_refresh_token(user_id: UUID) -> str:
        return create_refresh_token({"sub": str(user_id)})
