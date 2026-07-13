"""app/modules/dining/crud.py — CRUD خالص (DB فقط، لا HTTPException، لا business logic).

يدمج restaurant/crud.py + cafe/crud.py — نفس المنطق بالظبط، outlet_id بدل
الفصل بين موديولين. راجع CLAUDE.md §4 لقاعدة الطبقات الحرفية.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.resort_os.timezone_utils import local_date_to_utc_range
from app.modules.dining.models import (
    DiningCategory, DiningItem, DiningItemExtra, DiningItemExtraGroup,
    DiningItemRecipeLine, DiningItemVariant, DiningItemVariantRecipeLine,
    DiningKDSScreen, DiningKitchenTicket, DiningOrder, DiningOrderItem,
    DiningOrderItemExtra, VenueTable, Outlet,
)
from app.modules.dining.schemas import (
    DiningCategoryCreate, DiningItemCreate, DiningItemExtraGroupCreate,
    DiningItemRecipeLineCreate, DiningItemRecipeLineUpdate, DiningItemUpdate,
    DiningItemVariantCreate, DiningItemVariantRecipeLineCreate,
    DiningItemVariantRecipeLineUpdate, DiningItemVariantUpdate,
    OutletCreate, OutletUpdate,
)


# ── Outlet ────────────────────────────────────────────────────────────

def list_outlets(db: Session, branch_id: int, active_only: bool = False) -> list[Outlet]:
    q = db.query(Outlet).filter(Outlet.branch_id == branch_id)
    if active_only:
        q = q.filter(Outlet.is_active.is_(True))
    return q.order_by(Outlet.name).all()


def get_outlet(db: Session, outlet_id: int) -> Optional[Outlet]:
    return db.query(Outlet).filter(Outlet.id == outlet_id).first()


def create_outlet(db: Session, data: OutletCreate) -> Outlet:
    obj = Outlet(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


def update_outlet(db: Session, outlet: Outlet, data: OutletUpdate) -> Outlet:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(outlet, field, value)
    db.flush()
    return outlet


# ── DiningCategory ───────────────────────────────────────────────────

def list_categories(db: Session, outlet_id: int) -> list[DiningCategory]:
    return (
        db.query(DiningCategory)
        .filter(DiningCategory.outlet_id == outlet_id, DiningCategory.is_active.is_(True))
        .order_by(DiningCategory.sort_order)
        .all()
    )


def create_category(db: Session, data: DiningCategoryCreate) -> DiningCategory:
    obj = DiningCategory(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


def update_category(db: Session, category: DiningCategory, data) -> DiningCategory:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(category, field, value)
    db.flush()
    return category


def get_category(db: Session, category_id: int) -> Optional[DiningCategory]:
    return db.query(DiningCategory).filter(DiningCategory.id == category_id).first()


def delete_category(db: Session, category_id: int) -> bool:
    obj = get_category(db, category_id)
    if not obj:
        return False
    db.delete(obj)
    db.flush()
    return True


# ── DiningItem ────────────────────────────────────────────────────────

def get_item(db: Session, item_id: int) -> Optional[DiningItem]:
    return db.query(DiningItem).filter(DiningItem.id == item_id).first()


def list_items(
    db: Session,
    outlet_id: int,
    category_id: Optional[int] = None,
    available_only: bool = True,
) -> list[DiningItem]:
    q = db.query(DiningItem).filter(DiningItem.outlet_id == outlet_id)
    if available_only:
        q = q.filter(DiningItem.is_available.is_(True))
    if category_id is not None:
        q = q.filter(DiningItem.category_id == category_id)
    return q.order_by(DiningItem.name).all()


def create_item(db: Session, data: DiningItemCreate) -> DiningItem:
    obj = DiningItem(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


def update_item(db: Session, item: DiningItem, data: DiningItemUpdate) -> DiningItem:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.flush()
    return item


def delete_item(db: Session, item_id: int) -> bool:
    item = get_item(db, item_id)
    if not item:
        return False
    db.delete(item)
    db.flush()
    return True


def create_extra_group(db: Session, item_id: int, data: DiningItemExtraGroupCreate) -> DiningItemExtraGroup:
    group = DiningItemExtraGroup(
        item_id=item_id,
        name=data.name,
        name_ar=data.name_ar,
        group_type=data.group_type,
        min_select=data.min_select,
        max_select=data.max_select,
        sort_order=data.sort_order,
    )
    db.add(group)
    db.flush()
    for opt in data.options:
        db.add(DiningItemExtra(group_id=group.id, **opt.model_dump()))
    db.flush()
    return group


def delete_extra_group(db: Session, group_id: int) -> bool:
    group = db.query(DiningItemExtraGroup).filter(DiningItemExtraGroup.id == group_id).first()
    if not group:
        return False
    db.delete(group)
    db.flush()
    return True


# ── Recipe / BOM ──────────────────────────────────────────────────────

def get_recipe_line(db: Session, line_id: int) -> Optional[DiningItemRecipeLine]:
    return db.query(DiningItemRecipeLine).filter(DiningItemRecipeLine.id == line_id).first()


def create_recipe_line(db: Session, item_id: int, data: DiningItemRecipeLineCreate) -> DiningItemRecipeLine:
    line = DiningItemRecipeLine(item_id=item_id, **data.model_dump())
    db.add(line)
    db.flush()
    return line


def update_recipe_line(db: Session, line: DiningItemRecipeLine, data: DiningItemRecipeLineUpdate) -> DiningItemRecipeLine:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(line, field, value)
    db.flush()
    return line


def delete_recipe_line(db: Session, line_id: int) -> bool:
    line = get_recipe_line(db, line_id)
    if not line:
        return False
    db.delete(line)
    db.flush()
    return True


# ── Variants ──────────────────────────────────────────────────────────

def get_variant(db: Session, variant_id: int) -> Optional[DiningItemVariant]:
    return db.query(DiningItemVariant).filter(DiningItemVariant.id == variant_id).first()


def create_variant(db: Session, item_id: int, data: DiningItemVariantCreate) -> DiningItemVariant:
    variant = DiningItemVariant(item_id=item_id, **data.model_dump())
    db.add(variant)
    db.flush()
    return variant


def update_variant(db: Session, variant: DiningItemVariant, data: DiningItemVariantUpdate) -> DiningItemVariant:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(variant, field, value)
    db.flush()
    return variant


def delete_variant(db: Session, variant_id: int) -> bool:
    variant = get_variant(db, variant_id)
    if not variant:
        return False
    db.delete(variant)
    db.flush()
    return True


def get_variant_recipe_line(db: Session, line_id: int) -> Optional[DiningItemVariantRecipeLine]:
    return db.query(DiningItemVariantRecipeLine).filter(DiningItemVariantRecipeLine.id == line_id).first()


def create_variant_recipe_line(db: Session, variant_id: int, data: DiningItemVariantRecipeLineCreate) -> DiningItemVariantRecipeLine:
    line = DiningItemVariantRecipeLine(variant_id=variant_id, **data.model_dump())
    db.add(line)
    db.flush()
    return line


def update_variant_recipe_line(db: Session, line: DiningItemVariantRecipeLine, data: DiningItemVariantRecipeLineUpdate) -> DiningItemVariantRecipeLine:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(line, field, value)
    db.flush()
    return line


def delete_variant_recipe_line(db: Session, line_id: int) -> bool:
    line = get_variant_recipe_line(db, line_id)
    if not line:
        return False
    db.delete(line)
    db.flush()
    return True


# ── VenueTable ───────────────────────────────────────────────────────

def list_tables(db: Session, outlet_id: int) -> list[VenueTable]:
    return (
        db.query(VenueTable)
        .filter(VenueTable.outlet_id == outlet_id)
        .order_by(VenueTable.table_number)
        .all()
    )


def get_table(db: Session, table_id: int) -> Optional[VenueTable]:
    return db.query(VenueTable).filter(VenueTable.id == table_id).first()


def create_table(db: Session, data) -> VenueTable:
    table = VenueTable(**data.model_dump())
    db.add(table)
    db.flush()
    return table


def update_table(db: Session, table: VenueTable, data) -> VenueTable:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(table, field, value)
    db.flush()
    return table


def update_table_grid(db: Session, table: VenueTable, grid_row: Optional[int], grid_col: Optional[int]) -> VenueTable:
    table.grid_row = grid_row
    table.grid_col = grid_col
    db.flush()
    return table


def delete_table(db: Session, table_id: int) -> bool:
    table = get_table(db, table_id)
    if not table:
        return False
    db.delete(table)
    db.flush()
    return True


def update_table_status(db: Session, table: VenueTable, status: str) -> VenueTable:
    table.status = status
    table.occupied_at = datetime.utcnow() if status == "occupied" else None
    db.flush()
    return table


def get_active_order_for_table(
    db: Session, table_id: int, exclude_order_id: Optional[int] = None,
) -> Optional[DiningOrder]:
    """أي طلب غير مقفول (مش paid/cancelled) مرتبط بالطاولة دي حاليًا — يُستخدم
    للتحقق إن الطاولة "مشغولة بطلب آخر" قبل نقل طلب ليها. راجع
    restaurant.crud.get_active_order_for_table — نفس المنطق بالظبط."""
    q = db.query(DiningOrder).filter(
        DiningOrder.table_id == table_id,
        DiningOrder.status.notin_(("paid", "cancelled")),
    )
    if exclude_order_id is not None:
        q = q.filter(DiningOrder.id != exclude_order_id)
    return q.first()


# ── Order ─────────────────────────────────────────────────────────────

def get_order(db: Session, order_id: int) -> Optional[DiningOrder]:
    return db.query(DiningOrder).filter(DiningOrder.id == order_id).first()


def get_order_by_local_id(db: Session, local_id: str) -> Optional[DiningOrder]:
    return db.query(DiningOrder).filter(DiningOrder.client_local_id == local_id).first()


def list_orders(
    db: Session,
    branch_id: int,
    outlet_id: Optional[int] = None,
    status: Optional[str] = None,
    order_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[DiningOrder], int]:
    q = db.query(DiningOrder).filter(DiningOrder.branch_id == branch_id)
    if outlet_id is not None:
        q = q.filter(DiningOrder.outlet_id == outlet_id)
    if status:
        q = q.filter(DiningOrder.status == status)
    if order_date:
        start, end = local_date_to_utc_range(order_date, settings.TIMEZONE)
        q = q.filter(DiningOrder.created_at.between(start, end))
    total = q.count()
    items = q.order_by(DiningOrder.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def generate_order_number(db: Session, branch_id: int) -> str:
    """رقم الطلب بتوقيت المنتجع (Africa/Cairo) — نفس منطق
    restaurant.crud.generate_order_number بالظبط، مشترك بين كل الـ outlets
    في الفرع (نفس sequence، زي ما كان restaurant/cafe منفصلين قبل كده بس
    ORD- prefix واحد الآن)."""
    from app.resort_os.timezone_utils import local_now  # noqa: PLC0415
    today_str = local_now(settings.TIMEZONE).strftime("%Y%m%d")
    prefix = f"ORD-{today_str}-"
    count = (
        db.query(DiningOrder)
        .filter(DiningOrder.order_number.like(f"{prefix}%"))
        .count()
    )
    return f"{prefix}{count + 1:04d}"


def create_order_with_items(
    db: Session,
    branch_id: int,
    outlet_id: int,
    order_number: str,
    order_type: str,
    table_id: Optional[int],
    guests_count: int,
    notes: Optional[str],
    subtotal: "Decimal",
    vat_amount: "Decimal",
    service_charge: "Decimal",
    total: "Decimal",
    waiter_id: Optional[int],
    items_data: list[dict],
    client_local_id: Optional[str] = None,
    status: str = "open",
    customer_id: Optional[int] = None,
    payment_method: Optional[str] = None,
    discount_amount: "Decimal | None" = None,
) -> DiningOrder:
    order = DiningOrder(
        branch_id=branch_id,
        outlet_id=outlet_id,
        order_number=order_number,
        order_type=order_type,
        table_id=table_id,
        guests_count=guests_count,
        notes=notes,
        subtotal=subtotal,
        vat_amount=vat_amount,
        service_charge=service_charge,
        total=total,
        waiter_id=waiter_id,
        client_local_id=client_local_id,
        status=status,
        customer_id=customer_id,
        payment_method=payment_method,
        discount_amount=discount_amount if discount_amount is not None else Decimal("0"),
    )
    db.add(order)
    db.flush()

    for item_d in items_data:
        extras = item_d.pop("extras", [])
        order_item = DiningOrderItem(order_id=order.id, **item_d)
        db.add(order_item)
        db.flush()
        for extra_d in extras:
            db.add(DiningOrderItemExtra(order_item_id=order_item.id, **extra_d))
    db.flush()
    return order


def update_order_status(db: Session, order: DiningOrder, status: str) -> DiningOrder:
    order.status = status
    db.flush()
    return order


def get_order_item(db: Session, order_id: int, item_id: int) -> Optional[DiningOrderItem]:
    return (
        db.query(DiningOrderItem)
        .filter(DiningOrderItem.id == item_id, DiningOrderItem.order_id == order_id)
        .first()
    )


def void_order_item(db: Session, item: DiningOrderItem, reason: str, voided_by: int) -> DiningOrderItem:
    item.status = "cancelled"
    item.voided_reason = reason
    item.voided_by = voided_by
    item.voided_at = datetime.utcnow()
    db.flush()
    return item


def update_order_item_status(db: Session, item: DiningOrderItem, status: str) -> DiningOrderItem:
    """تحديث حالة صنف واحد داخل طلب (pending|in_kitchen|ready|served) — bump
    فردي من شاشة الـ KDS. راجع restaurant.crud.update_order_item_status —
    نفس المنطق بالظبط، بدون أي أثر مالي."""
    item.status = status
    db.flush()
    return item


def refund_order_item(db: Session, item: DiningOrderItem, reason: str, refunded_by: int) -> DiningOrderItem:
    item.status = "refunded"
    item.voided_reason = reason
    item.voided_by = refunded_by
    item.voided_at = datetime.utcnow()
    db.flush()
    return item


def update_order_discount(
    db: Session,
    order: DiningOrder,
    discount_amount: "Decimal",
    rule_id: Optional[int],
) -> DiningOrder:
    order.discount_amount = discount_amount
    order.total = max(
        Decimal("0"),
        order.subtotal + order.vat_amount + order.service_charge - discount_amount,
    )
    order.applied_discount_rule_id = rule_id
    db.flush()
    return order


# ── KitchenTicket ─────────────────────────────────────────────────────

def create_kitchen_ticket(
    db: Session,
    order_id: int,
    branch_id: int,
    outlet_id: int,
    station: str,
    items_snapshot: list,
) -> DiningKitchenTicket:
    ticket = DiningKitchenTicket(
        order_id=order_id,
        branch_id=branch_id,
        outlet_id=outlet_id,
        station=station,
        items_snapshot=items_snapshot,
        status="pending",
    )
    db.add(ticket)
    db.flush()
    return ticket


def list_tickets_for_order(db: Session, order_id: int) -> list[DiningKitchenTicket]:
    """كل تذاكر المطبخ (أي حالة، بما فيها 'done') لطلب معيّن — يُستخدم لمزامنة
    حالة التذكرة بعد bump فردي لصنف (راجع services._sync_kitchen_tickets_for_order).
    راجع restaurant.crud.list_tickets_for_order — نفس المنطق، بدون فلتر module
    (dining_kitchen_tickets FK حقيقي على dining_orders، مفيش ambiguity)."""
    return (
        db.query(DiningKitchenTicket)
        .filter(DiningKitchenTicket.order_id == order_id)
        .all()
    )


def list_pending_tickets(
    db: Session,
    branch_id: int,
    outlet_id: Optional[int] = None,
    stations: Optional[list[str]] = None,
) -> list[DiningKitchenTicket]:
    q = db.query(DiningKitchenTicket).filter(
        DiningKitchenTicket.branch_id == branch_id,
        DiningKitchenTicket.status != "done",
    )
    if outlet_id is not None:
        q = q.filter(DiningKitchenTicket.outlet_id == outlet_id)
    if stations:
        q = q.filter(DiningKitchenTicket.station.in_(stations))
    return q.order_by(DiningKitchenTicket.created_at).all()


def update_ticket_status(db: Session, ticket_id: int, new_status: str) -> Optional[DiningKitchenTicket]:
    ticket = db.query(DiningKitchenTicket).filter(DiningKitchenTicket.id == ticket_id).first()
    if ticket:
        ticket.status = new_status
        db.flush()
    return ticket


# ── KDSScreen ─────────────────────────────────────────────────────────

def list_kds_screens(db: Session, branch_id: int) -> list[DiningKDSScreen]:
    return (
        db.query(DiningKDSScreen)
        .filter(DiningKDSScreen.branch_id == branch_id, DiningKDSScreen.is_active.is_(True))
        .order_by(DiningKDSScreen.name)
        .all()
    )


def create_kds_screen(db: Session, data: dict) -> DiningKDSScreen:
    screen = DiningKDSScreen(**data)
    db.add(screen)
    db.flush()
    return screen


# ── Reporting / Food Cost ─────────────────────────────────────────────

def list_items_for_food_cost(db: Session, branch_id: int, outlet_id: Optional[int] = None) -> list[DiningItem]:
    q = db.query(DiningItem).filter(DiningItem.branch_id == branch_id)
    if outlet_id is not None:
        q = q.filter(DiningItem.outlet_id == outlet_id)
    return q.order_by(DiningItem.name).all()


def get_paid_order_items_for_food_cost(
    db: Session, branch_id: int, range_start: datetime, range_end: datetime,
    outlet_id: Optional[int] = None,
) -> list[tuple[int, Optional[int], "Decimal", int, datetime]]:
    """راجع restaurant.crud.get_paid_order_items_for_food_cost — نفس المنطق
    بالظبط (الأصناف الملغاة مُستبعدة، المرتجعة مُتضمّنة عمدًا، طلبات paid
    وrefunded الاتنين)."""
    q = (
        db.query(DiningOrderItem.item_id, DiningOrderItem.variant_id, DiningOrderItem.unit_price,
                  DiningOrderItem.quantity, DiningOrder.created_at)
        .join(DiningOrder, DiningOrderItem.order_id == DiningOrder.id)
        .filter(
            DiningOrder.branch_id == branch_id,
            DiningOrder.status.in_(("paid", "refunded")),
            DiningOrder.created_at >= range_start,
            DiningOrder.created_at <= range_end,
            DiningOrderItem.status != "cancelled",
        )
    )
    if outlet_id is not None:
        q = q.filter(DiningOrder.outlet_id == outlet_id)
    return [tuple(row) for row in q.all()]
