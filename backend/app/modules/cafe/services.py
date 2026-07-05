"""app/modules/cafe/services.py — نفس منطق restaurant مع جداول cafe"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.cafe import crud
from app.modules.cafe.models import CafeOrder
from app.modules.cafe.schemas import CafeOrderCreate


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

    # قيد إيراد الكافيه (لو مفيش folio — راجع نفس الملاحظة في restaurant.services)
    # + خصم المخزون + تحديث إحصائيات العميل عند الدفع
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


def _deduct_inventory_for_order(db: Session, order: CafeOrder) -> None:
    """يخصم المخزون لكل صنف في الطلب مربوط بمنتج مخزني (CafeItem.linked_product_id).
    نفس فلسفة restaurant._deduct_inventory_for_order — فشل صنف واحد ميوقفش
    باقي الأصناف ولا يوقف إتمام الدفع."""
    from app.modules.inventory import crud as inventory_crud  # noqa: PLC0415
    from app.modules.inventory import services as inventory_services  # noqa: PLC0415

    for order_item in order.items:
        if order_item.status == "cancelled":
            continue
        try:
            item = crud.get_item(db, order_item.item_id)
            if not item or not item.linked_product_id:
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
    """Dr. Cash (1100) / Cr. Cafe Revenue (4400)."""
    from datetime import date as _date  # noqa: PLC0415
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    post_simple_revenue_journal(
        db, order.branch_id, _date.today(),
        debit_account_code="1100", credit_account_code="4400",
        amount=order.total or Decimal("0"),
        reference=f"ORD-{order.order_number}",
        description=f"إيرادات كافيه — {order.order_number}",
        source="cafe", source_id=order.id,
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
    total      = max(Decimal("0"), subtotal + vat_amount + svc_charge - order.discount_amount)

    order.subtotal       = subtotal
    order.vat_amount     = vat_amount
    order.service_charge = svc_charge
    order.total          = total

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
    except Exception:
        pass


def _post_order_refund_reversal_journal(db: Session, order: CafeOrder, refund_amount: Decimal) -> None:
    """عكس _post_order_revenue_journal — Dr. Cafe Revenue (4400) / Cr. Cash (1100)."""
    from datetime import date as _date  # noqa: PLC0415
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    post_simple_revenue_journal(
        db, order.branch_id, _date.today(),
        debit_account_code="4400", credit_account_code="1100",
        amount=refund_amount,
        reference=f"ORD-REFUND-{order.order_number}",
        description=f"مرتجع بعد الدفع — {order.order_number}",
        source="cafe_refund", source_id=order.id,
    )
