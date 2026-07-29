"""encrypt hub_online_bookings guest pii

Revision ID: 88d1c505a9dc
Revises: c4d8e2f6a901
Create Date: 2026-07-29

Widens guest_name/guest_phone/guest_email on hub_online_bookings — they now
store Fernet-encrypted ciphertext (app.core.encryption.EncryptedString)
instead of plaintext, matching Lead/ContactForm in the same module (same
convention as 347cbfa7a11d_encrypt_national_id_fields). The TypeDecorator's
underlying impl is plain String, so the DDL itself only needs the widened
VARCHAR length — encryption is a Python/ORM-level concern, not a schema one.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "88d1c505a9dc"
down_revision: str | None = "c4d8e2f6a901"
branch_labels = None
depends_on = None

_COLUMNS = [
    ("guest_name", 200, 512, False),
    ("guest_phone", 20, 255, False),
    ("guest_email", 150, 512, True),
]


def upgrade() -> None:
    for column, old_len, new_len, nullable in _COLUMNS:
        op.alter_column(
            "hub_online_bookings", column,
            existing_type=sa.String(length=old_len),
            type_=sa.String(length=new_len),
            existing_nullable=nullable,
        )


def downgrade() -> None:
    for column, old_len, new_len, nullable in _COLUMNS:
        op.alter_column(
            "hub_online_bookings", column,
            existing_type=sa.String(length=new_len),
            type_=sa.String(length=old_len),
            existing_nullable=nullable,
        )
