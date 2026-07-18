"""Production-safe release migration repair.

Heroku release can fail if the database alembic_version points at a revision
that is not resolvable in the current release image. This script creates the
chat tables idempotently and stamps Alembic to the current head used by this
release.
"""

import asyncio

from sqlalchemy import text

from app.core.database import engine

HEAD_REVISION = "d3e4f5a6b7c8"


DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS course_chat_messages (
        id UUID PRIMARY KEY,
        course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
        sender_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        content TEXT NOT NULL,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_course_chat_messages_course_id ON course_chat_messages (course_id)",
    "CREATE INDEX IF NOT EXISTS ix_course_chat_messages_sender_id ON course_chat_messages (sender_id)",
    "CREATE INDEX IF NOT EXISTS ix_course_chat_messages_created_at ON course_chat_messages (created_at)",
    """
    CREATE TABLE IF NOT EXISTS social_chat_rooms (
        id UUID PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        description TEXT NULL,
        kind VARCHAR(20) NOT NULL,
        created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_social_chat_rooms_kind ON social_chat_rooms (kind)",
    "CREATE INDEX IF NOT EXISTS ix_social_chat_rooms_created_by ON social_chat_rooms (created_by)",
    "CREATE INDEX IF NOT EXISTS ix_social_chat_rooms_created_at ON social_chat_rooms (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_social_chat_rooms_updated_at ON social_chat_rooms (updated_at)",
    """
    CREATE TABLE IF NOT EXISTS social_chat_members (
        id UUID PRIMARY KEY,
        room_id UUID NOT NULL REFERENCES social_chat_rooms(id) ON DELETE CASCADE,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role VARCHAR(20) NOT NULL,
        joined_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        CONSTRAINT uq_social_chat_room_user UNIQUE (room_id, user_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_social_chat_members_room_id ON social_chat_members (room_id)",
    "CREATE INDEX IF NOT EXISTS ix_social_chat_members_user_id ON social_chat_members (user_id)",
    """
    CREATE TABLE IF NOT EXISTS social_chat_messages (
        id UUID PRIMARY KEY,
        room_id UUID NOT NULL REFERENCES social_chat_rooms(id) ON DELETE CASCADE,
        sender_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        content TEXT NOT NULL,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_social_chat_messages_room_id ON social_chat_messages (room_id)",
    "CREATE INDEX IF NOT EXISTS ix_social_chat_messages_sender_id ON social_chat_messages (sender_id)",
    "CREATE INDEX IF NOT EXISTS ix_social_chat_messages_created_at ON social_chat_messages (created_at)",
    "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)",
    "DELETE FROM alembic_version",
    f"INSERT INTO alembic_version (version_num) VALUES ('{HEAD_REVISION}')",
]


async def main() -> None:
    async with engine.begin() as connection:
        for statement in DDL_STATEMENTS:
            await connection.execute(text(statement))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
