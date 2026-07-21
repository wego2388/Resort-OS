"""add service_location_tokens table

Revision ID: 5fed6e302861
Revises: 9b4e1a2c7f30
Create Date: 2026-07-21 23:41:34.972765

Gate 8 Phase 1 Batch B — Service Location token (راجع
docs/decisions/0001-qr-guest-service-mode.md بند 5/6).

⚠️ راجع alembic/env.py وnote في migration 23e4eca09fe0 — الـ --autogenerate
الخام هنا كمان اقترح drop لجداول restaurant/cafe الأرشيفية القديمة + drift
غير متعلّق (dining/advance_payments/salary_advances indexes) بسبب فرق نسخة
DB التطوير المشتركة، اتشالوا يدويًا. الملف ده بيعمل حاجة واحدة بس: إنشاء
جدول service_location_tokens.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '5fed6e302861'
down_revision: Union[str, None] = '9b4e1a2c7f30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'service_location_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=False),
        sa.Column('location_type', sa.String(length=30), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_service_location_tokens_location', 'service_location_tokens',
        ['branch_id', 'location_type', 'location_id'], unique=False,
    )
    op.create_index(
        op.f('ix_service_location_tokens_token'), 'service_location_tokens',
        ['token'], unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_service_location_tokens_token'), table_name='service_location_tokens')
    op.drop_index('ix_service_location_tokens_location', table_name='service_location_tokens')
    op.drop_table('service_location_tokens')
