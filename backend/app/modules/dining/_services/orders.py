"""
app/modules/dining/_services/orders.py
Extracted from app/modules/dining/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Optional
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.modules.dining import crud
from app.modules.dining.models import DiningItem, DiningOrder
from app.modules.dining.schemas import (
    OrderCreate,
)
from app.resort_os.dining_pricing import calculate_mixed_pricing, snapshot_price_component
from app.modules.dining._services._helpers import (
    assert_order_transition,
    _lock_order_or_conflict,
    _get_outlet_or_404,
    _snapshot_selected_extras,
    _resolve_extras,
    _resolve_variant,
    _check_item_available_now,
)
from app.modules.dining._services.settlement import (
    _mark_order_paid,
)
from app.modules.dining._services.discounts import (
    _recompute_order_totals,
    _customer_group_discount_amount,
)


def assert_guest_self_order_enabled(db: Session, branch_id: int) -> None:
    """Gate 1 containment (Decision 0001 point 3 / PRODUCTION_READINESS_AUDIT
    C-02): unauthenticated guest self-ordering is closed by default.

    **تصحيح (جولة مراجعة Codex الثالثة):** AGENTS.md بيمنع الاعتماد على
    core.Setting (حر، قابل للتعديل عبر API الإعدادات) كبوابة أمان لوحدها.
    لازم الاتنين معًا: settings.DINING_SELF_ORDER_ENABLED (typed،
    deployment-level، مش قابل للتغيير من غير deploy/restart) + core.Setting
    الخاص بالفرع (dining.self_order_enabled). أي واحد بس متفعّل مش كافي."""
    from app.core.config import settings  # noqa: PLC0415
    from app.modules.core import services as core_services  # noqa: PLC0415

    if not settings.DINING_SELF_ORDER_ENABLED:
        raise ValueError("الطلب الذاتي غير متاح حاليًا — نادِ الجرسون لطلب الطلب أو الحساب")

    raw_value = core_services.get_setting_value(
        db, "dining.self_order_enabled", branch_id=branch_id, default="false",
    )
    enabled = str(raw_value).strip().lower() in ("1", "true", "yes", "y", "نعم")
    if not enabled:
        raise ValueError("الطلب الذاتي غير متاح حاليًا — نادِ الجرسون لطلب الطلب أو الحساب")


def create_order(
    db: Session,
    branch_id: int,
    data: OrderCreate,
    waiter_id: Optional[int] = None,
    hold: bool = False,
    guest_session_id: Optional[int] = None,
    guest_public_reference: Optional[str] = None,
    allow_cross_outlet: bool = False,
    client_local_id: Optional[str] = None,
) -> DiningOrder:
    """⚠️ باج حقيقي اتصلح (2026-08-02): POST /dining/public/orders (الضيف
    بيطلب من QR الطاولة، بدون auth) ماكانش عنده أي حماية idempotency خالص
    — رد فقد بعد timeout/network drop، وبعدين إعادة إرسال من الضيف (تلقائي
    أو يدوي)، كان بينشئ طلب طعام حقيقي تاني (تذكرة مطبخ تانية، إيراد
    مزدوج محتمل). نفس آلية client_local_id المستخدمة بالفعل في
    sync_offline_order (POS بدون إنترنت) — عمود موجود بالفعل على
    DiningOrder بقيد UNIQUE عام، مفيش migration جديدة محتاجة."""
    if client_local_id:
        existing = crud.get_order_by_local_id(db, client_local_id)
        if existing is not None:
            return existing

    outlet = _get_outlet_or_404(db, data.outlet_id)
    if outlet.branch_id != branch_id:
        # Gate 1 containment (جولة تصحيح ثانية): دايمًا صحيح للمسار
        # العام/الداخلي الحاليين (branch_id بيتحسب من outlet.branch_id
        # نفسه في الـ3 callers الموجودين) — دفاع عن أي caller مستقبلي
        # يبعت branch_id تاني بالغلط أو عمدًا.
        raise ValueError(f"المنفذ {data.outlet_id} لا يتبع هذا الفرع")

    if data.table_id is not None:
        table = crud.get_table(db, data.table_id)
        if not table:
            raise ValueError(f"الطاولة {data.table_id} غير موجودة")
        if table.branch_id != branch_id:
            raise ValueError(f"الطاولة {data.table_id} لا تتبع هذا الفرع")
        if table.status == "out_of_service":
            raise ValueError(f"الطاولة {table.table_number} خارج الخدمة")
        # Gate 4C: قفل صف الطاولة (blocking) ثم فحص طلب نشط — يسلسل أي
        # محاولتين متزامنتين يفتحوا طلب على نفس الطاولة، مع partial unique
        # index (uq_active_order_per_table) كـ backstop نهائي على مستوى الـ DB.
        crud.lock_table_for_update(db, data.table_id)
        conflicting = crud.get_active_order_for_table(db, data.table_id)
        if conflicting:
            raise ValueError(
                f"الطاولة {table.table_number} مشغولة بطلب نشط بالفعل ({conflicting.order_number})"
            )

    from app.modules.core.services import get_effective_vat_percentage  # noqa: PLC0415

    vat_pct = get_effective_vat_percentage(db, branch_id) / Decimal("100")
    # قرار موثّق: _service_charge_pct بتتقرا عبر الواجهة (services.py) مش
    # استيراد مباشر — تستات test_dining.py بتعمل patch("app.modules.dining.
    # services._service_charge_pct") صراحةً على الوردية (Happy Hour).
    from app.modules.dining import services as _dining_services  # noqa: PLC0415
    svc_pct = _dining_services._service_charge_pct(db, outlet, data.order_type)
    items_data = []
    subtotal = Decimal("0")
    exclusive_subtotal = Decimal("0")
    listed_gross_total = Decimal("0")

    # ── batch-load كل الأصناف بـ query واحدة بدل N queries فردية ──────────
    item_ids = [req.item_id for req in data.items]
    items_map = crud.get_items_by_ids(db, item_ids)

    for item_req in data.items:
        item = items_map.get(item_req.item_id)
        if not item:
            raise ValueError(f"الصنف {item_req.item_id} غير موجود")
        # cross-outlet: الصنف مسموح من أي outlet في نفس الفرع، مش لازم يطابق
        # data.outlet_id — نفس الفاتورة تقدر تحمل مثلاً صنف مطعم وصنف كافيه
        # مع بعض. راجع docstring DiningOrderItem.outlet_id وnotes
        # _build_outlet_revenue_splits تحت لتوزيع الإيراد per-outlet.
        # ⚠️ كان قاصر على طلبات النادل (POS الداخلي) بس قبل كده — الطلب
        # الذاتي العام (QR، guest_session_id) كان صارم عمدًا (Gate 1
        # containment: ضيف ميقدرش يطلب صنف من outlet مختلف عن المُعلن).
        # اتغيّر بطلب صريح من Mohamed (2026-08-03): الضيف بقى بيتصفح كل
        # منافذ الفرع مدموجين من غير أي مفهوم "منفذ" ظاهر له، فcreate_
        # guest_order في الراوتر بقى بيبعت allow_cross_outlet=True زي
        # النادل بالظبط — نفس الآلية دي، مش استثناء أمني جديد.
        if allow_cross_outlet:
            if item.branch_id != branch_id:
                raise ValueError(f"الصنف {item_req.item_id} لا يتبع هذا الفرع")
        elif item.outlet_id != data.outlet_id or item.branch_id != branch_id:
            raise ValueError(f"الصنف {item_req.item_id} لا يتبع هذا المنفذ")
        if not item.is_available:
            raise ValueError(f"الصنف '{item.name}' غير متاح حالياً")
        _check_item_available_now(item)

        variant = _resolve_variant(db, item, item_req.variant_id)
        displayed_base_price = variant.price if variant else item.price
        base_price, listed_base_price = snapshot_price_component(
            displayed_base_price,
            is_final_price=item.price_includes_vat_service,
            vat_pct=vat_pct,
            service_pct=svc_pct,
        )
        item_name = f"{item.name} - {variant.name}" if variant else item.name
        # name_ar snapshot (2026-08-03): بغض النظر عن لغة الضيف اللي طلب
        # بيها (ar/en/ru/it) — راجع docstring DiningOrderItem.name_ar.
        item_name_ar = f"{item.name_ar} - {variant.name_ar}" if variant and item.name_ar and variant.name_ar \
            else (item.name_ar if not variant else None)

        extras_data, _ = _resolve_extras(db, item, item_req.extra_ids, item_req.extra_texts)
        extras_data, extra_price_per_unit, exclusive_extra, listed_extra = _snapshot_selected_extras(
            extras_data,
            is_final_price=item.price_includes_vat_service,
            vat_pct=vat_pct,
            service_pct=svc_pct,
        )

        line_total = (base_price + extra_price_per_unit) * item_req.quantity
        subtotal += line_total
        quantity = Decimal(item_req.quantity)
        if listed_base_price is None:
            exclusive_subtotal += base_price * quantity
        else:
            listed_gross_total += listed_base_price * quantity
        exclusive_subtotal += exclusive_extra * quantity
        listed_gross_total += listed_extra * quantity
        items_data.append({
            "item_id":    item_req.item_id,
            "outlet_id":  item.outlet_id,
            "variant_id": variant.id if variant else None,
            "name":       item_name,
            "name_ar":    item_name_ar,
            "unit_price": base_price,
            "listed_unit_price": listed_base_price,
            "quantity":   item_req.quantity,
            "notes":      item_req.notes,
            "extras":     extras_data,
        })

    vat_amount, svc_charge, gross_total = calculate_mixed_pricing(
        subtotal=subtotal,
        exclusive_subtotal=exclusive_subtotal,
        listed_gross_total=listed_gross_total,
        vat_pct=vat_pct,
        service_pct=svc_pct,
    )

    # رسم توصيل ثابت — بس delivery، ولقطة وقت الإنشاء (رسم ثابت مش نسبة،
    # فمش محتاج إعادة حساب لما الأصناف تتغيّر بعدين، راجع add_items_to_order
    # وvoid_order_item تحت).
    delivery_fee = Decimal("0")
    if data.order_type == "delivery" and outlet is not None and outlet.delivery_fee:
        delivery_fee = outlet.delivery_fee

    # خصم مجموعة العميل الدائم (standing discount) — تلقائي بالكامل لو
    # الطلب مرتبط بعميل عنده مجموعة نشطة، من غير أي تدخّل يدوي أو موافقة
    # PIN (مختلف عن apply_order_discount اللي بيطبّق قاعدة خصم شرطية —
    # راجع _resolve_order_discount تحت لقرار "الأفضل يفوز، مش تراكم" لما
    # الاتنين يتقابلوا لاحقًا على نفس الطلب).
    discount_amount = _customer_group_discount_amount(db, data.customer_id, subtotal)
    total = max(Decimal("0"), gross_total + delivery_fee - discount_amount)

    order_number = crud.generate_order_number(db, branch_id)

    # ⚠️ باج حقيقي كان هنا (اتصلح 2026-07-28): crud.create_order_with_items
    # بتعمل db.flush() فورًا بعد db.add(order) (لازم عشان تجيب order.id
    # للأصناف) — يعني أي IntegrityError (order_number المكرر، أو
    # uq_active_order_per_table الـbackstop اللي التعليق تحت كان بيدّعي إنه
    # بيتلقط) بيتفجّر هنا جوه try كان بيلف db.commit() بس تحت، مش هنا —
    # الـbackstop كان عمليًا ميوصلش له أبدًا، وأي تصادم كان بيطلع 500 خام.
    try:
        order = crud.create_order_with_items(
            db=db,
            branch_id=branch_id,
            outlet_id=outlet.id,
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
            discount_amount=discount_amount,
            delivery_fee=delivery_fee,
            created_by=waiter_id,
            guest_session_id=guest_session_id,
            guest_public_reference=guest_public_reference,
            guest_name=data.guest_name,
            guest_phone=data.guest_phone,
            client_local_id=client_local_id,
            b2b_contract_id=getattr(data, "b2b_contract_id", None),
            beach_location_id=getattr(data, "beach_location_id", None),
        )
    except IntegrityError as exc:
        db.rollback()
        _raise_order_integrity_error(exc)

    if guest_session_id is not None:
        from app.modules.core import crud as core_crud  # noqa: PLC0415
        from app.modules.core.schemas import AuditLogCreate  # noqa: PLC0415
        core_crud.create_audit_log(db, AuditLogCreate(
            branch_id=branch_id,
            action="guest_order_created",
            entity_type="dining_order",
            entity_id=order.id,
            new_data=json.dumps({
                "public_reference": guest_public_reference,
                "outlet_id": outlet.id,
                "table_id": data.table_id,
            }, ensure_ascii=False, sort_keys=True),
        ))

    if data.table_id and data.order_type == "dine_in":
        table = crud.get_table(db, data.table_id)
        if table:
            crud.update_table_status(db, table, "occupied")

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_order_integrity_error(exc)
    db.refresh(order)
    return order


def _raise_order_integrity_error(exc: IntegrityError) -> None:
    """رسالة واضحة (→400) بدل خطأ DB خام لسباقات إنشاء الطلب الحقيقية:
    (أ) partial unique index بيمنع طلبين نشطين على نفس الطاولة (سباق فات
    فحص get_active_order_for_table تحت القفل)، (ب) order_number المتكرر —
    أول طلبين في نفس اليوم (SELECT FOR UPDATE في generate_order_number
    مالوش صفوف تتقفل لسه، راجع تعليق الدالة نفسها). أي IntegrityError تانية
    غير متوقعة بتتصعّد زي ما هي."""
    detail = str(getattr(exc, "orig", exc))
    if "uq_active_order_per_table" in detail:
        raise ValueError("الطاولة مشغولة بطلب نشط بالفعل (سباق فتح مزدوج)") from exc
    if "order_number" in detail:
        raise ValueError("رقم الطلب اتكرر بسبب طلب متزامن — أعد المحاولة") from exc
    if "client_local_id" in detail:
        # سباق حقيقي: نفس client_local_id اتبعت مرتين في نفس اللحظة بالظبط
        # (بين فحص get_order_by_local_id في بداية create_order والـcommit
        # هنا) — الفحص المبدئي مايكفيش لوحده تحت تزامن حقيقي، والقيد على
        # مستوى الـDB هو الـbackstop النهائي. رسالة واضحة بدل IntegrityError خام.
        raise ValueError("الطلب ده اتسجّل بالفعل (retry متزامن) — تحقق من حالة الطلب الحالية") from exc
    raise exc


def _create_kitchen_tickets_for_items(
    db: Session,
    order: DiningOrder,
    order_items: list,
) -> int:
    """Create one KDS ticket per (outlet, station) for the supplied,
    not-yet-ticketed lines — cross-outlet orders route each line's ticket to
    its own item's outlet, not order.outlet_id."""
    if not order_items:
        return 0

    menu_item_ids = {item.item_id for item in order_items}
    station_by_item = {
        menu_item.id: menu_item.station
        for menu_item in db.query(DiningItem).filter(DiningItem.id.in_(menu_item_ids)).all()
    } if menu_item_ids else {}

    # cross-outlet: التذكرة بتتوجّه لـoutlet الصنف نفسه (order_item.outlet_id)
    # مش outlet الطلب — عشان صنف كافيه على طلب مطعم يوصل لشاشة KDS الصح لو
    # المنتجع بيستخدم شاشات مخصّصة لكل outlet (راجع DiningKDSScreen.outlet_id).
    items_by_ticket: dict[tuple[int, str], list[dict]] = {}
    for order_item in order_items:
        station = station_by_item.get(order_item.item_id, "hot")
        outlet_id = order_item.outlet_id or order.outlet_id
        items_by_ticket.setdefault((outlet_id, station), []).append({
            "order_item_id": order_item.id,
            "name": order_item.name,
            "name_ar": order_item.name_ar,
            "quantity": order_item.quantity,
            "notes": order_item.notes,
        })

    for (outlet_id, station), items_snapshot in items_by_ticket.items():
        crud.create_kitchen_ticket(
            db,
            order_id=order.id,
            branch_id=order.branch_id,
            outlet_id=outlet_id,
            station=station,
            items_snapshot=items_snapshot,
        )
    return len(items_by_ticket)


def _ensure_kitchen_tickets_for_order(db: Session, order: DiningOrder) -> int:
    """Ticket every live line exactly once while preserving existing KDS state."""
    ticketed_item_ids = {
        entry.get("order_item_id")
        for ticket in crud.list_tickets_for_order(db, order.id)
        for entry in ticket.items_snapshot
    }
    missing_items = [
        item for item in crud.list_active_order_items(db, order.id)
        if item.id not in ticketed_item_ids
    ]
    return _create_kitchen_tickets_for_items(db, order, missing_items)


def add_items_to_order(db: Session, order_id: int, items: list, added_by: Optional[int] = None) -> DiningOrder:
    """راجع restaurant.services.add_items_to_order — نفس المنطق بالظبط.
    Gate 4C: كل صنف جديد بيحفظ مين أضافه (added_by) للتدقيق."""
    from app.modules.dining.models import DiningOrderItem, DiningOrderItemExtra  # noqa: PLC0415

    # Gate 4 (جولة مراجعة Codex الأولى): قفل الطلب + إعادة فحص الحالة تحت
    # القفل — عشان إضافة أصناف مايتسابقش مع دفع نفس الطلب.
    order = _lock_order_or_conflict(db, order_id)
    if order.status not in ("held", "open", "in_kitchen", "served"):
        raise ValueError(f"لا يمكن إضافة أصناف لطلب بحالة {order.status}")

    outlet = crud.get_outlet(db, order.outlet_id)
    from app.modules.core.services import get_effective_vat_percentage  # noqa: PLC0415

    vat_pct = get_effective_vat_percentage(db, order.branch_id) / Decimal("100")
    # راجع create_order فوق — نفس عقد الـpatchability بالظبط.
    from app.modules.dining import services as _dining_services  # noqa: PLC0415
    svc_pct = _dining_services._service_charge_pct(db, outlet, order.order_type)
    new_items = []

    # ── batch-load الأصناف بـ query واحدة ────────────────────────────────
    item_ids = [req.item_id for req in items]
    items_map = crud.get_items_by_ids(db, item_ids)

    for item_req in items:
        item = items_map.get(item_req.item_id)
        if not item:
            raise ValueError(f"الصنف {item_req.item_id} غير موجود")
        # cross-outlet: نفس القرار في create_order فوق — الصنف مسموح من أي
        # outlet في نفس فرع الطلب، مش لازم يطابق order.outlet_id.
        if item.branch_id != order.branch_id:
            raise ValueError(
                f"الصنف {item_req.item_id} لا ينتمي لنفس فرع الطلب"
            )
        if not item.is_available:
            raise ValueError(f"الصنف '{item.name}' غير متاح حالياً")
        _check_item_available_now(item)

        variant = _resolve_variant(db, item, item_req.variant_id)
        displayed_base_price = variant.price if variant else item.price
        base_price, listed_base_price = snapshot_price_component(
            displayed_base_price,
            is_final_price=item.price_includes_vat_service,
            vat_pct=vat_pct,
            service_pct=svc_pct,
        )
        item_name  = f"{item.name} - {variant.name}" if variant else item.name
        item_name_ar = f"{item.name_ar} - {variant.name_ar}" if variant and item.name_ar and variant.name_ar \
            else (item.name_ar if not variant else None)
        extras_data, _ = _resolve_extras(db, item, item_req.extra_ids, item_req.extra_texts)
        extras_data, _, _, _ = _snapshot_selected_extras(
            extras_data,
            is_final_price=item.price_includes_vat_service,
            vat_pct=vat_pct,
            service_pct=svc_pct,
        )

        new_item = DiningOrderItem(
            order_id  = order.id,
            item_id   = item_req.item_id,
            outlet_id = item.outlet_id,
            variant_id= variant.id if variant else None,
            name      = item_name,
            name_ar   = item_name_ar,
            unit_price= base_price,
            listed_unit_price=listed_base_price,
            quantity  = item_req.quantity,
            notes     = item_req.notes,
            status    = "pending",
            added_by  = added_by,
        )
        db.add(new_item)
        db.flush()
        new_items.append(new_item)

        for e in extras_data:
            db.add(DiningOrderItemExtra(
                order_item_id  = new_item.id,
                extra_id       = e["extra_id"],
                extra_name     = e["extra_name"],
                extra_name_ar  = e.get("extra_name_ar"),
                price_addition = e["price_addition"],
                listed_price_addition = e.get("listed_price_addition"),
                text_value     = e.get("text_value"),
            ))

    db.flush()
    # يعيد بناء الخصم والضرائب من كل اللقطات، بما فيها الأصناف القديمة
    # الصافية والأصناف ذات السعر النهائي على نفس الفاتورة.
    _recompute_order_totals(db, order)

    # أصناف تضاف بعد إرسال الطلب لازم تظهر في KDS فورًا. ولو الطلب كان served،
    # وجود صنف pending جديد يعيده لحالة in_kitchen بدل ادعاء أن الكل اتخدم.
    if order.status in ("in_kitchen", "served"):
        _create_kitchen_tickets_for_items(db, order, new_items)
        order.status = "in_kitchen"

    db.commit()
    db.refresh(order)
    return order


def sync_offline_order(
    db: Session,
    branch_id: int,
    data,  # OrderSyncRequest
    waiter_id: Optional[int] = None,
):
    """راجع restaurant.services.sync_offline_order — نفس عقد fulfilled/
    partial/rejected بالظبط (07-BUSINESS-RULES.md § 9)، idempotent عبر
    client_local_id."""
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

    # batch-load الأصناف بـ query واحدة
    item_ids  = [req.item_id for req in data.items]
    items_map = crud.get_items_by_ids(db, item_ids)

    for item_req in data.items:
        item = items_map.get(item_req.item_id)
        if not item or not item.is_available:
            rejected_items.append({
                "item_id": item_req.item_id,
                "name": item.name if item else f"#{item_req.item_id}",
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
        outlet_id=data.outlet_id,
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

    order = update_order_status(db, order.id, "in_kitchen")
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
    db: Session, order_id: int, new_status: str,
    charge_to_room_id: Optional[int] = None,
    payment_method: Optional[str] = None,
    credit_account_id: Optional[int] = None,
    payment_currency: Optional[str] = None,
    payment_fx_rate: Optional[Decimal] = None,
    payment_channel_id: Optional[int] = None,
    settled_by: Optional[int] = None,
    acting_user_level: int = 100,
    approver_user_id: Optional[int] = None,
    approver_pin: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> DiningOrder:
    """يغيّر حالة الطلب. التحويل لـ "مدفوع" وحده بقى وحدة عمل صارمة منفصلة
    (_mark_order_paid → settle_order — Gate 1B/4A: قفل صف الطلب، idempotency
    guard، إنشاء Payment منسوب للكاشير/الوردية، شحنة فوليو/خصم مخزون/قيد
    محاسبي من غير أي بلع أخطاء صامت، وcommit واحد بس). باقي التحويلات
    سلوكها القديم زي ما هو بالظبط — مفيش أثر مالي فيهم غير تحرير الطاولة.

    POS-03: payment_currency/payment_fx_rate للكاش بعملة أجنبية — اختياريان.

    ⚠️ transition state machine: التحويلات المسموحة بتتحقق من جدول واحد
    مركزي (ORDER_TRANSITIONS) بدل شرط ad-hoc — راجع assert_order_transition."""
    if new_status == "paid":
        return _mark_order_paid(
            db, order_id,
            charge_to_room_id=charge_to_room_id,
            payment_method=payment_method,
            credit_account_id=credit_account_id,
            payment_currency=payment_currency,
            payment_fx_rate=payment_fx_rate,
            payment_channel_id=payment_channel_id,
            settled_by=settled_by,
            acting_user_level=acting_user_level,
            approver_user_id=approver_user_id,
            approver_pin=approver_pin,
            idempotency_key=idempotency_key,
        )

    # Gate 4 (جولة مراجعة Codex الأولى): نقفل صف الطلب ونعيد فحص حالته تحت
    # القفل — سباق تحويل حالة (إلغاء/تعليق) مع دفع نفس الطلب كان ممكن يسيب
    # طلب مدفوع متعلّم cancelled. النمط نفسه بتاع settle_order/refund بالظبط.
    order = _lock_order_or_conflict(db, order_id)

    assert_order_transition(order.status, new_status)

    # M4 (state invariant): تحويل in_kitchen→in_kitchen no-op حقيقي — قبل
    # كده كان بيعيد إنشاء تذاكر مطبخ مكررة رغم إنه idempotent. لازم نلتقط
    # الحالة السابقة قبل الكتابة عشان نعرف هل ده أول دخول للمطبخ ولا إعادة.
    previous_status = order.status

    order = crud.update_order_status(db, order, new_status)

    # إرسال ticket لكل محطة (hot/grill/cold/bar/dessert) عند تحويل الطلب
    # لـ in_kitchen — راجع restaurant.services.update_order_status للتبرير
    # الكامل. هنا موحّد عبر كل الـ outlets (مفيش فرق مطعم/كافيه في الكود).
    # M4: بس أول دخول للمطبخ (previous_status != "in_kitchen") بيولّد تذاكر —
    # إعادة إرسال طلب أصلاً in_kitchen مابتنشئش تذاكر مكررة.
    if new_status == "in_kitchen" and previous_status != "in_kitchen":
        active_items = [item for item in order.items if item.status != "cancelled"]
        _create_kitchen_tickets_for_items(db, order, active_items)

    if new_status == "cancelled" and order.table_id:
        table = crud.get_table(db, order.table_id)
        if table:
            crud.update_table_status(db, table, "available")

    db.commit()
    db.refresh(order)
    return order
