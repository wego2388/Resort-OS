"""app/modules/analytics/services.py"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from jose import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.resort_os.timezone_utils import business_today

if TYPE_CHECKING:
    from app.modules.analytics.models import GuestReview

logger = logging.getLogger(__name__)


def get_dining_revenue_by_outlet_type(
    db: Session, branch_id: int, range_start: datetime, range_end: datetime,
) -> dict[str, dict]:
    """إيراد المطعم/الكافيه (والـ outlets المستقبلية زي بار المسبح/البوفيه من
    غير أي كود إضافي) — DINING_CUTOVER_PLAN.md D-05: بديل استعلامين منفصلين
    (restaurant.Order + cafe.CafeOrder) باستعلام واحد على DiningOrder،
    مفلتر بـ Outlet.outlet_type. مصدر الحقيقة الوحيد بعد الـ cutover.

    بيرجّع dict مفتاحه outlet_type، كل bucket فيه orders/total/covers
    (guests_count مجموع — مستخدم لـ DailyStats.restaurant_covers في
    app/tasks/analytics_tasks.py). الـ caller هو اللي بيقرر إيه المفاتيح
    المضمونة الوجود في الـ response (زي "restaurant"/"cafe" اللي الفرونت
    إند بيعتمد عليهم فعليًا)، الدالة دي مجرد بترجع اللي لقيته فعليًا في
    البيانات."""
    from app.modules.dining.models import DiningOrder, Outlet  # noqa: PLC0415

    rows = (
        db.query(Outlet.outlet_type, DiningOrder)
        .join(Outlet, DiningOrder.outlet_id == Outlet.id)
        .filter(
            DiningOrder.branch_id == branch_id,
            DiningOrder.status == "paid",
            DiningOrder.created_at >= range_start,
            DiningOrder.created_at <= range_end,
        )
        .all()
    )
    result: dict[str, dict] = {}
    for outlet_type, order in rows:
        bucket = result.setdefault(outlet_type, {"orders": 0, "total": Decimal("0"), "covers": 0})
        bucket["orders"] += 1
        bucket["total"] += order.total or Decimal("0")
        bucket["covers"] += order.guests_count or 0
    return result


SURVEY_TOKEN_ALGORITHM = "HS256"
SURVEY_TOKEN_TTL_DAYS = 7


def create_survey_token(
    branch_id: int, booking_id: int | None = None, timeshare_visit_id: int | None = None,
) -> str:
    """ينشئ JWT صالح 7 أيام للاستبيان — يُرسل لشاشة checkout (حجز فندقي) أو
    لزيارة تايم شير على حدٍّ سواء (ref_type يميّز بينهما، sub يحمل الـ id
    المناسب) — واحد بس لازم يتحدد، مش الاتنين ومش ولا واحد."""
    if bool(booking_id) == bool(timeshare_visit_id):
        raise ValueError("حدِّد إما booking_id أو timeshare_visit_id (واحد بالظبط)")

    ref_type = "booking" if booking_id else "timeshare_visit"
    ref_id = booking_id if booking_id else timeshare_visit_id
    payload = {
        "sub": str(ref_id),
        "ref_type": ref_type,
        "branch_id": branch_id,
        "purpose": "guest_survey",
        "exp": datetime.now(timezone.utc) + timedelta(days=SURVEY_TOKEN_TTL_DAYS),
    }
    return jwt.encode(payload, settings.SURVEY_TOKEN_SECRET, algorithm=SURVEY_TOKEN_ALGORITHM)


def verify_survey_token(token: str) -> dict:
    """يتحقق من صحة token الاستبيان — يُرجع payload أو يرفع HTTPException."""
    from fastapi import HTTPException
    try:
        payload = jwt.decode(token, settings.SURVEY_TOKEN_SECRET, algorithms=[SURVEY_TOKEN_ALGORITHM])
        if payload.get("purpose") != "guest_survey":
            raise HTTPException(status_code=400, detail="invalid survey token")
        return payload
    except Exception:
        raise HTTPException(status_code=400, detail="survey token expired or invalid")


def submit_review(
    db, branch_id: int, booking_id: int | None, data: dict,
    timeshare_visit_id: int | None = None,
) -> "GuestReview":
    """يُسجّل تقييم الضيف + ينشئ Activity(complaint) لو avg ≤ 2. يُربط إما
    بحجز فندقي (booking_id) أو بزيارة تايم شير (timeshare_visit_id) — الاثنين
    اختياريان ومستقلان (مش نفس الجدول، وحدات التايم شير مبنى منفصل)."""
    from app.modules.analytics.models import GuestReview, ReviewCategory

    overall = data.get("overall_rating", 3)

    review = GuestReview(
        branch_id=branch_id,
        guest_name=data.get("guest_name", "ضيف"),
        overall_rating=overall,
        comment=data.get("comment"),
        source="checkout_survey",
        is_published=overall >= 3,  # تُنشر التقييمات ≥ 3 تلقائياً
        reviewed_at=business_today(settings.TIMEZONE),
        booking_id=booking_id,
        timeshare_visit_id=timeshare_visit_id,
    )
    db.add(review)
    db.flush()

    # Add category ratings
    for cat_data in data.get("categories", []):
        db.add(ReviewCategory(
            review_id=review.id,
            category=cat_data["category"],
            rating=cat_data["rating"],
        ))

    db.commit()
    db.refresh(review)

    # avg ≤ 2 → CRM Activity(complaint) تلقائي
    if overall <= 2:
        try:
            _create_complaint_activity(db, branch_id, booking_id, timeshare_visit_id, overall)
        except Exception as exc:
            logger.error("Failed to create complaint activity: %s", exc)

    return review


def _create_complaint_activity(
    db, branch_id: int, booking_id: int | None, timeshare_visit_id: int | None, rating: int,
) -> None:
    """ينشئ Activity(complaint) في CRM عند تقييم ≤ 2."""
    from app.modules.crm.models import Activity, Customer

    # الحصول على عميل placeholder أو إنشاؤه
    customer = db.query(Customer).filter(
        Customer.branch_id == branch_id,
        Customer.full_name == "ضيف غير محدد",
    ).first()
    if not customer:
        customer = Customer(
            branch_id=branch_id,
            full_name="ضيف غير محدد",
            source="walk_in",
        )
        db.add(customer)
        db.flush()

    if booking_id:
        ref_label = f"حجز #{booking_id}"
    elif timeshare_visit_id:
        ref_label = f"زيارة تايم شير #{timeshare_visit_id}"
    else:
        ref_label = "تقييم يدوي (بدون حجز أو زيارة)"
    db.add(Activity(
        branch_id=branch_id,
        customer_id=customer.id,
        activity_type="complaint",
        title=f"تقييم سلبي من {ref_label} — التقييم: {rating}/5",
        due_date=business_today(settings.TIMEZONE),
        status="pending",
        notes=f"تقييم الضيف {rating}/5 — يحتاج متابعة عاجلة",
    ))
    db.commit()


# ── UtilityReading ────────────────────────────────────────────────────
# Task B audit (resort-os-docs/06-MODULES.md § ANALYTICS): "UtilityReading:
# type/period/consumption/unit_cost/total_cost → JournalEntry تلقائي" — الـ
# model والـ migration كانوا موجودين من زمان، بس مفيش أي طريقة تسجيل قراءة في
# كل النظام (لا schema، لا service، لا router). نفس فئة الباج الموثّقة في
# CLAUDE.md § 11.6 و TenantCashLog في leasing.

def record_utility_reading(db, data, recorded_by: int | None):
    """يسجّل قراءة مرفق (كهرباء/مياه/غاز/ديزل)، يحسب total_cost، ويرحّل قيد
    مصروف مرافق تلقائي (Dr. مصروفات مرافق 5300 / Cr. الصندوق 1100) —
    زي أي قيد تلقائي تاني في النظام، wrapped في try/except عشان غياب
    finance module مايكسرش analytics."""
    from app.modules.analytics.models import UtilityReading

    total_cost = (data.reading_value * data.unit_cost).quantize(Decimal("0.01"))
    reading = UtilityReading(
        branch_id=data.branch_id,
        reading_date=data.reading_date,
        utility_type=data.utility_type,
        reading_value=data.reading_value,
        unit=data.unit,
        unit_cost=data.unit_cost,
        total_cost=total_cost,
        notes=data.notes,
        recorded_by=recorded_by,
    )
    db.add(reading)
    db.flush()

    _post_utility_expense_journal(db, reading)

    db.commit()
    db.refresh(reading)
    return reading


def _post_utility_expense_journal(db, reading) -> None:
    """Dr. مصروفات مرافق (5300) / Cr. الصندوق (1100) — نفس نمط
    leasing._post_deposit_journal (try/except، no-op بصمت لو الحسابات
    مش موجودة)."""
    try:
        from app.modules.finance.crud import get_account_by_code, create_journal_entry  # noqa: PLC0415
        from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate  # noqa: PLC0415

        amount = reading.total_cost or Decimal("0")
        if amount <= 0:
            return

        expense_acc = get_account_by_code(db, reading.branch_id, "5300")
        cash_acc    = get_account_by_code(db, reading.branch_id, "1100")
        if not expense_acc or not cash_acc:
            return

        create_journal_entry(db, JournalEntryCreate(
            branch_id=reading.branch_id,
            entry_date=reading.reading_date,
            reference=f"UTL-{reading.id:06d}",
            description=f"مصروف مرفق ({reading.utility_type}) — {reading.reading_date}",
            source="analytics",
            source_id=reading.id,
            lines=[
                JournalLineCreate(account_id=expense_acc.id, debit=amount, credit=Decimal("0")),
                JournalLineCreate(account_id=cash_acc.id, debit=Decimal("0"), credit=amount),
            ],
        ), reading.recorded_by or 0)
    except Exception:
        logger.error(
            "_post_utility_expense_journal فشل — قراءة #%s (%s) مبلغ %.2f — القيد يحتاج تسجيل يدوي",
            getattr(reading, 'id', '?'), getattr(reading, 'utility_type', '?'),
            float(amount), exc_info=True,
        )


def list_utility_readings(db, branch_id: int, utility_type: str | None = None, period: str | None = None):
    """period بصيغة YYYY-MM — بيفلتر على reading_date."""
    from app.modules.analytics.models import UtilityReading

    q = db.query(UtilityReading).filter(UtilityReading.branch_id == branch_id)
    if utility_type:
        q = q.filter(UtilityReading.utility_type == utility_type)
    if period:
        year, month = (int(x) for x in period.split("-"))
        q = q.filter(
            UtilityReading.reading_date >= date(year, month, 1),
            UtilityReading.reading_date < (date(year, month, 1) + timedelta(days=32)).replace(day=1),
        )
    return q.order_by(UtilityReading.reading_date.desc()).all()


def get_energy_kpis(db, branch_id: int, period: str) -> dict:
    """مؤشر الطاقة (تكلفة كيلوواط/نزيل) لشهر معيّن (period=YYYY-MM) — بيقسّم
    إجمالي تكلفة الكهرباء على إجمالي ليالي الإشغال في نفس الشهر (من
    DailyStats.occupied_rooms، كـ proxy لعدد النزلاء لعدم وجود عمود مباشر
    لعدد الضيوف)."""
    from app.modules.analytics.models import DailyStats

    readings = list_utility_readings(db, branch_id, period=period)
    by_type: dict[str, Decimal] = {}
    for r in readings:
        by_type.setdefault(r.utility_type, Decimal("0"))
        by_type[r.utility_type] += r.total_cost

    year, month = (int(x) for x in period.split("-"))
    stats = db.query(DailyStats).filter(
        DailyStats.branch_id == branch_id,
        DailyStats.stat_date >= date(year, month, 1),
        DailyStats.stat_date < (date(year, month, 1) + timedelta(days=32)).replace(day=1),
    ).all()
    guest_nights = sum(s.occupied_rooms for s in stats) or 0

    electricity_cost = by_type.get("electricity", Decimal("0"))
    cost_per_guest = (
        (electricity_cost / guest_nights).quantize(Decimal("0.01"))
        if guest_nights > 0 else None
    )

    return {
        "period": period,
        "by_type": {k: float(v) for k, v in by_type.items()},
        "total_cost": float(sum(by_type.values())),
        "guest_nights": guest_nights,
        "electricity_cost_per_guest_night": float(cost_per_guest) if cost_per_guest is not None else None,
    }


def get_energy_trend(db, branch_id: int, end_period: str, months: int = 24) -> list[dict]:
    """wagdy.md #18: كانت شاشة المرافق بتعرض لقطة شهر واحد بس — مفيش اتجاه
    شهري ولا مقارنة بالسنة السابقة. بيرجّع `months` شهر متتالي (افتراضيًا 24
    — سنة حالية + سنة سابقة، عشان الفرونت إند يقدر يعرض المقارنة السنوية من
    نفس الرد بدون طلب تاني) بترتيب زمني تصاعدي، كل شهر بنفس شكل
    get_energy_kpis بالظبط (نفس الاستعلام، مُكرَّر لكل شهر — الشاشة دي إدارية
    مش عالية التردد، فمفيش داعي لتحسين أداء إضافي)."""
    year, month = (int(x) for x in end_period.split("-"))
    periods: list[str] = []
    for i in range(months - 1, -1, -1):
        y, m = year, month - i
        while m <= 0:
            m += 12
            y -= 1
        periods.append(f"{y:04d}-{m:02d}")
    return [get_energy_kpis(db, branch_id, p) for p in periods]


def generate_energy_trend_excel(db, branch_id: int, end_period: str, months: int = 24) -> bytes:
    """تصدير Excel لاتجاه تكلفة المرافق (wagdy.md #18)."""
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    trend = get_energy_trend(db, branch_id, end_period, months)
    utility_types = sorted({k for row in trend for k in row["by_type"].keys()})

    rows = [
        [
            row["period"],
            *[row["by_type"].get(t, 0) for t in utility_types],
            row["total_cost"], row["guest_nights"],
            row["electricity_cost_per_guest_night"] if row["electricity_cost_per_guest_night"] is not None else "—",
        ]
        for row in trend
    ]

    return builder.excel(
        sheets=[{
            "name": "اتجاه تكلفة المرافق",
            "headers": ["الشهر", *[k for k in utility_types], "إجمالي التكلفة",
                        "ليالي الإشغال", "تكلفة الكهرباء/ليلة نزيل"],
            "rows": rows,
            "col_types": ["text", *(["currency"] * len(utility_types)), "currency", "number", "currency"],
            "summary": {"عدد الأشهر": len(trend)},
        }],
        title=f"اتجاه تكلفة المرافق — حتى {end_period}",
    )


# ── Guest Feedback per-category insights ("GSS + per-category insights") ──
# Task B audit: ReviewCategory بيتسجّل فعلاً في submit_review() أعلاه، بس
# مفيش أي مكان في النظام كان بيقرأه أو يجمّعه — البيانات موجودة، العرض ناقص.

def get_review_category_insights(db, branch_id: int) -> dict:
    from app.modules.analytics.models import GuestReview, ReviewCategory

    reviews = db.query(GuestReview).filter(
        GuestReview.branch_id == branch_id,
        GuestReview.is_published.is_(True),
    ).all()
    overall_avg = (
        round(sum(r.overall_rating for r in reviews) / len(reviews), 2) if reviews else None
    )

    review_ids = [r.id for r in reviews]
    breakdown: dict[str, list[int]] = {}
    if review_ids:
        rows = db.query(ReviewCategory).filter(ReviewCategory.review_id.in_(review_ids)).all()
        for row in rows:
            breakdown.setdefault(row.category, []).append(row.rating)

    category_breakdown = [
        {"category": cat, "avg_rating": round(sum(ratings) / len(ratings), 2), "count": len(ratings)}
        for cat, ratings in sorted(breakdown.items())
    ]

    return {
        "overall_avg": overall_avg,
        "gss_score": overall_avg,
        "review_count": len(reviews),
        "category_breakdown": category_breakdown,
    }
