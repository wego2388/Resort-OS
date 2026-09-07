"""
app/modules/dining/_services/settlement.py
Extracted from app/modules/dining/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.modules.dining import crud
from app.modules.dining.models import DiningOrder
from app.resort_os.timezone_utils import (
    local_today,
    utc_naive_to_local_date,
)
from app.modules.dining._services._exceptions import (
    OrderAlreadyPaidError,
    InvalidOrderTotalError,
    InvalidPaymentMethodError,
    IdempotencyConflictError,
    NoOpenShiftError,
    PaymentAllocationError,
)
from app.modules.dining._services._helpers import (
    _get_order_or_404,
    _lock_order_or_conflict,
    _outlet_cost_center_code,
    _build_outlet_revenue_splits,
    _effective_recipe,
)


def _settlement_intent_hash(order_id: int, tenders: list[dict]) -> str:
    """sha256 لبنية التسوية الأساسية — نفس order_id + نفس مجموعة الـ tenders
    (طريقة/مبلغ/غرفة، مرتبة) = نفس الـ hash. أساس idempotency: retry بنفس
    النية بيطابق، ونية مختلفة بنفس المفتاح بتترفض 409. المبلغ None (دفع
    كامل بـ tender واحد) بيتمثّل كـ "full" عشان يفضل ثابت عبر إعادة المحاولة."""
    norm = [
        {
            "method": str(t["method"]),
            "amount": (
                "full"
                if t.get("amount") is None
                else str(Decimal(str(t["amount"])).quantize(Decimal("0.01")))
            ),
            "charge_to_room_id": t.get("charge_to_room_id"),
            "credit_account_id": t.get("credit_account_id"),
        }
        for t in tenders
    ]
    norm.sort(key=lambda t: (t["method"], t["amount"], str(t["charge_to_room_id"] or "")))
    canonical = json.dumps(
        {"order_id": order_id, "tenders": norm},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def settle_order(
    db: Session,
    order_id: int,
    *,
    tenders: list[dict],
    settled_by: Optional[int] = None,
    acting_user_level: int = 100,
    approver_user_id: Optional[int] = None,
    approver_pin: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> DiningOrder:
    """وحدة العمل الصارمة الموحّدة لتحصيل طلب دايننج (Gate 4A) — المسار
    الوحيد لتحويل طلب لـ "مدفوع"، سواء بـ tender واحد (paid) أو أكتر (split).
    commit واحد بس؛ أي فشل بيعمل rollback كامل صريح.

    ``tenders``: list of {"method": cash|card|wallet|room, "amount": Decimal|None,
    "charge_to_room_id": Optional[int]}. amount=None مسموح فقط لـ tender واحد
    (يعني "الإجمالي كله"). مجموع المبالغ لازم يساوي order.total بدقة Decimal.

    عقد الذرّية (الـ brief §2.3): في نفس المعاملة — قفل الطلب وإعادة فحصه،
    idempotency guard، شحنة الفوليو للجزء المحمّل على الغرفة، Payment لكل
    tender مباشر منسوب للكاشير/الوردية، خصم المخزون، القيد المحاسبي الصح لكل
    allocation، زيارة العميل، حالة الطلب والطاولة، وصف DiningSettlement.
    """
    from app.modules.dining.payment_policy import (  # noqa: PLC0415
        ALL_TENDER_METHODS, is_direct_method, resolve_tender_channel,
    )
    from app.modules.finance import services as finance_services  # noqa: PLC0415

    try:
        order = _lock_order_or_conflict(db, order_id)

        intent_hash = _settlement_intent_hash(order_id, tenders)

        # idempotency guard — قبل أي فحص حالة، عشان replay ناجح يرجّع نفس
        # النتيجة حتى لو الطلب بقى "paid".
        if idempotency_key:
            existing = crud.get_settlement_by_key(db, order.branch_id, idempotency_key)
            if existing is not None:
                if existing.order_id == order_id and existing.intent_hash == intent_hash:
                    db.rollback()  # مفيش تعديل — نسيب القفل ونرجّع النتيجة الموجودة
                    return _get_order_or_404(db, order_id)
                raise IdempotencyConflictError(
                    "نفس مفتاح الـ idempotency اتبعت لعملية دفع مختلفة — "
                    "استخدم مفتاح جديد لمحاولة جديدة"
                )

        if order.status == "paid":
            raise OrderAlreadyPaidError(f"الطلب #{order_id} مدفوع بالفعل")
        if order.status in ("cancelled", "refunded"):
            raise ValueError(f"لا يمكن تحصيل طلب بحالة '{order.status}'")

        if (order.total or Decimal("0")) <= 0:
            raise InvalidOrderTotalError(f"إجمالي الطلب #{order_id} غير صالح (صفر أو سالب)")

        # ── تطبيع وتحقق الـ tenders ──────────────────────────────────
        if not tenders:
            raise PaymentAllocationError("لازم tender واحد على الأقل")
        none_amounts = [t for t in tenders if t.get("amount") is None]
        if none_amounts and len(tenders) > 1:
            raise PaymentAllocationError("amount=None (الإجمالي كله) مسموح فقط لـ tender واحد")

        norm: list[dict] = []
        for t in tenders:
            method = t["method"]
            if method not in ALL_TENDER_METHODS:
                raise PaymentAllocationError(f"طريقة دفع غير معروفة: {method}")
            amount = order.total if t.get("amount") is None else Decimal(str(t["amount"])).quantize(Decimal("0.01"))
            if amount <= 0:
                raise PaymentAllocationError(f"مبلغ tender غير صالح: {amount}")
            norm.append({
                "method": method,
                "amount": amount,
                "charge_to_room_id": t.get("charge_to_room_id"),
                "credit_account_id": t.get("credit_account_id"),
                # POS-03: عملة/سعر الصرف للكاش بعملة أجنبية — بيتمرّر لـ _settle_direct_tender
                "currency": (t.get("currency") or "EGP").upper(),
                "fx_rate": t.get("fx_rate"),
                "payment_channel_id": t.get("payment_channel_id"),
            })

        # M1 (جولة مراجعة Codex الأولى): مقارنة Decimal دقيقة بعد quantize
        # للطرفين — مش tolerance ± 0.01 اللي كان بيسمح بانحراف قرش كامل يعدّي
        # (الـ brief §2.1: "لا tolerance غامضة تسمح بزيادة/نقص فعلي"). كل
        # مبلغ tender متكوّنتز أصلاً لـ 0.01، وorder.total عمود Numeric(_,2)،
        # فمجموع الـ tenders الصح لازم يساوي order.total بالظبط.
        total_tenders = sum((t["amount"] for t in norm), Decimal("0")).quantize(Decimal("0.01"))
        order_total_q = (order.total or Decimal("0")).quantize(Decimal("0.01"))
        if total_tenders != order_total_q:
            raise PaymentAllocationError(
                f"مجموع الدفعات ({total_tenders:.2f}) لا يساوي إجمالي الطلب ({order_total_q:.2f})"
            )

        direct = [t for t in norm if is_direct_method(t["method"])]
        room = [t for t in norm if t["method"] == "room"]
        credit = [t for t in norm if t["method"] == "credit_account"]

        if len(room) > 1:
            raise PaymentAllocationError(
                "تقسيم الدفع على أكثر من tender غرفة غير مدعوم بأمان؛ "
                "استخدم tender غرفة واحد والباقي طرق دفع مباشرة"
            )

        # حل قناة التحصيل/حساب GL لكل tender مباشر (fail-closed) قبل أي
        # تعديل — قناة حقيقية مُعرَّفة (finance.PaymentChannel) هي المصدر
        # الأساسي؛ فرع بلا قنوات لسه بيشتغل بمسار الحساب القديم (legacy).
        # أي طريقة غير مهيّأة في الاتنين بترفع PaymentMethodNotConfiguredError.
        for t in direct:
            resolution = resolve_tender_channel(
                db, order.branch_id, t["method"], t.get("payment_channel_id"),
            )
            t["account"] = resolution.account_code
            t["channel_snapshot"] = resolution.channel_snapshot

        # tender مباشر محتاج وردية مفتوحة لنفس الكاشير والفرع (الـ brief §2.1).
        # الإنفاذ بيتفعّل كل ما فيه كاشير محدد (settled_by) — وده **دايمًا**
        # صحيح على مسار الإنتاج الوحيد (الـ router بيفرض كاشير+ ويمرّر user.id،
        # راجع PATCH .../status و.../split-bill)، فالـ invariant مضمون في
        # الإنتاج بالكامل. settled_by=None يعني مفيش actor كاشير أصلاً (نداء
        # داخلي/قديم، مش مسار HTTP) — في الحالة دي الـ tender بيتسجّل بدون
        # نسبة وردية بدل ما نرفض بالغلط "كاشير بلا وردية" وهو مفيش كاشير أصلاً.
        # Gate 4 (جولة مراجعة Codex الأولى): نقفل صف الوردية (NOWAIT) بدل
        # قراءة غير مقفولة — عشان نسب الـ Payment للوردية يتسلسل فعليًا ضد
        # close_shift (نفس الصف). ترتيب القفل ثابت: Order (اتقفل فوق) قبل
        # Shift — مفيش مسار تاني بياخد Shift قبل Order، فمفيش deadlock. لو
        # الوردية بتتقفل الآن → ShiftCloseInProgressError (409 retry).
        shift_id = None
        if direct and settled_by is not None:
            open_shift = finance_services._lock_open_shift_or_conflict(db, order.branch_id, settled_by)
            if not open_shift:
                raise NoOpenShiftError(
                    "مفيش وردية مفتوحة لهذا الكاشير — لازم تفتح وردية قبل تحصيل دفع مباشر"
                )
            shift_id = open_shift.id

        # حل فوليو كل tender غرفة
        for t in room:
            room_id = t.get("charge_to_room_id")
            if room_id:
                from app.modules.pms.services import find_active_folio_for_room  # noqa: PLC0415
                folio_id = find_active_folio_for_room(db, order.branch_id, room_id)
                if not folio_id:
                    raise ValueError(f"مفيش ضيف مسجّل دخول في الغرفة {room_id} حاليًا")
            elif order.folio_id:
                folio_id = order.folio_id
            else:
                raise InvalidPaymentMethodError(
                    "الدفع على الغرفة محتاج charge_to_room_id أو فوليو مرتبط بالطلب بالفعل"
                )
            t["folio_id"] = folio_id

        # تناقض: فوليو مرتبط بالطلب بالفعل لكن مفيش أي tender غرفة (قيد فوليو
        # هيترحّل بينما الدفع بيدّعي كاش/بطاقة) — نفس شبكة أمان Gate 1B.
        if order.folio_id and not room:
            raise InvalidPaymentMethodError(
                f"الطلب مرتبط بفوليو #{order.folio_id} لكن مفيش دفعة 'room' — "
                "القيد المحاسبي لازم يتطابق مع طريقة الدفع"
            )

        # حل credit account لكل credit tender — fail-fast قبل أي تعديل
        if credit:
            from app.modules.credit import crud as credit_crud  # noqa: PLC0415
            if len(credit) > 1:
                raise PaymentAllocationError(
                    "استخدم جزء حساب آجل واحد فقط في الفاتورة المقسمة"
                )
            for t in credit:
                if t.get("credit_account_id"):
                    _credit_acc = credit_crud.get_account(db, t["credit_account_id"])
                    if not _credit_acc or _credit_acc.branch_id != order.branch_id:
                        raise InvalidPaymentMethodError(
                            "الحساب الآجل غير موجود في هذا الفرع"
                        )
                    if _credit_acc.holder_type == "customer" and (
                        not order.customer_id or _credit_acc.customer_id != order.customer_id
                    ):
                        raise InvalidPaymentMethodError(
                            "حساب العميل الآجل لا يطابق العميل المربوط بالطلب"
                        )
                else:
                    if not order.customer_id:
                        raise InvalidPaymentMethodError(
                            "حدد حساب الموظف الآجل أو اربط الطلب بعميل"
                        )
                    _credit_acc = credit_crud.get_account_for_customer(
                        db, order.customer_id, order.branch_id
                    )
                    if not _credit_acc:
                        raise InvalidPaymentMethodError(
                            f"العميل {order.customer_id} ليس لديه حساب آجل في هذا الفرع"
                        )
                t["credit_account_id"] = _credit_acc.id

        # ── تنفيذ التسوية ────────────────────────────────────────────
        single_tender = len(norm) == 1
        if single_tender:
            order.payment_method = norm[0]["method"]
        else:
            order.payment_method = "split:" + ",".join(t["method"] for t in norm)
        if room and not order.folio_id:
            order.folio_id = room[0]["folio_id"]

        order = crud.update_order_status(db, order, "paid")
        if order.table_id:
            table = crud.get_table(db, order.table_id)
            if table:
                crud.update_table_status(db, table, "available")

        outlet = crud.get_outlet(db, order.outlet_id)
        revenue_account = outlet.revenue_account_code if outlet else "4200"

        # حساب توزيع الإيراد per-outlet (cross-outlet support):
        # لو كل الأصناف من نفس الـ outlet → قيد واحد (المسار العادي).
        # لو فيه أصناف من outlets مختلفة → كل outlet بيتقيّد إيراده منفصل.
        outlet_splits = _build_outlet_revenue_splits(db, order, order.outlet_id)

        for tender_idx, t in enumerate(room):
            _settle_room_tender(
                db, order, t, revenue_account,
                single_tender=single_tender,
                outlet_splits=outlet_splits,
                tender_idx=tender_idx,
            )
        for tender_idx, t in enumerate(direct):
            _settle_direct_tender(
                db, order, t, revenue_account,
                cashier_id=settled_by, shift_id=shift_id,
                outlet_splits=outlet_splits,
                tender_idx=tender_idx,
            )
        for t in credit:
            _settle_credit_tender(
                db, order, t, revenue_account,
                cashier_id=settled_by,
                outlet_splits=outlet_splits,
                acting_user_level=acting_user_level,
                approver_user_id=approver_user_id,
                approver_pin=approver_pin,
            )

        # 2026-09-04 — طلب Mohamed: استهلاك مجموعات "ضيافة/تكريم" (زي
        # الموظفين) يترحّل كمصروف حقيقي بدل ما يختفي بصمت مع الخصم.
        _post_complimentary_expense_if_applicable(db, order, outlet_splits, revenue_account)

        # خصم المخزون مرة واحدة للطلب كله جوه المعاملة الصارمة.
        _deduct_inventory_for_order(db, order, commit=False, strict=True)

        if order.customer_id:
            from app.modules.crm.services import record_customer_visit  # noqa: PLC0415
            visit_date = (
                utc_naive_to_local_date(order.created_at, settings.TIMEZONE)
                if order.created_at else local_today(settings.TIMEZONE)
            )
            record_customer_visit(db, order.customer_id, order.total, visit_date)

        # M2 (جولة مراجعة Codex الأولى): لقطة توزيع الـ tenders — مصدر تاريخي
        # مستقل عن حالة Payment (تقرير الوردية بيجمع حصة الغرفة من هنا،
        # والإيصال التاريخي يعيد بناء الـ split بدون سعر منيو حالي).
        tender_breakdown = [
            {
                "method": t["method"],
                "amount": str(t["amount"]),
                **({"account": t["account"]} if t.get("account") else {}),
                **({"folio_id": t["folio_id"]} if t.get("folio_id") else {}),
                **({"credit_account_id": t["credit_account_id"]} if t.get("credit_account_id") else {}),
                **(
                    {
                        "payment_channel_id": t["channel_snapshot"]["payment_channel_id"],
                        "payment_channel_code": t["channel_snapshot"]["payment_channel_code"],
                        "payment_channel_name": t["channel_snapshot"]["payment_channel_name"],
                    }
                    if t.get("channel_snapshot") and t["channel_snapshot"].get("payment_channel_id")
                    else {}
                ),
            }
            for t in norm
        ]
        crud.create_settlement(
            db, branch_id=order.branch_id, order_id=order.id,
            idempotency_key=idempotency_key, intent_hash=intent_hash,
            total=order.total, cashier_id=settled_by if direct else None,
            shift_id=shift_id, created_by=settled_by,
            tender_breakdown=tender_breakdown,
        )

        # Gate 8: a linked "request bill" is operational state only. Close
        # it in this same strict payment transaction after all financial
        # effects succeeded and before the single commit.
        from app.modules.core import services as core_services  # noqa: PLC0415
        core_services.resolve_bill_requests_for_paid_order(db, order, settled_by)

        db.commit()
        db.refresh(order)
        return order
    except Exception:
        db.rollback()
        raise


def _settle_room_tender(
    db: Session, order: DiningOrder, tender: dict, revenue_account_code: str,
    *, single_tender: bool,
    outlet_splits: "list[tuple] | None" = None,
    tender_idx: int = 0,
) -> None:
    """جزء الطلب المحمّل على فوليو غرفة — شحنة فوليو + قيد Dr ذمم(1150)/Cr
    إيراد. outlet_splits: لو فيه cross-outlet — كل split بيتقيّد على حساب
    الـ outlet الخاص به بدل حساب order.outlet فقط. tender_idx: ترتيب هذا
    الـ tender بين عدة room tenders لنفس الطلب (نادر بس ممكن — تسوية مقسّمة
    على أكتر من فوليو غرفة) — لازم يدخل في reference القيد المحاسبي (راجع
    _post_folio_revenue_splits) وإلا الـ idempotency check الجديدة في
    post_taxed_sale_journal هتعتبر تاني tender نفس القيد الأول وترجّعه من
    غير ترحيل حقيقي (FIN-TAX-01، OPS-DATA-02 §11.2)."""
    from app.modules.finance import services as finance_services  # noqa: PLC0415
    from app.modules.finance.schemas import FolioChargeCreate  # noqa: PLC0415

    folio_id = tender["folio_id"]
    if single_tender:
        discount = order.discount_amount or Decimal("0")
        net_subtotal = max(Decimal("0"), order.subtotal - discount)
        charge_data = FolioChargeCreate(
            charge_type="dining", description=f"طلب {order.order_number}",
            amount=net_subtotal, vat_amount=order.vat_amount,
            service_charge=order.service_charge,
            posted_at=datetime.utcnow(), ref_order_id=order.id,
        )
        finance_services.add_folio_charge(db, folio_id, charge_data)
        # قيد الإيراد per-outlet
        _post_folio_revenue_splits(db, order, outlet_splits, revenue_account_code, tender_idx=tender_idx)
        return

    amount = tender["amount"]
    ratio = (amount / order.total) if order.total > 0 else Decimal("0")
    vat_share = (order.vat_amount * ratio).quantize(Decimal("0.01"))
    svc_share = (order.service_charge * ratio).quantize(Decimal("0.01"))
    amt_share = amount - vat_share - svc_share
    charge_data = FolioChargeCreate(
        charge_type="dining", description=f"طلب {order.order_number} (split)",
        amount=amt_share, vat_amount=vat_share, service_charge=svc_share,
        posted_at=datetime.utcnow(), ref_order_id=order.id,
    )
    finance_services.add_folio_charge(db, folio_id, charge_data)
    # split tender — نوزّع القيد per-outlet بنسبة حصة الـ tender
    _post_folio_revenue_splits(
        db, order, outlet_splits, revenue_account_code,
        tender_ratio=ratio, tender_idx=tender_idx,
    )


def _post_folio_revenue_splits(
    db: Session, order: DiningOrder,
    outlet_splits: "list[tuple] | None",
    fallback_revenue_code: str,
    tender_ratio: "Decimal | None" = None,
    tender_idx: int = 0,
) -> None:
    """يُرحّل قيود Dr.1150/Cr.إيراد صافي + VAT/service payable per-outlet —
    يدعم single وsplit tenders. tender_ratio=None → قيد كامل (single_tender).
    tender_ratio=X → نسبة X من كل split.

    OPS-DATA-02 §11.2 (FIN-TAX-01): كانت الدالة دي بترحّل total_share
    (الإجمالي شامل VAT/service بعد الخصم) كله على حساب الإيراد — الفصل
    (VAT→2160، service→2165) اتضاف هنا بدل post_taxed_sale_journal، والباقي
    (نسب per-outlet/split-tender/الخصم/rounding) زي ما هو بالظبط.

    reference لازم يكون فريد لكل قيد حقيقي مختلف داخل نفس الطلب (tender_idx
    لتعدد room tenders النادر، outlet.id لcross-outlet) — post_taxed_sale_
    journal الصارمة idempotent بـ(branch/source/source_id/reference)، فلو
    قيدين مختلفين فعليًا استخدموا نفس reference كانت التانية هترجع نسخة
    القيد الأولى بدل ما ترحّل فعليًا (باج حقيقي اتكشف واتصلح وقت كتابة
    هذه الدفعة — راجع test_cross_outlet_order_posts_per_outlet_journals)."""
    from app.modules.finance import services as finance_services  # noqa: PLC0415
    one = Decimal("1")
    ratio = tender_ratio if tender_ratio is not None else one
    ref_base = f"ORD-{order.order_number}" + (f"-T{tender_idx}" if tender_idx else "")

    if not outlet_splits or len(outlet_splits) == 1:
        # المسار العادي — قيد واحد
        outlet = outlet_splits[0][0] if outlet_splits else None
        rev_code = outlet.revenue_account_code if outlet else fallback_revenue_code
        base_amount = (outlet_splits[0][1] if outlet_splits else (order.subtotal or Decimal("0")))
        vat_share = (order.vat_amount * ratio).quantize(Decimal("0.01"))
        svc_share = (order.service_charge * ratio).quantize(Decimal("0.01"))
        disc_share = ((order.discount_amount or Decimal("0")) * ratio).quantize(Decimal("0.01"))
        net_share = (base_amount * ratio - disc_share).quantize(Decimal("0.01"))
        total_share = net_share + vat_share + svc_share
        if total_share > 0:
            finance_services.post_taxed_sale_journal(
                db, order.branch_id, local_today(settings.TIMEZONE),
                debit_account_code="1150", revenue_account_code=rev_code,
                net_revenue_amount=net_share, vat_amount=vat_share, service_charge_amount=svc_share,
                reference=ref_base,
                description=f"إيرادات دايننج (فوليو) — {order.order_number}",
                source="dining_folio_charge", source_id=order.id,
                cost_center_code=_outlet_cost_center_code(outlet),
                commit_cost_centers=False,
            )
        return

    # cross-outlet — قيد لكل outlet بنسبة subtotal
    total_subtotal = sum(s for _, s in outlet_splits) or Decimal("1")
    for idx, (outlet, sub) in enumerate(outlet_splits):
        sub_ratio = (sub / total_subtotal * ratio).quantize(Decimal("0.0001"))
        vat_share = (order.vat_amount * sub_ratio).quantize(Decimal("0.01"))
        svc_share = (order.service_charge * sub_ratio).quantize(Decimal("0.01"))
        disc_share = ((order.discount_amount or Decimal("0")) * sub_ratio).quantize(Decimal("0.01"))
        net_share = (sub * ratio - disc_share).quantize(Decimal("0.01"))
        amount_share = net_share + vat_share + svc_share
        if amount_share <= 0:
            continue
        finance_services.post_taxed_sale_journal(
            db, order.branch_id, local_today(settings.TIMEZONE),
            debit_account_code="1150",
            revenue_account_code=outlet.revenue_account_code,
            net_revenue_amount=net_share, vat_amount=vat_share, service_charge_amount=svc_share,
            reference=f"{ref_base}-OUT{outlet.id}",
            description=f"إيرادات دايننج (فوليو/{outlet.name}) — {order.order_number}",
            source="dining_folio_charge", source_id=order.id,
            cost_center_code=_outlet_cost_center_code(outlet),
            commit_cost_centers=False,
        )


def _post_complimentary_expense_if_applicable(
    db: Session, order: DiningOrder,
    outlet_splits: "list[tuple] | None",
    fallback_revenue_code: str,
) -> None:
    """2026-09-04 — طلب Mohamed: لو عميل الطلب مربوط بمجموعة "ضيافة/تكريم"
    حقيقية (CustomerGroup.is_complimentary — زي مجموعة "الموظفين")، الجزء
    المخصوم من الطلب بيترحّل كمصروف ضيافة حقيقي (5400) بدل ما يختفي بصمت مع
    الخصم. من غير القيد ده: المخزون بيتخصم فعليًا (_deduct_inventory_for_order
    شغالة لكل الطلبات بغض النظر عن الخصم) لكن مفيش أي أثر محاسبي مقابل —
    يعني تقرير تكلفة الطعام كان هيشوف نقص مخزون "مجهول" بدل مصروف موثّق.

    خصومات المجموعات العادية (ولاء، سعر شركات متفاوَض) **ميتأثروش خالص** —
    دول تسعير تجاري حقيقي، الإيراد المخفّض هو الإيراد الصح من الأساس، صفر
    قيد إضافي. الفرق كله في علم CustomerGroup.is_complimentary.

    النسبة (net/vat/service) للجزء المخصوم بتتحسب بنفس أسلوب _settle_direct_
    tender بالظبط (نسبة من نفس order.vat_amount/service_charge الكاملين) —
    عشان مجموع (الجزء المُحصَّل + الجزء المُتبرَّع به) يفضل يساوي القيم
    الكاملة المخزّنة على الطلب بالظبط، بدون أي ازدواج أو فقدان قرش."""
    from app.modules.crm.services import is_customer_group_complimentary  # noqa: PLC0415
    from app.modules.finance import services as finance_services  # noqa: PLC0415

    discount = order.discount_amount or Decimal("0")
    if discount <= 0 or not order.customer_id:
        return
    if not is_customer_group_complimentary(db, order.customer_id):
        return

    full_amount_before_discount = (order.total or Decimal("0")) + discount
    if full_amount_before_discount <= 0:
        return
    ratio = discount / full_amount_before_discount
    vat_share = (order.vat_amount * ratio).quantize(Decimal("0.01"))
    svc_share = (order.service_charge * ratio).quantize(Decimal("0.01"))
    ref_base = f"ORD-{order.order_number}-COMP"

    if not outlet_splits or len(outlet_splits) == 1:
        outlet = outlet_splits[0][0] if outlet_splits else None
        rev_code = outlet.revenue_account_code if outlet else fallback_revenue_code
        net_share = (discount - vat_share - svc_share).quantize(Decimal("0.01"))
        if net_share + vat_share + svc_share <= 0:
            return
        finance_services.post_taxed_sale_journal(
            db, order.branch_id, local_today(settings.TIMEZONE),
            debit_account_code="5400", revenue_account_code=rev_code,
            net_revenue_amount=net_share, vat_amount=vat_share, service_charge_amount=svc_share,
            reference=ref_base,
            description=f"استهلاك مجموعة ضيافة/تكريم — {order.order_number}",
            source="dining_complimentary_expense", source_id=order.id,
            cost_center_code=_outlet_cost_center_code(outlet),
            commit_cost_centers=False,
        )
        return

    total_subtotal = sum(s for _, s in outlet_splits) or Decimal("1")
    for outlet, sub in outlet_splits:
        sub_ratio = (sub / total_subtotal).quantize(Decimal("0.0001"))
        outlet_vat = (vat_share * sub_ratio).quantize(Decimal("0.01"))
        outlet_svc = (svc_share * sub_ratio).quantize(Decimal("0.01"))
        outlet_disc = (discount * sub_ratio).quantize(Decimal("0.01"))
        outlet_net = (outlet_disc - outlet_vat - outlet_svc).quantize(Decimal("0.01"))
        amount = outlet_net + outlet_vat + outlet_svc
        if amount <= 0:
            continue
        finance_services.post_taxed_sale_journal(
            db, order.branch_id, local_today(settings.TIMEZONE),
            debit_account_code="5400", revenue_account_code=outlet.revenue_account_code,
            net_revenue_amount=outlet_net, vat_amount=outlet_vat, service_charge_amount=outlet_svc,
            reference=f"{ref_base}-OUT{outlet.id}",
            description=f"استهلاك مجموعة ضيافة/تكريم ({outlet.name}) — {order.order_number}",
            source="dining_complimentary_expense", source_id=order.id,
            cost_center_code=_outlet_cost_center_code(outlet),
            commit_cost_centers=False,
        )


def _settle_direct_tender(
    db: Session, order: DiningOrder, tender: dict, revenue_account_code: str,
    *, cashier_id: Optional[int], shift_id: Optional[int],
    outlet_splits: "list[tuple] | None" = None,
    tender_idx: int = 0,
) -> None:
    """tender مباشر (cash/card/wallet) — Payment حقيقي + قيد Dr <حساب>/Cr
    إيراد صافي + VAT/service payable (FIN-TAX-01، OPS-DATA-02 §11.2).
    outlet_splits: لو cross-outlet — قيود per-outlet بدل قيد واحد.
    POS-03: tender يمكن أن يحتوي currency/fx_rate لدعم الكاش بعملة أجنبية.
    amount في كل الأحوال EGP-equivalent؛ العملة/السعر الأصليين للتدقيق فقط.

    tender["amount"] نسبة من order.total (زي split-tender) — نفس نمط
    _settle_room_tender: نستنتج نصيب VAT/service من نسبة amount/order.total
    (order.total لسه هو الإجمالي شامل الضريبة/الخدمة الحقيقي)."""
    from app.modules.finance import crud as finance_crud  # noqa: PLC0415
    from app.modules.finance import services as finance_services  # noqa: PLC0415

    amount   = tender["amount"]
    method   = tender["method"]
    account  = tender["account"]
    currency = tender.get("currency", "EGP") or "EGP"
    fx_rate  = tender.get("fx_rate")  # None → EGP, create_direct_payment يتعامل معها

    finance_crud.create_direct_payment(
        db, branch_id=order.branch_id, amount=amount, method=method,
        posted_at=datetime.utcnow(), shift_id=shift_id, cashier_id=cashier_id,
        reference=f"ORD-{order.order_number}", ref_order_id=order.id, source="dining",
        currency=currency, fx_rate=fx_rate,
        channel_snapshot=tender.get("channel_snapshot"),
    )

    tender_ratio = (amount / order.total) if order.total > 0 else Decimal("0")
    vat_share = (order.vat_amount * tender_ratio).quantize(Decimal("0.01"))
    svc_share = (order.service_charge * tender_ratio).quantize(Decimal("0.01"))
    net_amount = amount - vat_share - svc_share
    # reference فريد لكل tender/outlet حقيقي — راجع تعليق _post_folio_
    # revenue_splits لسبب الحاجة لده مع post_taxed_sale_journal الـidempotent.
    ref_base = f"ORD-{order.order_number}" + (f"-T{tender_idx}" if tender_idx else "")

    if not outlet_splits or len(outlet_splits) == 1:
        # المسار العادي — قيد واحد
        outlet = outlet_splits[0][0] if outlet_splits else None
        rev_code = outlet.revenue_account_code if outlet else revenue_account_code
        cost_cc = _outlet_cost_center_code(outlet)
        finance_services.post_taxed_sale_journal(
            db, order.branch_id, local_today(settings.TIMEZONE),
            debit_account_code=account, revenue_account_code=rev_code,
            net_revenue_amount=net_amount, vat_amount=vat_share, service_charge_amount=svc_share,
            reference=ref_base,
            description=f"إيرادات دايننج ({method}) — {order.order_number}",
            source="dining", source_id=order.id,
            cost_center_code=cost_cc,
            commit_cost_centers=False,
        )
        return

    # cross-outlet — نوزّع القيد per-outlet بنسبة الـ subtotals، وVAT/service
    # كل واحد بنفس نسبة نصيبه من net_amount (آخر outlet بياخد الباقي
    # لتجنب فروق التقريب، لكل من الصافي والضريبة/الخدمة كل على حدة).
    total_subtotal = sum(s for _, s in outlet_splits) or Decimal("1")
    remaining_net = net_amount
    remaining_vat = vat_share
    remaining_svc = svc_share
    for idx, (outlet, sub) in enumerate(outlet_splits):
        is_last = idx == len(outlet_splits) - 1
        if is_last:
            net_share, vat_out_share, svc_out_share = remaining_net, remaining_vat, remaining_svc
        else:
            outlet_ratio = (sub / total_subtotal).quantize(Decimal("0.0001"))
            net_share = (net_amount * outlet_ratio).quantize(Decimal("0.01"))
            vat_out_share = (vat_share * outlet_ratio).quantize(Decimal("0.01"))
            svc_out_share = (svc_share * outlet_ratio).quantize(Decimal("0.01"))
        share = net_share + vat_out_share + svc_out_share
        if share <= 0:
            continue
        finance_services.post_taxed_sale_journal(
            db, order.branch_id, local_today(settings.TIMEZONE),
            debit_account_code=account,
            revenue_account_code=outlet.revenue_account_code,
            net_revenue_amount=net_share, vat_amount=vat_out_share, service_charge_amount=svc_out_share,
            reference=f"{ref_base}-OUT{outlet.id}",
            description=f"إيرادات دايننج ({method}/{outlet.name}) — {order.order_number}",
            source="dining", source_id=order.id,
            cost_center_code=_outlet_cost_center_code(outlet),
            commit_cost_centers=False,
        )
        remaining_net -= net_share
        remaining_vat -= vat_out_share
        remaining_svc -= svc_out_share


def _settle_credit_tender(
    db: Session, order: DiningOrder, tender: dict, revenue_account_code: str,
    *, cashier_id: Optional[int], outlet_splits: "list[tuple] | None" = None,
    acting_user_level: int = 100,
    approver_user_id: Optional[int] = None,
    approver_pin: Optional[str] = None,
) -> None:
    """tender حساب آجل شخصي — يُرحَّل على CreditAccount.
    الـ credit_account_id تم حله وتخزينه في tender قبل استدعاء هذه الدالة.
    يُنشئ CreditTransaction + JournalEntry (Dr 1160 / Cr revenue account(s)) بدون commit
    — الـ commit الموحّد يتم في نهاية settle_order.
    """
    from app.modules.credit import services as credit_services  # noqa: PLC0415

    amount = tender["amount"]
    allocations: list[tuple[str, Decimal, str | None]] = []
    if not outlet_splits or len(outlet_splits) == 1:
        outlet = outlet_splits[0][0] if outlet_splits else None
        allocations.append((
            outlet.revenue_account_code if outlet else revenue_account_code,
            amount,
            _outlet_cost_center_code(outlet),
        ))
    else:
        total_subtotal = sum(subtotal for _, subtotal in outlet_splits) or Decimal("1")
        remaining = amount
        for index, (outlet, subtotal) in enumerate(outlet_splits):
            share = (
                remaining
                if index == len(outlet_splits) - 1
                else (amount * subtotal / total_subtotal).quantize(Decimal("0.01"))
            )
            allocations.append((
                outlet.revenue_account_code, share, _outlet_cost_center_code(outlet),
            ))
            remaining -= share

    credit_services.charge_to_account(
        db,
        tender["credit_account_id"],
        order.branch_id,
        amount,
        cashier_id or 0,
        ref_order_id=order.id,
        notes=f"طلب {order.order_number}",
        revenue_allocations=allocations,
        acting_user_level=acting_user_level,
        approver_user_id=approver_user_id,
        approver_pin=approver_pin,
        commit=False,
    )


def _mark_order_paid(
    db: Session,
    order_id: int,
    *,
    charge_to_room_id: Optional[int],
    payment_method: Optional[str],
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
    """تحصيل طلب بـ tender واحد (المسار العادي من PATCH .../status=paid) —
    بيبني tender واحد ويمرّره لـ settle_order (المسار الموحّد). يحل طريقة
    الدفع النهائية من payment_method/charge_to_room_id/فوليو الطلب بنفس
    منطق Gate 1B بالظبط (peek غير مقفول لبناء الـ tender؛ settle_order بيعيد
    القفل والتحقق كله تحت قفل صف الطلب).
    POS-03: payment_currency/payment_fx_rate للكاش بعملة أجنبية."""
    order = crud.get_order(db, order_id)
    if not order:
        raise ValueError(f"الطلب {order_id} غير موجود")

    # عقد payment_method/فوليو (Gate 1B) — يترفض 400 قبل أي أثر.
    if charge_to_room_id and payment_method and payment_method != "room":
        raise InvalidPaymentMethodError(
            f"مينفعش تحدد charge_to_room_id مع payment_method='{payment_method}' "
            "— لازم يبقى 'room' لو الدفع محمّل على غرفة"
        )
    if payment_method == "room" and not charge_to_room_id and not order.folio_id:
        raise InvalidPaymentMethodError(
            "payment_method='room' محتاج charge_to_room_id أو فوليو مرتبط بالطلب بالفعل"
        )

    if payment_method:
        method = payment_method
    elif order.folio_id or charge_to_room_id:
        method = "room"
    elif order.payment_method and order.payment_method in ("cash", "card", "wallet", "room", "credit_account"):
        method = order.payment_method
    else:
        method = "cash"

    tender: dict = {
        "method": method,
        "amount": None,
        "charge_to_room_id": charge_to_room_id,
        "credit_account_id": credit_account_id,
        "payment_channel_id": payment_channel_id,
    }
    # POS-03: نمرّر العملة/سعر الصرف فقط لو الدفع كاش بعملة أجنبية
    if method == "cash" and payment_currency and (payment_currency or "EGP").upper() != "EGP":
        tender["currency"] = payment_currency.upper()
        tender["fx_rate"] = payment_fx_rate
    return settle_order(
        db, order_id, tenders=[tender], settled_by=settled_by,
        acting_user_level=acting_user_level,
        approver_user_id=approver_user_id, approver_pin=approver_pin,
        idempotency_key=idempotency_key,
    )


def _deduct_inventory_for_order(
    db: Session, order: DiningOrder, *, commit: bool = True, strict: bool = False,
) -> None:
    """راجع restaurant.services._deduct_inventory_for_order — نفس أولوية
    الخصم بالظبط (وصفة حقيقية → ربط 1:1 قديم → تجاوز صامت).

    commit/strict (Gate 1B): زي consume_stock بالظبط. الافتراضي (True/False)
    يحافظ على السلوك القديم — بيتجاوز (continue) أي بند فشل خصمه بصمت عشان
    فشل مكوّن واحد ميوقفش تحصيل الطلب كله (استخدام split_bill/التوافق
    الخلفي). strict=True (دفع طلب دايننج فقط) بيوقف عند أول فشل ويرفعه —
    استهلاك المخزون بقى جزء من معاملة الدفع الصارمة اللي لازم تفشل كلها أو
    تنجح كلها، مش تكمل من غير أثر مخزون حقيقي بصمت."""
    from app.modules.inventory import crud as inventory_crud  # noqa: PLC0415
    from app.modules.inventory import services as inventory_services  # noqa: PLC0415
    from app.modules.inventory.services import InventoryConfigurationError  # noqa: PLC0415

    outlet = crud.get_outlet(db, order.outlet_id)
    cost_center_code = _outlet_cost_center_code(outlet)

    def _skip_or_raise(strict_message: str) -> None:
        """مراجعة Codex الثانية (Gate 1B): كل "تجاوز صامت" هنا كان بيتحول
        continue بدون تمييز — يعني إعداد ناقص حقيقي (منتج/مخزن محذوف، منتج
        من فرع تاني) كان بيتجاوز بصمت زي بالظبط "الصنف مفهوش وصفة ولا منتج
        مرتبط" (الحالة الوحيدة المقصودة فعلاً تتجاوز). strict=True بقى يفشل
        بوضوح لأي حالة غير الحالة المقصودة دي، مش يكمل من غير خصم مخزون
        حقيقي بصمت."""
        if strict:
            raise InventoryConfigurationError(strict_message)

    active_items = [oi for oi in order.items if oi.status != "cancelled"]
    if not active_items:
        return

    # ── batch-load كل الأصناف والـ variants بـ query واحدة لكل ──────────
    # بدل N queries فردية (N = عدد أصناف الطلب × عدد مكوّنات الوصفة).
    item_ids    = list({oi.item_id for oi in active_items})
    variant_ids = list({oi.variant_id for oi in active_items if oi.variant_id})
    items_map    = crud.get_items_by_ids(db, item_ids)
    variants_map = crud.get_variants_by_ids(db, variant_ids)

    # اجمع كل product_ids المطلوبة (من الوصفات + linked_product_id) قبل الـ loop
    product_ids_needed: set[int] = set()
    for order_item in active_items:
        item = items_map.get(order_item.item_id)
        if not item:
            continue
        variant = variants_map.get(order_item.variant_id) if order_item.variant_id else None
        recipe_lines = _effective_recipe(item, variant)
        if recipe_lines:
            for line in recipe_lines:
                product_ids_needed.add(line.product_id)
        elif item.linked_product_id:
            product_ids_needed.add(item.linked_product_id)

    products_map  = inventory_crud.get_products_by_ids_any_branch(db, list(product_ids_needed))
    wh_ids_needed = {p.warehouse_id for p in products_map.values() if p.warehouse_id}
    warehouses_map = inventory_crud.get_warehouses_by_ids(db, list(wh_ids_needed))

    # ── الـ loop نفسه — صفر queries إضافية داخله ───────────────────────
    for order_item in active_items:
        try:
            item = items_map.get(order_item.item_id)
            if not item:
                _skip_or_raise(
                    f"صنف الطلب #{order_item.id} بيشير لـDiningItem #{order_item.item_id} غير موجود"
                )
                continue
            variant = variants_map.get(order_item.variant_id) if order_item.variant_id else None
            recipe_lines = _effective_recipe(item, variant)
            if recipe_lines:
                for line in recipe_lines:
                    product = products_map.get(line.product_id)
                    if not product:
                        _skip_or_raise(
                            f"منتج الوصفة #{line.product_id} (لصنف #{item.id}) غير موجود"
                        )
                        continue
                    if product.branch_id != order.branch_id:
                        _skip_or_raise(
                            f"منتج الوصفة #{product.id} يخص فرع #{product.branch_id}، "
                            f"مش فرع الطلب #{order.branch_id}"
                        )
                        continue
                    if not product.warehouse_id:
                        _skip_or_raise(f"منتج الوصفة #{product.id} من غير مخزن مرتبط")
                        continue
                    warehouse = warehouses_map.get(product.warehouse_id)
                    if not warehouse:
                        _skip_or_raise(
                            f"مخزن منتج الوصفة #{product.id} (#{product.warehouse_id}) غير موجود"
                        )
                        continue
                    if warehouse.branch_id != order.branch_id:
                        _skip_or_raise(
                            f"مخزن منتج الوصفة #{product.id} يخص فرع #{warehouse.branch_id}، "
                            f"مش فرع الطلب #{order.branch_id}"
                        )
                        continue
                    inventory_services.consume_stock(
                        db,
                        branch_id=order.branch_id,
                        product_id=product.id,
                        warehouse_id=product.warehouse_id,
                        quantity=line.quantity_per_unit * order_item.quantity,
                        reference_type="dining_order",
                        reference_id=order.id,
                        moved_by=0,
                        allow_negative=True,
                        cost_center_code=cost_center_code,
                        commit=commit,
                        strict=strict,
                    )
                continue
            if not item.linked_product_id:
                # الحالة الوحيدة المقصودة عمدًا تتجاوز حتى في strict=True —
                # الصنف مفهوش وصفة ولا منتج مرتبط أصلاً (مش إعداد ناقص).
                continue
            product = products_map.get(item.linked_product_id)
            if not product:
                _skip_or_raise(f"المنتج المرتبط #{item.linked_product_id} (لصنف #{item.id}) غير موجود")
                continue
            if product.branch_id != order.branch_id:
                _skip_or_raise(
                    f"المنتج المرتبط #{product.id} يخص فرع #{product.branch_id}، "
                    f"مش فرع الطلب #{order.branch_id}"
                )
                continue
            if not product.warehouse_id:
                _skip_or_raise(f"المنتج المرتبط #{product.id} من غير مخزن مرتبط")
                continue
            warehouse = warehouses_map.get(product.warehouse_id)
            if not warehouse:
                _skip_or_raise(
                    f"مخزن المنتج المرتبط #{product.id} (#{product.warehouse_id}) غير موجود"
                )
                continue
            if warehouse.branch_id != order.branch_id:
                _skip_or_raise(
                    f"مخزن المنتج المرتبط #{product.id} يخص فرع #{warehouse.branch_id}، "
                    f"مش فرع الطلب #{order.branch_id}"
                )
                continue
            inventory_services.consume_stock(
                db,
                branch_id=order.branch_id,
                product_id=product.id,
                warehouse_id=product.warehouse_id,
                quantity=Decimal(order_item.quantity),
                reference_type="dining_order",
                reference_id=order.id,
                moved_by=0,
                cost_center_code=cost_center_code,
                commit=commit,
                strict=strict,
            )
        except InventoryConfigurationError:
            raise
        except Exception:
            if strict:
                raise
            continue
