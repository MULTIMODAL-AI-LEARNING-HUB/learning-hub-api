"""Add Google and Facebook OAuth columns to users table and make password_hash nullable

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-07-21
"""

from alembic import op
import sqlalchemy as sa

revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make password_hash nullable for OAuth users
    op.alter_column("users", "password_hash", existing_type=sa.String(length=255), nullable=True)

    # Add OAuth provider and social ID columns
    op.add_column("users", sa.Column("oauth_provider", sa.String(length=50), nullable=True))
    op.add_column("users", sa.Column("google_id", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("facebook_id", sa.String(length=255), nullable=True))

    # Add unique indexes for google_id and facebook_id
    op.create_index(op.f("ix_users_google_id"), "users", ["google_id"], unique=True)
    op.create_index(op.f("ix_users_facebook_id"), "users", ["facebook_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_facebook_id"), table_name="users")
    op.drop_index(op.f("ix_users_google_id"), table_name="users")
    op.drop_column("users", "facebook_id")
    op.drop_column("users", "google_id")
    op.drop_column("users", "oauth_provider")
    op.alter_column("users", "password_hash", existing_type=sa.String(length=255), nullable=False)
