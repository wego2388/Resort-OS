"""app/modules/inventory/crud.py"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.modules.inventory.models import (
    Category, Product, PurchaseOrder, PurchaseOrderItem,
    PurchaseRequest, PurchaseRequestItem, PurchaseApproval,
    StockCount, StockMovement, Warehouse,
)
from app.modules.inventory.schemas import (
    CategoryCreate, ProductCreate, ProductUpdate,
    PurchaseOrderCreate, StockMovementCreate, WarehouseCreate,
)


# ── Warehouse ─────────────────────────────────────────────────────────

def get_warehouse(db: Session, wh_id: int) -> Optional[Warehouse]:
    return db.query(Warehouse).filter(Warehouse.id == wh_id).first()


def list_warehouses(db: Session, branch_id: int) -> list[Warehouse]:
    return db.query(Warehouse).filter(
        Warehouse.branch_id == branch_id, Warehouse.is_active.is_(True)
    ).order_by(Warehouse.name).all()


def create_warehouse(db: Session, data: WarehouseCreate) -> Warehouse:
    obj = Warehouse(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


# ── Category ──────────────────────────────────────────────────────────

def list_categories(db: Session, branch_id: int) -> list[Category]:
    return db.query(Category).filter(Category.branch_id == branch_id).order_by(Category.name).all()


def create_category(db: Session, data: CategoryCreate) -> Category:
    obj = Category(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


# ── Product ───────────────────────────────────────────────────────────

def get_product(db: Session, product_id: int) -> Optional[Product]:
    return db.query(Product).filter(Product.id == product_id).first()


def get_product_by_sku(db: Session, branch_id: int, sku: str) -> Optional[Product]:
    return db.query(Product).filter(Product.branch_id == branch_id, Product.sku == sku).first()


def list_products(
    db: Session,
    branch_id: int,
    category_id: Optional[int] = None,
    low_stock_only: bool = False,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Product], int]:
    q = db.query(Product).filter(Product.branch_id == branch_id, Product.is_active.is_(True))
    if category_id:
        q = q.filter(Product.category_id == category_id)
    if low_stock_only:
        q = q.filter(Product.current_stock <= Product.reorder_point)
    if search:
        like = f"%{search}%"
        q = q.filter(Product.name.ilike(like) | Product.sku.ilike(like))
    total = q.count()
    items = q.order_by(Product.name).offset(skip).limit(limit).all()
    return items, total


def get_products_by_ids(db: Session, branch_id: int, product_ids: list[int]) -> list[Product]:
    return (
        db.query(Product)
        .filter(Product.branch_id == branch_id, Product.id.in_(product_ids))
        .order_by(Product.name)
        .all()
    )


def create_product(db: Session, data: ProductCreate) -> Product:
    obj = Product(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


def update_product(db: Session, product: Product, data: ProductUpdate) -> Product:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.flush()
    return product


def adjust_stock(db: Session, product: Product, delta: Decimal) -> Product:
    """يُحدّث current_stock بالفرق — موجب=إضافة، سالب=خصم."""
    product.current_stock = max(Decimal("0"), product.current_stock + delta)
    db.flush()
    return product


# ── StockMovement ─────────────────────────────────────────────────────

def create_movement(db: Session, data: StockMovementCreate, moved_by: int) -> StockMovement:
    obj = StockMovement(**data.model_dump(), moved_by=moved_by)
    db.add(obj)
    db.flush()
    return obj


def list_movements(
    db: Session,
    branch_id: int,
    product_id: Optional[int] = None,
    movement_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[StockMovement], int]:
    q = db.query(StockMovement).filter(StockMovement.branch_id == branch_id)
    if product_id:
        q = q.filter(StockMovement.product_id == product_id)
    if movement_type:
        q = q.filter(StockMovement.movement_type == movement_type)
    total = q.count()
    items = q.order_by(StockMovement.moved_at.desc()).offset(skip).limit(limit).all()
    return items, total


# ── PurchaseOrder ─────────────────────────────────────────────────────

def _next_po_number(db: Session) -> str:
    today = datetime.utcnow().strftime("%Y%m%d")
    count = db.query(PurchaseOrder).filter(
        PurchaseOrder.order_number.like(f"PO-{today}-%")
    ).count()
    return f"PO-{today}-{count + 1:04d}"


def get_purchase_order(db: Session, po_id: int) -> Optional[PurchaseOrder]:
    return db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()


def list_purchase_orders(
    db: Session,
    branch_id: int,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[PurchaseOrder], int]:
    q = db.query(PurchaseOrder).filter(PurchaseOrder.branch_id == branch_id)
    if status:
        q = q.filter(PurchaseOrder.status == status)
    total = q.count()
    items = q.order_by(PurchaseOrder.ordered_at.desc()).offset(skip).limit(limit).all()
    return items, total


def create_purchase_order(db: Session, data: PurchaseOrderCreate) -> PurchaseOrder:
    items_data = data.items
    po_data = data.model_dump(exclude={"items"})
    po = PurchaseOrder(**po_data, order_number=_next_po_number(db), total_amount=Decimal("0"))
    db.add(po)
    db.flush()

    total = Decimal("0")
    for item in items_data:
        line_total = item.ordered_qty * item.unit_cost
        poi = PurchaseOrderItem(
            purchase_order_id=po.id,
            product_id=item.product_id,
            ordered_qty=item.ordered_qty,
            received_qty=Decimal("0"),
            unit_cost=item.unit_cost,
            total_cost=line_total,
        )
        db.add(poi)
        total += line_total

    po.total_amount = total
    db.flush()
    return po


def receive_purchase_order(
    db: Session,
    po: PurchaseOrder,
    received_items: list[dict],
    warehouse_id: int,
    received_at,
    received_by: int,
) -> PurchaseOrder:
    """يُسجّل استلام البضاعة ويُحدّث المخزون."""
    all_received = True
    for item_data in received_items:
        item = db.query(PurchaseOrderItem).filter(
            PurchaseOrderItem.id == item_data["item_id"],
            PurchaseOrderItem.purchase_order_id == po.id,
        ).first()
        if not item:
            continue
        qty = Decimal(str(item_data["received_qty"]))
        item.received_qty += qty

        # حركة مخزون
        mov = StockMovement(
            branch_id=po.branch_id,
            product_id=item.product_id,
            warehouse_id=warehouse_id,
            movement_type="purchase_in",
            quantity=qty,
            unit_cost=item.unit_cost,
            reference_type="purchase_order",
            reference_id=po.id,
            moved_by=received_by,
            moved_at=datetime.combine(received_at, datetime.min.time()) if hasattr(received_at, 'year') else datetime.utcnow(),
        )
        db.add(mov)

        # تحديث المخزون + متوسط التكلفة المتحرك
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if product:
            old_stock = product.current_stock
            old_cost  = product.cost_price or Decimal("0")
            if old_stock + qty > 0:
                product.cost_price = (
                    (old_stock * old_cost + qty * item.unit_cost) / (old_stock + qty)
                ).quantize(Decimal("0.0001"))
            product.current_stock += qty

        if item.received_qty < item.ordered_qty:
            all_received = False

    po.status = "received" if all_received else "partial"
    po.received_at = received_at
    db.flush()
    return po


# ── PurchaseRequest ───────────────────────────────────────────────────

def get_purchase_request(db: Session, request_id: int) -> Optional[PurchaseRequest]:
    return db.query(PurchaseRequest).filter(PurchaseRequest.id == request_id).first()


def list_purchase_requests(
    db: Session,
    branch_id: int,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[PurchaseRequest], int]:
    q = db.query(PurchaseRequest).filter(PurchaseRequest.branch_id == branch_id)
    if status:
        q = q.filter(PurchaseRequest.status == status)
    total = q.count()
    items = q.order_by(PurchaseRequest.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def create_purchase_request_record(
    db: Session,
    branch_id: int,
    requester_id: int,
    department: str,
    notes: Optional[str],
    total_estimated: Decimal,
) -> PurchaseRequest:
    pr = PurchaseRequest(
        branch_id=branch_id,
        requester_id=requester_id,
        department=department,
        notes=notes,
        total_estimated=total_estimated,
        status="draft",
    )
    db.add(pr)
    db.flush()
    return pr


def create_pr_item(
    db: Session,
    request_id: int,
    product_id: int,
    quantity_requested: Decimal,
    unit: str,
    estimated_unit_cost: Decimal,
) -> PurchaseRequestItem:
    item = PurchaseRequestItem(
        request_id=request_id,
        product_id=product_id,
        quantity_requested=quantity_requested,
        unit=unit,
        estimated_unit_cost=estimated_unit_cost,
    )
    db.add(item)
    db.flush()
    return item


def update_pr_status(
    db: Session,
    request: PurchaseRequest,
    new_status: str,
    rejected_reason: Optional[str] = None,
) -> PurchaseRequest:
    request.status = new_status
    if rejected_reason is not None:
        request.rejected_reason = rejected_reason
    db.flush()
    return request


def create_approval(
    db: Session,
    request_id: int,
    approver_id: int,
    level: str,
    approval_status: str,
    notes: Optional[str] = None,
) -> PurchaseApproval:
    approval = PurchaseApproval(
        request_id=request_id,
        approver_id=approver_id,
        level=level,
        status=approval_status,
        notes=notes,
    )
    db.add(approval)
    db.flush()
    return approval


# ── StockCount ────────────────────────────────────────────────────────

def get_stock_count(db: Session, count_id: int) -> Optional[StockCount]:
    return db.query(StockCount).filter(StockCount.id == count_id).first()


def list_stock_counts(
    db: Session,
    branch_id: int,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[StockCount], int]:
    q = db.query(StockCount).filter(StockCount.branch_id == branch_id)
    if status:
        q = q.filter(StockCount.status == status)
    total = q.count()
    items = q.order_by(StockCount.count_date.desc()).offset(skip).limit(limit).all()
    return items, total
