"""add_crm_customer_id_links

Revision ID: d92bcf723477
Revises: 2aeb25b5e7d2
Create Date: 2026-07-02 22:40:26.357820
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd92bcf723477'
down_revision: Union[str, None] = '2aeb25b5e7d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = ["orders", "cafe_orders", "beach_transactions", "bookings"]


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column('customer_id', sa.Integer(), nullable=True))
        op.create_foreign_key(
            f'fk_{table}_customer_id', table, 'crm_customers',
            ['customer_id'], ['id'], ondelete='SET NULL',
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_constraint(f'fk_{table}_customer_id', table, type_='foreignkey')
        op.drop_column(table, 'customer_id')
