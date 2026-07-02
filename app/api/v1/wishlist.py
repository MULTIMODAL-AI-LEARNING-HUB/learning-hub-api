from fastapi import APIRouter, Depends, HTTPException, status
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import WishlistItem, Course
from app.schemas.wishlist import WishlistItemResponse
from app.dependencies.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/wishlist", tags=["wishlist"])


@router.get("", response_model=list[WishlistItemResponse])
async def list_wishlist(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        select(WishlistItem)
        .where(WishlistItem.user_id == current_user.id)
        .options(selectinload(WishlistItem.course))
        .order_by(WishlistItem.created_at.desc())
    )
    result = await db.execute(query)
    items = result.scalars().all()

    return [
        WishlistItemResponse(
            id=item.id,
            user_id=item.user_id,
            course_id=item.course_id,
            course_title=item.course.title if item.course else None,
            course_thumbnail=item.course.thumbnail_url if item.course else None,
            course_price=item.course.price_vnd if item.course else None,
            created_at=item.created_at,
        )
        for item in items
    ]


@router.post("/{course_id}", response_model=WishlistItemResponse, status_code=status.HTTP_201_CREATED)
async def add_to_wishlist(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    course_result = await db.execute(select(Course).where(Course.id == course_id))
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    existing = await db.execute(
        select(WishlistItem).where(
            WishlistItem.user_id == current_user.id,
            WishlistItem.course_id == course_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Course already in wishlist")

    item = WishlistItem(user_id=current_user.id, course_id=course_id)
    db.add(item)
    await db.commit()
    await db.refresh(item)

    return WishlistItemResponse(
        id=item.id,
        user_id=item.user_id,
        course_id=item.course_id,
        course_title=course.title,
        course_thumbnail=course.thumbnail_url,
        course_price=course.price_vnd,
        created_at=item.created_at,
    )


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_wishlist(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(WishlistItem).where(
            WishlistItem.user_id == current_user.id,
            WishlistItem.course_id == course_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Wishlist item not found")

    await db.delete(item)
    await db.commit()


@router.get("/check/{course_id}", response_model=dict)
async def check_wishlist(
    course_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(WishlistItem).where(
            WishlistItem.user_id == current_user.id,
            WishlistItem.course_id == course_id,
        )
    )
    item = result.scalar_one_or_none()
    return {"is_wishlisted": item is not None}
