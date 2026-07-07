"""app/modules/restaurant/schemas.py — Pydantic v2"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MenuCategoryCreate(BaseModel):
    branch_id:  int
    name:       str = Field(..., max_length=100)
    name_ar:    Optional[str] = Field(None, max_length=100)
    sort_order: int = 0
    is_active:  bool = True


class MenuCategoryRead(MenuCategoryCreate):
    model_config = ConfigDict(from_attributes=True)
    id:         int
    created_at: datetime


class MenuItemCreate(BaseModel):
    branch_id:           int
    category_id:         Optional[int] = None
    name:                str  = Field(..., max_length=200)
    name_ar:             Optional[str] = Field(None, max_length=200)
    price:               Decimal = Field(..., gt=0)
    cost:                Optional[Decimal] = Field(None, ge=0)
    is_available:        bool = True
    preparation_minutes: int  = 10
    image_url:           Optional[str] = Field(None, max_length=500)
    station:             str = Field("hot", pattern=r"^(hot|grill|cold|bar|dessert)$")
    linked_product_id:   Optional[int] = None


class MenuItemUpdate(BaseModel):
    name:                Optional[str]     = None
    name_ar:             Optional[str]     = None
    price:               Optional[Decimal] = Field(None, gt=0)
    cost:                Optional[Decimal] = None
    is_available:        Optional[bool]    = None
    preparation_minutes: Optional[int]     = None
    category_id:         Optional[int]     = None
    station:             Optional[str]     = Field(None, pattern=r"^(hot|grill|cold|bar|dessert)$")
    image_url:           Optional[str]     = None
    linked_product_id:   Optional[int]     = None


# ─────────────────────── Extras / Modifiers ───────────────────────────

class MenuItemExtraCreate(BaseModel):
    name:           str = Field(..., max_length=100)
    name_ar:        Optional[str] = Field(None, max_length=100)
    price_addition: Decimal = Field(Decimal("0"), ge=0)
    is_available:   bool = True
    sort_order:     int = 0


class MenuItemExtraRead(MenuItemExtraCreate):
    model_config = ConfigDict(from_attributes=True)
    id:       int
    group_id: int


class MenuItemExtraGroupCreate(BaseModel):
    name:       str = Field(..., max_length=100)
    name_ar:    Optional[str] = Field(None, max_length=100)
    min_select: int = Field(0, ge=0)
    max_select: int = Field(1, ge=1)
    sort_order: int = 0
    options:    list[MenuItemExtraCreate] = Field(default_factory=list)


class MenuItemExtraGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:           int
    menu_item_id: int
    name:         str
    name_ar:      Optional[str]
    min_select:   int
    max_select:   int
    sort_order:   int
    options:      list[MenuItemExtraRead] = []


# ─────────────────────── Recipe / BOM ──────────────────────────────────
# وصفة الصنف — كمية من inventory.Product بتتستهلك لكل وحدة مباعة. راجع
# app.modules.restaurant.models.MenuItemRecipeLine للتفاصيل الكاملة.

class MenuItemRecipeLineCreate(BaseModel):
    product_id:        int
    quantity_per_unit: Decimal = Field(..., gt=0)
    notes:             Optional[str] = Field(None, max_length=200)


class MenuItemRecipeLineUpdate(BaseModel):
    quantity_per_unit: Optional[Decimal] = Field(None, gt=0)
    notes:             Optional[str]     = Field(None, max_length=200)


class MenuItemRecipeLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:                int
    menu_item_id:      int
    product_id:        int
    product_name:      str
    product_unit:      str
    quantity_per_unit: Decimal
    unit_cost:         Decimal   # snapshot لحظي من Product.cost_price الحالي
    line_cost:         Decimal   # quantity_per_unit × unit_cost
    notes:             Optional[str]


# ─────────────────────── Variants (حجم/نوع حقيقي) ──────────────────────
# متغيّر حقيقي — سعر ووصفة مستقلين تمامًا عن الصنف الأساسي، مختلف عن
# MenuItemExtra (رسم إضافي فوق وصفة ثابتة). راجع
# app.modules.restaurant.models.MenuItemVariant للتفاصيل الكاملة.

class MenuItemVariantRecipeLineCreate(BaseModel):
    product_id:        int
    quantity_per_unit: Decimal = Field(..., gt=0)
    notes:             Optional[str] = Field(None, max_length=200)


class MenuItemVariantRecipeLineUpdate(BaseModel):
    quantity_per_unit: Optional[Decimal] = Field(None, gt=0)
    notes:             Optional[str]     = Field(None, max_length=200)


class MenuItemVariantRecipeLineRead(BaseModel):
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


class MenuItemVariantCreate(BaseModel):
    name:         str = Field(..., max_length=100)
    name_ar:      Optional[str] = Field(None, max_length=100)
    price:        Decimal = Field(..., gt=0)
    is_available: bool = True
    sort_order:   int = 0


class MenuItemVariantUpdate(BaseModel):
    name:         Optional[str]     = Field(None, max_length=100)
    name_ar:      Optional[str]     = Field(None, max_length=100)
    price:        Optional[Decimal] = Field(None, gt=0)
    is_available: Optional[bool]    = None
    sort_order:   Optional[int]     = None


class MenuItemVariantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:            int
    menu_item_id:  int
    name:          str
    name_ar:       Optional[str]
    price:         Decimal
    is_available:  bool
    sort_order:    int
    recipe_lines:  list[MenuItemVariantRecipeLineRead] = []
    computed_cost: Decimal = Decimal("0")
    # ملحوظة: مبنية من dict جاهز (services.build_variant_read) مش من ORM
    # مباشرة — نفس أسلوب recipe_lines فوق، مفيش before-validator هنا.


class MenuItemRead(MenuItemCreate):
    model_config = ConfigDict(from_attributes=True)
    id:           int
    created_at:   datetime
    updated_at:   datetime
    extra_groups: list[MenuItemExtraGroupRead] = []
    recipe_lines: list[MenuItemRecipeLineRead] = []
    variants:     list[MenuItemVariantRead] = []
    # تكلفة محسوبة من الوصفة (مجموع quantity_per_unit × تكلفة المنتج الحالية
    # لكل سطر) لو فيه وصفة حقيقية، وإلا fallback لحقل cost اليدوي — الفورمولا
    # نفسها في services.compute_menu_item_cost (business logic، مش هنا).
    computed_cost: Decimal = Decimal("0")

    @model_validator(mode="before")
    @classmethod
    def _inject_recipe_fields(cls, obj):
        """recipe_lines/variants/computed_cost مش أعمدة حقيقية على MenuItem
        (ORM) — بيتحسبوا هنا من الـ relationships + سعر المنتج الحالي قبل
        الـ validation العادي، عشان MenuItemRead.model_validate(item) يفضل
        شغال زي ما هو من كل نقط الاستدعاء الموجودة من غير أي تعديل عليهم."""
        if isinstance(obj, (dict, cls)):
            return obj
        from app.modules.restaurant import services as _services  # noqa: PLC0415 — تجنّب circular import مع services.py

        data = {name: getattr(obj, name, None) for name in cls.model_fields
                if name not in ("recipe_lines", "computed_cost", "extra_groups", "variants")}
        data["extra_groups"] = getattr(obj, "extra_groups", [])
        data["recipe_lines"] = [_services.build_recipe_line_read(line) for line in getattr(obj, "recipe_lines", [])]
        data["variants"] = [_services.build_variant_read(v) for v in getattr(obj, "variants", [])]
        data["computed_cost"] = _services.compute_menu_item_cost(obj)
        return data


class DiningTableRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:           int
    branch_id:    int
    table_number: str
    capacity:     int
    status:       str
    section:      Optional[str]
    occupied_at:  Optional[datetime] = None


class DiningTableStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(available|occupied|reserved|out_of_service)$")


class OrderItemCreate(BaseModel):
    menu_item_id: int
    variant_id:   Optional[int] = None  # MenuItemVariant.id — إجباري لو الصنف عنده متغيّرات متاحة
    quantity:     int = Field(1, ge=1)
    notes:        Optional[str] = Field(None, max_length=200)
    extra_ids:    list[int] = Field(default_factory=list)  # MenuItemExtra.id المختارة


class OrderCreate(BaseModel):
    table_id:    Optional[int] = None
    order_type:  str = Field("dine_in", pattern=r"^(dine_in|takeaway|delivery|room_service)$")
    guests_count:int = Field(1, ge=1)
    notes:       Optional[str] = Field(None, max_length=500)
    customer_id: Optional[int] = None
    items:       list[OrderItemCreate] = Field(..., min_length=1)


class OrderItemVoidRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=200)


class OrderItemExtraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:             int
    extra_id:       Optional[int]
    extra_name:     str
    price_addition: Decimal


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:           int
    order_id:     int
    menu_item_id: int
    variant_id:   Optional[int] = None
    name:         str
    unit_price:   Decimal
    quantity:     int
    notes:        Optional[str]
    status:       str
    extras:       list[OrderItemExtraRead] = []
    voided_reason: Optional[str] = None
    voided_by:     Optional[int] = None
    voided_at:     Optional[datetime] = None
    # ملحوظة: نفس الحقول دي (voided_reason/voided_by/voided_at) بتتسجّل كمان
    # لمرتجع بعد الدفع (status="refunded") — راجع services.refund_order_item،
    # نفس شكل "مين/ليه/إمتى" صالح للحالتين، مفيش داعي لحقول مكرّرة.


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:                       int
    branch_id:                int
    table_id:                 Optional[int]
    order_number:             str
    status:                   str
    order_type:               str
    subtotal:                 Decimal
    vat_amount:               Decimal
    service_charge:           Decimal
    discount_amount:          Decimal
    total:                    Decimal
    refunded_amount:          Decimal
    guests_count:             int
    notes:                    Optional[str]
    waiter_id:                Optional[int]
    applied_discount_rule_id: Optional[int]
    customer_id:              Optional[int]
    items:                    list[OrderItemRead] = []
    created_at:               datetime
    updated_at:               datetime


class OrderStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(held|open|in_kitchen|served|paid|cancelled)$")
    charge_to_room_id: Optional[int] = None
    # لو موجود وقت status="paid": يدوّر على الحجز الـ checked_in في الغرفة دي
    # ويحمّل قيمة الطلب على فوليو الضيف بدل ما ياخد كاش فورًا (Charge to Room)


# ─────────────────────── Offline POS Sync ─────────────────────────────
# عقد متوافق مع 07-BUSINESS-RULES.md § 9 — الـ client (IndexedDB) يرسل
# الطلب اللي اتعمل وهو offline، والـ server هو مصدر الحقيقة لتوفر الأصناف.

class OrderSyncRequest(BaseModel):
    local_id:     str = Field(..., max_length=60)  # UUID من IndexedDB — idempotency key
    table_id:     Optional[int] = None
    order_type:   str = Field("dine_in", pattern=r"^(dine_in|takeaway|delivery|room_service)$")
    guests_count: int = Field(1, ge=1)
    notes:        Optional[str] = Field(None, max_length=500)
    items:        list[OrderItemCreate] = Field(..., min_length=1)
    created_offline_at: Optional[datetime] = None


class RejectedSyncItem(BaseModel):
    item_id:       int
    name:          str
    reason:        str  # out_of_stock
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
    order_id:       int
    module:         str
    station:        str
    items_snapshot: list
    status:         str
    created_at:     datetime


class TicketStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(pending|in_progress|done)$")


class KDSScreenCreate(BaseModel):
    branch_id:           int
    name:                str = Field(..., max_length=100)
    module:              str = Field("restaurant", pattern=r"^(restaurant|cafe)$")
    stations:            list[str]
    display_mode:        str = Field("kanban", pattern=r"^(kanban|list|grid)$")
    alert_after_minutes: int = 15
    is_active:           bool = True


class KDSScreenRead(KDSScreenCreate):
    model_config = ConfigDict(from_attributes=True)
    id:         int
    created_at: datetime


# ── Public (Guest QR) Schemas — بدون auth ────────────────────────────
# هذه الـ schemas مقلّصة عمداً — الضيف يشوف بس اللي يحتاجه

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
    """للضيف عبر QR — بدون cost أو station أو بيانات داخلية."""
    model_config = ConfigDict(from_attributes=True)
    id:                  int
    name:                str
    name_ar:             Optional[str]
    price:               Decimal
    is_available:        bool
    preparation_minutes: int
    image_url:           Optional[str]
    category_id:         Optional[int]
    extra_groups:        list[PublicMenuExtraGroupRead] = []
    variants:            list[PublicMenuVariantRead] = []


class PublicMenuCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:       int
    name:     str
    name_ar:  Optional[str]


class PublicMenuResponse(BaseModel):
    """الرد الكامل على GET /public/menu — categories + items في طلب واحد."""
    branch_id:  int
    table_id:   Optional[int]
    categories: list[PublicMenuCategoryRead]
    items:      list[PublicMenuItemRead]


class GuestOrderItemCreate(BaseModel):
    menu_item_id: int
    variant_id:   Optional[int] = None
    quantity:     int = Field(1, ge=1)
    notes:        Optional[str] = Field(None, max_length=200)
    extra_ids:    list[int] = Field(default_factory=list)


class GuestOrderCreate(BaseModel):
    """الطلب من الضيف عبر QR."""
    branch_id:    int
    table_id:     Optional[int] = None
    guests_count: int = Field(1, ge=1)
    notes:        Optional[str] = Field(None, max_length=300)
    items:        list[GuestOrderItemCreate] = Field(..., min_length=1)


class GuestOrderRead(BaseModel):
    """ما يشوفه الضيف بعد تقديم الطلب — بدون بيانات مالية داخلية."""
    order_id:     int
    order_number: str
    status:       str
    total:        Decimal
    items_count:  int
    message:      str


# ─────────────────────── Reporting / Food Cost ────────────────────────
# راجع app.resort_os.food_cost_engine للفورمولا الأصلية — هنا بس شكل الرد.

class FoodCostReportLine(BaseModel):
    """صف واحد لكل "وحدة تقرير" — الصنف الأساسي لو مفهوش متغيّرات متاحة،
    وإلا صف منفصل لكل متغيّر (سعر ووصفة مستقلين تمامًا لكل حجم/نوع — راجع
    services.get_food_cost_report للتبرير الكامل). تكلفة نظرية (وصفة × كمية
    مباعة فعليًا) مقابل الإيراد الفعلي في المدى المطلوب."""
    menu_item_id:           int
    menu_item_name:         str
    # اسم العرض يتضمّن اسم المتغيّر لو موجود (مثال: "كابتشينو - كبير") —
    # variant_id فوق للتعريف البرمجي، الاسم هنا جاهز للعرض المباشر.
    variant_id:             Optional[int] = None
    has_recipe:             bool
    # False يعني الصنف مفيهوش وصفة (BOM) مسجّلة — التكلفة/النسبة هنا صفر
    # افتراضيًا، مش لأن التكلفة الحقيقية صفر، لازم الواجهة تُظهر تنبيه مختلف
    # ("وصفة ناقصة") مش "تكلفة ممتازة 0%".
    quantity_sold:          int
    revenue:                Decimal
    theoretical_unit_cost:  Decimal
    theoretical_total_cost: Decimal
    food_cost_pct:          Optional[Decimal] = None
    gross_margin_amount:    Decimal
    gross_margin_pct:       Optional[Decimal] = None
    exceeds_threshold:      bool


class CogsTrendPoint(BaseModel):
    """نقطة واحدة في اتجاه تكلفة الطعام اليومي عبر المدى الزمني المطلوب."""
    date:            date
    revenue:         Decimal
    theoretical_cost: Decimal
    food_cost_pct:   Optional[Decimal] = None


class GrossMarginSummary(BaseModel):
    """ملخص الفرع بالكامل للمدى الزمني — محسوب فقط من الأصناف اللي ليها
    وصفة حقيقية (has_recipe=True)؛ الأصناف الناقصة الوصفة مُستبعدة من
    الإجمالي المالي (مش معتبرة تكلفتها صفر) لكن معدودة صراحةً تحت
    ``items_missing_recipe`` عشان المدير يعرف حجم الفجوة في تغطية البيانات."""
    branch_id:                int
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
    """الرد الكامل لـ GET /reports/food-cost — الاستعلام الأساسي واحد
    (كل الطلبات المدفوعة في المدى)، وباقي الأشكال (lines/alerts/trend/
    summary) كلها اشتقاقات في الذاكرة منه، مش استعلامات منفصلة."""
    lines:   list[FoodCostReportLine]
    alerts:  list[FoodCostReportLine]
    trend:   list[CogsTrendPoint]
    summary: GrossMarginSummary
