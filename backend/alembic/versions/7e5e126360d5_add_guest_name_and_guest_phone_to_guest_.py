"""add guest_name and guest_phone to guest_sessions and dining_orders

Revision ID: 7e5e126360d5
Revises: f1e6c8b4a3d7
Create Date: 2026-08-03

طلب Mohamed (2026-08-03): هوية الضيف (اسم إجباري، تليفون اختياري) تُلتقط
مرة واحدة على guest_sessions (أول مسح QR)، وتُنسخ (snapshot) على
dining_orders — نفس نمط DiningOrderItem.name_ar، عشان تفضل موجودة حتى لو
الجلسة انتهت وتشتغل برضو للطلبات اللي الكاشير بيفتحها يدويًا (بدون
guest_session_id). الأعمدة VARCHAR(255) — نفس نمط
347cbfa7a11d_encrypt_national_id_fields.py — تخزّن نص Fernet مشفّر
(app.core.encryption.EncryptedString)، مش plaintext.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "7e5e126360d5"
down_revision: str | None = "f1e6c8b4a3d7"
branch_labels = None
depends_on = None

_TABLES = ["guest_sessions", "dining_orders"]


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("guest_name", sa.String(length=255), nullable=True))
        op.add_column(table, sa.Column("guest_phone", sa.String(length=255), nullable=True))


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "guest_phone")
        op.drop_column(table, "guest_name")
