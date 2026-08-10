"""HIST-01 — مولّد بيانات Hub/CRM التاريخية ليوليو 2026 (OPS-DATA-02 §10.3).
بيستخدم services/crud الحقيقية بس (hub.services.create_online_booking/
confirm_booking/cancel_booking، crm.services.create_customer/create_opportunity)
— صفر SQL مباشر لأي جدول عدا `ContactForm` نفسها (راجع التبرير تحت).

⚠️ قرارات نطاق موثّقة صراحةً:
- `ContactForm` بتتنشأ هنا بـORM مباشر بدل `hub.public_contact.
  submit_public_contact()` عمدًا: الدالة العامة دي مصمّمة لحركة زوار غير
  موثوقين حقيقية — بتعمل rate limiting (`_enforce_abuse_limits`) وidempotency
  hashing وبتعمل `db.commit()` داخلي بنفسها. مولّد HIST-01 لازم يعمل flush
  بس (الـ CLI هو مالك الـtransaction الشاملة، راجع operational_history_
  seed.py) — نداء دالة بتعمل commit داخلي هيكسر عقد dry-run بالكامل.
  بدل ما نكرر منطق الحقل-بحقل يدويًا، بنستخدم `_create_marketing_lead()`
  الحقيقية (نفس الدالة اللي submit_public_contact بتنادّيها لما
  marketing_consent=True) عشان تحويل الفورم لـLead يفضل نفس السلوك
  المحاسبي/الـCRM بالظبط بدون تكرار منطق.
- تأكيد "confirmed→PMS" لطلبين بيدور فعليًا على غرفة متاحة حقيقية
  (get_available_rooms ضد حالة الداتابيز اللحظية وقت التشغيل، بالظبط
  نفس اللي hub.services._confirm_room_type_leg بيعمله داخليًا) بدل
  افتراض تواريخ فاضية — يشتغل صح بغض النظر عن ترتيب تسجيل الموديول.
  مسجَّل بعد `dining_beach` عمدًا (بعد ما `pms_bookings` يخلص حجزه) عشان
  الـpacker بتاع pms_bookings (occupied dict محلي فاضي من الأول، مش
  بيقرأ الداتابيز) میکونش عرضة لتعارض حجز حقيقي كان هيحصل لو Hub حجز
  قبله."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.operational_history_seed import ScenarioContext

# (guest_name, guest_phone, source, requested_date_offset, has_stay_dates, outcome)
# outcome: "confirmed" | "cancelled" | "pending"
_REQUESTS: tuple[tuple[str, str, str, int, bool, str], ...] = (
    ("أحمد فتحي - HIST", "01011110001", "website", 1, True, "confirmed"),
    ("منى إبراهيم - HIST", "01011110002", "whatsapp", 3, True, "confirmed"),
    ("سامي عادل - HIST", "01011110003", "website", 5, True, "cancelled"),
    ("هبة الشريف - HIST", "01011110004", "instagram", 7, False, "cancelled"),
    ("كريم يوسف - HIST", "01011110005", "whatsapp", 9, True, "cancelled"),
    ("ريهام عزت - HIST", "01011110006", "website", 11, True, "pending"),
    ("طارق منصور - HIST", "01011110007", "whatsapp", 13, False, "pending"),
    ("دينا سالم - HIST", "01011110008", "website", 15, True, "pending"),
    ("عمر الحسيني - HIST", "01011110009", "instagram", 17, True, "pending"),
    ("ياسمين فوزي - HIST", "01011110010", "website", 19, False, "pending"),
    ("محمود جلال - HIST", "01011110011", "website", 21, True, "pending"),
    ("نور الدين حامد - HIST", "01011110012", "whatsapp", 23, True, "pending"),
)

_CONTACT_FORMS: tuple[tuple[str, str, str, str, bool], ...] = (
    # (full_name, phone, subject, purpose, marketing_consent)
    ("أحمد فتحي - HIST", "01011110001", "استفسار عن باقة الغطس", "activity_request", True),
    ("سلمى وهبة - HIST", "01099990002", "طلب عرض سعر لحفل خاص", "other", True),
    ("وليد عاشور - HIST", "01099990003", "شكوى بسيطة عن التنظيف", "general_inquiry", False),
    ("ماجدة صبري - HIST", "01099990004", "استفسار عن مواعيد الشاطئ", "beach_service", False),
    ("رامي فؤاد - HIST", "01099990005", "طلب حجز سبا", "spa_request", False),
)


def _find_available_room_and_dates(
    db: "Session", branch_id: int, room_type_id: int, month_start: date, days_in_month: int,
) -> tuple[int, date, date] | None:
    """أول غرفة/تاريخ فعليًا فاضيين ضد الداتابيز الحقيقية (get_available_rooms)
    — مش تخمين، بالظبط نفس الاستعلام اللي confirm_booking الحقيقي بيستخدمه."""
    from app.modules.pms.crud import get_available_rooms  # noqa: PLC0415

    for offset in range(days_in_month - 1):
        check_in = month_start + timedelta(days=offset)
        check_out = check_in + timedelta(days=1)
        available = get_available_rooms(
            db, branch_id=branch_id, check_in=check_in, check_out=check_out,
            room_type_id=room_type_id,
        )
        if available:
            return available[0].id, check_in, check_out
    return None


def generate(db: "Session", ctx: "ScenarioContext") -> dict:
    from app.modules.crm import services as crm_services
    from app.modules.crm.crud import get_customer_by_phone
    from app.modules.crm.schemas import CustomerCreate, OpportunityCreate
    from app.modules.hub import services as hub_services
    from app.modules.hub.models import ContactForm
    from app.modules.hub.public_contact import _create_marketing_lead
    from app.modules.hub.schemas import OnlineBookingCreate
    from app.modules.pms.models import RoomType

    branch_id = ctx.branch_id
    month_start = date(ctx.period_year, ctx.period_month, 1)
    days_in_month = 31 if ctx.period_month == 7 else (
        date(ctx.period_year, ctx.period_month % 12 + 1, 1) - timedelta(days=1)
    ).day

    room_type = (
        db.query(RoomType).filter(RoomType.branch_id == branch_id).order_by(RoomType.id).first()
    )
    if not room_type:
        raise RuntimeError(f"hub HIST-01: مفيش أي RoomType للفرع {branch_id}")

    counts = {"confirmed": 0, "confirmed_with_pms": 0, "cancelled": 0, "pending": 0}
    for name, phone, source, offset, has_stay, outcome in _REQUESTS:
        requested_date = month_start + timedelta(days=offset)
        data = OnlineBookingCreate(
            branch_id=branch_id, guest_name=name, guest_phone=phone,
            guest_email=None, guests_count=2, requested_date=requested_date,
            check_in=requested_date if has_stay else None,
            check_out=requested_date + timedelta(days=2) if has_stay else None,
            adults=2, children=0, source=source,
            notes="HIST-01 synthetic Hub request",
        )
        booking = hub_services.create_online_booking(db, data)

        if outcome == "cancelled":
            hub_services.cancel_booking(db, booking.id)
            counts["cancelled"] += 1
            continue
        if outcome == "pending":
            counts["pending"] += 1
            continue

        # confirmed — بنلاقي غرفة/تاريخ متاحين فعليًا ونحدّث الطلب بيهم قبل
        # التأكيد (بدل ما نعتمد على requested_date العشوائي اللي فوق يكون
        # فاضي بالصدفة).
        found = _find_available_room_and_dates(db, branch_id, room_type.id, month_start, days_in_month)
        if found:
            _, real_check_in, real_check_out = found
            booking.check_in = real_check_in
            booking.check_out = real_check_out
            booking.room_type_id = room_type.id
            db.flush()
        confirmed = hub_services.confirm_booking(db, booking.id, confirmed_by=0)
        counts["confirmed"] += 1
        if confirmed.pms_booking_id:
            counts["confirmed_with_pms"] += 1

    # ── Contact forms — موافقة خدمة إلزامية، consent تسويقي محدود ────────
    now = datetime.utcnow()
    leads_created = 0
    dedup_customer_id: int | None = None
    for idx, (full_name, phone, subject, purpose, marketing_consent) in enumerate(_CONTACT_FORMS):
        form = ContactForm(
            branch_id=branch_id, full_name=full_name, phone=phone, email=None,
            subject=subject, message=f"{subject} — HIST-01 synthetic contact form.",
            source_page="/contact", source="public_website", purpose=purpose,
            language="ar", service_contact_authorized=True,
            service_disclosure_version="v1", service_contact_authorized_at=now,
            marketing_consent=marketing_consent,
            marketing_consent_version="v1" if marketing_consent else None,
            marketing_consent_at=now if marketing_consent else None,
            status="accepted",
            crm_sync_status="pending" if marketing_consent else "not_requested",
        )
        db.add(form)
        db.flush()

        if marketing_consent:
            lead = _create_marketing_lead(db, form, now)
            form.lead_id = lead.id
            form.crm_sync_status = "created"
            leads_created += 1
            db.flush()

            # نفس الهاتف زي أول طلب Hub — سيناريو ضيف حقيقي رجع تاني، بيثبت
            # عدم تكرار العميل بالهاتف (dedup) بدل إنشاء Customer مزدوج.
            if idx == 0:
                existing_customer = get_customer_by_phone(db, branch_id, phone)
                if existing_customer:
                    dedup_customer_id = existing_customer.id
                else:
                    customer = crm_services.create_customer(db, CustomerCreate(
                        branch_id=branch_id, full_name=full_name, phone=phone,
                        segment="regular", source="social_media",
                        notes="HIST-01 synthetic — created from marketing-consent contact form",
                    ))
                    dedup_customer_id = customer.id
                crm_services.create_opportunity(db, OpportunityCreate(
                    branch_id=branch_id, customer_id=dedup_customer_id,
                    title="اهتمام بباقة أنشطة بحرية — HIST-01",
                    product_type="other", expected_value=Decimal("5000.00"),
                    probability=30,
                ))

    db.commit()

    return {
        "counts": {
            "hub_requests_total": len(_REQUESTS),
            "hub_confirmed": counts["confirmed"],
            "hub_confirmed_with_pms_booking": counts["confirmed_with_pms"],
            "hub_cancelled": counts["cancelled"],
            "hub_pending": counts["pending"],
            "contact_forms": len(_CONTACT_FORMS),
            "marketing_leads_created": leads_created,
        },
        "totals": {},
    }
