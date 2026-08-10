"""app/modules/timeshare/crud.py"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.timeshare.models import (
    TimeshareContract, TimeshareInstallment, TimeshareMaintenanceDue,
    TimeshareSupportTicket, TimeshareSupportTicketReply,
    TimeshareUnit, TimeshareVisit, TimeshareVisitRequest, TimeshareWaitlist,
)
from app.modules.timeshare.schemas import (
    TimeshareContractCreate, TimeshareContractUpdate,
    PayInstallmentRequest, PayMaintenanceDueRequest,
    TimeshareSupportTicketCreate, TimeshareUnitCreate, TimeshareUnitUpdate,
    TimeshareVisitCreate, TimeshareVisitRequestCreate,
    TimeshareVisitUpdate, WaitlistCreate,
)
from app.core.config import settings
from app.resort_os.timezone_utils import business_today


def _next_contract_number(db: Session) -> str:
    # ⚠️ كان بيستخدم datetime.utcnow() — لو السيرفر مش UTC+0 بتوقيت المنتجع
    # (Africa/Cairo)، عقد يتوقّع في أول/آخر الليل كان ممكن ياخد تاريخ يوم غلط
    # في رقمه (نفس فئة باج توقيت تذاكر المطبخ). بقى بتوقيت المنتجع الفعلي.
    today = business_today(settings.TIMEZONE).strftime("%Y%m%d")
    count = db.query(TimeshareContract).filter(
        TimeshareContract.contract_number.like(f"TS-{today}-%")
    ).count()
    return f"TS-{today}-{count + 1:04d}"


def get_contract(db: Session, contract_id: int) -> Optional[TimeshareContract]:
    return db.query(TimeshareContract).filter(TimeshareContract.id == contract_id).first()


def get_contract_by_number(db: Session, contract_number: str) -> Optional[TimeshareContract]:
    """بوابة العميل العامة (verify-request) — contract_number فريد عالميًا
    (unique=True على العمود)، فمحتاجناش branch_id للبحث."""
    return db.query(TimeshareContract).filter(TimeshareContract.contract_number == contract_number).first()


def get_contract_by_form_number(db: Session, branch_id: int, form_number: str) -> Optional[TimeshareContract]:
    return db.query(TimeshareContract).filter(
        TimeshareContract.branch_id == branch_id,
        TimeshareContract.form_number == form_number,
    ).first()


def get_contract_by_natural_key(
    db: Session, branch_id: int, customer_name: str,
    unit_id: Optional[int], start_date: date, total_value: Decimal,
) -> Optional[TimeshareContract]:
    """يستخدم كـ fallback لكشف التكرار وقت استيراد Excel لما ``form_number``
    فاضي — بدونه أي صفوف بدون رقم فورمة كانت بتتفادى فحص التكرار خالص، فرفع
    نفس الملف مرتين كان بيضاعف كل عقودها. المفتاح الطبيعي هنا (اسم العميل +
    الوحدة + تاريخ البداية + القيمة الإجمالية) مش مفتاح فريد قاعديًا (مفيش
    UniqueConstraint عليه)، بس تطابق الأربعة مع بعض عمليًا شبه مؤكد إنه نفس
    الصف بالظبط اتكرر، مش عقدين مختلفين بمصادفة."""
    return db.query(TimeshareContract).filter(
        TimeshareContract.branch_id == branch_id,
        TimeshareContract.customer_name == customer_name,
        TimeshareContract.unit_id == unit_id,
        TimeshareContract.start_date == start_date,
        TimeshareContract.total_value == total_value,
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


def lock_installment_for_update(db: Session, inst_id: int) -> Optional[TimeshareInstallment]:
    """SELECT ... FOR UPDATE NOWAIT — باج حقيقي اتصلح (2026-07-28، اتأكد
    بريبرو حي): pay_installment كانت بتقرا/تعدّل paid_amount من غير أي قفل
    صف خالص — تحصيلين متزامنين على نفس القسط ممكن يقروا نفس paid_amount
    القديم، وآخر واحد يعمل commit يمسح أثر التاني بصمت (فلوس محصّلة فعليًا
    بتختفي من غير أي خطأ). نفس نمط beach.crud.lock_inventory_for_update/
    timeshare.crud.lock_unit_for_visit — .populate_existing() لازم هنا نفس
    السبب الموثّق في lock_unit_for_visit فوق."""
    return (
        db.query(TimeshareInstallment)
        .filter(TimeshareInstallment.id == inst_id)
        .with_for_update(nowait=True)
        .populate_existing()
        .first()
    )


def lock_maintenance_due_for_update(db: Session, due_id: int) -> Optional[TimeshareMaintenanceDue]:
    """مرآة lock_installment_for_update — pay_maintenance_due نفس فئة الباج
    بالظبط (نفس نمط read-then-write من غير قفل)."""
    return (
        db.query(TimeshareMaintenanceDue)
        .filter(TimeshareMaintenanceDue.id == due_id)
        .with_for_update(nowait=True)
        .populate_existing()
        .first()
    )


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


# ── Maintenance dues (رسوم الصيانة السنوية) ───────────────────────────

def create_maintenance_due(
    db: Session, contract_id: int, fee_year: int, due_date: date, amount: Decimal,
) -> TimeshareMaintenanceDue:
    due = TimeshareMaintenanceDue(
        contract_id=contract_id, fee_year=fee_year, due_date=due_date, amount=amount,
    )
    db.add(due)
    db.flush()
    return due


def get_maintenance_due(db: Session, due_id: int) -> Optional[TimeshareMaintenanceDue]:
    return db.query(TimeshareMaintenanceDue).filter(TimeshareMaintenanceDue.id == due_id).first()


def get_maintenance_due_for_year(db: Session, contract_id: int, fee_year: int) -> Optional[TimeshareMaintenanceDue]:
    return db.query(TimeshareMaintenanceDue).filter(
        TimeshareMaintenanceDue.contract_id == contract_id,
        TimeshareMaintenanceDue.fee_year == fee_year,
    ).first()


def list_maintenance_dues(db: Session, contract_id: int) -> list[TimeshareMaintenanceDue]:
    return (
        db.query(TimeshareMaintenanceDue)
        .filter(TimeshareMaintenanceDue.contract_id == contract_id)
        .order_by(TimeshareMaintenanceDue.fee_year.desc())
        .all()
    )


def pay_maintenance_due(
    db: Session, due: TimeshareMaintenanceDue, req: PayMaintenanceDueRequest,
) -> TimeshareMaintenanceDue:
    due.paid_amount += req.paid_amount
    due.payment_method = req.payment_method
    due.receipt_number = req.receipt_number
    due.notes = req.notes
    if due.paid_amount >= due.amount:
        due.status = "paid"
        due.paid_at = datetime.utcnow()
    else:
        due.status = "partial"
    db.flush()
    return due


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


def list_visits_for_calendar(
    db: Session, branch_id: int, year: int,
) -> list[TimeshareVisit]:
    """زيارات فعلية مسجّلة (scheduled/active/completed) لسنة بعينها —
    لإدراجها في الكالندر بجانب العقود الثابتة المحسوبة رياضياً.

    نستخدم تحقق عام بدل فلتر ISO-week مباشر في SQL (PostgreSQL عنده
    date_part/extract، SQLite عندها strftime) — بنجيب كل زيارة تبدأ أو
    تنتهي في نفس السنة، ونترك حساب رقم الأسبوع للـ Python (isocalendar).
    الحجم صغير جداً (مئات الزيارات/سنة كحد أقصى) فلا مشكلة أداء."""
    return (
        db.query(TimeshareVisit)
        .filter(
            TimeshareVisit.branch_id == branch_id,
            TimeshareVisit.status.in_(["scheduled", "active", "completed"]),
            TimeshareVisit.check_in >= date(year, 1, 1),
            TimeshareVisit.check_in <= date(year, 12, 31),
        )
        .order_by(TimeshareVisit.check_in)
        .all()
    )


def get_booked_week_numbers(
    db: Session, branch_id: int, year: int, room_type: Optional[str] = None,
) -> set[int]:
    """أرقام الأسابيع المحجوزة فعلاً (عقود ثابتة + زيارات مجدولة/جارية) —
    لحساب الأسابيع المتاحة للبيع (`GET /timeshare/available-weeks`).

    العقود الثابتة: نعدّ أسبوعها بشكل مباشر من week_number.
    الزيارات الفعلية: نستخرج رقم الأسبوع ISO من check_in."""
    booked: set[int] = set()

    # ① عقود ثابتة (نشطة + موقوفة) — نفس منطق list_contracts_with_week
    q_contracts = db.query(TimeshareContract.week_number).filter(
        TimeshareContract.branch_id == branch_id,
        TimeshareContract.status.in_(["active", "suspended"]),
        TimeshareContract.week_number.isnot(None),
    )
    if room_type:
        q_contracts = q_contracts.filter(TimeshareContract.room_type == room_type)
    for (wn,) in q_contracts:
        booked.add(wn)

    # ② زيارات مجدولة/جارية (عقود عائمة أو ثابتة لسنة بعينها)
    q_visits = db.query(TimeshareVisit.check_in).filter(
        TimeshareVisit.branch_id == branch_id,
        TimeshareVisit.status.in_(["scheduled", "active"]),
        TimeshareVisit.check_in >= date(year, 1, 1),
        TimeshareVisit.check_in <= date(year, 12, 31),
    )
    if room_type:
        q_visits = q_visits.join(
            TimeshareContract, TimeshareContract.id == TimeshareVisit.contract_id
        ).filter(TimeshareContract.room_type == room_type)
    for (check_in,) in q_visits:
        booked.add(check_in.isocalendar()[1])

    return booked


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


def list_all_maintenance_dues(
    db: Session, branch_id: int,
    status: Optional[str] = None,
    contract_id: Optional[int] = None,
    fee_year: Optional[int] = None,
    search: Optional[str] = None,
    limit: int = 200,
) -> list[TimeshareMaintenanceDue]:
    """مرآة list_all_installments — نفس نمط الـ join/contains_eager بالظبط،
    بس فلتر fee_year بدل month (مستحقات الصيانة سنوية مش شهرية)."""
    from sqlalchemy.orm import contains_eager  # noqa: PLC0415

    q = (
        db.query(TimeshareMaintenanceDue)
        .join(TimeshareContract, TimeshareContract.id == TimeshareMaintenanceDue.contract_id)
        .options(contains_eager(TimeshareMaintenanceDue.contract))
        .filter(TimeshareContract.branch_id == branch_id)
    )
    if status:
        q = q.filter(TimeshareMaintenanceDue.status == status)
    if contract_id:
        q = q.filter(TimeshareMaintenanceDue.contract_id == contract_id)
    if fee_year:
        q = q.filter(TimeshareMaintenanceDue.fee_year == fee_year)
    if search:
        q = q.filter(TimeshareContract.customer_name.ilike(f"%{search}%"))
    return q.order_by(TimeshareMaintenanceDue.due_date.desc()).limit(limit).all()


def maintenance_dues_summary(db: Session, branch_id: int) -> dict:
    """مرآة installments_summary."""
    from sqlalchemy import func  # noqa: PLC0415

    overdue = (
        db.query(func.coalesce(func.sum(TimeshareMaintenanceDue.amount), 0))
        .join(TimeshareContract, TimeshareContract.id == TimeshareMaintenanceDue.contract_id)
        .filter(TimeshareContract.branch_id == branch_id, TimeshareMaintenanceDue.status == "overdue")
        .scalar()
    )
    pending = (
        db.query(func.coalesce(func.sum(TimeshareMaintenanceDue.amount), 0))
        .join(TimeshareContract, TimeshareContract.id == TimeshareMaintenanceDue.contract_id)
        .filter(TimeshareContract.branch_id == branch_id, TimeshareMaintenanceDue.status == "pending")
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
    contract.status = "cancelled"
    contract.cancelled_at = business_today(settings.TIMEZONE)
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
    """waiting + notified بس — الحالتان اللي لسه محتاجتان متابعة/إجراء من
    الموظف. confirmed/cancelled/expired حالات نهائية (تاريخية)، مش قائمة
    عمل — استبعادها هنا مقصود، مش سهو."""
    return db.query(TimeshareWaitlist).filter(
        TimeshareWaitlist.branch_id == branch_id,
        TimeshareWaitlist.status.in_(["waiting", "notified"]),
    ).order_by(TimeshareWaitlist.position).all()


def get_waitlist_entry(db: Session, waitlist_id: int) -> Optional[TimeshareWaitlist]:
    return db.query(TimeshareWaitlist).filter(TimeshareWaitlist.id == waitlist_id).first()


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


def get_unit_by_number(db: Session, branch_id: int, unit_number: str) -> Optional[TimeshareUnit]:
    return db.query(TimeshareUnit).filter(
        TimeshareUnit.branch_id == branch_id, TimeshareUnit.unit_number == unit_number,
    ).first()


def lock_unit_for_visit(db: Session, unit_id: int) -> Optional[TimeshareUnit]:
    """SELECT ... FOR UPDATE NOWAIT — يقفل صف الوحدة طوال الـ transaction عشان
    يمنع تعارض حجز حقيقي (double-booking) لو حصلت محاولتين متزامنتين لتخصيص
    نفس الوحدة لنفس الفترة. نفس منطق pms.crud.lock_room_for_booking بالظبط —
    كان ناقص هنا رغم إن create_visit بيعمل تحقق تعارض (has_overlapping_visit)
    زي get_available_rooms بالظبط، بس من غير أي قفل صف يمنع الـ race condition
    بين التحقق والـ INSERT.

    ⚠️ `.populate_existing()` لازم هنا: للعقود العائمة (`contract.unit_id`
    فاضي)، `services.create_visit` بيعمل قراءة أولى غير مقفولة بـ
    `find_available_unit` قبل القفل ده على نفس الوحدة — نفس فئة الباج اللي
    اتكشفت فعليًا في beach.crud (identity map الـ Session بيفضل على القيمة
    القديمة من غير `.populate_existing()`، حتى بعد قفل ناجح). هنا التأثير
    أضيق من beach (ضمان منع الحجز المزدوج نفسه سليم لأن `has_overlapping_visit`
    استعلام حي من الداتابيز، مش بيعتمد على أي attribute من الـ unit object) —
    لكن `unit.status == "maintenance"` بعد القفل مباشرة كان ممكن يقرا حالة
    قديمة (قبل ما transaction تانية تحط الوحدة تحت الصيانة فعليًا وتعمل
    commit)، فيسمح بحجز زيارة على وحدة تحت الصيانة فعليًا."""
    return (
        db.query(TimeshareUnit)
        .filter(TimeshareUnit.id == unit_id)
        .populate_existing()
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


def unit_occupancy_today(db: Session, branch_id: int, today: date) -> tuple[int, int]:
    """(الوحدات المشغولة اليوم، إجمالي المخزون القابل للحجز) — TimeshareUnit.
    status='occupied' موصوف في الموديل بس مفيش أي كود بيضبطه فعليًا خالص
    (حالة حية، مش flag يدوي)، فبنحسبها ديناميكيًا من TimeshareVisit
    المتقاطعة مع اليوم — نفس منطق find_available_unit بالظبط. وحدات
    maintenance مستبعدة من الإجمالي (مش مخزون قابل للبيع حاليًا)."""
    total = db.query(TimeshareUnit).filter(
        TimeshareUnit.branch_id == branch_id,
        TimeshareUnit.status != "maintenance",
    ).count()
    occupied = (
        db.query(TimeshareVisit.unit_id)
        .join(TimeshareUnit, TimeshareUnit.id == TimeshareVisit.unit_id)
        .filter(
            TimeshareUnit.branch_id == branch_id,
            TimeshareVisit.status.in_(["scheduled", "active"]),
            TimeshareVisit.check_in <= today,
            TimeshareVisit.check_out > today,
        )
        .distinct()
        .count()
    )
    return occupied, total


def create_unit(db: Session, data: TimeshareUnitCreate) -> TimeshareUnit:
    unit = TimeshareUnit(**data.model_dump())
    db.add(unit)
    db.flush()
    return unit


def update_unit(db: Session, unit: TimeshareUnit, data: TimeshareUnitUpdate) -> TimeshareUnit:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(unit, field, value)
    db.flush()
    return unit


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


def has_upcoming_visit(db: Session, contract_id: int, today: date) -> bool:
    """فيه زيارة مجدولة/جارية (scheduled|active) لسه ما خلصتش لهذا العقد —
    راجع services.transfer_unit: تحويل وحدة عقد عنده زيارة قادمة على الوحدة
    القديمة هيسيب تعارض بين TimeshareVisit.unit_id (لسه القديمة) وعقد بقى
    مربوط بوحدة تانية، فبنرفض التحويل لحد ما المدير يلغي/يعيد جدولة الزيارة."""
    return db.query(TimeshareVisit).filter(
        TimeshareVisit.contract_id == contract_id,
        TimeshareVisit.status.in_(["scheduled", "active"]),
        TimeshareVisit.check_out >= today,
    ).first() is not None


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


# ── Visit Requests (بوابة العميل العامة) ─────────────────────────────

def create_visit_request(
    db: Session, contract: TimeshareContract, data: TimeshareVisitRequestCreate,
) -> TimeshareVisitRequest:
    now = datetime.utcnow()
    req = TimeshareVisitRequest(
        branch_id=contract.branch_id, contract_id=contract.id,
        preferred_start=data.preferred_start, preferred_end=data.preferred_end,
        alt_start_1=data.alt_start_1, alt_end_1=data.alt_end_1,
        alt_start_2=data.alt_start_2, alt_end_2=data.alt_end_2,
        notes=data.notes,
        terms_version=data.terms_version, terms_accepted_at=now,
        booking_rules_version=data.booking_rules_version, booking_rules_accepted_at=now,
    )
    db.add(req)
    db.flush()
    return req


def get_visit_request(db: Session, request_id: int) -> Optional[TimeshareVisitRequest]:
    return db.query(TimeshareVisitRequest).filter(TimeshareVisitRequest.id == request_id).first()


def list_visit_requests_for_contract(db: Session, contract_id: int) -> list[TimeshareVisitRequest]:
    return (
        db.query(TimeshareVisitRequest)
        .filter(TimeshareVisitRequest.contract_id == contract_id)
        .order_by(TimeshareVisitRequest.created_at.desc())
        .all()
    )


def list_visit_requests_for_branch(
    db: Session, branch_id: int, status: Optional[str] = None,
) -> list[TimeshareVisitRequest]:
    from sqlalchemy.orm import contains_eager  # noqa: PLC0415

    q = (
        db.query(TimeshareVisitRequest)
        .join(TimeshareContract, TimeshareContract.id == TimeshareVisitRequest.contract_id)
        .options(contains_eager(TimeshareVisitRequest.contract))
        .filter(TimeshareVisitRequest.branch_id == branch_id)
    )
    if status:
        q = q.filter(TimeshareVisitRequest.status == status)
    return q.order_by(TimeshareVisitRequest.created_at.desc()).all()


def count_pending_visit_requests(db: Session, branch_id: int) -> int:
    return db.query(TimeshareVisitRequest).filter(
        TimeshareVisitRequest.branch_id == branch_id,
        TimeshareVisitRequest.status == "pending",
    ).count()


# ── Support Tickets (بوابة العميل العامة) ────────────────────────────

def create_support_ticket(
    db: Session, contract: TimeshareContract, data: TimeshareSupportTicketCreate,
) -> TimeshareSupportTicket:
    ticket = TimeshareSupportTicket(
        branch_id=contract.branch_id, contract_id=contract.id, subject=data.subject,
    )
    db.add(ticket)
    db.flush()
    reply = TimeshareSupportTicketReply(
        ticket_id=ticket.id, author_type="owner", author_user_id=None, message=data.message,
    )
    db.add(reply)
    db.flush()
    return ticket


def get_support_ticket(db: Session, ticket_id: int) -> Optional[TimeshareSupportTicket]:
    return db.query(TimeshareSupportTicket).filter(TimeshareSupportTicket.id == ticket_id).first()


def list_support_tickets_for_contract(db: Session, contract_id: int) -> list[TimeshareSupportTicket]:
    return (
        db.query(TimeshareSupportTicket)
        .filter(TimeshareSupportTicket.contract_id == contract_id)
        .order_by(TimeshareSupportTicket.created_at.desc())
        .all()
    )


def list_support_tickets_for_branch(
    db: Session, branch_id: int, status: Optional[str] = None,
) -> list[TimeshareSupportTicket]:
    from sqlalchemy.orm import contains_eager  # noqa: PLC0415

    q = (
        db.query(TimeshareSupportTicket)
        .join(TimeshareContract, TimeshareContract.id == TimeshareSupportTicket.contract_id)
        .options(contains_eager(TimeshareSupportTicket.contract))
        .filter(TimeshareSupportTicket.branch_id == branch_id)
    )
    if status:
        q = q.filter(TimeshareSupportTicket.status == status)
    return q.order_by(TimeshareSupportTicket.created_at.desc()).all()


def count_open_support_tickets(db: Session, branch_id: int) -> int:
    return db.query(TimeshareSupportTicket).filter(
        TimeshareSupportTicket.branch_id == branch_id,
        TimeshareSupportTicket.status.in_(("open", "in_progress")),
    ).count()


def add_ticket_reply(
    db: Session, ticket: TimeshareSupportTicket, message: str,
    author_type: str, author_user_id: Optional[int] = None,
) -> TimeshareSupportTicketReply:
    reply = TimeshareSupportTicketReply(
        ticket_id=ticket.id, author_type=author_type, author_user_id=author_user_id, message=message,
    )
    db.add(reply)
    db.flush()
    return reply
