"""
app/modules/leasing/models.py
Leasing Module — عقود الإيجار التجاري
Tables: lease_contracts, lease_payments
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date, DateTime, ForeignKey, Integer,
    Numeric, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wego_core.models.mixins import TimestampMixin
from app.core.database import Base
from app.core.encryption import EncryptedString


class LeaseContract(Base, TimestampMixin):
    __tablename__ = "lease_contracts"

    id:               Mapped[int]           = mapped_column(primary_key=True)
    branch_id:        Mapped[int]           = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    contract_number:  Mapped[str]           = mapped_column(String(30), unique=True)  # LC-20260630-0001
    tenant_name:      Mapped[str]           = mapped_column(String(200))
    tenant_phone:     Mapped[str | None]    = mapped_column(String(20), nullable=True)
    tenant_national_id: Mapped[str | None]  = mapped_column(EncryptedString(255), nullable=True)
    unit_description: Mapped[str]           = mapped_column(String(300))  # وصف الوحدة المؤجَّرة
    start_date:       Mapped[date]          = mapped_column(Date)
    end_date:         Mapped[date]          = mapped_column(Date)
    base_rent:        Mapped[Decimal]       = mapped_column(Numeric(12, 2))
    increase_rate:    Mapped[Decimal]       = mapped_column(Numeric(5, 2), default=Decimal("0"))  # % سنوي
    billing_day:      Mapped[int]           = mapped_column(Integer, default=1)    # يوم الاستحقاق الشهري
    grace_months:     Mapped[int]           = mapped_column(Integer, default=0)    # أشهر إعفاء
    payment_period:   Mapped[str]           = mapped_column(String(20), default="monthly")
    # monthly|quarterly|biannual|annual
    security_deposit: Mapped[Decimal]       = mapped_column(Numeric(12, 2), default=Decimal("0"))
    status:           Mapped[str]           = mapped_column(String(20), default="active")
    # draft|active|expired|terminated
    signed_by:        Mapped[int | None]    = mapped_column(Integer, nullable=True)
    notes:            Mapped[str | None]    = mapped_column(Text, nullable=True)

    payments: Mapped[list["LeasePayment"]] = relationship(
        "LeasePayment", back_populates="contract", lazy="select"
    )


class TenantCashLog(Base, TimestampMixin):
    """سجل نقدي للمستأجر — مدفوعات خارج دورة الاستحقاق."""
    __tablename__ = "tenant_cash_logs"

    id:              Mapped[int]            = mapped_column(primary_key=True)
    branch_id:       Mapped[int]            = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    contract_id:     Mapped[int]            = mapped_column(ForeignKey("lease_contracts.id", ondelete="CASCADE"))
    amount:          Mapped[Decimal]        = mapped_column(Numeric(12, 2))
    activity_type:   Mapped[str]            = mapped_column(String(30), default="rent_payment")
    # rent_payment | penalty | deposit | refund | maintenance | other
    payment_method:  Mapped[str | None]     = mapped_column(String(30), nullable=True)
    reference:       Mapped[str | None]     = mapped_column(String(50), nullable=True)
    notes:           Mapped[str | None]     = mapped_column(Text, nullable=True)
    recorded_by:     Mapped[int | None]     = mapped_column(Integer, nullable=True)

    contract: Mapped["LeaseContract"] = relationship("LeaseContract")


class LeasePayment(Base, TimestampMixin):
    __tablename__ = "lease_payments"

    id:             Mapped[int]            = mapped_column(primary_key=True)
    contract_id:    Mapped[int]            = mapped_column(ForeignKey("lease_contracts.id", ondelete="CASCADE"))
    due_date:       Mapped[date]           = mapped_column(Date, index=True)
    amount:         Mapped[Decimal]        = mapped_column(Numeric(12, 2))
    penalty:        Mapped[Decimal]        = mapped_column(Numeric(12, 2), default=Decimal("0"))
    paid_amount:    Mapped[Decimal]        = mapped_column(Numeric(12, 2), default=Decimal("0"))
    status:         Mapped[str]            = mapped_column(String(20), default="pending")
    # pending|paid|partial|overdue
    paid_at:        Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    payment_method: Mapped[str | None]     = mapped_column(String(30), nullable=True)
    receipt_number: Mapped[str | None]     = mapped_column(String(50), nullable=True)
    year_n:         Mapped[int]            = mapped_column(Integer, default=0)  # سنة العقد (للزيادة)
    notes:          Mapped[str | None]     = mapped_column(String(300), nullable=True)

    contract: Mapped["LeaseContract"] = relationship("LeaseContract", back_populates="payments")
