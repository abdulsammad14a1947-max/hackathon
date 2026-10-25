"""face attendance (M10): templates, verification events, challenges, attendance.source

Revision ID: 9c41f7d2ab30
Revises: f3eb2260e584
Create Date: 2026-10-25

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '9c41f7d2ab30'
down_revision: Union[str, None] = 'f3eb2260e584'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'employee_face_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('embedding', sa.Text(), nullable=False),
        sa.Column('embedding_dim', sa.Integer(), nullable=False),
        sa.Column('model_name', sa.String(length=60), nullable=False),
        sa.Column('template_version', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('capture_meta', sa.JSON(), nullable=True),
        sa.Column('enrolled_by_user_id', sa.Integer(), nullable=True),
        sa.Column('enrolled_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['enrolled_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('employee_id', name='uq_face_template_employee'),
    )
    op.create_index(
        op.f('ix_employee_face_templates_company_id'),
        'employee_face_templates',
        ['company_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_employee_face_templates_employee_id'),
        'employee_face_templates',
        ['employee_id'],
        unique=False,
    )

    op.create_table(
        'face_verification_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('purpose', sa.String(length=20), nullable=False),
        sa.Column('outcome', sa.String(length=40), nullable=False),
        sa.Column('detail', sa.String(length=300), nullable=True),
        sa.Column('similarity', sa.Float(), nullable=True),
        sa.Column('threshold', sa.Float(), nullable=True),
        sa.Column('detector_score', sa.Float(), nullable=True),
        sa.Column('template_version', sa.Integer(), nullable=True),
        sa.Column('lat', sa.Float(), nullable=True),
        sa.Column('lng', sa.Float(), nullable=True),
        sa.Column('accuracy_m', sa.Float(), nullable=True),
        sa.Column('distance_m', sa.Float(), nullable=True),
        sa.Column('attendance_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['attendance_id'], ['attendance.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_face_verification_events_company_id'),
        'face_verification_events',
        ['company_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_face_verification_events_employee_id'),
        'face_verification_events',
        ['employee_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_face_verification_events_outcome'),
        'face_verification_events',
        ['outcome'],
        unique=False,
    )

    op.create_table(
        'face_challenges',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('nonce', sa.String(length=64), nullable=False),
        sa.Column('token', sa.String(length=200), nullable=False),
        sa.Column('issued_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_face_challenges_company_id'), 'face_challenges', ['company_id'], unique=False
    )
    op.create_index(
        op.f('ix_face_challenges_user_id'), 'face_challenges', ['user_id'], unique=False
    )
    op.create_index(
        op.f('ix_face_challenges_nonce'), 'face_challenges', ['nonce'], unique=True
    )
    op.create_index(
        op.f('ix_face_challenges_expires_at'), 'face_challenges', ['expires_at'], unique=False
    )

    # attendance: how the day record was created (manual UI vs camera).
    with op.batch_alter_table('attendance', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('source', sa.String(length=30), nullable=False, server_default='manual')
        )


def downgrade() -> None:
    with op.batch_alter_table('attendance', schema=None) as batch_op:
        batch_op.drop_column('source')

    for index in (
        'ix_face_challenges_expires_at',
        'ix_face_challenges_nonce',
        'ix_face_challenges_user_id',
        'ix_face_challenges_company_id',
    ):
        op.drop_index(index, table_name='face_challenges')
    op.drop_table('face_challenges')

    for index in (
        'ix_face_verification_events_outcome',
        'ix_face_verification_events_employee_id',
        'ix_face_verification_events_company_id',
    ):
        op.drop_index(index, table_name='face_verification_events')
    op.drop_table('face_verification_events')

    op.drop_index(
        op.f('ix_employee_face_templates_employee_id'),
        table_name='employee_face_templates',
    )
    op.drop_index(
        op.f('ix_employee_face_templates_company_id'),
        table_name='employee_face_templates',
    )
    op.drop_table('employee_face_templates')
