"""app/modules/hub/schemas.py — Pydantic v2"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ── HubPage ───────────────────────────────────────────────────────────

class HubPageCreate(BaseModel):
    branch_id:    int
    slug:         str = Field(..., max_length=100, pattern=r"^[a-z0-9-]+$")
    title:        str = Field(..., max_length=300)
    title_ar:     Optional[str] = Field(None, max_length=300)
    content:      Optional[str] = None
    content_ar:   Optional[str] = None
    page_type:    str = Field("info", pattern=r"^(info|offer|news|gallery|contact)$")
    meta_title:   Optional[str] = Field(None, max_length=200)
    meta_desc:    Optional[str] = Field(None, max_length=300)
    sort_order:   int = 100


class HubPageUpdate(BaseModel):
    title:        Optional[str] = None
    title_ar:     Optional[str] = None
    content:      Optional[str] = None
    content_ar:   Optional[str] = None
    meta_title:   Optional[str] = None
    meta_desc:    Optional[str] = None
    sort_order:   Optional[int] = None
    is_published: Optional[bool] = None


class HubPageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:           int
    branch_id:    int
    slug:         str
    title:        str
    title_ar:     Optional[str]
    page_type:    str
    is_published: bool
    published_at: Optional[datetime]
    meta_title:   Optional[str]
    meta_desc:    Optional[str]
    sort_order:   int
    created_at:   datetime
    updated_at:   datetime


# ── HubOffer ──────────────────────────────────────────────────────────

class HubOfferCreate(BaseModel):
    branch_id:      int
    title:          str = Field(..., max_length=300)
    title_ar:       Optional[str] = None
    description:    Optional[str] = None
    description_ar: Optional[str] = None
    offer_type:     str = Field(..., pattern=r"^(room|beach|restaurant|package|event)$")
    original_price: Decimal = Field(..., gt=0)
    offer_price:    Decimal = Field(..., gt=0)
    valid_from:     date
    valid_until:    date
    max_bookings:   int = -1
    image_url:      Optional[str] = Field(None, max_length=500)


class HubOfferUpdate(BaseModel):
    title:          Optional[str]     = None
    description:    Optional[str]     = None
    offer_price:    Optional[Decimal] = None
    valid_until:    Optional[date]    = None
    max_bookings:   Optional[int]     = None
    is_active:      Optional[bool]    = None
    image_url:      Optional[str]     = None


class HubOfferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:             int
    branch_id:      int
    title:          str
    title_ar:       Optional[str]
    offer_type:     str
    original_price: Decimal
    offer_price:    Decimal
    valid_from:     date
    valid_until:    date
    max_bookings:   int
    bookings_count: int
    is_active:      bool
    image_url:      Optional[str]
    created_at:     datetime
    updated_at:     datetime


# ── HubOnlineBooking ──────────────────────────────────────────────────

class OnlineBookingCreate(BaseModel):
    branch_id:      int
    offer_id:       Optional[int] = None
    guest_name:     str = Field(..., max_length=200)
    guest_phone:    str = Field(..., max_length=20)
    guest_email:    Optional[str] = Field(None, max_length=150)
    guests_count:   int = Field(1, ge=1)
    requested_date: date
    # بيانات الإقامة — اختيارية للـ lead العادي، إلزامية لو مطلوب PMS booking تلقائي
    check_in:       Optional[date] = None
    check_out:      Optional[date] = None
    room_type_id:   Optional[int]  = None
    adults:         int = Field(1, ge=1)
    notes:          Optional[str] = None
    source:         str = Field("website", pattern=r"^(website|whatsapp|instagram|tiktok|other)$")


class OnlineBookingUpdate(BaseModel):
    status:       Optional[str] = Field(None, pattern=r"^(pending|confirmed|cancelled|no_show)$")
    notes:        Optional[str] = None
    total_amount: Optional[Decimal] = None


class OnlineBookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:             int
    branch_id:      int
    offer_id:       Optional[int]
    guest_name:     str
    guest_phone:    str
    guest_email:    Optional[str]
    guests_count:   int
    requested_date: date
    notes:          Optional[str]
    status:         str
    source:         str
    confirmed_by:   Optional[int]
    confirmed_at:   Optional[datetime]
    total_amount:    Decimal
    check_in:        Optional[date] = None
    check_out:       Optional[date] = None
    room_type_id:    Optional[int]  = None
    adults:          int = 1
    pms_booking_id:  Optional[int]  = None
    created_at:      datetime
    updated_at:      datetime
