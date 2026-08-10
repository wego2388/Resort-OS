"""leasing: accrual-based rent recognition + deposit-on-receipt

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-08-10

OPS-DATA-02 §10.5: قبل seed أصلح المحاسبة الحالية للإيجار — التأمين كان
يترحّل Cash فورًا عند توقيع العقد (مش عند الاستلام الفعلي)، والإيراد كان
يُثبت فقط عند التحصيل (cash-basis، مش accrual عند تاريخ الاستحقاق).
LeasePayment.accrued يمنع ترحيل قيد الاستحقاق مرتين لنفس الدفعة.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "a6b7c8d9e0f1"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lease_contracts",
        sa.Column("deposit_received", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("lease_contracts", sa.Column("deposit_received_at", sa.DateTime(), nullable=True))
    op.add_column("lease_contracts", sa.Column("deposit_payment_method", sa.String(30), nullable=True))
    op.add_column("lease_contracts", sa.Column("deposit_received_by", sa.Integer(), nullable=True))

    op.add_column(
        "lease_payments",
        sa.Column("accrued", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "lease_payments",
        sa.Column("accrual_journal_entry_id", sa.Integer(),
                  sa.ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("lease_payments", "accrual_journal_entry_id")
    op.drop_column("lease_payments", "accrued")
    op.drop_column("lease_contracts", "deposit_received_by")
    op.drop_column("lease_contracts", "deposit_payment_method")
    op.drop_column("lease_contracts", "deposit_received_at")
    op.drop_column("lease_contracts", "deposit_received")
