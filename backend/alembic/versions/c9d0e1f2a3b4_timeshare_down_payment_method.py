"""Record the timeshare down-payment tender method.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
"""
from alembic import op
import sqlalchemy as sa


revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "timeshare_contracts",
        sa.Column("down_payment_method", sa.String(length=30), nullable=True),
    )
    op.execute(
        "UPDATE timeshare_contracts SET down_payment_method = 'cash' "
        "WHERE down_payment > 0 AND down_payment_method IS NULL"
    )


def downgrade() -> None:
    op.drop_column("timeshare_contracts", "down_payment_method")
