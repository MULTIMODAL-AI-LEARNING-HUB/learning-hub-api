from uuid import UUID

from fastapi import HTTPException, status

from app.core.security import create_access_token, create_refresh_token, hash_password, verify_password
from app.models.user import User
from app.repositories.user_repo import UserRepository


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

    @staticmethod
    def build_access_token(user_id: UUID) -> str:
        return create_access_token({"sub": str(user_id)})

    @staticmethod
    def build_refresh_token(user_id: UUID) -> str:
        return create_refresh_token({"sub": str(user_id)})
