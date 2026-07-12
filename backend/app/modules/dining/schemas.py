"""app/modules/dining/schemas.py — Pydantic v2

يدمج restaurant/schemas.py + cafe/schemas.py — نفس الشكل بالظبط، إضافة
outlet_id/outlet_type فين ما يلزم بدل الفصل بين موديولين. راجع
DiningItem/DiningOrder وباقي دوكسترنجز models.py للتبرير التجاري الكامل.
"""
from __future__ import annotations

from datetime import date, datetime
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
    is_active:            bool = True


class OutletUpdate(BaseModel):
    name:                 Optional[str] = Field(None, max_length=100)
    name_ar:              Optional[str] = Field(None, max_length=100)
    outlet_type:          Optional[str] = Field(None, max_length=30)
    revenue_account_code: Optional[str] = Field(None, max_length=10)
    default_service_charge_pct: Optional[Decimal] = Field(None, ge=0, le=100)
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
    price:               Decimal = Field(..., gt=0)
    cost:                Optional[Decimal] = Field(None, ge=0)
    is_available:        bool = True
    preparation_minutes: int  = 10
    image_url:           Optional[str] = Field(None, max_length=500)
    station:             str = Field("hot", pattern=r"^(hot|grill|cold|bar|dessert)$")
    linked_product_id:   Optional[int] = None


class DiningItemUpdate(BaseModel):
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
    outlet_id:    int
    table_number: str
    capacity:     int
    status:       str
    section:      Optional[str]
    occupied_at:  Optional[datetime] = None
    grid_row:     Optional[int] = None
    grid_col:     Optional[int] = None


class DiningTableCreate(BaseModel):
    branch_id:    int
    outlet_id:    int
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
    table_id:     Optional[int] = None
    order_type:   str = Field("dine_in", pattern=r"^(dine_in|takeaway|delivery|room_service)$")
    guests_count: int = Field(1, ge=1)
    notes:        Optional[str] = Field(None, max_length=500)
    customer_id:  Optional[int] = None
    items:        list[OrderItemCreate] = Field(..., min_length=1)


class OrderItemVoidRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=200)
    approver_user_id: Optional[int] = None
    approver_pin:      Optional[str] = Field(None, pattern=r"^\d{4,6}$")


class OrderItemExtraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:             int
    extra_id:       Optional[int]
    extra_name:     str
    price_addition: Decimal
    text_value:     Optional[str] = None


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:           int
    order_id:     int
    item_id:      int
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
    discount_amount:           Decimal
    total:                     Decimal
    refunded_amount:           Decimal
    guests_count:              int
    notes:                     Optional[str]
    waiter_id:                 Optional[int]
    payment_method:            Optional[str] = None
    applied_discount_rule_id:  Optional[int]
    customer_id:                Optional[int]
    items:                      list[OrderItemRead] = []
    created_at:                 datetime
    updated_at:                 datetime


class OrderStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(held|open|in_kitchen|served|paid|cancelled)$")
    charge_to_room_id: Optional[int] = None
    payment_method: Optional[str] = Field(None, pattern=r"^(cash|card|room|wallet)$")


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
    table_id:     Optional[int] = None
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
