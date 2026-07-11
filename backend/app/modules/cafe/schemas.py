"""app/modules/cafe/schemas.py — Pydantic v2 (نفس نمط restaurant)"""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CafeCategoryCreate(BaseModel):
    branch_id: int
    name:       str = Field(..., max_length=100)
    name_ar:    Optional[str] = None
    sort_order: int = 0


class CafeCategoryUpdate(BaseModel):
    name:       Optional[str]  = Field(None, max_length=100)
    name_ar:    Optional[str]  = None
    sort_order: Optional[int]  = None
    is_active:  Optional[bool] = None


class CafeCategoryRead(CafeCategoryCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int; is_active: bool; created_at: datetime


# ─────────────────────── Extras / Modifiers ───────────────────────────

class CafeMenuItemExtraCreate(BaseModel):
    name:           str = Field(..., max_length=100)
    name_ar:        Optional[str] = Field(None, max_length=100)
    price_addition: Decimal = Field(Decimal("0"), ge=0)
    is_available:   bool = True
    sort_order:     int = 0


class CafeMenuItemExtraRead(CafeMenuItemExtraCreate):
    model_config = ConfigDict(from_attributes=True)
    id:       int
    group_id: int


class CafeMenuItemExtraGroupCreate(BaseModel):
    name:       str = Field(..., max_length=100)
    name_ar:    Optional[str] = Field(None, max_length=100)
    min_select: int = Field(0, ge=0)
    max_select: int = Field(1, ge=1)
    sort_order: int = 0
    options:    list[CafeMenuItemExtraCreate] = Field(default_factory=list)


class CafeMenuItemExtraGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:           int
    cafe_item_id: int
    name:         str
    name_ar:      Optional[str]
    min_select:   int
    max_select:   int
    sort_order:   int
    options:      list[CafeMenuItemExtraRead] = []


class CafeItemCreate(BaseModel):
    branch_id:           int
    category_id:         Optional[int] = None
    name:                str = Field(..., max_length=200)
    name_ar:             Optional[str] = None
    price:               Decimal = Field(..., gt=0)
    cost:                Optional[Decimal] = None
    is_available:        bool = True
    preparation_minutes: int = 5
    image_url:           Optional[str] = None
    station:             str = Field("bar", pattern=r"^(hot|grill|cold|bar|dessert)$")
    linked_product_id:   Optional[int] = None
    available_from_time: Optional[time] = None
    available_until_time: Optional[time] = None
    # نافذة تقديم الصنف — نفس restaurant.MenuItemCreate بالظبط.


class CafeItemUpdate(BaseModel):
    name:                Optional[str]     = None
    price:               Optional[Decimal] = None
    cost:                Optional[Decimal] = None
    is_available:        Optional[bool]    = None
    preparation_minutes: Optional[int]     = None
    category_id:         Optional[int]     = None
    station:             Optional[str]     = Field(None, pattern=r"^(hot|grill|cold|bar|dessert)$")
    linked_product_id:   Optional[int]     = None
    available_from_time: Optional[time]    = None
    available_until_time: Optional[time]   = None


# ─────────────────────── Recipe / BOM ───────────────────────────────────
# نفس نمط restaurant.MenuItemRecipeLine* بالضبط — راجع
# app.modules.cafe.models.CafeItemRecipeLine.

class CafeItemRecipeLineCreate(BaseModel):
    product_id:        int
    quantity_per_unit: Decimal = Field(..., gt=0)
    notes:             Optional[str] = Field(None, max_length=200)


class CafeItemRecipeLineUpdate(BaseModel):
    quantity_per_unit: Optional[Decimal] = Field(None, gt=0)
    notes:             Optional[str]     = Field(None, max_length=200)


class CafeItemRecipeLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:                int
    cafe_item_id:      int
    product_id:        int
    product_name:      str
    product_unit:      str
    quantity_per_unit: Decimal
    unit_cost:         Decimal
    line_cost:         Decimal
    notes:             Optional[str]


# ─────────────────────── Variants (حجم/نوع حقيقي) ──────────────────────
# نفس نمط restaurant.MenuItemVariant* بالضبط — راجع
# app.modules.cafe.models.CafeItemVariant للتفاصيل الكاملة.

class CafeItemVariantRecipeLineCreate(BaseModel):
    product_id:        int
    quantity_per_unit: Decimal = Field(..., gt=0)
    notes:             Optional[str] = Field(None, max_length=200)


class CafeItemVariantRecipeLineUpdate(BaseModel):
    quantity_per_unit: Optional[Decimal] = Field(None, gt=0)
    notes:             Optional[str]     = Field(None, max_length=200)


class CafeItemVariantRecipeLineRead(BaseModel):
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


class CafeItemVariantCreate(BaseModel):
    name:         str = Field(..., max_length=100)
    name_ar:      Optional[str] = Field(None, max_length=100)
    price:        Decimal = Field(..., gt=0)
    is_available: bool = True
    sort_order:   int = 0


class CafeItemVariantUpdate(BaseModel):
    name:         Optional[str]     = Field(None, max_length=100)
    name_ar:      Optional[str]     = Field(None, max_length=100)
    price:        Optional[Decimal] = Field(None, gt=0)
    is_available: Optional[bool]    = None
    sort_order:   Optional[int]     = None


class CafeItemVariantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:            int
    cafe_item_id:  int
    name:          str
    name_ar:       Optional[str]
    price:         Decimal
    is_available:  bool
    sort_order:    int
    recipe_lines:  list[CafeItemVariantRecipeLineRead] = []
    computed_cost: Decimal = Decimal("0")


class CafeItemRead(CafeItemCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int; created_at: datetime; updated_at: datetime
    extra_groups: list[CafeMenuItemExtraGroupRead] = []
    recipe_lines: list[CafeItemRecipeLineRead] = []
    variants: list[CafeItemVariantRead] = []
    computed_cost: Decimal = Decimal("0")

    @model_validator(mode="before")
    @classmethod
    def _inject_recipe_fields(cls, obj):
        """نفس منطق restaurant.MenuItemRead._inject_recipe_fields بالضبط."""
        if isinstance(obj, (dict, cls)):
            return obj
        from app.modules.cafe import services as _services  # noqa: PLC0415 — تجنّب circular import

        data = {name: getattr(obj, name, None) for name in cls.model_fields
                if name not in ("recipe_lines", "computed_cost", "extra_groups", "variants")}
        data["extra_groups"] = getattr(obj, "extra_groups", [])
        data["recipe_lines"] = [_services.build_recipe_line_read(line) for line in getattr(obj, "recipe_lines", [])]
        data["variants"] = [_services.build_variant_read(v) for v in getattr(obj, "variants", [])]
        data["computed_cost"] = _services.compute_cafe_item_cost(obj)
        return data


class CafeTableCreate(BaseModel):
    branch_id:    int
    table_number: str = Field(..., max_length=20)
    capacity:     int = Field(2, ge=1)
    section:      Optional[str] = Field(None, max_length=50)


class CafeTableUpdate(BaseModel):
    table_number: Optional[str] = Field(None, max_length=20)
    capacity:     Optional[int] = Field(None, ge=1)
    section:      Optional[str] = Field(None, max_length=50)
    status:       Optional[str] = None


class CafeTableRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; table_number: str; capacity: int; status: str; section: Optional[str]
    occupied_at: Optional[datetime] = None


class CafeOrderItemCreate(BaseModel):
    item_id:  int
    variant_id: Optional[int] = None  # CafeItemVariant.id — إجباري لو الصنف عنده متغيّرات متاحة
    quantity: int = Field(1, ge=1)
    notes:    Optional[str] = None
    extra_ids: list[int] = Field(default_factory=list)  # CafeMenuItemExtra.id المختارة


class CafeOrderCreate(BaseModel):
    branch_id:      int
    table_id:       Optional[int] = None
    order_type:     str = Field("dine_in", pattern=r"^(dine_in|takeaway|delivery)$")
    notes:          Optional[str] = None
    customer_id:    Optional[int] = None
    payment_method: Optional[str] = Field(None, pattern=r"^(cash|card|wallet)$")
    items:          list[CafeOrderItemCreate] = Field(..., min_length=1)


class CafeOrderItemVoidRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=200)
    # موافقة مدير بالـ PIN — راجع restaurant.schemas.OrderItemVoidRequest
    # لنفس التعليق بالتفصيل (نفس النمط بالظبط في الموديولين).
    approver_user_id: Optional[int] = None
    approver_pin:      Optional[str] = Field(None, pattern=r"^\d{4,6}$")


class CafeOrderItemExtraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:             int
    extra_id:       Optional[int]
    extra_name:     str
    price_addition: Decimal


class CafeOrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; order_id: int; item_id: int; variant_id: Optional[int] = None; name: str
    unit_price: Decimal; quantity: int; notes: Optional[str]; status: str
    extras: list[CafeOrderItemExtraRead] = []
    voided_reason: Optional[str] = None
    voided_by:     Optional[int] = None
    voided_at:     Optional[datetime] = None


class CafeOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; table_id: Optional[int]; order_number: str
    status: str; order_type: str; subtotal: Decimal; vat_amount: Decimal
    service_charge: Decimal; discount_amount: Decimal; total: Decimal
    refunded_amount: Decimal = Decimal("0")
    notes: Optional[str]; waiter_id: Optional[int]
    payment_method: Optional[str] = None
    # #7: guests_count كان مش موجود في CafeOrderRead — بعض الـ Views كانت
    # بتفترضه موجود وتعرض "X غطاء" بشكل غلط. Optional=None يمنع أي crash.
    guests_count: Optional[int] = None
    applied_discount_rule_id: Optional[int] = None
    customer_id: Optional[int] = None
    items: list[CafeOrderItemRead] = []
    created_at: datetime; updated_at: datetime


class CafeOrderStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(held|open|in_kitchen|served|paid|cancelled)$")
    charge_to_room_id: Optional[int] = None
    payment_method: Optional[str] = Field(None, pattern=r"^(cash|card|wallet|room)$")
    # payment_method يتسجّل وقت إتمام الدفع (status=paid) — اختياري في باقي الحالات.


# ── Public (Guest / Marketing site) Schemas — بدون auth ─────────────
# نفس نمط restaurant.PublicMenu* — مقلّصة عمداً، الضيف يشوف بس اللي يحتاجه

class CafePublicMenuExtraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:             int
    name:           str
    name_ar:        Optional[str]
    price_addition: Decimal


class CafePublicMenuExtraGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:         int
    name:       str
    name_ar:    Optional[str]
    min_select: int
    max_select: int
    options:    list[CafePublicMenuExtraRead] = []


class CafePublicMenuVariantRead(BaseModel):
    """للزائر عبر الموقع العام — بدون تكلفة/وصفة، سعر واسم بس."""
    model_config = ConfigDict(from_attributes=True)
    id:           int
    name:         str
    name_ar:      Optional[str]
    price:        Decimal
    is_available: bool


class CafePublicMenuItemRead(BaseModel):
    """للزائر عبر الموقع العام — بدون cost أو بيانات داخلية."""
    model_config = ConfigDict(from_attributes=True)
    id:                  int
    name:                str
    name_ar:             Optional[str]
    price:               Decimal
    is_available:        bool
    preparation_minutes: int
    image_url:           Optional[str]
    category_id:         Optional[int]
    extra_groups:        list[CafePublicMenuExtraGroupRead] = []
    variants:            list[CafePublicMenuVariantRead] = []


class CafePublicMenuCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:      int
    name:    str
    name_ar: Optional[str]


class CafePublicMenuResponse(BaseModel):
    """الرد الكامل على GET /cafe/public/menu — categories + items في طلب واحد."""
    branch_id:  int
    categories: list[CafePublicMenuCategoryRead]
    items:      list[CafePublicMenuItemRead]


# ── Public (Guest QR) Order Schemas — بدون auth ──────────────────────
# نفس نمط restaurant.GuestOrder* بالضبط — الضيف يطلب من طاولة كافيه أو
# شمسية (نفس آلية الترقيم؛ الشمسيات مُمثَّلة كصفوف CafeTable برقم مميز،
# مفيش موديل منفصل — راجع CLAUDE.md §13).

class CafeGuestOrderItemCreate(BaseModel):
    item_id:  int
    variant_id: Optional[int] = None
    quantity: int = Field(1, ge=1)
    notes:    Optional[str] = Field(None, max_length=200)
    extra_ids: list[int] = Field(default_factory=list)


class CafeGuestOrderCreate(BaseModel):
    """الطلب من الضيف عبر QR (طاولة كافيه أو شمسية)."""
    branch_id: int
    table_id:  Optional[int] = None
    notes:     Optional[str] = Field(None, max_length=300)
    items:     list[CafeGuestOrderItemCreate] = Field(..., min_length=1)


class CafeGuestOrderRead(BaseModel):
    """ما يشوفه الضيف بعد تقديم الطلب — بدون بيانات مالية داخلية."""
    order_id:     int
    order_number: str
    status:       str
    total:        Decimal
    items_count:  int
    message:      str


# ─────────────────────── Reporting / Food Cost ────────────────────────
# نفس نمط restaurant.schemas بالضبط — راجع التعليقات هناك للتفاصيل الكاملة.

class CafeFoodCostReportLine(BaseModel):
    """راجع restaurant.schemas.FoodCostReportLine للتبرير الكامل — صف واحد
    لكل "وحدة تقرير" (الصنف الأساسي أو متغيّر منفرد لو موجود)."""
    cafe_item_id:            int
    cafe_item_name:          str
    variant_id:              Optional[int] = None
    has_recipe:              bool
    quantity_sold:           int
    revenue:                 Decimal
    theoretical_unit_cost:   Decimal
    theoretical_total_cost:  Decimal
    food_cost_pct:           Optional[Decimal] = None
    gross_margin_amount:     Decimal
    gross_margin_pct:        Optional[Decimal] = None
    exceeds_threshold:       bool


class CafeCogsTrendPoint(BaseModel):
    date:             date
    revenue:          Decimal
    theoretical_cost: Decimal
    food_cost_pct:    Optional[Decimal] = None


class CafeGrossMarginSummary(BaseModel):
    branch_id:                    int
    date_from:                    date
    date_to:                      date
    threshold_pct:                Decimal
    total_revenue:                Decimal
    total_theoretical_cost:       Decimal
    food_cost_pct:                Optional[Decimal] = None
    gross_margin_amount:          Decimal
    gross_margin_pct:             Optional[Decimal] = None
    items_missing_recipe:         int
    items_missing_recipe_revenue: Decimal


class CafeFoodCostReportResponse(BaseModel):
    lines:   list[CafeFoodCostReportLine]
    alerts:  list[CafeFoodCostReportLine]
    trend:   list[CafeCogsTrendPoint]
    summary: CafeGrossMarginSummary
