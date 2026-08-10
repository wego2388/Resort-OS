"""app/modules/timeshare/schemas.py — Pydantic v2"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ── إثبات موافقة (OPS-DATA-02 §8 نقطة 1) ────────────────────────────────
# terms_accepted/booking_rules_accepted بوليان مؤقت مش كافي — لازم نعرف
# بالظبط أي نسخة نص العميل وافق عليها. نص جديد = version جديد، ومفيش أي
# نص قديم بيتكتب فوقه (الصف نفسه immutable بعد الإنشاء). النصوص هنا مستخرجة
# من نموذج الحجز الداخلي/اللوائح (راجع TIMESHARE-01_FULL_PLAN_AR.md §2.1/٢.٢) —
# نسخة أولى للـTrial، مش نص قانوني نهائي معتمد.
TIMESHARE_TERMS_VERSION = "timeshare-terms-2026-08-10.v1"
TIMESHARE_BOOKING_RULES_VERSION = "timeshare-booking-rules-2026-08-10.v1"


class TimeshareContractCreate(BaseModel):
    branch_id:              int
    customer_name:          str = Field(..., max_length=200)
    customer_phone:         Optional[str] = None
    customer_email:         Optional[str] = None
    customer_national_id:   Optional[str] = None
    room_type:              str = Field(..., pattern=r"^(Studio|Chalet)$")
    # None = غير معروف بعد (نفس فلسفة RoomType.base_rate في pms — None قيمة
    # صريحة "مش موافَق عليها/مش معروفة"، مش صفر). العميل (شاشة إنشاء عقد
    # يدوي) بيحدده دايمًا فعليًا؛ الاستيراد الجماعي (import_contracts_excel)
    # هو المسار الوحيد اللي بيسمح None فعليًا — بيستنتج Studio=2 بأمان
    # ويسيب Chalet None + يبلّغه في تقرير "unknown_capacity" بدل تخمين 4
    # أو 6 عشوائيًا (راجع OPS-DATA-02 §8 نقطة 2). راجع
    # _validate_capacity_matches_room_type للتحقق لو اتحدد فعلاً.
    unit_capacity:          Optional[int] = Field(None, description="عدد الأفراد: 2 (Studio) أو 4/6 (Chalet)")
    beneficiary_name:       Optional[str] = Field(None, max_length=200)
    customer_phone_work:    Optional[str] = Field(None, max_length=20)
    customer_phone_home:    Optional[str] = Field(None, max_length=20)
    mailing_address:        Optional[str] = Field(None, max_length=300)
    unit_id:                Optional[int] = None  # وحدة مخصَّصة دائمًا — None=عائم
    week_number:            Optional[int] = Field(None, ge=1, le=52)
    nights_per_year:        int = Field(7, ge=1)
    season:                 str = Field("high", pattern=r"^(high|low|both)$")
    total_value:            Decimal = Field(..., gt=0)
    down_payment:           Decimal = Field(..., ge=0)
    installments:           int = Field(12, ge=1)
    installment_period:     int = Field(1, pattern=None)
    first_installment_date: date
    partner_share_pct:      Decimal = Field(Decimal("0"), ge=0, le=100)
    partner_company:        Optional[str] = None
    start_date:             date
    end_date:               Optional[date] = None
    notes:                  Optional[str] = None
    # بيانات العميل الموسّعة
    nationality:            Optional[str] = None
    occupation:             Optional[str] = None
    passport_number:        Optional[str] = None
    address:                Optional[str] = None
    # بيانات العقد الموسّعة
    contract_date:          Optional[date] = None
    purchase_price:         Optional[Decimal] = None
    contract_deposit:       Optional[Decimal] = None
    maintenance_fee:        Decimal = Decimal("0")
    maintenance_increase:   Decimal = Decimal("10")
    batch_number:           Optional[int] = None
    form_number:            Optional[str] = None
    receipt_number:         Optional[str] = None
    rci_included:           bool = False
    contract_value:         Optional[Decimal] = None
    net_contract_value:     Optional[Decimal] = None
    over_under_price:       Decimal = Decimal("0")
    years_count:            int = 99
    payment_type:           str = Field("installment", pattern=r"^(installment|cash)$")

    @model_validator(mode="after")
    def _validate_capacity_matches_room_type(self):
        if self.unit_capacity is None:
            return self
        if self.unit_capacity not in (2, 4, 6):
            raise ValueError("unit_capacity يجب أن يكون 2 أو 4 أو 6")
        if self.room_type == "Studio" and self.unit_capacity != 2:
            raise ValueError("Studio دايمًا سعة 2 أفراد")
        if self.room_type == "Chalet" and self.unit_capacity not in (4, 6):
            raise ValueError("Chalet سعة 4 أو 6 أفراد (6 = باقة Family Compound)")
        return self


class TimeshareContractUpdate(BaseModel):
    customer_phone:    Optional[str]  = None
    customer_email:    Optional[str]  = None
    unit_id:           Optional[int]  = None
    week_number:       Optional[int]  = Field(None, ge=1, le=52)
    status:            Optional[str]  = Field(None, pattern=r"^(draft|active|suspended|cancelled|expired)$")
    booking_frozen:    Optional[bool] = None
    notes:             Optional[str]  = None
    nationality:       Optional[str]  = None
    address:           Optional[str]  = None
    # مراجعة/تصحيح سعة عقد قديم (backfill يدوي بعد مراجعة — OPS-DATA-02 §8
    # نقطة 2) — مش موجود في Create لعقد جديد بيتفرض من هناك، هنا فرصة تصحيح
    # عقود قديمة كانت None. لو room_type=Studio لازم يفضل 2 (يترفض غير كده
    # في services.update_contract).
    unit_capacity:        Optional[int] = Field(None, ge=2, le=6)
    beneficiary_name:     Optional[str] = Field(None, max_length=200)
    customer_phone_work:  Optional[str] = Field(None, max_length=20)
    customer_phone_home:  Optional[str] = Field(None, max_length=20)
    mailing_address:      Optional[str] = Field(None, max_length=300)
    # rسم الصيانة السنوي — كان موجود في الموديل بدون أي طريقة للتعديل عبر الـ
    # API خالص (باج حقيقي: الحقل موجود ومُخزَّن من وقت الاستيراد، لكن محدّش كان
    # يقدر يحدّثه لما تعميم صيانة جديد يصدر). ge=0 عشان مايتحطش سالب بالغلط.
    maintenance_fee:   Optional[Decimal] = Field(None, ge=0)


class InstallmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; contract_id: int; installment_no: int; due_date: date
    amount: Decimal; paid_amount: Decimal; status: str
    paid_at: Optional[datetime]; payment_method: Optional[str]
    receipt_number: Optional[str]; notes: Optional[str]
    created_at: datetime
    # بيانات العميل للعرض في جدول الأقساط (لوحة متابعة المتأخرات) — تُملأ فقط في
    # list_installments حيث الـ join على العقد متاح، وإلا None (مثلاً عند
    # pay_installment اللي بيرجّع القسط لوحده بدون العقد).
    customer_name:  Optional[str] = None
    customer_phone: Optional[str] = None
    room_type:      Optional[str] = None


class TimeshareMaintenanceDueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; contract_id: int; fee_year: int; due_date: date
    amount: Decimal; paid_amount: Decimal; status: str
    paid_at: Optional[datetime]; payment_method: Optional[str]
    receipt_number: Optional[str]; notes: Optional[str]
    created_at: datetime
    # نفس نمط InstallmentRead — بتتملى بس في list_maintenance_dues حيث الـ
    # join على العقد متاح
    customer_name:  Optional[str] = None
    customer_phone: Optional[str] = None
    room_type:      Optional[str] = None


class TimeshareContractRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; contract_number: str
    customer_name: str; customer_phone: Optional[str]; customer_email: Optional[str]
    customer_national_id: Optional[str]
    room_type: str; unit_capacity: Optional[int] = None
    beneficiary_name: Optional[str] = None
    customer_phone_work: Optional[str] = None; customer_phone_home: Optional[str] = None
    mailing_address: Optional[str] = None
    unit_id: Optional[int]; week_number: Optional[int]; nights_per_year: int; season: str
    total_value: Decimal; down_payment: Decimal; installments: int
    installment_period: int; first_installment_date: date
    partner_share_pct: Decimal; partner_company: Optional[str]
    status: str; booking_frozen: bool
    start_date: date; end_date: Optional[date]; notes: Optional[str]
    nationality: Optional[str]; occupation: Optional[str]
    passport_number: Optional[str]; address: Optional[str]
    contract_date: Optional[date]; purchase_price: Optional[Decimal]
    contract_deposit: Optional[Decimal]; maintenance_fee: Decimal
    maintenance_increase: Decimal; batch_number: Optional[int]
    form_number: Optional[str]; receipt_number: Optional[str]
    rci_included: bool; contract_value: Optional[Decimal]
    net_contract_value: Optional[Decimal]; over_under_price: Decimal
    years_count: int; payment_type: str
    cancelled_at: Optional[date]; cancel_amount: Decimal
    installments_list: list[InstallmentRead] = []
    maintenance_dues_list: list[TimeshareMaintenanceDueRead] = []
    created_at: datetime; updated_at: datetime


class TimeshareCancelRequest(BaseModel):
    cancel_amount: Decimal = Field(Decimal("0"), ge=0)


class TimeshareUnitTransferRequest(BaseModel):
    """wagdy.md #10: نقل عقد من وحدة ثابتة لوحدة تانية (نفس room_type —
    تغيير نوع الوحدة/"ترقية" بقيمة مختلفة قرار تسعير منفصل، مش في نطاق
    العملية دي، راجع services.transfer_unit). التعديل المباشر عبر
    TimeshareContractUpdate.unit_id كان موجود من غير أي تحقق خالص — مش مجرد
    UI ناقص، عملية غير آمنة فعليًا لو استُخدمت مباشرة."""
    new_unit_id: int
    reason: str = Field(..., min_length=3, max_length=300)


class PayInstallmentRequest(BaseModel):
    paid_amount:    Decimal = Field(..., gt=0)
    payment_method: str = Field(..., pattern=r"^(cash|card|bank_transfer|other)$")
    receipt_number: Optional[str] = None
    notes:          Optional[str] = None


class PayMaintenanceDueRequest(BaseModel):
    paid_amount:    Decimal = Field(..., gt=0)
    payment_method: str = Field(..., pattern=r"^(cash|card|bank_transfer|other)$")
    receipt_number: Optional[str] = None
    notes:          Optional[str] = None


class WaitlistCreate(BaseModel):
    branch_id:       int
    contract_id:     int
    requested_start: date
    requested_end:   date


class WaitlistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; contract_id: int
    requested_start: date; requested_end: date; position: int
    status: str; notified_at: Optional[datetime]; expires_at: Optional[datetime]
    created_at: datetime


class WaitlistStatusUpdate(BaseModel):
    """تحكم يدوي من الموظف — confirmed (اتحجزله فعليًا) أو cancelled (العميل
    ملوش نية)، مش waiting/notified (انتقالات نظامية بس عبر مهمة مجدولة)."""
    status: str = Field(..., pattern=r"^(confirmed|cancelled)$")


class TimeshareVisitCreate(BaseModel):
    branch_id:   int
    contract_id: int
    check_in:    date
    check_out:   date
    booking_id:  Optional[int] = None
    notes:       Optional[str] = None


class TimeshareVisitUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern=r"^(scheduled|active|completed|cancelled)$")
    notes:  Optional[str] = None


class TimeshareVisitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; contract_id: int; booking_id: Optional[int]
    unit_id: Optional[int]
    check_in: date; check_out: date; nights: int; status: str
    notes: Optional[str]
    created_at: datetime


class TimeshareUnitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; unit_number: str; unit_type: str
    status: str; notes: Optional[str]
    created_at: datetime


class TimeshareUnitCreate(BaseModel):
    branch_id: int
    unit_number: str = Field(..., max_length=20)
    unit_type: str = Field(..., pattern=r"^(Studio|Chalet)$")
    notes: Optional[str] = Field(None, max_length=300)


class TimeshareUnitUpdate(BaseModel):
    unit_number: Optional[str] = Field(None, max_length=20)
    unit_type: Optional[str] = Field(None, pattern=r"^(Studio|Chalet)$")
    status: Optional[str] = Field(None, pattern=r"^(available|occupied|maintenance)$")
    notes: Optional[str] = Field(None, max_length=300)


# ── Simple fixed-shape response schemas ──────────────────────────────────────
class ImportContractsResponse(BaseModel):
    imported: int
    skipped:  int
    errors:   list[str] = []
    # صفوف Chalet استُوردت بنجاح لكن سعتها (4 أو 6) غير معروفة من الملف —
    # عمدًا مش مخمّنة (راجع OPS-DATA-02 §8 نقطة 2). لازم مراجعة يدوية
    # (PATCH /timeshare/contracts/{id} بـunit_capacity الصح).
    unknown_capacity_rows: list[int] = []


# ── Owner Portal (بوابة صاحب العقد العامة، طلب Mohamed 2026-08-03) ───────────

class TimeshareOwnerVerifyRequest(BaseModel):
    """الخطوة ١: العميل بيكتب رقم عقده + رقم موبايله المسجّل — لو الاتنين
    متطابقين، كود تحقق (OTP) بيتبعت واتساب. الرد دايمًا نفس الرسالة العامة
    بغض النظر عن التطابق (راجع services.request_owner_otp) عشان محدّش
    يقدر يكتشف أرقام عقود حقيقية بالتجربة."""
    contract_number: str = Field(..., max_length=30)
    phone:            str = Field(..., max_length=20)


class TimeshareOwnerVerifyConfirm(BaseModel):
    """الخطوة ٢: كود الـOTP اللي وصل واتساب."""
    contract_number: str = Field(..., max_length=30)
    otp_code:         str = Field(..., min_length=4, max_length=8)


class TimeshareOwnerPortalToken(BaseModel):
    token:            str
    expires_in_minutes: int


class TimeshareOwnerContractRead(BaseModel):
    """نسخة مبسّطة ومحدودة من TimeshareContractRead لعرض العميل نفسه —
    عمدًا بدون بيانات إدارية داخلية (رقم الدفعة/الفورمة/الإيصال، نسبة
    الشريك، إلخ) وبدون هوية/جواز (مش لازمة لغرض المتابعة والحجز، وطلب
    Mohamed كان صريح: "ما يكونش معقد")."""
    model_config = ConfigDict(from_attributes=True)
    id: int; contract_number: str; customer_name: str
    room_type: str; week_number: Optional[int]; nights_per_year: int; season: str
    status: str; booking_frozen: bool
    start_date: date; end_date: Optional[date]
    unit_number: Optional[str] = None  # يتملى من contract.unit.unit_number لو وحدة ثابتة


class TimeshareVisitRequestCreate(BaseModel):
    """طلب العميل نفسه — تواريخ مفضّلة + حتى تاريخين بديلين (نموذج الحجز
    الداخلي: "يرجى كتابة ثلاث فترات بديلة" — preferred_* هي الأولى، البديل
    التالت من غير حاجة صريحة زيادة). المدير هو اللي يحدد الفعلي عند
    الموافقة (راجع TimeshareVisitRequestApprove).

    terms_accepted/booking_rules_accepted لازم يكونوا True حرفيًا، والنسخة
    المرسلة لازم تطابق النسخة الحالية بالظبط (Literal) — عميل بنسخة قديمة
    من الواجهة (نص اتغيّر من تحته) يترفض بـ422 صريح بدل قبول موافقة على
    نص قديم من غير علم."""
    preferred_start: date
    preferred_end:   date
    alt_start_1: Optional[date] = None
    alt_end_1:   Optional[date] = None
    alt_start_2: Optional[date] = None
    alt_end_2:   Optional[date] = None
    notes:           Optional[str] = Field(None, max_length=500)
    terms_accepted:          Literal[True]
    terms_version:           Literal[TIMESHARE_TERMS_VERSION]
    booking_rules_accepted:  Literal[True]
    booking_rules_version:   Literal[TIMESHARE_BOOKING_RULES_VERSION]

    @model_validator(mode="after")
    def _validate_alt_dates(self):
        for start, end, label in (
            (self.alt_start_1, self.alt_end_1, "الأول"),
            (self.alt_start_2, self.alt_end_2, "الثاني"),
        ):
            if (start is None) != (end is None):
                raise ValueError(f"التاريخ البديل {label}: لازم تحدد البداية والنهاية معًا")
            if start is not None and end <= start:
                raise ValueError(f"التاريخ البديل {label}: النهاية يجب أن تكون بعد البداية")
        return self


class TimeshareVisitRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; contract_id: int
    preferred_start: date; preferred_end: date; notes: Optional[str]
    alt_start_1: Optional[date] = None
    alt_end_1:   Optional[date] = None
    alt_start_2: Optional[date] = None
    alt_end_2:   Optional[date] = None
    status: str; reviewed_at: Optional[datetime]; rejection_reason: Optional[str]
    visit_id: Optional[int]
    terms_version:          Optional[str] = None
    terms_accepted_at:       Optional[datetime] = None
    booking_rules_version:   Optional[str] = None
    booking_rules_accepted_at: Optional[datetime] = None
    is_peak:            bool = False
    peak_season_names:  list[str] = []
    created_at: datetime
    # بتتملى في القايمة الإدارية بس (join على العقد متاح هناك) — نفس نمط
    # InstallmentRead.customer_name
    customer_name:  Optional[str] = None
    customer_phone: Optional[str] = None
    contract_number: Optional[str] = None


class TimeshareVisitRequestApprove(BaseModel):
    """موافقة مدير — هو اللي بيحدد التواريخ الفعلية (طلب Mohamed الصريح:
    "المسؤول هو اللي يحدد الأسبوع")، مش بالضرورة نفس تواريخ العميل
    المفضّلة. بتمرّ بنفس services.create_visit الموجودة (منع تعارض/تجميد)."""
    check_in:  date
    check_out: date


class TimeshareVisitRequestReject(BaseModel):
    reason: str = Field(..., min_length=3, max_length=300)


class TimeshareSupportTicketCreate(BaseModel):
    subject: str = Field(..., min_length=3, max_length=200)
    message: str = Field(..., min_length=3, max_length=2000)


class TimeshareTicketReplyCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class TimeshareTicketReplyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; author_type: str; message: str; created_at: datetime


class TimeshareSupportTicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; contract_id: int
    subject: str; status: str; resolved_at: Optional[datetime]
    created_at: datetime
    replies: list[TimeshareTicketReplyRead] = []
    # بتتملى في القايمة الإدارية بس
    customer_name:  Optional[str] = None
    contract_number: Optional[str] = None


class TimeshareTicketStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(open|in_progress|resolved|closed)$")


# ── Timeshare Staff (مدير التايم شير بيدير موظفي وحدته، طلب Mohamed 2026-08-03) ──

class TimeshareStaffCreate(BaseModel):
    """role مش حقل هنا عمدًا — ثابت timeshare_agent دايمًا، مش قابل
    للاختيار (راجع services.provision_timeshare_agent)."""
    branch_id: int
    email: str = Field(..., min_length=3, max_length=320)
    full_name: str = Field(..., min_length=3, max_length=255)
    phone: Optional[str] = None
    preferred_language: str = Field("ar", pattern=r"^(ar|en)$")


class TimeshareStaffProvisioned(BaseModel):
    id: int
    email: str
    full_name: str
    temporary_password: str
    must_change_password: bool


class TimeshareStaffRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; email: str; full_name: str; phone: Optional[str]
    is_active: bool; must_change_password: bool
    created_at: datetime


class TimeshareStaffStatusUpdate(BaseModel):
    is_active: bool
