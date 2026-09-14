"""Add notes table for lesson notes feature

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-09-13
"""

import sqlalchemy as sa

from alembic import op

revision = "a6b7c8d9e0f1"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("lesson_id", sa.Uuid(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notes_user_id", "notes", ["user_id"], unique=False)
    op.create_index("ix_notes_course_id", "notes", ["course_id"], unique=False)
    op.create_index("ix_notes_lesson_id", "notes", ["lesson_id"], unique=False)
    op.create_index("ix_notes_user_course", "notes", ["user_id", "course_id"], unique=False)
    op.create_index("ix_notes_user_lesson", "notes", ["user_id", "lesson_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_notes_user_lesson", table_name="notes")
    op.drop_index("ix_notes_user_course", table_name="notes")
    op.drop_index("ix_notes_lesson_id", table_name="notes")
    op.drop_index("ix_notes_course_id", table_name="notes")
    op.drop_index("ix_notes_user_id", table_name="notes")
    op.drop_table("notes")
