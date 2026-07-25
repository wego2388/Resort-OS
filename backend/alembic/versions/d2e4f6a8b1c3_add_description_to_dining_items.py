"""add_description_to_dining_items

Revision ID: d2e4f6a8b1c3
Revises: c1156be7cc43
Create Date: 2026-07-24 21:18:00.000000

يضيف عمود description لجدول dining_items لعرض وصف الصنف
في قائمة الضيف عبر QR (OrderView).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd2e4f6a8b1c3'
down_revision: Union[str, None] = 'c1156be7cc43'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'dining_items',
        sa.Column('description', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('dining_items', 'description')
