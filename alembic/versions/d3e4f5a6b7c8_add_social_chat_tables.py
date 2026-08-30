"""add social chat tables

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
"""

import sqlalchemy as sa

from alembic import op

revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "social_chat_rooms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_chat_rooms_kind", "social_chat_rooms", ["kind"])
    op.create_index("ix_social_chat_rooms_created_by", "social_chat_rooms", ["created_by"])
    op.create_index("ix_social_chat_rooms_created_at", "social_chat_rooms", ["created_at"])
    op.create_index("ix_social_chat_rooms_updated_at", "social_chat_rooms", ["updated_at"])

    op.create_table(
        "social_chat_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["social_chat_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "user_id", name="uq_social_chat_room_user"),
    )
    op.create_index("ix_social_chat_members_room_id", "social_chat_members", ["room_id"])
    op.create_index("ix_social_chat_members_user_id", "social_chat_members", ["user_id"])

    op.create_table(
        "social_chat_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("sender_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["social_chat_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_chat_messages_room_id", "social_chat_messages", ["room_id"])
    op.create_index("ix_social_chat_messages_sender_id", "social_chat_messages", ["sender_id"])
    op.create_index("ix_social_chat_messages_created_at", "social_chat_messages", ["created_at"])


def downgrade() -> None:
    op.drop_table("social_chat_messages")
    op.drop_table("social_chat_members")
    op.drop_table("social_chat_rooms")
