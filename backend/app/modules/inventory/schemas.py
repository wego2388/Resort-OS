"""app/modules/inventory/schemas.py — Pydantic v2"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class WarehouseCreate(BaseModel):
    branch_id: int
    name:      str = Field(..., max_length=100)
    name_ar:   Optional[str] = None
    code:      str = Field(..., max_length=20)
    notes:     Optional[str] = None


class WarehouseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; name: str; name_ar: Optional[str]
    code: str; is_active: bool; created_at: datetime; updated_at: datetime


class CategoryCreate(BaseModel):
    branch_id: int
    name:      str = Field(..., max_length=100)
    name_ar:   Optional[str] = None
    parent_id: Optional[int] = None


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; name: str; name_ar: Optional[str]
    parent_id: Optional[int]; created_at: datetime


class ProductCreate(BaseModel):
    branch_id:    int
    category_id:  Optional[int] = None
    warehouse_id: Optional[int] = None
    name:         str = Field(..., max_length=200)
    name_ar:      Optional[str] = None
    sku:          str = Field(..., max_length=50)
    unit:         str = Field("piece", pattern=r"^(piece|kg|liter|box|pack|dozen)$")
    cost_price:   Decimal = Field(Decimal("0"), ge=0)
    min_stock:    Decimal = Field(Decimal("0"), ge=0)
    max_stock:    Optional[Decimal] = None
    reorder_point: Decimal = Field(Decimal("0"), ge=0)
    notes:        Optional[str] = None


class ProductUpdate(BaseModel):
    name:         Optional[str]     = None
    name_ar:      Optional[str]     = None
    category_id:  Optional[int]     = None
    warehouse_id: Optional[int]     = None
    cost_price:   Optional[Decimal] = None
    min_stock:    Optional[Decimal] = None
    max_stock:    Optional[Decimal] = None
    reorder_point: Optional[Decimal] = None
    is_active:    Optional[bool]    = None
    notes:        Optional[str]     = None


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; category_id: Optional[int]; warehouse_id: Optional[int]
    name: str; name_ar: Optional[str]; sku: str; unit: str
    cost_price: Decimal; current_stock: Decimal; min_stock: Decimal
    max_stock: Optional[Decimal]; reorder_point: Decimal
    is_active: bool; notes: Optional[str]; created_at: datetime; updated_at: datetime

    @property
    def is_low_stock(self) -> bool:
        return self.current_stock <= self.reorder_point


class StockMovementCreate(BaseModel):
    branch_id:      int
    product_id:     int
    warehouse_id:   int
    movement_type:  str = Field(..., pattern=r"^(purchase_in|consumption|adjustment|transfer_in|transfer_out|spoilage)$")
    quantity:       Decimal  # موجب=دخول، سالب=خروج
    unit_cost:      Decimal = Field(Decimal("0"), ge=0)
    reference_type: Optional[str] = None
    reference_id:   Optional[int] = None
    notes:          Optional[str] = None
    moved_at:       datetime


class StockMovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; product_id: int; warehouse_id: int
    movement_type: str; quantity: Decimal; unit_cost: Decimal
    reference_type: Optional[str]; reference_id: Optional[int]
    notes: Optional[str]; moved_by: Optional[int]; moved_at: datetime; created_at: datetime


class PurchaseOrderItemCreate(BaseModel):
    product_id:  int
    ordered_qty: Decimal = Field(..., gt=0)
    unit_cost:   Decimal = Field(..., ge=0)


class PurchaseOrderCreate(BaseModel):
    branch_id:      int
    supplier_name:  str = Field(..., max_length=200)
    supplier_phone: Optional[str] = None
    ordered_at:     date
    expected_at:    Optional[date] = None
    notes:          Optional[str] = None
    items:          list[PurchaseOrderItemCreate] = Field(..., min_length=1)


class PurchaseOrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; purchase_order_id: int; product_id: int
    ordered_qty: Decimal; received_qty: Decimal; unit_cost: Decimal; total_cost: Decimal


class PurchaseOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; order_number: str; supplier_name: str
    supplier_phone: Optional[str]; status: str; ordered_at: date
    expected_at: Optional[date]; received_at: Optional[date]
    total_amount: Decimal; notes: Optional[str]
    items: list[PurchaseOrderItemRead] = []
    created_at: datetime; updated_at: datetime


class ReceiveItemsRequest(BaseModel):
    """استلام جزئي أو كامل لأمر الشراء."""
    items: list[dict]  # [{"item_id": int, "received_qty": Decimal}]
    warehouse_id: int
    received_at: date


# ── Purchase Request Workflow ─────────────────────────────────────────

class PurchaseRequestItemCreate(BaseModel):
    product_id:          int
    quantity_requested:  Decimal = Field(..., gt=0)
    unit:                str     = Field(..., max_length=20)
    estimated_unit_cost: Decimal = Field(Decimal("0"), ge=0)


class PurchaseRequestCreate(BaseModel):
    branch_id:    int
    requester_id: int
    department:   str = Field(..., max_length=100)
    notes:        Optional[str] = None
    items:        list[PurchaseRequestItemCreate] = Field(..., min_length=1)


class PurchaseRequestItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; request_id: int; product_id: int
    quantity_requested: Decimal; unit: str; estimated_unit_cost: Decimal
    created_at: datetime


class PurchaseApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; request_id: int; approver_id: int
    level: str; status: str; notes: Optional[str]
    created_at: datetime


class PurchaseRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; requester_id: int; department: str
    status: str; notes: Optional[str]; rejected_reason: Optional[str]
    total_estimated: Decimal
    items:     list[PurchaseRequestItemRead] = []
    approvals: list[PurchaseApprovalRead]   = []
    created_at: datetime; updated_at: datetime


class ApproveRequest(BaseModel):
    level: str = Field(..., pattern=r"^(dept|finance)$")
    notes: Optional[str] = None


class RejectRequest(BaseModel):
    level:  str = Field(..., pattern=r"^(dept|finance)$")
    reason: str = Field(..., max_length=300)
    notes:  Optional[str] = None


# ── Stock Count ───────────────────────────────────────────────────────

class StockCountCreate(BaseModel):
    branch_id:    int
    warehouse_id: Optional[int] = None
    count_date:   date
    counted_by:   int
    product_ids:  Optional[list[int]] = None   # None = all active products
    notes:        Optional[str] = None


class StockCountLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; count_id: int; product_id: int
    system_quantity: Decimal; counted_quantity: Decimal; variance: Decimal
    created_at: datetime


class StockCountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; warehouse_id: Optional[int]; count_date: date
    status: str; notes: Optional[str]; counted_by: int; approved_by: Optional[int]
    lines: list[StockCountLineRead] = []
    created_at: datetime; updated_at: datetime


class SubmitStockCountRequest(BaseModel):
    """يحدّث counted_quantity لكل سطر من سطور الجرد."""
    lines: list[dict]  # [{"line_id": int, "counted_quantity": Decimal}]
