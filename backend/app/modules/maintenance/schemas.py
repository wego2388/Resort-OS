"""app/modules/maintenance/schemas.py — Pydantic v2"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Asset ─────────────────────────────────────────────────────────────

class AssetCreate(BaseModel):
    branch_id:      int
    name:           str = Field(..., max_length=200)
    code:           str = Field(..., max_length=50)
    category:       str = Field(..., pattern=r"^(hvac|electrical|plumbing|furniture|vehicle|other)$")
    location:       Optional[str] = Field(None, max_length=200)
    serial_number:  Optional[str] = Field(None, max_length=100)
    purchase_date:  Optional[date] = None
    warranty_until: Optional[date] = None
    notes:          Optional[str] = None
    # ── depreciation basis (اختياري — بدونها الأصل مش مؤهّل للإهلاك الشهري) ──
    purchase_cost:           Optional[Decimal] = Field(None, gt=0)
    salvage_value:           Decimal           = Field(Decimal("0"), ge=0)
    useful_life_years:       Optional[int]     = Field(None, gt=0, le=100)
    depreciation_start_date: Optional[date]    = None


class AssetUpdate(BaseModel):
    name:           Optional[str]  = Field(None, max_length=200)
    category:       Optional[str]  = None
    location:       Optional[str]  = None
    serial_number:  Optional[str]  = None
    warranty_until: Optional[date] = None
    status:         Optional[str]  = Field(None, pattern=r"^(operational|under_maintenance|out_of_service|disposed)$")
    notes:          Optional[str]  = None
    purchase_cost:           Optional[Decimal] = Field(None, gt=0)
    salvage_value:           Optional[Decimal] = Field(None, ge=0)
    useful_life_years:       Optional[int]     = Field(None, gt=0, le=100)
    depreciation_start_date: Optional[date]    = None


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:             int
    branch_id:      int
    name:           str
    code:           str
    category:       str
    location:       Optional[str]
    serial_number:  Optional[str]
    purchase_date:  Optional[date]
    warranty_until: Optional[date]
    status:         str
    notes:          Optional[str]
    purchase_cost:            Optional[Decimal]
    salvage_value:            Decimal
    useful_life_years:        Optional[int]
    depreciation_method:      str
    depreciation_start_date:  Optional[date]
    accumulated_depreciation: Decimal
    created_at:     datetime
    updated_at:     datetime


# ── WorkOrder ─────────────────────────────────────────────────────────

class WorkOrderCreate(BaseModel):
    branch_id:      int
    asset_id:       Optional[int] = None
    title:          str = Field(..., max_length=300)
    description:    Optional[str] = None
    order_type:     str = Field("corrective", pattern=r"^(corrective|preventive|inspection)$")
    priority:       str = Field("medium", pattern=r"^(low|medium|high|critical)$")
    assigned_to:    Optional[int] = None
    scheduled_date: Optional[date] = None
    notes:          Optional[str] = None
    schedule_id:    Optional[int] = None


class WorkOrderUpdate(BaseModel):
    title:          Optional[str]  = Field(None, max_length=300)
    description:    Optional[str]  = None
    priority:       Optional[str]  = Field(None, pattern=r"^(low|medium|high|critical)$")
    status:         Optional[str]  = Field(None, pattern=r"^(open|in_progress|pending_parts|completed|cancelled)$")
    assigned_to:    Optional[int]  = None
    scheduled_date: Optional[date] = None
    labour_hours:   Optional[Decimal] = None
    labour_cost:    Optional[Decimal] = None
    notes:          Optional[str]  = None


class WorkOrderPartCreate(BaseModel):
    """
    product_id: اختياري — لو موجود بيخصم من inventory تلقائياً.
      unit_cost في هذه الحالة بيتملأ من سعر المنتج لو 0.
    لو مفيش product_id: قطعة خارجية — part_name + unit_cost يدوي.
    """
    product_id:  Optional[int]  = None
    part_name:   str = Field(..., max_length=200)
    part_number: Optional[str] = None
    quantity:    Decimal = Field(Decimal("1"), gt=0)
    unit_cost:   Decimal = Field(Decimal("0"), ge=0)


class WorkOrderPartRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:           int
    work_order_id: int
    product_id:   Optional[int] = None
    part_name:    str
    part_number:  Optional[str]
    quantity:     Decimal
    unit_cost:    Decimal
    total_cost:   Decimal
    created_at:   datetime


class WorkOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:             int
    branch_id:      int
    asset_id:       Optional[int]
    order_number:   str
    title:          str
    description:    Optional[str]
    order_type:     str
    schedule_id:    Optional[int]
    priority:       str
    status:         str
    assigned_to:    Optional[int]
    reported_by:    Optional[int]
    scheduled_date: Optional[date]
    completed_at:   Optional[datetime]
    labour_hours:   Decimal
    labour_cost:    Decimal
    parts_cost:     Decimal
    notes:          Optional[str]
    parts:          list[WorkOrderPartRead] = []
    created_at:     datetime
    updated_at:     datetime


# ── PreventiveSchedule ────────────────────────────────────────────────

class PreventiveScheduleCreate(BaseModel):
    branch_id:      int
    asset_id:       int
    title:          str = Field(..., max_length=300)
    frequency_days: int = Field(..., gt=0)
    next_due:       date
    assigned_to:    Optional[int] = None
    checklist:      Optional[str] = None  # JSON string


class PreventiveScheduleUpdate(BaseModel):
    title:          Optional[str]  = None
    frequency_days: Optional[int]  = Field(None, gt=0)
    next_due:       Optional[date] = None
    assigned_to:    Optional[int]  = None
    checklist:      Optional[str]  = None
    is_active:      Optional[bool] = None


class PreventiveScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:             int
    branch_id:      int
    asset_id:       int
    title:          str
    frequency_days: int
    last_done:      Optional[date]
    next_due:       date
    is_active:      bool
    assigned_to:    Optional[int]
    checklist:      Optional[str]
    created_at:     datetime
    updated_at:     datetime
