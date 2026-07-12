"""app/modules/pms/schemas.py — Pydantic v2"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class RoomTypeCreate(BaseModel):
    branch_id:     int
    name:          str = Field(..., max_length=100)
    name_ar:       Optional[str] = None
    base_rate:     Decimal = Field(..., gt=0)
    max_occupancy: int = Field(2, ge=1)
    amenities:     Optional[str] = None
    is_active:     bool = True


class RoomTypeRead(RoomTypeCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


class RoomCreate(BaseModel):
    branch_id:    int
    room_type_id: int
    name:         str = Field(..., max_length=20)
    floor:        int = 1
    notes:        Optional[str] = None


class RoomRead(RoomCreate):
    model_config = ConfigDict(from_attributes=True)
    id:     int
    status: str
    updated_at: datetime


class RoomStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(available|occupied|reserved|maintenance|checkout_pending)$")
    notes:  Optional[str] = None


class BookingCreate(BaseModel):
    branch_id:         int
    guest_name:        str = Field(..., max_length=200)
    guest_phone:       Optional[str] = Field(None, max_length=20)
    guest_email:       Optional[str] = Field(None, max_length=100)
    guest_national_id: Optional[str] = Field(None, max_length=20)
    check_in:          date
    check_out:         date
    adults:            int = Field(1, ge=1)
    children:          int = Field(0, ge=0)
    source:            str = Field("direct", pattern=r"^(direct|online|b2b|phone)$")
    room_ids:          list[int] = Field(..., min_length=1)
    notes:             Optional[str] = None
    customer_id:       Optional[int] = None
    # خطة أسعار موسمية اختيارية — لو اتبعتت، services.create_booking بتتحقق
    # إنها سارية للفترة/الفرع المطلوبين وتطبّق سعرها بدل base_rate الخام
    # (على الغرف اللي نوعها متوافق مع room_type_id بتاع الخطة، لو محدد).
    rate_plan_id:      Optional[int] = None


class BookingRoomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:           int
    room_id:      int
    daily_rate:   Decimal
    nights:       int
    total:        Decimal
    rate_plan_id: Optional[int] = None


class BookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:               int
    branch_id:        int
    booking_number:   str
    guest_name:       str
    guest_phone:      Optional[str]
    guest_email:      Optional[str]
    check_in:         date
    check_out:        date
    adults:           int
    children:         int
    status:           str
    source:           str
    folio_id:         Optional[int]
    customer_id:      Optional[int] = None
    total_rate:         Decimal
    extra_charge:       Decimal = Decimal("0")
    notes:              Optional[str]
    early_checkin_at:   Optional[datetime] = None
    late_checkout_at:   Optional[datetime] = None
    rooms:              list[BookingRoomRead] = []
    created_at:         datetime
    updated_at:         datetime


class BookingStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(confirmed|checked_in|checked_out|cancelled|no_show)$")


class EarlyLateRequest(BaseModel):
    """طلب وصول مبكر أو مغادرة متأخرة.
    charge: رسوم إضافية بالجنيه — 0 لو مجاني أو عرض ترحيبي.
    """
    early_checkin_at:  Optional[datetime] = None
    late_checkout_at:  Optional[datetime] = None
    charge:            Decimal = Field(Decimal("0"), ge=0)
    notes:             Optional[str] = Field(None, max_length=500)


class HousekeepingTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:           int
    branch_id:    int
    room_id:      int
    assigned_to:  Optional[int]
    task_type:    str
    status:       str
    priority:     str
    notes:        Optional[str]
    started_at:   Optional[datetime]
    completed_at: Optional[datetime]
    created_at:   datetime


class HousekeepingTaskStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(dirty|cleaning|inspecting|available)$")
    notes:  Optional[str] = None
    # wagdy.md P-12: assigned_to كان عمود حقيقي في الموديل وبيتعرض في
    # الفرونت إند، بس مفيش أي طريقة تحدّده — المشرف كان مضطر يبلّغ الموظف
    # شفهيًا بدل ما يعيّنه من الشاشة نفسها.
    assigned_to: Optional[int] = None


class RatePlanCreate(BaseModel):
    branch_id:            int
    room_type_id:         Optional[int] = None
    name:                 str = Field(..., max_length=100)
    name_ar:              Optional[str] = None
    base_rate_override:   Optional[Decimal] = Field(None, gt=0)
    rate_multiplier:      Decimal = Field(Decimal("1.0000"), gt=0)
    valid_from:           date
    valid_until:          date
    seasonal_adjustments: Optional[str] = None
    min_nights:           int = Field(1, ge=1)
    is_active:            bool = True


class RatePlanUpdate(BaseModel):
    room_type_id:         Optional[int] = None
    name:                 Optional[str] = Field(None, max_length=100)
    name_ar:              Optional[str] = None
    base_rate_override:   Optional[Decimal] = Field(None, gt=0)
    rate_multiplier:      Optional[Decimal] = Field(None, gt=0)
    valid_from:           Optional[date] = None
    valid_until:          Optional[date] = None
    seasonal_adjustments: Optional[str] = None
    min_nights:           Optional[int] = Field(None, ge=1)
    is_active:            Optional[bool] = None
    # is_active=False هو طريقة إلغاء تفعيل الخطة — مفيش endpoint منفصل،
    # نفس نمط MenuItem.is_available/is_active في باقي المشروع.


class RatePlanRead(RatePlanCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


class NightAuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:              int
    branch_id:       int
    audit_date:      date
    occupied_rooms:  int
    total_rooms:     int
    occupancy_pct:   Decimal
    room_revenue:    Decimal
    no_shows:        int
    checkouts_today: int
    checkins_today:  int
    status:          str
    completed_at:    Optional[datetime]
    gm_notified:     bool
    created_at:      datetime
