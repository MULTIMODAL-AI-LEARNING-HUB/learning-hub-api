from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class WishlistItemResponse(BaseModel):
    id: UUID
    user_id: UUID
    course_id: UUID
    course_title: str | None = None
    course_thumbnail: str | None = None
    course_price: int | None = None
    created_at: datetime

    class Config:
        from_attributes = True
