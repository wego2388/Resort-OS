"""encrypt_national_id_fields

Revision ID: 347cbfa7a11d
Revises: af9285101fa9
Create Date: 2026-07-01

Widens national_id-style columns from VARCHAR(20) to VARCHAR(255) — they now
store Fernet-encrypted ciphertext (app.core.encryption.EncryptedString)
instead of plaintext, per 08-SECURITY.md § Data Encryption.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "347cbfa7a11d"
down_revision: str | None = "af9285101fa9"
branch_labels = None
depends_on = None

_COLUMNS = [
    ("employees", "national_id"),
    ("bookings", "guest_national_id"),
    ("crm_customers", "national_id"),
    ("guest_profiles", "national_id"),
    ("lease_contracts", "tenant_national_id"),
    ("timeshare_contracts", "customer_national_id"),
]


def upgrade() -> None:
    for table, column in _COLUMNS:
        op.alter_column(
            table, column,
            existing_type=sa.String(length=20),
            type_=sa.String(length=255),
            existing_nullable=True,
        )


def downgrade() -> None:
    for table, column in _COLUMNS:
        op.alter_column(
            table, column,
            existing_type=sa.String(length=255),
            type_=sa.String(length=20),
            existing_nullable=True,
        )
