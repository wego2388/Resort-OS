"""app/modules/timeshare/_services/visit_requests_support.py — owner-portal
visit requests (with peak-season fair-use rules) and support tickets."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.modules.timeshare import crud
from app.modules.timeshare.models import TimeshareContract, TimeshareSupportTicket, TimeshareVisitRequest
from app.modules.timeshare.schemas import (
    TimeshareSupportTicketCreate, TimeshareVisitCreate, TimeshareVisitRequestCreate,
)

from .contracts import get_contract_or_404
from .visits import create_visit

# ── قواعد الذروة (OPS-DATA-02 §8 نقطة 5) ─────────────────────────────

HOLIDAY_COOLDOWN_YEARS = 1
HOLIDAY_COOLDOWN_VERSION = "timeshare-holiday-cooldown-2026-08-10.v1"
# سياسة الـTrial المختارة (OPS-DATA-02 §18 قرار 7): مش فجوة 30 يوم — عقد
# استخدم أسبوعًا داخل موسم peak_kind=official_holiday في سنة موسم معيّنة
# لا يحصل على official holiday تاني في السنة التالية مباشرة؛ يقدر يقدّم
# تاني بعد سنة فاصلة واحدة. الصيف/الموسم العادي (peak_kind=regular) مش
# "عيد" ومعفى من القاعدة دي تمامًا (لسه خاضع لحد أسبوع الذروة الواحد سنويًا).


def _peak_event_years_for_contract(
    db: Session, contract: TimeshareContract, peak_kind: Optional[str] = None,
    include_pending: bool = False,
) -> set[int]:
    """السنوات اللي العقد ده استخدم فيها فعليًا أسبوع ذروة (من نوع
    peak_kind لو محدد، وإلا أي نوع) — بدون عدّ مزدوج بين الطلب المعتمد
    والزيارة الناتجة عنه (نفس الحدث؛ راجع OPS-DATA-02 §8 نقطة 6).

    include_pending=False (الافتراضي، مستخدَم لقاعدة عدم تتابع الأعياد
    عبر السنين): بس الاستخدام المؤكَّد فعليًا (approved) — طلب pending لسه
    ممكن يُرفض، مايستهلكش "سنة عيد" حقيقية.
    include_pending=True (لقاعدة الأسبوع الواحد في نفس السنة): يشمل
    pending كمان — عشان العميل ميقدرش يقدّم أكتر من طلب ذروة واحد لنفس
    السنة أصلًا، حتى لو ولا واحد اتراجع لسه (رفض فوري بدل ما ينتظر
    المراجعة اليدوية تكتشف التكرار)."""
    counted_visit_ids: set[int] = set()
    years: set[int] = set()
    pending_statuses = ("approved", "pending") if include_pending else ("approved",)

    for req in crud.list_visit_requests_for_contract(db, contract.id):
        if req.status not in pending_statuses:
            continue
        if req.visit_id:
            visit = crud.get_visit(db, req.visit_id)
            if not visit or visit.status == "cancelled":
                continue
            counted_visit_ids.add(visit.id)
            check_in, check_out = visit.check_in, visit.check_out
        else:
            check_in, check_out = req.preferred_start, req.preferred_end
        seasons = crud.get_overlapping_peak_seasons(db, contract.branch_id, check_in, check_out, peak_kind)
        if seasons:
            years.add(seasons[0].season_year)

    # زيارات اتعملت مباشرة (staff، مش من طلب عميل عبر البوابة) — عشان
    # مايتحسبوش مرتين لو أصلًا اتعدّوا فوق من خلال visit_id.
    for visit in crud.list_visits(db, contract.branch_id, contract_id=contract.id):
        if visit.id in counted_visit_ids or visit.status == "cancelled":
            continue
        seasons = crud.get_overlapping_peak_seasons(db, contract.branch_id, visit.check_in, visit.check_out, peak_kind)
        if seasons:
            years.add(seasons[0].season_year)

    return years


def _check_peak_rules(db: Session, contract: TimeshareContract, start: "date", end: "date") -> None:
    """يرفع ValueError واضح لو الطلب مخالف لقاعدة الذروة — بيتنادى من
    request_visit قبل إنشاء الصف (نفس نمط باقي تحققات request_visit
    المبكرة). مفيش أي تأثير لو الفترة المطلوبة مش ذروة أصلًا."""
    seasons = crud.get_overlapping_peak_seasons(db, contract.branch_id, start, end)
    if not seasons:
        return
    target_year = seasons[0].season_year

    # قاعدة: أسبوع ذروة واحد بس في السنة (أي نوع — عيد أو موسم عادي) —
    # include_pending=True عشان العميل ميقدرش يقدّم طلب تاني لنفس السنة
    # أصلًا، حتى لو الأول لسه مراجعة مديرش عليه.
    if target_year in _peak_event_years_for_contract(db, contract, include_pending=True):
        raise ValueError(
            f"تم استخدام حصة أسبوع الذروة لهذا العقد في سنة {target_year} — "
            "لا يُسمح بأكثر من أسبوع ذروة واحد في السنة لتحقيق تكافؤ الفرص بين جميع الأعضاء"
        )

    # قاعدة عدم تتابع الأعياد — بس لو الموسم المطلوب official_holiday؛
    # الصيف/الموسم العادي معفى تمامًا (راجع التعليق فوق HOLIDAY_COOLDOWN_YEARS)
    if any(s.peak_kind == "official_holiday" for s in seasons):
        holiday_years = _peak_event_years_for_contract(db, contract, peak_kind="official_holiday")
        for used_year in holiday_years:
            if 0 < (target_year - used_year) <= HOLIDAY_COOLDOWN_YEARS:
                raise ValueError(
                    f"العقد استخدم أسبوع عيد رسمي في سنة {used_year} — لا يُسمح بعيد رسمي آخر "
                    f"قبل سنة {used_year + HOLIDAY_COOLDOWN_YEARS + 1} (سنة فاصلة واحدة على الأقل، "
                    f"إعداد {HOLIDAY_COOLDOWN_VERSION})"
                )


def request_visit(db: Session, contract_id: int, data: TimeshareVisitRequestCreate) -> TimeshareVisitRequest:
    """طلب العميل نفسه — تحقق مبكر (عقد نشط، مش مجمَّد) عشان العميل ياخد
    رسالة واضحة فورًا بدل ما يقدّم طلب مصيره الرفض التلقائي عند المراجعة.

    OPS-DATA-02 §8 نقطة 1: terms_accepted/booking_rules_accepted بوليان
    مؤقت مش كافي كإثبات موافقة — data.terms_version/booking_rules_version
    (Literal مطابق للنسخة الحالية بالظبط، schemas.py) بيتخزنوا كلقطة دائمة
    على الصف نفسه (crud.create_visit_request) + AuditLog صريح هنا، عشان
    ثبوت "وافق على أي نص بالظبط ومتى" ميعتمدش على بوليان وحيد قابل للتفسير
    بعد سنين. لا يوجد user_id (العميل بيستخدم بوابة OTP، مش حساب staff).

    OPS-DATA-02 §8 نقطة 5: _check_peak_rules بتفحص أسبوع الذروة الواحد
    سنويًا + عدم تتابع الأعياد الرسمية قبل ما أي صف يتخزّن أصلًا."""
    contract = get_contract_or_404(db, contract_id)
    if data.preferred_end <= data.preferred_start:
        raise ValueError("تاريخ النهاية يجب أن يكون بعد تاريخ البداية")
    if contract.status in ("cancelled", "expired"):
        raise ValueError("هذا العقد غير نشط حاليًا — يرجى التواصل مع خدمة العملاء")
    if contract.booking_frozen:
        raise ValueError("الحجز مجمَّد حاليًا بسبب متأخرات على العقد — يرجى التواصل مع خدمة العملاء")
    _check_peak_rules(db, contract, data.preferred_start, data.preferred_end)
    req = crud.create_visit_request(db, contract, data)

    from app.modules.core import crud as core_crud  # noqa: PLC0415
    from app.modules.core.schemas import AuditLogCreate  # noqa: PLC0415
    import json  # noqa: PLC0415
    core_crud.create_audit_log(db, AuditLogCreate(
        user_id=None, branch_id=contract.branch_id,
        action="timeshare_visit_request_terms_accepted",
        entity_type="timeshare_visit_request", entity_id=req.id,
        new_data=json.dumps({
            "contract_id": contract.id, "contract_number": contract.contract_number,
            "terms_version": req.terms_version, "terms_accepted_at": req.terms_accepted_at.isoformat(),
            "booking_rules_version": req.booking_rules_version,
            "booking_rules_accepted_at": req.booking_rules_accepted_at.isoformat(),
        }, ensure_ascii=False, sort_keys=True),
        ip_address=None, user_agent=None,
    ))

    db.commit()
    db.refresh(req)
    return req


def approve_visit_request(
    db: Session, request_id: int, check_in, check_out, approved_by: int,
    unit_id: Optional[int] = None,
) -> TimeshareVisitRequest:
    """موافقة مدير — بيحدد التواريخ الفعلية بنفسه (مش بالضرورة نفس تفضيل
    العميل)، وبتمرّ بنفس visits.create_visit الموجودة حرفيًا — صفر تكرار
    لمنطق منع التعارض/التجميد/انتهاء العقد. unit_id: اختيار يدوي من خريطة
    الوحدات (2026-08-16) — لعقد عائم بس، create_visit بترفضه لعقد ثابت."""
    req = crud.get_visit_request(db, request_id)
    if not req:
        raise ValueError(f"طلب الزيارة {request_id} غير موجود")
    if req.status != "pending":
        raise ValueError(f"طلب الزيارة {request_id} تمت مراجعته بالفعل ({req.status})")

    visit = create_visit(db, TimeshareVisitCreate(
        branch_id=req.branch_id, contract_id=req.contract_id,
        check_in=check_in, check_out=check_out, notes=req.notes,
        unit_id=unit_id,
    ))
    req.status = "approved"
    req.reviewed_by = approved_by
    req.reviewed_at = datetime.now(timezone.utc)
    req.visit_id = visit.id
    db.commit()
    db.refresh(req)
    # العميل مالوش أي جلسة دائمة (بوابة OTP بس) — من غير واتساب، الطريقة
    # الوحيدة إنه يعرف إن طلبه اتوافق عليه هي إنه يرجع يعمل OTP تاني بنفسه.
    if req.contract.customer_phone:
        from app.core.kernel.whatsapp import send_whatsapp_message  # noqa: PLC0415

        send_whatsapp_message(
            req.contract.customer_phone,
            f"تمت الموافقة على طلب زيارتك في El Kheima Beach Resort ✅\n"
            f"من {check_in.isoformat()} إلى {check_out.isoformat()}\n"
            f"للتفاصيل، ادخل على بوابة عقدك.",
        )
    return req


def reject_visit_request(db: Session, request_id: int, reason: str, reviewed_by: int) -> TimeshareVisitRequest:
    req = crud.get_visit_request(db, request_id)
    if not req:
        raise ValueError(f"طلب الزيارة {request_id} غير موجود")
    if req.status != "pending":
        raise ValueError(f"طلب الزيارة {request_id} تمت مراجعته بالفعل ({req.status})")
    req.status = "rejected"
    req.reviewed_by = reviewed_by
    req.reviewed_at = datetime.now(timezone.utc)
    req.rejection_reason = reason
    db.commit()
    db.refresh(req)
    if req.contract.customer_phone:
        from app.core.kernel.whatsapp import send_whatsapp_message  # noqa: PLC0415

        send_whatsapp_message(
            req.contract.customer_phone,
            f"للأسف تعذّرت الموافقة على طلب زيارتك في El Kheima Beach Resort.\n"
            f"السبب: {reason}\n"
            f"للتواصل مع خدمة العملاء، افتح تذكرة دعم من بوابة عقدك.",
        )
    return req


def submit_support_ticket(
    db: Session, contract_id: int, data: TimeshareSupportTicketCreate,
) -> TimeshareSupportTicket:
    contract = get_contract_or_404(db, contract_id)
    ticket = crud.create_support_ticket(db, contract, data)
    db.commit()
    db.refresh(ticket)
    return ticket


def reply_to_ticket(
    db: Session, ticket_id: int, message: str,
    author_type: str, author_user_id: Optional[int] = None,
):
    ticket = crud.get_support_ticket(db, ticket_id)
    if not ticket:
        raise ValueError(f"تذكرة الدعم {ticket_id} غير موجودة")
    if ticket.status == "closed":
        raise ValueError("التذكرة مغلقة — لا يمكن الرد عليها")
    reply = crud.add_ticket_reply(db, ticket, message, author_type, author_user_id)
    # رد موظف على تذكرة "مفتوحة" جديدة يحوّلها "قيد المعالجة" تلقائيًا —
    # مؤشر بصري بسيط إنها اتشافت، من غير ما يحتاج الموظف يعدّل الحالة يدويًا
    # كل مرة يرد فيها.
    if author_type == "staff" and ticket.status == "open":
        ticket.status = "in_progress"
    db.commit()
    db.refresh(reply)
    # 2026-08-04: نفس الفجوة اللي في طلبات الزيارة — مفيش تنبيه في أي اتجاه.
    # رد الموظف لازم يوصل للعميل واتساب (مفيش جلسة دائمة يشوفها فيها)، ورد
    # العميل التاني (متابعة على تذكرة موجودة، مش أول رسالة) لازم يوصل
    # للموظف زي ما التذكرة الجديدة نفسها كانت بتوصّل بالفعل.
    if author_type == "staff" and ticket.contract.customer_phone:
        from app.core.kernel.whatsapp import send_whatsapp_message  # noqa: PLC0415

        send_whatsapp_message(
            ticket.contract.customer_phone,
            f"عندك رد جديد من خدمة العملاء على تذكرتك \"{ticket.subject}\" في El Kheima Beach Resort.\n"
            f"للاطلاع، ادخل على بوابة عقدك.",
        )
    return reply


def update_ticket_status(db: Session, ticket_id: int, new_status: str) -> TimeshareSupportTicket:
    ticket = crud.get_support_ticket(db, ticket_id)
    if not ticket:
        raise ValueError(f"تذكرة الدعم {ticket_id} غير موجودة")
    ticket.status = new_status
    if new_status in ("resolved", "closed"):
        ticket.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(ticket)
    return ticket
