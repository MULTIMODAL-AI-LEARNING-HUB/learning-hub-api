from datetime import datetime, timedelta, timezone
from uuid import uuid4

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    plain_bytes = plain.encode("utf-8")
    hashed_bytes = hashed.encode("utf-8")
    return bcrypt.checkpw(plain_bytes, hashed_bytes)


def create_access_token(data: dict) -> str:
    return _create_token(data, minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES, token_type="access")


def create_refresh_token(data: dict) -> str:
    return _create_token(
        data,
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS,
        token_type="refresh",
    )


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


def _create_token(
    data: dict,
    minutes: int | None = None,
    days: int | None = None,
    token_type: str | None = None,
) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if minutes is not None:
        expire = now + timedelta(minutes=minutes)
    elif days is not None:
        expire = now + timedelta(days=days)
    else:
        raise ValueError("Token expiry not specified")
    to_encode.update({
        "exp": expire,
        "iat": int(now.timestamp()),
        "jti": str(uuid4()),
    })
    if token_type:
        to_encode.update({"type": token_type})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
