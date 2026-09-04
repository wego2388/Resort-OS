"""app/modules/beach/crud.py — CRUD خالص"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.beach.models import (
    B2BContract, B2BContractDay, B2BContractMonth,
    BeachInventory, BeachLocation, BeachReservation, BeachTransaction,
)
from app.modules.beach.schemas import (
    B2BContractCreate, BeachReservationCreate,
)


# ── BeachInventory ────────────────────────────────────────────────────

def get_inventory(db: Session, branch_id: int, inv_date: date) -> Optional[BeachInventory]:
    return (
        db.query(BeachInventory)
        .filter(
            BeachInventory.branch_id == branch_id,
            BeachInventory.inventory_date == inv_date,
        )
        .first()
    )


def get_or_create_inventory(
    db: Session,
    branch_id: int,
    inv_date: date,
    capacity_max: int = 200,
    towels_total: int = 200,
) -> BeachInventory:
    """⚠️ باج حقيقي اتصلح هنا: check-then-insert بسيط من غير أي حماية —
    أول بيعتين في نفس اليوم بالظبط (زي الساعة 6 الصبح لما أول كاشير يفتح
    الشاشة) ممكن الاتنين يقروا row=None في نفس اللحظة، فيحاولوا يعملوا
    INSERT مرتين لنفس (branch_id, inventory_date) — الصف الأول ينجح، التاني
    كان بيرمي IntegrityError خام (500 غير متوقع) بدل ما يتعامل مع السباق
    ويرجّع نفس صف اليوم اللي اتعمل بالفعل. الحل: SAVEPOINT (begin_nested)
    حوالين الـINSERT بس — لو اتصادم، بنرجّع للـSAVEPOINT فقط (مش
    db.rollback() الكامل، اللي كان هيمسح أي تعديلات تانية غير ملتزمة لسه
    في نفس الـtransaction الأكبر، زي أصناف سابقة في سلة atomic)."""
    row = get_inventory(db, branch_id, inv_date)
    if row:
        return row
    row = BeachInventory(
        branch_id=branch_id,
        inventory_date=inv_date,
        capacity_max=capacity_max,
        towels_total=towels_total,
        towels_available=towels_total,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        row = get_inventory(db, branch_id, inv_date)
        if row is None:
            raise
    return row


def lock_inventory_for_update(db: Session, inventory_id: int) -> Optional[BeachInventory]:
    """SELECT ... FOR UPDATE NOWAIT — يقفل صف الـ inventory اليومي طوال الـ
    transaction عشان يمنع تجاوز السعة/الفوط (double-sell) لو عمليتين بيع/
    تشيك-إن حصلوا في نفس اللحظة بالظبط على نفس الفرع/اليوم. نفس نمط
    pms.crud.lock_room_for_booking (Postgres فقط — على SQLite بيتجاهله الـ
    driver من غير error).

    ⚠️ باج حقيقي كان هنا (اتكشف بتجربة حية حقيقية على Postgres فعلي بعمليتين
    متزامنتين — مش تست، لأن تستات الوحدة شغالة على SQLite واللي بيتجاهل
    with_for_update أصلاً): `sell_ticket`/`b2b_checkin` بيعملوا قراءة أولى
    غير مقفولة (`get_or_create_inventory`) قبل القفل، فالصف بيتسجّل في
    identity map الخاصة بالـ Session بالقيم القديمة. لما القفل نفسه يتاخد
    بعد كده (`with_for_update`)، SQLAlchemy مكنش بيحدّث قيم الـ object
    الموجود بالفعل في الـ identity map من نتيجة الاستعلام الجديدة — فالكود
    كان بيكمل بقيمة capacity_used/checked_in_count **قديمة** حتى لو معاملة
    تانية (session تانية) كانت خلصت وعدّلت الصف فعليًا في نفس اللحظة قبل
    القفل ده. النتيجة الفعلية اللي لوحظت: عمليتا بيع ناجحتين (201 لكل واحدة،
    تذكرتين حقيقيتين اتسجّلوا) بس `capacity_used` اتزاد مرة واحدة بس — يعني
    lost update حقيقي (سعة الشاطئ بتفضل أقل من العدد الحقيقي اللي دخل فعلاً،
    ممكن يوصل لتجاوز السعة الفعلية من غير ما النظام يلاحظ). الحل:
    `.populate_existing()` يجبر SQLAlchemy يحدّث الـ object من نتيجة
    الـ SELECT FOR UPDATE نفسها، مش يسيبه على القيمة القديمة المخزّنة."""
    return (
        db.query(BeachInventory)
        .filter(BeachInventory.id == inventory_id)
        .populate_existing()
        .with_for_update(nowait=True)
        .first()
    )


def set_surge_manual(
    db: Session,
    branch_id: int,
    inv_date: date,
    surge_pct: Decimal,
) -> BeachInventory:
    """يضبط surge_pct يدوياً (0 = إيقاف)."""
    row = get_or_create_inventory(db, branch_id, inv_date)
    row.surge_pct = surge_pct
    db.flush()
    return row


def apply_inventory_delta(
    db: Session,
    inventory: BeachInventory,
    capacity_delta: int,
    towel_delta: int,
) -> BeachInventory:
    # سالب delta = إضافة (شخص يدخل) — مطابق لنمط الفوط
    inventory.capacity_used    = max(0, inventory.capacity_used    - capacity_delta)
    inventory.towels_used      = max(0, inventory.towels_used      - towel_delta)
    inventory.towels_available = max(0, inventory.towels_available + towel_delta)

    # surge تلقائي عند capacity > 80%
    if inventory.capacity_max > 0:
        pct = inventory.capacity_used / inventory.capacity_max * 100
        inventory.surge_pct = Decimal("50.0") if pct >= 80 else Decimal("0.0")

    db.flush()
    return inventory


# ── BeachTransaction ──────────────────────────────────────────────────

def create_transaction(db: Session, data: dict) -> BeachTransaction:
    tx = BeachTransaction(**data)
    db.add(tx)
    db.flush()
    return tx


def get_transaction(db: Session, tx_id: int) -> Optional[BeachTransaction]:
    return db.query(BeachTransaction).filter(BeachTransaction.id == tx_id).first()


def get_transaction_by_local_id(db: Session, local_id: str) -> Optional[BeachTransaction]:
    return db.query(BeachTransaction).filter(BeachTransaction.client_local_id == local_id).first()


def get_transactions_by_cart_local_id(db: Session, cart_local_id: str) -> list[BeachTransaction]:
    """كل تذاكر سلة atomic اتسجّلت بمفتاح idempotency السلة ده — كل صنف بيتخزّن
    بـclient_local_id = f"{cart_local_id}:{index}" (راجع services.sell_cart).
    إما الكل موجود (السلة اتسجّلت بنجاح) أو ولا واحد (rollback كامل)."""
    return (
        db.query(BeachTransaction)
        .filter(BeachTransaction.client_local_id.like(f"{cart_local_id}:%"))
        .order_by(BeachTransaction.id)
        .all()
    )


def void_transaction(db: Session, tx: BeachTransaction, voided_by: int, reason: str) -> BeachTransaction:
    tx.voided_at = datetime.utcnow()
    tx.voided_by = voided_by
    tx.voided_reason = reason
    db.flush()
    return tx


def list_transactions(
    db: Session,
    branch_id: int,
    tx_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 100,
) -> tuple[list[BeachTransaction], int]:
    q = db.query(BeachTransaction).filter(
        BeachTransaction.branch_id == branch_id,
        BeachTransaction.voided_at.is_(None),
    )
    if tx_date:
        q = q.filter(BeachTransaction.tx_date == tx_date)
    total = q.count()
    items = q.order_by(BeachTransaction.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def get_daily_summary(db: Session, branch_id: int, tx_date: date) -> dict:
    rows = (
        db.query(BeachTransaction)
        .filter(
            BeachTransaction.branch_id == branch_id,
            BeachTransaction.tx_date == tx_date,
            BeachTransaction.voided_at.is_(None),
        )
        .all()
    )
    entries       = sum(r.quantity for r in rows if r.tx_type in ("entry", "entry_towel"))
    b2b_entries   = sum(r.quantity for r in rows if r.b2b_contract_id and r.tx_type in ("entry", "entry_towel"))
    total_revenue = sum(r.total_amount for r in rows if r.tx_type != "towel_return")
    b2b_revenue   = sum(r.total_amount for r in rows if r.b2b_contract_id)
    towels_rented = sum(r.quantity for r in rows if r.tx_type in ("entry_towel", "towel_rent"))
    surge_active  = any(r.surge_applied for r in rows)
    return {
        "date":          tx_date,
        "total_entries": entries,
        "total_revenue": total_revenue,
        "b2b_entries":   b2b_entries,
        "b2b_revenue":   b2b_revenue,
        "towels_rented": towels_rented,
        "surge_active":  surge_active,
    }


def get_eod_breakdown(db: Session, branch_id: int, tx_date: date) -> dict:
    """تفصيل يوم كامل حسب نوع العملية — للتقرير اليومي (End of Day)."""
    rows = (
        db.query(BeachTransaction)
        .filter(
            BeachTransaction.branch_id == branch_id,
            BeachTransaction.tx_date == tx_date,
            BeachTransaction.voided_at.is_(None),
        )
        .all()
    )
    voided_count = (
        db.query(BeachTransaction)
        .filter(
            BeachTransaction.branch_id == branch_id,
            BeachTransaction.tx_date == tx_date,
            BeachTransaction.voided_at.isnot(None),
        )
        .count()
    )

    by_type: dict[str, dict] = {}
    for r in rows:
        d = by_type.setdefault(r.tx_type, {"quantity": 0, "total_amount": Decimal("0"), "count": 0})
        d["quantity"] += r.quantity
        d["total_amount"] += r.total_amount
        d["count"] += 1

    b2b_rows = [r for r in rows if r.b2b_contract_id]
    entry_types = ("entry", "entry_child", "entry_resident", "entry_towel")

    return {
        "by_type":       by_type,
        "total_entries": sum(r.quantity for r in rows if r.tx_type in entry_types),
        "total_revenue": sum((r.total_amount for r in rows if r.tx_type != "towel_return"), Decimal("0")),
        "b2b_entries":   sum(r.quantity for r in b2b_rows if r.tx_type in entry_types),
        # 2026-08-20: دايمًا 0 دلوقتي — عقود B2B بقت بمبلغ شهري ثابت
        # (راجع models.B2BContract)، مفيش قيمة مالية لكل تشيك-إن. الإيراد
        # الحقيقي بيترحّل شهريًا (services.post_b2b_monthly_fees)، مش هنا.
        "b2b_revenue":   sum((r.total_amount for r in b2b_rows), Decimal("0")),
        "voided_count":  voided_count,
    }


# ── B2BContract ───────────────────────────────────────────────────────

def get_b2b_contract(db: Session, contract_id: int) -> Optional[B2BContract]:
    return db.query(B2BContract).filter(B2BContract.id == contract_id).first()


def lock_b2b_contract_for_update(db: Session, contract_id: int) -> Optional[B2BContract]:
    """SELECT ... FOR UPDATE NOWAIT — يقفل صف العقد طوال التسوية (مراجعة
    Codex 2026-08-30، H-04) عشان يمنع تسويتين متزامنتين لنفس العقد (double
    settlement: القيدين اتنين بيترحّلوا، وآخر تحديث لـ`last_settled_at`
    بيكسب بصمت). نفس نمط lock_contract_day_for_update/
    lock_inventory_for_update بالظبط، بما فيها `.populate_existing()`
    لنفس السبب (قراءة سابقة غير مقفولة قبل القفل ممكن تسيب قيمة قديمة في
    identity map الـ Session)."""
    return (
        db.query(B2BContract)
        .filter(B2BContract.id == contract_id)
        .populate_existing()
        .with_for_update(nowait=True)
        .first()
    )


def list_b2b_contracts(
    db: Session, branch_id: int, active_only: bool = True
) -> list[B2BContract]:
    q = db.query(B2BContract).filter(B2BContract.branch_id == branch_id)
    if active_only:
        q = q.filter(B2BContract.is_active.is_(True))
    return q.order_by(B2BContract.hotel_name).all()


def create_b2b_contract(db: Session, data: B2BContractCreate) -> B2BContract:
    obj = B2BContract(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


def update_b2b_contract_credit(
    db: Session, contract: B2BContract,
    credit_limit: Optional[Decimal] = None, payment_terms_days: Optional[int] = None,
    credit_limit_set: bool = False,
) -> B2BContract:
    """تعديل إعدادات الائتمان فقط (حد الائتمان/مهلة السداد) — مش كل حقول
    العقد، عشان الأسعار/الحصة اليومية تفضل ليها مسار تعديل منفصل لو
    احتجناه لاحقًا. ``credit_limit_set`` يميّز "المستخدم بعت credit_limit=None
    صراحةً (إلغاء الحد)" عن "المستخدم ما بعتش الحقل خالص"."""
    if credit_limit_set:
        contract.credit_limit = credit_limit
    if payment_terms_days is not None:
        contract.payment_terms_days = payment_terms_days
    db.flush()
    return contract


def list_b2b_contracts_with_today_usage(
    db: Session, branch_id: int, day: date,
) -> list[tuple[B2BContract, int]]:
    """كل عقود B2B النشطة مع عدد اللي دخلوا اليوم — بدون إنشاء أي صف
    (read-only، عكس get_or_create_contract_day)."""
    contracts = list_b2b_contracts(db, branch_id, active_only=True)
    rows: list[tuple[B2BContract, int]] = []
    for c in contracts:
        day_row = (
            db.query(B2BContractDay)
            .filter(B2BContractDay.contract_id == c.id, B2BContractDay.day == day)
            .first()
        )
        rows.append((c, day_row.checked_in_count if day_row else 0))
    return rows


def get_or_create_contract_day(
    db: Session, contract_id: int, day: date
) -> B2BContractDay:
    row = (
        db.query(B2BContractDay)
        .filter(B2BContractDay.contract_id == contract_id, B2BContractDay.day == day)
        .first()
    )
    if not row:
        row = B2BContractDay(contract_id=contract_id, day=day)
        db.add(row)
        db.flush()
    return row


def lock_contract_day_for_update(db: Session, row_id: int) -> Optional[B2BContractDay]:
    """SELECT ... FOR UPDATE NOWAIT — يقفل صف B2BContractDay طوال الـ
    transaction عشان يمنع تجاوز حصة B2B اليومية (double check-in) لو عمليتين
    تشيك-إن حصلوا في نفس اللحظة بالظبط لنفس العقد/اليوم. نفس نمط
    lock_inventory_for_update فوق و pms.crud.lock_room_for_booking (Postgres
    فقط — على SQLite بيتجاهله الـ driver من غير error).

    `.populate_existing()` هنا لنفس سبب lock_inventory_for_update بالظبط —
    `get_or_create_contract_day` بيعمل قراءة أولى غير مقفولة قبل القفل، ومن
    غيرها كان ممكن يفضل checked_in_count قديم في identity map الـ Session
    حتى بعد القفل الناجح، لو معاملة تشيك-إن تانية خلصت وعدّلت الصف فعليًا
    قبل القفل ده مباشرة."""
    return (
        db.query(B2BContractDay)
        .filter(B2BContractDay.id == row_id)
        .populate_existing()
        .with_for_update(nowait=True)
        .first()
    )


def increment_b2b_checkins(
    db: Session, contract_id: int, day: date, count: int,
) -> B2BContractDay:
    """2026-08-20: عدّاد هيدكاونت بحت دلوقتي — مفيش مبلغ لكل تشيك-إن في
    نموذج المبلغ الشهري الثابت (راجع models.B2BContract)."""
    row = get_or_create_contract_day(db, contract_id, day)
    row.checked_in_count += count
    db.flush()
    return row


def decrement_b2b_checkins(
    db: Session, contract_id: int, day: date, count: int,
) -> Optional[B2BContractDay]:
    """يعكس increment_b2b_checkins — بيُستدعى عند إلغاء عملية تشيك-إن B2B
    (services.void_transaction)."""
    row = (
        db.query(B2BContractDay)
        .filter(B2BContractDay.contract_id == contract_id, B2BContractDay.day == day)
        .first()
    )
    if not row:
        return None
    row.checked_in_count = max(0, row.checked_in_count - count)
    db.flush()
    return row


def get_b2b_checked_in_count_for_month(
    db: Session, contract_id: int, month_start: date, month_end: date,
) -> int:
    """إجمالي عدد الضيوف اللي دخلوا خلال شهر معيّن (بما فيهم كل الأيام من
    ``month_start`` لحد ``month_end``) — يُستخدم لتحذير اقتراب الحد الشهري
    (services.b2b_checkin) ولقطة guests_count وقت الترحيل الشهري
    (services.post_b2b_monthly_fees)."""
    from sqlalchemy import func as sa_func  # noqa: PLC0415

    total = (
        db.query(sa_func.coalesce(sa_func.sum(B2BContractDay.checked_in_count), 0))
        .filter(
            B2BContractDay.contract_id == contract_id,
            B2BContractDay.day >= month_start,
            B2BContractDay.day <= month_end,
        )
        .scalar()
    )
    return int(total or 0)


# ── B2BContractMonth (ترحيل الرسم الشهري الثابت) ───────────────────────

def get_b2b_contract_month(
    db: Session, contract_id: int, period_month: date,
) -> Optional[B2BContractMonth]:
    return (
        db.query(B2BContractMonth)
        .filter(
            B2BContractMonth.contract_id == contract_id,
            B2BContractMonth.period_month == period_month,
        )
        .first()
    )


def create_b2b_contract_month(
    db: Session, contract_id: int, period_month: date,
    guests_count: int, amount: Decimal, journal_entry_id: int,
) -> B2BContractMonth:
    """إنشاء صف ترحيل شهري — idempotent فعليًا بـ UniqueConstraint
    (contract_id, period_month) على مستوى الداتابيز؛ راجع
    services.post_b2b_monthly_fees للتحقق قبل الاستدعاء (get_b2b_contract_month)."""
    row = B2BContractMonth(
        contract_id=contract_id, period_month=period_month,
        guests_count=guests_count, amount=amount, journal_entry_id=journal_entry_id,
        billed_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    return row


# ── B2B credit / dunning ──────────────────────────────────────────────

def get_b2b_outstanding_balance(
    db: Session, contract_id: int, since: Optional[date] = None, through: Optional[date] = None,
) -> Decimal:
    """مجموع B2BContractMonth.amount لكل شهر اتُرحّل بعد آخر تسوية
    (``since`` = contract.last_settled_at) — الرصيد المستحق الحالي على
    الفندق الشريك. ``since=None`` يعني لسه مفيش تسوية من بداية العقد، فكل
    الشهور المُرحَّلة تدخل في الحساب.

    ``through`` (مراجعة Codex 2026-08-30، H-04): كان غايب تمامًا قبل كده —
    يعني تسوية جزئية/بتاريخ سابق (settled_through أقدم من النهاردة) كانت
    بتجمع كل الشهور المُرحَّلة **حتى المستقبلية** بدل ما تقف عند التاريخ
    المطلوب فعليًا، فتحصيل شهر واحد كان ممكن "يبلع" شهور تالية معاه بالغلط."""
    q = db.query(B2BContractMonth).filter(B2BContractMonth.contract_id == contract_id)
    if since:
        q = q.filter(B2BContractMonth.period_month > since)
    if through:
        q = q.filter(B2BContractMonth.period_month <= through)
    return sum((row.amount for row in q.all()), Decimal("0"))


def get_b2b_oldest_unsettled_month(
    db: Session, contract_id: int, since: Optional[date] = None
) -> Optional[date]:
    """أقدم شهر مُرحَّل ولسه مش متسوّى بعد آخر تسوية — يُستخدم لحساب هل
    العقد تخطّى مهلة السداد (payment_terms_days) ولا لأ."""
    q = db.query(B2BContractMonth).filter(B2BContractMonth.contract_id == contract_id)
    if since:
        q = q.filter(B2BContractMonth.period_month > since)
    row = q.order_by(B2BContractMonth.period_month.asc()).first()
    return row.period_month if row else None


def settle_b2b_contract(db: Session, contract: B2BContract, settled_through: date) -> B2BContract:
    """يسجّل إن رصيد العقد اتسوّى (اتحصّل) بالكامل لحد تاريخ ``settled_through``
    — بيصفّر الرصيد المستحق فعليًا (كل الشهور المُرحَّلة لحد كده هتتجاهل في
    الحسابات الجاية) وبيلغي أي علم تأخر سابق. القيد المحاسبي العكسي
    (Dr. حساب التحصيل / Cr. 1165) بيترحّل في services.settle_b2b_contract
    قبل ما ينادي هنا، مش هنا — دي طبقة تخزين بحتة."""
    contract.last_settled_at = settled_through
    contract.is_overdue = False
    contract.notified_overdue = False
    db.flush()
    return contract


def list_active_b2b_contracts(db: Session) -> list[B2BContract]:
    """كل عقود B2B النشطة عبر كل الفروع — يُستخدم في مهمتي Celery الدوريتين
    (تأخر السداد + الترحيل الشهري، نفس نمط timeshare_tasks._mark_overdue
    اللي بيمشي على كل العقود النشطة من غير فلترة فرع، لأنها مهام خلفية
    شاملة مش endpoint لفرع معين)."""
    return db.query(B2BContract).filter(B2BContract.is_active.is_(True)).all()


# ── BeachReservation ──────────────────────────────────────────────────

def get_reservation(db: Session, reservation_id: int) -> Optional[BeachReservation]:
    return db.query(BeachReservation).filter(BeachReservation.id == reservation_id).first()


def create_reservation(db: Session, data: BeachReservationCreate) -> BeachReservation:
    obj = BeachReservation(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


def list_reservations(
    db: Session,
    branch_id: int,
    res_date: Optional[date] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[BeachReservation], int]:
    q = db.query(BeachReservation).filter(BeachReservation.branch_id == branch_id)
    if res_date:
        q = q.filter(BeachReservation.reservation_date == res_date)
    if status:
        q = q.filter(BeachReservation.status == status)
    total = q.count()
    items = q.order_by(BeachReservation.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def update_reservation_status(
    db: Session, res: BeachReservation, status: str, tx_id: Optional[int] = None
) -> BeachReservation:
    res.status = status
    if tx_id:
        res.tx_id = tx_id
    db.flush()
    return res


# ── BeachLocation (live map) ───────────────────────────────────────────

def get_location(db: Session, location_id: int) -> Optional[BeachLocation]:
    return db.query(BeachLocation).filter(BeachLocation.id == location_id).first()


def list_locations(
    db: Session, branch_id: int, location_type: Optional[str] = None
) -> list[BeachLocation]:
    q = db.query(BeachLocation).filter(BeachLocation.branch_id == branch_id)
    if location_type:
        q = q.filter(BeachLocation.location_type == location_type)
    return q.order_by(BeachLocation.location_type, BeachLocation.grid_row, BeachLocation.grid_col).all()


def get_max_location_number(db: Session, branch_id: int, location_type: str) -> int:
    """أعلى رقم موجود فعليًا لنوع مواقع معيّن — الأرقام مخزّنة كنص (بعض
    المنتجعات بترقّم بحروف/بادئات زي "VIP-1")، فبنلقط الأرقام الصحيحة الخالصة
    بس ونتجاهل أي رقم غير قياسي عند حساب "التالي تلقائيًا"."""
    numbers = (
        db.query(BeachLocation.number)
        .filter(BeachLocation.branch_id == branch_id, BeachLocation.location_type == location_type)
        .all()
    )
    numeric = [int(n) for (n,) in numbers if n.isdigit()]
    return max(numeric) if numeric else 0


def bulk_create_locations(
    db: Session, branch_id: int, location_type: str, count: int, start_number: int,
    per_row: int = 10,
) -> list[BeachLocation]:
    created: list[BeachLocation] = []
    for i in range(count):
        n = start_number + i
        loc = BeachLocation(
            branch_id=branch_id, location_type=location_type, number=str(n),
            grid_row=(n - 1) // per_row + 1, grid_col=(n - 1) % per_row + 1,
            status="available",
        )
        db.add(loc)
        created.append(loc)
    db.flush()
    return created


def get_removable_locations(
    db: Session, branch_id: int, location_type: str, count: int
) -> list[BeachLocation]:
    """آخر N مواقع *متاحة* من نوع معيّن (الأحدث أولاً) — مواقع مشغولة
    (status != available) مش مرشّحة للحذف خالص."""
    return (
        db.query(BeachLocation)
        .filter(
            BeachLocation.branch_id == branch_id,
            BeachLocation.location_type == location_type,
            BeachLocation.status == "available",
        )
        .order_by(BeachLocation.id.desc())
        .limit(count)
        .all()
    )


def delete_locations(db: Session, locations: list[BeachLocation]) -> None:
    for loc in locations:
        db.delete(loc)
    db.flush()


def lock_location_for_update(db: Session, location_id: int) -> Optional[BeachLocation]:
    """SELECT ... FOR UPDATE NOWAIT — يقفل صف الموقع نفسه طوال الـ transaction
    عشان يمنع double check-in (كاشيرين مختلفين بيسجّلوا دخول نفس الموقع في
    نفس اللحظة بالظبط). نفس نمط lock_inventory_for_update/lock_room_for_booking
    بالظبط — Postgres فقط، SQLite بيتجاهله من غير error.

    `.populate_existing()` لنفس سبب lock_inventory_for_update: من غيرها
    SQLAlchemy مش هيحدّث الـ object الموجود بالفعل في identity map الجلسة
    من نتيجة القفل — يعني لو معاملة تانية خلصت وغيّرت status الموقع فعليًا
    قبل القفل ده بلحظة، الكود كان هيكمل بقيمة status قديمة (lost update)."""
    return (
        db.query(BeachLocation)
        .filter(BeachLocation.id == location_id)
        .populate_existing()
        .with_for_update(nowait=True)
        .first()
    )
