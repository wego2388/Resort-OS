"""app/modules/finance/schemas.py — Pydantic v2"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConditionalDiscountCreate(BaseModel):
    branch_id:       int
    condition_type:  str = Field(..., pattern=r"^(total_amount|item_count|day_of_week|customer_group)$")
    condition_value: str = Field(..., max_length=100)
    discount_type:   str = Field(..., pattern=r"^(percentage|fixed_amount|free_item)$")
    discount_value:  Decimal = Field(..., ge=0)
    max_uses:        int = -1
    valid_from:      date
    valid_until:     date
    priority:        int = 1
    is_active:       bool = True


class ConditionalDiscountUpdate(BaseModel):
    condition_value: Optional[str]     = None
    discount_value:  Optional[Decimal] = None
    max_uses:        Optional[int]     = None
    valid_from:      Optional[date]    = None
    valid_until:     Optional[date]    = None
    priority:        Optional[int]     = None
    is_active:       Optional[bool]    = None


class ConditionalDiscountRead(ConditionalDiscountCreate):
    model_config = ConfigDict(from_attributes=True)
    id:         int
    uses_count: int
    created_at: datetime
    updated_at: datetime


class FolioCreate(BaseModel):
    branch_id:  int
    guest_name: str = Field(..., max_length=200)
    check_in:   datetime
    check_out:  datetime
    currency:   str = Field("EGP", pattern=r"^[A-Z]{3}$")
    # عملة الفوليو — ثابتة طول عمره، افتراضها EGP للتوافق مع أي كود قديم
    # مابيبعتش الحقل ده أصلاً.


class FolioUpdate(BaseModel):
    guest_name: Optional[str]      = None
    check_out:  Optional[datetime] = None
    status:     Optional[str]      = Field(None, pattern=r"^(open|closed|cancelled)$")


class FolioChargeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:              int
    folio_id:        int
    charge_type:     str
    description:     str
    amount:          Decimal
    vat_amount:      Decimal
    posted_at:       datetime
    is_settled:      bool
    ref_order_id:    Optional[int]
    ref_beach_tx_id: Optional[int]
    created_at:      datetime


class FolioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:         int
    branch_id:  int
    guest_name: str
    check_in:   datetime
    check_out:  datetime
    status:     str
    total:      Decimal
    currency:   str
    charges:    list[FolioChargeRead] = []
    created_at: datetime
    updated_at: datetime


class FolioChargeCreate(BaseModel):
    charge_type:     str = Field(..., max_length=30)
    description:     str = Field(..., max_length=300)
    amount:          Decimal = Field(..., gt=0)
    vat_amount:      Decimal = Field(Decimal("0"), ge=0)
    posted_at:       datetime
    ref_order_id:    Optional[int] = None
    ref_beach_tx_id: Optional[int] = None


class PaymentCreate(BaseModel):
    folio_id:  int
    branch_id: int
    amount:    Decimal = Field(..., gt=0)
    method:    str = Field(..., pattern=r"^(cash|card|bank_transfer|credit|room_charge|other)$")
    # credit = آجل (on-account / deferred payment)
    reference: Optional[str] = Field(None, max_length=100)
    notes:     Optional[str] = Field(None, max_length=500)
    posted_at: datetime
    cashier_id: Optional[int] = None


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:        int
    folio_id:  int
    branch_id: int
    amount:    Decimal
    currency:  str
    method:    str
    reference: Optional[str]
    notes:     Optional[str]
    posted_at: datetime
    voided_at: Optional[datetime]
    voided_by: Optional[int]
    cashier_id: Optional[int]
    shift_id:   Optional[int]
    created_at: datetime


# ── Cashier Shift / Safe (POS Day) ─────────────────────────────────────

class CashierShiftOpen(BaseModel):
    branch_id:     int
    opening_float: Decimal = Field(Decimal("0"), ge=0)
    notes:         Optional[str] = Field(None, max_length=1000)


class CashCountLine(BaseModel):
    denomination: Decimal = Field(..., gt=0)
    quantity:     int     = Field(..., ge=0)


class CashCountLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    denomination: Decimal
    quantity:     int
    subtotal:     Decimal


class CashierShiftClose(BaseModel):
    counted_cash:  Optional[Decimal] = Field(None, ge=0)
    cash_count:    Optional[list[CashCountLine]] = None
    notes:         Optional[str] = Field(None, max_length=1000)
    handover_note: Optional[str] = Field(None, max_length=1000)
    # ملاحظة تسليم — بتظهر لصاحب الوردية الجاية في نفس الفرع (راجع
    # GET /finance/shifts/handover-note) قبل ما يفتح ورديته

    @model_validator(mode="after")
    def _require_counted_amount(self) -> "CashierShiftClose":
        if self.counted_cash is None and not self.cash_count:
            raise ValueError("لازم تدخل المبلغ المعدود (counted_cash) أو تفاصيل عدّ الفئات (cash_count)")
        return self


class CashierShiftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:            int
    branch_id:     int
    cashier_id:    int
    opened_at:     datetime
    opened_by:     int
    opening_float: Decimal
    status:        str
    closed_at:     Optional[datetime]
    closed_by:     Optional[int]
    expected_cash: Optional[Decimal]
    counted_cash:  Optional[Decimal]
    variance:      Optional[Decimal]
    notes:         Optional[str]
    handover_note: Optional[str] = None
    created_at:    datetime


class ShiftEndReport(BaseModel):
    """تقرير نهاية الوردية — لكل كاشير: كاش + كارت + آجل، عدد الفواتير،
    المرتجع/الملغي، ومقارنة بالوردية السابقة لنفس الكاشير."""
    shift_id:             int
    branch_id:            int
    cashier_id:           int
    status:               str
    opened_at:             datetime
    closed_at:             Optional[datetime]
    opening_float:         Decimal
    total_cash:            Decimal
    total_card:            Decimal
    total_credit:          Decimal
    total_other:           Decimal
    total_sales:           Decimal
    invoice_count:         int
    voided_count:          int
    voided_amount:         Decimal
    expected_cash:         Decimal
    counted_cash:          Optional[Decimal]
    variance:              Optional[Decimal]
    cash_count:            list[CashCountLineRead] = Field(default_factory=list)
    previous_shift_id:     Optional[int]
    previous_total_sales:  Optional[Decimal]
    delta_vs_previous:     Optional[Decimal]
    reporting_currency:    str = "EGP"
    # كل الإجماليات هنا EGP equivalent — أي دفعة بعملة غير EGP بتتحوّل بسعر
    # الصرف وقت تاريخ الدفعة قبل الجمع (راجع build_shift_end_report).


class DiscountCalculateRequest(BaseModel):
    branch_id:      int
    order_total:    Decimal = Field(..., gt=0)
    item_count:     int = Field(1, ge=1)
    customer_group: str = "default"
    order_date:     Optional[date] = None


# ── Double-Entry Accounting Schemas ───────────────────────────────────

class AccountCreate(BaseModel):
    branch_id:    int
    code:         str = Field(..., max_length=20)
    name:         str = Field(..., max_length=200)
    name_ar:      Optional[str] = Field(None, max_length=200)
    account_type: str = Field(..., pattern=r"^(asset|liability|equity|revenue|expense)$")
    parent_id:    Optional[int] = None
    is_active:    bool = True


class AccountRead(AccountCreate):
    model_config = ConfigDict(from_attributes=True)
    id:         int
    created_at: datetime
    updated_at: datetime


class JournalLineCreate(BaseModel):
    account_id:  int
    debit:       Decimal = Field(Decimal("0"), ge=0)
    credit:      Decimal = Field(Decimal("0"), ge=0)
    description: Optional[str] = Field(None, max_length=300)


class JournalLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:          int
    entry_id:    int
    account_id:  int
    debit:       Decimal
    credit:      Decimal
    description: Optional[str]
    created_at:  datetime


class JournalEntryCreate(BaseModel):
    branch_id:   int
    entry_date:  date
    reference:   str = Field(..., max_length=50)
    description: str = Field(..., max_length=500)
    source:      Optional[str] = Field(None, max_length=50)
    source_id:   Optional[int] = None
    currency:    str = Field("EGP", max_length=3)
    fx_rate:     Decimal = Field(Decimal("1"), gt=0)
    # مبالغ lines لازم تكون بالفعل EGP-equivalent (بعد التحويل) — currency/fx_rate
    # هنا بيسجّلوا بس عملة القيد الأصلية وسعر التحويل وقتها للعرض/المراجعة، مش
    # للتحويل التلقائي وقت الإدخال.
    lines:       list[JournalLineCreate] = Field(..., min_length=2)


class JournalEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:          int
    branch_id:   int
    entry_date:  date
    reference:   str
    description: str
    status:      str
    created_by:  int
    source:      Optional[str]
    source_id:   Optional[int]
    currency:    str
    fx_rate:     Decimal
    lines:       list[JournalLineRead] = []
    created_at:  datetime
    updated_at:  datetime


class AccountingPeriodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:        int
    branch_id: int
    year:      int
    month:     int
    status:    str
    closed_by: Optional[int]
    closed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class ClosePeriodRequest(BaseModel):
    branch_id: int


# ─────────────────────── Checks ────────────────────────────────────────
# ملاحظة: كانت الـ endpoints دي بتاخد `dict` خام من غير أي Pydantic validation
# — بيشتغل مصادفةً على Postgres (بيحوّل نص التاريخ ضمنياً) لكن بيطيح فعلياً
# على SQLite (تحديداً tests/) بـ TypeError. اتصلح بإضافة schemas صريحة.

class CheckCreate(BaseModel):
    branch_id:    int
    check_number: str = Field(..., max_length=50)
    bank_name:    str = Field(..., max_length=150)
    amount:       Decimal = Field(..., gt=0)
    due_date:     date
    drawer_name:  str = Field(..., max_length=200)
    received_at:  date
    notes:        Optional[str] = None


class CheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:           int
    branch_id:    int
    check_number: str
    bank_name:    str
    amount:       Decimal
    due_date:     date
    drawer_name:  str
    status:       str
    notes:        Optional[str]
    created_by:   int
    received_at:  date
    deposited_at: Optional[date]
    cleared_at:   Optional[date]
    bounced_at:   Optional[date]
    created_at:   datetime
    updated_at:   datetime


class CheckMoveStatus(BaseModel):
    to_status: str = Field(..., pattern=r"^(received|deposited|cleared|bounced)$")
    notes:     Optional[str] = None


# ─────────────────────── ETA E-Invoice ────────────────────────────────

class ETAInvoiceLineItem(BaseModel):
    description: str
    quantity:    float = Field(..., gt=0)
    unit_price:  float = Field(..., ge=0)
    vat_rate:    Optional[float] = None  # افتراضي: settings.VAT_PERCENTAGE
    item_code:   Optional[str] = None    # GS1 code — افتراضي EG-99999999


class ETAInvoiceSubmitRequest(BaseModel):
    branch_id:     int
    folio_id:      Optional[int] = None
    receiver_name: str
    receiver_rin:  Optional[str] = None  # فاضي = B2C
    line_items:    list[ETAInvoiceLineItem] = Field(..., min_length=1)


class ETAInvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:              int
    branch_id:       int
    folio_id:        Optional[int]
    internal_id:     str
    submission_uuid: Optional[str]
    long_id:         Optional[str]
    status:          str
    error_message:   Optional[str]
    submitted_at:    Optional[datetime]
    created_at:      datetime


# ── Cost Centers ─────────────────────────────────────────────────────

class CostCenterCreate(BaseModel):
    branch_id: int
    code:      str = Field(..., max_length=20)
    name:      str = Field(..., max_length=200)
    is_active: bool = True


class CostCenterRead(CostCenterCreate):
    model_config = ConfigDict(from_attributes=True)
    id:         int
    created_at: datetime
    updated_at: datetime


class CostCenterReportLine(BaseModel):
    code:    str
    name:    str
    revenue: Decimal
    source:  str  # "ledger" (من دفتر اليومية) | "direct" (من جداول العمليات مباشرة)


class CostCenterReport(BaseModel):
    branch_id:          int
    date_from:          date
    date_to:            date
    lines:              list[CostCenterReportLine]
    total_revenue:      Decimal
    reporting_currency: str = "EGP"
    # المصدر "direct" (REST/CAFE/BEACH) بيقرأ folio_charges/beach_transactions
    # مباشرة — لو الفوليو بعملة غير EGP بيتحوّل هنا لـ EGP equivalent بسعر
    # الصرف وقت الحركة نفسها قبل الجمع، عشان الفوليوهات المختلطة العملة ما
    # تدّيش رقم غلط.


# ── Exchange Rates (Multi-Currency) ───────────────────────────────────
# ⚠️ الأسعار المزروعة افتراضياً (ensure_default_exchange_rates في services.py)
# قيم dummy للتطوير/العرض فقط — مش أسعار حية. الإنتاج الحقيقي محتاج ربط
# بمصدر رسمي (البنك المركزي المصري مثلاً) بدل الإدخال اليدوي/الافتراضي.

class ExchangeRateCreate(BaseModel):
    from_currency:  str = Field(..., pattern=r"^[A-Z]{3}$")
    to_currency:    str = Field(..., pattern=r"^[A-Z]{3}$")
    rate:           Decimal = Field(..., gt=0)
    effective_date: date


class ExchangeRateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:             int
    from_currency:  str
    to_currency:    str
    rate:           Decimal
    effective_date: date
    created_by:     int
    created_at:     datetime
    updated_at:     datetime


# ── Financial Reports (Trial Balance / Income Statement / Balance Sheet) ─
# ملاحظة عن العملة: دفتر اليومية (JournalEntry/JournalLine) نفسه لا يحمل حقل
# عملة — كل موديول بيرحّل له (pms/restaurant/cafe/beach/hr/...) بيستخدم مبلغه
# الأصلي بافتراض إنه EGP بالفعل (مفيش تحويل عملة داخل أي من هذه المسارات
# اليوم). الفوليو/الدفعة (Folio/Payment) نظام موازٍ منفصل للفوترة، ومش بيترحّل
# تلقائياً لدفتر اليومية. فالتقارير دي EGP-only بالفعل اليوم بحكم البنية —
# `reporting_currency` هنا توثيق صريح لهذه الحقيقة (مش تحويل فعلي لأي قيمة)،
# وتجهيز لو حصل ترحيل multi-currency فعلي لدفتر اليومية مستقبلاً.

class TrialBalanceLine(BaseModel):
    account_code: str
    account_name: str
    account_type: str
    debit:        Decimal
    credit:       Decimal


class TrialBalanceReport(BaseModel):
    branch_id:          int
    as_of:              date
    lines:              list[TrialBalanceLine]
    total_debit:        Decimal
    total_credit:       Decimal
    is_balanced:        bool
    reporting_currency: str = "EGP"


class IncomeStatementLine(BaseModel):
    account_code: str
    account_name: str
    amount:       Decimal


class IncomeStatementReport(BaseModel):
    branch_id:          int
    date_from:          date
    date_to:            date
    revenue_lines:      list[IncomeStatementLine]
    expense_lines:      list[IncomeStatementLine]
    total_revenue:      Decimal
    total_expense:      Decimal
    net_income:         Decimal
    reporting_currency: str = "EGP"


class BalanceSheetLine(BaseModel):
    account_code: str
    account_name: str
    amount:       Decimal


class BalanceSheetReport(BaseModel):
    branch_id:                    int
    as_of:                        date
    asset_lines:                  list[BalanceSheetLine]
    liability_lines:              list[BalanceSheetLine]
    equity_lines:                 list[BalanceSheetLine]
    retained_earnings:            Decimal
    total_assets:                 Decimal
    total_liabilities:            Decimal
    total_equity:                 Decimal
    total_liabilities_and_equity: Decimal
    is_balanced:                  bool
    reporting_currency:           str = "EGP"
