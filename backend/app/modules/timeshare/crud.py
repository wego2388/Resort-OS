"""app/modules/timeshare/crud.py"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.timeshare.models import (
    TimeshareContract, TimeshareInstallment, TimeshareUnit, TimeshareVisit, TimeshareWaitlist,
)
from app.modules.timeshare.schemas import (
    TimeshareContractCreate, TimeshareContractUpdate,
    PayInstallmentRequest, TimeshareVisitCreate, TimeshareVisitUpdate, WaitlistCreate,
)


def _next_contract_number(db: Session) -> str:
    today = datetime.utcnow().strftime("%Y%m%d")
    count = db.query(TimeshareContract).filter(
        TimeshareContract.contract_number.like(f"TS-{today}-%")
    ).count()
    return f"TS-{today}-{count + 1:04d}"


def get_contract(db: Session, contract_id: int) -> Optional[TimeshareContract]:
    return db.query(TimeshareContract).filter(TimeshareContract.id == contract_id).first()


def get_contract_by_form_number(db: Session, branch_id: int, form_number: str) -> Optional[TimeshareContract]:
    return db.query(TimeshareContract).filter(
        TimeshareContract.branch_id == branch_id,
        TimeshareContract.form_number == form_number,
    ).first()


def list_contracts(
    db: Session, branch_id: int,
    status: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0, limit: int = 50,
) -> tuple[list[TimeshareContract], int]:
    q = db.query(TimeshareContract).filter(TimeshareContract.branch_id == branch_id)
    if status:
        q = q.filter(TimeshareContract.status == status)
    if search:
        like = f"%{search}%"
        q = q.filter(
            TimeshareContract.customer_name.ilike(like) |
            TimeshareContract.customer_phone.ilike(like) |
            TimeshareContract.contract_number.ilike(like)
        )
    total = q.count()
    items = q.order_by(TimeshareContract.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def create_contract(db: Session, data: TimeshareContractCreate, signed_by: int) -> TimeshareContract:
    contract = TimeshareContract(
        **data.model_dump(),
        contract_number=_next_contract_number(db),
        signed_by=signed_by,
    )
    db.add(contract)
    db.flush()
    return contract


def update_contract(db: Session, contract: TimeshareContract, data: TimeshareContractUpdate) -> TimeshareContract:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(contract, field, value)
    db.flush()
    return contract


def create_installments(db: Session, contract_id: int, schedule: list[dict]) -> list[TimeshareInstallment]:
    objs = []
    for item in schedule:
        inst = TimeshareInstallment(
            contract_id=contract_id,
            installment_no=item["installment_no"],
            due_date=item["due_date"],
            amount=item["amount"],
        )
        db.add(inst)
        objs.append(inst)
    db.flush()
    return objs


def get_installment(db: Session, inst_id: int) -> Optional[TimeshareInstallment]:
    return db.query(TimeshareInstallment).filter(TimeshareInstallment.id == inst_id).first()


def pay_installment(db: Session, inst: TimeshareInstallment, req: PayInstallmentRequest) -> TimeshareInstallment:
    inst.paid_amount += req.paid_amount
    inst.payment_method = req.payment_method
    inst.receipt_number = req.receipt_number
    inst.notes = req.notes
    if inst.paid_amount >= inst.amount:
        inst.status = "paid"
        inst.paid_at = datetime.utcnow()
    else:
        inst.status = "partial"
    db.flush()
    return inst


# ── CS Dashboard aggregates ──────────────────────────────────────────

def list_active_contracts_with_aggregates(db: Session, branch_id: int) -> list:
    """كل عقد نشط مع collected/overdue/pending_count/next_due — لـ CS Dashboard."""
    from sqlalchemy import case, func  # noqa: PLC0415

    return (
        db.query(
            TimeshareContract,
            func.coalesce(func.sum(case(
                (TimeshareInstallment.status == "paid", TimeshareInstallment.paid_amount), else_=0,
            )), 0).label("collected"),
            func.coalesce(func.sum(case(
                (TimeshareInstallment.status == "overdue", TimeshareInstallment.amount), else_=0,
            )), 0).label("overdue_amount"),
            func.count(case(
                (TimeshareInstallment.status.in_(["pending", "overdue"]), TimeshareInstallment.id),
            )).label("pending_count"),
            func.min(case(
                (TimeshareInstallment.status.in_(["pending", "overdue"]), TimeshareInstallment.due_date),
            )).label("next_due"),
        )
        .outerjoin(TimeshareInstallment, TimeshareInstallment.contract_id == TimeshareContract.id)
        .filter(TimeshareContract.branch_id == branch_id, TimeshareContract.status == "active")
        .group_by(TimeshareContract.id)
        .order_by(TimeshareContract.customer_name)
        .all()
    )


def count_contracts_by_status(db: Session, branch_id: int) -> dict[str, int]:
    """عدد العقود حسب الحالة — لعرض الـ pipeline (draft → active) في لوحة المبيعات."""
    from sqlalchemy import func  # noqa: PLC0415

    rows = (
        db.query(TimeshareContract.status, func.count(TimeshareContract.id))
        .filter(TimeshareContract.branch_id == branch_id)
        .group_by(TimeshareContract.status)
        .all()
    )
    return {status: count for status, count in rows}


def get_this_month_due(db: Session, branch_id: int, today: date) -> Decimal:
    from sqlalchemy import extract, func  # noqa: PLC0415

    total = (
        db.query(func.coalesce(func.sum(TimeshareInstallment.amount), 0))
        .join(TimeshareContract, TimeshareContract.id == TimeshareInstallment.contract_id)
        .filter(
            TimeshareContract.branch_id == branch_id,
            TimeshareInstallment.status.in_(["pending", "overdue"]),
            extract("year", TimeshareInstallment.due_date) == today.year,
            extract("month", TimeshareInstallment.due_date) == today.month,
        )
        .scalar()
    )
    return total or Decimal("0")


def list_contracts_with_week(db: Session, branch_id: int) -> list[TimeshareContract]:
    """عقود نشطة/موقوفة بأسبوع ثابت — للكالندر والزيارات القادمة."""
    return (
        db.query(TimeshareContract)
        .filter(
            TimeshareContract.branch_id == branch_id,
            TimeshareContract.status.in_(["active", "suspended"]),
            TimeshareContract.week_number.isnot(None),
        )
        .order_by(TimeshareContract.week_number)
        .all()
    )


def list_all_installments(
    db: Session, branch_id: int,
    status: Optional[str] = None,
    contract_id: Optional[int] = None,
    month: Optional[str] = None,   # "YYYY-MM"
    search: Optional[str] = None,
    limit: int = 200,
) -> list[TimeshareInstallment]:
    from sqlalchemy import extract  # noqa: PLC0415
    from sqlalchemy.orm import contains_eager  # noqa: PLC0415

    q = (
        db.query(TimeshareInstallment)
        .join(TimeshareContract, TimeshareContract.id == TimeshareInstallment.contract_id)
        # contains_eager: نعيد استخدام الـ join الموجود لتحميل العقد بدون N+1
        # (جدول الأقساط في الفرونت بيعرض اسم/هاتف/نوع غرفة العميل لكل قسط)
        .options(contains_eager(TimeshareInstallment.contract))
        .filter(TimeshareContract.branch_id == branch_id)
    )
    if status:
        q = q.filter(TimeshareInstallment.status == status)
    if contract_id:
        q = q.filter(TimeshareInstallment.contract_id == contract_id)
    if month:
        year_s, month_s = month.split("-")
        q = q.filter(
            extract("year", TimeshareInstallment.due_date) == int(year_s),
            extract("month", TimeshareInstallment.due_date) == int(month_s),
        )
    if search:
        q = q.filter(TimeshareContract.customer_name.ilike(f"%{search}%"))
    return q.order_by(TimeshareInstallment.due_date.desc()).limit(limit).all()


def installments_summary(db: Session, branch_id: int) -> dict:
    from sqlalchemy import func  # noqa: PLC0415

    overdue = (
        db.query(func.coalesce(func.sum(TimeshareInstallment.amount), 0))
        .join(TimeshareContract, TimeshareContract.id == TimeshareInstallment.contract_id)
        .filter(TimeshareContract.branch_id == branch_id, TimeshareInstallment.status == "overdue")
        .scalar()
    )
    pending = (
        db.query(func.coalesce(func.sum(TimeshareInstallment.amount), 0))
        .join(TimeshareContract, TimeshareContract.id == TimeshareInstallment.contract_id)
        .filter(TimeshareContract.branch_id == branch_id, TimeshareInstallment.status == "pending")
        .scalar()
    )
    return {"overdue_total": overdue or Decimal("0"), "pending_total": pending or Decimal("0")}


def stats_by_partner(db: Session, branch_id: int) -> list:
    """
    عقود نشطة (غير ملغاة) مجمّعة حسب الشريك — مع صافي حصة المنتجع
    (resort_share) من إجمالي الدفعات الأولى بعد خصم نصيب الشريك
    (partner_share_pct) — مصدر: elkheima-beach-resort خاصية khayma_share.
    """
    from sqlalchemy import func  # noqa: PLC0415

    return (
        db.query(
            TimeshareContract.partner_company,
            func.count(TimeshareContract.id).label("contracts"),
            func.coalesce(func.sum(TimeshareContract.total_value), 0).label("total_value"),
            func.coalesce(func.sum(TimeshareContract.down_payment), 0).label("total_down"),
            func.coalesce(
                func.sum(
                    TimeshareContract.down_payment
                    * (1 - TimeshareContract.partner_share_pct / 100)
                ), 0,
            ).label("resort_share"),
        )
        .filter(TimeshareContract.branch_id == branch_id, TimeshareContract.status != "cancelled")
        .group_by(TimeshareContract.partner_company)
        .order_by(func.sum(TimeshareContract.total_value).desc())
        .all()
    )


def stats_by_room_type(db: Session, branch_id: int) -> list:
    from sqlalchemy import func  # noqa: PLC0415

    return (
        db.query(
            TimeshareContract.room_type,
            func.count(TimeshareContract.id).label("contracts"),
            func.coalesce(func.sum(TimeshareContract.total_value), 0).label("total_value"),
            func.coalesce(func.avg(TimeshareContract.total_value), 0).label("avg_value"),
        )
        .filter(TimeshareContract.branch_id == branch_id, TimeshareContract.status != "cancelled")
        .group_by(TimeshareContract.room_type)
        .order_by(func.count(TimeshareContract.id).desc())
        .all()
    )


def stats_by_batch(db: Session, branch_id: int) -> list:
    from sqlalchemy import func  # noqa: PLC0415

    return (
        db.query(
            TimeshareContract.batch_number,
            func.count(TimeshareContract.id).label("contracts"),
            func.coalesce(func.sum(TimeshareContract.total_value), 0).label("total_value"),
            func.coalesce(func.sum(TimeshareContract.down_payment), 0).label("total_down"),
            func.min(TimeshareContract.created_at).label("batch_date"),
        )
        .filter(TimeshareContract.branch_id == branch_id, TimeshareContract.batch_number.isnot(None))
        .group_by(TimeshareContract.batch_number)
        .order_by(TimeshareContract.batch_number.desc())
        .limit(20)
        .all()
    )


def cancellation_summary(db: Session, branch_id: int) -> dict:
    from sqlalchemy import func  # noqa: PLC0415

    row = (
        db.query(
            func.count(TimeshareContract.id),
            func.coalesce(func.sum(TimeshareContract.cancel_amount), 0),
        )
        .filter(TimeshareContract.branch_id == branch_id, TimeshareContract.status == "cancelled")
        .first()
    )
    return {"count": row[0] or 0, "refunded": row[1] or Decimal("0")}


def overall_collection(db: Session, branch_id: int) -> dict:
    from sqlalchemy import case, func  # noqa: PLC0415

    row = (
        db.query(
            func.coalesce(func.sum(case((TimeshareInstallment.status == "paid", TimeshareInstallment.paid_amount), else_=0)), 0),
            func.coalesce(func.sum(case((TimeshareInstallment.status.in_(["pending", "overdue"]), TimeshareInstallment.amount), else_=0)), 0),
            func.coalesce(func.sum(case((TimeshareInstallment.status == "overdue", TimeshareInstallment.amount), else_=0)), 0),
        )
        .join(TimeshareContract, TimeshareContract.id == TimeshareInstallment.contract_id)
        .filter(TimeshareContract.branch_id == branch_id)
        .first()
    )
    collected, pending, overdue = row[0] or Decimal("0"), row[1] or Decimal("0"), row[2] or Decimal("0")
    return {"collected": collected, "pending": pending, "overdue": overdue}


def cancel_contract(db: Session, contract: TimeshareContract, cancel_amount: Decimal) -> TimeshareContract:
    from datetime import date as _date  # noqa: PLC0415

    contract.status = "cancelled"
    contract.cancelled_at = _date.today()
    contract.cancel_amount = cancel_amount
    db.flush()
    return contract


# ── Waitlist ──────────────────────────────────────────────────────────

def get_next_position(db: Session, branch_id: int) -> int:
    from sqlalchemy import func  # noqa: PLC0415
    max_pos = db.query(func.max(TimeshareWaitlist.position)).filter(
        TimeshareWaitlist.branch_id == branch_id,
        TimeshareWaitlist.status == "waiting",
    ).scalar()
    return (max_pos or 0) + 1


def create_waitlist_entry(db: Session, data: WaitlistCreate) -> TimeshareWaitlist:
    obj = TimeshareWaitlist(
        **data.model_dump(),
        position=get_next_position(db, data.branch_id),
    )
    db.add(obj)
    db.flush()
    return obj


def list_waitlist(db: Session, branch_id: int) -> list[TimeshareWaitlist]:
    return db.query(TimeshareWaitlist).filter(
        TimeshareWaitlist.branch_id == branch_id,
        TimeshareWaitlist.status == "waiting",
    ).order_by(TimeshareWaitlist.position).all()


# ── Visits ────────────────────────────────────────────────────────────

def create_visit(db: Session, data: TimeshareVisitCreate, nights: int, unit_id: Optional[int] = None) -> TimeshareVisit:
    visit = TimeshareVisit(
        branch_id=data.branch_id, contract_id=data.contract_id,
        booking_id=data.booking_id, unit_id=unit_id, check_in=data.check_in, check_out=data.check_out,
        nights=nights, notes=data.notes,
    )
    db.add(visit)
    db.flush()
    return visit


# ── Units — تخصيص وحدة فعلية عند إنشاء زيارة ─────────────────────────

def get_unit(db: Session, unit_id: int) -> Optional[TimeshareUnit]:
    return db.query(TimeshareUnit).filter(TimeshareUnit.id == unit_id).first()


def lock_unit_for_visit(db: Session, unit_id: int) -> Optional[TimeshareUnit]:
    """SELECT ... FOR UPDATE NOWAIT — يقفل صف الوحدة طوال الـ transaction عشان
    يمنع تعارض حجز حقيقي (double-booking) لو حصلت محاولتين متزامنتين لتخصيص
    نفس الوحدة لنفس الفترة. نفس منطق pms.crud.lock_room_for_booking بالظبط —
    كان ناقص هنا رغم إن create_visit بيعمل تحقق تعارض (has_overlapping_visit)
    زي get_available_rooms بالظبط، بس من غير أي قفل صف يمنع الـ race condition
    بين التحقق والـ INSERT."""
    return (
        db.query(TimeshareUnit)
        .filter(TimeshareUnit.id == unit_id)
        .with_for_update(nowait=True)
        .first()
    )


def list_units(
    db: Session, branch_id: int,
    unit_type: Optional[str] = None, status: Optional[str] = None,
) -> list[TimeshareUnit]:
    q = db.query(TimeshareUnit).filter(TimeshareUnit.branch_id == branch_id)
    if unit_type:
        q = q.filter(TimeshareUnit.unit_type == unit_type)
    if status:
        q = q.filter(TimeshareUnit.status == status)
    return q.order_by(TimeshareUnit.unit_number).all()


def has_overlapping_visit(
    db: Session, unit_id: int, check_in: date, check_out: date,
    exclude_visit_id: Optional[int] = None,
) -> bool:
    """هل فيه زيارة أخرى (scheduled/active) على نفس الوحدة بتتقاطع مع
    الفترة المطلوبة؟ نفس منطق date-overlap subquery المستخدم في
    pms.crud.get_available_rooms."""
    q = db.query(TimeshareVisit).filter(
        TimeshareVisit.unit_id == unit_id,
        TimeshareVisit.status.in_(["scheduled", "active"]),
        TimeshareVisit.check_in < check_out,
        TimeshareVisit.check_out > check_in,
    )
    if exclude_visit_id:
        q = q.filter(TimeshareVisit.id != exclude_visit_id)
    return db.query(q.exists()).scalar()


def find_available_unit(
    db: Session, branch_id: int, unit_type: str, check_in: date, check_out: date,
) -> Optional[TimeshareUnit]:
    """يُرجع أول وحدة متاحة من نوع unit_type بدون أي زيارة متقاطعة مع
    الفترة المطلوبة — لعقد عائم (بدون unit_id ثابت)."""
    booked_unit_ids = (
        db.query(TimeshareVisit.unit_id)
        .filter(
            TimeshareVisit.unit_id.isnot(None),
            TimeshareVisit.status.in_(["scheduled", "active"]),
            TimeshareVisit.check_in < check_out,
            TimeshareVisit.check_out > check_in,
        )
        .subquery()
    )
    return (
        db.query(TimeshareUnit)
        .filter(
            TimeshareUnit.branch_id == branch_id,
            TimeshareUnit.unit_type == unit_type,
            TimeshareUnit.status != "maintenance",
            ~TimeshareUnit.id.in_(select(booked_unit_ids.c.unit_id)),
        )
        .order_by(TimeshareUnit.unit_number)
        .first()
    )


def get_visit(db: Session, visit_id: int) -> Optional[TimeshareVisit]:
    return db.query(TimeshareVisit).filter(TimeshareVisit.id == visit_id).first()


def list_visits(
    db: Session, branch_id: int,
    contract_id: Optional[int] = None, status: Optional[str] = None,
) -> list[TimeshareVisit]:
    q = db.query(TimeshareVisit).filter(TimeshareVisit.branch_id == branch_id)
    if contract_id:
        q = q.filter(TimeshareVisit.contract_id == contract_id)
    if status:
        q = q.filter(TimeshareVisit.status == status)
    return q.order_by(TimeshareVisit.check_in.desc()).all()


def update_visit(db: Session, visit: TimeshareVisit, data: TimeshareVisitUpdate) -> TimeshareVisit:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(visit, field, value)
    db.flush()
    return visit
