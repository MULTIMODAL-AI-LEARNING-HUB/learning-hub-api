"""Add quiz_sets and quiz_questions tables for persisted quiz history

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-09-10
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quiz_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("job_id", sa.String(length=64), nullable=True),
        sa.Column("quiz_type", sa.String(length=20), nullable=False, server_default="quick"),
        sa.Column("question_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_quiz_sets_user_id"), "quiz_sets", ["user_id"], unique=False)
    op.create_index(op.f("ix_quiz_sets_document_id"), "quiz_sets", ["document_id"], unique=False)
    op.create_index(op.f("ix_quiz_sets_job_id"), "quiz_sets", ["job_id"], unique=True)

    op.create_table(
        "quiz_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("quiz_set_id", sa.Uuid(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("correct_answer", sa.String(length=10), nullable=False, server_default=""),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["quiz_set_id"], ["quiz_sets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_quiz_questions_quiz_set_id"), "quiz_questions", ["quiz_set_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_quiz_questions_quiz_set_id"), table_name="quiz_questions")
    op.drop_table("quiz_questions")
    op.drop_index(op.f("ix_quiz_sets_job_id"), table_name="quiz_sets")
    op.drop_index(op.f("ix_quiz_sets_document_id"), table_name="quiz_sets")
    op.drop_index(op.f("ix_quiz_sets_user_id"), table_name="quiz_sets")
    op.drop_table("quiz_sets")
