"""add service_charge column to folio_charges

Revision ID: b4d8f1a3c6e2
Revises: a1c9e2f4b8d3
Create Date: 2026-07-05 16:30:00.000000

Real revenue-leakage bug found during live accountant acceptance testing:
restaurant/cafe orders paid via "Charge to Room" built the guest's
FolioCharge from order.subtotal + order.vat_amount only — order.service_charge
(12% service charge, calculated correctly on the order itself) was silently
dropped and never reached the guest's folio at all, meaning every
room-service/charge-to-room bill understated what the guest actually owed at
checkout by the full service-charge amount. FolioCharge had no column to
hold it in the first place. server_default='0' backfills existing rows
safely (they predate this fix and had no service charge tracked anyway).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'b4d8f1a3c6e2'
down_revision: Union[str, None] = 'a1c9e2f4b8d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'folio_charges',
        sa.Column('service_charge', sa.Numeric(10, 2), server_default='0', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('folio_charges', 'service_charge')
