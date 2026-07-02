"""merge_finance_crm_hub_heads

Revision ID: 5c181f7389c6
Revises: d1e3f920, e2f4a610, f3b5c740
Create Date: 2026-06-30 23:47:50.850317
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '5c181f7389c6'
down_revision: Union[str, None] = ('d1e3f920', 'e2f4a610', 'f3b5c740')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
