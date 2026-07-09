"""Add early_checkin_at / late_checkout_at + extra_charge to bookings

Revision ID: a3b4c5d6e7f8
Revises: f1a2b3c4d5e6
Create Date: 2026-07-09

يضيف حقلين للحجز:
- early_checkin_at: وقت الوصول المبكر (datetime) — لو قبل check-in الاعتيادي
- late_checkout_at: وقت المغادرة المتأخرة (datetime) — لو بعد check-out الاعتيادي
- extra_charge: رسوم إضافية (early + late) — بتُضاف لـ total_rate وتُحمَّل على الفوليو
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa


revision: str = "a3b4c5d6e7f8"
down_revision: str = "d9e8f7a6b5c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("early_checkin_at",  sa.DateTime, nullable=True))
    op.add_column("bookings", sa.Column("late_checkout_at",  sa.DateTime, nullable=True))
    op.add_column("bookings", sa.Column(
        "extra_charge", sa.Numeric(10, 2), nullable=False, server_default="0",
    ))


def downgrade() -> None:
    op.drop_column("bookings", "extra_charge")
    op.drop_column("bookings", "late_checkout_at")
    op.drop_column("bookings", "early_checkin_at")
