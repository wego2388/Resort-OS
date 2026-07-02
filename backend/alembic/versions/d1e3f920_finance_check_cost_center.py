"""Finance: Check, CostCenter, ExchangeRate, RevenueAuditLog

Revision ID: d1e3f920
Revises: c9f1a852
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa

revision = "d1e3f920"
down_revision = "c9f1a852"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cost_centers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("branch_id", sa.Integer, sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("branch_id", "code", name="uq_cost_center_branch_code"),
    )

    op.create_table(
        "exchange_rates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("from_currency", sa.String(3), nullable=False),
        sa.Column("to_currency", sa.String(3), nullable=False),
        sa.Column("rate", sa.Numeric(12, 6), nullable=False),
        sa.Column("effective_date", sa.Date, nullable=False),
        sa.Column("created_by", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("from_currency", "to_currency", "effective_date", name="uq_exchange_rate"),
    )

    op.create_table(
        "checks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("branch_id", sa.Integer, sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("check_number", sa.String(50), nullable=False),
        sa.Column("bank_name", sa.String(150), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("due_date", sa.Date, nullable=False),
        sa.Column("drawer_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), default="received", nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", sa.Integer, nullable=False),
        sa.Column("received_at", sa.Date, nullable=False),
        sa.Column("deposited_at", sa.Date, nullable=True),
        sa.Column("cleared_at", sa.Date, nullable=True),
        sa.Column("bounced_at", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "check_movements",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("check_id", sa.Integer, sa.ForeignKey("checks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_status", sa.String(20), nullable=False),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("moved_by", sa.Integer, nullable=False),
        sa.Column("notes", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "revenue_audit_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("branch_id", sa.Integer, sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", sa.Integer, nullable=False),
        sa.Column("old_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("new_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("changed_by", sa.Integer, nullable=False),
        sa.Column("approved_by", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("revenue_audit_logs")
    op.drop_table("check_movements")
    op.drop_table("checks")
    op.drop_table("exchange_rates")
    op.drop_table("cost_centers")
