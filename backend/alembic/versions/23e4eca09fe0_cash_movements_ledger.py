"""cash_movements_ledger

Revision ID: 23e4eca09fe0
Revises: fee9db0c91b1
Create Date: 2026-07-13 16:38:28.727200

Operations & Control Layer plan §3.2 — Cash Control ledger (cash_in/
cash_out/petty_cash/safe_drop/drawer_open/correction on a cashier shift).

⚠️ راجع alembic/env.py:37-46 — الـ --autogenerate الخام كان مقترح DROP TABLE
لكل جدول restaurant/cafe القديم (لسه موجودين فعليًا في Postgres كأرشيف
عمدًا) + drop/create index مش متعلّقين بالتغيير ده خالص (دايننج/advance_
payments/salary_advances drift مش له علاقة بالـ commit ده). اتشالوا يدويًا
من هنا — الملف ده بيعمل حاجة واحدة بس: إنشاء جدول cash_movements.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '23e4eca09fe0'
down_revision: Union[str, None] = 'fee9db0c91b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cash_movements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=False),
        sa.Column('shift_id', sa.Integer(), nullable=False),
        sa.Column('movement_type', sa.String(length=20), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=False),
        sa.Column('performed_by', sa.Integer(), nullable=False),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shift_id'], ['cashier_shifts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_cash_movements_branch_id'), 'cash_movements', ['branch_id'], unique=False)
    op.create_index(op.f('ix_cash_movements_movement_type'), 'cash_movements', ['movement_type'], unique=False)
    op.create_index(op.f('ix_cash_movements_shift_id'), 'cash_movements', ['shift_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_cash_movements_shift_id'), table_name='cash_movements')
    op.drop_index(op.f('ix_cash_movements_movement_type'), table_name='cash_movements')
    op.drop_index(op.f('ix_cash_movements_branch_id'), table_name='cash_movements')
    op.drop_table('cash_movements')
