"""Link HubOnlineBooking to PMS Booking on confirmation

Revision ID: b5c6d7e8f9a0
Revises: a3b4c5d6e7f8
Create Date: 2026-07-09

يضيف:
- pms_booking_id على hub_online_bookings — الحجز الفعلي في PMS
  اللي اتنشأ تلقائياً لما المدير أكّد طلب الحجز الأونلاين
- check_in / check_out / room_type_id / adults على hub_online_bookings
  عشان نقدر ننشئ PMS booking من بيانات الطلب
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision: str = "b5c6d7e8f9a0"
down_revision: str = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hub_online_bookings", sa.Column(
        "pms_booking_id",
        sa.Integer,
        sa.ForeignKey("bookings.id", ondelete="SET NULL"),
        nullable=True,
    ))
    op.add_column("hub_online_bookings", sa.Column("check_in",     sa.Date, nullable=True))
    op.add_column("hub_online_bookings", sa.Column("check_out",    sa.Date, nullable=True))
    op.add_column("hub_online_bookings", sa.Column("room_type_id", sa.Integer, nullable=True))
    op.add_column("hub_online_bookings", sa.Column("adults",       sa.Integer, nullable=True, server_default="1"))


def downgrade() -> None:
    op.drop_column("hub_online_bookings", "adults")
    op.drop_column("hub_online_bookings", "room_type_id")
    op.drop_column("hub_online_bookings", "check_out")
    op.drop_column("hub_online_bookings", "check_in")
    op.drop_column("hub_online_bookings", "pms_booking_id")
