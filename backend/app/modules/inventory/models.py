"""
app/modules/inventory/models.py
Inventory Module — المخازن وإدارة المخزون
Tables: warehouses, categories, products, stock_movements, purchase_orders, purchase_order_items
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer,
    Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wego_core.models.mixins import TimestampMixin
from app.core.database import Base


class Warehouse(Base, TimestampMixin):
    __tablename__ = "warehouses"

    id:        Mapped[int]         = mapped_column(primary_key=True)
    branch_id: Mapped[int]         = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    name:      Mapped[str]         = mapped_column(String(100))
    name_ar:   Mapped[str | None]  = mapped_column(String(100), nullable=True)
    code:      Mapped[str]         = mapped_column(String(20), unique=True)
    is_active: Mapped[bool]        = mapped_column(Boolean, default=True)
    notes:     Mapped[str | None]  = mapped_column(Text, nullable=True)

    stock_movements: Mapped[list["StockMovement"]] = relationship(
        "StockMovement", back_populates="warehouse", lazy="select"
    )


class Category(Base, TimestampMixin):
    __tablename__ = "inventory_categories"

    id:        Mapped[int]        = mapped_column(primary_key=True)
    branch_id: Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    name:      Mapped[str]        = mapped_column(String(100))
    name_ar:   Mapped[str | None] = mapped_column(String(100), nullable=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_categories.id", ondelete="SET NULL"), nullable=True)

    products: Mapped[list["Product"]] = relationship("Product", back_populates="category", lazy="select")


class Product(Base, TimestampMixin):
    """صنف مخزني — يُستخدم في المطعم والكافيه وغيرها."""
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("branch_id", "sku", name="uq_product_branch_sku"),
    )

    id:              Mapped[int]          = mapped_column(primary_key=True)
    branch_id:       Mapped[int]          = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    category_id:     Mapped[int | None]   = mapped_column(ForeignKey("inventory_categories.id", ondelete="SET NULL"), nullable=True)
    warehouse_id:    Mapped[int | None]   = mapped_column(ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True)
    name:            Mapped[str]          = mapped_column(String(200))
    name_ar:         Mapped[str | None]   = mapped_column(String(200), nullable=True)
    sku:             Mapped[str]          = mapped_column(String(50))
    unit:            Mapped[str]          = mapped_column(String(20), default="piece")
    # piece|kg|liter|box|pack|dozen
    cost_price:      Mapped[Decimal]      = mapped_column(Numeric(10, 2), default=Decimal("0"))
    current_stock:   Mapped[Decimal]      = mapped_column(Numeric(12, 3), default=Decimal("0"))
    min_stock:       Mapped[Decimal]      = mapped_column(Numeric(12, 3), default=Decimal("0"))
    max_stock:       Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    reorder_point:   Mapped[Decimal]      = mapped_column(Numeric(12, 3), default=Decimal("0"))
    is_active:       Mapped[bool]         = mapped_column(Boolean, default=True)
    notes:           Mapped[str | None]   = mapped_column(Text, nullable=True)

    category:  Mapped["Category | None"]      = relationship("Category",  back_populates="products")
    movements: Mapped[list["StockMovement"]]  = relationship("StockMovement", back_populates="product", lazy="select")


class StockMovement(Base, TimestampMixin):
    """حركة المخزون — إدخال، إخراج، تحويل، جرد."""
    __tablename__ = "stock_movements"

    id:             Mapped[int]          = mapped_column(primary_key=True)
    branch_id:      Mapped[int]          = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    product_id:     Mapped[int]          = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    warehouse_id:   Mapped[int]          = mapped_column(ForeignKey("warehouses.id", ondelete="RESTRICT"))
    movement_type:  Mapped[str]          = mapped_column(String(30))
    # purchase_in|consumption|adjustment|transfer_in|transfer_out|spoilage
    quantity:       Mapped[Decimal]      = mapped_column(Numeric(12, 3))   # موجب=دخول، سالب=خروج
    unit_cost:      Mapped[Decimal]      = mapped_column(Numeric(10, 2), default=Decimal("0"))
    reference_type: Mapped[str | None]   = mapped_column(String(30), nullable=True)
    # purchase_order|order|manual|inventory_count
    reference_id:   Mapped[int | None]   = mapped_column(Integer, nullable=True)
    notes:          Mapped[str | None]   = mapped_column(String(300), nullable=True)
    moved_by:       Mapped[int | None]   = mapped_column(Integer, nullable=True)
    moved_at:       Mapped[datetime]     = mapped_column(DateTime)

    product:   Mapped["Product"]   = relationship("Product",   back_populates="movements")
    warehouse: Mapped["Warehouse"] = relationship("Warehouse", back_populates="stock_movements")


class PurchaseOrder(Base, TimestampMixin):
    """أمر شراء."""
    __tablename__ = "purchase_orders"

    id:            Mapped[int]             = mapped_column(primary_key=True)
    branch_id:     Mapped[int]             = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    order_number:  Mapped[str]             = mapped_column(String(30), unique=True)  # PO-20260630-0001
    supplier_name: Mapped[str]             = mapped_column(String(200))
    supplier_phone: Mapped[str | None]     = mapped_column(String(20), nullable=True)
    status:        Mapped[str]             = mapped_column(String(20), default="draft")
    # draft|sent|partial|received|cancelled
    ordered_at:    Mapped[date]            = mapped_column(Date)
    expected_at:   Mapped[date | None]     = mapped_column(Date, nullable=True)
    received_at:   Mapped[date | None]     = mapped_column(Date, nullable=True)
    total_amount:  Mapped[Decimal]         = mapped_column(Numeric(12, 2), default=Decimal("0"))
    notes:         Mapped[str | None]      = mapped_column(Text, nullable=True)

    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        "PurchaseOrderItem", back_populates="purchase_order", lazy="select"
    )


class PurchaseOrderItem(Base, TimestampMixin):
    __tablename__ = "purchase_order_items"

    id:                Mapped[int]     = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int]     = mapped_column(ForeignKey("purchase_orders.id", ondelete="CASCADE"))
    product_id:        Mapped[int]     = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    ordered_qty:       Mapped[Decimal] = mapped_column(Numeric(12, 3))
    received_qty:      Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0"))
    unit_cost:         Mapped[Decimal] = mapped_column(Numeric(10, 2))
    total_cost:        Mapped[Decimal] = mapped_column(Numeric(12, 2))

    purchase_order: Mapped["PurchaseOrder"] = relationship("PurchaseOrder", back_populates="items")


# ── Purchase Request Workflow ──────────────────────────────────────────

class PurchaseRequest(Base, TimestampMixin):
    """طلب شراء — workflow: draft→dept_approved→finance_approved→rejected→converted"""
    __tablename__ = "purchase_requests"

    id:              Mapped[int]          = mapped_column(primary_key=True)
    branch_id:       Mapped[int]          = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    requester_id:    Mapped[int]          = mapped_column(Integer)
    department:      Mapped[str]          = mapped_column(String(100))
    status:          Mapped[str]          = mapped_column(String(30), default="draft")
    # draft|dept_approved|finance_approved|rejected|converted
    notes:           Mapped[str | None]   = mapped_column(String(500), nullable=True)
    rejected_reason: Mapped[str | None]   = mapped_column(String(300), nullable=True)
    total_estimated: Mapped[Decimal]      = mapped_column(Numeric(12, 2), default=Decimal("0"))

    items:     Mapped[list["PurchaseRequestItem"]] = relationship(
        "PurchaseRequestItem", back_populates="request", lazy="select", cascade="all, delete-orphan"
    )
    approvals: Mapped[list["PurchaseApproval"]] = relationship(
        "PurchaseApproval", back_populates="request", lazy="select"
    )


class PurchaseRequestItem(Base, TimestampMixin):
    __tablename__ = "purchase_request_items"

    id:                  Mapped[int]     = mapped_column(primary_key=True)
    request_id:          Mapped[int]     = mapped_column(ForeignKey("purchase_requests.id", ondelete="CASCADE"))
    product_id:          Mapped[int]     = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    quantity_requested:  Mapped[Decimal] = mapped_column(Numeric(10, 3))
    unit:                Mapped[str]     = mapped_column(String(20))
    estimated_unit_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))

    request: Mapped["PurchaseRequest"] = relationship("PurchaseRequest", back_populates="items")


class PurchaseApproval(Base, TimestampMixin):
    __tablename__ = "purchase_approvals"

    id:          Mapped[int]         = mapped_column(primary_key=True)
    request_id:  Mapped[int]         = mapped_column(ForeignKey("purchase_requests.id", ondelete="CASCADE"))
    approver_id: Mapped[int]         = mapped_column(Integer)
    level:       Mapped[str]         = mapped_column(String(20))   # dept|finance
    status:      Mapped[str]         = mapped_column(String(20))   # approved|rejected
    notes:       Mapped[str | None]  = mapped_column(String(300), nullable=True)

    request: Mapped["PurchaseRequest"] = relationship("PurchaseRequest", back_populates="approvals")


# ── Stock Count (Physical Inventory) ──────────────────────────────────

class StockCount(Base, TimestampMixin):
    """جرد المخزون — workflow: draft→submitted→approved→adjustment_posted"""
    __tablename__ = "stock_counts"

    id:           Mapped[int]          = mapped_column(primary_key=True)
    branch_id:    Mapped[int]          = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    warehouse_id: Mapped[int | None]   = mapped_column(ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True)
    count_date:   Mapped[date]         = mapped_column(Date)
    status:       Mapped[str]          = mapped_column(String(30), default="draft")
    # draft|submitted|approved|adjustment_posted
    notes:        Mapped[str | None]   = mapped_column(String(500), nullable=True)
    counted_by:   Mapped[int]          = mapped_column(Integer)
    approved_by:  Mapped[int | None]   = mapped_column(Integer, nullable=True)

    lines: Mapped[list["StockCountLine"]] = relationship(
        "StockCountLine", back_populates="count", lazy="select", cascade="all, delete-orphan"
    )


class StockCountLine(Base, TimestampMixin):
    __tablename__ = "stock_count_lines"

    id:               Mapped[int]     = mapped_column(primary_key=True)
    count_id:         Mapped[int]     = mapped_column(ForeignKey("stock_counts.id", ondelete="CASCADE"))
    product_id:       Mapped[int]     = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    system_quantity:  Mapped[Decimal] = mapped_column(Numeric(10, 3))   # from system at count time
    counted_quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=Decimal("0"))
    variance:         Mapped[Decimal] = mapped_column(Numeric(10, 3), default=Decimal("0"))
    # variance = counted - system

    count: Mapped["StockCount"] = relationship("StockCount", back_populates="lines")
