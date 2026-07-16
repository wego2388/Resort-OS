"""app/modules/finance/schemas.py — Pydantic v2"""
from __future__ import annotations

import re
from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


_TIME_RANGE_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$")
_COMBO_ITEMS_RE = re.compile(r"^\d+:[1-9]\d*(,\d+:[1-9]\d*)*$")


class ConditionalDiscountCreate(BaseModel):
    branch_id:       int
    condition_type:  str = Field(
        ..., pattern=r"^(total_amount|item_count|day_of_week|customer_group|time_of_day|combo_items)$",
    )
    condition_value: str = Field(..., max_length=100)
    discount_type:   str = Field(..., pattern=r"^(percentage|fixed_amount|free_item|combo_fixed_price)$")
    discount_value:  Decimal = Field(..., ge=0)
    max_uses:        int = -1
    valid_from:      date
    valid_until:     date
    priority:        int = 1
    is_active:       bool = True
    # نطاق التطبيق — راجع app.modules.finance.models.ConditionalDiscount
    # وapp.resort_os.discount_engine.DiscountRule للتفاصيل الكاملة.
    scope_type:      str = Field("order", pattern=r"^(order|outlet|category|item)$")
    scope_outlet:    Optional[str] = Field(None, pattern=r"^(restaurant|cafe|beach)$")
    scope_id:        Optional[int] = None

    @model_validator(mode="after")
    def _validate_condition_value_format(self) -> "ConditionalDiscountCreate":
        value = self.condition_value.strip()
        if self.condition_type == "time_of_day" and not _TIME_RANGE_RE.match(value):
            raise ValueError(
                "condition_value لـ time_of_day لازم يكون بصيغة 'HH:MM-HH:MM' مثال '14:00-17:00'"
            )
        if self.condition_type == "combo_items" and not _COMBO_ITEMS_RE.match(value):
            raise ValueError(
                "condition_value لـ combo_items لازم يكون بصيغة 'item_id:qty,item_id:qty' مثال '12:1,15:2'"
            )
        return self

    @model_validator(mode="after")
    def _validate_scope(self) -> "ConditionalDiscountCreate":
        if self.scope_type == "order":
            if self.scope_outlet is not None or self.scope_id is not None:
                raise ValueError("scope_type='order' لا يقبل scope_outlet/scope_id")
        elif self.scope_type == "outlet":
            if self.scope_outlet is None:
                raise ValueError("scope_type='outlet' يتطلب scope_outlet")
            if self.scope_id is not None:
                raise ValueError("scope_type='outlet' لا يقبل scope_id")
        else:  # category | item
            if self.scope_outlet is None or self.scope_id is None:
                raise ValueError(f"scope_type='{self.scope_type}' يتطلب scope_outlet و scope_id معًا")
        if self.condition_type == "combo_items" and self.scope_type != "outlet":
            raise ValueError(
                "condition_type='combo_items' لازم يترافق مع scope_type='outlet' — "
                "قائمة أصناف الـ combo نفسها جاية من condition_value، وscope_outlet "
                "هنا بس بيحدد أي جدول أصناف (منع تلبيس بين menu_items.id وcafe_items.id)"
            )
        return self


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
    service_charge:  Decimal
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
    service_charge:  Decimal = Field(Decimal("0"), ge=0)
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


class VoidPaymentRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


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
    """سطر عدّ نقدي بالفئة — بيدعم عملات متعددة.
    denomination: قيمة الورقة/القطعة (200 / 100 / 50 ج أو 1 / 5 / 10 $€)
    currency: عملة هذا السطر (EGP, USD, EUR) — افتراضي EGP
    quantity: عدد الأوراق/القطع
    """
    denomination: Decimal = Field(..., gt=0)
    currency:     str     = Field("EGP", pattern=r"^[A-Z]{3}$")
    quantity:     int     = Field(..., ge=0)


class CashCountLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    denomination:   Decimal
    currency:       str = "EGP"
    quantity:       int
    subtotal:       Decimal   # denomination × quantity (عملة أصلية)
    fx_rate:        Decimal = Decimal("1")
    egp_equivalent: Decimal   # subtotal × fx_rate (جنيه دايمًا)


class ForeignCurrencySummary(BaseModel):
    """ملخص العملة الأجنبية في عدّ الوردية — لكل عملة غير EGP."""
    currency:       str
    total_foreign:  Decimal   # إجمالي بالعملة الأصلية (مثلاً 110 USD)
    fx_rate:        Decimal   # سعر الصرف المستخدم (مثلاً 48.00 EGP/USD)
    egp_equivalent: Decimal   # إجمالي بالجنيه (مثلاً 5280 EGP)


class CashierShiftClose(BaseModel):
    counted_cash:  Optional[Decimal] = Field(None, ge=0)
    cash_count:    Optional[list[CashCountLine]] = None
    notes:         Optional[str] = Field(None, max_length=1000)
    handover_note: Optional[str] = Field(None, max_length=1000)
    # ملاحظة تسليم — بتظهر لصاحب الوردية الجاية في نفس الفرع (راجع
    # GET /finance/shifts/handover-note) قبل ما يفتح ورديته

    # فرق كاش أكبر من الحد المسموح (راجع services.close_shift —
    # CASH_VARIANCE_REJECT_PCT/FLOOR) بيترفض القفل تلقائيًا بـ 400. لو مدير
    # حاضر فعليًا وعايز يعتمد الفرق ده بدل ما يفضل الكاشير معلّق لحد ما مدير
    # يتفرّغ لاحقًا، force_close=true + موافقة PIN (نفس نمط
    # core.services.resolve_pin_approval المستخدم في إلغاء صنف الطلب) بيسمحوا
    # بالقفل — مع AuditLog إجباري يوثّق مين وافق (راجع wagdy.md بند S-06).
    force_close:      bool = False
    approver_user_id: Optional[int] = None
    approver_pin:     Optional[str] = Field(None, pattern=r"^\d{4,6}$")

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
    # #14: reconciliation — يُحسب عند الإغلاق بشكل تلقائي
    # reconciliation_ok: True لو |variance| ≤ 50 ج (مقبول تشغيليًا)
    # reconciliation_warning: رسالة للمدير لو الفرق كبير (None = كل شيء تمام)
    reconciliation_ok:      Optional[bool]    = None
    reconciliation_warning: Optional[str]     = None
    # multi-currency close summary — مش None إلا لما في close مع عملات أجنبية
    foreign_currency_summary: list["ForeignCurrencySummary"] = Field(default_factory=list)
    counted_cash_egp:       Optional[Decimal] = None


class CashMovementCreate(BaseModel):
    """حركة نقدية يدوية على درج وردية مفتوحة — راجع
    finance.models.CashMovement/finance.services.record_cash_movement.
    ``branch_id`` مش موجود هنا عمدًا — بيتحسب من الوردية نفسها server-side
    (مفيش ثقة في أي حاجة قادمة من العميل، راجع CLAUDE.md §5.5)."""
    movement_type: str = Field(
        ..., pattern=r"^(cash_in|cash_out|petty_cash|safe_drop|drawer_open|correction)$",
    )
    amount: Decimal = Field(Decimal("0"), ge=0)
    reason: str = Field(..., min_length=3, max_length=500)
    # موافقة PIN مدير+ — إجبارية لأي منفّذ أقل من مدير، بغض النظر عن نوع
    # الحركة (راجع core.services.resolve_pin_approval، نفس نمط void/discount).
    approver_user_id: Optional[int] = None
    approver_pin:      Optional[str] = Field(None, pattern=r"^\d{4,6}$")
    # بس لـ movement_type="safe_drop" — فين رايح الكاش لما يسيب الدرج
    # (راجع CashMovement.destination). اختياري حتى وقت safe_drop نفسها.
    destination:    Optional[str] = Field(None, pattern=r"^(main_safe|bank|petty_cash_box)$")
    cost_center_id: Optional[int] = None


class CashMovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:            int
    branch_id:     int
    shift_id:      int
    movement_type: str
    amount:        Decimal
    reason:        str
    performed_by:  int
    approved_by:   Optional[int]
    destination:    Optional[str] = None
    cost_center_id: Optional[int] = None
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
    # ملخص العملات الأجنبية — فاضي لو كل العدّ EGP، وإلا فيه عنصر لكل عملة أجنبية
    foreign_currency_summary: list["ForeignCurrencySummary"] = Field(default_factory=list)
    # counted_cash_egp: إجمالي العدّ المحوّل لـ EGP (يشمل كل العملات)
    # يساوي sum(egp_equivalent) لكل سطور cash_count
    counted_cash_egp:      Optional[Decimal] = None
    previous_shift_id:     Optional[int]
    previous_total_sales:  Optional[Decimal]
    delta_vs_previous:     Optional[Decimal]
    reporting_currency:    str = "EGP"
    # كل الإجماليات هنا EGP equivalent — أي دفعة بعملة غير EGP بتتحوّل بسعر
    # الصرف وقت تاريخ الدفعة قبل الجمع (راجع build_shift_end_report).


class ShiftInvoiceLine(BaseModel):
    """سطر واحد في سجل فواتير الوردية (InvoiceLogModal، wagdy.md بند S-02) —
    دفعة حقيقية مربوطة بالوردية عبر Payment.shift_id، مع اسم الضيف من
    الفوليو المرتبط. مختلف عن ``invoice_count`` الإجمالي في ShiftEndReport:
    هنا كل فاتورة سطر مستقل بتفاصيلها، مش رقم مجمّع بس."""
    payment_id: int
    folio_id:   int
    guest_name: str
    amount:     Decimal
    method:     str
    reference:  Optional[str]
    posted_at:  datetime
    is_voided:  bool
    voided_at:  Optional[datetime]


class DiscountCalculateRequest(BaseModel):
    branch_id:      int
    order_total:    Decimal = Field(..., gt=0)
    item_count:     int = Field(1, ge=1)
    customer_group: str = "default"
    order_date:     Optional[date] = None
    order_time:     Optional[time] = None
    # ملحوظة: preview بمستوى الطلب كله بس (بدون سطور) — عمدًا مفيهوش outlet/
    # line_items، فقواعد scope_type="outlet"/"category"/"item" أو
    # condition_type="combo_items" مش هتتحقق أبدًا هنا (نفس سلوك أي rule
    # نطاقها مش منطبق). استخدم POST /dining/orders/{id}/discount الحقيقي
    # لمعاينة/تطبيق خصومات بنطاق محدد على طلب فعلي.


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
    # رصيد الحساب (موجب = طبيعي حسب نوعه: مدين صافي للأصول/المصروفات، دائن
    # صافي للخصوم/حقوق الملكية/الإيرادات) — يُحسب في الراوتر وقت الاستعلام
    # (مش عمود مخزّن)، لأن الفرونت إند (FinanceView.vue tab "الحسابات") كان
    # بيقرا acc.balance من غير ما الـ API يرجّعه أصلاً (باج حقيقي: undefined
    # في كل صف، .toLocaleString() كانت هتطيح الشاشة).
    balance:    Decimal = Decimal("0")


class JournalLineCreate(BaseModel):
    account_id:      int
    debit:           Decimal = Field(Decimal("0"), ge=0)
    credit:          Decimal = Field(Decimal("0"), ge=0)
    description:     Optional[str] = Field(None, max_length=300)
    cost_center_id:  Optional[int] = None


class JournalLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:              int
    entry_id:        int
    account_id:      int
    debit:           Decimal
    credit:          Decimal
    description:     Optional[str]
    cost_center_id:  Optional[int]
    created_at:      datetime


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
    expense: Decimal = Decimal("0")
    net:     Decimal = Decimal("0")
    source:  str = "ledger"
    # "ledger" دايمًا من دلوقتي — قبل كده كان فيه مصدر "direct" (جداول
    # العمليات مباشرة لـ REST/CAFE/BEACH لأنهم ماكانوش بيتحسبوا من
    # journal_lines.cost_center_id خالص). الحقل باقٍ للتوافق مع الفرونت
    # إند الحالي، لكن قيمته الوحيدة دلوقتي "ledger" — راجع
    # services.get_cost_center_report للتفاصيل.


class CostCenterReport(BaseModel):
    branch_id:          int
    date_from:          date
    date_to:            date
    lines:              list[CostCenterReportLine]
    total_revenue:      Decimal
    total_expense:      Decimal = Decimal("0")
    total_net:          Decimal = Decimal("0")
    reporting_currency: str = "EGP"
    # كل الأرقام دلوقتي من journal_lines.cost_center_id المُوسوم فعليًا وقت
    # الترحيل (راجع services.post_simple_revenue_journal's cost_center_code)
    # — مش استنتاج بعدي من جداول العمليات. قيود قديمة اتُرحّلت قبل هذه
    # الدفعة (Batch 3) مالهاش cost_center_id (NULL) عمدًا — مفيش backfill
    # تاريخي هنا (قرار نطاق: الاستنتاج الرجعي محتاج ربط كل قيد قديم بمصدره
    # الأصلي عبر source_id، تعقيد إضافي غير مبرر لبيانات تطوير/ما قبل
    # الإطلاق) — فتقرير على مدى تاريخي قديم هيورّي أرقام أقل من الحقيقة لحد
    # ما قيود جديدة موسومة تتراكم.


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
    grouped_by_parent:  bool = False
    # لو True: كل سطر في lines فوق بيمثّل حساب أب (parent header — مثال
    # "الأصول"/"الإيرادات") برصيده المجمّع من كل الحسابات الفرعية تحته، مش
    # حساب فردي. راجع Account.parent_id + services.get_trial_balance's
    # group_by_parent param + seed.py's 4 حسابات أب (1-2 مستويات بس، حسب
    # توصية البحث الصريحة بعدم بناء تسلسل هرمي عميق للشجرة المزروعة).


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


# ── Fixed-Asset Depreciation ───────────────────────────────────────────

class DepreciationRunRequest(BaseModel):
    branch_id: int
    year:      int = Field(..., ge=2000, le=2100)
    month:     int = Field(..., ge=1, le=12)


class AssetDepreciationEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:                int
    asset_id:          int
    branch_id:         int
    year:              int
    month:             int
    amount:            Decimal
    accumulated_after: Decimal
    journal_entry_id:  Optional[int]
    posted_by:         int
    created_at:        datetime


class DepreciationRunResult(BaseModel):
    branch_id:        int
    year:             int
    month:            int
    entries:          list[AssetDepreciationEntryRead]
    total_amount:     Decimal
    journal_entry_id: Optional[int]
    skipped_assets:   list[str] = Field(default_factory=list)
    # أكواد الأصول اللي اتخطّتها الدورة دي (بالفعل مُهلَكة بالكامل، أو الشهر
    # ده اتترحّل قبل كده، أو تاريخ بداية الإهلاك لسه ماجاش)


# ── Bank Reconciliation ────────────────────────────────────────────────

class BankAccountCreate(BaseModel):
    branch_id:       int
    bank_name:       str = Field(..., max_length=150)
    account_name:    str = Field(..., max_length=200)
    account_number:  str = Field(..., max_length=50)
    currency:        str = Field("EGP", pattern=r"^[A-Z]{3}$")
    gl_account_id:   Optional[int] = None
    opening_balance: Decimal = Field(Decimal("0"))


class BankAccountUpdate(BaseModel):
    bank_name:       Optional[str]     = Field(None, max_length=150)
    account_name:    Optional[str]     = Field(None, max_length=200)
    gl_account_id:   Optional[int]     = None
    opening_balance: Optional[Decimal] = None
    is_active:       Optional[bool]    = None


class BankAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:              int
    branch_id:       int
    bank_name:       str
    account_name:    str
    account_number:  str
    currency:        str
    gl_account_id:   Optional[int]
    opening_balance: Decimal
    is_active:       bool
    created_at:      datetime
    updated_at:      datetime


class BankStatementLineCreate(BaseModel):
    line_date:           date
    description:         str = Field(..., max_length=300)
    amount:              Decimal = Field(..., description="موجب=إيداع، سالب=سحب/عمولة")
    external_reference:  Optional[str] = Field(None, max_length=100)

    @model_validator(mode="after")
    def _amount_not_zero(self) -> "BankStatementLineCreate":
        if self.amount == 0:
            raise ValueError("قيمة سطر كشف الحساب لا يمكن أن تكون صفراً")
        return self


class BankStatementImportRequest(BaseModel):
    lines: list[BankStatementLineCreate] = Field(..., min_length=1, max_length=1000)


class BankStatementLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:                  int
    bank_account_id:     int
    branch_id:           int
    line_date:           date
    description:         str
    amount:              Decimal
    external_reference:  Optional[str]
    status:              str
    matched_payment_id:  Optional[int]
    matched_at:          Optional[datetime]
    matched_by:          Optional[int]
    created_at:          datetime


class BankStatementMatchRequest(BaseModel):
    payment_id: int


class BankReconciliationSummary(BaseModel):
    bank_account_id:    int
    as_of:              date
    opening_balance:    Decimal
    book_balance:       Decimal
    # opening_balance + مجموع الدفعات المطابقة (matched) حتى as_of
    statement_balance:  Decimal
    # opening_balance + مجموع كل سطور كشف الحساب حتى as_of (matched + unmatched غير المتجاهلة)
    difference:         Decimal
    is_reconciled:      bool
    unmatched_statement_lines: int
    unmatched_payments_count:  int
    unmatched_payments_total:  Decimal


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


# ── Revenue Audit Log ───────────────────────────────────────────────────
# RevenueAuditLog كان موجود بالكامل في models.py من غير أي schema/crud/router
# — نفس فئة الباج الموثّقة مرارًا. سجل تدقيق إلزامي بيتسجّل تلقائيًا (مش
# create endpoint للمستخدم) عند أي تغيير فعلي في سعر/قيمة — أول استخدام
# حقيقي: إلغاء دفعة (POST /finance/payments/{id}/void).

class RevenueAuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:          int
    branch_id:   int
    entity_type: str
    entity_id:   int
    old_value:   Decimal
    new_value:   Decimal
    reason:      str
    changed_by:  int
    approved_by: Optional[int]
    created_at:  datetime
