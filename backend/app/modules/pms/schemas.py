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

    def validate_dates(self) -> None:
        if self.check_out <= self.check_in:
            raise ValueError("check_out يجب أن يكون بعد check_in")


class BookingRoomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:         int
    room_id:    int
    daily_rate: Decimal
    nights:     int
    total:      Decimal


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
    total_rate:       Decimal
    notes:            Optional[str]
    rooms:            list[BookingRoomRead] = []
    created_at:       datetime
    updated_at:       datetime


class BookingStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(confirmed|checked_in|checked_out|cancelled|no_show)$")


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
