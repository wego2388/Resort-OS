"""Record who cancelled a salary advance and when.

Revision ID: a7b8c9d0e1f2
Revises: 90f2a4c81b3e
"""
from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = "90f2a4c81b3e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("salary_advances", sa.Column("cancelled_by", sa.Integer(), nullable=True))
    op.add_column("salary_advances", sa.Column("cancelled_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("salary_advances", "cancelled_at")
    op.drop_column("salary_advances", "cancelled_by")
