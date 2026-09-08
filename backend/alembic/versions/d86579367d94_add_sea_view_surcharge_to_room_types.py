"""add sea view surcharge to room types

Revision ID: d86579367d94
Revises: ec05152cb131
Create Date: 2026-09-08 23:29:24.972314
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd86579367d94'
down_revision: Union[str, None] = 'ec05152cb131'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('room_types', sa.Column('sea_view_surcharge', sa.Numeric(precision=10, scale=2), nullable=True))


def downgrade() -> None:
    op.drop_column('room_types', 'sea_view_surcharge')
