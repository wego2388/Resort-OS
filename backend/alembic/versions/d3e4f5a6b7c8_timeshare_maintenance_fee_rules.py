"""timeshare_maintenance_fee_rules table

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-08-10

OPS-DATA-02 §8 نقطة 3: قواعد صيانة effective-dated/versioned بدل dict ثابت
في الكود بيتصحّح يدويًا كل سنة. راجع models.TimeshareMaintenanceFeeRule.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "timeshare_maintenance_fee_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.String(60), nullable=False),
        sa.Column("fee_year", sa.Integer(), nullable=False),
        sa.Column("contract_tier_from", sa.Date(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("fee", sa.Numeric(10, 2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "branch_id", "fee_year", "contract_tier_from", "capacity",
            name="uq_maintenance_fee_rule_branch_year_tier_capacity",
        ),
    )
    op.create_index(
        "ix_timeshare_maintenance_fee_rules_fee_year",
        "timeshare_maintenance_fee_rules", ["fee_year"],
    )


def downgrade() -> None:
    op.drop_index("ix_timeshare_maintenance_fee_rules_fee_year", table_name="timeshare_maintenance_fee_rules")
    op.drop_table("timeshare_maintenance_fee_rules")
