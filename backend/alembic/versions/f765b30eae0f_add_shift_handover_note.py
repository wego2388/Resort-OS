"""add_shift_handover_note

Revision ID: f765b30eae0f
Revises: d92bcf723477
Create Date: 2026-07-03 00:24:29.822081
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f765b30eae0f'
down_revision: Union[str, None] = 'd92bcf723477'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cashier_shifts', sa.Column('handover_note', sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column('cashier_shifts', 'handover_note')
