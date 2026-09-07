"""app/modules/timeshare/_services/calendar_availability.py — 52-week ISO
calendar, available-weeks-for-sale, unit availability map, upcoming visits."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.modules.timeshare import crud


def get_calendar(db: Session, branch_id: int, year: Optional[int] = None) -> dict:
    """تقويم 52 أسبوع ISO — كل أسبوع وعقوده وزياراته الفعلية.

    المصادر التي تُبنى منها بيانات كل أسبوع:
    ① عقود ثابتة (week_number محدد) — النافذة محسوبة رياضياً من timeshare_engine.
    ② زيارات فعلية من جدول timeshare_visits (سواء لعقود ثابتة أو عائمة) —
       check_in.isocalendar()[1] يحدّد الأسبوع الفعلي.

    يتم التمييز في الـ response بـ `source: "contract" | "visit"`:
    - `source=contract` → نافذة محسوبة (عقد ثابت لم يُجدَّل بعد بزيارة فعلية)
    - `source=visit`    → زيارة مسجّلة فعلاً في قاعدة البيانات
    """
    from datetime import date as _date, timedelta as _timedelta  # noqa: PLC0415

    from app.core.config import settings  # noqa: PLC0415
    from app.resort_os.timeshare_engine import calculate_visit_window  # noqa: PLC0415
    from app.resort_os.timezone_utils import business_today  # noqa: PLC0415

    today = business_today(settings.TIMEZONE)
    year = year or today.year

    MONTH_AR = ["يناير", "فبراير", "مارس", "إبريل", "مايو", "يونيو",
                "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
    cur_week = today.isocalendar()[1] if today.year == year else -1

    week_map: dict[int, list[dict]] = {}

    # ① عقود ثابتة — النافذة المحسوبة رياضياً
    for c in crud.list_contracts_with_week(db, branch_id):
        window = calculate_visit_window(c.week_number, c.nights_per_year, year, today)
        if not window:
            continue
        week_map.setdefault(c.week_number, []).append({
            "id": c.id, "contract_number": c.contract_number,
            "customer_name": c.customer_name, "customer_phone": c.customer_phone,
            "room_type": c.room_type, "season": c.season,
            "rci_included": c.rci_included, "nights_per_year": c.nights_per_year,
            "visit_start": window.visit_start.isoformat(), "visit_end": window.visit_end.isoformat(),
            "booking_frozen": c.booking_frozen,
            "source": "contract",
            "visit_id": None,
            "visit_status": None,
        })

    # ② زيارات فعلية — تُضاف بجانب/بدل النافذة المحسوبة (المستخدم يرى كلاهما)
    for v in crud.list_visits_for_calendar(db, branch_id, year):
        week_num = v.check_in.isocalendar()[1]
        contract = v.contract  # lazy="select" — محمّل عند الوصول (OK: حجم صغير)
        if contract is None:
            continue
        week_map.setdefault(week_num, []).append({
            "id": contract.id, "contract_number": contract.contract_number,
            "customer_name": contract.customer_name, "customer_phone": contract.customer_phone,
            "room_type": contract.room_type, "season": contract.season,
            "rci_included": contract.rci_included, "nights_per_year": contract.nights_per_year,
            "visit_start": v.check_in.isoformat(), "visit_end": v.check_out.isoformat(),
            "booking_frozen": contract.booking_frozen,
            "source": "visit",
            "visit_id": v.id,
            "visit_status": v.status,
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


def get_available_weeks(
    db: Session, branch_id: int, year: int, room_type: Optional[str] = None,
) -> dict:
    """الأسابيع المتاحة للبيع في سنة بعينها — لفريق المبيعات.

    المنطق: (52 أسبوع ISO) - (أسابيع محجوزة بعقود ثابتة) - (أسابيع محجوزة
    بزيارات فعلية من عقود عائمة).
    يدعم فلتر room_type اختياري (Studio/Chalet)."""
    from datetime import date as _date, timedelta as _timedelta  # noqa: PLC0415

    booked = crud.get_booked_week_numbers(db, branch_id, year, room_type)

    available_weeks: list[dict] = []
    for w in range(1, 53):
        try:
            ws = _date.fromisocalendar(year, w, 1)
        except ValueError:
            continue
        if w not in booked:
            available_weeks.append({
                "week": w,
                "start_date": ws.isoformat(),
                "end_date": (ws + _timedelta(days=6)).isoformat(),
            })

    return {
        "year": year,
        "room_type": room_type,
        "total_available": len(available_weeks),
        "total_booked": 52 - len(available_weeks),
        "available_weeks": available_weeks,
    }


def get_units_availability(
    db: Session, branch_id: int, unit_type: str, check_in, check_out,
) -> list[dict]:
    """خريطة الوحدات لفترة معيّنة — كل وحدة من النوع المطلوب مع is_available
    (مش تحت صيانة ومفيش زيارة scheduled/active متقاطعة معاها في الفترة دي).
    2026-08-16: كان مفيش أي طريقة للموظف يشوف/يختار وحدة فعلية وقت تأكيد
    زيارة — الاختيار كان أوتوماتيكي بالكامل (find_available_unit). الشاشة
    دي بتوفّر البيانات لخريطة بصرية حقيقية بدل التخصيص الأعمى."""
    units = crud.list_units(db, branch_id, unit_type=unit_type)
    return [
        {
            "id": unit.id,
            "unit_number": unit.unit_number,
            "unit_type": unit.unit_type,
            "status": unit.status,
            "is_available": (
                unit.status != "maintenance"
                and not crud.has_overlapping_visit(db, unit.id, check_in, check_out)
            ),
        }
        for unit in units
    ]


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
        # مفيش حد أدنى صفر على days_until — زيارة جارية دلوقتي (بدأت قبل
        # النهاردة، لسه ما خلصتش) لازم تفضل ظاهرة برضه، راجع تعليق
        # timeshare_engine.find_next_visit/get_upcoming_visits.
        if visit and visit.days_until <= days:
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
