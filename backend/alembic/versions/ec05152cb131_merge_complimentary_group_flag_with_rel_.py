"""merge complimentary_group_flag with rel-15 tip

Revision ID: ec05152cb131
Revises: e5f6a7b8c9d0, 6449668eb81a
Create Date: 2026-09-04 23:33:29.148890
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ec05152cb131'
down_revision: Union[str, None] = ('e5f6a7b8c9d0', '6449668eb81a')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
