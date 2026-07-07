"""Add token_version to users table for JWT invalidation on password reset.

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f9
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa

revision = "b1c2d3e4f5a6"
down_revision = "a1b2c3d4e5f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("token_version", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("users", "token_version")
