"""Add missing columns to enrollments table

Revision ID: a1b2c3d4e5f1
Revises: a1b2c3d4e5f0
Create Date: 2026-07-02 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f1'
down_revision: Union[str, None] = 'a1b2c3d4e5f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('enrollments', sa.Column('progress_percent', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('enrollments', sa.Column('last_accessed_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('enrollments', 'last_accessed_at')
    op.drop_column('enrollments', 'progress_percent')
