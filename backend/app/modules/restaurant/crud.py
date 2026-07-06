"""app/modules/restaurant/crud.py — CRUD خالص"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.resort_os.timezone_utils import local_date_to_utc_range
from app.modules.restaurant.models import (
    DiningTable, KDSScreen, KitchenTicket, MenuCategory, MenuItem, MenuItemExtra,
    MenuItemExtraGroup, MenuItemRecipeLine, Order, OrderItem, OrderItemExtra,
)
from app.modules.restaurant.schemas import (
    MenuCategoryCreate, MenuItemCreate, MenuItemExtraGroupCreate,
    MenuItemRecipeLineCreate, MenuItemRecipeLineUpdate, MenuItemUpdate,
)


# ── MenuCategory ──────────────────────────────────────────────────────

def list_categories(db: Session, branch_id: int) -> list[MenuCategory]:
    return (
        db.query(MenuCategory)
        .filter(MenuCategory.branch_id == branch_id, MenuCategory.is_active.is_(True))
        .order_by(MenuCategory.sort_order)
        .all()
    )


def create_category(db: Session, data: MenuCategoryCreate) -> MenuCategory:
    obj = MenuCategory(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


# ── MenuItem ──────────────────────────────────────────────────────────

def get_menu_item(db: Session, item_id: int) -> Optional[MenuItem]:
    return db.query(MenuItem).filter(MenuItem.id == item_id).first()


def list_menu_items(
    db: Session,
    branch_id: int,
    category_id: Optional[int] = None,
    available_only: bool = True,
) -> list[MenuItem]:
    q = db.query(MenuItem).filter(MenuItem.branch_id == branch_id)
    if available_only:
        q = q.filter(MenuItem.is_available.is_(True))
    if category_id is not None:
        q = q.filter(MenuItem.category_id == category_id)
    return q.order_by(MenuItem.name).all()


def create_menu_item(db: Session, data: MenuItemCreate) -> MenuItem:
    obj = MenuItem(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


def update_menu_item(db: Session, item: MenuItem, data: MenuItemUpdate) -> MenuItem:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.flush()
    return item


def create_extra_group(db: Session, menu_item_id: int, data: MenuItemExtraGroupCreate) -> MenuItemExtraGroup:
    group = MenuItemExtraGroup(
        menu_item_id=menu_item_id,
        name=data.name,
        name_ar=data.name_ar,
        min_select=data.min_select,
        max_select=data.max_select,
        sort_order=data.sort_order,
    )
    db.add(group)
    db.flush()
    for opt in data.options:
        db.add(MenuItemExtra(group_id=group.id, **opt.model_dump()))
    db.flush()
    return group


def delete_extra_group(db: Session, group_id: int) -> bool:
    group = db.query(MenuItemExtraGroup).filter(MenuItemExtraGroup.id == group_id).first()
    if not group:
        return False
    db.delete(group)
    db.flush()
    return True


# ── Recipe / BOM ──────────────────────────────────────────────────────

def get_recipe_line(db: Session, line_id: int) -> Optional[MenuItemRecipeLine]:
    return db.query(MenuItemRecipeLine).filter(MenuItemRecipeLine.id == line_id).first()


def create_recipe_line(db: Session, menu_item_id: int, data: MenuItemRecipeLineCreate) -> MenuItemRecipeLine:
    line = MenuItemRecipeLine(menu_item_id=menu_item_id, **data.model_dump())
    db.add(line)
    db.flush()
    return line


def update_recipe_line(db: Session, line: MenuItemRecipeLine, data: MenuItemRecipeLineUpdate) -> MenuItemRecipeLine:
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


# ── DiningTable ───────────────────────────────────────────────────────

def list_tables(db: Session, branch_id: int) -> list[DiningTable]:
    return (
        db.query(DiningTable)
        .filter(DiningTable.branch_id == branch_id)
        .order_by(DiningTable.table_number)
        .all()
    )


def get_table(db: Session, table_id: int) -> Optional[DiningTable]:
    return db.query(DiningTable).filter(DiningTable.id == table_id).first()


def update_table_status(db: Session, table: DiningTable, status: str) -> DiningTable:
    table.status = status
    table.occupied_at = datetime.utcnow() if status == "occupied" else None
    db.flush()
    return table


# ── Order ─────────────────────────────────────────────────────────────

def get_order(db: Session, order_id: int) -> Optional[Order]:
    return db.query(Order).filter(Order.id == order_id).first()


def get_order_by_local_id(db: Session, local_id: str) -> Optional[Order]:
    return db.query(Order).filter(Order.client_local_id == local_id).first()


def list_orders(
    db: Session,
    branch_id: int,
    status: Optional[str] = None,
    order_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Order], int]:
    q = db.query(Order).filter(Order.branch_id == branch_id)
    if status:
        q = q.filter(Order.status == status)
    if order_date:
        # created_at مخزّن UTC — لازم نحوّل "اليوم" بتوقيت المنتجع (settings.TIMEZONE)
        # لمدى UTC، وإلا فلترة "اليوم" بتفشل لمدة ~3 ساعات كل يوم (فرق UTC+3 القاهرة).
        start, end = local_date_to_utc_range(order_date, settings.TIMEZONE)
        q = q.filter(Order.created_at.between(start, end))
    total = q.count()
    items = q.order_by(Order.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def generate_order_number(db: Session, branch_id: int) -> str:
    today_str = datetime.utcnow().strftime("%Y%m%d")
    prefix = f"ORD-{today_str}-"
    count = (
        db.query(Order)
        .filter(Order.order_number.like(f"{prefix}%"))
        .count()
    )
    return f"{prefix}{count + 1:04d}"


def create_order_with_items(
    db: Session,
    branch_id: int,
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
) -> Order:
    order = Order(
        branch_id=branch_id,
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
    )
    db.add(order)
    db.flush()

    for item_d in items_data:
        extras = item_d.pop("extras", [])
        order_item = OrderItem(order_id=order.id, **item_d)
        db.add(order_item)
        db.flush()  # يحتاج order_item.id قبل ما نربط الإضافات
        for extra_d in extras:
            db.add(OrderItemExtra(order_item_id=order_item.id, **extra_d))
    db.flush()
    return order


def update_order_status(db: Session, order: Order, status: str) -> Order:
    order.status = status
    db.flush()
    return order


def get_order_item(db: Session, order_id: int, item_id: int) -> Optional[OrderItem]:
    return (
        db.query(OrderItem)
        .filter(OrderItem.id == item_id, OrderItem.order_id == order_id)
        .first()
    )


def void_order_item(db: Session, item: OrderItem, reason: str, voided_by: int) -> OrderItem:
    item.status = "cancelled"
    item.voided_reason = reason
    item.voided_by = voided_by
    item.voided_at = datetime.utcnow()
    db.flush()
    return item


def refund_order_item(db: Session, item: OrderItem, reason: str, refunded_by: int) -> OrderItem:
    """مرتجع بعد الدفع — نفس حقول void_order_item بالظبط (مين/ليه/إمتى)، بس
    status='refunded' بدل 'cancelled' عشان يتفرّق تقريريًا عن إلغاء قبل الدفع."""
    item.status = "refunded"
    item.voided_reason = reason
    item.voided_by = refunded_by
    item.voided_at = datetime.utcnow()
    db.flush()
    return item


# ── KitchenTicket ─────────────────────────────────────────────────────

def create_kitchen_ticket(
    db: Session,
    order_id: int,
    branch_id: int,
    station: str,
    items_snapshot: list,
    module: str = "restaurant",
) -> KitchenTicket:
    ticket = KitchenTicket(
        order_id=order_id,
        branch_id=branch_id,
        station=station,
        items_snapshot=items_snapshot,
        module=module,
        status="pending",
    )
    db.add(ticket)
    db.flush()
    return ticket


def list_pending_tickets(
    db: Session,
    branch_id: int,
    stations: Optional[list[str]] = None,
    module: str = "restaurant",
) -> list[KitchenTicket]:
    q = db.query(KitchenTicket).filter(
        KitchenTicket.branch_id == branch_id,
        KitchenTicket.module == module,
        KitchenTicket.status != "done",
    )
    if stations:
        q = q.filter(KitchenTicket.station.in_(stations))
    return q.order_by(KitchenTicket.created_at).all()


def update_ticket_status(db: Session, ticket_id: int, new_status: str) -> Optional[KitchenTicket]:
    ticket = db.query(KitchenTicket).filter(KitchenTicket.id == ticket_id).first()
    if ticket:
        ticket.status = new_status
        db.flush()
    return ticket


# ── KDSScreen ─────────────────────────────────────────────────────────

def list_kds_screens(db: Session, branch_id: int) -> list[KDSScreen]:
    return (
        db.query(KDSScreen)
        .filter(KDSScreen.branch_id == branch_id, KDSScreen.is_active.is_(True))
        .order_by(KDSScreen.name)
        .all()
    )


def create_kds_screen(db: Session, data: dict) -> KDSScreen:
    screen = KDSScreen(**data)
    db.add(screen)
    db.flush()
    return screen


def update_order_discount(
    db: Session,
    order: Order,
    discount_amount: "Decimal",
    rule_id: Optional[int],
) -> Order:
    from decimal import Decimal
    order.discount_amount = discount_amount
    order.total = max(
        Decimal("0"),
        order.subtotal + order.vat_amount + order.service_charge - discount_amount,
    )
    order.applied_discount_rule_id = rule_id
    db.flush()
    return order
