"""app/modules/dining/schemas.py — Pydantic v2

يدمج restaurant/schemas.py + cafe/schemas.py — نفس الشكل بالظبط، إضافة
outlet_id/outlet_type فين ما يلزم بدل الفصل بين موديولين. راجع
DiningItem/DiningOrder وباقي دوكسترنجز models.py للتبرير التجاري الكامل.
"""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ─────────────────────── Outlet ────────────────────────────────────────

class OutletCreate(BaseModel):
    branch_id:            int
    name:                 str = Field(..., max_length=100)
    name_ar:              Optional[str] = Field(None, max_length=100)
    outlet_type:          str = Field("restaurant", max_length=30)
    revenue_account_code: str = Field("4200", max_length=10)
    default_service_charge_pct: Optional[Decimal] = Field(None, ge=0, le=100)
    # تسعير حسب قناة الطلب — NULL افتراضيًا = صفر تغيير (راجع
    # services._service_charge_pct). كلهم اختياريين، مفيش أي حد إجباري.
    takeaway_service_charge_pct:     Optional[Decimal] = Field(None, ge=0, le=100)
    delivery_service_charge_pct:     Optional[Decimal] = Field(None, ge=0, le=100)
    room_service_service_charge_pct: Optional[Decimal] = Field(None, ge=0, le=100)
    delivery_fee: Optional[Decimal] = Field(None, ge=0)
    is_active:            bool = True


class OutletUpdate(BaseModel):
    name:                 Optional[str] = Field(None, max_length=100)
    name_ar:              Optional[str] = Field(None, max_length=100)
    outlet_type:          Optional[str] = Field(None, max_length=30)
    revenue_account_code: Optional[str] = Field(None, max_length=10)
    default_service_charge_pct: Optional[Decimal] = Field(None, ge=0, le=100)
    takeaway_service_charge_pct:     Optional[Decimal] = Field(None, ge=0, le=100)
    delivery_service_charge_pct:     Optional[Decimal] = Field(None, ge=0, le=100)
    room_service_service_charge_pct: Optional[Decimal] = Field(None, ge=0, le=100)
    delivery_fee: Optional[Decimal] = Field(None, ge=0)
    is_active:            Optional[bool] = None


class OutletRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:                    int
    branch_id:             int
    name:                  str
    name_ar:               Optional[str]
    outlet_type:           str
    revenue_account_code:  str
    default_service_charge_pct: Optional[Decimal]
    takeaway_service_charge_pct:     Optional[Decimal] = None
    delivery_service_charge_pct:     Optional[Decimal] = None
    room_service_service_charge_pct: Optional[Decimal] = None
    delivery_fee: Optional[Decimal] = None
    is_active:              bool
    legacy_module:           Optional[str] = None
    created_at:              datetime


# ─────────────────────── Menu ──────────────────────────────────────────

class DiningCategoryCreate(BaseModel):
    branch_id:  int
    outlet_id:  int
    name:       str = Field(..., max_length=100)
    name_ar:    Optional[str] = Field(None, max_length=100)
    sort_order: int = 0
    is_active:  bool = True


class DiningCategoryUpdate(BaseModel):
    name:       Optional[str] = Field(None, max_length=100)
    name_ar:    Optional[str] = Field(None, max_length=100)
    sort_order: Optional[int] = None
    is_active:  Optional[bool] = None


class DiningCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:         int
    branch_id:  int
    outlet_id:  int
    name:       str
    name_ar:    Optional[str]
    sort_order: int
    is_active:  bool
    created_at: datetime


class DiningItemCreate(BaseModel):
    branch_id:           int
    outlet_id:           int
    category_id:         Optional[int] = None
    name:                str  = Field(..., max_length=200)
    name_ar:             Optional[str] = Field(None, max_length=200)
    description:         Optional[str] = Field(None, max_length=500)
    price:               Decimal = Field(..., gt=0)
    cost:                Optional[Decimal] = Field(None, ge=0)
    is_available:        bool = True
    preparation_minutes: int  = 10
    image_url:           Optional[str] = Field(None, max_length=500)
    station:             str = Field("hot", pattern=r"^(hot|grill|cold|bar|dessert)$")
    linked_product_id:   Optional[int] = None
    available_from_time:  Optional[time] = None
    available_until_time: Optional[time] = None


class DiningItemUpdate(BaseModel):
    name:                Optional[str]     = None
    name_ar:             Optional[str]     = None
    description:         Optional[str]     = Field(None, max_length=500)
    price:               Optional[Decimal] = Field(None, gt=0)
    cost:                Optional[Decimal] = None
    is_available:        Optional[bool]    = None
    preparation_minutes: Optional[int]     = None
    category_id:         Optional[int]     = None
    station:             Optional[str]     = Field(None, pattern=r"^(hot|grill|cold|bar|dessert)$")
    image_url:           Optional[str]     = None
    linked_product_id:   Optional[int]     = None
    available_from_time:  Optional[time]   = None
    available_until_time: Optional[time]   = None


# ─────────────────────── Extras / Modifiers ───────────────────────────

class DiningItemExtraCreate(BaseModel):
    name:           str = Field(..., max_length=100)
    name_ar:        Optional[str] = Field(None, max_length=100)
    price_addition: Decimal = Field(Decimal("0"), ge=0)
    is_available:   bool = True
    sort_order:     int = 0


class DiningItemExtraRead(DiningItemExtraCreate):
    model_config = ConfigDict(from_attributes=True)
    id:       int
    group_id: int


class DiningItemExtraGroupCreate(BaseModel):
    name:       str = Field(..., max_length=100)
    name_ar:    Optional[str] = Field(None, max_length=100)
    group_type: str = Field("pick_list", pattern=r"^(pick_list|text)$")
    # pick_list = قائمة اختيارات (options تحت)، text = prompt نصي حر (مثلاً
    # "كام سمكة؟") — راجع docstring models.DiningItemExtraGroup. لمجموعات
    # النص min_select يتصرف كـ "إجباري؟" (0/1)، وoptions المفروض تفضل فاضية.
    min_select: int = Field(0, ge=0)
    max_select: int = Field(1, ge=1)
    sort_order: int = 0
    options:    list[DiningItemExtraCreate] = Field(default_factory=list)


class DiningItemExtraGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:         int
    item_id:    int
    name:       str
    name_ar:    Optional[str]
    group_type: str
    min_select: int
    max_select: int
    sort_order: int
    options:    list[DiningItemExtraRead] = []


# ─────────────────────── Recipe / BOM ──────────────────────────────────

class DiningItemRecipeLineCreate(BaseModel):
    product_id:        int
    quantity_per_unit: Decimal = Field(..., gt=0)
    notes:             Optional[str] = Field(None, max_length=200)


class DiningItemRecipeLineUpdate(BaseModel):
    quantity_per_unit: Optional[Decimal] = Field(None, gt=0)
    notes:             Optional[str]     = Field(None, max_length=200)


class DiningItemRecipeLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:                int
    item_id:           int
    product_id:        int
    product_name:      str
    product_unit:      str
    quantity_per_unit: Decimal
    unit_cost:         Decimal
    line_cost:         Decimal
    notes:             Optional[str]


# ─────────────────────── Variants ──────────────────────────────────────

class DiningItemVariantRecipeLineCreate(BaseModel):
    product_id:        int
    quantity_per_unit: Decimal = Field(..., gt=0)
    notes:             Optional[str] = Field(None, max_length=200)


class DiningItemVariantRecipeLineUpdate(BaseModel):
    quantity_per_unit: Optional[Decimal] = Field(None, gt=0)
    notes:             Optional[str]     = Field(None, max_length=200)


class DiningItemVariantRecipeLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:                int
    variant_id:        int
    product_id:        int
    product_name:      str
    product_unit:      str
    quantity_per_unit: Decimal
    unit_cost:         Decimal
    line_cost:         Decimal
    notes:             Optional[str]


class DiningItemVariantCreate(BaseModel):
    name:         str = Field(..., max_length=100)
    name_ar:      Optional[str] = Field(None, max_length=100)
    price:        Decimal = Field(..., gt=0)
    is_available: bool = True
    sort_order:   int = 0


class DiningItemVariantUpdate(BaseModel):
    name:         Optional[str]     = Field(None, max_length=100)
    name_ar:      Optional[str]     = Field(None, max_length=100)
    price:        Optional[Decimal] = Field(None, gt=0)
    is_available: Optional[bool]    = None
    sort_order:   Optional[int]     = None


class DiningItemVariantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:            int
    item_id:       int
    name:          str
    name_ar:       Optional[str]
    price:         Decimal
    is_available:  bool
    sort_order:    int
    recipe_lines:  list[DiningItemVariantRecipeLineRead] = []
    computed_cost: Decimal = Decimal("0")


class DiningItemRead(DiningItemCreate):
    model_config = ConfigDict(from_attributes=True)
    id:           int
    created_at:   datetime
    updated_at:   datetime
    extra_groups: list[DiningItemExtraGroupRead] = []
    recipe_lines: list[DiningItemRecipeLineRead] = []
    variants:     list[DiningItemVariantRead] = []
    computed_cost: Decimal = Decimal("0")

    @model_validator(mode="before")
    @classmethod
    def _inject_recipe_fields(cls, obj):
        """نفس نمط restaurant.schemas.MenuItemRead._inject_recipe_fields
        بالظبط — recipe_lines/variants/computed_cost مش أعمدة حقيقية،
        بيتحسبوا من الـ relationships + سعر المنتج الحالي قبل الـ
        validation العادي."""
        if isinstance(obj, (dict, cls)):
            return obj
        from app.modules.dining import services as _services  # noqa: PLC0415

        data = {name: getattr(obj, name, None) for name in cls.model_fields
                if name not in ("recipe_lines", "computed_cost", "extra_groups", "variants")}
        data["extra_groups"] = getattr(obj, "extra_groups", [])
        data["recipe_lines"] = [_services.build_recipe_line_read(line) for line in getattr(obj, "recipe_lines", [])]
        data["variants"] = [_services.build_variant_read(v) for v in getattr(obj, "variants", [])]
        data["computed_cost"] = _services.compute_item_cost(obj)
        return data


# ─────────────────────── Tables ────────────────────────────────────────

class DiningTableRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:           int
    branch_id:    int
    table_number: str
    capacity:     int
    status:       str
    section:      Optional[str]
    occupied_at:  Optional[datetime] = None
    grid_row:     Optional[int] = None
    grid_col:     Optional[int] = None
    # ── Active order info — computed in list_tables_with_orders (not a DB field) ──
    active_order_id:     Optional[int]   = None
    active_order_number: Optional[str]   = None
    active_order_total:  Optional[float] = None
    active_covers:       Optional[int]   = None
    order_status:        Optional[str]   = None  # open | in_kitchen | served
    # أي منفذ فتح الطلب الشاغل للطاولة دي — مهم لما الكاشير يكون واقف على
    # منيو منفذ تاني ويشوف الطاولة مشغولة (مثلاً طلب كافيه وهو واقف على
    # تاب المطعم)، عشان يعرف يفتح تفاصيل الطلب الصح بدل ما يفتره إنه فاضي.
    active_order_outlet_id: Optional[int] = None
    # هوية الضيف القاعد على الطاولة دي (2026-08-03) — من DiningOrder.
    # guest_name/guest_phone بتاعة الطلب النشط، نفس نمط active_order_* فوق.
    active_order_guest_name:  Optional[str] = None
    active_order_guest_phone: Optional[str] = None


class DiningTableCreate(BaseModel):
    branch_id:    int
    table_number: str = Field(..., max_length=20)
    capacity:     int = Field(4, ge=1)
    section:      Optional[str] = Field(None, max_length=50)
    grid_row:     Optional[int] = Field(None, ge=0)
    grid_col:     Optional[int] = Field(None, ge=0)


class DiningTableUpdate(BaseModel):
    table_number: Optional[str] = Field(None, max_length=20)
    capacity:     Optional[int] = Field(None, ge=1)
    section:      Optional[str] = Field(None, max_length=50)
    grid_row:     Optional[int] = Field(None, ge=0)
    grid_col:     Optional[int] = Field(None, ge=0)


class DiningTableGridUpdate(BaseModel):
    grid_row: Optional[int] = Field(None, ge=0)
    grid_col: Optional[int] = Field(None, ge=0)


# ─────────────────────── Orders ────────────────────────────────────────

class OrderItemCreate(BaseModel):
    item_id:    int
    variant_id: Optional[int] = None  # DiningItemVariant.id — إجباري لو الصنف عنده متغيّرات متاحة
    quantity:   int = Field(1, ge=1)
    notes:      Optional[str] = Field(None, max_length=200)
    extra_ids:  list[int] = Field(default_factory=list)
    extra_texts: dict[int, str] = Field(default_factory=dict)
    # group_id (DiningItemExtraGroup.id بـ group_type="text") -> إجابة نصية
    # حرة، مثال حقيقي: {12: "3 سمكات"} لمجموعة "كام سمكة؟" — راجع
    # services._resolve_extras للتحقق (إجباري/اختياري حسب min_select).


class OrderCreate(BaseModel):
    outlet_id:    int
    table_id:     Optional[int] = Field(None, ge=1)
    order_type:   str = Field("dine_in", pattern=r"^(dine_in|takeaway|delivery|room_service)$")
    guests_count: int = Field(1, ge=1)
    notes:        Optional[str] = Field(None, max_length=500)
    customer_id:  Optional[int] = None
    items:        list[OrderItemCreate] = Field(..., min_length=1)
    # هوية الضيف القاعد على الطاولة (2026-08-03، طلب Mohamed) — اختياريان
    # هنا على مستوى الـschema عمدًا (OrderCreate بيغطي dine_in/takeaway/
    # delivery/room_service كلهم)، الإجبارية الفعلية بتاعة "اسم عند فتح
    # طاولة جديدة" قرار UX بيتفرض من الفرونت إند (UnifiedPOSView.vue's
    # فورم فتح الطاولة)، مش من الـschema العام ده. للطلب الذاتي عبر QR،
    # الراوتر بيملأهم من GuestSession.guest_name/guest_phone تلقائيًا.
    guest_name:   Optional[str] = Field(None, max_length=100)
    guest_phone:  Optional[str] = Field(None, max_length=30)
    # ── فيتشر الفنادق (2026-08-07) ──────────────────────────────────────
    # اختياري — الكاشير/الويتر يختار الفندق المتعاقد لو الضيف من فندق.
    b2b_contract_id:   Optional[int] = None
    # ── فيتشر خريطة الشمسيات (2026-08-07) ──────────────────────────────
    # اختياري — بديل table_id لما الطلب من شمسية/برجولة مش طاولة مطعم.
    beach_location_id: Optional[int] = None


class OrderItemVoidRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=200)
    approver_user_id: Optional[int] = None
    approver_pin:      Optional[str] = Field(None, pattern=r"^\d{4,6}$")


class ApplyDiscountRequest(BaseModel):
    """راجع core.services.resolve_pin_approval — الكاشير صفر صلاحية خصم
    خالص (level 40 < min_approver_level=60 بتاع الخصم)، فأي محاولة تطبيق
    خصم من كاشير أو أوطى محتاجة PIN مدير/محاسب حاضر فعليًا، بغض النظر عن
    نتيجة قاعدة الخصم نفسها — الموافقة مطلوبة على *محاولة* التطبيق نفسها
    مش بس على نتيجتها (زي OrderItemVoidRequest بالظبط، مفيش نظام موافقة
    موازي)."""
    approver_user_id: Optional[int] = None
    approver_pin:      Optional[str] = Field(None, pattern=r"^\d{4,6}$")


class OrderItemExtraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:             int
    extra_id:       Optional[int]
    extra_name:     str
    extra_name_ar:  Optional[str] = None
    price_addition: Decimal
    text_value:     Optional[str] = None


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:           int
    order_id:     int
    item_id:      int
    variant_id:   Optional[int] = None
    name:         str
    name_ar:      Optional[str] = None
    unit_price:   Decimal
    quantity:     int
    notes:        Optional[str]
    status:       str
    extras:       list[OrderItemExtraRead] = []
    voided_reason: Optional[str] = None
    voided_by:     Optional[int] = None
    voided_at:     Optional[datetime] = None


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:                       int
    branch_id:                int
    outlet_id:                int
    table_id:                 Optional[int]
    order_number:             str
    status:                   str
    order_type:               str
    subtotal:                 Decimal
    vat_amount:                Decimal
    service_charge:            Decimal
    delivery_fee:               Decimal = Decimal("0")
    discount_amount:           Decimal
    total:                     Decimal
    refunded_amount:           Decimal
    guests_count:              int
    notes:                     Optional[str]
    waiter_id:                 Optional[int]
    payment_method:            Optional[str] = None
    applied_discount_rule_id:  Optional[int]
    customer_id:                Optional[int]
    guest_name:                 Optional[str] = None
    guest_phone:                Optional[str] = None
    # ── فيتشر الفنادق (2026-08-07) ──────────────────────────────────────
    b2b_contract_id:            Optional[int] = None
    hotel_name:                 Optional[str] = None   # snapshot من b2b_contracts.hotel_name
    # ── فيتشر خريطة الشمسيات (2026-08-07) ──────────────────────────────
    beach_location_id:          Optional[int] = None
    beach_location_label:       Optional[str] = None   # مثال: "⛱️ شمسية 5" — بيتحسب في الراوتر
    items:                      list[OrderItemRead] = []
    created_at:                 datetime
    updated_at:                 datetime


class OrderStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(held|open|in_kitchen|served|paid|cancelled)$")
    charge_to_room_id: Optional[int] = None
    payment_method: Optional[str] = Field(None, pattern=r"^(cash|card|room|wallet|credit_account)$")
    credit_account_id: Optional[int] = Field(None, gt=0)
    approver_user_id: Optional[int] = Field(None, gt=0)
    approver_pin: Optional[str] = Field(None, min_length=4, max_length=12)
    # POS-03: عملة الدفع الكاش — اختيارية، افتراضية EGP. لو currency ≠ EGP
    # وpayment_method="cash"، يجب تمرير fx_rate (سعر الصرف الحالي).
    payment_currency: Optional[str] = Field(None, pattern=r"^[A-Z]{3}$")
    payment_fx_rate:  Optional[Decimal] = Field(None, gt=0)

    @model_validator(mode="after")
    def _validate_fx(self) -> "OrderStatusUpdate":
        cur = (self.payment_currency or "EGP").upper()
        if cur != "EGP" and self.payment_method == "cash" and not self.payment_fx_rate:
            raise ValueError(
                "payment_fx_rate مطلوب لو payment_currency ≠ EGP وطريقة الدفع كاش"
            )
        if (self.approver_user_id is None) != (self.approver_pin is None):
            raise ValueError("بيانات موافقة المدير يجب أن تُرسل كاملة")
        if self.credit_account_id and self.payment_method != "credit_account":
            raise ValueError("credit_account_id يُستخدم فقط مع الدفع الآجل")
        return self


class OrderTransferRequest(BaseModel):
    """نقل طلب مفتوح من طاولة لأخرى (الضيوف اتحركوا فعليًا) — راجع
    services.transfer_order_table للتحقق الكامل (نفس الفرع/مش مشغولة بطلب
    تاني/الطاولة مش خارج الخدمة). راجع restaurant.schemas.OrderTransferRequest."""
    table_id: int


class WaiterTransferRequest(BaseModel):
    """تغيير النادل المسند لطلب مفتوح (M5 — الـ brief §2.6 بند 3): بيحتاج سبب
    صريح، والتغيير بيترك AuditLog ولا يمسح creator الأصلي (created_by ثابت).
    مثال: النادل الأصلي مشي/راح break، ومدير بيسند الطلب لنادل تاني."""
    new_waiter_id: int = Field(..., gt=0)
    reason: str = Field(..., min_length=3, max_length=500)


class SplitBillPayment(BaseModel):
    """جزء دفعة واحدة في تقسيم الفاتورة."""
    amount: Decimal = Field(..., gt=0)
    payment_method: str = Field(..., pattern=r"^(cash|card|room|wallet|credit_account)$")
    charge_to_room_id: Optional[int] = None  # لو payment_method = room
    credit_account_id: Optional[int] = Field(None, gt=0)
    # POS-03: عملة الدفع الكاش — اختيارية، افتراضية EGP
    currency: Optional[str] = Field(None, pattern=r"^[A-Z]{3}$")
    fx_rate:  Optional[Decimal] = Field(None, gt=0)

    @model_validator(mode="after")
    def _validate_fx(self) -> "SplitBillPayment":
        cur = (self.currency or "EGP").upper()
        if cur != "EGP" and self.payment_method == "cash" and not self.fx_rate:
            raise ValueError("fx_rate مطلوب لو currency ≠ EGP وطريقة الدفع كاش")
        if self.credit_account_id and self.payment_method != "credit_account":
            raise ValueError("credit_account_id يُستخدم فقط مع الدفع الآجل")
        return self


class SplitBillRequest(BaseModel):
    """P-07 — تقسيم الفاتورة على أكثر من طريقة دفع.
    المجموع لازم يساوي order.total بفارق ≤ 0.01 جنيه (floating-point tolerance).
    مثال: فاتورة 300ج → كاش 200 + بطاقة 100."""
    payments: list[SplitBillPayment] = Field(..., min_length=2, max_length=10)
    approver_user_id: Optional[int] = Field(None, gt=0)
    approver_pin: Optional[str] = Field(None, min_length=4, max_length=12)

    @model_validator(mode="after")
    def _validate_approval(self) -> "SplitBillRequest":
        if (self.approver_user_id is None) != (self.approver_pin is None):
            raise ValueError("بيانات موافقة المدير يجب أن تُرسل كاملة")
        return self


class OrderItemStatusUpdate(BaseModel):
    """تأكيد صنف واحد داخل تذكرة مطبخ (bump فردي) — بدل تأكيد التذكرة كلها
    دفعة واحدة عبر TicketStatusUpdate. راجع restaurant.schemas.OrderItemStatusUpdate
    — نفس المنطق بالظبط. cancelled/refunded مستبعدين عمداً — ليهم endpoints
    مخصصة (void/refund) بمنطق مالي/صلاحيات مختلف تمامًا."""
    status: str = Field(..., pattern=r"^(pending|in_kitchen|ready|served)$")


# ─────────────────────── Offline POS Sync ─────────────────────────────

class OrderSyncRequest(BaseModel):
    local_id:     str = Field(..., max_length=60)
    outlet_id:    int
    table_id:     Optional[int] = Field(None, ge=1)
    order_type:   str = Field("dine_in", pattern=r"^(dine_in|takeaway|delivery|room_service)$")
    guests_count: int = Field(1, ge=1)
    notes:        Optional[str] = Field(None, max_length=500)
    items:        list[OrderItemCreate] = Field(..., min_length=1)
    created_offline_at: Optional[datetime] = None


class RejectedSyncItem(BaseModel):
    item_id:       int
    name:          str
    reason:        str
    available_qty: int
    requested_qty: int


class OrderSyncResponse(BaseModel):
    order_id:         Optional[int]
    status:            str  # fulfilled|partial|rejected
    fulfilled_items:   list[OrderItemRead] = []
    rejected_items:    list[RejectedSyncItem] = []
    message:           str


# ── KDS schemas ───────────────────────────────────────────────────────

class KitchenTicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:             int
    branch_id:      int
    outlet_id:      int
    order_id:       int
    station:        str
    items_snapshot: list
    status:         str
    created_at:     datetime
    # ── حقول إضافية للعرض في KDS — computed في router ──
    order_number:   Optional[str] = None   # رقم الأوردر للعرض في بطاقة KDS
    table_number:   Optional[str] = None   # رقم الطاولة (dine_in فقط)
    order_type:     Optional[str] = None   # dine_in|takeaway|delivery|room_service
    order_notes:    Optional[str] = None   # ملاحظة الأوردر الكلية
    outlet_name:    Optional[str] = None   # اسم المنفذ — لو أكثر من منفذ في نفس المطبخ


class TicketStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(pending|in_progress|done)$")


class KDSScreenCreate(BaseModel):
    branch_id:           int
    outlet_id:           Optional[int] = None  # None = يعرض كل الـ outlets في الفرع
    name:                str = Field(..., max_length=100)
    stations:            list[str]
    display_mode:        str = Field("kanban", pattern=r"^(kanban|list|grid)$")
    alert_after_minutes: int = 15
    is_active:           bool = True


class KDSScreenRead(KDSScreenCreate):
    model_config = ConfigDict(from_attributes=True)
    id:         int
    created_at: datetime


# ─────────────────────── Reporting / Food Cost ────────────────────────

class FoodCostReportLine(BaseModel):
    item_id:                 int
    item_name:                str
    variant_id:               Optional[int] = None
    has_recipe:               bool
    quantity_sold:            int
    revenue:                  Decimal
    theoretical_unit_cost:    Decimal
    theoretical_total_cost:   Decimal
    food_cost_pct:            Optional[Decimal] = None
    gross_margin_amount:      Decimal
    gross_margin_pct:         Optional[Decimal] = None
    exceeds_threshold:        bool


class CogsTrendPoint(BaseModel):
    date:            date
    revenue:         Decimal
    theoretical_cost: Decimal
    food_cost_pct:   Optional[Decimal] = None


class GrossMarginSummary(BaseModel):
    branch_id:                int
    outlet_id:                Optional[int]
    date_from:                date
    date_to:                  date
    threshold_pct:            Decimal
    total_revenue:            Decimal
    total_theoretical_cost:   Decimal
    food_cost_pct:            Optional[Decimal] = None
    gross_margin_amount:      Decimal
    gross_margin_pct:         Optional[Decimal] = None
    items_missing_recipe:        int
    items_missing_recipe_revenue: Decimal


class FoodCostReportResponse(BaseModel):
    lines:   list[FoodCostReportLine]
    alerts:  list[FoodCostReportLine]
    trend:   list[CogsTrendPoint]
    summary: GrossMarginSummary


# ─────────────────────── Public / Guest (QR ordering, no auth) ────────
# راجع restaurant.schemas.PublicMenuItemRead وما حولها — نفس الشكل بالظبط،
# outlet_id بدل الفصل بين restaurant/cafe (DINING_CUTOVER_PLAN.md Batch 6:
# فجوة تكافؤ حقيقية اتكشفت وهي بتحذف restaurant/cafe — موقع الحجز العام
# (`public` app) كان بيكلّم /restaurant/public/* و/cafe/public/* حصريًا،
# بدون أي إصدار dining مقابل، فحذفهم من غير الإضافة دي كان هيكسر طلب
# الضيف عبر QR بالكامل).

class PublicOutletRead(BaseModel):
    """للموقع العام (apps/public's DiningView.vue — صفحة المنيو التسويقية)
    عشان يعرف outlet_id لكل منفذ من غير تسجيل دخول. حقول محدودة عمدًا —
    بدون revenue_account_code/branch_id الداخليين (راجع OutletRead)."""
    model_config = ConfigDict(from_attributes=True)
    id:          int
    name:        str
    name_ar:     Optional[str]
    outlet_type: str


class PublicMenuExtraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:             int
    name:           str
    name_ar:        Optional[str]
    price_addition: Decimal


class PublicMenuExtraGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:         int
    name:       str
    name_ar:    Optional[str]
    group_type: str
    min_select: int
    max_select: int
    options:    list[PublicMenuExtraRead] = []


class PublicMenuVariantRead(BaseModel):
    """للضيف عبر QR — بدون تكلفة/وصفة، سعر واسم بس."""
    model_config = ConfigDict(from_attributes=True)
    id:           int
    name:         str
    name_ar:      Optional[str]
    price:        Decimal
    is_available: bool


class PublicMenuItemRead(BaseModel):
    """للضيف عبر QR — بدون cost أو station أو بيانات داخلية.

    name_ru/name_it/description_ru/description_it (2026-08-03، منيو 2026):
    الموقع العام بيدعم 4 لغات فعلاً (ar/en/ru/it) لكن كان بيرجع اسم/وصف
    الصنف بالإنجليزي/العربي بس — ضيف روسي أو إيطالي كان شايف واجهة الموقع
    بلغته لكن أسماء الأصناف نفسها بالإنجليزي دايمًا. راجع
    core.services._guest_service_outlets/create_guest_order's ملاحظة عن
    نظام الموظفين اللي فاضل عربي/إنجليزي بس عمدًا (القرار مختلف تمامًا —
    الضيف 4 لغات، الموظف لغتين، راجع DiningOrderItem.name_ar)."""
    model_config = ConfigDict(from_attributes=True)
    id:                  int
    name:                str
    name_ar:             Optional[str]
    name_ru:             Optional[str] = None
    name_it:             Optional[str] = None
    description:         Optional[str]
    description_ar:      Optional[str] = None
    description_ru:      Optional[str] = None
    description_it:      Optional[str] = None
    price:               Decimal
    is_available:        bool
    preparation_minutes: int
    image_url:           Optional[str]
    category_id:         Optional[int]
    extra_groups:        list[PublicMenuExtraGroupRead] = []
    variants:            list[PublicMenuVariantRead] = []


class PublicMenuCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:      int
    name:    str
    name_ar: Optional[str]
    name_ru: Optional[str] = None
    name_it: Optional[str] = None


class PublicMenuResponse(BaseModel):
    """الرد الكامل على GET /dining/public/menu — categories + items في طلب واحد.
    outlet_name/outlet_name_ar مضافين (DINING_CUTOVER_PLAN.md Batch 6 frontend)
    عشان apps/public's OrderView.vue تعرض اسم المنفذ الحقيقي بدل تسمية ثابتة
    "المطعم"/"الكافيه" (dining بيدعم أي outlet_type مفتوح، مش بس النوعين دول).

    self_order_enabled (Gate 8 Phase 1 Batch D/E، 2026-07-22): قبل كده
    الفرونت إند كان بيعرض سلة الطلب الذاتي دايمًا بغض النظر عن حالة
    services.assert_guest_self_order_enabled — الضيف كان يقدر يملى سلة
    كاملة ويكتشف الرفض (400) بس وقت الإرسال. بقى الرد نفسه بيقول للضيف
    مقدمًا لو الطلب الذاتي متاح لهذا الفرع، فالواجهة تعرض view_and_call
    بس (الافتراضي حسب Decision 0001) لو لأ."""
    branch_id:          int
    outlet_id:          int
    outlet_name:        str
    outlet_name_ar:     Optional[str]
    table_id:           Optional[int]
    self_order_enabled: bool
    categories:         list[PublicMenuCategoryRead]
    items:              list[PublicMenuItemRead]


class GuestServiceMenuResponse(BaseModel):
    """Token/session-scoped menu without branch or physical-location IDs."""
    outlet_id:          int
    outlet_name:        str
    outlet_name_ar:     Optional[str]
    self_order_enabled: bool
    categories:         list[PublicMenuCategoryRead]
    items:              list[PublicMenuItemRead]


class GuestOrderItemCreate(BaseModel):
    item_id:     int
    variant_id:  Optional[int] = None
    quantity:    int = Field(1, ge=1)
    notes:       Optional[str] = Field(None, max_length=200)
    extra_ids:   list[int] = Field(default_factory=list)
    extra_texts: dict[int, str] = Field(default_factory=dict)


class GuestOrderCreate(BaseModel):
    """Order body; table and branch come from X-Guest-Session."""
    model_config = ConfigDict(extra="forbid")

    outlet_id:    int
    guests_count: int = Field(1, ge=1)
    notes:        Optional[str] = Field(None, max_length=300)
    items:        list[GuestOrderItemCreate] = Field(..., min_length=1)


class GuestOrderRead(BaseModel):
    """Session-bound guest order creation/status response.

    ``public_reference`` is random and status reads additionally require the
    issuing guest session; the sequential database ID is never returned.
    """
    public_reference: str
    order_number: str
    status:       str
    total:        Decimal
    items_count:  int
    message:      str


# ── Outlet Sales Report ───────────────────────────────────────────────────────

class SalesReportPeriod(BaseModel):
    from_: str = Field(alias="from")
    to: str
    model_config = ConfigDict(populate_by_name=True)

class PaymentBreakdownItem(BaseModel):
    orders: int
    total:  float

class TopSalesItem(BaseModel):
    name:    str
    qty:     int
    revenue: float

class OutletSalesReport(BaseModel):
    """GET /dining/outlets/{outlet_id}/reports/sales"""
    period:           SalesReportPeriod
    outlet_id:        int
    branch_id:        int
    total_orders:     int
    total_revenue:    float
    total_vat:        float
    total_discount:   float
    avg_order_value:  float
    payment_breakdown: dict[str, PaymentBreakdownItem] = Field(default_factory=dict)
    top_items:        list[TopSalesItem] = Field(default_factory=list)


# ── Hotel (B2B) Consumption Report (2026-08-07) ──────────────────────────────

class HotelOutletBreakdown(BaseModel):
    """إيراد منفذ واحد (مطعم أو كافيه) لفندق محدد."""
    outlet_id:    int
    outlet_name:  str
    outlet_type:  str
    orders_count: int
    revenue:      Decimal


class HotelConsumptionRow(BaseModel):
    """صف واحد في تقرير استهلاك الفنادق — فندق × فترة."""
    contract_id:        int
    hotel_name:         str
    hotel_name_ar:      Optional[str] = None
    # إجماليات
    total_orders:       int
    total_guests:       int           # مجموع guests_count على الطلبات
    total_revenue:      Decimal
    # مقارنة بقيمة العقد (entry_price × daily_quota × أيام الفترة)
    # nullable لأن daily_quota/entry_price حقول الشاطئ مش الدايننج —
    # بس بيديك فكرة: "الفندق ده بيكسبني ولا لا؟"
    contract_daily_quota:    int
    contract_entry_price:    Decimal
    # تفصيل لكل منفذ (مطعم/كافيه) بشكل منفصل
    by_outlet: list[HotelOutletBreakdown] = Field(default_factory=list)


class HotelConsumptionReport(BaseModel):
    """GET /dining/reports/hotel-consumption — تقرير استهلاك الفنادق."""
    from_date:   date
    to_date:     date
    branch_id:   int
    hotels:      list[HotelConsumptionRow] = Field(default_factory=list)
    # إجمالي كل الفنادق معًا
    grand_total_orders:  int
    grand_total_guests:  int
    grand_total_revenue: Decimal
