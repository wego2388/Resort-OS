"""app/modules/cafe/services.py — نفس منطق restaurant مع جداول cafe"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.cafe import crud
from app.modules.cafe.models import CafeItem, CafeItemRecipeLine, CafeOrder
from app.modules.cafe.schemas import (
    CafeCogsTrendPoint, CafeFoodCostReportLine, CafeFoodCostReportResponse, CafeGrossMarginSummary,
    CafeItemRecipeLineCreate, CafeItemRecipeLineUpdate, CafeOrderCreate,
)
from app.resort_os.discount_engine import DiscountRule, OrderContext, OrderLineItem, calculate_discount
from app.resort_os.food_cost_engine import DEFAULT_FOOD_COST_THRESHOLD_PCT, compute_food_cost_result, exceeds_threshold
from app.resort_os.timezone_utils import (
    local_date_to_utc_range, local_now,
    utc_naive_to_local_date, utc_naive_to_local_time,
)


def _get_order_or_404(db: Session, order_id: int) -> CafeOrder:
    order = crud.get_order(db, order_id)
    if not order:
        raise ValueError(f"الطلب {order_id} غير موجود")
    return order


def _resolve_extras(db: Session, cafe_item, extra_ids: list[int]) -> tuple[list[dict], Decimal]:
    """يتحقق من الإضافات المختارة (تتبع نفس الصنف + قواعد min/max_select
    لكل مجموعة) ويرجّع (extras snapshot data, إجمالي الإضافة للوحدة الواحدة).
    نفس منطق restaurant._resolve_extras بالضبط."""
    if not cafe_item.extra_groups and not extra_ids:
        return [], Decimal("0")

    valid_extra_ids = {
        extra.id for group in cafe_item.extra_groups for extra in group.options
    }
    for extra_id in extra_ids:
        if extra_id not in valid_extra_ids:
            raise ValueError(f"الإضافة {extra_id} لا تنتمي لصنف '{cafe_item.name}'")

    selected = set(extra_ids)
    extras_data: list[dict] = []
    price_addition = Decimal("0")

    for group in cafe_item.extra_groups:
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
# نفس منطق restaurant.services (compute_menu_item_cost/build_recipe_line_read/
# add_recipe_line/...) بالضبط — راجع التعليقات هناك للتفاصيل الكاملة.

def compute_cafe_item_cost(item: CafeItem) -> Decimal:
    if item.recipe_lines:
        total = Decimal("0")
        for line in item.recipe_lines:
            unit_cost = (line.product.cost_price if line.product else None) or Decimal("0")
            total += line.quantity_per_unit * unit_cost
        return total.quantize(Decimal("0.01"))
    return item.cost if item.cost is not None else Decimal("0")


def build_recipe_line_read(line: CafeItemRecipeLine) -> dict:
    unit_cost = (line.product.cost_price if line.product else None) or Decimal("0")
    return {
        "id": line.id,
        "cafe_item_id": line.cafe_item_id,
        "product_id": line.product_id,
        "product_name": line.product.name if line.product else "",
        "product_unit": line.product.unit if line.product else "",
        "quantity_per_unit": line.quantity_per_unit,
        "unit_cost": unit_cost,
        "line_cost": (line.quantity_per_unit * unit_cost).quantize(Decimal("0.01")),
        "notes": line.notes,
    }


def add_recipe_line(db: Session, cafe_item_id: int, data: CafeItemRecipeLineCreate) -> CafeItemRecipeLine:
    from app.modules.inventory import crud as inventory_crud  # noqa: PLC0415

    item = crud.get_item(db, cafe_item_id)
    if not item:
        raise ValueError(f"الصنف {cafe_item_id} غير موجود")
    product = inventory_crud.get_product(db, data.product_id)
    if not product:
        raise ValueError(f"المنتج {data.product_id} غير موجود في المخزون")
    if product.branch_id != item.branch_id:
        raise ValueError("المنتج المخزني لازم يكون من نفس فرع الصنف")
    if any(line.product_id == data.product_id for line in item.recipe_lines):
        raise ValueError(f"المنتج '{product.name}' مضاف بالفعل لوصفة هذا الصنف")

    line = crud.create_recipe_line(db, cafe_item_id, data)
    db.commit()
    db.refresh(line)
    return line


def update_recipe_line(db: Session, line_id: int, data: CafeItemRecipeLineUpdate) -> CafeItemRecipeLine:
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
    data: CafeOrderCreate,
    waiter_id: Optional[int] = None,
    hold: bool = False,
) -> CafeOrder:
    if data.table_id:
        table = crud.get_table(db, data.table_id)
        if not table:
            raise ValueError(f"الطاولة {data.table_id} غير موجودة")
        if table.status == "out_of_service":
            raise ValueError(f"الطاولة {table.table_number} خارج الخدمة")

    items_data = []
    subtotal = Decimal("0")

    for item_req in data.items:
        item = crud.get_item(db, item_req.item_id)
        if not item:
            raise ValueError(f"الصنف {item_req.item_id} غير موجود")
        if not item.is_available:
            raise ValueError(f"الصنف '{item.name}' غير متاح حالياً")

        extras_data, extra_price_per_unit = _resolve_extras(db, item, item_req.extra_ids)

        line_total = (item.price + extra_price_per_unit) * item_req.quantity
        subtotal += line_total
        items_data.append({
            "item_id":    item_req.item_id,
            "name":       item.name,
            "unit_price": item.price,
            "quantity":   item_req.quantity,
            "notes":      item_req.notes,
            "extras":     extras_data,
        })

    vat_pct    = Decimal(str(settings.VAT_PERCENTAGE)) / Decimal("100")
    svc_pct    = Decimal(str(settings.SERVICE_CHARGE_PERCENTAGE)) / Decimal("100")
    vat_amount = (subtotal * vat_pct).quantize(Decimal("0.01"))
    svc_charge = (subtotal * svc_pct).quantize(Decimal("0.01"))
    total      = subtotal + vat_amount + svc_charge

    order = crud.create_order(
        db=db, branch_id=data.branch_id, order_type=data.order_type,
        table_id=data.table_id, notes=data.notes,
        subtotal=subtotal, vat_amount=vat_amount,
        service_charge=svc_charge, total=total,
        waiter_id=waiter_id, items_data=items_data,
        status="held" if hold else "open",
        customer_id=data.customer_id,
    )

    if data.table_id and data.order_type == "dine_in":
        table = crud.get_table(db, data.table_id)
        if table:
            crud.update_table_status(db, table, "occupied")

    db.commit()
    db.refresh(order)
    return order


# ── Discount ──────────────────────────────────────────────────────────
# نفس منطق restaurant.services (apply_order_discount/_recompute_discount_for_rule)
# بالظبط — راجع التعليقات هناك للتفاصيل الكاملة. الكافيه ما كانش عنده أي طريقة
# حقيقية يطبّق بيها ConditionalDiscount خالص قبل كده (discount_amount كان
# عمود ميتاته ملوش أي كود بيكتب فيه) — يعني نطاق "outlet" الجديد في الـ
# discount engine (مثال: "10% خصم كافيه بس") كان هيفضل نظري بدون تكامل حقيقي.

def _order_local_date_and_time(order: CafeOrder) -> tuple[date, time]:
    """راجع restaurant.services._order_local_date_and_time للتفاصيل الكاملة —
    نفس المنطق بالظبط (created_at UTC naive → تاريخ/وقت بتوقيت القاهرة)."""
    if not order.created_at:
        now_local = local_now(settings.TIMEZONE)
        return now_local.date(), now_local.time()
    return (
        utc_naive_to_local_date(order.created_at, settings.TIMEZONE),
        utc_naive_to_local_time(order.created_at, settings.TIMEZONE),
    )


def _build_discount_line_items(db: Session, order: CafeOrder) -> list[OrderLineItem]:
    """راجع restaurant.services._build_discount_line_items — نفس المنطق
    بالظبط (استعلام واحد لكل الأصناف المميزة، بدون N+1)."""
    active_items = [i for i in order.items if i.status != "cancelled"]
    item_ids = {i.item_id for i in active_items}
    category_by_item: dict[int, int | None] = {}
    if item_ids:
        category_by_item = dict(
            db.query(CafeItem.id, CafeItem.category_id)
            .filter(CafeItem.id.in_(item_ids))
            .all()
        )
    return [
        OrderLineItem(
            item_id=i.item_id,
            quantity=i.quantity,
            unit_price=i.unit_price,
            category_id=category_by_item.get(i.item_id),
        )
        for i in active_items
    ]


def apply_order_discount(db: Session, order_id: int) -> CafeOrder:
    """نفس restaurant.services.apply_order_discount بالظبط، بـ outlet="cafe"
    عشان قواعد scope_type="outlet" تفرّق فعليًا بين مطعم وكافيه."""
    order = _get_order_or_404(db, order_id)

    if order.status in ("paid", "cancelled"):
        raise ValueError("لا يمكن تطبيق خصم على طلب مغلق")

    rules: list[DiscountRule] = []
    try:
        from app.modules.finance.models import ConditionalDiscount  # noqa: PLC0415
        from app.modules.finance.services import discount_rule_from_orm  # noqa: PLC0415
        rules_orm = (
            db.query(ConditionalDiscount)
            .filter(
                ConditionalDiscount.branch_id == order.branch_id,
                ConditionalDiscount.is_active.is_(True),
            )
            .all()
        )
        rules = [discount_rule_from_orm(r) for r in rules_orm]
    except ImportError:
        pass

    total_items = sum(item.quantity for item in order.items)
    order_date, order_time = _order_local_date_and_time(order)
    ctx = OrderContext(
        total_amount=order.subtotal,
        item_count=total_items,
        order_date=order_date,
        order_time=order_time,
        outlet="cafe",
        line_items=_build_discount_line_items(db, order),
    )

    result = calculate_discount(order.subtotal, rules, ctx)
    order = crud.update_order_discount(
        db, order,
        discount_amount=result.amount_saved,
        rule_id=result.rule_id,
    )

    if result.applied and result.rule_id:
        try:
            from app.modules.finance.crud import increment_discount_uses  # noqa: PLC0415
            increment_discount_uses(db, result.rule_id)
        except ImportError:
            pass

    db.commit()
    db.refresh(order)
    return order


def _recompute_discount_for_rule(
    db: Session, rule_id: int, new_subtotal: Decimal, order: CafeOrder,
) -> tuple[Decimal, Optional[int]]:
    """راجع restaurant.services._recompute_discount_for_rule — نفس المنطق
    بالظبط، بيتنادى من void_order_item بعد إلغاء صنف."""
    try:
        from app.modules.finance.models import ConditionalDiscount  # noqa: PLC0415
        from app.modules.finance.services import discount_rule_from_orm  # noqa: PLC0415
    except ImportError:
        return Decimal("0"), None

    rule_orm = db.query(ConditionalDiscount).filter(ConditionalDiscount.id == rule_id).first()
    if not rule_orm or not rule_orm.is_active:
        return Decimal("0"), None

    order_date, order_time = _order_local_date_and_time(order)
    ctx = OrderContext(
        total_amount=new_subtotal,
        item_count=0,
        order_date=order_date,
        order_time=order_time,
        outlet="cafe",
        line_items=_build_discount_line_items(db, order),
    )
    result = calculate_discount(new_subtotal, [discount_rule_from_orm(rule_orm)], ctx)
    return result.amount_saved, result.rule_id


def generate_receipt_pdf(db: Session, order_id: int) -> bytes:
    """يُولّد PDF إيصال طلب كافيه (مقاس رول حراري 80mm — نفس مقاس طابعات الكاشير الحقيقية)."""
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    order = _get_order_or_404(db, order_id)
    fields = [
        ("رقم الطلب",    order.order_number),
        ("نوع الطلب",    order.order_type),
    ]
    # سطر منفصل لكل صنف — أوضح على رول حراري ضيّق من نص واحد مجمّع
    for item in order.items:
        fields.append((f"{item.quantity}× {item.name}", f"{item.unit_price:,.2f} EGP"))
    fields += [
        ("المجموع قبل الضريبة", f"{order.subtotal:,.2f} EGP"),
        ("ضريبة (VAT)",  f"{order.vat_amount:,.2f} EGP"),
        ("رسوم الخدمة",  f"{order.service_charge:,.2f} EGP"),
    ]
    return builder.receipt_pdf_thermal(
        reference=order.order_number,
        title="إيصال الكافيه",
        fields=fields,
        total=float(order.total),
        currency="EGP",
        note="شكراً لزيارتكم — الخيمة بيتش ريزورت",
    )


def update_order_status(
    db: Session, order_id: int, new_status: str, charge_to_room_id: Optional[int] = None,
) -> CafeOrder:
    order = _get_order_or_404(db, order_id)
    if order.status in ("paid", "cancelled"):
        raise ValueError(f"لا يمكن تغيير حالة طلب '{order.status}'")

    if new_status == "paid" and charge_to_room_id and not order.folio_id:
        from app.modules.pms.services import find_active_folio_for_room  # noqa: PLC0415
        folio_id = find_active_folio_for_room(db, order.branch_id, charge_to_room_id)
        if not folio_id:
            raise ValueError(f"مفيش ضيف مسجّل دخول في الغرفة {charge_to_room_id} حاليًا")
        order.folio_id = folio_id

    order = crud.update_order_status(db, order, new_status)

    # إرسال ticket للمطبخ عند تحويل الطلب لـ in_kitchen
    if new_status == "in_kitchen":
        from app.modules.restaurant.crud import create_kitchen_ticket  # noqa: PLC0415
        items_snapshot = [
            {
                "order_item_id": item.id,
                "name":          item.name,
                "quantity":      item.quantity,
                "notes":         item.notes,
            }
            for item in order.items
        ]
        create_kitchen_ticket(
            db,
            order_id=order.id,
            branch_id=order.branch_id,
            station="bar",
            items_snapshot=items_snapshot,
            module="cafe",
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
                charge_type="cafe",
                description=f"طلب {order.order_number}",
                amount=order.subtotal,
                vat_amount=order.vat_amount,
                # ⚠️ باج حقيقي كان هنا (اتصلح) — نفس باج restaurant.services:
                # service_charge كان بيضيع خالص لما الطلب يتحمّل على الغرفة.
                service_charge=order.service_charge,
                posted_at=datetime.utcnow(),
                ref_order_id=order.id,
            )
            finance_crud.add_charge(db, order.folio_id, charge_data)
            # ⚠️ باج حقيقي كان هنا (اتصلح 2026-07-04): add_charge لوحدها بتضيف
            # صف FolioCharge بس — Folio.total (العمود المخزّن اللي GET
            # /finance/folios بيرجّعه مباشرة) كان بيفضل زي ما هو، من غير أي
            # تحديث. checkout نفسه كان آمن (folio_engine.FolioSummary بتحسب
            # المجموع من folio.charges لحظيًا مش من العمود ده)، لكن أي شاشة/تقرير
            # بيعرض Folio.total مباشرة كان بيوريه رقم قديم ناقص كل شحنات
            # Charge-to-Room من الكافيه.
            folio = finance_crud.get_folio(db, order.folio_id)
            if folio:
                finance_crud.recalculate_folio_total(db, folio)
        except Exception:
            pass  # ميمنعش إتمام الدفع لو فشل نشر الـ charge على الفوليو

    # قيد إيراد الكافيه — فورًا في الحالتين (كاش أو محمّل على فوليو غرفة)، بس
    # لحساب مختلف حسب طريقة الدفع (راجع نفس الملاحظة والباج المُصلَح في
    # restaurant.services._post_order_folio_charge_journal) + خصم المخزون +
    # تحديث إحصائيات العميل عند الدفع
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


def _deduct_inventory_for_order(db: Session, order: CafeOrder) -> None:
    """يخصم المخزون لكل صنف في الطلب — نفس أولوية
    restaurant._deduct_inventory_for_order بالظبط: وصفة حقيقية (recipe_lines)
    أولاً (بمخزون سالب مسموح + تحذير)، وإلا fallback لربط 1:1 القديم
    (linked_product_id، بدون مخزون سالب — سلوك مؤكد باختبارات موجودة). فشل
    صنف واحد ميوقفش باقي الأصناف ولا يوقف إتمام الدفع."""
    from app.modules.inventory import crud as inventory_crud  # noqa: PLC0415
    from app.modules.inventory import services as inventory_services  # noqa: PLC0415

    for order_item in order.items:
        if order_item.status == "cancelled":
            continue
        try:
            item = crud.get_item(db, order_item.item_id)
            if not item:
                continue
            if item.recipe_lines:
                for line in item.recipe_lines:
                    product = inventory_crud.get_product(db, line.product_id)
                    if not product or not product.warehouse_id:
                        continue
                    inventory_services.consume_stock(
                        db,
                        branch_id=order.branch_id,
                        product_id=product.id,
                        warehouse_id=product.warehouse_id,
                        quantity=line.quantity_per_unit * order_item.quantity,
                        reference_type="cafe_order",
                        reference_id=order.id,
                        moved_by=0,
                        allow_negative=True,
                    )
                continue
            if not item.linked_product_id:
                continue
            product = inventory_crud.get_product(db, item.linked_product_id)
            if not product or not product.warehouse_id:
                continue
            inventory_services.consume_stock(
                db,
                branch_id=order.branch_id,
                product_id=product.id,
                warehouse_id=product.warehouse_id,
                quantity=Decimal(order_item.quantity),
                reference_type="cafe_order",
                reference_id=order.id,
                moved_by=0,
            )
        except Exception:
            continue


def _post_order_revenue_journal(db: Session, order: "CafeOrder") -> None:
    """Dr. Cash (1100) / Cr. Cafe Revenue (4400) — دفع كاش/كارت فوري."""
    from app.core.config import settings  # noqa: PLC0415
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415
    from app.resort_os.timezone_utils import local_today  # noqa: PLC0415

    post_simple_revenue_journal(
        db, order.branch_id, local_today(settings.TIMEZONE),
        debit_account_code="1100", credit_account_code="4400",
        amount=order.total or Decimal("0"),
        reference=f"ORD-{order.order_number}",
        description=f"إيرادات كافيه — {order.order_number}",
        source="cafe", source_id=order.id,
    )


def _post_order_folio_charge_journal(db: Session, order: "CafeOrder") -> None:
    """Dr. ذمم الفوليو (1150) / Cr. إيراد الكافيه (4400) — طلب محمّل على
    فوليو غرفة. راجع restaurant.services._post_order_folio_charge_journal
    للتفاصيل الكاملة — نفس المنطق بالظبط."""
    from app.core.config import settings  # noqa: PLC0415
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415
    from app.resort_os.timezone_utils import local_today  # noqa: PLC0415

    post_simple_revenue_journal(
        db, order.branch_id, local_today(settings.TIMEZONE),
        debit_account_code="1150", credit_account_code="4400",
        amount=order.total or Decimal("0"),
        reference=f"ORD-{order.order_number}",
        description=f"إيرادات كافيه (محمّل على الغرفة) — {order.order_number}",
        source="cafe_folio_charge", source_id=order.id,
    )


def void_order_item(db: Session, order_id: int, item_id: int, reason: str, voided_by: int) -> CafeOrder:
    """إلغاء صنف واحد من الطلب مع سبب إجباري + توثيق مين لغاه — نفس منطق
    restaurant.void_order_item بالضبط، بيعيد حساب subtotal/vat/service/total
    من الأصناف الفعّالة بس."""
    order = _get_order_or_404(db, order_id)
    if order.status in ("paid", "cancelled"):
        raise ValueError(f"لا يمكن إلغاء صنف من طلب '{order.status}' — استخدم مرتجع بعد الدفع")

    item = crud.get_order_item(db, order_id, item_id)
    if not item:
        raise ValueError(f"الصنف {item_id} غير موجود في هذا الطلب")
    if item.status == "cancelled":
        raise ValueError("الصنف ده ملغي بالفعل")

    crud.void_order_item(db, item, reason, voided_by)

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

    # راجع restaurant.services.void_order_item لتفاصيل الباج الأصلي اللي ده
    # بيصلحه: خصم % محسوب على subtotal أكبر قبل الإلغاء لازم يتصلح على
    # subtotal الجديد الأصغر، وإلا نسبة الخصم الفعلية تزيد عن اللي القاعدة سمحت
    # بيه (أو الطلب يفضل "مؤهل" لخصم مبقاش شرطه متحقق أصلاً).
    discount_amount = order.discount_amount
    applied_rule_id = order.applied_discount_rule_id
    if applied_rule_id:
        discount_amount, applied_rule_id = _recompute_discount_for_rule(
            db, applied_rule_id, subtotal, order,
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


def refund_order_item(db: Session, order_id: int, item_id: int, reason: str, refunded_by: int) -> CafeOrder:
    """مرتجع بعد الدفع — نفس منطق restaurant.refund_order_item بالضبط. الطلب
    المدفوع بالفعل بيفضل subtotal/vat/service/total الأصليين زي ما هم (سجل
    تاريخي)، وrefunded_amount تراكمي بيتسجّل بدل كده + الأثر المالي بيتعكس فعليًا."""
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


def _reduce_folio_charge_for_refund(db: Session, order: CafeOrder, refund_amount: Decimal) -> None:
    """يقلّل شحنة الفوليو (Charge to Room) المرتبطة بالطلب ده بمقدار المرتجع
    ويعيد حساب Folio.total — راجع restaurant.services للنسخة المرجعية."""
    try:
        from app.modules.finance import crud as finance_crud  # noqa: PLC0415
        from app.modules.finance.models import FolioCharge  # noqa: PLC0415

        # ⚠️ باج حقيقي تاني كان هنا (اتصلح) — نفس باج restaurant.services: الفلترة
        # كانت بس بـ ref_order_id، رقم مش فريد عبر الموديولات (نفس الرقم ممكن
        # يتكرر في Order بتاع المطعم لطلب في فوليو ضيف تاني تمامًا). charge_type
        # + folio_id بيضمنوا إننا بنعدّل شحنة الكافيه الصح بس.
        charge = (
            db.query(FolioCharge)
            .filter_by(ref_order_id=order.id, folio_id=order.folio_id, charge_type="cafe")
            .first()
        )
        if not charge:
            return
        folio = finance_crud.get_folio(db, order.folio_id)
        if not folio or folio.status == "closed":
            return
        # ⚠️ باج حقيقي كان هنا (اتصلح) — نفس باج restaurant.services: gross_before
        # والـ ratio كانوا بيتجاهلوا service_charge، فمرتجع كامل كان يسيب
        # charge.service_charge زي ما هو للأبد بدل ما يترجع مع باقي المبلغ.
        gross_before = charge.amount + charge.vat_amount + charge.service_charge
        new_gross = max(Decimal("0"), gross_before - refund_amount)
        ratio = (new_gross / gross_before) if gross_before > 0 else Decimal("0")
        charge.amount = (charge.amount * ratio).quantize(Decimal("0.01"))
        charge.vat_amount = (charge.vat_amount * ratio).quantize(Decimal("0.01"))
        charge.service_charge = (charge.service_charge * ratio).quantize(Decimal("0.01"))
        db.flush()
        finance_crud.recalculate_folio_total(db, folio)
        _post_order_folio_refund_reversal_journal(db, order, refund_amount)
    except Exception:
        pass


def _post_order_folio_refund_reversal_journal(db: Session, order: CafeOrder, refund_amount: Decimal) -> None:
    """عكس _post_order_folio_charge_journal — Dr. إيراد الكافيه (4400) /
    Cr. ذمم الفوليو (1150)."""
    from app.core.config import settings  # noqa: PLC0415
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415
    from app.resort_os.timezone_utils import local_today  # noqa: PLC0415

    post_simple_revenue_journal(
        db, order.branch_id, local_today(settings.TIMEZONE),
        debit_account_code="4400", credit_account_code="1150",
        amount=refund_amount,
        reference=f"ORD-REFUND-{order.order_number}",
        description=f"مرتجع بعد الدفع (محمّل على الغرفة) — {order.order_number}",
        source="cafe_folio_refund", source_id=order.id,
    )


def _post_order_refund_reversal_journal(db: Session, order: CafeOrder, refund_amount: Decimal) -> None:
    """عكس _post_order_revenue_journal — Dr. Cafe Revenue (4400) / Cr. Cash (1100)."""
    from app.core.config import settings  # noqa: PLC0415
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415
    from app.resort_os.timezone_utils import local_today  # noqa: PLC0415

    post_simple_revenue_journal(
        db, order.branch_id, local_today(settings.TIMEZONE),
        debit_account_code="4400", credit_account_code="1100",
        amount=refund_amount,
        reference=f"ORD-REFUND-{order.order_number}",
        description=f"مرتجع بعد الدفع — {order.order_number}",
        source="cafe_refund", source_id=order.id,
    )


# ─────────────────────── Reporting / Food Cost ────────────────────────
# نفس منطق restaurant.services.get_food_cost_report بالضبط — راجع التعليقات
# هناك للتفاصيل الكاملة (استبعاد الأصناف الملغاة بس مش المرتجعة، استبعاد
# إيراد/تكلفة الأصناف الناقصة الوصفة من الإجمالي والـ trend، إلخ).

def get_food_cost_report(
    db: Session,
    branch_id: int,
    date_from: date,
    date_to: date,
    threshold_pct: Decimal = DEFAULT_FOOD_COST_THRESHOLD_PCT,
) -> CafeFoodCostReportResponse:
    range_start, _ = local_date_to_utc_range(date_from, settings.TIMEZONE)
    _, range_end = local_date_to_utc_range(date_to, settings.TIMEZONE)

    items = crud.list_items_for_food_cost(db, branch_id)
    sales_rows = crud.get_paid_order_items_for_food_cost(db, branch_id, range_start, range_end)

    qty_by_item: dict[int, int] = defaultdict(int)
    revenue_by_item: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    by_day: dict[date, dict[int, list]] = defaultdict(lambda: defaultdict(lambda: [0, Decimal("0")]))

    for cafe_item_id, unit_price, quantity, created_at in sales_rows:
        line_revenue = unit_price * quantity
        qty_by_item[cafe_item_id] += quantity
        revenue_by_item[cafe_item_id] += line_revenue
        local_day = utc_naive_to_local_date(created_at, settings.TIMEZONE)
        day_entry = by_day[local_day][cafe_item_id]
        day_entry[0] += quantity
        day_entry[1] += line_revenue

    lines: list[CafeFoodCostReportLine] = []
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
                items_missing_recipe += 1
                items_missing_recipe_revenue += revenue

        lines.append(CafeFoodCostReportLine(
            cafe_item_id=item.id,
            cafe_item_name=item.name,
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

    trend: list[CafeCogsTrendPoint] = []
    current = date_from
    while current <= date_to:
        day_revenue = Decimal("0")
        day_cost = Decimal("0")
        for cafe_item_id, (qty, item_revenue) in by_day.get(current, {}).items():
            if cafe_item_id in recipe_item_ids:
                day_revenue += item_revenue
                day_cost += unit_cost_by_item.get(cafe_item_id, Decimal("0")) * qty
        day_cost = day_cost.quantize(Decimal("0.01"))
        trend.append(CafeCogsTrendPoint(
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
    summary = CafeGrossMarginSummary(
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
    return CafeFoodCostReportResponse(lines=lines, alerts=alerts, trend=trend, summary=summary)
