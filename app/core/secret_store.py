"""Encrypt service secrets before persisting them in the database."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.ai_key import AiApiKey

PREFIX = "enc:v1:"


def _cipher() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    if value.startswith(PREFIX):
        return value
    return PREFIX + _cipher().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    if not value.startswith(PREFIX):
        # Legacy rows are accepted for one migration pass and are re-encrypted
        # by the admin key synchronization routine.
        return value
    try:
        return _cipher().decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Stored secret cannot be decrypted") from exc


async def migrate_legacy_ai_keys(db: AsyncSession) -> int:
    """Encrypt legacy plaintext AI keys during application startup."""
    result = await db.execute(select(AiApiKey))
    keys = result.scalars().all()
    changed = 0
    for key in keys:
        encrypted = encrypt_secret(key.api_key)
        if encrypted != key.api_key:
            key.api_key = encrypted
            changed += 1
    if changed:
        await db.commit()
    return changed
