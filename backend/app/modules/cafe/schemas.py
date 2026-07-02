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


class CafeItemUpdate(BaseModel):
    name:                Optional[str]     = None
    price:               Optional[Decimal] = None
    cost:                Optional[Decimal] = None
    is_available:        Optional[bool]    = None
    preparation_minutes: Optional[int]     = None
    category_id:         Optional[int]     = None


class CafeItemRead(CafeItemCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int; created_at: datetime; updated_at: datetime


class CafeTableRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; table_number: str; capacity: int; status: str; section: Optional[str]


class CafeOrderItemCreate(BaseModel):
    item_id:  int
    quantity: int = Field(1, ge=1)
    notes:    Optional[str] = None


class CafeOrderCreate(BaseModel):
    branch_id:  int
    table_id:   Optional[int] = None
    order_type: str = Field("dine_in", pattern=r"^(dine_in|takeaway|delivery)$")
    notes:      Optional[str] = None
    items:      list[CafeOrderItemCreate] = Field(..., min_length=1)


class CafeOrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; order_id: int; item_id: int; name: str
    unit_price: Decimal; quantity: int; notes: Optional[str]; status: str


class CafeOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; table_id: Optional[int]; order_number: str
    status: str; order_type: str; subtotal: Decimal; vat_amount: Decimal
    service_charge: Decimal; discount_amount: Decimal; total: Decimal
    notes: Optional[str]; waiter_id: Optional[int]
    items: list[CafeOrderItemRead] = []
    created_at: datetime; updated_at: datetime


class CafeOrderStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(open|in_kitchen|served|paid|cancelled)$")
