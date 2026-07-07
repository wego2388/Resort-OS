"""app/modules/restaurant/services.py — Business logic"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.restaurant import crud
from app.modules.restaurant.models import KitchenTicket, MenuItem, MenuItemRecipeLine, Order
from app.modules.restaurant.schemas import (
    FoodCostReportLine, FoodCostReportResponse, CogsTrendPoint, GrossMarginSummary,
    MenuItemRecipeLineCreate, MenuItemRecipeLineUpdate, OrderCreate,
)
from app.resort_os.discount_engine import DiscountRule, OrderContext, calculate_discount
from app.resort_os.food_cost_engine import DEFAULT_FOOD_COST_THRESHOLD_PCT, compute_food_cost_result, exceeds_threshold
from app.resort_os.timezone_utils import local_date_to_utc_range, utc_naive_to_local_date


def _get_order_or_404(db: Session, order_id: int) -> Order:
    order = crud.get_order(db, order_id)
    if not order:
        raise ValueError(f"الطلب {order_id} غير موجود")
    return order


def _resolve_extras(db: Session, menu_item, extra_ids: list[int]) -> tuple[list[dict], Decimal]:
    """يتحقق من الإضافات المختارة (تتبع نفس الصنف + قواعد min/max_select
    لكل مجموعة) ويرجّع (extras snapshot data, إجمالي الإضافة للوحدة الواحدة)."""
    if not menu_item.extra_groups and not extra_ids:
        return [], Decimal("0")

    valid_extra_ids = {
        extra.id for group in menu_item.extra_groups for extra in group.options
    }
    for extra_id in extra_ids:
        if extra_id not in valid_extra_ids:
            raise ValueError(f"الإضافة {extra_id} لا تنتمي لصنف '{menu_item.name}'")

    selected = set(extra_ids)
    extras_data: list[dict] = []
    price_addition = Decimal("0")

    for group in menu_item.extra_groups:
        group_selected = [opt for opt in group.options if opt.id in selected]
        if len(group_selected) < group.min_select:
            raise ValueError(f"لازم تختار {group.min_select} على الأقل من '{group.name}'")
        if len(group_selected) > group.max_select:
            raise ValueError(f"أقصى اختيار من '{group.name}' هو {group.max_select}")
        for opt in group_selected:
            if not opt.is_available:
                raise ValueError(f"الإضافة '{opt.name}' غير متاحة حالياً")
            extras_data.append({
                "extra_id":       opt.id,
                "extra_name":     opt.name,
                "price_addition": opt.price_addition,
            })
            price_addition += opt.price_addition

    return extras_data, price_addition


# ─────────────────────── Recipe / BOM ──────────────────────────────────

def compute_menu_item_cost(item: MenuItem) -> Decimal:
    """تكلفة الصنف الحقيقية — لو فيه وصفة (BOM)، التكلفة = مجموع (كمية كل
    مكوّن × تكلفة المنتج المخزني الحالية). لو مفيش وصفة، fallback لحقل
    cost اليدوي (أو صفر لو ده كمان مش موجود). أي صنف قديم بدون وصفة يفضل
    شغال بنفس سلوكه الحالي بالظبط — الوصفة إضافة اختيارية مش استبدال قسري."""
    if item.recipe_lines:
        total = Decimal("0")
        for line in item.recipe_lines:
            unit_cost = (line.product.cost_price if line.product else None) or Decimal("0")
            total += line.quantity_per_unit * unit_cost
        return total.quantize(Decimal("0.01"))
    return item.cost if item.cost is not None else Decimal("0")


def build_recipe_line_read(line: MenuItemRecipeLine) -> dict:
    """يبني dict متوافق مع MenuItemRecipeLineRead من سطر وصفة ORM — بيضمّن
    snapshot لحظي لاسم/وحدة/تكلفة المنتج المخزني الحالية (مش مخزّنة على
    السطر نفسه، بتتقرأ من inventory.Product وقت الطلب)."""
    unit_cost = (line.product.cost_price if line.product else None) or Decimal("0")
    return {
        "id": line.id,
        "menu_item_id": line.menu_item_id,
        "product_id": line.product_id,
        "product_name": line.product.name if line.product else "",
        "product_unit": line.product.unit if line.product else "",
        "quantity_per_unit": line.quantity_per_unit,
        "unit_cost": unit_cost,
        "line_cost": (line.quantity_per_unit * unit_cost).quantize(Decimal("0.01")),
        "notes": line.notes,
    }


def add_recipe_line(db: Session, menu_item_id: int, data: MenuItemRecipeLineCreate) -> MenuItemRecipeLine:
    from app.modules.inventory import crud as inventory_crud  # noqa: PLC0415

    item = crud.get_menu_item(db, menu_item_id)
    if not item:
        raise ValueError(f"الصنف {menu_item_id} غير موجود")
    product = inventory_crud.get_product(db, data.product_id)
    if not product:
        raise ValueError(f"المنتج {data.product_id} غير موجود في المخزون")
    if product.branch_id != item.branch_id:
        raise ValueError("المنتج المخزني لازم يكون من نفس فرع الصنف")
    if any(line.product_id == data.product_id for line in item.recipe_lines):
        raise ValueError(f"المنتج '{product.name}' مضاف بالفعل لوصفة هذا الصنف")

    line = crud.create_recipe_line(db, menu_item_id, data)
    db.commit()
    db.refresh(line)
    return line


def update_recipe_line(db: Session, line_id: int, data: MenuItemRecipeLineUpdate) -> MenuItemRecipeLine:
    line = crud.get_recipe_line(db, line_id)
    if not line:
        raise ValueError(f"سطر الوصفة {line_id} غير موجود")
    line = crud.update_recipe_line(db, line, data)
    db.commit()
    db.refresh(line)
    return line


def remove_recipe_line(db: Session, line_id: int) -> None:
    if not crud.delete_recipe_line(db, line_id):
        raise ValueError(f"سطر الوصفة {line_id} غير موجود")
    db.commit()


def create_order(
    db: Session,
    branch_id: int,
    data: OrderCreate,
    waiter_id: Optional[int] = None,
    hold: bool = False,
) -> Order:
    # تحقق من الطاولة
    if data.table_id:
        table = crud.get_table(db, data.table_id)
        if not table:
            raise ValueError(f"الطاولة {data.table_id} غير موجودة")
        if table.status == "out_of_service":
            raise ValueError(f"الطاولة {table.table_number} خارج الخدمة")

    # تحقق من كل الأصناف وبناء items_data
    items_data = []
    subtotal = Decimal("0")

    for item_req in data.items:
        menu_item = crud.get_menu_item(db, item_req.menu_item_id)
        if not menu_item:
            raise ValueError(f"الصنف {item_req.menu_item_id} غير موجود")
        if not menu_item.is_available:
            raise ValueError(f"الصنف '{menu_item.name}' غير متاح حالياً")

        extras_data, extra_price_per_unit = _resolve_extras(db, menu_item, item_req.extra_ids)

        line_total = (menu_item.price + extra_price_per_unit) * item_req.quantity
        subtotal += line_total
        items_data.append({
            "menu_item_id": item_req.menu_item_id,
            "name":         menu_item.name,
            "unit_price":   menu_item.price,
            "quantity":     item_req.quantity,
            "notes":        item_req.notes,
            "extras":       extras_data,
        })

    vat_pct     = Decimal(str(settings.VAT_PERCENTAGE)) / Decimal("100")
    svc_pct     = Decimal(str(settings.SERVICE_CHARGE_PERCENTAGE)) / Decimal("100")
    vat_amount  = (subtotal * vat_pct).quantize(Decimal("0.01"))
    svc_charge  = (subtotal * svc_pct).quantize(Decimal("0.01"))
    total       = subtotal + vat_amount + svc_charge

    order_number = crud.generate_order_number(db, branch_id)

    order = crud.create_order_with_items(
        db=db,
        branch_id=branch_id,
        order_number=order_number,
        order_type=data.order_type,
        table_id=data.table_id,
        guests_count=data.guests_count,
        notes=data.notes,
        subtotal=subtotal,
        vat_amount=vat_amount,
        service_charge=svc_charge,
        total=total,
        waiter_id=waiter_id,
        items_data=items_data,
        status="held" if hold else "open",
        customer_id=data.customer_id,
    )

    # تحديث حالة الطاولة
    if data.table_id and data.order_type == "dine_in":
        table = crud.get_table(db, data.table_id)
        if table:
            crud.update_table_status(db, table, "occupied")

    db.commit()
    db.refresh(order)
    return order


def sync_offline_order(
    db: Session,
    branch_id: int,
    data,  # OrderSyncRequest
    waiter_id: Optional[int] = None,
):
    """يستقبل طلب اتعمل وهو offline (IndexedDB) ويسوّيه مع حالة المخزون
    الحالية — السيرفر هو مصدر الحقيقة. يرجّع fulfilled/partial/rejected
    حسب 07-BUSINESS-RULES.md § 9.

    Idempotent عبر client_local_id: لو الطلب ده اتعمل قبل كده (retry بعد
    انقطاع نت جزئي)، يرجّع نفس النتيجة من غير ما يكرر الطلب."""
    existing = crud.get_order_by_local_id(db, data.local_id)
    if existing:
        return {
            "order_id": existing.id,
            "status": "fulfilled",
            "fulfilled_items": existing.items,
            "rejected_items": [],
            "message": "الطلب اتسجّل بالفعل (retry آمن)",
        }

    fulfilled_requests = []
    rejected_items = []

    for item_req in data.items:
        menu_item = crud.get_menu_item(db, item_req.menu_item_id)
        if not menu_item or not menu_item.is_available:
            rejected_items.append({
                "item_id": item_req.menu_item_id,
                "name": menu_item.name if menu_item else f"#{item_req.menu_item_id}",
                "reason": "out_of_stock",
                "available_qty": 0,
                "requested_qty": item_req.quantity,
            })
        else:
            fulfilled_requests.append(item_req)

    if not fulfilled_requests:
        return {
            "order_id": None,
            "status": "rejected",
            "fulfilled_items": [],
            "rejected_items": rejected_items,
            "message": "كل الأصناف غير متاحة حالياً",
        }

    sync_order_data = OrderCreate(
        table_id=data.table_id,
        order_type=data.order_type,
        guests_count=data.guests_count,
        notes=data.notes,
        items=fulfilled_requests,
    )
    order = create_order(db, branch_id, sync_order_data, waiter_id=waiter_id)
    order.client_local_id = data.local_id
    db.commit()
    db.refresh(order)

    return {
        "order_id": order.id,
        "status": "partial" if rejected_items else "fulfilled",
        "fulfilled_items": order.items,
        "rejected_items": rejected_items,
        "message": (
            "تم تنفيذ الطلب جزئياً — راجع الأصناف المرفوضة" if rejected_items
            else "تم تنفيذ الطلب بالكامل"
        ),
    }


def update_order_status(
    db: Session, order_id: int, new_status: str, charge_to_room_id: Optional[int] = None,
) -> Order:
    order = _get_order_or_404(db, order_id)

    # لا يمكن إرجاع طلب مدفوع أو ملغي
    if order.status in ("paid", "cancelled"):
        raise ValueError(f"لا يمكن تغيير حالة طلب '{order.status}'")

    if new_status == "paid" and charge_to_room_id and not order.folio_id:
        from app.modules.pms.services import find_active_folio_for_room  # noqa: PLC0415
        folio_id = find_active_folio_for_room(db, order.branch_id, charge_to_room_id)
        if not folio_id:
            raise ValueError(f"مفيش ضيف مسجّل دخول في الغرفة {charge_to_room_id} حاليًا")
        order.folio_id = folio_id

    order = crud.update_order_status(db, order, new_status)

    # إرسال ticket لكل محطة (hot/grill/cold/bar/dessert) عند تحويل الطلب لـ in_kitchen
    # — بنقسّم الأصناف حسب MenuItem.station بدل تذكرة واحدة لكل الطلب، عشان شاشة الـ
    # KDS الخاصة بكل محطة (KDSScreen.stations) تعرض بس الأصناف اللي تخصها فعليًا.
    if new_status == "in_kitchen":
        active_items = [item for item in order.items if item.status != "cancelled"]
        menu_item_ids = {item.menu_item_id for item in active_items}
        station_by_menu_item = {
            mi.id: mi.station
            for mi in db.query(MenuItem).filter(MenuItem.id.in_(menu_item_ids)).all()
        } if menu_item_ids else {}

        items_by_station: dict[str, list[dict]] = {}
        for item in active_items:
            station = station_by_menu_item.get(item.menu_item_id, "hot")
            items_by_station.setdefault(station, []).append({
                "order_item_id": item.id,
                "name":          item.name,
                "quantity":      item.quantity,
                "notes":         item.notes,
            })

        for station, items_snapshot in items_by_station.items():
            crud.create_kitchen_ticket(
                db,
                order_id=order.id,
                branch_id=order.branch_id,
                station=station,
                items_snapshot=items_snapshot,
                module="restaurant",
            )

    # إعادة الطاولة للحالة available عند الدفع أو الإلغاء
    if new_status in ("paid", "cancelled") and order.table_id:
        table = crud.get_table(db, order.table_id)
        if table:
            crud.update_table_status(db, table, "available")

    # نشر charge على folio الغرفة عند الدفع
    if new_status == "paid" and order.folio_id:
        try:
            from app.modules.finance import crud as finance_crud  # noqa: PLC0415
            from app.modules.finance.schemas import FolioChargeCreate  # noqa: PLC0415
            charge_data = FolioChargeCreate(
                charge_type="restaurant",
                description=f"طلب {order.order_number}",
                amount=order.subtotal,
                vat_amount=order.vat_amount,
                # ⚠️ باج حقيقي كان هنا (اتصلح): service_charge (12% من الطلب)
                # كان بيضيع تمامًا هنا — الطلب نفسه بيحسبه صح (order.total)، بس
                # مكانش بيوصل للفوليو خالص، يعني فاتورة الضيف عند الـ checkout
                # كانت ناقصة قيمة الخدمة لكل طلب اتحمّل على الغرفة.
                service_charge=order.service_charge,
                posted_at=datetime.utcnow(),
                ref_order_id=order.id,
            )
            finance_crud.add_charge(db, order.folio_id, charge_data)
            # ⚠️ باج حقيقي كان هنا (اتصلح 2026-07-04): add_charge لوحدها بتضيف
            # صف FolioCharge بس — Folio.total (العمود المخزّن اللي GET
            # /finance/folios بيرجّعه مباشرة) كان بيفضل زي ما هو من غير تحديث.
            # checkout نفسه آمن (folio_engine.FolioSummary بتحسب المجموع من
            # folio.charges لحظيًا)، لكن أي شاشة/تقرير بيعرض Folio.total
            # مباشرة كان بيوريه رقم قديم ناقص كل شحنات Charge-to-Room.
            folio = finance_crud.get_folio(db, order.folio_id)
            if folio:
                finance_crud.recalculate_folio_total(db, folio)
        except Exception:
            pass  # ميمنعش إتمام الدفع لو فشل نشر الـ charge على الفوليو

    # قيد إيراد المطعم — بيترحّل فورًا في الحالتين، بس لحساب مختلف حسب طريقة
    # الدفع:
    #   - كاش/كارت فوري: Dr Cash(1100) / Cr إيراد المطعم(4200).
    #   - محمّل على فوليو غرفة (Charge to Room): Dr ذمم الفوليو(1150) /
    #     Cr إيراد المطعم(4200) — الإيراد بيتسجّل دلوقتي (وقت تقديم الخدمة
    #     فعليًا)، والكاش الحقيقي بيتسجّل لاحقًا لما الضيف يسدّد الفوليو
    #     (finance.services.add_payment، Dr Cash/Cr ذمم الفوليو).
    #
    # ⚠️ باج حقيقي كان هنا (اتصلح 2026-07-07، فجوة معمارية موثّقة في
    # CLAUDE.md §18): الحالة التانية (محمّل على فوليو) كانت من غير أي قيد
    # محاسبي خالص — إيراد المطعم الحقيقي من كل الطلبات اللي بتتحمّل على
    # الغرفة (نسبة كبيرة من مبيعات المطعم في منتجع فيه نزلاء) كان غايب تمامًا
    # عن دفتر الأستاذ، رغم إنه بيظهر صح في فاتورة الضيف المطبوعة.
    if new_status == "paid":
        _deduct_inventory_for_order(db, order)
        if order.folio_id:
            _post_order_folio_charge_journal(db, order)
        else:
            _post_order_revenue_journal(db, order)
        if order.customer_id:
            from app.modules.crm.services import record_customer_visit  # noqa: PLC0415
            record_customer_visit(db, order.customer_id, order.total, order.created_at.date())

    db.commit()
    db.refresh(order)
    return order


def _deduct_inventory_for_order(db: Session, order: Order) -> None:
    """يخصم المخزون لكل صنف في الطلب. أولوية الخصم:
      1) وصفة حقيقية (MenuItem.recipe_lines) — كل مكوّن يتخصم بكميته ×
         quantity المطلوبة، مسموح بمخزون سالب مع تحذير (نفضّل عدم إيقاف
         عملية بيع طعام حقيقية بسبب فرق جرد، على إيقافها أو تجاهلها بصمت).
      2) مفيش وصفة بس فيه ربط قديم 1:1 (MenuItem.linked_product_id) — نفس
         السلوك القديم بالظبط (بيرفض الخصم بصمت لو الرصيد مش كافي، مفيش
         مخزون سالب هنا — سلوك مؤكد باختبارات موجودة، مش هدف هذا التغيير).
      3) مفيش أي ربط — بيتم تجاوز الصنف بصمت (معظم الأصناف كده).
    فشل خصم صنف واحد ميوقفش باقي الأصناف ولا يوقف إتمام الدفع — نفس فلسفة
    _post_order_revenue_journal أعلاه."""
    from app.modules.inventory import crud as inventory_crud  # noqa: PLC0415
    from app.modules.inventory import services as inventory_services  # noqa: PLC0415

    for item in order.items:
        if item.status == "cancelled":
            continue
        try:
            menu_item = crud.get_menu_item(db, item.menu_item_id)
            if not menu_item:
                continue
            if menu_item.recipe_lines:
                for line in menu_item.recipe_lines:
                    product = inventory_crud.get_product(db, line.product_id)
                    if not product or not product.warehouse_id:
                        continue
                    inventory_services.consume_stock(
                        db,
                        branch_id=order.branch_id,
                        product_id=product.id,
                        warehouse_id=product.warehouse_id,
                        quantity=line.quantity_per_unit * item.quantity,
                        reference_type="restaurant_order",
                        reference_id=order.id,
                        moved_by=0,
                        allow_negative=True,
                    )
                continue
            if not menu_item.linked_product_id:
                continue
            product = inventory_crud.get_product(db, menu_item.linked_product_id)
            if not product or not product.warehouse_id:
                continue
            inventory_services.consume_stock(
                db,
                branch_id=order.branch_id,
                product_id=product.id,
                warehouse_id=product.warehouse_id,
                quantity=Decimal(item.quantity),
                reference_type="restaurant_order",
                reference_id=order.id,
                moved_by=0,
            )
        except Exception:
            continue


def _post_order_revenue_journal(db: Session, order: "Order") -> None:
    """Dr. Cash (1100) / Cr. Restaurant Revenue (4200) — دفع كاش/كارت فوري."""
    from app.core.config import settings  # noqa: PLC0415
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415
    from app.resort_os.timezone_utils import local_today  # noqa: PLC0415

    post_simple_revenue_journal(
        db, order.branch_id, local_today(settings.TIMEZONE),
        debit_account_code="1100", credit_account_code="4200",
        amount=order.total or Decimal("0"),
        reference=f"ORD-{order.order_number}",
        description=f"إيرادات مطعم — {order.order_number}",
        source="restaurant", source_id=order.id,
    )


def _post_order_folio_charge_journal(db: Session, order: "Order") -> None:
    """Dr. ذمم الفوليو (1150) / Cr. إيراد المطعم (4200) — طلب محمّل على فوليو
    غرفة (Charge to Room). الإيراد بيتسجّل دلوقتي (وقت الخدمة)، والكاش
    الحقيقي بيتسجّل لاحقًا وقت تسوية الفوليو (راجع finance.services.add_payment).
    نظير _post_order_revenue_journal فوق، بس لحساب ذمم بدل الكاش المباشر."""
    from app.core.config import settings  # noqa: PLC0415
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415
    from app.resort_os.timezone_utils import local_today  # noqa: PLC0415

    post_simple_revenue_journal(
        db, order.branch_id, local_today(settings.TIMEZONE),
        debit_account_code="1150", credit_account_code="4200",
        amount=order.total or Decimal("0"),
        reference=f"ORD-{order.order_number}",
        description=f"إيرادات مطعم (محمّل على الغرفة) — {order.order_number}",
        source="restaurant_folio_charge", source_id=order.id,
    )


def void_order_item(
    db: Session, order_id: int, item_id: int, reason: str, voided_by: int,
    acting_user_level: int = 100, approver_user_id: Optional[int] = None,
    approver_pin: Optional[str] = None,
) -> Order:
    """إلغاء صنف واحد من الطلب مع سبب إجباري + توثيق مين لغاه (زي
    InvoiceDetails.isavoid/avoidreason/avoiduserId عند Trucker) — مش إلغاء
    الطلب كله. بيعيد حساب subtotal/vat/service/total من الأصناف الفعّالة بس.

    ``acting_user_level`` الافتراضي (100) مقصود — أي caller داخلي (تستات،
    سكريبتات) من غير ما يحدده معناه "موثوق"، بس الـ router (المسار
    الإنتاجي الوحيد الحقيقي) بيمرّر المستوى الفعلي دايمًا. لو المنفّذ أقل
    من مستوى مدير (60)، لازم PIN موافقة صحيح — راجع
    core.services.resolve_pin_approval."""
    order = _get_order_or_404(db, order_id)
    if order.status in ("paid", "cancelled"):
        raise ValueError(f"لا يمكن إلغاء صنف من طلب '{order.status}' — استخدم مرتجع بعد الدفع")

    item = crud.get_order_item(db, order_id, item_id)
    if not item:
        raise ValueError(f"الصنف {item_id} غير موجود في هذا الطلب")
    if item.status == "cancelled":
        raise ValueError("الصنف ده ملغي بالفعل")

    from app.modules.core import crud as core_crud, services as core_services  # noqa: PLC0415
    from app.modules.core.schemas import AuditLogCreate  # noqa: PLC0415

    approved_by = core_services.resolve_pin_approval(
        db, acting_user_level, approver_user_id, approver_pin, min_approver_level=60,
    )

    crud.void_order_item(db, item, reason, voided_by)
    core_crud.create_audit_log(db, AuditLogCreate(
        user_id=voided_by, approved_by=approved_by, branch_id=order.branch_id,
        action="void_order_item", entity_type="order_item", entity_id=item.id,
        new_data=json.dumps({"reason": reason}),
    ))

    subtotal = Decimal("0")
    for i in order.items:
        if i.status == "cancelled":
            continue
        extras_total = sum((e.price_addition for e in i.extras), Decimal("0"))
        subtotal += (i.unit_price + extras_total) * i.quantity

    vat_pct    = Decimal(str(settings.VAT_PERCENTAGE)) / Decimal("100")
    svc_pct    = Decimal(str(settings.SERVICE_CHARGE_PERCENTAGE)) / Decimal("100")
    vat_amount = (subtotal * vat_pct).quantize(Decimal("0.01"))
    svc_charge = (subtotal * svc_pct).quantize(Decimal("0.01"))

    # ⚠️ باج حقيقي كان هنا (اتصلح 2026-07-05): لو الكاشير طبّق خصم الأول (%)
    # وبعدين ألغى صنف، discount_amount كان بيفضل نفس المبلغ الثابت القديم —
    # محسوب على subtotal الأكبر قبل الإلغاء. النتيجة: نسبة الخصم الفعلية على
    # الـ subtotal الجديد الأصغر بتزيد عن اللي القاعدة (ConditionalDiscount)
    # سمحت بيه فعليًا (تسريب إيراد بسيط)، وممكن كمان الطلب يفضل "مؤهل" لخصم
    # كان شرطه (مثلاً total_amount>=500) بقى مش متحقق خالص بعد الإلغاء.
    # الحل: أعد تقييم نفس الـ rule (لو موجودة) على الـ subtotal الجديد بدل ما
    # نسيب الرقم القديم زي ما هو.
    discount_amount = order.discount_amount
    applied_rule_id = order.applied_discount_rule_id
    if applied_rule_id:
        discount_amount, applied_rule_id = _recompute_discount_for_rule(
            db, applied_rule_id, subtotal, order.created_at,
        )

    total = max(Decimal("0"), subtotal + vat_amount + svc_charge - discount_amount)

    order.subtotal                 = subtotal
    order.vat_amount               = vat_amount
    order.service_charge           = svc_charge
    order.discount_amount          = discount_amount
    order.applied_discount_rule_id = applied_rule_id
    order.total                    = total

    db.commit()
    db.refresh(order)
    return order


def _recompute_discount_for_rule(
    db: Session, rule_id: int, new_subtotal: Decimal, order_date,
) -> tuple[Decimal, Optional[int]]:
    """يعيد حساب خصم قاعدة معيّنة (اللي كانت متطبّقة على الطلب) على subtotal
    جديد أصغر (بعد إلغاء صنف) — يستخدم نفس محرك الخصم بتاع apply_order_discount
    بدل ما يسيب discount_amount قديم غير متسق. لو القاعدة اتشالت/بقت غير نشطة/
    مبقتش مؤهلة على الـ subtotal الجديد، الخصم بيتصفّر بدل ما يفضل رقم غلط."""
    try:
        from app.modules.finance.models import ConditionalDiscount  # noqa: PLC0415
    except ImportError:
        return Decimal("0"), None

    rule_orm = db.query(ConditionalDiscount).filter(ConditionalDiscount.id == rule_id).first()
    if not rule_orm or not rule_orm.is_active:
        return Decimal("0"), None

    rule = DiscountRule(
        id=rule_orm.id,
        condition_type=rule_orm.condition_type,
        condition_value=rule_orm.condition_value,
        discount_type=rule_orm.discount_type,
        discount_value=rule_orm.discount_value,
        max_uses=rule_orm.max_uses,
        valid_from=rule_orm.valid_from,
        valid_until=rule_orm.valid_until,
        priority=rule_orm.priority,
        uses_count=rule_orm.uses_count,
    )
    ctx = OrderContext(
        total_amount=new_subtotal,
        item_count=0,
        order_date=order_date.date() if order_date else date.today(),
    )
    result = calculate_discount(new_subtotal, [rule], ctx)
    return result.amount_saved, result.rule_id


def refund_order_item(db: Session, order_id: int, item_id: int, reason: str, refunded_by: int) -> Order:
    """مرتجع بعد الدفع — الميزة اللي void_order_item كانت بترشد ليها بالاسم
    ('استخدم مرتجع بعد الدفع') من غير ما تكون موجودة فعليًا. عكس
    void_order_item: هنا الطلب المدفوع بالفعل — subtotal/vat/service/total
    الأصليين بيفضلوا زي ما هم (سجل تاريخي للفاتورة الأصلية)، وبدل كده بيتسجّل
    refunded_amount تراكمي + الأثر المالي بيتعكس فعليًا (قيد عكسي لو كاش
    فوري، أو تقليل شحنة الفوليو لو Charge to Room)."""
    order = _get_order_or_404(db, order_id)
    if order.status != "paid":
        raise ValueError(f"المرتجع بعد الدفع متاح بس للطلبات المدفوعة — الطلب ده حالته '{order.status}'")

    item = crud.get_order_item(db, order_id, item_id)
    if not item:
        raise ValueError(f"الصنف {item_id} غير موجود في هذا الطلب")
    if item.status in ("cancelled", "refunded"):
        raise ValueError("الصنف ده ملغي/مرتجع بالفعل")

    extras_total = sum((e.price_addition for e in item.extras), Decimal("0"))
    item_gross = (item.unit_price + extras_total) * item.quantity
    # نصيب الصنف من الضريبة/الخدمة بنفس نسبته من subtotal الأصلي المدفوع فعلاً
    share_ratio = (item_gross / order.subtotal) if order.subtotal > 0 else Decimal("0")
    refund_vat = (order.vat_amount * share_ratio).quantize(Decimal("0.01"))
    refund_svc = (order.service_charge * share_ratio).quantize(Decimal("0.01"))
    refund_amount = item_gross + refund_vat + refund_svc

    crud.refund_order_item(db, item, reason, refunded_by)
    order.refunded_amount = (order.refunded_amount or Decimal("0")) + refund_amount

    active_items = [i for i in order.items if i.status not in ("cancelled", "refunded")]
    if not active_items:
        order.status = "refunded"

    if order.folio_id:
        _reduce_folio_charge_for_refund(db, order, refund_amount)
    else:
        _post_order_refund_reversal_journal(db, order, refund_amount)

    db.commit()
    db.refresh(order)
    return order


def _reduce_folio_charge_for_refund(db: Session, order: Order, refund_amount: Decimal) -> None:
    """يقلّل شحنة الفوليو (Charge to Room) المرتبطة بالطلب ده بمقدار المرتجع،
    ويعيد حساب Folio.total. مايعملش حاجة (بصمت) لو الفوليو اتقفل بالفعل —
    نفس فلسفة _post_order_revenue_journal: فشل التسوية المحاسبية ميوقفش
    إتمام المرتجع نفسه، بس التقرير في الحالة دي محتاج مراجعة يدوية."""
    try:
        from app.modules.finance import crud as finance_crud  # noqa: PLC0415
        from app.modules.finance.models import FolioCharge  # noqa: PLC0415

        # ⚠️ باج حقيقي تاني كان هنا (اتصلح): الفلترة كانت بس بـ ref_order_id،
        # وده رقم PK جدول Order (المطعم) — لكن نفس العمود ده بيتخزّن فيه كمان
        # ref_order_id بتاع CafeOrder على FolioCharge تانية (charge_type="cafe")
        # ممكن يكون بنفس الرقم فعليًا لأوردر تاني تمامًا في فوليو ضيف مختلف.
        # من غير charge_type="restaurant" + folio_id في الفلتر، مرتجع صنف من
        # المطعم كان ممكن (نظريًا) يقلّل شحنة كافيه/فوليو ضيف تاني بالغلط لو
        # الأرقام اتصادفت.
        charge = (
            db.query(FolioCharge)
            .filter_by(ref_order_id=order.id, folio_id=order.folio_id, charge_type="restaurant")
            .first()
        )
        if not charge:
            return
        folio = finance_crud.get_folio(db, order.folio_id)
        if not folio or folio.status == "closed":
            return
        # ⚠️ باج حقيقي كان هنا (اتصلح): gross_before/الـ ratio كانوا بيتجاهلوا
        # service_charge خالص — مرتجع كامل على طلب اتحمّل على الغرفة كان بيصفّر
        # amount/vat_amount بس ويسيب charge.service_charge زي ما هو للأبد، يعني
        # الضيف يفضل محمّل عليه قيمة خدمة لصنف اترجع فعليًا.
        gross_before = charge.amount + charge.vat_amount + charge.service_charge
        new_gross = max(Decimal("0"), gross_before - refund_amount)
        ratio = (new_gross / gross_before) if gross_before > 0 else Decimal("0")
        charge.amount = (charge.amount * ratio).quantize(Decimal("0.01"))
        charge.vat_amount = (charge.vat_amount * ratio).quantize(Decimal("0.01"))
        charge.service_charge = (charge.service_charge * ratio).quantize(Decimal("0.01"))
        db.flush()
        finance_crud.recalculate_folio_total(db, folio)
        # عكس نصيب المرتجع من قيد _post_order_folio_charge_journal الأصلي —
        # لازم يترحّل من غير ما يوقف باقي المرتجع لو فشل، نفس فلسفة الدالة دي.
        _post_order_folio_refund_reversal_journal(db, order, refund_amount)
    except Exception:
        pass


def _post_order_folio_refund_reversal_journal(db: Session, order: Order, refund_amount: Decimal) -> None:
    """عكس _post_order_folio_charge_journal — Dr. إيراد المطعم (4200) /
    Cr. ذمم الفوليو (1150) — بيلغي نصيب الصنف المرتجع من قيد الإيراد
    الأصلي المرحّل وقت تحميل الطلب على الغرفة."""
    from app.core.config import settings  # noqa: PLC0415
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415
    from app.resort_os.timezone_utils import local_today  # noqa: PLC0415

    post_simple_revenue_journal(
        db, order.branch_id, local_today(settings.TIMEZONE),
        debit_account_code="4200", credit_account_code="1150",
        amount=refund_amount,
        reference=f"ORD-REFUND-{order.order_number}",
        description=f"مرتجع بعد الدفع (محمّل على الغرفة) — {order.order_number}",
        source="restaurant_folio_refund", source_id=order.id,
    )


def _post_order_refund_reversal_journal(db: Session, order: Order, refund_amount: Decimal) -> None:
    """عكس _post_order_revenue_journal — Dr. Restaurant Revenue (4200) /
    Cr. Cash (1100) — بيلغي نصيب الصنف المرتجع من قيد الإيراد الأصلي."""
    from app.core.config import settings  # noqa: PLC0415
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415
    from app.resort_os.timezone_utils import local_today  # noqa: PLC0415

    post_simple_revenue_journal(
        db, order.branch_id, local_today(settings.TIMEZONE),
        debit_account_code="4200", credit_account_code="1100",
        amount=refund_amount,
        reference=f"ORD-REFUND-{order.order_number}",
        description=f"مرتجع بعد الدفع — {order.order_number}",
        source="restaurant_refund", source_id=order.id,
    )


def get_kds_tickets(
    db: Session,
    branch_id: int,
    stations: Optional[list[str]] = None,
    module: str = "restaurant",
) -> list[KitchenTicket]:
    """يرجّع تذاكر الـ KDS المعلقة لفرع معيّن — فلترة اختيارية حسب المحطة و/أو الموديول
    (مطعم أو كافيه، كل واحد فيهم بيعمل تذاكره في نفس الجدول)."""
    return crud.list_pending_tickets(db, branch_id, stations=stations, module=module)


def generate_receipt_pdf(db: Session, order_id: int) -> bytes:
    """يُولّد PDF إيصال طلب مطعم (مقاس رول حراري 80mm — نفس مقاس طابعات الكاشير الحقيقية)."""
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    order = _get_order_or_404(db, order_id)
    table_label = order.table.table_number if order.table else "—"

    fields = [
        ("رقم الطلب",    order.order_number),
        ("نوع الطلب",    order.order_type),
        ("الطاولة",      table_label),
    ]
    # سطر منفصل لكل صنف — أوضح على رول حراري ضيّق من نص واحد مجمّع
    for item in order.items:
        fields.append((f"{item.quantity}× {item.name}", f"{item.unit_price:,.2f} EGP"))
    fields += [
        ("المجموع قبل الضريبة", f"{order.subtotal:,.2f} EGP"),
        ("ضريبة (VAT)",  f"{order.vat_amount:,.2f} EGP"),
        ("رسوم الخدمة",  f"{order.service_charge:,.2f} EGP"),
    ]
    if order.discount_amount and order.discount_amount > 0:
        fields.append(("الخصم", f"-{order.discount_amount:,.2f} EGP"))

    return builder.receipt_pdf_thermal(
        reference=order.order_number,
        title="إيصال المطعم",
        fields=fields,
        total=float(order.total),
        currency="EGP",
        note="شكراً لزيارتكم — الخيمة بيتش ريزورت",
    )


def apply_order_discount(db: Session, order_id: int) -> Order:
    order = _get_order_or_404(db, order_id)

    if order.status in ("paid", "cancelled"):
        raise ValueError("لا يمكن تطبيق خصم على طلب مغلق")

    # جلب discount rules من finance module
    rules: list[DiscountRule] = []
    try:
        from app.modules.finance.models import ConditionalDiscount  # noqa: PLC0415
        rules_orm = (
            db.query(ConditionalDiscount)
            .filter(
                ConditionalDiscount.branch_id == order.branch_id,
                ConditionalDiscount.is_active.is_(True),
            )
            .all()
        )
        rules = [
            DiscountRule(
                id=r.id,
                condition_type=r.condition_type,
                condition_value=r.condition_value,
                discount_type=r.discount_type,
                discount_value=r.discount_value,
                max_uses=r.max_uses,
                valid_from=r.valid_from,
                valid_until=r.valid_until,
                priority=r.priority,
                uses_count=r.uses_count,
            )
            for r in rules_orm
        ]
    except ImportError:
        pass

    total_items = sum(item.quantity for item in order.items)
    ctx = OrderContext(
        total_amount=order.subtotal,
        item_count=total_items,
        order_date=order.created_at.date() if order.created_at else date.today(),
    )

    result = calculate_discount(order.subtotal, rules, ctx)
    order = crud.update_order_discount(
        db, order,
        discount_amount=result.amount_saved,
        rule_id=result.rule_id,
    )

    # زيادة uses_count
    if result.applied and result.rule_id:
        try:
            from app.modules.finance.crud import increment_discount_uses  # noqa: PLC0415
            increment_discount_uses(db, result.rule_id)
        except ImportError:
            pass

    db.commit()
    db.refresh(order)
    return order


# ─────────────────────── Reporting / Food Cost ────────────────────────
# تقرير تكلفة الطعام (Food Cost / COGS) — راجع app.resort_os.food_cost_engine
# للفورمولا نفسها؛ هنا بس تجميع بيانات الوصفة (recipe_lines) والمبيعات
# الفعلية (طلبات مدفوعة) من الداتابيز قبل ما تتغذى للـ engine.

def get_food_cost_report(
    db: Session,
    branch_id: int,
    date_from: date,
    date_to: date,
    threshold_pct: Decimal = DEFAULT_FOOD_COST_THRESHOLD_PCT,
) -> FoodCostReportResponse:
    """تقرير كامل لكل أصناف المطعم في الفرع: التكلفة النظرية (وصفة × كمية
    مباعة فعليًا) مقابل الإيراد الفعلي، لكل صنف ولكل يوم (trend) وملخص
    إجمالي — استعلامان بس (كل الأصناف + كل المبيعات المدفوعة في المدى)،
    وباقي التجميع (لكل صنف/لكل يوم) في الذاكرة، مفيش N+1."""
    range_start, _ = local_date_to_utc_range(date_from, settings.TIMEZONE)
    _, range_end = local_date_to_utc_range(date_to, settings.TIMEZONE)

    items = crud.list_menu_items_for_food_cost(db, branch_id)
    sales_rows = crud.get_paid_order_items_for_food_cost(db, branch_id, range_start, range_end)

    qty_by_item: dict[int, int] = defaultdict(int)
    revenue_by_item: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    # لكل يوم محلي: {menu_item_id: (كمية, إيراد)} — أساس الـ trend اليومي.
    by_day: dict[date, dict[int, list]] = defaultdict(lambda: defaultdict(lambda: [0, Decimal("0")]))

    for menu_item_id, unit_price, quantity, created_at in sales_rows:
        line_revenue = unit_price * quantity
        qty_by_item[menu_item_id] += quantity
        revenue_by_item[menu_item_id] += line_revenue
        local_day = utc_naive_to_local_date(created_at, settings.TIMEZONE)
        day_entry = by_day[local_day][menu_item_id]
        day_entry[0] += quantity
        day_entry[1] += line_revenue

    lines: list[FoodCostReportLine] = []
    unit_cost_by_item: dict[int, Decimal] = {}
    recipe_item_ids: set[int] = set()
    total_revenue = Decimal("0")
    total_theoretical_cost = Decimal("0")
    items_missing_recipe = 0
    items_missing_recipe_revenue = Decimal("0")

    for item in items:
        has_recipe = bool(item.recipe_lines)
        recipe_lines = [
            ((line.product.cost_price if line.product else None) or Decimal("0"), line.quantity_per_unit)
            for line in item.recipe_lines
        ]
        quantity_sold = qty_by_item.get(item.id, 0)
        revenue = revenue_by_item.get(item.id, Decimal("0"))
        result = compute_food_cost_result(recipe_lines, quantity_sold, revenue)
        unit_cost_by_item[item.id] = result.theoretical_unit_cost
        if has_recipe:
            recipe_item_ids.add(item.id)

        if quantity_sold > 0:
            if has_recipe:
                total_revenue += revenue
                total_theoretical_cost += result.theoretical_total_cost
            else:
                # مفيش وصفة → التكلفة "غير معروفة" مش صفر — مُستبعدة من
                # الإجمالي المالي (وباقي trend) عشان ما تضخّمش هامش الربح
                # بالغلط، ومعدودة هنا صراحةً عشان تظهر في الملخص كفجوة
                # بيانات لازم تتقفل.
                items_missing_recipe += 1
                items_missing_recipe_revenue += revenue

        lines.append(FoodCostReportLine(
            menu_item_id=item.id,
            menu_item_name=item.name,
            has_recipe=has_recipe,
            quantity_sold=quantity_sold,
            revenue=revenue,
            theoretical_unit_cost=result.theoretical_unit_cost,
            theoretical_total_cost=result.theoretical_total_cost,
            food_cost_pct=result.food_cost_pct if has_recipe else None,
            gross_margin_amount=result.gross_margin_amount,
            gross_margin_pct=result.gross_margin_pct if has_recipe else None,
            exceeds_threshold=has_recipe and exceeds_threshold(result.food_cost_pct, threshold_pct),
        ))

    # trend: نفس استبعاد "مفيش وصفة" بتاع الملخص — وإلا نسبة تكلفة الطعام
    # اليومية هتبقى مخفّضة بالغلط بإيراد أصناف تكلفتها غير معروفة أصلاً.
    trend: list[CogsTrendPoint] = []
    current = date_from
    while current <= date_to:
        day_revenue = Decimal("0")
        day_cost = Decimal("0")
        for menu_item_id, (qty, item_revenue) in by_day.get(current, {}).items():
            if menu_item_id in recipe_item_ids:
                day_revenue += item_revenue
                day_cost += unit_cost_by_item.get(menu_item_id, Decimal("0")) * qty
        day_cost = day_cost.quantize(Decimal("0.01"))
        trend.append(CogsTrendPoint(
            date=current,
            revenue=day_revenue,
            theoretical_cost=day_cost,
            food_cost_pct=(day_cost / day_revenue * 100).quantize(Decimal("0.01")) if day_revenue > 0 else None,
        ))
        current += timedelta(days=1)

    summary_pct = (total_theoretical_cost / total_revenue * 100).quantize(Decimal("0.01")) if total_revenue > 0 else None
    summary_margin_pct = (
        ((total_revenue - total_theoretical_cost) / total_revenue * 100).quantize(Decimal("0.01"))
        if total_revenue > 0 else None
    )
    summary = GrossMarginSummary(
        branch_id=branch_id,
        date_from=date_from,
        date_to=date_to,
        threshold_pct=threshold_pct,
        total_revenue=total_revenue,
        total_theoretical_cost=total_theoretical_cost,
        food_cost_pct=summary_pct,
        gross_margin_amount=(total_revenue - total_theoretical_cost).quantize(Decimal("0.01")),
        gross_margin_pct=summary_margin_pct,
        items_missing_recipe=items_missing_recipe,
        items_missing_recipe_revenue=items_missing_recipe_revenue,
    )

    alerts = [line for line in lines if line.exceeds_threshold]
    return FoodCostReportResponse(lines=lines, alerts=alerts, trend=trend, summary=summary)
