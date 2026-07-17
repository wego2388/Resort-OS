"""
app/modules/finance/models.py
Finance Module — always_on
Tables: folios, folio_charges, payments, conditional_discounts,
        accounts, journal_entries, journal_lines, accounting_periods,
        eta_invoices, asset_depreciation_entries, bank_accounts,
        bank_statement_lines, cash_movements
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer,
    Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.kernel.models.mixins import TimestampMixin
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
    # نطاق التطبيق — "order" (افتراضي، زي القديم بالظبط) يعني الخصم على إجمالي
    # الطلب كله أي outlet. "outlet" يقصر الخصم على مطعم/كافيه/شاطئ بعينه.
    # "category"/"item" يقصر الخصم على سطور الطلب المطابقة بس (مش الإجمالي
    # كله) — راجع docstring DiscountRule في app.resort_os.discount_engine
    # للتفاصيل الكاملة + صيغة condition_value الجديدة (time_of_day/combo_items).
    scope_type:      Mapped[str]         = mapped_column(String(20), default="order")
    scope_outlet:    Mapped[str | None]  = mapped_column(String(20), nullable=True)
    scope_id:        Mapped[int | None]  = mapped_column(Integer, nullable=True)


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
    # ⚠️ باج حقيقي كان هنا (اتصلح): restaurant/cafe كانوا بيبنوا FolioCharge
    # لطلب "الدفع على حساب الغرفة" من subtotal+vat بس — service_charge
    # (12% من الطلب، محسوب وموجود فعليًا على الـ Order) كان بيضيع تمامًا،
    # يعني فاتورة الضيف عند الـ checkout كانت أقل من المفروض بقيمة الخدمة.
    service_charge:   Mapped[Decimal]       = mapped_column(Numeric(10, 2), server_default="0", default=Decimal("0"))
    posted_at:        Mapped[datetime]      = mapped_column(DateTime)
    is_settled:       Mapped[bool]          = mapped_column(Boolean, default=False)
    ref_order_id:     Mapped[int | None]    = mapped_column(Integer, nullable=True)
    ref_beach_tx_id:  Mapped[int | None]    = mapped_column(Integer, nullable=True)

    folio: Mapped["Folio"] = relationship("Folio", back_populates="charges")


class Payment(Base, TimestampMixin):
    # ⚠️ باج حقيقي اتصلح: migration 504f42d2c755 (2026-07-15) عمل
    # folio_id nullable + ضاف عمود ref_order_id على جدول payments فعليًا
    # (alter_column + add_column على الداتابيز حقيقي)، بس الموديول SQLAlchemy
    # هنا عمره ما اتحدّث ليطابق — folio_id فضل Mapped[int] (غير nullable في
    # الـ ORM رغم إن العمود nullable فعليًا في الداتابيز)، وref_order_id
    # عمره ما كان موجود كـ attribute خالص. نفس فئة الباج "الموديل موجود
    # بس مش مطابق للداتابيز" (راجع migration نفسها: docstring بتقول صراحةً
    # "Direct POS sales (dining/beach) don't go through a Folio... Making
    # folio_id nullable lets us record a Payment with a shift_id so
    # cashier-shift reports see real totals" — نية واضحة اتسجّلت في
    # الـ migration بس عمرها ما اتنفّذت في كود حقيقي حتى اللحظة دي).
    __tablename__ = "payments"

    id:        Mapped[int]            = mapped_column(primary_key=True)
    folio_id:  Mapped[int | None]     = mapped_column(ForeignKey("folios.id", ondelete="RESTRICT"), nullable=True)
    branch_id: Mapped[int]            = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    amount:    Mapped[Decimal]        = mapped_column(Numeric(10, 2))
    currency:  Mapped[str]            = mapped_column(String(3), default="EGP")
    # موروثة من folio.currency وقت إنشاء الدفعة (مش قابلة للتحديد من العميل
    # مباشرة) — عشان نضمن اتساق عملة الفوليو مع كل دفعاته. لدفعة POS مباشرة
    # (folio_id=None) العملة الافتراضية EGP.
    method:    Mapped[str]            = mapped_column(String(30))
    reference: Mapped[str | None]     = mapped_column(String(100), nullable=True)
    notes:     Mapped[str | None]     = mapped_column(String(500), nullable=True)
    posted_at: Mapped[datetime]       = mapped_column(DateTime)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    voided_by: Mapped[int | None]      = mapped_column(Integer, nullable=True)
    cashier_id: Mapped[int | None]     = mapped_column(Integer, nullable=True, index=True)
    shift_id:  Mapped[int | None]      = mapped_column(ForeignKey("cashier_shifts.id", ondelete="SET NULL"), nullable=True, index=True)
    # مرجع اختياري لمصدر البيع المباشر (مثلاً DiningOrder.id) — بدون FK
    # حقيقي عمدًا (زي FolioCharge.ref_order_id بالظبط) لأن Payment مش بيتربط
    # بموديول عمل معيّن دايمًا (finance مش بيستورد dining/beach — راجع
    # طبقات المعمارية §4). المصدر الحقيقي القابل للقراءة دايمًا هو `reference`
    # (نص حر زي "BCH-000123").
    ref_order_id: Mapped[int | None]   = mapped_column(Integer, nullable=True)

    folio: Mapped["Folio | None"] = relationship("Folio", back_populates="payments")
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
    """تفاصيل عدّ النقدية بالفئة وقت قفل الوردية — بيدعم عملات متعددة (EGP/USD/EUR).

    مثال: 5×200ج (EGP) + 10×$1 (USD fx=48) + 2×€50 (EUR fx=52)
    - denomination: قيمة الورقة بعملتها الأصلية
    - currency: عملة هذا السطر — افتراضي EGP
    - subtotal: denomination × quantity (بالعملة الأصلية — للعرض)
    - egp_equivalent: subtotal × fx_rate — القيمة بالجنيه (للمطابقة)
    - fx_rate: سعر الصرف وقت العدّ (1.0 للـ EGP) — للتدقيق التاريخي
    """
    __tablename__ = "cashier_shift_cash_counts"

    id:             Mapped[int]     = mapped_column(primary_key=True)
    shift_id:       Mapped[int]     = mapped_column(ForeignKey("cashier_shifts.id", ondelete="CASCADE"), index=True)
    denomination:   Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency:       Mapped[str]     = mapped_column(String(3), default="EGP")
    quantity:       Mapped[int]     = mapped_column(Integer)
    subtotal:       Mapped[Decimal] = mapped_column(Numeric(10, 2))
    fx_rate:        Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("1"))
    egp_equivalent: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    shift: Mapped["CashierShift"] = relationship("CashierShift", back_populates="cash_count_lines")


class CashMovement(Base, TimestampMixin):
    """حركة نقدية يدوية على درج الكاشير — إيداع/سحب/عهدة نثرية/تنزيل خزنة/
    فتح الدرج/تصحيح — منفصلة تمامًا عن أي حركة بيع (Payment). راجع Operations
    & Control Layer plan §3.2: كشف Click القديم كان بيسجّل كل حركة يدوية على
    الدرج في Safe_History.IsApproved، مش بس التصحيحات — نفس القرار هنا (قرار
    Mohamed 2026-07-13 عن "التصحيح" حصرًا اتوسّع ليشمل بقية الأنواع، لأنها
    نفس فئة الخطر بالظبط؛ راجع تقرير الدفعة دي لو حابب تضيّق النطاق لاحقًا).

    كل حركة (بغض النظر عن نوعها) من مستوى أقل من مدير محتاجة موافقة PIN —
    راجع finance.services.record_cash_movement و core.services.resolve_pin_approval
    (نفس الدالة المركزية المستخدمة في void/discount/close_shift variance،
    مفيش نظام موافقة موازي).

    ``destination`` (2026-07-16، بحث مقارنة Click القديم): Click كان بيمثّل
    الخزنة الرئيسية/البنك/الفيزا كمواقع مستقلة كل واحدة ليها حساب GL خاص —
    قرار متعمد إننا *مانبنيش* ledger موازي كامل بأرصدة تراكمية لكل موقع في
    الدفعة دي (ده تحسين تاني أكبر، مش استخراج). اللي فعليًا مفيد ومنخفض
    المخاطرة: تسجيل *فين رايح* الكاش لما يسيب الدرج (``safe_drop`` بس —
    باقي الأنواع تبادل جوه الدرج نفسه، مفيش "وجهة" منطقية ليها). ``None``
    لأي نوع حركة تاني، أو لـ safe_drop قديم اتسجّل قبل الحقل ده.
    ``cost_center_id``: تاجّ اختياري، مفيش اشتقاق تلقائي زي outlet_type→
    cost_center في dining/beach (مفيش "منفذ" واضح لحركة كاش يدوية عامة) —
    الكاشير/المحاسب بيختاره وقت التسجيل لو حابب."""
    __tablename__ = "cash_movements"

    id:            Mapped[int]           = mapped_column(primary_key=True)
    branch_id:     Mapped[int]           = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), index=True)
    shift_id:      Mapped[int]           = mapped_column(ForeignKey("cashier_shifts.id", ondelete="CASCADE"), index=True)
    movement_type: Mapped[str]           = mapped_column(String(20), index=True)
    # cash_in | cash_out | petty_cash | safe_drop | drawer_open | correction
    amount:        Mapped[Decimal]       = mapped_column(Numeric(10, 2), default=Decimal("0"))
    reason:        Mapped[str]           = mapped_column(String(500))
    destination:    Mapped[str | None]   = mapped_column(String(20), nullable=True)
    # main_safe | bank | petty_cash_box — بس لـ movement_type="safe_drop"
    cost_center_id: Mapped[int | None]   = mapped_column(
        ForeignKey("cost_centers.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    performed_by:  Mapped[int]           = mapped_column(Integer)
    approved_by:   Mapped[int | None]    = mapped_column(Integer, nullable=True)

    shift: Mapped["CashierShift"] = relationship("CashierShift")


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
    # مركز التكلفة اللي السطر ده بيخص أي موديول (ROOM/REST/CAFE/BEACH/TS) —
    # بيتحدد وقت الترحيل نفسه (راجع services.post_simple_revenue_journal's
    # cost_center_code) بدل استنتاجه بعدين من account_id/source زي ما كان
    # get_cost_center_report بيعمل قبل كده. nullable — قيود عامة (تحصيل/
    # إلغاء دفعة فوليو، رواتب...) مش دايمًا مرتبطة بمركز تكلفة واحد واضح.
    cost_center_id: Mapped[int | None] = mapped_column(
        ForeignKey("cost_centers.id", ondelete="SET NULL"), nullable=True, index=True,
    )

    entry:       Mapped["JournalEntry"]      = relationship("JournalEntry", back_populates="lines")
    account:     Mapped["Account"]           = relationship("Account", back_populates="lines")
    cost_center: Mapped["CostCenter | None"] = relationship("CostCenter")


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


# ── Fixed-Asset Depreciation (straight-line MVP) ───────────────────────

class AssetDepreciationEntry(Base, TimestampMixin):
    """سطر إهلاك شهري واحد لأصل واحد — مصدر الحقيقة للتاريخ الكامل، بينما
    Asset.accumulated_depreciation (maintenance module) نسخة مجمّعة (cache)
    بتتحدّث مع كل سطر جديد. UniqueConstraint يمنع تشغيل نفس الشهر مرتين
    لنفس الأصل (إعادة تشغيل run_depreciation آمنة/idempotent)."""
    __tablename__ = "asset_depreciation_entries"
    __table_args__ = (
        UniqueConstraint("asset_id", "year", "month", name="uq_depreciation_asset_period"),
    )

    id:                Mapped[int]           = mapped_column(primary_key=True)
    asset_id:          Mapped[int]           = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    branch_id:         Mapped[int]           = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    year:              Mapped[int]           = mapped_column(Integer)
    month:             Mapped[int]           = mapped_column(Integer)
    amount:            Mapped[Decimal]       = mapped_column(Numeric(12, 2))
    accumulated_after: Mapped[Decimal]       = mapped_column(Numeric(12, 2))
    journal_entry_id:  Mapped[int | None]    = mapped_column(ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True)
    posted_by:         Mapped[int]           = mapped_column(Integer)


# ── Bank Reconciliation ─────────────────────────────────────────────────

class BankAccount(Base, TimestampMixin):
    """حساب بنكي حقيقي للمنتجع — نقطة الربط بين كشف حساب البنك والدفاتر."""
    __tablename__ = "bank_accounts"
    __table_args__ = (
        UniqueConstraint("branch_id", "account_number", name="uq_bank_account_branch_number"),
    )

    id:              Mapped[int]           = mapped_column(primary_key=True)
    branch_id:       Mapped[int]           = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    bank_name:       Mapped[str]           = mapped_column(String(150))
    account_name:    Mapped[str]           = mapped_column(String(200))
    account_number:  Mapped[str]           = mapped_column(String(50))
    currency:        Mapped[str]           = mapped_column(String(3), default="EGP")
    gl_account_id:   Mapped[int | None]    = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    # حساب دفتر اليومية المقابل (asset type، عادة "البنك") — اختياري، لو
    # موجود بيسمح بمقارنة رصيد الدفاتر برصيد كشف الحساب في تقرير المطابقة.
    opening_balance: Mapped[Decimal]       = mapped_column(Numeric(12, 2), default=Decimal("0"))
    is_active:       Mapped[bool]          = mapped_column(Boolean, default=True)

    statement_lines: Mapped[list["BankStatementLine"]] = relationship(
        "BankStatementLine", back_populates="bank_account", lazy="select",
    )


class BankStatementLine(Base, TimestampMixin):
    """سطر واحد من كشف حساب البنك — مستورد يدوياً (لصق/إدخال القيم)، بعدين
    بيتطابق (auto أو manual) مع دفعة (Payment) حقيقية مسجّلة في النظام."""
    __tablename__ = "bank_statement_lines"

    id:                     Mapped[int]           = mapped_column(primary_key=True)
    bank_account_id:        Mapped[int]           = mapped_column(ForeignKey("bank_accounts.id", ondelete="CASCADE"), index=True)
    branch_id:              Mapped[int]           = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    line_date:               Mapped[date]          = mapped_column(Date, index=True)
    description:            Mapped[str]           = mapped_column(String(300))
    amount:                 Mapped[Decimal]       = mapped_column(Numeric(12, 2))
    # موجب = إيداع (deposit)، سالب = سحب/عمولة بنكية (withdrawal)
    external_reference:     Mapped[str | None]    = mapped_column(String(100), nullable=True)
    status:                 Mapped[str]           = mapped_column(String(20), default="unmatched", index=True)
    # unmatched | matched | ignored
    matched_payment_id:     Mapped[int | None]    = mapped_column(ForeignKey("payments.id", ondelete="SET NULL"), nullable=True)
    matched_at:             Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    matched_by:             Mapped[int | None]     = mapped_column(Integer, nullable=True)
    uploaded_by:            Mapped[int]           = mapped_column(Integer)

    bank_account: Mapped["BankAccount"] = relationship("BankAccount", back_populates="statement_lines")
    matched_payment: Mapped["Payment"]  = relationship("Payment")


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
