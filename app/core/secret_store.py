"""Encrypt service secrets before persisting them in the database."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.ai_key import AiApiKey

PREFIX = "enc:v2:"
LEGACY_PREFIX = "enc:v1:"


def _legacy_cipher() -> Fernet:
    """Decrypt values written by the pre-HKDF implementation during migration."""
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest())
    return Fernet(key)


def _cipher() -> Fernet:
    key_material = settings.AI_KEY_ENCRYPTION_KEY or settings.SECRET_KEY
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"learning-hub/ai-api-key-encryption/v2",
    ).derive(key_material.encode("utf-8"))
    key = base64.urlsafe_b64encode(key)
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    if value.startswith(PREFIX):
        return value
    return PREFIX + _cipher().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    if value.startswith(LEGACY_PREFIX):
        try:
            return _legacy_cipher().decrypt(value[len(LEGACY_PREFIX):].encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
            raise ValueError("Stored legacy secret cannot be decrypted") from exc
    if not value.startswith(PREFIX):
        # Legacy rows are accepted for one migration pass and are re-encrypted
        # by the admin key synchronization routine.
        return value
    try:
        return _cipher().decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Stored secret cannot be decrypted") from exc


async def migrate_legacy_ai_keys(db: AsyncSession) -> int:
    """Re-encrypt plaintext and v1 AI keys with the v2 key derivation scheme."""
    result = await db.execute(select(AiApiKey))
    keys = result.scalars().all()
    changed = 0
    for key in keys:
        if key.api_key.startswith(LEGACY_PREFIX):
            encrypted = encrypt_secret(decrypt_secret(key.api_key))
        else:
            encrypted = encrypt_secret(key.api_key)
        if encrypted != key.api_key:
            key.api_key = encrypted
            changed += 1
    if changed:
        await db.commit()
    return changed
