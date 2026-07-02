"""
app/modules/beach/models.py
Beach Module
Tables: beach_inventory, beach_transactions, b2b_contracts, b2b_contract_days,
        beach_reservations
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer,
    Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wego_core.models.mixins import TimestampMixin
from app.core.database import Base


class BeachInventory(Base, TimestampMixin):
    """حالة الشاطئ اليومية — snapshot per day."""
    __tablename__ = "beach_inventory"
    __table_args__ = (
        UniqueConstraint("branch_id", "inventory_date", name="uq_beach_inventory_date"),
    )

    id:               Mapped[int]     = mapped_column(primary_key=True)
    branch_id:        Mapped[int]     = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    inventory_date:   Mapped[date]    = mapped_column(Date, index=True)
    capacity_max:     Mapped[int]     = mapped_column(Integer, default=200)
    capacity_used:    Mapped[int]     = mapped_column(Integer, default=0)
    towels_total:     Mapped[int]     = mapped_column(Integer, default=200)
    towels_available: Mapped[int]     = mapped_column(Integer, default=200)
    towels_used:      Mapped[int]     = mapped_column(Integer, default=0)
    surge_pct:        Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    # surge يُفعَّل تلقائياً عند capacity > 80%


class BeachTransaction(Base, TimestampMixin):
    """كل عملية بيع في الشاطئ."""
    __tablename__ = "beach_transactions"

    id:              Mapped[int]          = mapped_column(primary_key=True)
    branch_id:       Mapped[int]          = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    tx_type:         Mapped[str]          = mapped_column(String(30))
    # entry|entry_towel|towel_rent|towel_return
    quantity:        Mapped[int]          = mapped_column(Integer, default=1)
    unit_price:      Mapped[Decimal]      = mapped_column(Numeric(10, 2))
    total_amount:    Mapped[Decimal]      = mapped_column(Numeric(10, 2))
    vat_amount:      Mapped[Decimal]      = mapped_column(Numeric(10, 2), default=Decimal("0"))
    surge_applied:   Mapped[bool]         = mapped_column(Boolean, default=False)
    tx_date:         Mapped[date]         = mapped_column(Date, index=True)
    cashier_id:      Mapped[int | None]   = mapped_column(Integer, nullable=True)
    folio_id:        Mapped[int | None]   = mapped_column(ForeignKey("folios.id", ondelete="SET NULL"), nullable=True)
    b2b_contract_id: Mapped[int | None]   = mapped_column(ForeignKey("b2b_contracts.id", ondelete="SET NULL"), nullable=True)
    notes:           Mapped[str | None]   = mapped_column(String(300), nullable=True)
    voided_at:       Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    voided_by:       Mapped[int | None]      = mapped_column(Integer, nullable=True)
    voided_reason:   Mapped[str | None]      = mapped_column(String(200), nullable=True)
    shift_id:        Mapped[int | None]      = mapped_column(ForeignKey("cashier_shifts.id", ondelete="SET NULL"), nullable=True, index=True)


class B2BContract(Base, TimestampMixin):
    """عقد فندق B2B."""
    __tablename__ = "b2b_contracts"

    id:             Mapped[int]        = mapped_column(primary_key=True)
    branch_id:      Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    hotel_name:     Mapped[str]        = mapped_column(String(200))
    hotel_name_ar:  Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_phone:  Mapped[str | None] = mapped_column(String(20), nullable=True)
    daily_quota:    Mapped[int]        = mapped_column(Integer, default=50)
    entry_price:    Mapped[Decimal]    = mapped_column(Numeric(10, 2))
    towel_price:    Mapped[Decimal]    = mapped_column(Numeric(10, 2), default=Decimal("0"))
    valid_from:     Mapped[date]       = mapped_column(Date)
    valid_until:    Mapped[date]       = mapped_column(Date)
    is_active:      Mapped[bool]       = mapped_column(Boolean, default=True)
    notes:          Mapped[str | None] = mapped_column(Text, nullable=True)

    days: Mapped[list["B2BContractDay"]] = relationship("B2BContractDay", back_populates="contract", lazy="select")


class B2BContractDay(Base, TimestampMixin):
    """تتبع استخدام حصة الفندق يومياً."""
    __tablename__ = "b2b_contract_days"
    __table_args__ = (
        UniqueConstraint("contract_id", "day", name="uq_b2b_contract_day"),
    )

    id:               Mapped[int]     = mapped_column(primary_key=True)
    contract_id:      Mapped[int]     = mapped_column(ForeignKey("b2b_contracts.id", ondelete="CASCADE"))
    day:              Mapped[date]    = mapped_column(Date)
    checked_in_count: Mapped[int]     = mapped_column(Integer, default=0)
    total_amount:     Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    notified_quota_warning: Mapped[bool] = mapped_column(Boolean, default=False)

    contract: Mapped["B2BContract"] = relationship("B2BContract", back_populates="days")


class BeachReservation(Base, TimestampMixin):
    """حجز مسبق للشاطئ."""
    __tablename__ = "beach_reservations"

    id:             Mapped[int]          = mapped_column(primary_key=True)
    branch_id:      Mapped[int]          = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    guest_name:     Mapped[str]          = mapped_column(String(200))
    guest_phone:    Mapped[str | None]   = mapped_column(String(20), nullable=True)
    reservation_date: Mapped[date]       = mapped_column(Date, index=True)
    guests_count:   Mapped[int]          = mapped_column(Integer, default=1)
    with_towel:     Mapped[bool]         = mapped_column(Boolean, default=False)
    status:         Mapped[str]          = mapped_column(String(20), default="pending")
    # pending|confirmed|checked_in|no_show|cancelled
    total_amount:   Mapped[Decimal]      = mapped_column(Numeric(10, 2), default=Decimal("0"))
    tx_id:          Mapped[int | None]   = mapped_column(ForeignKey("beach_transactions.id", ondelete="SET NULL"), nullable=True)
    notes:          Mapped[str | None]   = mapped_column(String(300), nullable=True)
