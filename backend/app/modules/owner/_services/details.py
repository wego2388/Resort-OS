"""
app/modules/owner/_services/details.py
Extracted from app/modules/owner/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from app.modules.owner.schemas import (
    BeachTypeDetailResponse,
    BeachTypeTransaction,
    DiningItemDetailResponse,
    DiningItemTransaction,
    ExpenseDetailResponse,
    ExpenseJournalLine,
    ProductDetailResponse,
    ProductMovement,
    RevenueDetailResponse,
    RevenueJournalLine,
    SupplierDetailResponse,
    SupplierPurchaseOrder,
)
from app.modules.owner._services._helpers import (
    _utc_date_bounds,
    _pagination_meta,
)


# Phase 8 — تفاصيل التفاصيل (Universal Drill-Down)
# ══════════════════════════════════════════════════════════════════════
# نفس مصدر البيانات المستخدم في التجميع أعلاه بالظبط، بس السجلات الخام
# بدل الإجمالي. صفر منطق مالي جديد.

def get_dining_item_detail(
    db: Session, branch_id: int, item_id: int, date_from: date, date_to: date,
    *, page: int = 1, size: int = 50,
) -> DiningItemDetailResponse:
    """كل الطلبات اللي فيها صنف مطعم/كافيه معيّن — نفس فلتر get_sales_
    performance بالظبط (paid orders، غير ملغاة) بس على مستوى الطلب لا التجميع."""
    from sqlalchemy import func as sa_func  # noqa: PLC0415
    from app.modules.dining.models import DiningOrder, DiningOrderItem, Outlet  # noqa: PLC0415

    range_start_utc, range_end_utc = _utc_date_bounds(date_from, date_to)
    base_query = (
        db.query(DiningOrderItem, DiningOrder, Outlet.name.label("outlet_name"))
        .join(DiningOrder, DiningOrder.id == DiningOrderItem.order_id)
        .join(Outlet, Outlet.id == DiningOrder.outlet_id)
        .filter(
            DiningOrder.branch_id == branch_id,
            DiningOrder.status == "paid",
            DiningOrderItem.item_id == item_id,
            DiningOrderItem.status != "cancelled",
            DiningOrder.created_at >= range_start_utc,
            DiningOrder.created_at <= range_end_utc,
        )
    )
    total_items = base_query.count()
    totals = (
        base_query
        .with_entities(
            sa_func.sum(DiningOrderItem.quantity).label("qty"),
            sa_func.sum(DiningOrderItem.unit_price * DiningOrderItem.quantity).label("revenue"),
        )
        .one()
    )
    name_row = base_query.with_entities(DiningOrderItem.name).first()
    rows = (
        base_query.order_by(DiningOrder.created_at.desc(), DiningOrderItem.id.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    item_name = name_row[0] if name_row else ""
    transactions = [
        DiningItemTransaction(
            order_id=item.order_id,
            order_number=order.order_number,
            outlet_name=outlet_name,
            order_type=order.order_type,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=item.unit_price * item.quantity,
            status=order.status,
            ordered_at=order.created_at,
        )
        for item, order, outlet_name in rows
    ]

    return DiningItemDetailResponse(
        item_id=item_id,
        item_name=item_name,
        period_from=date_from,
        period_to=date_to,
        transactions=transactions,
        total_quantity=int(totals.qty or 0),
        total_revenue=Decimal(str(totals.revenue or 0)),
        **_pagination_meta(page, size, total_items),
        computed_at=datetime.utcnow(),
    )


def get_beach_type_detail(
    db: Session, branch_id: int, tx_type: str, date_from: date, date_to: date,
    *, page: int = 1, size: int = 50,
) -> BeachTypeDetailResponse:
    """كل معاملات نوع تذكرة شاطئ معيّن — نفس فلتر get_beach_performance."""
    from sqlalchemy import func as sa_func  # noqa: PLC0415
    from app.modules.beach.models import BeachTransaction  # noqa: PLC0415
    from app.core.kernel.models.user import User  # noqa: PLC0415

    base_query = (
        db.query(BeachTransaction)
        .filter(
            BeachTransaction.branch_id == branch_id,
            BeachTransaction.voided_at.is_(None),
            BeachTransaction.tx_type == tx_type,
            BeachTransaction.tx_date >= date_from,
            BeachTransaction.tx_date <= date_to,
        )
    )

    total_items = base_query.count()
    total_revenue = Decimal(str(
        base_query.with_entities(sa_func.sum(BeachTransaction.total_amount)).scalar() or 0
    ))
    rows = (
        base_query.order_by(BeachTransaction.tx_date.desc(), BeachTransaction.id.desc())
        .offset((page - 1) * size).limit(size).all()
    )

    cashier_ids = {r.cashier_id for r in rows if r.cashier_id}
    cashier_names: dict[int, str] = {}
    if cashier_ids:
        users = db.query(User).filter(User.id.in_(cashier_ids)).all()
        cashier_names = {u.id: (u.full_name or f"#{u.id}") for u in users}

    transactions = [
        BeachTypeTransaction(
            transaction_id=r.id,
            tx_date=r.tx_date,
            guest_name=None,  # لا بيانات ضيف شخصية في شاشة الأونر — نفس قاعدة HR
            unit_price=r.unit_price,
            total_amount=r.total_amount,
            cashier_name=cashier_names.get(r.cashier_id) if r.cashier_id else None,
        )
        for r in rows
    ]

    return BeachTypeDetailResponse(
        tx_type=tx_type,
        period_from=date_from,
        period_to=date_to,
        transactions=transactions,
        total_count=total_items,
        total_revenue=total_revenue,
        **_pagination_meta(page, size, total_items),
        computed_at=datetime.utcnow(),
    )


def get_expense_detail(
    db: Session, branch_id: int, account_code: str, date_from: date, date_to: date,
    *, page: int = 1, size: int = 50,
) -> ExpenseDetailResponse:
    """كل قيود اليومية (سطور المدين) داخل حساب مصروف معيّن — نفس فترة
    get_expense_analytics بس سطور خام بدل إجمالي الحساب."""
    from sqlalchemy import func as sa_func  # noqa: PLC0415
    from app.modules.finance.models import Account, JournalEntry, JournalLine  # noqa: PLC0415

    account = db.query(Account).filter(
        Account.branch_id == branch_id, Account.code == account_code,
    ).first()
    if not account:
        return ExpenseDetailResponse(
            account_code=account_code, account_name=account_code,
            period_from=date_from, period_to=date_to, lines=[],
            total_amount=Decimal("0"), computed_at=datetime.utcnow(),
            **_pagination_meta(page, size, 0),
        )

    base_query = (
        db.query(JournalLine, JournalEntry)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .filter(
            JournalLine.account_id == account.id,
            JournalEntry.branch_id == branch_id,
            JournalEntry.entry_date >= date_from,
            JournalEntry.entry_date <= date_to,
            JournalLine.debit > 0,
        )
    )

    total_items = base_query.count()
    total_amount = Decimal(str(
        base_query.with_entities(sa_func.sum(JournalLine.debit)).scalar() or 0
    ))
    rows = (
        base_query.order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc())
        .offset((page - 1) * size).limit(size).all()
    )
    lines = [
        ExpenseJournalLine(
            entry_id=entry.id,
            entry_date=entry.entry_date,
            reference=entry.reference,
            description=line.description or entry.description,
            amount=line.debit,
            source=entry.source,
            cost_center=None,
        )
        for line, entry in rows
    ]

    return ExpenseDetailResponse(
        account_code=account_code,
        account_name=account.name,
        period_from=date_from,
        period_to=date_to,
        lines=lines,
        total_amount=total_amount,
        **_pagination_meta(page, size, total_items),
        computed_at=datetime.utcnow(),
    )


def get_revenue_detail(
    db: Session, branch_id: int, account_code: str, date_from: date, date_to: date,
    *, page: int = 1, size: int = 50,
) -> RevenueDetailResponse:
    """كل قيود اليومية (سطور الدائن) داخل حساب إيراد معيّن — نظير
    get_expense_detail بالظبط على الجانب الآخر (الإيراد يزيد بالدائن،
    عكس المصروف اللي يزيد بالمدين)."""
    from sqlalchemy import func as sa_func  # noqa: PLC0415
    from app.modules.finance.models import Account, JournalEntry, JournalLine  # noqa: PLC0415

    account = db.query(Account).filter(
        Account.branch_id == branch_id, Account.code == account_code,
    ).first()
    if not account:
        return RevenueDetailResponse(
            account_code=account_code, account_name=account_code,
            period_from=date_from, period_to=date_to, lines=[],
            total_amount=Decimal("0"), computed_at=datetime.utcnow(),
            **_pagination_meta(page, size, 0),
        )

    base_query = (
        db.query(JournalLine, JournalEntry)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .filter(
            JournalLine.account_id == account.id,
            JournalEntry.branch_id == branch_id,
            JournalEntry.entry_date >= date_from,
            JournalEntry.entry_date <= date_to,
            JournalLine.credit > 0,
        )
    )

    total_items = base_query.count()
    total_amount = Decimal(str(
        base_query.with_entities(sa_func.sum(JournalLine.credit)).scalar() or 0
    ))
    rows = (
        base_query.order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc())
        .offset((page - 1) * size).limit(size).all()
    )
    lines = [
        RevenueJournalLine(
            entry_id=entry.id,
            entry_date=entry.entry_date,
            reference=entry.reference,
            description=line.description or entry.description,
            amount=line.credit,
            source=entry.source,
        )
        for line, entry in rows
    ]

    return RevenueDetailResponse(
        account_code=account_code,
        account_name=account.name,
        period_from=date_from,
        period_to=date_to,
        lines=lines,
        total_amount=total_amount,
        **_pagination_meta(page, size, total_items),
        computed_at=datetime.utcnow(),
    )


def get_supplier_detail(
    db: Session, branch_id: int, supplier_id: int, date_from: date, date_to: date,
    *, page: int = 1, size: int = 50,
) -> SupplierDetailResponse:
    """كل أوامر الشراء المستلمة لمورد معيّن — نفس فلتر get_procurement_analytics."""
    from sqlalchemy import func as sa_func  # noqa: PLC0415
    from app.modules.inventory.models import PurchaseOrder, PurchaseOrderItem, Supplier  # noqa: PLC0415

    supplier = db.query(Supplier).filter(
        Supplier.id == supplier_id, Supplier.branch_id == branch_id,
    ).first()

    base_query = (
        db.query(
            PurchaseOrder,
            sa_func.count(PurchaseOrderItem.id).label("item_count"),
        )
        .outerjoin(PurchaseOrderItem, PurchaseOrderItem.purchase_order_id == PurchaseOrder.id)
        .filter(
            PurchaseOrder.branch_id == branch_id,
            PurchaseOrder.supplier_id == supplier_id,
            PurchaseOrder.status.in_(["received", "partial"]),
            PurchaseOrder.ordered_at >= date_from,
            PurchaseOrder.ordered_at <= date_to,
        )
        .group_by(PurchaseOrder.id)
    )
    total_items = base_query.count()
    total_amount = Decimal(str(
        db.query(sa_func.sum(PurchaseOrder.total_amount))
        .filter(
            PurchaseOrder.branch_id == branch_id,
            PurchaseOrder.supplier_id == supplier_id,
            PurchaseOrder.status.in_(["received", "partial"]),
            PurchaseOrder.ordered_at >= date_from,
            PurchaseOrder.ordered_at <= date_to,
        )
        .scalar() or 0
    ))
    rows = (
        base_query.order_by(PurchaseOrder.ordered_at.desc(), PurchaseOrder.id.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    orders = [
        SupplierPurchaseOrder(
            po_id=po.id,
            po_number=po.order_number,
            status=po.status,
            ordered_at=po.ordered_at,
            received_at=po.received_at,
            item_count=int(item_count or 0),
            total_amount=po.total_amount,
        )
        for po, item_count in rows
    ]

    return SupplierDetailResponse(
        supplier_id=supplier_id,
        supplier_name=(supplier.name if supplier else "غير محدد"),
        period_from=date_from,
        period_to=date_to,
        orders=orders,
        total_amount=total_amount,
        **_pagination_meta(page, size, total_items),
        computed_at=datetime.utcnow(),
    )


def get_product_detail(
    db: Session, branch_id: int, product_id: int, date_from: date, date_to: date,
    *, page: int = 1, size: int = 50,
) -> ProductDetailResponse:
    """حركات مخزون منتج معيّن (شراء/استهلاك/تعديل/تحويل) + الرصيد الحالي."""
    from sqlalchemy import func as sa_func  # noqa: PLC0415
    from app.modules.inventory.models import Product, StockMovement, Warehouse  # noqa: PLC0415
    range_start_utc, range_end_utc = _utc_date_bounds(date_from, date_to)

    product = db.query(Product).filter(
        Product.id == product_id, Product.branch_id == branch_id,
    ).first()
    if not product:
        return ProductDetailResponse(
            product_id=product_id, product_name="غير موجود", unit="",
            current_stock=Decimal("0"), cost_price=Decimal("0"),
            period_from=date_from, period_to=date_to, movements=[],
            total_in=Decimal("0"), total_out=Decimal("0"), computed_at=datetime.utcnow(),
            **_pagination_meta(page, size, 0),
        )

    base_query = (
        db.query(StockMovement, Warehouse.name.label("warehouse_name"))
        .join(Warehouse, Warehouse.id == StockMovement.warehouse_id)
        .filter(
            StockMovement.branch_id == branch_id,
            StockMovement.product_id == product_id,
            StockMovement.moved_at >= range_start_utc,
            StockMovement.moved_at <= range_end_utc,
        )
    )
    total_items = base_query.count()
    total_in = Decimal(str(
        base_query.filter(StockMovement.quantity > 0)
        .with_entities(sa_func.sum(StockMovement.quantity)).scalar() or 0
    ))
    total_out = -Decimal(str(
        base_query.filter(StockMovement.quantity < 0)
        .with_entities(sa_func.sum(StockMovement.quantity)).scalar() or 0
    ))
    rows = (
        base_query.order_by(StockMovement.moved_at.desc(), StockMovement.id.desc())
        .offset((page - 1) * size).limit(size).all()
    )

    movements = [
        ProductMovement(
            movement_id=m.id,
            movement_type=m.movement_type,
            quantity=m.quantity,
            unit_cost=m.unit_cost,
            warehouse_name=wh_name,
            moved_at=m.moved_at,
            notes=m.notes,
        )
        for m, wh_name in rows
    ]

    return ProductDetailResponse(
        product_id=product_id,
        product_name=product.name,
        unit=product.unit,
        current_stock=product.current_stock,
        cost_price=product.cost_price,
        period_from=date_from,
        period_to=date_to,
        movements=movements,
        total_in=total_in,
        total_out=total_out,
        **_pagination_meta(page, size, total_items),
        computed_at=datetime.utcnow(),
    )
