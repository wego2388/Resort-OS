"""
app/modules/pms/models.py
PMS Module — Hotel Property Management System
Tables: room_types, rooms, bookings, booking_rooms, night_audit_logs
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, JSON,
    Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wego_core.models.mixins import TimestampMixin
from app.core.database import Base
from app.core.encryption import EncryptedString


class RoomType(Base, TimestampMixin):
    __tablename__ = "room_types"

    id:           Mapped[int]         = mapped_column(primary_key=True)
    branch_id:    Mapped[int]         = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    name:         Mapped[str]         = mapped_column(String(100))
    name_ar:      Mapped[str | None]  = mapped_column(String(100), nullable=True)
    base_rate:    Mapped[Decimal]     = mapped_column(Numeric(10, 2))
    max_occupancy:Mapped[int]         = mapped_column(Integer, default=2)
    amenities:    Mapped[str | None]  = mapped_column(Text, nullable=True)   # JSON list
    is_active:    Mapped[bool]        = mapped_column(Boolean, default=True)

    rooms: Mapped[list["Room"]] = relationship("Room", back_populates="room_type", lazy="select")


class Room(Base, TimestampMixin):
    __tablename__ = "rooms"
    __table_args__ = (
        UniqueConstraint("branch_id", "name", name="uq_room_branch_name"),
    )

    id:           Mapped[int]        = mapped_column(primary_key=True)
    branch_id:    Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    room_type_id: Mapped[int]        = mapped_column(ForeignKey("room_types.id", ondelete="RESTRICT"))
    name:         Mapped[str]        = mapped_column(String(20))     # "101", "A-204"
    floor:        Mapped[int]        = mapped_column(Integer, default=1)
    status:       Mapped[str]        = mapped_column(String(30), default="available")
    # available|occupied|reserved|maintenance|checkout_pending
    notes:        Mapped[str | None] = mapped_column(String(300), nullable=True)

    room_type: Mapped["RoomType"] = relationship("RoomType", back_populates="rooms")


class Booking(Base, TimestampMixin):
    __tablename__ = "bookings"

    id:              Mapped[int]          = mapped_column(primary_key=True)
    branch_id:       Mapped[int]          = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    booking_number:  Mapped[str]          = mapped_column(String(30), unique=True)   # BKG-20260630-0001
    guest_name:      Mapped[str]          = mapped_column(String(200))
    guest_phone:     Mapped[str | None]   = mapped_column(String(20), nullable=True)
    guest_email:     Mapped[str | None]   = mapped_column(String(100), nullable=True)
    guest_national_id: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)
    check_in:        Mapped[date]         = mapped_column(Date)
    check_out:       Mapped[date]         = mapped_column(Date)
    adults:          Mapped[int]          = mapped_column(Integer, default=1)
    children:        Mapped[int]          = mapped_column(Integer, default=0)
    status:          Mapped[str]          = mapped_column(String(30), default="confirmed")
    # confirmed|checked_in|checked_out|cancelled|no_show
    source:          Mapped[str]          = mapped_column(String(30), default="direct")
    # direct|online|b2b|phone
    folio_id:        Mapped[int | None]   = mapped_column(ForeignKey("folios.id", ondelete="SET NULL"), nullable=True)
    total_rate:      Mapped[Decimal]      = mapped_column(Numeric(12, 2), default=Decimal("0"))
    notes:           Mapped[str | None]   = mapped_column(Text, nullable=True)
    cancelled_at:    Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_by:    Mapped[int | None]      = mapped_column(Integer, nullable=True)

    rooms: Mapped[list["BookingRoom"]] = relationship("BookingRoom", back_populates="booking", lazy="select")


class BookingRoom(Base, TimestampMixin):
    """Many-to-many بين Booking و Room مع السعر اليومي."""
    __tablename__ = "booking_rooms"
    __table_args__ = (
        UniqueConstraint("booking_id", "room_id", name="uq_booking_room"),
    )

    id:           Mapped[int]     = mapped_column(primary_key=True)
    booking_id:   Mapped[int]     = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"))
    room_id:      Mapped[int]     = mapped_column(ForeignKey("rooms.id",    ondelete="RESTRICT"))
    daily_rate:   Mapped[Decimal] = mapped_column(Numeric(10, 2))
    nights:       Mapped[int]     = mapped_column(Integer)
    total:        Mapped[Decimal] = mapped_column(Numeric(10, 2))

    booking: Mapped["Booking"] = relationship("Booking", back_populates="rooms")


class HousekeepingTask(Base, TimestampMixin):
    """مهمة تنظيف الغرف — dirty → cleaning → inspecting → available."""
    __tablename__ = "housekeeping_tasks"

    id:           Mapped[int]          = mapped_column(primary_key=True)
    branch_id:    Mapped[int]          = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    room_id:      Mapped[int]          = mapped_column(ForeignKey("rooms.id",    ondelete="CASCADE"))
    assigned_to:  Mapped[int | None]   = mapped_column(Integer, nullable=True)
    task_type:    Mapped[str]          = mapped_column(String(30), default="checkout_clean")
    status:       Mapped[str]          = mapped_column(String(30), default="dirty")
    priority:     Mapped[str]          = mapped_column(String(10), default="normal")
    notes:        Mapped[str | None]   = mapped_column(Text, nullable=True)
    started_at:   Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    room: Mapped["Room"] = relationship("Room")


class RatePlan(Base, TimestampMixin):
    """خطة أسعار موسمية."""
    __tablename__ = "rate_plans"

    id:                   Mapped[int]           = mapped_column(primary_key=True)
    branch_id:            Mapped[int]           = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    room_type_id:         Mapped[int | None]    = mapped_column(ForeignKey("room_types.id", ondelete="CASCADE"), nullable=True)
    name:                 Mapped[str]           = mapped_column(String(100))
    name_ar:              Mapped[str | None]    = mapped_column(String(100), nullable=True)
    base_rate_override:   Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    rate_multiplier:      Mapped[Decimal]        = mapped_column(Numeric(6, 4), default=Decimal("1.0000"))
    valid_from:           Mapped[date]           = mapped_column(Date)
    valid_until:          Mapped[date]           = mapped_column(Date)
    seasonal_adjustments: Mapped[str | None]    = mapped_column(Text, nullable=True)  # JSON
    min_nights:           Mapped[int]            = mapped_column(Integer, default=1)
    is_active:            Mapped[bool]           = mapped_column(Boolean, default=True)

    room_type: Mapped["RoomType | None"] = relationship("RoomType")


class NightAuditLog(Base, TimestampMixin):
    """سجل Night Audit اليومي."""
    __tablename__ = "night_audit_logs"
    __table_args__ = (
        UniqueConstraint("branch_id", "audit_date", name="uq_audit_branch_date"),
    )

    id:                 Mapped[int]          = mapped_column(primary_key=True)
    branch_id:          Mapped[int]          = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    audit_date:         Mapped[date]         = mapped_column(Date)
    occupied_rooms:     Mapped[int]          = mapped_column(Integer, default=0)
    total_rooms:        Mapped[int]          = mapped_column(Integer, default=0)
    occupancy_pct:      Mapped[Decimal]      = mapped_column(Numeric(5, 2), default=Decimal("0"))
    room_revenue:       Mapped[Decimal]      = mapped_column(Numeric(12, 2), default=Decimal("0"))
    no_shows:           Mapped[int]          = mapped_column(Integer, default=0)
    checkouts_today:    Mapped[int]          = mapped_column(Integer, default=0)
    checkins_today:     Mapped[int]          = mapped_column(Integer, default=0)
    status:             Mapped[str]          = mapped_column(String(20), default="pending")
    # pending|running|completed|failed
    completed_at:       Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    gm_notified:        Mapped[bool]            = mapped_column(Boolean, default=False)
    summary_json:       Mapped[str | None]      = mapped_column(Text, nullable=True)
