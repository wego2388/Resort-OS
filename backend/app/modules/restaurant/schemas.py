"""app/modules/restaurant/schemas.py — Pydantic v2"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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


class MenuItemRead(MenuItemCreate):
    model_config = ConfigDict(from_attributes=True)
    id:           int
    created_at:   datetime
    updated_at:   datetime
    extra_groups: list[MenuItemExtraGroupRead] = []


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
