"""
app/modules/finance/models.py
Finance Module — always_on
Tables: folios, folio_charges, payments, conditional_discounts,
        accounts, journal_entries, journal_lines, accounting_periods,
        eta_invoices
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


class ConditionalDiscount(Base, TimestampMixin):
    __tablename__ = "conditional_discounts"

    id:              Mapped[int]     = mapped_column(primary_key=True)
    branch_id:       Mapped[int]     = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    condition_type:  Mapped[str]     = mapped_column(String(40))
    condition_value: Mapped[str]     = mapped_column(String(100))
    discount_type:   Mapped[str]     = mapped_column(String(30))
    discount_value:  Mapped[Decimal] = mapped_column(Numeric(10, 2))
    max_uses:        Mapped[int]     = mapped_column(Integer, default=-1)
    uses_count:      Mapped[int]     = mapped_column(Integer, default=0)
    valid_from:      Mapped[date]    = mapped_column(Date)
    valid_until:     Mapped[date]    = mapped_column(Date)
    priority:        Mapped[int]     = mapped_column(Integer, default=1)
    is_active:       Mapped[bool]    = mapped_column(Boolean, default=True)


class Folio(Base, TimestampMixin):
    __tablename__ = "folios"

    id:         Mapped[int]      = mapped_column(primary_key=True)
    branch_id:  Mapped[int]      = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    guest_name: Mapped[str]      = mapped_column(String(200))
    check_in:   Mapped[datetime] = mapped_column(DateTime)
    check_out:  Mapped[datetime] = mapped_column(DateTime)
    status:     Mapped[str]      = mapped_column(String(20), default="open")
    total:      Mapped[Decimal]  = mapped_column(Numeric(12, 2), default=Decimal("0"))
    currency:   Mapped[str]      = mapped_column(String(3), default="EGP")
    # عملة الفوليو — تتحدد مرة واحدة عند الإنشاء وهي المرجع الوحيد (source of
    # truth) لكل charges/payments تحت نفس الفوليو. لا نخزّن عملة منفصلة لكل
    # FolioCharge — نفس منطق folio.total (رصيد واحد مجمّع)، والافتراض إن كل
    # حركات الفوليو بنفس عملته طول عمره (لا تحويل عملة نصف الطريق).

    charges:  Mapped[list["FolioCharge"]] = relationship("FolioCharge", back_populates="folio", lazy="select")
    payments: Mapped[list["Payment"]]     = relationship("Payment",     back_populates="folio", lazy="select")


class FolioCharge(Base, TimestampMixin):
    __tablename__ = "folio_charges"

    id:               Mapped[int]           = mapped_column(primary_key=True)
    folio_id:         Mapped[int]           = mapped_column(ForeignKey("folios.id", ondelete="RESTRICT"))
    charge_type:      Mapped[str]           = mapped_column(String(30))
    description:      Mapped[str]           = mapped_column(String(300))
    amount:           Mapped[Decimal]       = mapped_column(Numeric(10, 2))
    vat_amount:       Mapped[Decimal]       = mapped_column(Numeric(10, 2), default=Decimal("0"))
    posted_at:        Mapped[datetime]      = mapped_column(DateTime)
    is_settled:       Mapped[bool]          = mapped_column(Boolean, default=False)
    ref_order_id:     Mapped[int | None]    = mapped_column(Integer, nullable=True)
    ref_beach_tx_id:  Mapped[int | None]    = mapped_column(Integer, nullable=True)

    folio: Mapped["Folio"] = relationship("Folio", back_populates="charges")


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id:        Mapped[int]            = mapped_column(primary_key=True)
    folio_id:  Mapped[int]            = mapped_column(ForeignKey("folios.id", ondelete="RESTRICT"))
    branch_id: Mapped[int]            = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    amount:    Mapped[Decimal]        = mapped_column(Numeric(10, 2))
    currency:  Mapped[str]            = mapped_column(String(3), default="EGP")
    # موروثة من folio.currency وقت إنشاء الدفعة (مش قابلة للتحديد من العميل
    # مباشرة) — عشان نضمن اتساق عملة الفوليو مع كل دفعاته.
    method:    Mapped[str]            = mapped_column(String(30))
    reference: Mapped[str | None]     = mapped_column(String(100), nullable=True)
    notes:     Mapped[str | None]     = mapped_column(String(500), nullable=True)
    posted_at: Mapped[datetime]       = mapped_column(DateTime)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    voided_by: Mapped[int | None]      = mapped_column(Integer, nullable=True)
    cashier_id: Mapped[int | None]     = mapped_column(Integer, nullable=True, index=True)
    shift_id:  Mapped[int | None]      = mapped_column(ForeignKey("cashier_shifts.id", ondelete="SET NULL"), nullable=True, index=True)

    folio: Mapped["Folio"] = relationship("Folio", back_populates="payments")
    shift: Mapped["CashierShift"] = relationship("CashierShift", back_populates="payments")


class CashierShift(Base, TimestampMixin):
    """وردية الكاشير / درج النقدية اليومي (POS Day) — فتح برصيد ابتدائي،
    قفل بعدّ نقدي فعلي مقابل المتوقع (variance)."""
    __tablename__ = "cashier_shifts"

    id:             Mapped[int]           = mapped_column(primary_key=True)
    branch_id:      Mapped[int]           = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    cashier_id:     Mapped[int]           = mapped_column(Integer, index=True)
    opened_at:      Mapped[datetime]      = mapped_column(DateTime)
    opened_by:      Mapped[int]           = mapped_column(Integer)
    opening_float:  Mapped[Decimal]       = mapped_column(Numeric(10, 2), default=Decimal("0"))
    status:         Mapped[str]           = mapped_column(String(20), default="open", index=True)
    # open | closed
    closed_at:      Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_by:      Mapped[int | None]      = mapped_column(Integer, nullable=True)
    expected_cash:  Mapped[Decimal | None]  = mapped_column(Numeric(10, 2), nullable=True)
    counted_cash:   Mapped[Decimal | None]  = mapped_column(Numeric(10, 2), nullable=True)
    variance:       Mapped[Decimal | None]  = mapped_column(Numeric(10, 2), nullable=True)
    notes:          Mapped[str | None]      = mapped_column(String(1000), nullable=True)
    handover_note:  Mapped[str | None]      = mapped_column(String(1000), nullable=True)
    # ملاحظة تسليم للوردية الجاية تحديدًا (مختلفة عن notes العامة) — بتتكتب
    # وقت القفل، وبيشوفها اللي هيفتح الوردية الجاية في نفس الفرع قبل ما يبدأ

    payments: Mapped[list["Payment"]] = relationship("Payment", back_populates="shift", lazy="select")
    cash_count_lines: Mapped[list["CashierShiftCashCount"]] = relationship(
        "CashierShiftCashCount", back_populates="shift", lazy="select", cascade="all, delete-orphan",
    )


class CashierShiftCashCount(Base, TimestampMixin):
    """تفاصيل عدّ النقدية بالفئة (200ج × 5، 100ج × 3...) وقت قفل الوردية —
    محفوظة للتدقيق حتى لو الكاشير غيّر رأيه أو حصل خلاف على الإجمالي المعدود."""
    __tablename__ = "cashier_shift_cash_counts"

    id:           Mapped[int]      = mapped_column(primary_key=True)
    shift_id:     Mapped[int]      = mapped_column(ForeignKey("cashier_shifts.id", ondelete="CASCADE"), index=True)
    denomination: Mapped[Decimal]  = mapped_column(Numeric(10, 2))
    quantity:     Mapped[int]      = mapped_column(Integer)
    subtotal:     Mapped[Decimal]  = mapped_column(Numeric(10, 2))

    shift: Mapped["CashierShift"] = relationship("CashierShift", back_populates="cash_count_lines")


# ── Double-Entry Accounting ────────────────────────────────────────────

class Account(Base, TimestampMixin):
    """دليل الحسابات (Chart of Accounts)"""
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("branch_id", "code", name="uq_accounts_branch_code"),)

    id:           Mapped[int]      = mapped_column(primary_key=True)
    branch_id:    Mapped[int]      = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    code:         Mapped[str]      = mapped_column(String(20))
    name:         Mapped[str]      = mapped_column(String(200))
    name_ar:      Mapped[str | None] = mapped_column(String(200), nullable=True)
    account_type: Mapped[str]      = mapped_column(String(30))  # asset|liability|equity|revenue|expense
    parent_id:    Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    is_active:    Mapped[bool]     = mapped_column(Boolean, default=True)

    lines: Mapped[list["JournalLine"]] = relationship("JournalLine", back_populates="account", lazy="select")


class JournalEntry(Base, TimestampMixin):
    """قيد يومية - السجل الرئيسي"""
    __tablename__ = "journal_entries"

    id:          Mapped[int]      = mapped_column(primary_key=True)
    branch_id:   Mapped[int]      = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    entry_date:  Mapped[date]     = mapped_column(Date, index=True)
    reference:   Mapped[str]      = mapped_column(String(50))
    description: Mapped[str]      = mapped_column(String(500))
    status:      Mapped[str]      = mapped_column(String(20), default="posted")
    created_by:  Mapped[int]      = mapped_column(Integer)
    source:      Mapped[str | None]  = mapped_column(String(50), nullable=True)
    source_id:   Mapped[int | None]  = mapped_column(Integer, nullable=True)
    currency:    Mapped[str]      = mapped_column(String(3), default="EGP")
    fx_rate:     Mapped[Decimal]  = mapped_column(Numeric(12, 6), default=Decimal("1"))
    # مبالغ السطور (debit/credit) دايمًا EGP-equivalent — نفس اللي التقارير
    # (trial balance/income statement/balance sheet) بتجمعها مباشرة من غير أي
    # تحويل. currency/fx_rate هنا بيسجّلوا العملة الأصلية للقيد وسعر التحويل
    # وقتها بس، عشان تقدر تعرض/تراجع المبلغ الأصلي (amount = line_amount /
    # fx_rate) من غير ما تكسر أي جمع موجود فعلاً.

    lines: Mapped[list["JournalLine"]] = relationship("JournalLine", back_populates="entry", lazy="select")


class JournalLine(Base, TimestampMixin):
    """سطر قيد يومية - مجموع المدين لازم يساوي مجموع الدائن في القيد كله"""
    __tablename__ = "journal_lines"

    id:          Mapped[int]      = mapped_column(primary_key=True)
    entry_id:    Mapped[int]      = mapped_column(ForeignKey("journal_entries.id", ondelete="CASCADE"))
    account_id:  Mapped[int]      = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    debit:       Mapped[Decimal]  = mapped_column(Numeric(12, 2), default=Decimal("0"))
    credit:      Mapped[Decimal]  = mapped_column(Numeric(12, 2), default=Decimal("0"))
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)

    entry:   Mapped["JournalEntry"] = relationship("JournalEntry", back_populates="lines")
    account: Mapped["Account"]      = relationship("Account", back_populates="lines")


class AccountingPeriod(Base, TimestampMixin):
    """فترة محاسبية - لو مقفولة، بتمنع ترحيل أي قيود يومية جديدة فيها"""
    __tablename__ = "accounting_periods"
    __table_args__ = (UniqueConstraint("branch_id", "year", "month", name="uq_period_branch_year_month"),)

    id:        Mapped[int]           = mapped_column(primary_key=True)
    branch_id: Mapped[int]           = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    year:      Mapped[int]           = mapped_column(Integer)
    month:     Mapped[int]           = mapped_column(Integer)
    status:    Mapped[str]           = mapped_column(String(20), default="open")
    closed_by: Mapped[int | None]    = mapped_column(Integer, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Check(Base, TimestampMixin):
    __tablename__ = "checks"

    id:            Mapped[int]          = mapped_column(primary_key=True)
    branch_id:     Mapped[int]          = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    check_number:  Mapped[str]          = mapped_column(String(50))
    bank_name:     Mapped[str]          = mapped_column(String(150))
    amount:        Mapped[Decimal]      = mapped_column(Numeric(12, 2))
    due_date:      Mapped[date]         = mapped_column(Date)
    drawer_name:   Mapped[str]          = mapped_column(String(200))
    status:        Mapped[str]          = mapped_column(String(20), default="received")
    # received | deposited | cleared | bounced
    notes:         Mapped[str | None]   = mapped_column(Text, nullable=True)
    created_by:    Mapped[int]          = mapped_column(Integer)
    received_at:   Mapped[date]         = mapped_column(Date)
    deposited_at:  Mapped[date | None]  = mapped_column(Date, nullable=True)
    cleared_at:    Mapped[date | None]  = mapped_column(Date, nullable=True)
    bounced_at:    Mapped[date | None]  = mapped_column(Date, nullable=True)

    movements: Mapped[list["CheckMovement"]] = relationship("CheckMovement", back_populates="check_obj", lazy="select")


class CheckMovement(Base, TimestampMixin):
    __tablename__ = "check_movements"

    id:          Mapped[int]         = mapped_column(primary_key=True)
    check_id:    Mapped[int]         = mapped_column(ForeignKey("checks.id", ondelete="CASCADE"))
    from_status: Mapped[str]         = mapped_column(String(20))
    to_status:   Mapped[str]         = mapped_column(String(20))
    moved_by:    Mapped[int]         = mapped_column(Integer)
    notes:       Mapped[str | None]  = mapped_column(String(300), nullable=True)

    check_obj: Mapped["Check"] = relationship("Check", back_populates="movements")


class CostCenter(Base, TimestampMixin):
    __tablename__ = "cost_centers"
    __table_args__ = (UniqueConstraint("branch_id", "code", name="uq_cost_center_branch_code"),)

    id:        Mapped[int]          = mapped_column(primary_key=True)
    branch_id: Mapped[int]          = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    code:      Mapped[str]          = mapped_column(String(20))
    name:      Mapped[str]          = mapped_column(String(200))
    is_active: Mapped[bool]         = mapped_column(Boolean, default=True)


class ExchangeRate(Base, TimestampMixin):
    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("from_currency", "to_currency", "effective_date", name="uq_exchange_rate"),)

    id:             Mapped[int]    = mapped_column(primary_key=True)
    from_currency:  Mapped[str]    = mapped_column(String(3))
    to_currency:    Mapped[str]    = mapped_column(String(3))
    rate:           Mapped[Decimal] = mapped_column(Numeric(12, 6))
    effective_date: Mapped[date]   = mapped_column(Date)
    created_by:     Mapped[int]    = mapped_column(Integer)


class RevenueAuditLog(Base, TimestampMixin):
    """سجل تدقيق إلزامي لأي تغيير في سعر أو خصم."""
    __tablename__ = "revenue_audit_logs"

    id:           Mapped[int]         = mapped_column(primary_key=True)
    branch_id:    Mapped[int]         = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    entity_type:  Mapped[str]         = mapped_column(String(30))
    # booking|folio|invoice|payment
    entity_id:    Mapped[int]         = mapped_column(Integer)
    old_value:    Mapped[Decimal]     = mapped_column(Numeric(12, 2))
    new_value:    Mapped[Decimal]     = mapped_column(Numeric(12, 2))
    reason:       Mapped[str]         = mapped_column(String(500))
    changed_by:   Mapped[int]         = mapped_column(Integer)
    approved_by:  Mapped[int | None]  = mapped_column(Integer, nullable=True)


class ETAInvoice(Base, TimestampMixin):
    """تتبّع إرسال الفاتورة الإلكترونية لمصلحة الضرائب (ETA)."""
    __tablename__ = "eta_invoices"

    id:               Mapped[int]          = mapped_column(primary_key=True)
    branch_id:        Mapped[int]          = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    folio_id:         Mapped[int | None]   = mapped_column(ForeignKey("folios.id", ondelete="SET NULL"), nullable=True)
    internal_id:      Mapped[str]          = mapped_column(String(50), unique=True)
    submission_uuid:  Mapped[str | None]   = mapped_column(String(100), nullable=True)
    long_id:          Mapped[str | None]   = mapped_column(String(100), nullable=True)
    status:           Mapped[str]          = mapped_column(String(20), default="pending")
    # pending|submitted|valid|invalid|failed
    document_json:    Mapped[str]          = mapped_column(Text)
    response_json:    Mapped[str | None]   = mapped_column(Text, nullable=True)
    error_message:    Mapped[str | None]   = mapped_column(String(1000), nullable=True)
    submitted_at:     Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
