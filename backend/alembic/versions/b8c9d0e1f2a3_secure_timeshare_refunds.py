"""Secure timeshare cancellation refunds.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
"""
from alembic import op
import sqlalchemy as sa


revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("timeshare_contracts", sa.Column("cancelled_by", sa.Integer(), nullable=True))
    op.add_column("timeshare_contracts", sa.Column("refund_method", sa.String(length=30), nullable=True))
    op.create_foreign_key(
        "fk_timeshare_contracts_cancelled_by_users",
        "timeshare_contracts",
        "users",
        ["cancelled_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        "UPDATE timeshare_contracts SET refund_method = 'cash' "
        "WHERE cancel_amount > 0 AND refund_method IS NULL"
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_timeshare_contracts_cancelled_by_users",
        "timeshare_contracts",
        type_="foreignkey",
    )
    op.drop_column("timeshare_contracts", "refund_method")
    op.drop_column("timeshare_contracts", "cancelled_by")
