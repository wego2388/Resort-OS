"""
app/modules/dining/_services/refunds.py
Extracted from app/modules/dining/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.modules.dining import crud
from app.modules.dining.models import DiningOrder, Outlet
from app.resort_os.timezone_utils import (
    local_today,
)
from app.modules.dining._services._helpers import (
    _lock_order_or_conflict,
    _outlet_cost_center_code,
)


def refund_order_item(db: Session, order_id: int, item_id: int, reason: str, refunded_by: int) -> DiningOrder:
    """راجع restaurant.services.refund_order_item — نفس المنطق الأساسي، مع
    إصلاح باج محاسبي حقيقي حول تناسب الخصم (راجع تعليق item_gross تحت).

    Gate 4C: بيقفل صف الطلب (get_order_for_update NOWAIT) ويعيد فحص حالة
    الصنف تحت القفل — مرتجعان متزامنان لنفس الصنف: واحد بس ينجح، والتاني
    يترفض (409 مشغول أو 'مرتجع بالفعل')، فمفيش عكس مالي مكرر. commit واحد،
    وأي فشل بيعمل rollback كامل."""
    try:
        order = _lock_order_or_conflict(db, order_id)
        return _refund_order_item_locked(db, order, order_id, item_id, reason, refunded_by)
    except Exception:
        db.rollback()
        raise


def _refund_order_item_locked(
    db: Session, order: DiningOrder, order_id: int, item_id: int, reason: str, refunded_by: int,
) -> DiningOrder:
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
    # ⚠️ باج محاسبي حقيقي اتصلح: كان بيحسب refund_amount = item_gross + نصيب
    # الـ VAT/service_charge بس — من غير أي نصيب من order.discount_amount.
    # القيد الأصلي وقت الدفع بيرحّل order.total (صافي بعد الخصم —
    # _post_folio_revenue_splits)، فمرتجع صنف واحد من طلب عليه خصم كان بيعكس
    # إيراد أكتر مما اترحّل فعليًا لنفس الصنف ده، وبيسيب باقي الطلب بقيمة أقل
    # من الصح في دفتر الأستاذ (ولنفس السبب في رصيد شحنة الفوليو). النصيب من
    # الخصم لازم يتناسب بنفس share_ratio (الخصم بيتحسب على subtotal زي الـ
    # VAT/service_charge بالظبط)، عشان مجموع مرتجعات كل الأصناف يرجع بالظبط
    # لـ order.total الأصلي.
    refund_discount = (order.discount_amount * share_ratio).quantize(Decimal("0.01")) if order.discount_amount else Decimal("0")
    refund_amount = max(Decimal("0"), item_gross - refund_discount + refund_vat + refund_svc)

    active_before = [
        order_item for order_item in order.items
        if order_item.status not in ("cancelled", "refunded")
    ]
    remaining_refundable = max(
        Decimal("0"),
        (order.total or Decimal("0")) - (order.refunded_amount or Decimal("0")),
    )
    if remaining_refundable <= 0:
        raise ValueError("لا يوجد رصيد متبقٍ قابل للمرتجع على هذا الطلب")
    if len(active_before) == 1:
        # Give the final line the exact remainder so per-line rounding can never
        # leave a cent behind or reverse more than the original settlement.
        refund_amount = remaining_refundable
    else:
        refund_amount = min(refund_amount, remaining_refundable)

    crud.refund_order_item(db, item, reason, refunded_by)
    order.refunded_amount = (order.refunded_amount or Decimal("0")) + refund_amount

    active_items = [i for i in order.items if i.status not in ("cancelled", "refunded")]
    if not active_items:
        order.status = "refunded"
        # M4 (جولة مراجعة Codex الأولى): طلب اترجّع بالكامل بيحرّر الطاولة —
        # قبل كده كانت تفضل "مشغولة" للأبد (نفس منطق cancel/paid). الحالة
        # "refunded" خارج مجموعة الطلب النشط، فمفيش طلب فعلي بيحجز الطاولة.
        if order.table_id:
            table = crud.get_table(db, order.table_id)
            if table:
                crud.update_table_status(db, table, "available")

    # cross-outlet (2026-08-02): لازم حساب إيراد *الصنف نفسه* مش المنفذ
    # الأساسي للطلب — لو الطلب فيه صنف من outlet تاني (راجع add_items_to_order)
    # ورجّعناه بحساب order.outlet_id، القيد العكسي كان هيتقيد على المنفذ
    # الغلط (مثلاً يعكس إيراد المطعم بدل الكافيه لصنف كافيه اترجّع)، وده
    # بيسيب حسابين غلط في نفس الوقت: المنفذ الصح فاضل بإيراد متضخّم لصنف
    # اترجّع بالفعل، والمنفذ التاني بيتعكس منه إيراد ماكانش له أصلاً.
    item_outlet = crud.get_outlet(db, item.outlet_id or order.outlet_id)
    revenue_account = item_outlet.revenue_account_code if item_outlet else "4200"
    # Gate 4 (جولة مراجعة Codex الأولى — High 3/4): العكس بيتقاد بالـ tenders
    # الأصلية الفعلية (مش boolean folio_id)، ولكل جزء بحسابه الصح، وfail-closed.
    _post_refund_reversals(db, order, refund_amount, revenue_account, refunded_by, outlet=item_outlet)

    db.commit()
    db.refresh(order)
    return order


def _post_refund_reversals(
    db: Session, order: DiningOrder, refund_amount: Decimal,
    revenue_account_code: str, refunded_by: int, outlet: Optional[Outlet] = None,
) -> None:
    """يعكس مرتجع صنف بالتناسب على *كل* الـ tenders الأصلية اللي حصّلت الطلب
    (Gate 4، جولة مراجعة Codex الأولى — High 3/4).

    الباج القديم (High 3): كان بيفرّع على ``order.folio_id`` boolean بس —
    طلب split (كاش + غرفة) folio_id بتاعه set لأن *جزء* اتحمّل على الغرفة،
    فكان بياخد مسار "عكس فوليو" لوحده ويسيب حصة الكاش المباشرة من غير أي عكس
    خالص (positive_direct_total بيفضل زي ما هو). دلوقتي العكس بيتوزّع بالتناسب
    على كل tender أصلي حسب حصته من order.total:
      • كل tender مباشر (Payment موجب) → Payment عكسي سالب بحصته + قيد Dr
        إيراد / Cr *حساب الطريقة الأصلي نفسه* (cash→1100، card/wallet→حساب
        المقاصّة المهيّأ عبر resolve_direct_tender_account، مش 1100 ثابت — High 4b).
      • حصة الغرفة (order.total - مجموع المباشر، لو الطلب عليه فوليو) → تقليل
        شحنة الفوليو + قيد Dr إيراد / Cr 1150.

    كله fail-closed (High 4a): أي فشل محاسبي بيرفع استثناء → refund_order_item
    بيعمل rollback كامل (حالة الطلب/الصنف + كل صفوف العكس)، مش يبتلع بصمت."""
    from app.modules.dining.payment_policy import resolve_direct_tender_account  # noqa: PLC0415
    from app.modules.credit import crud as credit_crud  # noqa: PLC0415
    from app.modules.finance import crud as finance_crud  # noqa: PLC0415
    from app.modules.finance import services as finance_services  # noqa: PLC0415

    order_total = order.total or Decimal("0")
    if order_total <= 0 or refund_amount <= 0:
        return

    direct_payments = [
        p for p in finance_crud.list_direct_payments_for_order(db, order.id)
        if p.voided_at is None and p.amount > 0
    ]
    direct_total = sum((p.amount for p in direct_payments), Decimal("0"))

    credit_charge = credit_crud.get_charge_for_source(db, ref_order_id=order.id)
    expects_credit = "credit_account" in (order.payment_method or "")
    if expects_credit and not credit_charge:
        raise ValueError(
            "حركة الحساب الآجل الأصلية للطلب غير موجودة — لا يمكن تنفيذ المرتجع بأمان"
        )
    if credit_charge and credit_charge.branch_id != order.branch_id:
        raise ValueError("حركة الحساب الآجل لا تنتمي لفرع الطلب")
    credit_total = credit_charge.amount if credit_charge else Decimal("0")

    # الحساب الآجل أولاً، ثم المدفوعات المباشرة، والغرفة آخر بند. وجود أي
    # rounding متراكم في مرتجعات متعددة يُمتص في بند لاحق، بينما آخر مرتجع
    # للحساب الآجل يأخذ المتبقي الحقيقي من حركة الترحيل الأصلية بالضبط.
    parts: list[tuple[str, Decimal, object]] = []
    if credit_charge:
        parts.append(("credit", credit_total, credit_charge))
    parts.extend(("direct", p.amount, p) for p in direct_payments)
    if order.folio_id:
        room_total = max(Decimal("0"), order_total - direct_total - credit_total)
        if room_total > 0:
            parts.append(("room", room_total, None))
    if not parts:
        return

    shift_id = None
    if any(kind == "direct" for kind, _, _ in parts):
        open_shift = finance_services._lock_open_shift_or_conflict(db, order.branch_id, refunded_by)
        if not open_shift:
            # Gate 4 review (2026-07-21, finding N1): refund_order_item is
            # manager-gated (min_role_level=60) — refunded_by is almost
            # always a manager approving the refund, not a cashier running a
            # drawer, so they rarely have an open shift of their own. Without
            # this fallback the reversed cash Payment gets shift_id=None and
            # never reduces any shift's expected_cash in build_shift_end_
            # report, even though the cash physically left a real drawer.
            # Only resolve this when exactly one shift is open at the branch
            # (the unambiguous case — that's the drawer the cash came from);
            # zero or multiple open shifts stay unattributed rather than
            # guess which cashier's drawer to charge.
            open_shifts, _ = finance_crud.list_shifts(db, order.branch_id, status="open", limit=2)
            if len(open_shifts) == 1:
                open_shift = finance_services._lock_open_shift_or_conflict(
                    db, order.branch_id, open_shifts[0].cashier_id,
                )
        if open_shift:
            shift_id = open_shift.id

    # cross-outlet: cost center برضو لازم يكون بتاع outlet الصنف نفسه، مش
    # المنفذ الأساسي للطلب (نفس السبب في اختيار revenue_account_code فوق).
    cost_center_code = _outlet_cost_center_code(outlet or crud.get_outlet(db, order.outlet_id))
    credit_remaining = Decimal("0")
    credit_refunded = Decimal("0")
    credit_target_cumulative = Decimal("0")
    final_order_refund = (order.refunded_amount or Decimal("0")) >= order_total
    if credit_charge:
        credit_refunded = sum(
            (
                adjustment.amount
                for adjustment in credit_crud.list_adjustments_for_transaction(
                    db, credit_charge.id,
                )
                if adjustment.txn_type == "refund"
            ),
            Decimal("0"),
        )
        credit_remaining = max(Decimal("0"), credit_charge.amount - credit_refunded)
        credit_target_cumulative = (
            credit_charge.amount
            if final_order_refund
            else (
                (order.refunded_amount or Decimal("0"))
                * credit_charge.amount
                / order_total
            ).quantize(Decimal("0.01"))
        )
    # FIN-TAX-01 (OPS-DATA-02 §11.2): كل share هنا لازم يترد بنفس الفصل
    # (إيراد صافي/VAT/service) اللي اترحّل بيه وقت البيع، مش يعكس كله على
    # حساب الإيراد كأنه "مصروف عكسي" واحد. order.vat_amount/service_charge
    # نسبة إلى order.total ثابتة على مستوى الطلب كله (بتتحدد وقت الإنشاء
    # ومابتتغيّرش بعد كده)، فبتتطبّق على أي share جزئي هنا بنفس النسبة —
    # net_share = share - vat_share - svc_share بالباقي (متوازن دايمًا
    # بالضبط بحكم الطرح، مش بحاجة remainder tracking عبر الأجزاء).
    vat_ratio = (order.vat_amount / order_total) if order.vat_amount else Decimal("0")
    svc_ratio = (order.service_charge / order_total) if order.service_charge else Decimal("0")

    allocated = Decimal("0")
    last_idx = len(parts) - 1
    for idx, (kind, amount, payment) in enumerate(parts):
        if idx == last_idx:
            share = refund_amount - allocated
        else:
            share = (refund_amount * amount / order_total).quantize(Decimal("0.01"))
        if kind == "credit":
            # Allocate to the cumulative target, not by rounding every refund
            # independently. This prevents many small item refunds from
            # accumulating cents above/below the original credit tender.
            share = min(
                max(Decimal("0"), credit_target_cumulative - credit_refunded),
                credit_remaining,
                refund_amount - allocated,
            )
        if share <= 0:
            continue
        vat_share = (share * vat_ratio).quantize(Decimal("0.01"))
        svc_share = (share * svc_ratio).quantize(Decimal("0.01"))
        net_share = share - vat_share - svc_share
        if kind == "credit":
            from app.modules.credit import services as credit_services  # noqa: PLC0415

            debit_allocations = [(revenue_account_code, net_share, cost_center_code)]
            if vat_share > 0:
                debit_allocations.append(("2160", vat_share, cost_center_code))
            if svc_share > 0:
                debit_allocations.append(("2165", svc_share, cost_center_code))
            credit_services.refund_charge(
                db,
                credit_charge.id,
                order.branch_id,
                share,
                f"مرتجع صنف من طلب {order.order_number}",
                refunded_by,
                debit_allocations=debit_allocations,
                commit=False,
            )
        elif kind == "direct":
            # حساب الطريقة الأصلي نفسه — cash→1100، card/wallet→حساب المقاصّة
            # المهيّأ. لو الطريقة اتشالت تهيئتها بعد البيع، fail-closed (503).
            account = resolve_direct_tender_account(payment.method)
            finance_crud.create_direct_payment(
                db, branch_id=order.branch_id, amount=-share, method=payment.method,
                posted_at=datetime.utcnow(), shift_id=shift_id, cashier_id=refunded_by,
                reference=f"ORD-REFUND-{order.order_number}", ref_order_id=order.id,
                source="dining_refund", original_payment_id=payment.id,
            )
            finance_services.reverse_taxed_sale_journal(
                db, order.branch_id, local_today(settings.TIMEZONE),
                debit_account_code=account, revenue_account_code=revenue_account_code,
                net_revenue_amount=net_share, vat_amount=vat_share, service_charge_amount=svc_share,
                reference=f"ORD-REFUND-{order.order_number}-{payment.id}",
                description=f"مرتجع بعد الدفع ({payment.method}) — {order.order_number}",
                source="dining_refund", source_id=order.id,
                cost_center_code=cost_center_code,
                commit_cost_centers=False,
            )
        else:  # room
            _reduce_folio_charge_for_refund(
                db, order, share, revenue_account_code,
                vat_amount=vat_share, service_charge_amount=svc_share, outlet=outlet,
            )
        allocated += share


def _reduce_folio_charge_for_refund(
    db: Session, order: DiningOrder, refund_amount: Decimal,
    revenue_account_code: str, *,
    vat_amount: Decimal = Decimal("0"), service_charge_amount: Decimal = Decimal("0"),
    outlet: Optional[Outlet] = None,
) -> None:
    """يقلّل شحنة فوليو الطلب بحصة الغرفة من المرتجع + قيد عكسي Dr إيراد / Cr
    1150. Gate 4 (High 4a): fail-closed — لو الشحنة مش موجودة أو الفوليو
    مقفول/مفقود، بيرفع ValueError بدل ما يبتلع الفشل بعد logging (اللي كان
    بيسيب الطلب 'refunded' من غير عكس محاسبي مقابل — أثر جزئي متناقض).

    بيفلتر charge_type + folio_id (منع تلبيس على شحنة outlet تاني في نفس
    الفوليو، نفس الباج اللي اتصلح في المصدر الأصلي)."""
    from app.modules.finance import crud as finance_crud  # noqa: PLC0415
    from app.modules.finance.models import FolioCharge  # noqa: PLC0415

    charge = (
        db.query(FolioCharge)
        .filter_by(ref_order_id=order.id, folio_id=order.folio_id, charge_type="dining")
        .first()
    )
    if not charge:
        raise ValueError(
            f"مفيش شحنة فوليو مطابقة للطلب {order.order_number} — لا يمكن عكس حصة الغرفة من المرتجع"
        )
    folio = finance_crud.get_folio(db, order.folio_id)
    if not folio:
        raise ValueError("الفوليو المرتبط بالطلب غير موجود — لا يمكن عكس المرتجع")
    if folio.status == "closed":
        raise ValueError(
            "الفوليو مقفول (تم checkout الضيف) — مينفعش عكس مرتجع الغرفة تلقائيًا، محتاج تسوية محاسبية يدوية"
        )
    gross_before = charge.amount + charge.vat_amount + charge.service_charge
    new_gross = max(Decimal("0"), gross_before - refund_amount)
    ratio = (new_gross / gross_before) if gross_before > 0 else Decimal("0")
    charge.amount = (charge.amount * ratio).quantize(Decimal("0.01"))
    charge.vat_amount = (charge.vat_amount * ratio).quantize(Decimal("0.01"))
    charge.service_charge = (charge.service_charge * ratio).quantize(Decimal("0.01"))
    db.flush()
    finance_crud.recalculate_folio_total(db, folio)
    _post_order_folio_refund_reversal_journal(
        db, order, refund_amount, revenue_account_code,
        vat_amount=vat_amount, service_charge_amount=service_charge_amount, outlet=outlet,
    )


def _post_order_folio_refund_reversal_journal(
    db: Session, order: DiningOrder, refund_amount: Decimal,
    revenue_account_code: str, *,
    vat_amount: Decimal = Decimal("0"), service_charge_amount: Decimal = Decimal("0"),
    outlet: Optional[Outlet] = None,
) -> None:
    from app.modules.finance.services import reverse_taxed_sale_journal  # noqa: PLC0415

    outlet = outlet or crud.get_outlet(db, order.outlet_id)
    net_amount = refund_amount - vat_amount - service_charge_amount
    # Gate 4 (High 4a) + FIN-TAX-01 (OPS-DATA-02 §11.2): fail-closed — فشل
    # ترحيل القيد بيرفع بدل ما يرجّع None بصمت، عشان عكس شحنة الفوليو
    # والقيد المقابل يفشلوا كوحدة واحدة. القيد بيعكس نفس فصل الإيراد/VAT/
    # service الأصلي بدل Dr Revenue بالإجمالي.
    reverse_taxed_sale_journal(
        db, order.branch_id, local_today(settings.TIMEZONE),
        debit_account_code="1150", revenue_account_code=revenue_account_code,
        net_revenue_amount=net_amount, vat_amount=vat_amount, service_charge_amount=service_charge_amount,
        reference=f"ORD-REFUND-{order.order_number}",
        description=f"مرتجع بعد الدفع (محمّل على الغرفة) — {order.order_number}",
        source="dining_folio_refund", source_id=order.id,
        cost_center_code=_outlet_cost_center_code(outlet),
        commit_cost_centers=False,
    )
