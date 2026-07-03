"""
app/modules/timeshare/models.py
Timeshare Module — عقود التايم شير
Tables: timeshare_contracts, timeshare_installments, timeshare_waitlist
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer,
    Numeric, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.kernel.models.mixins import TimestampMixin
from app.core.database import Base
from app.core.encryption import EncryptedString


class TimeshareContract(Base, TimestampMixin):
    __tablename__ = "timeshare_contracts"

    id:                    Mapped[int]           = mapped_column(primary_key=True)
    branch_id:             Mapped[int]           = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    contract_number:       Mapped[str]           = mapped_column(String(30), unique=True)  # TS-20260630-0001
    customer_name:         Mapped[str]           = mapped_column(String(200))
    customer_phone:        Mapped[str | None]    = mapped_column(String(20), nullable=True)
    customer_email:        Mapped[str | None]    = mapped_column(String(150), nullable=True)
    customer_national_id:  Mapped[str | None]    = mapped_column(EncryptedString(255), nullable=True)
    room_type:             Mapped[str]           = mapped_column(String(10))   # 2R|4R|6R
    week_number:           Mapped[int | None]    = mapped_column(Integer, nullable=True)  # 1-52 fixed, None=floating
    nights_per_year:       Mapped[int]           = mapped_column(Integer, default=7)
    season:                Mapped[str]           = mapped_column(String(10), default="high")  # high|low|both
    total_value:           Mapped[Decimal]       = mapped_column(Numeric(14, 2))
    down_payment:          Mapped[Decimal]       = mapped_column(Numeric(14, 2))
    installments:          Mapped[int]           = mapped_column(Integer, default=12)
    installment_period:    Mapped[int]           = mapped_column(Integer, default=1)  # 1=monthly,3=quarterly,6=biannual
    first_installment_date: Mapped[date]         = mapped_column(Date)
    partner_share_pct:     Mapped[Decimal]       = mapped_column(Numeric(5, 2), default=Decimal("0"))
    partner_company:       Mapped[str | None]    = mapped_column(String(200), nullable=True)
    status:                Mapped[str]           = mapped_column(String(20), default="active")
    # draft|active|suspended|cancelled|expired
    booking_frozen:        Mapped[bool]          = mapped_column(Boolean, default=False)
    start_date:            Mapped[date]          = mapped_column(Date)
    end_date:              Mapped[date | None]   = mapped_column(Date, nullable=True)
    signed_by:             Mapped[int | None]    = mapped_column(Integer, nullable=True)
    notes:                 Mapped[str | None]    = mapped_column(Text, nullable=True)

    # ── بيانات العميل الموسّعة (من نظام إنتاج فعلي — elkheima-beach-resort) ──
    nationality:           Mapped[str | None]    = mapped_column(String(50), nullable=True)
    occupation:             Mapped[str | None]    = mapped_column(String(100), nullable=True)
    passport_number:        Mapped[str | None]    = mapped_column(EncryptedString(255), nullable=True)
    address:                Mapped[str | None]    = mapped_column(String(300), nullable=True)

    # ── بيانات العقد التجارية الموسّعة ──
    contract_date:          Mapped[date | None]   = mapped_column(Date, nullable=True)
    purchase_price:         Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    contract_deposit:       Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    maintenance_fee:        Mapped[Decimal]       = mapped_column(Numeric(10, 2), default=Decimal("0"))
    maintenance_increase:   Mapped[Decimal]       = mapped_column(Numeric(5, 2), default=Decimal("10"))  # % سنوي
    batch_number:           Mapped[int | None]    = mapped_column(Integer, nullable=True)   # رقم دفعة الاستيراد
    form_number:            Mapped[str | None]    = mapped_column(String(50), nullable=True)  # رقم الاستمارة
    receipt_number:         Mapped[str | None]    = mapped_column(String(50), nullable=True)
    rci_included:           Mapped[bool]          = mapped_column(Boolean, default=False)
    contract_value:         Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)  # القيمة الإجمالية في الاستمارة
    net_contract_value:     Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    over_under_price:       Mapped[Decimal]       = mapped_column(Numeric(14, 2), default=Decimal("0"))
    years_count:            Mapped[int]           = mapped_column(Integer, default=99)
    payment_type:           Mapped[str]           = mapped_column(String(20), default="installment")  # installment|cash

    # ── إلغاء ──
    cancelled_at:           Mapped[date | None]   = mapped_column(Date, nullable=True)
    cancel_amount:          Mapped[Decimal]       = mapped_column(Numeric(14, 2), default=Decimal("0"))

    installments_list: Mapped[list["TimeshareInstallment"]] = relationship(
        "TimeshareInstallment", back_populates="contract", lazy="select",
        foreign_keys="TimeshareInstallment.contract_id",
    )
    waitlist: Mapped[list["TimeshareWaitlist"]] = relationship(
        "TimeshareWaitlist", back_populates="contract", lazy="select"
    )


class TimeshareInstallment(Base, TimestampMixin):
    __tablename__ = "timeshare_installments"

    id:              Mapped[int]            = mapped_column(primary_key=True)
    contract_id:     Mapped[int]            = mapped_column(ForeignKey("timeshare_contracts.id", ondelete="CASCADE"))
    installment_no:  Mapped[int]            = mapped_column(Integer)
    due_date:        Mapped[date]           = mapped_column(Date, index=True)
    amount:          Mapped[Decimal]        = mapped_column(Numeric(14, 2))
    paid_amount:     Mapped[Decimal]        = mapped_column(Numeric(14, 2), default=Decimal("0"))
    status:          Mapped[str]            = mapped_column(String(20), default="pending")
    # pending|paid|partial|overdue
    paid_at:         Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    payment_method:  Mapped[str | None]     = mapped_column(String(30), nullable=True)
    receipt_number:  Mapped[str | None]     = mapped_column(String(50), nullable=True)
    notes:           Mapped[str | None]     = mapped_column(String(300), nullable=True)

    contract: Mapped["TimeshareContract"] = relationship(
        "TimeshareContract", back_populates="installments_list",
        foreign_keys=[contract_id],
    )


class TimeshareVisit(Base, TimestampMixin):
    """زيارة فعلية لصاحب التايم شير — تحجز غرفة في PMS."""
    __tablename__ = "timeshare_visits"

    id:              Mapped[int]            = mapped_column(primary_key=True)
    branch_id:       Mapped[int]            = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    contract_id:     Mapped[int]            = mapped_column(ForeignKey("timeshare_contracts.id", ondelete="CASCADE"))
    booking_id:      Mapped[int | None]     = mapped_column(ForeignKey("bookings.id",  ondelete="SET NULL"), nullable=True)
    check_in:        Mapped[date]           = mapped_column(Date)
    check_out:       Mapped[date]           = mapped_column(Date)
    nights:          Mapped[int]            = mapped_column(Integer)
    status:          Mapped[str]            = mapped_column(String(20), default="scheduled")
    # scheduled|active|completed|cancelled
    notes:           Mapped[str | None]     = mapped_column(Text, nullable=True)

    contract: Mapped["TimeshareContract"] = relationship("TimeshareContract")


class TimeshareWaitlist(Base, TimestampMixin):
    """قائمة انتظار لأسابيع التايم شير العائم."""
    __tablename__ = "timeshare_waitlist"

    id:               Mapped[int]             = mapped_column(primary_key=True)
    branch_id:        Mapped[int]             = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    contract_id:      Mapped[int]             = mapped_column(ForeignKey("timeshare_contracts.id", ondelete="CASCADE"))
    requested_start:  Mapped[date]            = mapped_column(Date)
    requested_end:    Mapped[date]            = mapped_column(Date)
    position:         Mapped[int]             = mapped_column(Integer)
    status:           Mapped[str]             = mapped_column(String(20), default="waiting")
    # waiting|notified|confirmed|expired|cancelled
    notified_at:      Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at:       Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    contract: Mapped["TimeshareContract"] = relationship("TimeshareContract", back_populates="waitlist")
