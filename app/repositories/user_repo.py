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

    async def find_or_create_social_user(
        self,
        email: str,
        oauth_provider: str,
        google_id: str | None = None,
        facebook_id: str | None = None,
        full_name: str | None = None,
        avatar_url: str | None = None,
    ) -> User:
        user: User | None = None
        if google_id:
            result = await self.db.execute(
                select(User).where(User.google_id == google_id).options(selectinload(User.quota))
            )
            user = result.scalar_one_or_none()
        elif facebook_id:
            result = await self.db.execute(
                select(User).where(User.facebook_id == facebook_id).options(selectinload(User.quota))
            )
            user = result.scalar_one_or_none()

        if not user:
            user = await self.get_by_email(email)

        if user:
            changed = False
            if google_id and not user.google_id:
                user.google_id = google_id
                changed = True
            if facebook_id and not user.facebook_id:
                user.facebook_id = facebook_id
                changed = True
            if not user.oauth_provider:
                user.oauth_provider = oauth_provider
                changed = True
            if avatar_url and not user.avatar_url:
                user.avatar_url = avatar_url
                changed = True
            if full_name and not user.full_name:
                user.full_name = full_name
                changed = True

            if changed:
                await self.db.commit()
                result = await self.db.execute(
                    select(User).where(User.id == user.id).options(selectinload(User.quota))
                )
                user = result.scalar_one()
            return user
        else:
            from app.models.quota import Quota
            quota = Quota(
                storage_limit_mb=1024,
                storage_used_mb=0,
                video_limit=5,
                video_used=0,
                token_limit=50000,
                token_used=0,
            )
            new_user = User(
                email=email,
                password_hash=None,
                full_name=full_name,
                avatar_url=avatar_url,
                role="student",
                oauth_provider=oauth_provider,
                google_id=google_id,
                facebook_id=facebook_id,
                quota=quota,
            )
            return await self.create(new_user)

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
        import hashlib
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.reset_token = token_hash
            user.reset_token_expiry = expiry
            await self.db.commit()

    async def get_user_by_reset_token(self, token: str) -> User | None:
        import hashlib
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        result = await self.db.execute(
            select(User)
            .where(User.reset_token == token_hash, User.reset_token_expiry > datetime.now(timezone.utc))
            .options(selectinload(User.quota))
        )
        return result.scalar_one_or_none()

    async def update_password(self, user_id: UUID, new_password_hash: str, token_version: int | None = None) -> None:
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.password_hash = new_password_hash
            user.reset_token = None
            user.reset_token_expiry = None
            if token_version is not None:
                user.token_version = token_version
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

    async def update(self, user: User) -> User:
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_profile(self, user_id: UUID, full_name: str | None = None, avatar_url: str | None = None) -> User | None:
        result = await self.db.execute(
            select(User).where(User.id == user_id).options(selectinload(User.quota))
        )
        user = result.scalar_one_or_none()
        if not user:
            return None
        if full_name is not None:
            user.full_name = full_name
        if avatar_url is not None:
            user.avatar_url = avatar_url
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def delete(self, user_id: UUID) -> None:
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            await self.db.delete(user)
            await self.db.commit()
