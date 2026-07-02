"""timeshare_contract_expanded_fields

Revision ID: 67a5a4cf1db5
Revises: 07f92639806e
Create Date: 2026-07-01

Expands timeshare_contracts with real-world fields ported from a mature
production reference (elkheima-beach-resort's contracts.py): customer
email, season, partner company, extended customer info (nationality,
occupation, passport_number — encrypted, address), extended contract
info (batch/form/receipt numbers, RCI flag, contract/net values,
over/under price, years, payment type, maintenance fee), and
cancellation tracking.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

import app.core.encryption

revision: str = "67a5a4cf1db5"
down_revision: str | None = "07f92639806e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("timeshare_contracts", sa.Column("customer_email", sa.String(length=150), nullable=True))
    op.add_column("timeshare_contracts", sa.Column("season", sa.String(length=10), nullable=False, server_default="high"))
    op.add_column("timeshare_contracts", sa.Column("partner_company", sa.String(length=200), nullable=True))
    op.add_column("timeshare_contracts", sa.Column("nationality", sa.String(length=50), nullable=True))
    op.add_column("timeshare_contracts", sa.Column("occupation", sa.String(length=100), nullable=True))
    op.add_column("timeshare_contracts", sa.Column("passport_number", app.core.encryption.EncryptedString(length=255), nullable=True))
    op.add_column("timeshare_contracts", sa.Column("address", sa.String(length=300), nullable=True))
    op.add_column("timeshare_contracts", sa.Column("contract_date", sa.Date(), nullable=True))
    op.add_column("timeshare_contracts", sa.Column("purchase_price", sa.Numeric(precision=14, scale=2), nullable=True))
    op.add_column("timeshare_contracts", sa.Column("contract_deposit", sa.Numeric(precision=14, scale=2), nullable=True))
    op.add_column("timeshare_contracts", sa.Column("maintenance_fee", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"))
    op.add_column("timeshare_contracts", sa.Column("maintenance_increase", sa.Numeric(precision=5, scale=2), nullable=False, server_default="10"))
    op.add_column("timeshare_contracts", sa.Column("batch_number", sa.Integer(), nullable=True))
    op.add_column("timeshare_contracts", sa.Column("form_number", sa.String(length=50), nullable=True))
    op.add_column("timeshare_contracts", sa.Column("receipt_number", sa.String(length=50), nullable=True))
    op.add_column("timeshare_contracts", sa.Column("rci_included", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("timeshare_contracts", sa.Column("contract_value", sa.Numeric(precision=14, scale=2), nullable=True))
    op.add_column("timeshare_contracts", sa.Column("net_contract_value", sa.Numeric(precision=14, scale=2), nullable=True))
    op.add_column("timeshare_contracts", sa.Column("over_under_price", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0"))
    op.add_column("timeshare_contracts", sa.Column("years_count", sa.Integer(), nullable=False, server_default="99"))
    op.add_column("timeshare_contracts", sa.Column("payment_type", sa.String(length=20), nullable=False, server_default="installment"))
    op.add_column("timeshare_contracts", sa.Column("cancelled_at", sa.Date(), nullable=True))
    op.add_column("timeshare_contracts", sa.Column("cancel_amount", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0"))


def downgrade() -> None:
    for col in (
        "cancel_amount", "cancelled_at", "payment_type", "years_count",
        "over_under_price", "net_contract_value", "contract_value",
        "rci_included", "receipt_number", "form_number", "batch_number",
        "maintenance_increase", "maintenance_fee", "contract_deposit",
        "purchase_price", "contract_date", "address", "passport_number",
        "occupation", "nationality", "partner_company", "season", "customer_email",
    ):
        op.drop_column("timeshare_contracts", col)
