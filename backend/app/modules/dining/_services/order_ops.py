"""
app/modules/dining/_services/order_ops.py
Extracted from app/modules/dining/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.modules.dining import crud
from app.modules.dining.models import DiningOrder
from app.modules.dining._services._helpers import (
    _lock_order_or_conflict,
)
from app.modules.dining._services.orders import (
    _ensure_kitchen_tickets_for_order,
)
from app.modules.dining._services.settlement import (
    settle_order,
)
from app.modules.dining._services.discounts import (
    _recompute_order_totals,
    _sync_kitchen_tickets_for_order,
)


def void_order_item(
    db: Session, order_id: int, item_id: int, reason: str, voided_by: int,
    acting_user_level: int = 100, approver_user_id: Optional[int] = None,
    approver_pin: Optional[str] = None,
) -> DiningOrder:
    """راجع restaurant.services.void_order_item — نفس المنطق بالظبط، بما
    فيه موافقة PIN عبر core.services.resolve_pin_approval (مفيش نظام
    موافقة موازي).

    Gate 4 (جولة مراجعة Codex الأولى): قفل الطلب + إعادة فحص الحالة تحت
    القفل — عشان إلغاء صنف مايتسابقش مع دفع نفس الطلب."""
    order = _lock_order_or_conflict(db, order_id)
    if order.status in ("paid", "cancelled", "refunded"):
        raise ValueError(f"لا يمكن إلغاء صنف من طلب '{order.status}' — استخدم مرتجع بعد الدفع")

    item = crud.get_order_item(db, order_id, item_id)
    if not item:
        raise ValueError(f"الصنف {item_id} غير موجود في هذا الطلب")
    if item.status in ("cancelled", "refunded"):
        raise ValueError("الصنف ده ملغي أو مرتجع بالفعل")

    from app.modules.core import policy_engine  # noqa: PLC0415

    approved_by = policy_engine.require_approval(
        db, "void_order_item",
        acting_user_level=acting_user_level,
        approver_user_id=approver_user_id, approver_pin=approver_pin,
        target_branch_id=order.branch_id,
    )

    crud.void_order_item(db, item, reason, voided_by)
    policy_engine.record_policy_audit(
        db, "void_order_item",
        user_id=voided_by, approved_by=approved_by, branch_id=order.branch_id,
        entity_type="dining_order_item", entity_id=item.id,
        data={"reason": reason},
    )

    _recompute_order_totals(db, order)

    db.commit()
    db.refresh(order)
    return order


def transfer_order_table(db: Session, order_id: int, table_id: int) -> DiningOrder:
    """نقل طلب مفتوح من طاولة لأخرى — الضيوف اتحركوا فعليًا لطاولة تانية،
    والكاشير/النادل محتاج ينقل الطلب الجاري من غير ما يلغيه ويعمل واحد
    جديد. راجع restaurant.services.transfer_order_table — نفس المنطق
    بالظبط (الطاولة الجديدة لازم تكون في نفس الفرع، مش خارج الخدمة، ومش
    مشغولة بطلب مفتوح تاني).

    Gate 4 (جولة مراجعة Codex الأولى): قفل الطلب + قفل الطاولة الجديدة
    (blocking) + إعادة فحص الحالة تحت القفل — عشان نقل الطاولة مايتسابقش مع
    دفع الطلب، ولا مع نقل/فتح طلب تاني على نفس الطاولة الوجهة."""
    order = _lock_order_or_conflict(db, order_id)
    if order.status in ("paid", "cancelled", "refunded"):
        raise ValueError(f"لا يمكن نقل طلب بحالة '{order.status}'")

    new_table = crud.get_table(db, table_id)
    if not new_table:
        raise ValueError(f"الطاولة {table_id} غير موجودة")
    if new_table.branch_id != order.branch_id:
        raise ValueError("الطاولة المطلوبة لا تنتمي لنفس فرع الطلب")
    if new_table.status == "out_of_service":
        raise ValueError(f"الطاولة {new_table.table_number} خارج الخدمة")
    if order.table_id == table_id:
        raise ValueError(f"الطلب بالفعل على الطاولة {new_table.table_number}")

    crud.lock_table_for_update(db, table_id)
    conflicting = crud.get_active_order_for_table(db, table_id, exclude_order_id=order.id)
    if conflicting:
        raise ValueError(f"الطاولة {new_table.table_number} مشغولة بطلب آخر ({conflicting.order_number})")

    old_table_id = order.table_id
    order.table_id = table_id
    crud.update_table_status(db, new_table, "occupied")
    if old_table_id and old_table_id != table_id:
        old_table = crud.get_table(db, old_table_id)
        if old_table:
            crud.update_table_status(db, old_table, "available")

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "uq_active_order_per_table" in str(getattr(exc, "orig", exc)):
            raise ValueError("الطاولة المطلوبة مشغولة بطلب نشط بالفعل (سباق نقل مزدوج)") from exc
        raise
    db.refresh(order)
    return order


def transfer_order_waiter(
    db: Session, order_id: int, new_waiter_id: int, changed_by: int, reason: str,
) -> DiningOrder:
    """M5 (جولة مراجعة Codex الأولى — الـ brief §2.6 بند 3): تغيير النادل
    المسند لطلب مفتوح. بيقفل الطلب ويعيد فحص حالته، بيتحقق إن النادل الجديد
    موجود، بيغيّر waiter_id (assigned waiter) بس **بيسيب created_by زي ما هو**
    (تاريخ المنشئ الأصلي مايتمسحش)، وبيكتب AuditLog(action="transfer_waiter").
    الطلبات المقفولة (paid/cancelled/refunded) مايتنقلش نادلها."""
    from app.core.kernel.models.user import User  # noqa: PLC0415
    from app.modules.core import policy_engine  # noqa: PLC0415

    order = _lock_order_or_conflict(db, order_id)
    if order.status in ("paid", "cancelled", "refunded"):
        raise ValueError(f"لا يمكن تغيير نادل طلب بحالة '{order.status}'")

    new_waiter = db.query(User).filter(User.id == new_waiter_id).first()
    if not new_waiter or not new_waiter.is_active:
        raise ValueError("النادل الجديد غير موجود أو غير نشط")
    if order.waiter_id == new_waiter_id:
        raise ValueError("الطلب مسند بالفعل لهذا النادل")

    old_waiter_id = order.waiter_id
    order.waiter_id = new_waiter_id  # created_by ثابت — التاريخ محفوظ

    policy_engine.record_policy_audit(
        db, "transfer_waiter",
        user_id=changed_by, approved_by=None, branch_id=order.branch_id,
        entity_type="dining_order", entity_id=order.id,
        data={
            "old_waiter_id": old_waiter_id,
            "new_waiter_id": new_waiter_id,
            "created_by": order.created_by,
            "reason": reason,
        },
    )

    db.commit()
    db.refresh(order)
    return order


def claim_order_waiter(db: Session, order_id: int, user_id: int) -> DiningOrder:
    """تولّي نادل لطلب غير مسند لحد (بالذات طلبات QR اللي الضيف بيبعتها
    بنفسه — waiter_id=None من الأساس، مفيش حد مسؤول عن متابعتها). عكس
    transfer_order_waiter (مدير+، سبب إجباري، تدقيق كامل)، دي عملية ذاتية
    بسيطة للنادل نفسه — بس مسموحة بس لو الطلب فعلاً بلا نادل أو نادل بيتولى
    طلبه هو نفسه (idempotent)؛ سرقة طلب نادل تاني برّه النطاق، تمر عبر
    transfer_order_waiter بس (مدير+)."""
    order = _lock_order_or_conflict(db, order_id)
    if order.status in ("paid", "cancelled", "refunded"):
        raise ValueError(f"لا يمكن تولي طلب بحالة '{order.status}'")
    if order.waiter_id is not None and order.waiter_id != user_id:
        raise ValueError("الطلب مسند بالفعل لنادل آخر — راجع المدير لنقله")
    if order.waiter_id == user_id:
        return order

    order.waiter_id = user_id
    db.commit()
    db.refresh(order)
    return order


def merge_orders(db: Session, source_id: int, target_id: int, merged_by: int) -> DiningOrder:
    """Merge two live dine-in orders without corrupting totals or KDS ownership."""
    from app.modules.core import policy_engine  # noqa: PLC0415

    if source_id == target_id:
        raise ValueError("لا يمكن دمج أوردر مع نفسه")

    # Lock in deterministic order so reverse concurrent merges cannot deadlock.
    first_id, second_id = sorted((source_id, target_id))
    locked = {
        first_id: _lock_order_or_conflict(db, first_id),
        second_id: _lock_order_or_conflict(db, second_id),
    }
    source = locked[source_id]
    target = locked[target_id]

    if source.branch_id != target.branch_id:
        raise ValueError("الأوردران في فرعَين مختلفَين")
    if source.outlet_id != target.outlet_id:
        raise ValueError("لا يمكن دمج طلبين من منفذين مختلفين")
    if source.customer_id != target.customer_id:
        raise ValueError("لا يمكن دمج طلبين مرتبطين بعميلين مختلفين")
    if source.folio_id != target.folio_id:
        raise ValueError("لا يمكن دمج طلبين بارتباط فوليو مختلف")
    if source.applied_discount_rule_id != target.applied_discount_rule_id:
        raise ValueError("لا يمكن دمج طلبين عليهما قواعد خصم مختلفة")
    if source.guest_session_id != target.guest_session_id:
        raise ValueError(
            "لا يمكن دمج طلب ضيف QR مع طلب تابع لجلسة ضيف مختلفة"
        )

    active_statuses = {"held", "open", "in_kitchen", "served"}
    for order, label in ((source, "المصدر"), (target, "الهدف")):
        if order.status not in active_statuses:
            raise ValueError(f"لا يمكن دمج الطلب {label} بحالة '{order.status}'")
        if order.order_type != "dine_in" or not order.table_id:
            raise ValueError(f"الطلب {label} لازم يكون طلب صالة على طاولة")

    source_number = source.order_number
    source_total = source.total or Decimal("0")
    target_total = target.total or Decimal("0")
    moved_items = crud.reassign_order_items(db, source.id, target.id)
    moved_tickets = crud.reassign_kitchen_tickets(db, source.id, target.id)
    _recompute_order_totals(db, target)

    # الحالة المدمجة لا تدّعي served لو جزء من الطلب ما زال مفتوحًا/في المطبخ.
    # عند خلط open/held مع in_kitchen/served نرسل فقط الأصناف التي ليس لها
    # ticket، مع الحفاظ على التذاكر المنقولة وحالاتها كما هي.
    merged_statuses = {source.status, target.status}
    if merged_statuses == {"served"}:
        target.status = "served"
    elif merged_statuses & {"in_kitchen", "served"}:
        target.status = "in_kitchen"
        _ensure_kitchen_tickets_for_order(db, target)
    elif "open" in merged_statuses:
        target.status = "open"
    else:
        target.status = "held"

    if source.table_id:
        src_table = crud.get_table(db, source.table_id)
        if src_table:
            crud.update_table_status(db, src_table, "available")

    source.status = "cancelled"
    source.subtotal = Decimal("0")
    source.vat_amount = Decimal("0")
    source.service_charge = Decimal("0")
    source.delivery_fee = Decimal("0")
    source.discount_amount = Decimal("0")
    source.applied_discount_rule_id = None
    source.total = Decimal("0")

    source_note = f"مدموج في #{target.order_number} بواسطة user#{merged_by}"
    target_note = f"تم دمج الطلب #{source_number} في هذا الطلب"
    source.notes = f"{source.notes} | {source_note}" if source.notes else source_note
    target.notes = f"{target.notes} | {target_note}" if target.notes else target_note
    source.notes = source.notes[-500:]
    target.notes = target.notes[-500:]

    policy_engine.record_policy_audit(
        db, "merge_orders",
        user_id=merged_by, approved_by=None, branch_id=target.branch_id,
        entity_type="dining_order", entity_id=target.id,
        data={
            "source_order_id": source.id,
            "source_order_number": source_number,
            "moved_items_count": moved_items,
            "moved_tickets_count": moved_tickets,
            "source_total_before": str(source_total),
            "target_total_before": str(target_total),
            "target_total_after": str(target.total),
        },
    )

    db.commit()
    db.refresh(target)
    return target


def split_bill(
    db: Session,
    order_id: int,
    payments: list[dict],
    settled_by: Optional[int] = None,
    acting_user_level: int = 100,
    approver_user_id: Optional[int] = None,
    approver_pin: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> DiningOrder:
    """P-07 — تقسيم الفاتورة على أكثر من طريقة دفع (Gate 4A: بقى وحدة عمل
    صارمة كاملة عبر settle_order، مش مسار موازٍ). كل payment له amount +
    payment_method + charge_to_room_id (اختياري). المجموع لازم يساوي
    order.total بدقة Decimal. كل tender مباشر بيتعمله Payment منسوب للكاشير/
    الوردية، وكل tender غرفة بيتعمله شحنة فوليو متناسبة — الاتنين في نفس
    المعاملة الذرّية بتاعة settle_order مع idempotency guard."""
    tenders = [
        {
            "method": p["payment_method"],
            "amount": Decimal(str(p["amount"])),
            "charge_to_room_id": p.get("charge_to_room_id"),
            "credit_account_id": p.get("credit_account_id"),
            # POS-03: عملة/سعر الصرف للكاش بعملة أجنبية
            "currency": (p.get("currency") or "EGP").upper(),
            "fx_rate": p.get("fx_rate"),
            "payment_channel_id": p.get("payment_channel_id"),
        }
        for p in payments
    ]
    return settle_order(
        db, order_id, tenders=tenders, settled_by=settled_by,
        acting_user_level=acting_user_level,
        approver_user_id=approver_user_id, approver_pin=approver_pin,
        idempotency_key=idempotency_key,
    )


def bump_order_item_status(db: Session, order_id: int, item_id: int, new_status: str) -> DiningOrder:
    """يبدّل حالة صنف واحد داخل طلب دايننج (pending → in_kitchen → ready →
    served) — تأكيد صنف بصنف من شاشة الـ KDS، بدل الاضطرار لتأكيد التذكرة
    كلها. راجع restaurant.services.bump_order_item_status — نفس المنطق
    بالظبط. لما كل أصناف تذكرة معيّنة (محطة واحدة) تبقى ready/served/
    cancelled، التذكرة نفسها بتتحوّل لـ 'done' تلقائيًا."""
    order = _lock_order_or_conflict(db, order_id)
    if order.status not in ("held", "open", "in_kitchen", "served"):
        raise ValueError(f"لا يمكن تغيير حالة صنف في طلب بحالة '{order.status}'")

    item = crud.get_order_item(db, order_id, item_id)
    if not item:
        raise ValueError(f"الصنف {item_id} غير موجود في هذا الطلب")
    if item.status in ("cancelled", "refunded"):
        raise ValueError(f"لا يمكن تغيير حالة صنف {item.status}")

    crud.update_order_item_status(db, item, new_status)
    _sync_kitchen_tickets_for_order(db, order)

    db.commit()
    db.refresh(order)
    return order
