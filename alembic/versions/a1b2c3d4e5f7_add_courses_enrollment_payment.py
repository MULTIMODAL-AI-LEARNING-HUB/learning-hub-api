"""add_courses_enrollment_payment

Revision ID: a1b2c3d4e5f7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-26 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('categories',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('icon', sa.String(length=50), nullable=True),
        sa.Column('image_url', sa.String(length=500), nullable=True),
        sa.Column('parent_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['parent_id'], ['categories.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('slug')
    )
    op.create_index(op.f('ix_categories_slug'), 'categories', ['slug'], unique=True)
    op.create_index(op.f('ix_categories_parent_id'), 'categories', ['parent_id'], unique=False)

    op.create_table('courses',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('lecturer_id', sa.Uuid(), nullable=False),
        sa.Column('category_id', sa.Uuid(), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('thumbnail_url', sa.String(length=500), nullable=True),
        sa.Column('price_vnd', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['lecturer_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_courses_category_id'), 'courses', ['category_id'], unique=False)
    op.create_index(op.f('ix_courses_lecturer_id'), 'courses', ['lecturer_id'], unique=False)

    op.create_table('course_materials',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('course_id', sa.Uuid(), nullable=False),
        sa.Column('lecturer_id', sa.Uuid(), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=True),
        sa.Column('file_type', sa.String(length=50), nullable=False),
        sa.Column('file_url', sa.String(length=500), nullable=True),
        sa.Column('storage_key', sa.String(length=500), nullable=True),
        sa.Column('file_size', sa.BigInteger(), nullable=True),
        sa.Column('external_url', sa.String(length=500), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('file_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_indexed', sa.Boolean(), nullable=False),
        sa.Column('material_type', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['lecturer_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_course_materials_course_id'), 'course_materials', ['course_id'], unique=False)
    op.create_index(op.f('ix_course_materials_lecturer_id'), 'course_materials', ['lecturer_id'], unique=False)

    op.create_table('enrollments',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('student_id', sa.Uuid(), nullable=False),
        sa.Column('course_id', sa.Uuid(), nullable=False),
        sa.Column('payment_amount_vnd', sa.Integer(), nullable=False),
        sa.Column('payment_status', sa.String(length=50), nullable=False),
        sa.Column('payment_method', sa.String(length=50), nullable=True),
        sa.Column('transaction_id', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('enrolled_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['student_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_enrollments_course_id'), 'enrollments', ['course_id'], unique=False)
    op.create_index(op.f('ix_enrollments_student_id'), 'enrollments', ['student_id'], unique=False)

    op.create_table('material_progress',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('enrollment_id', sa.Uuid(), nullable=False),
        sa.Column('material_id', sa.Uuid(), nullable=False),
        sa.Column('completion_percent', sa.Integer(), nullable=False),
        sa.Column('completed', sa.Boolean(), nullable=False),
        sa.Column('last_position', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['enrollment_id'], ['enrollments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['material_id'], ['course_materials.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('enrollment_id', 'material_id', name='uq_enrollment_material')
    )
    op.create_index(op.f('ix_material_progress_enrollment_id'), 'material_progress', ['enrollment_id'], unique=False)
    op.create_index(op.f('ix_material_progress_material_id'), 'material_progress', ['material_id'], unique=False)

    op.create_table('payments',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('enrollment_id', sa.Uuid(), nullable=True),
        sa.Column('student_id', sa.Uuid(), nullable=False),
        sa.Column('course_id', sa.Uuid(), nullable=False),
        sa.Column('amount_vnd', sa.Integer(), nullable=False),
        sa.Column('payment_method', sa.String(length=50), nullable=False),
        sa.Column('transaction_id', sa.String(length=255), nullable=False),
        sa.Column('payment_status', sa.String(length=50), nullable=False),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['enrollment_id'], ['enrollments.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['student_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('transaction_id')
    )
    op.create_index(op.f('ix_payments_course_id'), 'payments', ['course_id'], unique=False)
    op.create_index(op.f('ix_payments_enrollment_id'), 'payments', ['enrollment_id'], unique=False)
    op.create_index(op.f('ix_payments_student_id'), 'payments', ['student_id'], unique=False)
    op.create_index(op.f('ix_payments_transaction_id'), 'payments', ['transaction_id'], unique=True)

    op.add_column('chat_sessions',
        sa.Column('course_id', sa.Uuid(), nullable=True))
    op.add_column('chat_sessions',
        sa.Column('context_type', sa.String(length=50), nullable=False, server_default='general'))
    op.drop_index(op.f('ix_chat_sessions_document_id'), table_name='chat_sessions')
    op.drop_column('chat_sessions', 'document_id')

    op.add_column('chat_messages',
        sa.Column('context_type', sa.String(length=50), nullable=False, server_default='general'))

    op.create_index(op.f('ix_chat_sessions_course_id'), 'chat_sessions', ['course_id'], unique=False)

    op.execute("UPDATE users SET role = 'student' WHERE role = 'user'")

    op.create_check_constraint('chk_user_role', 'users',
        sa.text("role IN ('admin', 'lecturer', 'student')"))


def downgrade() -> None:
    op.drop_constraint('chk_user_role', 'users', type_='check')

    op.drop_index(op.f('ix_chat_sessions_course_id'), table_name='chat_sessions')

    op.drop_column('chat_messages', 'context_type')

    op.add_column('chat_sessions',
        sa.Column('document_id', sa.Uuid(), nullable=True))
    op.drop_column('chat_sessions', 'context_type')
    op.drop_column('chat_sessions', 'course_id')
    op.create_index(op.f('ix_chat_sessions_document_id'), 'chat_sessions', ['document_id'], unique=False)

    op.drop_table('payments')
    op.drop_table('material_progress')
    op.drop_table('enrollments')
    op.drop_table('course_materials')
    op.drop_table('courses')
    op.drop_table('categories')