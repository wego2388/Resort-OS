"""
app/modules/dining/_services/discounts.py
Extracted from app/modules/dining/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.modules.dining import crud
from app.modules.dining.models import DiningItem, DiningOrder
from app.resort_os.discount_engine import DiscountRule, OrderContext, OrderLineItem, calculate_discount
from app.resort_os.dining_pricing import calculate_mixed_pricing
from app.resort_os.timezone_utils import (
    local_today,
    utc_naive_to_local_date,
    utc_naive_to_local_time,
)
from app.modules.dining._services._helpers import (
    _lock_order_or_conflict,
    _order_price_components,
)


def _recompute_order_totals(db: Session, order: DiningOrder) -> None:
    """Rebuild all monetary snapshots from the order lines currently in DB."""
    subtotal, exclusive_subtotal, listed_gross_total = _order_price_components(order)

    outlet = crud.get_outlet(db, order.outlet_id)
    from app.modules.core.services import get_effective_vat_percentage  # noqa: PLC0415
    vat_pct = get_effective_vat_percentage(db, order.branch_id) / Decimal("100")
    # قرار موثّق: _service_charge_pct بتتقرا عبر الواجهة (services.py) مش
    # استيراد مباشر — راجع services.py's docstring لعقد الـpatchability.
    from app.modules.dining import services as _dining_services  # noqa: PLC0415
    service_pct = _dining_services._service_charge_pct(db, outlet, order.order_type)
    vat_amount, service_charge, gross_total = calculate_mixed_pricing(
        subtotal=subtotal,
        exclusive_subtotal=exclusive_subtotal,
        listed_gross_total=listed_gross_total,
        vat_pct=vat_pct,
        service_pct=service_pct,
    )
    discount_amount, rule_id = _resolve_order_discount(db, order, subtotal)

    order.subtotal = subtotal
    order.vat_amount = vat_amount
    order.service_charge = service_charge
    order.discount_amount = discount_amount
    order.applied_discount_rule_id = rule_id
    order.total = max(
        Decimal("0"),
        gross_total + order.delivery_fee - discount_amount,
    )


def _sync_kitchen_tickets_for_order(db: Session, order: DiningOrder) -> None:
    """يحدّث حالة تذاكر المطبخ المرتبطة بالطلب ده حسب حالة أصنافها الفعلية —
    تذكرة تبقى 'done' لو كل أصنافها ready/served/cancelled، أو 'in_progress'
    لو أي صنف بدأ يتحرّك من pending. راجع
    restaurant.services._sync_kitchen_tickets_for_order — نفس المنطق
    بالظبط (تُستدعى بعد أي bump فردي، مش بعد التأكيد اليدوي الكامل)."""
    tickets = crud.list_tickets_for_order(db, order.id)
    if not tickets:
        return
    status_by_item_id = {item.id: item.status for item in order.items}
    for ticket in tickets:
        if ticket.status == "done":
            continue
        item_ids = [entry.get("order_item_id") for entry in ticket.items_snapshot]
        statuses = [status_by_item_id[iid] for iid in item_ids if iid in status_by_item_id]
        if not statuses:
            continue
        if all(s in ("ready", "served", "cancelled") for s in statuses):
            crud.update_ticket_status(db, ticket.id, "done")
        elif ticket.status == "pending" and any(s != "pending" for s in statuses):
            crud.update_ticket_status(db, ticket.id, "in_progress")


def _order_local_date_and_time(order: DiningOrder) -> tuple[date, time]:
    """راجع restaurant.services._order_local_date_and_time — نفس المنطق بالظبط."""
    if not order.created_at:
        # قرار موثّق: local_now بتتقرا عبر الواجهة (services.py) مش استيراد
        # مباشر — راجع services.py's docstring لعقد الـpatchability.
        from app.modules.dining import services as _dining_services  # noqa: PLC0415
        now_local = _dining_services.local_now(settings.TIMEZONE)
        return now_local.date(), now_local.time()
    return (
        utc_naive_to_local_date(order.created_at, settings.TIMEZONE),
        utc_naive_to_local_time(order.created_at, settings.TIMEZONE),
    )


def _normalize_order_date(order_date) -> date:
    if isinstance(order_date, datetime):
        return utc_naive_to_local_date(order_date, settings.TIMEZONE)
    if isinstance(order_date, date):
        return order_date
    return local_today(settings.TIMEZONE)


def _build_discount_line_items(db: Session, order: DiningOrder) -> list[OrderLineItem]:
    """راجع restaurant.services._build_discount_line_items — استعلام واحد
    لكل الأصناف المميزة، بدون N+1."""
    active_items = [i for i in order.items if i.status != "cancelled"]
    item_ids = {i.item_id for i in active_items}
    category_by_item: dict[int, int | None] = {}
    if item_ids:
        category_by_item = dict(
            db.query(DiningItem.id, DiningItem.category_id)
            .filter(DiningItem.id.in_(item_ids))
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


def _recompute_discount_for_rule(
    db: Session, rule_id: int, new_subtotal: Decimal, order: DiningOrder,
) -> tuple[Decimal, Optional[int]]:
    """راجع restaurant.services._recompute_discount_for_rule — نفس المنطق بالظبط."""
    try:
        from app.modules.finance.models import ConditionalDiscount  # noqa: PLC0415
        from app.modules.finance.services import discount_rule_from_orm  # noqa: PLC0415
    except ImportError:
        return Decimal("0"), None

    rule_orm = db.query(ConditionalDiscount).filter(ConditionalDiscount.id == rule_id).first()
    if not rule_orm or not rule_orm.is_active:
        return Decimal("0"), None
    order_date, order_time = _order_local_date_and_time(order)
    outlet = crud.get_outlet(db, order.outlet_id)
    ctx = OrderContext(
        total_amount=new_subtotal,
        item_count=0,
        order_date=_normalize_order_date(order_date),
        order_time=order_time,
        outlet=outlet.outlet_type if outlet else None,
        line_items=_build_discount_line_items(db, order),
    )
    result = calculate_discount(new_subtotal, [discount_rule_from_orm(rule_orm)], ctx)
    return result.amount_saved, result.rule_id


def _customer_group_discount_amount(db: Session, customer_id: Optional[int], subtotal: Decimal) -> Decimal:
    """خصم مجموعة العميل الدائم (crm.CustomerGroup.discount_percentage) على
    الـ subtotal — صفر لو مفيش عميل مرتبط أو مجموعته موقوفة/غير موجودة.
    راجع crm.services.get_customer_group_discount_percentage للمنطق الكامل."""
    from app.modules.crm.services import get_customer_group_discount_percentage  # noqa: PLC0415

    pct = get_customer_group_discount_percentage(db, customer_id)
    if pct <= 0:
        return Decimal("0")
    return (subtotal * pct / Decimal("100")).quantize(Decimal("0.01"))


def _resolve_order_discount(db: Session, order: DiningOrder, subtotal: Decimal) -> tuple[Decimal, Optional[int]]:
    """أفضل خصم للطلب على الـ subtotal الحالي — بيقارن بين نوعين مختلفين
    تمامًا ومستقلين عن بعض: (أ) خصم مجموعة العميل الدائم (تلقائي، بلا أي
    إجراء يدوي — _customer_group_discount_amount فوق) و(ب) قاعدة خصم شرطية
    (happy hour/بروموشن) اتطبّقت يدويًا من قبل على الطلب ده (لو موجودة،
    بإعادة حسابها على subtotal الجديد عبر _recompute_discount_for_rule).

    **قرار سياسة تجارية (Batch 2، customer groups)**: الاتنين ميتجمعوش
    (لا stacking) — الأعلى قيمة بس هو اللي يتطبّق فعليًا، نفس فلسفة "أفضل
    عرض للضيف الواحد" المتّبعة في discount_engine.calculate_discount نفسها
    (بتاخد أعلى priority بين القواعد الشرطية، مش تجمعهم). لو الفايز خصم
    المجموعة، بيرجّع rule_id=None — يعني القاعدة الشرطية (لو كانت مطبّقة)
    بتتنحّى بدون ما تُحسب مستخدمة (uses_count متتزودش)، لأنها فعليًا ملهاش
    أثر على المبلغ النهائي في اللحظة دي."""
    group_amount = _customer_group_discount_amount(db, order.customer_id, subtotal)

    rule_amount, rule_id = Decimal("0"), None
    if order.applied_discount_rule_id:
        rule_amount, rule_id = _recompute_discount_for_rule(db, order.applied_discount_rule_id, subtotal, order)

    if rule_amount >= group_amount:
        return rule_amount, rule_id
    return group_amount, None


def apply_order_discount(
    db: Session, order_id: int, applied_by: Optional[int] = None,
    acting_user_level: int = 100, approver_user_id: Optional[int] = None,
    approver_pin: Optional[str] = None,
) -> DiningOrder:
    """راجع restaurant.services.apply_order_discount — نفس المنطق بالظبط،
    بس outlet=outlet.outlet_type ديناميكي بدل نص ثابت "restaurant"/"cafe"،
    فقواعد scope_type="outlet" تفرّق فعليًا بين أي عدد من الـ outlets.

    قرار Mohamed (2026-07-13): الكاشير صفر صلاحية خصم خالص — أي محاولة
    تطبيق خصم من مستوى أقل من مدير (level < 60) محتاجة موافقة PIN مدير/
    محاسب حاضر فعليًا، عبر core.services.resolve_pin_approval بالظبط زي
    void_order_item، بغض النظر عن نتيجة قاعدة الخصم (حتى لو مفيش قاعدة
    سارية أصلاً والنتيجة صفر — الموافقة على *محاولة* التطبيق نفسها).

    Gate 4 (جولة مراجعة Codex الأولى): قفل الطلب + إعادة فحص الحالة تحت
    القفل — عشان تطبيق الخصم مايتسابقش مع دفع نفس الطلب."""
    order = _lock_order_or_conflict(db, order_id)

    if order.status in ("paid", "cancelled", "refunded"):
        raise ValueError("لا يمكن تطبيق خصم على طلب مغلق")

    from app.modules.core import policy_engine  # noqa: PLC0415

    approved_by = policy_engine.require_approval(
        db, "apply_order_discount",
        acting_user_level=acting_user_level,
        approver_user_id=approver_user_id, approver_pin=approver_pin,
        target_branch_id=order.branch_id,
    )

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

    outlet = crud.get_outlet(db, order.outlet_id)
    total_items = sum(item.quantity for item in order.items)
    order_date, order_time = _order_local_date_and_time(order)
    ctx = OrderContext(
        total_amount=order.subtotal,
        item_count=total_items,
        order_date=order_date,
        order_time=order_time,
        outlet=outlet.outlet_type if outlet else None,
        line_items=_build_discount_line_items(db, order),
    )

    result = calculate_discount(order.subtotal, rules, ctx)

    # الأفضل للضيف يفوز — مش تراكم (راجع _resolve_order_discount للتبرير
    # الكامل). لو خصم مجموعة العميل الدائم أكبر من القاعدة الشرطية المُقيَّمة
    # هنا، هو اللي بيتطبّق فعليًا بدل نتيجة الزرار، وrule_id بيتسجّل None
    # (القاعدة الشرطية معدتش "استخدمت" فعليًا في اللحظة دي).
    group_amount = _customer_group_discount_amount(db, order.customer_id, order.subtotal)
    conditional_wins = result.amount_saved >= group_amount
    final_amount = result.amount_saved if conditional_wins else group_amount
    final_rule_id = result.rule_id if conditional_wins else None

    order = crud.update_order_discount(
        db, order,
        discount_amount=final_amount,
        rule_id=final_rule_id,
    )

    policy_engine.record_policy_audit(
        db, "apply_discount",
        user_id=applied_by, approved_by=approved_by, branch_id=order.branch_id,
        entity_type="dining_order", entity_id=order.id,
        data={
            "applied": result.applied,
            "conditional_discount_amount": str(result.amount_saved),
            "conditional_rule_id": result.rule_id,
            "customer_group_discount_amount": str(group_amount),
            "final_discount_amount": str(final_amount),
            "final_rule_id": final_rule_id,
        },
    )

    if conditional_wins and result.applied and result.rule_id:
        try:
            from app.modules.finance.crud import increment_discount_uses  # noqa: PLC0415
            increment_discount_uses(db, result.rule_id)
        except ImportError:
            pass

    db.commit()
    db.refresh(order)
    return order


# ─────────────────────── Reporting / Shift Sold Items ──────────────────
# 2026-09-05 — طلب Mohamed بعد ما جرّب تطبيق الأونر بنفسه: الوردية كانت
# بتوري "3 فواتير بـ1190ج" من غير أي فكرة عن نوع اللي اتباع فعليًا (ساندوتش/
# بيتزا/مشروبات). مصدر واحد هنا يغذّي 3 واجهات: شاشة المحاسب (FinanceView
# shift detail)، تطبيق الأونر (كارت تصنيف + تفصيل فاتورة)، والفاتورة
# المطبوعة عند قفل الوردية. المصدر: DiningSettlement.shift_id — بيغطي كل
# طرق الدفع بما فيها الغرفة (عكس Payment.shift_id اللي بيفوّت تسويات
# الغرفة تمامًا، لأنها ذمّة على الفوليو مش صف Payment مباشر).
