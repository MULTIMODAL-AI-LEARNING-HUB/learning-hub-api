"""Quota and AI token accounting service."""

import math
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quota import Quota
from app.models.user import User

DEFAULT_TOKEN_LIMIT = 2000000
DEFAULT_STORAGE_LIMIT_MB = 10240


def estimate_tokens(query: str = "", answer: str = "") -> int:
    """Accurately estimate AI tokens for Vietnamese/English query + answer.

    1 token is approximately 3.5 characters for mixed Vietnamese and English/code text.
    Floor at 25 tokens minimum per turn.
    """
    total_chars = len(query.strip()) + len(answer.strip())
    return max(25, math.ceil(total_chars / 3.5))


async def get_or_create_quota(db: AsyncSession, user_id: UUID) -> Quota:
    """Retrieve user quota or create default if not yet provisioned."""
    res = await db.execute(select(Quota).where(Quota.user_id == user_id))
    quota = res.scalar_one_or_none()
    if not quota:
        quota = Quota(
            user_id=user_id,
            storage_limit_mb=DEFAULT_STORAGE_LIMIT_MB,
            storage_used_mb=0,
            video_limit=50,
            video_used=0,
            token_limit=DEFAULT_TOKEN_LIMIT,
            token_used=0,
        )
        db.add(quota)
        await db.flush()
    elif (quota.token_limit or 0) < DEFAULT_TOKEN_LIMIT:
        quota.token_limit = DEFAULT_TOKEN_LIMIT
    return quota


async def check_ai_token_quota(db: AsyncSession, user: User) -> None:
    """Raise 429 if the user has exhausted their 2M AI token limit."""
    quota = user.quota
    if not quota:
        quota = await get_or_create_quota(db, user.id)
    token_limit = quota.token_limit or DEFAULT_TOKEN_LIMIT
    token_used = quota.token_used or 0
    if token_used >= token_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Bạn đã sử dụng hết hạn mức {token_limit:,} token AI. Vui lòng liên hệ quản trị viên để mở rộng hạn mức.",
        )


async def consume_ai_tokens(db: AsyncSession, user_id: UUID, tokens: int) -> int:
    """Increment token_used by tokens and commit."""
    if tokens <= 0:
        return 0
    quota = await get_or_create_quota(db, user_id)
    quota.token_used = (quota.token_used or 0) + tokens
    await db.commit()
    return quota.token_used
