"""app/modules/crm/services.py — Business logic"""
from __future__ import annotations

import logging

from datetime import date

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.core.config import settings
from app.resort_os.timezone_utils import local_today

from app.modules.crm import crud
from app.modules.crm.models import Activity, Campaign, Customer, CustomerInteraction, Lead, Opportunity
from app.modules.crm.schemas import (
    ActivityCreate, ActivityUpdate,
    BlacklistRequest,
    CampaignCreate, CampaignUpdate,
    CustomerCreate, CustomerUpdate,
    InteractionCreate,
    LeadConvertRequest, LeadCreate, LeadStageUpdate,
    OpportunityCreate, OpportunityUpdate,
)


# ── Customer ──────────────────────────────────────────────────────────

def get_customer_or_404(db: Session, customer_id: int) -> Customer:
    c = crud.get_customer(db, customer_id)
    if not c:
        raise ValueError(f"العميل {customer_id} غير موجود")
    return c


def create_customer(db: Session, data: CustomerCreate) -> Customer:
    """⚠️ باج حقيقي كان هنا: مفيش أي تحقق من تكرار رقم الهاتف/الإيميل —
    الاستقبال يقدر يسجّل نفس العميل مرتين بالغلط، فيتقسم total_spent/
    visits_count على سجلين منفصلين بدل ما يتراكموا على عميل واحد (بالظبط
    نفس المشكلة اللي GuestProfile اتصمم من الأول عشان يتفاداها بـ
    UniqueConstraint(branch_id, phone))."""
    if data.phone:
        dup = crud.get_customer_by_phone(db, data.branch_id, data.phone)
        if dup:
            raise ValueError(f"يوجد عميل مسجّل بنفس رقم الهاتف بالفعل: {dup.full_name} (#{dup.id})")
    if data.email:
        dup = crud.get_customer_by_email(db, data.branch_id, data.email)
        if dup:
            raise ValueError(f"يوجد عميل مسجّل بنفس البريد الإلكتروني بالفعل: {dup.full_name} (#{dup.id})")
    obj = crud.create_customer(db, data)
    db.commit()
    db.refresh(obj)
    return obj


def update_customer(db: Session, customer_id: int, data: CustomerUpdate) -> Customer:
    customer = get_customer_or_404(db, customer_id)
    obj = crud.update_customer(db, customer, data)
    db.commit()
    db.refresh(obj)
    return obj


def record_customer_visit(db: Session, customer_id: int, amount, visit_date: date) -> None:
    """يُستدعى من موديولات تانية (مطعم/كافيه/شاطئ/PMS) عند إتمام دفع مرتبط
    بعميل CRM — بيحدّث total_spent/visits_count/last_visit. بيبتلع أي خطأ
    عمدًا (عميل محذوف مثلاً) عشان فشل تحديث إحصائية CRM ميمنعش إتمام الدفع
    الفعلي، نفس فلسفة post_simple_revenue_journal في finance."""
    try:
        customer = crud.get_customer(db, customer_id)
        if not customer:
            return
        crud.update_customer_stats(db, customer, amount, visit_date)
    except Exception:
        # إحصائيات CRM ثانوية — فشلها لا يوقف العملية الأصلية لكن نسجّل للمتابعة
        logger.warning(
            "record_customer_visit فشل — customer_id=%s amount=%s",
            customer_id, amount, exc_info=True,
        )


def blacklist_customer(db: Session, customer_id: int, req: BlacklistRequest) -> Customer:
    customer = get_customer_or_404(db, customer_id)
    if customer.blacklisted:
        raise ValueError("العميل مُدرج في القائمة السوداء مسبقاً")
    obj = crud.blacklist_customer(db, customer, req.reason)
    db.commit()
    db.refresh(obj)
    return obj


def unblacklist_customer(db: Session, customer_id: int) -> Customer:
    customer = get_customer_or_404(db, customer_id)
    if not customer.blacklisted:
        raise ValueError("العميل ليس في القائمة السوداء")
    obj = crud.unblacklist_customer(db, customer)
    db.commit()
    db.refresh(obj)
    return obj


# ── Interaction ───────────────────────────────────────────────────────

def log_interaction(db: Session, data: InteractionCreate, handled_by: int) -> CustomerInteraction:
    get_customer_or_404(db, data.customer_id)
    obj = crud.create_interaction(db, data, handled_by)
    db.commit()
    db.refresh(obj)
    return obj


# ── Opportunity ───────────────────────────────────────────────────────

def get_opportunity_or_404(db: Session, opp_id: int) -> Opportunity:
    opp = crud.get_opportunity(db, opp_id)
    if not opp:
        raise ValueError(f"الفرصة {opp_id} غير موجودة")
    return opp


def create_opportunity(db: Session, data: OpportunityCreate) -> Opportunity:
    get_customer_or_404(db, data.customer_id)
    obj = crud.create_opportunity(db, data)
    db.commit()
    db.refresh(obj)
    return obj


def update_opportunity(db: Session, opp_id: int, data: OpportunityUpdate) -> Opportunity:
    opp = get_opportunity_or_404(db, opp_id)
    if opp.stage in ("won", "lost"):
        raise ValueError("لا يمكن تعديل فرصة مغلقة")
    if data.stage == "lost" and not data.lost_reason:
        raise ValueError("يجب تحديد سبب الخسارة")
    obj = crud.update_opportunity(db, opp, data)
    db.commit()
    db.refresh(obj)
    return obj


# ── Activity ──────────────────────────────────────────────────────────

def get_activity_or_404(db: Session, activity_id: int) -> Activity:
    a = crud.get_activity(db, activity_id)
    if not a:
        raise ValueError(f"النشاط {activity_id} غير موجود")
    return a


def create_activity(db: Session, data: ActivityCreate) -> Activity:
    get_customer_or_404(db, data.customer_id)
    obj = crud.create_activity(db, data)
    db.commit()
    db.refresh(obj)
    return obj


def update_activity(db: Session, activity_id: int, data: ActivityUpdate) -> Activity:
    activity = get_activity_or_404(db, activity_id)
    if activity.status in ("done", "cancelled"):
        raise ValueError("لا يمكن تعديل نشاط منتهٍ أو ملغى")
    obj = crud.update_activity(db, activity, data)
    db.commit()
    db.refresh(obj)
    return obj


# ── Campaign ──────────────────────────────────────────────────────────
# ملاحظة تصميم: leads_generated و revenue_attributed بيتحدّثوا يدويًا من
# مسؤول التسويق (عبر PATCH) — مش auto-attribution آلي مربوط بـ Lead/Booking.
# سبب القرار: مفيش FK فعلي بين Campaign وLead/Booking في الـ schema الحالي
# (Lead.source مربوط بـ LeadSource مش Campaign)، فربط تلقائي حقيقي هيحتاج
# migration جديدة (عمود campaign_id على Lead + أي جدول orders/bookings تاني)
# ده تغيير schema أكبر من نطاق الطلب الحالي. التحديث اليدوي ده هو نفس الأسلوب
# المُستخدم فعليًا في فنادق حقيقية صغيرة/متوسطة (مدير التسويق بيراجع الحملة
# أسبوعيًا ويحدّث الأرقام من تقارير الحجز/المبيعات) — MVP واقعي وكافي الآن.
# لو ظهرت حاجة تشغيلية حقيقية لاحقًا لربط تلقائي، الأساس (schema + service)
# جاهز يستوعب حقل campaign_id على Lead من غير أي تعديل هنا.

def get_campaign_or_404(db: Session, campaign_id: int) -> Campaign:
    c = crud.get_campaign(db, campaign_id)
    if not c:
        raise ValueError(f"الحملة {campaign_id} غير موجودة")
    return c


def _validate_date_range(start_date, end_date) -> None:
    if end_date < start_date:
        raise ValueError("تاريخ نهاية الحملة يجب أن يكون بعد أو يساوي تاريخ البداية")


def create_campaign(db: Session, data: CampaignCreate, created_by: int) -> Campaign:
    _validate_date_range(data.start_date, data.end_date)
    obj = crud.create_campaign(db, data, created_by)
    db.commit()
    db.refresh(obj)
    return obj


def update_campaign(db: Session, campaign_id: int, data: CampaignUpdate) -> Campaign:
    campaign = get_campaign_or_404(db, campaign_id)
    new_start = data.start_date if data.start_date is not None else campaign.start_date
    new_end = data.end_date if data.end_date is not None else campaign.end_date
    _validate_date_range(new_start, new_end)
    obj = crud.update_campaign(db, campaign, data)
    db.commit()
    db.refresh(obj)
    return obj


# ── Lead ──────────────────────────────────────────────────────────────

def get_lead_or_404(db: Session, lead_id: int) -> Lead:
    lead = crud.get_lead(db, lead_id)
    if not lead:
        raise ValueError(f"العميل المحتمل {lead_id} غير موجود")
    return lead


def create_lead(db: Session, data: LeadCreate) -> Lead:
    return crud.create_lead(db, data.model_dump())


def update_lead_stage(db: Session, lead_id: int, data: LeadStageUpdate) -> Lead:
    """يتقدّم بالـ lead في الـ pipeline: new → contacted → qualified → proposal
    → won/lost. won/lost نهائيان (زي Opportunity.closed_at)."""
    from datetime import datetime as _dt  # noqa: PLC0415

    lead = get_lead_or_404(db, lead_id)
    if lead.stage in ("won", "lost"):
        raise ValueError(f"الـ lead في حالة نهائية '{lead.stage}' ولا يمكن تعديله")

    # ⚠️ باج حقيقي كان هنا: Lead.lost_reason كان اختياريًا فعليًا (على عكس
    # Opportunity.update_opportunity اللي بيرفض "lost" من غير سبب) — يعني
    # مدير الـ CRM كان يقدر يقفل عميل محتمل بحالة "خسارة" من غير أي تفسير،
    # فتقرير "ليه بنخسر عملاء محتملين" كان ممكن يطلع فاضي تمامًا لمعظم السجلات.
    if data.stage == "lost" and not data.lost_reason:
        raise ValueError("يجب تحديد سبب الخسارة")

    update_data: dict = {"stage": data.stage}
    if data.stage == "won":
        update_data["won_at"] = _dt.utcnow()
    elif data.stage == "lost":
        update_data["lost_at"] = _dt.utcnow()
        update_data["lost_reason"] = data.lost_reason

    return crud.update_lead(db, lead, update_data)


def update_lead_details(db: Session, lead_id: int, data) -> Lead:
    """يعدّل بيانات الـ lead الأساسية (مش الـ stage — ده من update_lead_stage).
    ممنوع تعديل lead في حالة نهائية (won/lost)، زي نفس القاعدة المطبّقة على
    الـ stage وعلى Opportunity/Activity."""
    lead = get_lead_or_404(db, lead_id)
    if lead.stage in ("won", "lost"):
        raise ValueError(f"الـ lead في حالة نهائية '{lead.stage}' ولا يمكن تعديله")
    update_data = data.model_dump(exclude_unset=True)
    return crud.update_lead(db, lead, update_data)


def convert_lead_to_booking(db: Session, lead_id: int, data: LeadConvertRequest) -> tuple[Lead, "object"]:
    """wagdy.md C-03 — يحوّل lead لحجز PMS حقيقي بضغطة واحدة، بدل ما يضطر
    الاستقبال ينسخ اسم/هاتف/إيميل الـ lead يدويًا في شاشة حجز منفصلة.
    البيانات اللي مش موجودة على الـ lead نفسه (الغرف/التواريخ) بتيجي من
    LeadConvertRequest. بيستخدم pms.services.create_booking الموجود فعلاً —
    نفس نمط الاستدعاء المتقاطع بين الموديولات المستخدم في
    restaurant/beach.services (راجع record_customer_visit)."""
    from app.modules.pms.schemas import BookingCreate  # noqa: PLC0415
    from app.modules.pms.services import create_booking as pms_create_booking  # noqa: PLC0415

    lead = get_lead_or_404(db, lead_id)
    if lead.stage in ("won", "lost"):
        raise ValueError(f"الـ lead في حالة نهائية '{lead.stage}' ولا يمكن تحويله لحجز")

    booking_data = BookingCreate(
        branch_id=lead.branch_id,
        guest_name=lead.full_name,
        guest_phone=lead.phone,
        guest_email=lead.email,
        check_in=data.check_in,
        check_out=data.check_out,
        adults=data.adults,
        children=data.children,
        source="direct",
        room_ids=data.room_ids,
        notes=data.notes,
        rate_plan_id=data.rate_plan_id,
    )
    # ⚠️ pms.services.create_booking بيعمل commit() داخلي (نقطة دخول أساسية
    # مستخدمة من الراوتر بتاعها مباشرة) — تحديث الـ lead تحت بيتعمله commit
    # منفصل. لو فشل تحديث الـ lead بعد نجاح الحجز، هيفضل حجز حقيقي من غير
    # ربط lead.booking_id (نادر، وقابل للتصحيح يدويًا)، أفضل من عكس حجز
    # ناجح فعليًا.
    booking = pms_create_booking(db, booking_data)

    from datetime import datetime as _dt  # noqa: PLC0415
    lead.stage = "won"
    lead.won_at = _dt.utcnow()
    lead.booking_id = booking.id
    db.commit()
    db.refresh(lead)
    return lead, booking


def get_overdue_activities(db: Session, branch_id: int) -> list[Activity]:
    """يُستخدم من Celery لإرسال تذكيرات.
    #tz-fix: local_today بدل date.today() — باج التوقيت الموثّق في timezone_utils.py:
    Celery workers بتشتغل بتوقيت UTC، فـ date.today() كان بيحسب "اليوم" من UTC
    مش من توقيت المنتجع، يعني نشاط مفروض يتذكّر كل يوم الساعة 9 صباحًا (Cairo)
    كان ممكن يتأخر أو يتقدم بـ 3 ساعات."""
    today = local_today(settings.TIMEZONE)
    items, _ = crud.list_activities(
        db, branch_id,
        status="pending",
        due_before=today,
        limit=500,
    )
    return items
