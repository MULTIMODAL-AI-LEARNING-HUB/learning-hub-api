"""Add reset_token and reset_token_expiry to users

Revision ID: a1b2c3d4e5f6
Revises: 171848043caf
Create Date: 2026-06-13 22:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '171848043caf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('reset_token', sa.String(255), nullable=True, unique=True))
    op.add_column('users', sa.Column('reset_token_expiry', sa.DateTime(), nullable=True))
    op.create_index('ix_users_reset_token', 'users', ['reset_token'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_users_reset_token', table_name='users')
    op.drop_column('users', 'reset_token_expiry')
    op.drop_column('users', 'reset_token')
