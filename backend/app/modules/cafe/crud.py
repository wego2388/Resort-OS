"""app/modules/cafe/crud.py"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.modules.cafe.models import CafeCategory, CafeItem, CafeOrder, CafeOrderItem, CafeTable
from app.modules.cafe.schemas import CafeCategoryCreate, CafeItemCreate, CafeItemUpdate, CafeOrderCreate


def list_categories(db: Session, branch_id: int) -> list[CafeCategory]:
    return db.query(CafeCategory).filter(
        CafeCategory.branch_id == branch_id, CafeCategory.is_active.is_(True)
    ).order_by(CafeCategory.sort_order).all()


def create_category(db: Session, data: CafeCategoryCreate) -> CafeCategory:
    obj = CafeCategory(**data.model_dump())
    db.add(obj); db.flush(); return obj


def get_item(db: Session, item_id: int) -> Optional[CafeItem]:
    return db.query(CafeItem).filter(CafeItem.id == item_id).first()


def list_items(db: Session, branch_id: int, category_id: Optional[int] = None,
               available_only: bool = True) -> list[CafeItem]:
    q = db.query(CafeItem).filter(CafeItem.branch_id == branch_id)
    if available_only:
        q = q.filter(CafeItem.is_available.is_(True))
    if category_id:
        q = q.filter(CafeItem.category_id == category_id)
    return q.order_by(CafeItem.name).all()


def create_item(db: Session, data: CafeItemCreate) -> CafeItem:
    obj = CafeItem(**data.model_dump())
    db.add(obj); db.flush(); return obj


def update_item(db: Session, item: CafeItem, data: CafeItemUpdate) -> CafeItem:
    for f, v in data.model_dump(exclude_unset=True).items():
        setattr(item, f, v)
    db.flush(); return item


def list_tables(db: Session, branch_id: int) -> list[CafeTable]:
    return db.query(CafeTable).filter(CafeTable.branch_id == branch_id).order_by(CafeTable.table_number).all()


def get_order(db: Session, order_id: int) -> Optional[CafeOrder]:
    return db.query(CafeOrder).filter(CafeOrder.id == order_id).first()


def list_orders(
    db: Session, branch_id: int,
    status: Optional[str] = None,
    order_date: Optional[date] = None,
    skip: int = 0, limit: int = 50,
) -> tuple[list[CafeOrder], int]:
    q = db.query(CafeOrder).filter(CafeOrder.branch_id == branch_id)
    if status:
        q = q.filter(CafeOrder.status == status)
    if order_date:
        q = q.filter(CafeOrder.created_at.between(
            datetime.combine(order_date, datetime.min.time()),
            datetime.combine(order_date, datetime.max.time()),
        ))
    total = q.count()
    return q.order_by(CafeOrder.created_at.desc()).offset(skip).limit(limit).all(), total


def _next_order_number(db: Session, branch_id: int) -> str:
    today = datetime.utcnow().strftime("%Y%m%d")
    prefix = f"CAF-{today}-"
    count = db.query(CafeOrder).filter(
        CafeOrder.order_number.like(f"{prefix}%")
    ).count()
    return f"{prefix}{count + 1:04d}"


def create_order(
    db: Session, branch_id: int, order_type: str,
    table_id: Optional[int], notes: Optional[str],
    subtotal: Decimal, vat_amount: Decimal, service_charge: Decimal,
    total: Decimal, waiter_id: Optional[int], items_data: list[dict],
) -> CafeOrder:
    order = CafeOrder(
        branch_id=branch_id,
        order_number=_next_order_number(db, branch_id),
        order_type=order_type, table_id=table_id, notes=notes,
        subtotal=subtotal, vat_amount=vat_amount,
        service_charge=service_charge, total=total, waiter_id=waiter_id,
    )
    db.add(order); db.flush()
    for d in items_data:
        db.add(CafeOrderItem(order_id=order.id, **d))
    db.flush(); return order


def update_order_status(db: Session, order: CafeOrder, status: str) -> CafeOrder:
    order.status = status; db.flush(); return order
