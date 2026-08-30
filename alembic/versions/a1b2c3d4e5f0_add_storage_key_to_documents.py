"""Add missing columns to documents and enrollments tables

Revision ID: a1b2c3d4e5f0
Revises: a1b2c3d4e5f9
Create Date: 2026-07-02 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = 'a1b2c3d4e5f0'
down_revision: Union[str, None] = 'a1b2c3d4e5f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('storage_key', sa.String(length=500), nullable=True))
    op.add_column('enrollments', sa.Column('progress_percent', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('enrollments', sa.Column('last_accessed_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('enrollments', 'last_accessed_at')
    op.drop_column('enrollments', 'progress_percent')
    op.drop_column('documents', 'storage_key')
