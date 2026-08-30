from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models import User
from app.models.social_chat import (
    SocialChatMember,
    SocialChatMessage,
    SocialChatRoom,
    utc_now_naive,
)
from app.schemas.social_chat import (
    SocialChatMessageCreate,
    SocialChatMessageResponse,
    SocialChatMessagesResponse,
    SocialChatRoomCreate,
    SocialChatRoomResponse,
    SocialChatRoomsResponse,
    SocialChatUserResponse,
)

router = APIRouter(prefix="/social-chat", tags=["social-chat"])


async def ensure_room_member(room_id: UUID, user: User, db: AsyncSession) -> SocialChatRoom:
    room = await db.get(SocialChatRoom, room_id)
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat room not found")

    membership = (
        await db.execute(
            select(SocialChatMember.id).where(
                SocialChatMember.room_id == room_id,
                SocialChatMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chat room membership required")
    return room


def serialize_message(message: SocialChatMessage, sender: User) -> SocialChatMessageResponse:
    return SocialChatMessageResponse(
        id=message.id,
        room_id=message.room_id,
        sender_id=message.sender_id,
        sender_name=sender.full_name,
        sender_avatar_url=sender.avatar_url,
        sender_role=sender.role,
        content=message.content,
        created_at=message.created_at,
    )


@router.get("/users", response_model=list[SocialChatUserResponse])
async def search_users(
    q: str = Query(default="", max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SocialChatUserResponse]:
    normalized = f"%{q.strip().lower()}%"
    conditions = [User.id != current_user.id, User.is_active.is_(True)]
    if q.strip():
        conditions.append(or_(func.lower(User.full_name).like(normalized), func.lower(User.email).like(normalized)))

    users = (
        await db.execute(
            select(User)
            .where(and_(*conditions))
            .order_by(User.full_name.asc().nullslast(), User.email.asc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        SocialChatUserResponse(id=user.id, full_name=user.full_name, email=user.email, avatar_url=user.avatar_url, role=user.role)
        for user in users
    ]


@router.get("/rooms", response_model=SocialChatRoomsResponse)
async def list_rooms(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SocialChatRoomsResponse:
    rooms = (
        await db.execute(
            select(SocialChatRoom)
            .join(SocialChatMember, SocialChatMember.room_id == SocialChatRoom.id)
            .where(SocialChatMember.user_id == current_user.id)
            .order_by(SocialChatRoom.updated_at.desc())
        )
    ).scalars().all()

    items: list[SocialChatRoomResponse] = []
    for room in rooms:
        member_count = (
            await db.execute(select(func.count(SocialChatMember.id)).where(SocialChatMember.room_id == room.id))
        ).scalar_one()
        last_message = (
            await db.execute(
                select(SocialChatMessage.content)
                .where(SocialChatMessage.room_id == room.id)
                .order_by(SocialChatMessage.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        items.append(
            SocialChatRoomResponse(
                id=room.id,
                name=room.name,
                description=room.description,
                kind=room.kind,
                member_count=member_count,
                last_message=last_message,
                updated_at=room.updated_at,
            )
        )

    return SocialChatRoomsResponse(items=items, total=len(items))


@router.post("/rooms", response_model=SocialChatRoomResponse, status_code=status.HTTP_201_CREATED)
async def create_room(
    payload: SocialChatRoomCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SocialChatRoomResponse:
    member_ids = list(dict.fromkeys([*payload.member_ids, current_user.id]))
    if len(member_ids) > 50:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A room can have at most 50 members")

    valid_members = (
        await db.execute(select(User.id).where(User.id.in_(member_ids), User.is_active.is_(True)))
    ).scalars().all()
    if current_user.id not in valid_members:
        valid_members.append(current_user.id)

    room = SocialChatRoom(
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        kind="group",
        created_by=current_user.id,
    )
    db.add(room)
    await db.flush()

    for user_id in valid_members:
        db.add(SocialChatMember(room_id=room.id, user_id=user_id, role="owner" if user_id == current_user.id else "member"))

    await db.commit()
    await db.refresh(room)
    return SocialChatRoomResponse(
        id=room.id,
        name=room.name,
        description=room.description,
        kind=room.kind,
        member_count=len(valid_members),
        last_message=None,
        updated_at=room.updated_at,
    )


@router.get("/rooms/{room_id}/messages", response_model=SocialChatMessagesResponse)
async def list_messages(
    room_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    before: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SocialChatMessagesResponse:
    await ensure_room_member(room_id, current_user, db)
    query = (
        select(SocialChatMessage, User)
        .join(User, User.id == SocialChatMessage.sender_id)
        .where(SocialChatMessage.room_id == room_id)
        .order_by(SocialChatMessage.created_at.desc())
        .limit(limit)
    )
    if before:
        pivot = await db.get(SocialChatMessage, before)
        if pivot:
            query = query.where(SocialChatMessage.created_at < pivot.created_at)

    rows = (await db.execute(query)).all()
    total = (
        await db.execute(select(func.count(SocialChatMessage.id)).where(SocialChatMessage.room_id == room_id))
    ).scalar_one()
    return SocialChatMessagesResponse(items=[serialize_message(message, sender) for message, sender in reversed(rows)], total=total)


@router.post("/rooms/{room_id}/messages", response_model=SocialChatMessageResponse, status_code=status.HTTP_201_CREATED)
async def create_message(
    room_id: UUID,
    payload: SocialChatMessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SocialChatMessageResponse:
    room = await ensure_room_member(room_id, current_user, db)
    message = SocialChatMessage(room_id=room_id, sender_id=current_user.id, content=payload.content.strip())
    room.updated_at = utc_now_naive()
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return serialize_message(message, current_user)
