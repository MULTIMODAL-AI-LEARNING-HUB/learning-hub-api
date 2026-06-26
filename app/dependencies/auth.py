"""Auth dependencies for request validation."""

from uuid import UUID
from functools import wraps

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.dependencies.db import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(User)
        .where(User.id == UUID(user_id))
        .options(selectinload(User.quota))
    )
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
    return user


def require_role(*allowed_roles: str):
    """Dependency factory for role-based access control."""
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role(s): {', '.join(allowed_roles)}"
            )
        return current_user
    return role_checker


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require admin role."""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


def require_lecturer(current_user: User = Depends(get_current_user)) -> User:
    """Require lecturer or admin role."""
    if current_user.role not in ("lecturer", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Lecturer access required")
    return current_user


def require_student(current_user: User = Depends(get_current_user)) -> User:
    """Require student role."""
    if current_user.role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Student access required")
    return current_user


def require_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Alias for get_current_user for clarity."""
    return current_user