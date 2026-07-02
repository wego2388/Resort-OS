"""journal_entry_currency_fx_rate

Revision ID: 2aeb25b5e7d2
Revises: 3fe20f98d77c
Create Date: 2026-07-02 22:25:47.922852
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2aeb25b5e7d2'
down_revision: Union[str, None] = '3fe20f98d77c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'journal_entries',
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='EGP'),
    )
    op.add_column(
        'journal_entries',
        sa.Column('fx_rate', sa.Numeric(precision=12, scale=6), nullable=False, server_default='1'),
    )


def downgrade() -> None:
    op.drop_column('journal_entries', 'fx_rate')
    op.drop_column('journal_entries', 'currency')
