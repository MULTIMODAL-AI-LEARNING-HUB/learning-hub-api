"""Production-safe release migration repair.

Heroku release can fail if the database alembic_version points at a revision
that is not resolvable in the current release image. This script creates the
chat tables idempotently and stamps Alembic to the current head used by this
release.
"""

import asyncio
import logging

from sqlalchemy import text

from app.core.database import engine

HEAD_REVISION = "f5a6b7c8d9e0"
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
logger = logging.getLogger(__name__)


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
    """
    CREATE TABLE IF NOT EXISTS ai_api_keys (
        id UUID PRIMARY KEY,
        provider VARCHAR(50) NOT NULL DEFAULT 'gemini',
        key_name VARCHAR(100) NOT NULL,
        api_key TEXT NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        usage_count INTEGER NOT NULL DEFAULT 0,
        last_used_at TIMESTAMP WITHOUT TIME ZONE NULL,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_ai_api_keys_provider ON ai_api_keys (provider)",
    "CREATE INDEX IF NOT EXISTS ix_ai_api_keys_is_active ON ai_api_keys (is_active)",
    """
    CREATE TABLE IF NOT EXISTS quiz_sets (
        id UUID PRIMARY KEY,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        document_id UUID NULL REFERENCES documents(id) ON DELETE SET NULL,
        job_id VARCHAR(64) NULL,
        quiz_type VARCHAR(20) NOT NULL DEFAULT 'quick',
        question_count INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_quiz_sets_user_id ON quiz_sets (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_quiz_sets_document_id ON quiz_sets (document_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_quiz_sets_job_id ON quiz_sets (job_id)",
    """
    CREATE TABLE IF NOT EXISTS quiz_questions (
        id UUID PRIMARY KEY,
        quiz_set_id UUID NOT NULL REFERENCES quiz_sets(id) ON DELETE CASCADE,
        question_text TEXT NOT NULL,
        options JSONB NOT NULL DEFAULT '[]',
        correct_answer VARCHAR(10) NOT NULL DEFAULT '',
        position INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_quiz_questions_quiz_set_id ON quiz_questions (quiz_set_id)",
    "UPDATE quotas SET token_limit = 2000000 WHERE token_limit < 2000000",
    "UPDATE quotas SET storage_limit_mb = 10240 WHERE storage_limit_mb < 10240",
    "UPDATE quotas SET video_limit = 50 WHERE video_limit < 50",
    "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)",
    "DELETE FROM alembic_version",
    f"INSERT INTO alembic_version (version_num) VALUES ('{HEAD_REVISION}')",
]


async def main() -> None:
    async with engine.begin() as connection:
        await connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        await connection.execute(text("SET LOCAL statement_timeout = '30s'"))
        for index, statement in enumerate(DDL_STATEMENTS, start=1):
            logger.info("Running release migration statement %s/%s", index, len(DDL_STATEMENTS))
            await connection.execute(text(statement))
        logger.info("Release migration repair completed at Alembic head %s", HEAD_REVISION)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
