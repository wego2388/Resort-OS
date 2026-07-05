"""app/modules/timeshare/services.py"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.modules.timeshare import crud
from app.modules.timeshare.models import TimeshareContract, TimeshareInstallment, TimeshareVisit
from app.modules.timeshare.schemas import (
    TimeshareContractCreate, TimeshareContractUpdate,
    PayInstallmentRequest, TimeshareVisitCreate, TimeshareVisitUpdate, WaitlistCreate,
)
from app.resort_os.timeshare_engine import (
    generate_installment_schedule,
)


class VisitConflictError(Exception):
    """وحدة تايم شير مقفولة فعلاً أو ماسكاها transaction تانية الآن — 409، مش 400."""


def get_contract_or_404(db: Session, contract_id: int) -> TimeshareContract:
    c = crud.get_contract(db, contract_id)
    if not c:
        raise ValueError(f"العقد {contract_id} غير موجود")
    return c


def create_contract(db: Session, data: TimeshareContractCreate, signed_by: int) -> TimeshareContract:
    if data.down_payment > data.total_value:
        raise ValueError("الدفعة الأولى لا يمكن أن تتجاوز إجمالي قيمة العقد")
    if data.end_date and data.end_date <= data.start_date:
        raise ValueError("تاريخ الانتهاء يجب أن يكون بعد تاريخ البداية")

    contract = crud.create_contract(db, data, signed_by)

    # توليد جدول الأقساط من الـ engine
    schedule = generate_installment_schedule(
        total_value=data.total_value,
        down_payment=data.down_payment,
        installments=data.installments,
        installment_period=data.installment_period,
        first_installment_date=data.first_installment_date,
    )
    crud.create_installments(db, contract.id, [
        {"installment_no": s.installment_no, "due_date": s.due_date, "amount": s.amount}
        for s in schedule
    ])

    # قيد إيرادات مؤجَّلة (deferred revenue)
    _post_deferred_revenue_journal(db, contract)

    db.commit()
    db.refresh(contract)
    return contract


def _post_deferred_revenue_journal(db: "Session", contract: "TimeshareContract") -> None:
    """Dr. Cash (1100) / Cr. Deferred Revenue (2300) عند إنشاء العقد."""
    from decimal import Decimal as _D  # noqa: PLC0415
    from app.core.config import settings  # noqa: PLC0415
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415
    from app.resort_os.timezone_utils import business_today  # noqa: PLC0415

    post_simple_revenue_journal(
        db, contract.branch_id, business_today(settings.TIMEZONE),
        debit_account_code="1100", credit_account_code="2300",
        amount=contract.down_payment or _D("0"),
        reference=f"TS-DP-{contract.contract_number}",
        description=f"دفعة أولى تايم شير — {contract.contract_number}",
        source="timeshare", source_id=contract.id,
        created_by=contract.signed_by or 0,
    )


def update_contract(db: Session, contract_id: int, data: TimeshareContractUpdate) -> TimeshareContract:
    contract = get_contract_or_404(db, contract_id)
    obj = crud.update_contract(db, contract, data)
    db.commit()
    db.refresh(obj)
    return obj


def pay_installment(db: Session, inst_id: int, req: PayInstallmentRequest) -> TimeshareInstallment:
    """⚠️ 3 باجات حقيقية اتصلحوا هنا (اتكشفوا أثناء اختبار حي كمدير خدمة عملاء
    تايم شير):
    1. مفيش أي تحقق من حالة العقد — كان ممكن تسجّل تحصيل قسط على عقد **ملغي**
       أو **منتهي** فعليًا (العقد اتلغى بس القسط المرتبط بيه فضل قابل للتحصيل).
    2. مفيش أي حد أقصى على المبلغ — إدخال 50,000 على قسط قيمته 10,000 كان
       بيتقبل بصمت (paid_amount بيبقى أكبر من amount، والحالة بتبقى "paid" من
       غير أي تنبيه أو تسجيل فرق) — باج مالي حقيقي، مش نظري.
    3. **الأهم**: تحصيل قسط عمره ما كان بيرحّل أي قيد يومية خالص — بعكس الدفعة
       الأولى (_post_deferred_revenue_journal بتترحّل عند إنشاء العقد فقط).
       يعني كل تحصيلات الأقساط (اللي هي معظم إيراد التايم شير على مدار سنين
       العقد) كانت غايبة تمامًا عن الدفاتر المحاسبية — مخالفة مباشرة لـ
       "Finance First" (§5.2 في CLAUDE.md بيذكر أقساط التايم شير بالاسم صراحةً).
    """
    inst = crud.get_installment(db, inst_id)
    if not inst:
        raise ValueError(f"القسط {inst_id} غير موجود")
    if inst.status == "paid":
        raise ValueError("القسط مدفوع بالكامل مسبقاً")

    contract = crud.get_contract(db, inst.contract_id)
    if not contract:
        raise ValueError(f"العقد المرتبط بالقسط {inst_id} غير موجود")
    if contract.status == "cancelled":
        raise ValueError(f"العقد {contract.contract_number} ملغي — لا يمكن تحصيل أقساط عليه")
    if contract.status == "expired":
        raise ValueError(f"العقد {contract.contract_number} منتهي — لا يمكن تحصيل أقساط عليه")

    remaining = inst.amount - inst.paid_amount
    if req.paid_amount > remaining:
        raise ValueError(
            f"المبلغ المُدخَل ({req.paid_amount:,.2f} ج) أكبر من المتبقي على هذا "
            f"القسط ({remaining:,.2f} ج) — تحقّق من المبلغ قبل التسجيل"
        )

    obj = crud.pay_installment(db, inst, req)
    _post_installment_payment_journal(db, contract, req.paid_amount, inst)

    # إلغاء تجميد الحجز إن كانت كل الأقساط المتأخرة سُدِّدت
    if contract.booking_frozen:
        overdue_count = sum(
            1 for i in contract.installments_list
            if i.status in ("overdue", "partial") and i.id != inst_id
        )
        if overdue_count == 0:
            contract.booking_frozen = False

    db.commit()
    db.refresh(obj)
    return obj


def _post_installment_payment_journal(
    db: "Session", contract: "TimeshareContract", paid_amount, inst: "TimeshareInstallment",
) -> None:
    """Dr. Cash (1100) / Cr. Deferred Revenue (2300) عند تحصيل أي قسط — نفس
    منطق _post_deferred_revenue_journal بالظبط بس لكل تحصيل قسط، مش الدفعة
    الأولى بس."""
    from app.core.config import settings  # noqa: PLC0415
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415
    from app.resort_os.timezone_utils import business_today  # noqa: PLC0415

    post_simple_revenue_journal(
        db, contract.branch_id, business_today(settings.TIMEZONE),
        debit_account_code="1100", credit_account_code="2300",
        amount=paid_amount,
        reference=f"TS-INST-{contract.contract_number}-{inst.installment_no}",
        description=f"تحصيل قسط رقم {inst.installment_no} — {contract.contract_number}",
        source="timeshare", source_id=contract.id,
        created_by=0,
    )


def add_to_waitlist(db: Session, data: WaitlistCreate) -> object:
    get_contract_or_404(db, data.contract_id)
    if data.requested_end <= data.requested_start:
        raise ValueError("تاريخ النهاية يجب أن يكون بعد تاريخ البداية")
    obj = crud.create_waitlist_entry(db, data)
    db.commit()
    db.refresh(obj)
    return obj


def generate_contract_pdf(db: Session, contract_id: int) -> bytes:
    """PDF ملخص عقد التايم شير."""
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    contract = get_contract_or_404(db, contract_id)
    week_label = f"أسبوع {contract.week_number}" if contract.week_number else "عائم"
    fields = [
        ("العميل",             contract.customer_name),
        ("رقم العقد",          contract.contract_number),
        ("نوع الغرفة",         contract.room_type),
        ("الأسبوع",            week_label),
        ("الليالي/سنة",        str(contract.nights_per_year)),
        ("إجمالي العقد",       f"{contract.total_value:,.2f} EGP"),
        ("الدفعة الأولى",      f"{contract.down_payment:,.2f} EGP"),
        ("عدد الأقساط",        str(contract.installments)),
        ("تاريخ البداية",      str(contract.start_date)),
        ("الحالة",             contract.status),
    ]
    return builder.receipt_pdf(
        reference=contract.contract_number,
        title="عقد تايم شير",
        fields=fields,
        total=float(contract.total_value),
        currency="EGP",
        note="الخيمة بيتش ريزورت — وثيقة العقد",
    )


# ── CS Dashboard ─────────────────────────────────────────────────────

def get_cs_summary(db: Session, branch_id: int) -> dict:
    """ملخص شامل لخدمة عملاء التايم شير — زيارات قادمة + متأخرات + نسبة تحصيل.

    ⚠️ "اليوم" هنا بيتحسب بتوقيت المنتجع (business_today) مش توقيت السيرفر
    المحلي — نفس فئة باج تذاكر المطبخ (KDS)، هنا بيأثّر على "الأيام المتبقية
    لزيارة قادمة" و"متأخرات" المعروضة لموظف خدمة العملاء."""
    from app.core.config import settings  # noqa: PLC0415
    from app.resort_os.timeshare_engine import ContractSummary, build_cs_summary, find_next_visit  # noqa: PLC0415
    from app.resort_os.timezone_utils import business_today  # noqa: PLC0415

    today = business_today(settings.TIMEZONE)
    rows = crud.list_active_contracts_with_aggregates(db, branch_id)

    summaries: list[ContractSummary] = []
    upcoming_visits = []
    for contract, collected, overdue_amount, pending_count, next_due in rows:
        summaries.append(ContractSummary(
            contract_id=contract.id,
            customer_name=contract.customer_name,
            customer_phone=contract.customer_phone,
            room_type=contract.room_type,
            week_number=contract.week_number,
            total_value=contract.total_value,
            collected=collected,
            overdue_amount=overdue_amount,
            pending_count=pending_count,
            next_due=next_due,
        ))
        if contract.week_number:
            visit = find_next_visit(contract.week_number, contract.nights_per_year, today)
            if visit and 0 <= visit.days_until <= 30:
                upcoming_visits.append({
                    "id": contract.id, "contract_number": contract.contract_number,
                    "customer_name": contract.customer_name, "customer_phone": contract.customer_phone,
                    "room_type": contract.room_type, "week_number": contract.week_number,
                    "visit_start": visit.visit_start.isoformat(), "visit_end": visit.visit_end.isoformat(),
                    "days_until": visit.days_until, "overdue_amount": float(overdue_amount),
                })

    this_month_due = crud.get_this_month_due(db, branch_id, today)
    summary = build_cs_summary(summaries, this_month_due)
    summary["upcoming_visits"] = sorted(upcoming_visits, key=lambda x: x["days_until"])
    summary["overdue_clients"] = [
        {
            "id": c.contract_id, "customer_name": c.customer_name, "customer_phone": c.customer_phone,
            "room_type": c.room_type, "overdue_amount": float(c.overdue_amount),
            "pending_count": c.pending_count,
            "next_due": c.next_due.isoformat() if c.next_due else None,
        }
        for c in summary["overdue_clients"]
    ]
    return summary


def get_sales_dashboard(db: Session, branch_id: int) -> dict:
    """لوحة مبيعات لفريق المبيعات (مختلفة عن cs-summary الإداري) — pipeline
    (draft→active→...)، متأخرات بأرقام تليفون جاهزة للاتصال، أقساط الشهر الحالي."""
    cs = get_cs_summary(db, branch_id)
    pipeline = crud.count_contracts_by_status(db, branch_id)
    for key in ("draft", "active", "suspended", "cancelled", "expired"):
        pipeline.setdefault(key, 0)

    return {
        "pipeline": pipeline,
        "active_contracts": cs["active_contracts"],
        "overdue_contracts_count": cs["overdue_contracts_count"],
        "expired_contracts_count": pipeline.get("expired", 0),
        "this_month_due": cs["this_month_due"],
        "collection_rate_pct": cs["collection_rate_pct"],
        "total_value": cs["total_value"],
        "total_collected": cs["total_collected"],
        "total_overdue": cs["total_overdue"],
        "overdue_clients": cs["overdue_clients"],  # كل واحد فيه customer_phone جاهز للاتصال
        "upcoming_visits": cs["upcoming_visits"],
    }


def get_calendar(db: Session, branch_id: int, year: Optional[int] = None) -> dict:
    """تقويم 52 أسبوع ISO — كل أسبوع وعقوده."""
    from datetime import date as _date, timedelta as _timedelta  # noqa: PLC0415

    from app.core.config import settings  # noqa: PLC0415
    from app.resort_os.timeshare_engine import calculate_visit_window  # noqa: PLC0415
    from app.resort_os.timezone_utils import business_today  # noqa: PLC0415

    today = business_today(settings.TIMEZONE)
    year = year or today.year
    contracts = crud.list_contracts_with_week(db, branch_id)

    MONTH_AR = ["يناير", "فبراير", "مارس", "إبريل", "مايو", "يونيو",
                "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
    cur_week = today.isocalendar()[1] if today.year == year else -1

    week_map: dict[int, list[dict]] = {}
    for c in contracts:
        window = calculate_visit_window(c.week_number, c.nights_per_year, year, today)
        if not window:
            continue
        week_map.setdefault(c.week_number, []).append({
            "id": c.id, "contract_number": c.contract_number,
            "customer_name": c.customer_name, "customer_phone": c.customer_phone,
            "room_type": c.room_type, "season": c.season,
            "rci_included": c.rci_included, "nights_per_year": c.nights_per_year,
            "visit_start": window.visit_start.isoformat(), "visit_end": window.visit_end.isoformat(),
        })

    months: dict[int, list[dict]] = {}
    for w in range(1, 53):
        try:
            ws = _date.fromisocalendar(year, w, 1)
        except ValueError:
            continue
        we = ws + _timedelta(days=6)
        months.setdefault(ws.month, []).append({
            "week": w, "start_date": ws.isoformat(), "end_date": we.isoformat(),
            "is_current": w == cur_week, "is_past": we < today,
            "contracts": week_map.get(w, []),
        })

    return {
        "year": year,
        "total_booked_weeks": len(week_map),
        "calendar": [
            {"month": m, "month_name": MONTH_AR[m - 1], "weeks": months[m]}
            for m in sorted(months)
        ],
    }


def get_upcoming_visits(db: Session, branch_id: int, days: int = 30) -> list[dict]:
    from app.core.config import settings  # noqa: PLC0415
    from app.resort_os.timeshare_engine import find_next_visit  # noqa: PLC0415
    from app.resort_os.timezone_utils import business_today  # noqa: PLC0415

    today = business_today(settings.TIMEZONE)
    contracts = crud.list_contracts_with_week(db, branch_id)
    result = []
    for c in contracts:
        if c.status != "active":
            continue
        visit = find_next_visit(c.week_number, c.nights_per_year, today)
        if visit and 0 <= visit.days_until <= days:
            result.append({
                "id": c.id, "contract_number": c.contract_number,
                "customer_name": c.customer_name, "customer_phone": c.customer_phone,
                "customer_email": c.customer_email,
                "room_type": c.room_type, "week_number": c.week_number,
                "nights_per_year": c.nights_per_year, "season": c.season,
                "rci_included": c.rci_included,
                "visit_start": visit.visit_start.isoformat(), "visit_end": visit.visit_end.isoformat(),
                "days_until": visit.days_until,
                "total_value": float(c.total_value),
            })
    return sorted(result, key=lambda x: x["days_until"])


def list_installments(
    db: Session, branch_id: int,
    status: Optional[str] = None, contract_id: Optional[int] = None,
    month: Optional[str] = None, search: Optional[str] = None, limit: int = 200,
) -> dict:
    items = crud.list_all_installments(db, branch_id, status, contract_id, month, search, limit)
    return {
        "installments": items,
        "total": len(items),
        "summary": crud.installments_summary(db, branch_id),
    }


def get_stats(db: Session, branch_id: int) -> dict:
    by_partner = crud.stats_by_partner(db, branch_id)
    by_room_type = crud.stats_by_room_type(db, branch_id)
    by_batch = crud.stats_by_batch(db, branch_id)
    cancelled = crud.cancellation_summary(db, branch_id)
    collection = crud.overall_collection(db, branch_id)

    collected, pending = collection["collected"], collection["pending"]
    rate = round(float(collected) / float(collected + pending) * 100, 1) if (collected + pending) > 0 else 0

    return {
        "by_partner": [
            {"partner_company": r.partner_company, "contracts": r.contracts,
             "total_value": float(r.total_value), "total_down": float(r.total_down),
             "resort_share": float(r.resort_share)}
            for r in by_partner
        ],
        "by_room_type": [
            {"room_type": r.room_type, "contracts": r.contracts,
             "total_value": float(r.total_value), "avg_value": float(r.avg_value)}
            for r in by_room_type
        ],
        "by_batch": [
            {"batch_number": r.batch_number, "contracts": r.contracts,
             "total_value": float(r.total_value), "total_down": float(r.total_down),
             "batch_date": r.batch_date.date().isoformat() if r.batch_date else None}
            for r in by_batch
        ],
        "cancelled": {"count": cancelled["count"], "refunded": float(cancelled["refunded"])},
        "collection": {
            "collected": float(collection["collected"]),
            "pending": float(collection["pending"]),
            "overdue": float(collection["overdue"]),
            "rate": rate,
        },
    }


def cancel_contract(db: Session, contract_id: int, cancel_amount) -> TimeshareContract:
    contract = get_contract_or_404(db, contract_id)
    if contract.status == "cancelled":
        raise ValueError("العقد ملغي بالفعل")
    obj = crud.cancel_contract(db, contract, cancel_amount)
    db.commit()
    db.refresh(obj)
    return obj


# ── Visits ───────────────────────────────────────────────────────────

def create_visit(db: Session, data: TimeshareVisitCreate) -> TimeshareVisit:
    """يخصّص وحدة تايم شير فعلية للزيارة (real allocation، مش مجرد سطر تاريخ
    بلا أي حجز حقيقي) — مع منع تعارض حجز حقيقي (double-booking) على نفس
    الوحدة، بنفس منطق date-overlap المستخدم في pms.crud.get_available_rooms.

    ⚠️ باج تزامن حقيقي كان هنا: التحقق من التعارض (has_overlapping_visit/
    find_available_unit) وعملية الـ INSERT ما كانوش محميين بأي SELECT FOR
    UPDATE NOWAIT — يعني لو حصلت محاولتين حقيقيتين متزامنتين لتخصيص نفس
    الوحدة لنفس الفترة (نفس race condition اللي pms.services.create_booking
    بيمنعها بالظبط بقفل صف الغرفة)، الاتنين كانوا ممكن يعدّوا التحقق قبل ما
    أي واحدة تعمل commit ويتم تخصيص نفس الوحدة مرتين فعليًا. اتصلح بقفل صف
    الوحدة (with_for_update(nowait=True)) قبل إعادة التحقق من التعارض،
    بنفس نمط lock_room_for_booking بالظبط.

    ⚠️ باجان حقيقيان تانيان اتكشفوا واتصلحوا هنا (اختبار حي كمدير خدمة عملاء
    تايم شير): كان ممكن تخصيص وحدة فعلية لزيارة على عقد **ملغي بالفعل** (صفر
    تحقق من contract.status)، وكان ممكن كمان تحجز زيارة بتاريخ بعد
    contract.end_date (انتهاء مدة العقد) بدون أي رفض — يعني عميل عقده انتهى
    كان لسه يقدر ياخد وحدة فعلية من مخزون المنتجع."""
    contract = get_contract_or_404(db, data.contract_id)
    if data.check_out <= data.check_in:
        raise ValueError("check_out يجب أن يكون بعد check_in")
    if contract.status == "cancelled":
        raise ValueError(f"العقد {contract.contract_number} ملغي — لا يمكن حجز زيارة عليه")
    if contract.status == "expired":
        raise ValueError(f"العقد {contract.contract_number} منتهي — لا يمكن حجز زيارة عليه")
    if contract.end_date and data.check_in > contract.end_date:
        raise ValueError(
            f"تاريخ الزيارة بعد نهاية مدة العقد {contract.contract_number} "
            f"({contract.end_date.isoformat()}) — العقد منتهي لهذه الفترة"
        )
    if contract.booking_frozen:
        raise ValueError("الحجز مجمَّد لوجود أقساط متأخرة — سدِّد المتأخرات أولاً")
    nights = (data.check_out - data.check_in).days

    if contract.unit_id:
        candidate_id = contract.unit_id
    else:
        # عقد عائم — ابحث عن أي وحدة متاحة من نفس نوع الغرفة (قبل القفل، مجرد
        # ترشيح أولي) ثم اقفلها وأعد التحقق تحت الحماية فعليًا تحت.
        found = crud.find_available_unit(db, contract.branch_id, contract.room_type, data.check_in, data.check_out)
        if not found:
            raise ValueError(f"لا توجد وحدة متاحة من نوع {contract.room_type} في الفترة المطلوبة")
        candidate_id = found.id

    try:
        unit = crud.lock_unit_for_visit(db, candidate_id)
    except OperationalError:
        db.rollback()
        raise VisitConflictError(f"الوحدة {candidate_id} مقفولة الآن من عملية حجز أخرى — حاول مرة أخرى")

    if not unit:
        raise ValueError("الوحدة المخصَّصة لهذا العقد لم تعد موجودة")
    if unit.status == "maintenance":
        raise ValueError(f"الوحدة {unit.unit_number} تحت الصيانة حاليًا")
    # إعادة التحقق من التعارض بعد القفل — مفيش حد تاني يقدر يخصص نفس الوحدة
    # لنفس الفترة لحد ما الـ transaction دي تخلص (commit/rollback)
    if crud.has_overlapping_visit(db, unit.id, data.check_in, data.check_out):
        raise ValueError(f"الوحدة {unit.unit_number} محجوزة بالفعل في هذه الفترة")

    visit = crud.create_visit(db, data, nights, unit_id=unit.id)
    db.commit()
    db.refresh(visit)
    return visit


def update_visit(db: Session, visit_id: int, data: TimeshareVisitUpdate) -> TimeshareVisit:
    visit = crud.get_visit(db, visit_id)
    if not visit:
        raise ValueError(f"الزيارة {visit_id} غير موجودة")
    obj = crud.update_visit(db, visit, data)
    db.commit()
    db.refresh(obj)
    return obj


# ── Excel Batch Import ───────────────────────────────────────────────
# الصف الأول = أسماء الأعمدة (مطابقة لحقول TimeshareContractCreate)،
# الأعمدة الإلزامية: customer_name, room_type, total_value, down_payment,
# installments, start_date, first_installment_date. الباقي اختياري.
# Idempotent: لو form_number موجود بالفعل لنفس الفرع، الصف يتجاهَل (مش يتكرر).

_REQUIRED_COLUMNS = {
    "customer_name", "room_type", "total_value", "down_payment",
    "installments", "start_date", "first_installment_date",
}

_DATE_FIELDS = {"start_date", "end_date", "first_installment_date", "contract_date"}
_DECIMAL_FIELDS = {
    "total_value", "down_payment", "partner_share_pct", "purchase_price",
    "contract_deposit", "maintenance_fee", "maintenance_increase",
    "contract_value", "net_contract_value", "over_under_price",
}
_INT_FIELDS = {"week_number", "nights_per_year", "installments", "installment_period", "batch_number", "years_count"}
_BOOL_FIELDS = {"rci_included"}


def _coerce_cell(field: str, value):
    if value is None or value == "":
        return None
    if field in _DATE_FIELDS:
        from datetime import date as _date, datetime as _datetime  # noqa: PLC0415
        if isinstance(value, _datetime):
            return value.date()
        if isinstance(value, _date):
            return value
        return _datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    if field in _DECIMAL_FIELDS:
        from decimal import Decimal as _Decimal  # noqa: PLC0415
        return _Decimal(str(value))
    if field in _INT_FIELDS:
        return int(value)
    if field in _BOOL_FIELDS:
        return str(value).strip().lower() in ("1", "true", "yes", "y", "نعم")
    return str(value).strip()


def import_contracts_excel(
    db: Session, branch_id: int, file_content: bytes, signed_by: int,
) -> dict:
    import openpyxl  # noqa: PLC0415
    import io as _io  # noqa: PLC0415

    wb = openpyxl.load_workbook(_io.BytesIO(file_content), data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError("الملف فاضي")

    headers = [str(h).strip() if h else "" for h in rows[0]]
    valid_fields = set(TimeshareContractCreate.model_fields.keys())
    missing = _REQUIRED_COLUMNS - set(headers)
    if missing:
        raise ValueError(f"أعمدة إلزامية ناقصة: {', '.join(sorted(missing))}")

    imported, skipped, errors = 0, 0, []

    for i, row in enumerate(rows[1:], start=2):
        row_dict = {h: v for h, v in zip(headers, row) if h}
        if not row_dict.get("customer_name"):
            continue
        try:
            payload = {"branch_id": branch_id}
            for field, raw_value in row_dict.items():
                if field in valid_fields:
                    payload[field] = _coerce_cell(field, raw_value)

            form_number = payload.get("form_number")
            if form_number and crud.get_contract_by_form_number(db, branch_id, str(form_number)):
                skipped += 1
                continue

            data = TimeshareContractCreate(**{k: v for k, v in payload.items() if v is not None or k == "branch_id"})
            create_contract(db, data, signed_by)
            imported += 1
        except Exception as exc:
            errors.append(f"صف {i}: {str(exc)[:120]}")

    return {"imported": imported, "skipped": skipped, "errors": errors[:20]}
