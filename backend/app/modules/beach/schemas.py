"""app/modules/beach/schemas.py — Pydantic v2"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BeachInventoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:               int
    branch_id:        int
    inventory_date:   date
    capacity_max:     int
    capacity_used:    int
    towels_total:     int
    towels_available: int
    towels_used:      int
    surge_pct:        Decimal
    available_slots:  int = 0
    capacity_pct:     int = 0
    # الأسعار مش عمود في جدول beach_inventory — بتتحسب من settings الفرع
    # (نفس الدالة اللي البيع الفعلي بيستخدمها، app.modules.beach.services
    # .get_base_prices) ومُدمجة هنا وقت الـ router.get_inventory() عشان
    # شاشة الـ POS تقدر تعرض السعر قبل ما الكاشير يعمل البيع فعليًا.
    adult_price:      Decimal = Decimal("0")
    child_price:      Decimal = Decimal("0")
    resident_price:   Decimal = Decimal("0")
    towel_price:      Decimal = Decimal("0")
    # 2026-08-23: رسم "خدمة" ثابت لدخول مأكولات خارجية — نفس نمط towel_price
    # بالظبط (سعر إضافي مستقل، من غير تأثير على السعة).
    outside_food_fee_price: Decimal = Decimal("0")
    surge_active:     bool = False
    # app.resort_os.beach_engine.calculate_tx_price يفسّر surge_pct=50.0 كـ
    # "+50%" (يعني الضرب في 1.5) — المضاعف ده نفسه، جاهز يتضرب في الأسعار
    # مباشرة في الفرونت إند بدل ما يعيد نفس الحسبة تاني.
    surge_multiplier: float = 1.0

    def model_post_init(self, __context: object) -> None:
        object.__setattr__(self, "available_slots",
                           max(0, self.capacity_max - self.capacity_used))
        cap_pct = (
            min(100, int(self.capacity_used / self.capacity_max * 100))
            if self.capacity_max > 0 else 100
        )
        object.__setattr__(self, "surge_multiplier", 1.0 + float(self.surge_pct) / 100.0)
        object.__setattr__(self, "capacity_pct", cap_pct)
        object.__setattr__(self, "surge_active", self.surge_pct > 0)


class BeachSellRequest(BaseModel):
    """طلب بيع تذكرة دخول أو فوطة."""
    tx_type:         str = Field(..., pattern=r"^(entry|entry_child|entry_resident|entry_towel|towel_rent|towel_return|outside_food_fee)$")
    # حد أعلى تشغيلي — يمنع إدخال غلط بالغلط (زفير رقم زيادة) من غير ما
    # يقيّد حجوزات مجموعات حقيقية معقولة لمنتجع واحد.
    quantity:        int = Field(1, ge=1, le=100)
    cashier_id:      Optional[int] = None
    folio_id:        Optional[int] = None
    room_id:         Optional[int] = None
    # لو موجود ومفيش folio_id مباشر: يدوّر على فوليو الضيف المقيم في الغرفة دي
    # (Charge to Room) — راجع pms.services.find_active_folio_for_room
    b2b_contract_id: Optional[int] = None
    customer_id:     Optional[int] = None
    credit_account_id: Optional[int] = Field(None, gt=0)
    notes:           Optional[str] = None
    # الموقع الفعلي (خريطة الشاطئ الحية) اللي العملية دي متسجّلة عشانه —
    # None لبيع تذاكر عادي من POS من غير خريطة. services.checkin_location
    # بيضبط الحقل ده داخليًا وقت بناء الطلب.
    location_id:     Optional[int] = None
    # مفتاح idempotency لـ retry بعد بيع أوفلاين (useOfflineQueue('beach')) —
    # راجع BeachTransaction.client_local_id. اختياري: بيع مباشر أونلاين
    # عادي (POS متصل) مش محتاجه، زي نفس نمط restaurant/cafe بالظبط.
    local_id:        Optional[str] = Field(None, max_length=60)
    # POS-03: عملة الكاش المستلمة فعليًا — اختياري، افتراضي EGP (بدون breaking change).
    # total_amount في BeachTransaction دايمًا EGP-equivalent؛ currency/fx_rate
    # للتسجيل المحاسبي والتدقيق في تقرير نهاية الوردية.
    # لو currency ≠ EGP وmethod="cash"، fx_rate إجباري (validator تحت).
    # ملحوظة: الفكة دايمًا بالجنيه (قرار Mohamed 2026-08-05).
    payment_currency: Optional[str]    = Field(None, pattern=r"^[A-Z]{3}$")
    payment_fx_rate:  Optional[Decimal] = Field(None, gt=0)
    # Decision 0005: الدفع على حساب آجل شخصي — يتطلب customer_id
    # لو مش None: يتجاهل folio_id/room_id ويرحّل على CreditAccount العميل
    payment_method:   Optional[str]    = Field(
        None,
        pattern=r"^(cash|card|wallet|room|credit_account)$",
        description="طريقة الدفع — افتراضي: cash أو room (لو folio_id/room_id موجود)",
    )
    # قناة التحصيل المختارة (صندوق/Visa CIB/Vodafone Cash...) — اختياري:
    # None يعني "استخدم الـdefault المُعرَّف لهذه الطريقة"، وفرع لسه معملوش
    # أي قنوات بيفضل يشتغل بمسار الحساب القديم (legacy) بدون أي تغيير.
    payment_channel_id: Optional[int] = Field(None, gt=0)
    approver_user_id: Optional[int] = Field(None, gt=0)
    approver_pin: Optional[str] = Field(None, min_length=4, max_length=12)

    @model_validator(mode="after")
    def _validate_fx(self) -> "BeachSellRequest":
        cur = (self.payment_currency or "EGP").upper()
        if cur != "EGP" and not self.payment_fx_rate:
            raise ValueError(
                "payment_fx_rate مطلوب لو payment_currency ≠ EGP — "
                "مرّر سعر الصرف الحالي عبر GET /finance/exchange-rates"
            )
        if self.payment_method == "credit_account" and not (
            self.customer_id or self.credit_account_id
        ):
            raise ValueError(
                "customer_id أو credit_account_id مطلوب للدفع على حساب آجل"
            )
        if self.credit_account_id and self.payment_method != "credit_account":
            raise ValueError("credit_account_id يُستخدم فقط مع payment_method = credit_account")
        has_room_target = self.folio_id is not None or self.room_id is not None
        if self.payment_method == "room" and not has_room_target:
            raise ValueError("payment_method = room يتطلب folio_id أو room_id")
        if has_room_target and self.payment_method not in (None, "room", "credit_account"):
            raise ValueError("طريقة الدفع لا تطابق تحميل البيع على الغرفة")
        if (self.approver_user_id is None) != (self.approver_pin is None):
            raise ValueError("بيانات موافقة المدير يجب أن تُرسل كاملة")
        return self


class BeachCartLineItem(BaseModel):
    """صنف واحد داخل سلة بيع متعددة الأصناف (زي "2 بالغ + فوطة")."""
    tx_type:  str = Field(..., pattern=r"^(entry|entry_child|entry_resident|entry_towel|towel_rent|towel_return|outside_food_fee)$")
    quantity: int = Field(1, ge=1, le=100)


class BeachCartSellRequest(BaseModel):
    """سلة بيع شاطئ متعددة الأصناف — تُنفَّذ كـtransaction واحدة atomic:
    إما كل الأصناف تنجح مع بعض أو ولا واحد فيهم يترحّل (راجع
    services.sell_cart). كل الحقول المشتركة (طريقة الدفع، العميل، الفوليو...)
    نفسها على مستوى السلة كلها؛ كل صنف بس عنده tx_type/quantity الخاصين بيه."""
    items: list[BeachCartLineItem] = Field(..., min_length=1, max_length=20)
    cashier_id:      Optional[int] = None
    folio_id:        Optional[int] = None
    room_id:         Optional[int] = None
    b2b_contract_id: Optional[int] = None
    customer_id:     Optional[int] = None
    credit_account_id: Optional[int] = Field(None, gt=0)
    notes:           Optional[str] = None
    location_id:     Optional[int] = None
    # مفتاح idempotency على مستوى السلة كلها (مش صنف واحد) — راجع
    # services.sell_cart لكيفية اشتقاق local_id لكل صنف منه.
    cart_local_id:   Optional[str] = Field(None, max_length=60)
    payment_currency: Optional[str]    = Field(None, pattern=r"^[A-Z]{3}$")
    payment_fx_rate:  Optional[Decimal] = Field(None, gt=0)
    payment_method:   Optional[str]    = Field(
        None, pattern=r"^(cash|card|wallet|room|credit_account)$",
    )
    payment_channel_id: Optional[int] = Field(None, gt=0)
    approver_user_id: Optional[int] = Field(None, gt=0)
    approver_pin: Optional[str] = Field(None, min_length=4, max_length=12)

    @model_validator(mode="after")
    def _validate_fx(self) -> "BeachCartSellRequest":
        cur = (self.payment_currency or "EGP").upper()
        if cur != "EGP" and not self.payment_fx_rate:
            raise ValueError(
                "payment_fx_rate مطلوب لو payment_currency ≠ EGP — "
                "مرّر سعر الصرف الحالي عبر GET /finance/exchange-rates"
            )
        if self.payment_method == "credit_account" and not (
            self.customer_id or self.credit_account_id
        ):
            raise ValueError(
                "customer_id أو credit_account_id مطلوب للدفع على حساب آجل"
            )
        if self.credit_account_id and self.payment_method != "credit_account":
            raise ValueError("credit_account_id يُستخدم فقط مع payment_method = credit_account")
        has_room_target = self.folio_id is not None or self.room_id is not None
        if self.payment_method == "room" and not has_room_target:
            raise ValueError("payment_method = room يتطلب folio_id أو room_id")
        if has_room_target and self.payment_method not in (None, "room", "credit_account"):
            raise ValueError("طريقة الدفع لا تطابق تحميل البيع على الغرفة")
        if (self.approver_user_id is None) != (self.approver_pin is None):
            raise ValueError("بيانات موافقة المدير يجب أن تُرسل كاملة")
        return self


class BeachTransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:              int
    branch_id:       int
    tx_type:         str
    quantity:        int
    unit_price:      Decimal
    total_amount:    Decimal
    vat_amount:      Decimal
    surge_applied:   bool
    tx_date:         date
    cashier_id:      Optional[int]
    payment_method:  Optional[str] = None
    folio_id:        Optional[int]
    b2b_contract_id: Optional[int]
    customer_id:     Optional[int] = None
    notes:           Optional[str]
    voided_at:       Optional[datetime]
    voided_reason:   Optional[str] = None
    shift_id:        Optional[int] = None
    location_id:     Optional[int] = None
    payment_channel_id:   Optional[int] = None
    payment_channel_code: Optional[str] = None
    payment_channel_name: Optional[str] = None
    settlement_account_code: Optional[str] = None
    created_at:      datetime


class VoidTransactionRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=200)


class B2BContractCreate(BaseModel):
    """2026-08-20، طلب Mohamed صراحةً — استبدال كامل لنموذج "سعر لكل ضيف ×
    حصة يومية" بـ"مبلغ شهري ثابت + حد أقصى استرشادي شهري". راجع
    beach.models.B2BContract للتفاصيل الكاملة."""
    branch_id:     int
    hotel_name:    str = Field(..., max_length=200)
    hotel_name_ar: Optional[str] = None
    contact_phone: Optional[str] = Field(None, max_length=20)
    monthly_fee:       Decimal = Field(..., gt=0)
    monthly_guest_cap: int     = Field(100, ge=1)
    valid_from:    date
    valid_until:   date
    is_active:     bool = True
    notes:         Optional[str] = None
    # ائتمان — nullable: مش كل فندق شريك محتاج حد (راجع تعليق B2BContract في models.py)
    credit_limit:       Optional[Decimal] = Field(None, ge=0)
    payment_terms_days: int               = Field(30, ge=1, le=365)


class B2BContractRead(B2BContractCreate):
    model_config = ConfigDict(from_attributes=True)
    id:              int
    last_settled_at: Optional[date] = None
    is_overdue:      bool = False
    created_at:      datetime
    updated_at:      datetime


class B2BContractUpdate(BaseModel):
    """تعديل جزئي — حاليًا لشاشة إدارة الائتمان (حد الائتمان/مهلة السداد)
    فقط، مش لكل حقول العقد (تجنّبًا لتغيير بيانات تشغيلية حساسة زي المبلغ
    الشهري/الحد الأقصى من غير مسار مخصص لها)."""
    credit_limit:       Optional[Decimal] = Field(None, ge=0)
    payment_terms_days: Optional[int]     = Field(None, ge=1, le=365)


class B2BSettleRequest(BaseModel):
    """تسجيل تسوية (تحصيل) رصيد الفندق الشريك حتى تاريخ معيّن.
    ``settlement_account_code`` الحساب اللي التحصيل دخل عليه فعليًا
    (افتراضيًا 1110 بنك — التحصيل عادة تحويل بنكي، مش كاش في درج كاشير
    الشاطئ)."""
    settled_through: Optional[date] = None
    settlement_account_code: str = Field("1110", max_length=10)


class B2BCheckinRequest(BaseModel):
    contract_id:  int
    guests_count: int = Field(1, ge=1)
    with_towel:   bool = False
    cashier_id:   Optional[int] = None


class BeachReservationCreate(BaseModel):
    branch_id:        int
    guest_name:       str = Field(..., max_length=200)
    guest_phone:      Optional[str] = Field(None, max_length=20)
    reservation_date: date
    guests_count:     int = Field(1, ge=1)
    with_towel:       bool = False
    notes:            Optional[str] = None


class BeachReservationRead(BeachReservationCreate):
    model_config = ConfigDict(from_attributes=True)
    id:           int
    status:       str
    total_amount: Decimal
    tx_id:        Optional[int]
    created_at:   datetime


class BeachReservationPublic(BaseModel):
    """معلومات عامة عن الحجز — تُعرض في صفحة QR قبل تأكيد الدخول، بدون تسجيل
    دخول. Gate 1 containment (2026-07-17): كانت بترجع guest_name/
    guests_count/with_towel/reservation_date/total_amount لأي رقم متسلسل
    يتم تخمينه، بدون أي مصادقة — تسريب PII ومبلغ مالي حقيقي. الحقول دي
    مش لازمة فعليًا للشاشة العامة (البيانات الكاملة بترجع من endpoint
    الـcheckin المصادَق عليه بعد تسجيل دخول الكاشير). لا نبني توكن/جلسة ضيف
    كاملة هنا — ده Gate 8، مش احتواء."""
    model_config = ConfigDict(from_attributes=True)
    id:     int
    status: str


class BeachSurgeSet(BaseModel):
    """طلب ضبط surge يدوياً من المدير."""
    surge_pct: Decimal = Field(..., ge=0, le=200)
    inv_date:  Optional[date] = None


class BeachDailySummary(BaseModel):
    """ملخص يومي للشاطئ."""
    date:             date
    total_entries:    int
    total_revenue:    Decimal
    b2b_entries:      int
    b2b_revenue:      Decimal
    capacity_pct:     int
    surge_active:     bool
    towels_rented:    int


# ── Beach Locations (live map) ──────────────────────────────────────────

class BeachLocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:                     int
    branch_id:              int
    location_type:          str
    number:                 str
    grid_row:               int
    grid_col:               int
    status:                 str
    current_transaction_id: Optional[int] = None
    guest_name:             Optional[str] = None
    guest_phone:            Optional[str] = None
    guests_count:           int
    towels_given:           int
    checked_in_at:          Optional[datetime] = None
    checked_in_by:          Optional[int] = None
    created_at:             datetime
    updated_at:             datetime


class BeachLocationBulkCreate(BaseModel):
    """إضافة مواقع جديدة بالجملة لنوع معيّن — منسّقة تلقائيًا في grid
    (10 أعمدة لكل صف)، مرقّمة تسلسليًا بعد أعلى رقم موجود لنفس النوع."""
    branch_id:     int
    location_type: str = Field(..., min_length=2, max_length=20, pattern=r"^[a-z_]+$")
    count:         int = Field(..., ge=1, le=200)


class BeachLocationBulkRemove(BaseModel):
    """حذف آخر N مواقع *متاحة* من نوع معيّن — بيرفض لو أي موقع مطلوب حذفه
    مشغول حاليًا (حماية من حذف موقع فيه ضيف قاعد عليه فعليًا)."""
    branch_id:     int
    location_type: str = Field(..., min_length=2, max_length=20)
    count:         int = Field(..., ge=1, le=200)


class BeachLocationUpdate(BaseModel):
    """تعديل مدير: تعطيل/تفعيل موقع (صيانة) أو تغيير مكانه في الـ grid.
    مفيش تعديل لـ location_type/number هنا — لو المدير غلط في النوع/الرقم،
    الأسهل حذف وإعادة إضافة (نفس فلسفة B2BContractUpdate: مسار محدود
    ومقصود، مش تعديل حر لكل حقل)."""
    status:   Optional[str] = Field(None, pattern=r"^(available|out_of_service)$")
    grid_row: Optional[int] = Field(None, ge=1)
    grid_col: Optional[int] = Field(None, ge=1)


class BeachLocationCheckinRequest(BaseModel):
    """تسجيل دخول ضيف لموقع فعلي — بيعمل عملية بيع حقيقية عبر
    services.sell_ticket (entry أو entry_towel)، مش مجرد تعليم "مشغول"."""
    guest_name:   Optional[str] = Field(None, max_length=200)
    guest_phone:  Optional[str] = Field(None, max_length=20)
    guests_count: int  = Field(1, ge=1)
    with_towel:   bool = False
    cashier_id:   Optional[int] = None
