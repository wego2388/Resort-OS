"""orders_client_local_id

Revision ID: 07f92639806e
Revises: 12f21e50c5f0
Create Date: 2026-07-01 01:02:39.941148
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '07f92639806e'
down_revision: Union[str, None] = '12f21e50c5f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("client_local_id", sa.String(length=60), nullable=True))
    op.create_unique_constraint("uq_orders_client_local_id", "orders", ["client_local_id"])


def downgrade() -> None:
    op.drop_constraint("uq_orders_client_local_id", "orders", type_="unique")
    op.drop_column("orders", "client_local_id")
