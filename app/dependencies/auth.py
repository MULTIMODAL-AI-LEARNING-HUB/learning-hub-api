"""Auth dependencies for request validation."""

from fastapi import Depends, HTTPException, status


def get_current_user():
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Not implemented")


def require_admin(user=Depends(get_current_user)):
    return user
