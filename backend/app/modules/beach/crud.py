"""app/modules/beach/crud.py — CRUD خالص"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.modules.beach.models import (
    B2BContract, B2BContractDay,
    BeachInventory, BeachLocation, BeachReservation, BeachTransaction,
)
from app.modules.beach.schemas import (
    B2BContractCreate, BeachReservationCreate,
)


# ── BeachInventory ────────────────────────────────────────────────────

def get_or_create_inventory(
    db: Session,
    branch_id: int,
    inv_date: date,
    capacity_max: int = 200,
    towels_total: int = 200,
) -> BeachInventory:
    row = (
        db.query(BeachInventory)
        .filter(BeachInventory.branch_id == branch_id, BeachInventory.inventory_date == inv_date)
        .first()
    )
    if not row:
        row = BeachInventory(
            branch_id=branch_id,
            inventory_date=inv_date,
            capacity_max=capacity_max,
            towels_total=towels_total,
            towels_available=towels_total,
        )
        db.add(row)
        db.flush()
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
        "b2b_revenue":   sum((r.total_amount for r in b2b_rows), Decimal("0")),
        "voided_count":  voided_count,
    }


# ── B2BContract ───────────────────────────────────────────────────────

def get_b2b_contract(db: Session, contract_id: int) -> Optional[B2BContract]:
    return db.query(B2BContract).filter(B2BContract.id == contract_id).first()


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
    db: Session, contract_id: int, day: date, count: int, amount: Decimal
) -> B2BContractDay:
    row = get_or_create_contract_day(db, contract_id, day)
    row.checked_in_count += count
    row.total_amount += amount
    db.flush()
    return row


def decrement_b2b_checkins(
    db: Session, contract_id: int, day: date, count: int, amount: Decimal
) -> Optional[B2BContractDay]:
    """يعكس increment_b2b_checkins — بيُستدعى عند إلغاء عملية تشيك-إن B2B
    (services.void_transaction). ⚠️ باج حقيقي كان هنا قبل التعديل الحالي:
    إلغاء عملية شاطئ B2B كان بيعكس الـ inventory والقيد المحاسبي، بس مايلمسش
    B2BContractDay.checked_in_count/total_amount خالص — يعني الرصيد المستحق
    على الفندق الشريك (المستخدم دلوقتي في حساب حد الائتمان والتأخر) كان
    هيفضل متضخّم للأبد حتى بعد الإلغاء الفعلي."""
    row = (
        db.query(B2BContractDay)
        .filter(B2BContractDay.contract_id == contract_id, B2BContractDay.day == day)
        .first()
    )
    if not row:
        return None
    row.checked_in_count = max(0, row.checked_in_count - count)
    row.total_amount = max(Decimal("0"), row.total_amount - amount)
    db.flush()
    return row


# ── B2B credit / dunning ──────────────────────────────────────────────

def get_b2b_outstanding_balance(
    db: Session, contract_id: int, since: Optional[date] = None
) -> Decimal:
    """مجموع B2BContractDay.total_amount لكل الأيام بعد آخر تسوية
    (``since`` = contract.last_settled_at) — الرصيد المستحق الحالي على
    الفندق الشريك. ``since=None`` يعني لسه مفيش تسوية من بداية العقد، فكل
    الأيام المسجّلة تدخل في الحساب."""
    q = db.query(B2BContractDay).filter(B2BContractDay.contract_id == contract_id)
    if since:
        q = q.filter(B2BContractDay.day > since)
    return sum((row.total_amount for row in q.all()), Decimal("0"))


def get_b2b_oldest_unsettled_day(
    db: Session, contract_id: int, since: Optional[date] = None
) -> Optional[date]:
    """أقدم يوم فيه رصيد غير مسوّى (total_amount > 0) بعد آخر تسوية — يُستخدم
    لحساب هل العقد تخطّى مهلة السداد (payment_terms_days) ولا لأ."""
    q = (
        db.query(B2BContractDay)
        .filter(B2BContractDay.contract_id == contract_id, B2BContractDay.total_amount > 0)
    )
    if since:
        q = q.filter(B2BContractDay.day > since)
    row = q.order_by(B2BContractDay.day.asc()).first()
    return row.day if row else None


def settle_b2b_contract(db: Session, contract: B2BContract, settled_through: date) -> B2BContract:
    """يسجّل إن رصيد العقد اتسوّى (اتحصّل) بالكامل لحد تاريخ ``settled_through``
    — بيصفّر الرصيد المستحق فعليًا (كل الأيام لحد كده هتتجاهل في الحسابات
    الجاية) وبيلغي أي علم تأخر سابق."""
    contract.last_settled_at = settled_through
    contract.is_overdue = False
    contract.notified_overdue = False
    db.flush()
    return contract


def list_active_b2b_contracts_for_overdue_check(db: Session) -> list[B2BContract]:
    """كل عقود B2B النشطة عبر كل الفروع — يُستخدم في مهمة Celery الدورية
    (نفس نمط timeshare_tasks._mark_overdue اللي بيمشي على كل العقود
    النشطة من غير فلترة فرع، لأنها مهمة خلفية شاملة مش endpoint لفرع معين)."""
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
