"""app/modules/restaurant/services.py — Business logic"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.restaurant import crud
from app.modules.restaurant.models import KitchenTicket, MenuItem, Order
from app.modules.restaurant.schemas import OrderCreate
from app.resort_os.discount_engine import DiscountRule, OrderContext, calculate_discount


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

    # قيد إيراد المطعم — بس لو الطلب اتقفل بكاش فوري (مفيش folio_id). لو
    # الطلب اتحمّل على فوليو غرفة (Charge to Room)، الإيراد ده بيتسجّل لاحقًا
    # لما الضيف يسدّد الفوليو كله وقت الخروج — مش دلوقتي، وإلا كان الإيراد
    # هيتسجّل مرتين (مرة هنا كـ cash، ومرة تانية جوه الفوليو).
    if new_status == "paid":
        _deduct_inventory_for_order(db, order)
        if not order.folio_id:
            _post_order_revenue_journal(db, order)
        if order.customer_id:
            from app.modules.crm.services import record_customer_visit  # noqa: PLC0415
            record_customer_visit(db, order.customer_id, order.total, order.created_at.date())

    db.commit()
    db.refresh(order)
    return order


def _deduct_inventory_for_order(db: Session, order: Order) -> None:
    """يخصم المخزون لكل صنف في الطلب مربوط بمنتج مخزني (MenuItem.linked_product_id).
    معظم الأصناف مفهاش ربط — بيتم تجاوزها بصمت. فشل خصم صنف واحد (رصيد غير كافٍ
    مثلاً) ميوقفش باقي الأصناف ولا يوقف إتمام الدفع — نفس فلسفة
    _post_order_revenue_journal أعلاه."""
    from app.modules.inventory import crud as inventory_crud  # noqa: PLC0415
    from app.modules.inventory import services as inventory_services  # noqa: PLC0415

    for item in order.items:
        if item.status == "cancelled":
            continue
        try:
            menu_item = crud.get_menu_item(db, item.menu_item_id)
            if not menu_item or not menu_item.linked_product_id:
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
    """Dr. Cash (1100) / Cr. Restaurant Revenue (4200)."""
    from datetime import date as _date  # noqa: PLC0415
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    post_simple_revenue_journal(
        db, order.branch_id, _date.today(),
        debit_account_code="1100", credit_account_code="4200",
        amount=order.total or Decimal("0"),
        reference=f"ORD-{order.order_number}",
        description=f"إيرادات مطعم — {order.order_number}",
        source="restaurant", source_id=order.id,
    )


def void_order_item(db: Session, order_id: int, item_id: int, reason: str, voided_by: int) -> Order:
    """إلغاء صنف واحد من الطلب مع سبب إجباري + توثيق مين لغاه (زي
    InvoiceDetails.isavoid/avoidreason/avoiduserId عند Trucker) — مش إلغاء
    الطلب كله. بيعيد حساب subtotal/vat/service/total من الأصناف الفعّالة بس."""
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
    except Exception:
        pass


def _post_order_refund_reversal_journal(db: Session, order: Order, refund_amount: Decimal) -> None:
    """عكس _post_order_revenue_journal — Dr. Restaurant Revenue (4200) /
    Cr. Cash (1100) — بيلغي نصيب الصنف المرتجع من قيد الإيراد الأصلي."""
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    post_simple_revenue_journal(
        db, order.branch_id, date.today(),
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
