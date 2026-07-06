"""app/modules/cafe/schemas.py — Pydantic v2 (نفس نمط restaurant)"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CafeCategoryCreate(BaseModel):
    branch_id: int
    name:       str = Field(..., max_length=100)
    name_ar:    Optional[str] = None
    sort_order: int = 0


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
    linked_product_id:   Optional[int] = None


class CafeItemUpdate(BaseModel):
    name:                Optional[str]     = None
    price:               Optional[Decimal] = None
    cost:                Optional[Decimal] = None
    is_available:        Optional[bool]    = None
    preparation_minutes: Optional[int]     = None
    category_id:         Optional[int]     = None
    linked_product_id:   Optional[int]     = None


class CafeItemRead(CafeItemCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int; created_at: datetime; updated_at: datetime
    extra_groups: list[CafeMenuItemExtraGroupRead] = []


class CafeTableRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; table_number: str; capacity: int; status: str; section: Optional[str]
    occupied_at: Optional[datetime] = None


class CafeOrderItemCreate(BaseModel):
    item_id:  int
    quantity: int = Field(1, ge=1)
    notes:    Optional[str] = None
    extra_ids: list[int] = Field(default_factory=list)  # CafeMenuItemExtra.id المختارة


class CafeOrderCreate(BaseModel):
    branch_id:  int
    table_id:   Optional[int] = None
    order_type: str = Field("dine_in", pattern=r"^(dine_in|takeaway|delivery)$")
    notes:      Optional[str] = None
    customer_id: Optional[int] = None
    items:      list[CafeOrderItemCreate] = Field(..., min_length=1)


class CafeOrderItemVoidRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=200)


class CafeOrderItemExtraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:             int
    extra_id:       Optional[int]
    extra_name:     str
    price_addition: Decimal


class CafeOrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; order_id: int; item_id: int; name: str
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
    customer_id: Optional[int] = None
    items: list[CafeOrderItemRead] = []
    created_at: datetime; updated_at: datetime


class CafeOrderStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(held|open|in_kitchen|served|paid|cancelled)$")
    charge_to_room_id: Optional[int] = None


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
