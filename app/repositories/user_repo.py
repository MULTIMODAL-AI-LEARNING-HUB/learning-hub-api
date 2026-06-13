"""User repository."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    async def get_by_id(self, user_id: UUID) -> User | None:
        result = await self.db.execute(
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.quota))
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(
            select(User)
            .where(User.email == email)
            .options(selectinload(User.quota))
        )
        return result.scalar_one_or_none()

    async def create(self, user: User) -> User:
        self.db.add(user)
        await self.db.commit()
        # Retrieve the user eagerly loaded with quota after committing
        result = await self.db.execute(
            select(User)
            .where(User.id == user.id)
            .options(selectinload(User.quota))
        )
        return result.scalar_one()

    async def count_all(self) -> int:
        from sqlalchemy import func
        result = await self.db.execute(select(func.count(User.id)))
        return result.scalar() or 0

    async def list_all(self, offset: int, limit: int) -> list[User]:
        result = await self.db.execute(
            select(User)
            .order_by(User.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def set_reset_token(self, user_id: UUID, token: str, expiry: datetime) -> None:
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.reset_token = token
            user.reset_token_expiry = expiry
            await self.db.commit()

    async def get_user_by_reset_token(self, token: str) -> User | None:
        result = await self.db.execute(
            select(User)
            .where(User.reset_token == token, User.reset_token_expiry > datetime.now(timezone.utc).replace(tzinfo=None))
            .options(selectinload(User.quota))
        )
        return result.scalar_one_or_none()

    async def update_password(self, user_id: UUID, new_password_hash: str) -> None:
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.password_hash = new_password_hash
            user.reset_token = None
            user.reset_token_expiry = None
            await self.db.commit()

    async def clear_reset_token(self, user_id: UUID) -> None:
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.reset_token = None
            user.reset_token_expiry = None
            await self.db.commit()
