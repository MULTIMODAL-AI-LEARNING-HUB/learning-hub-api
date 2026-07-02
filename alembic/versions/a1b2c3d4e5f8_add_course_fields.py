"""Add missing columns to courses table

Revision ID: a1b2c3d4e5f8
Revises: a1b2c3d4e5f7
Create Date: 2026-07-02 07:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f8'
down_revision: Union[str, None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('courses', sa.Column('level', sa.String(length=50), nullable=False, server_default='BEGINNER'))
    op.add_column('courses', sa.Column('language', sa.String(length=10), nullable=False, server_default='en'))
    op.add_column('courses', sa.Column('requirements', sa.Text(), nullable=True))
    op.add_column('courses', sa.Column('learning_outcomes', sa.Text(), nullable=True))
    op.add_column('courses', sa.Column('tags', sa.String(length=500), nullable=True))
    op.add_column('courses', sa.Column('view_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('courses', sa.Column('rating_avg', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('courses', sa.Column('rating_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('courses', 'rating_count')
    op.drop_column('courses', 'rating_avg')
    op.drop_column('courses', 'view_count')
    op.drop_column('courses', 'tags')
    op.drop_column('courses', 'learning_outcomes')
    op.drop_column('courses', 'requirements')
    op.drop_column('courses', 'language')
    op.drop_column('courses', 'level')
