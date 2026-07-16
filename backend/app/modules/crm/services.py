"""app/modules/crm/services.py — Business logic"""
from __future__ import annotations

import logging

from datetime import date

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.core.config import settings
from app.resort_os.timezone_utils import local_today

from decimal import Decimal
from typing import Optional

from app.modules.crm import crud
from app.modules.crm.models import Activity, Campaign, Customer, CustomerGroup, CustomerInteraction, Lead, Opportunity
from app.modules.crm.schemas import (
    ActivityCreate, ActivityUpdate,
    BlacklistRequest,
    CampaignCreate, CampaignUpdate,
    CustomerCreate, CustomerGroupCreate, CustomerGroupUpdate, CustomerUpdate,
    InteractionCreate,
    LeadConvertRequest, LeadCreate, LeadStageUpdate,
    LoyaltyAdjustRequest, LoyaltyProgramCreate, LoyaltyProgramUpdate, LoyaltyRedeemRequest,
    OpportunityCreate, OpportunityUpdate,
)


# ── CustomerGroup (standing discount) ───────────────────────────────────

def get_customer_group_or_404(db: Session, group_id: int) -> CustomerGroup:
    g = crud.get_customer_group(db, group_id)
    if not g:
        raise ValueError(f"مجموعة العملاء {group_id} غير موجودة")
    return g


def create_customer_group(db: Session, data: CustomerGroupCreate) -> CustomerGroup:
    obj = crud.create_customer_group(db, data)
    db.commit()
    db.refresh(obj)
    return obj


def update_customer_group(db: Session, group_id: int, data: CustomerGroupUpdate) -> CustomerGroup:
    group = get_customer_group_or_404(db, group_id)
    obj = crud.update_customer_group(db, group, data)
    db.commit()
    db.refresh(obj)
    return obj


def assign_customer_group(db: Session, customer_id: int, customer_group_id: Optional[int]) -> Customer:
    customer = get_customer_or_404(db, customer_id)
    if customer_group_id is not None:
        group = get_customer_group_or_404(db, customer_group_id)
        if group.branch_id != customer.branch_id:
            raise ValueError("مجموعة العملاء المحدّدة لا تتبع نفس فرع العميل")
    obj = crud.assign_customer_group(db, customer, customer_group_id)
    db.commit()
    db.refresh(obj)
    return obj


def get_customer_group_discount_percentage(db: Session, customer_id: Optional[int]) -> Decimal:
    """نسبة الخصم الدائم (standing discount) للعميل حسب مجموعته — صفر لو
    العميل من غير مجموعة، أو مجموعته موقوفة (is_active=False). دالة قراءة
    نقية بتُستدعى من dining/beach.services وقت حساب خصم الطلب — مش بتعمل
    أي كتابة، فآمنة تُنادى من أي مسار من غير قلق على transaction state."""
    if not customer_id:
        return Decimal("0")
    customer = crud.get_customer(db, customer_id)
    if not customer or not customer.customer_group_id:
        return Decimal("0")
    group = crud.get_customer_group(db, customer.customer_group_id)
    if not group or not group.is_active:
        return Decimal("0")
    return group.discount_percentage


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


# ── Loyalty Program Services ─────────────────────────────────────────────────

def get_or_create_loyalty_program(db: Session, branch_id: int) -> "LoyaltyProgram | None":
    """يجيب برنامج النقاط للفرع. لو مش موجود يرجع None (مش نشط بعد)."""
    from app.modules.crm.models import LoyaltyProgram  # noqa: PLC0415
    return crud.get_loyalty_program(db, branch_id)


def setup_loyalty_program(db: Session, data: LoyaltyProgramCreate) -> "LoyaltyProgram":
    """ينشئ برنامج نقاط للفرع — مرة واحدة فقط."""
    existing = crud.get_loyalty_program(db, data.branch_id)
    if existing:
        raise ValueError("برنامج النقاط موجود بالفعل لهذا الفرع — استخدم التعديل")
    obj = crud.create_loyalty_program(db, data)
    db.commit()
    db.refresh(obj)
    return obj


def update_loyalty_program(db: Session, branch_id: int, data: LoyaltyProgramUpdate) -> "LoyaltyProgram":
    program = crud.get_loyalty_program(db, branch_id)
    if not program:
        raise ValueError("لا يوجد برنامج نقاط لهذا الفرع")
    obj = crud.update_loyalty_program(db, program, data)
    db.commit()
    db.refresh(obj)
    return obj


def get_customer_loyalty_account(db: Session, branch_id: int, customer_id: int) -> "LoyaltyAccount | None":
    """يجيب حساب النقاط للعميل مع الرصيد الحالي."""
    return crud.get_loyalty_account_by_customer(db, branch_id, customer_id)


def earn_loyalty_points(
    db: Session,
    branch_id: int,
    customer_id: int,
    paid_amount: "Decimal",
    source: str,
    source_id: int | None = None,
    reference: str | None = None,
    created_by: int | None = None,
) -> int:
    """يحسب النقاط المكتسبة من مبلغ الدفع ويضيفها للحساب.
    يرجع عدد النقاط المضافة (0 لو البرنامج مش نشط أو مش موجود)."""
    program = crud.get_loyalty_program(db, branch_id)
    if not program or not program.is_active:
        return 0
    if paid_amount <= 0:
        return 0

    points = int(paid_amount / program.earn_rate)
    if points <= 0:
        return 0

    account = crud.get_or_create_loyalty_account(db, program, customer_id)
    if account.is_frozen:
        return 0

    crud.earn_points(db, account, points, source, source_id, reference, created_by)
    db.commit()
    return points


def redeem_loyalty_points(
    db: Session,
    data: LoyaltyRedeemRequest,
    created_by: int | None = None,
) -> "LoyaltyRedeemResponse":
    """يسترد نقاط عميل ويرجع قيمة الخصم.
    تتحقق من: البرنامج نشط، رصيد كافي، حد الاسترداد الأقصى من الفاتورة."""
    from app.modules.crm.schemas import LoyaltyRedeemResponse  # noqa: PLC0415

    program = crud.get_loyalty_program(db, data.branch_id)
    if not program or not program.is_active:
        raise ValueError("برنامج النقاط غير مفعّل لهذا الفرع")

    account = crud.get_loyalty_account_by_customer(db, data.branch_id, data.customer_id)
    if not account:
        raise ValueError("العميل لا يملك حساب نقاط")
    if account.is_frozen:
        raise ValueError("حساب النقاط مجمّد — تواصل مع الإدارة")
    if account.points < program.min_redeem:
        raise ValueError(f"الرصيد الحالي ({account.points} نقطة) أقل من الحد الأدنى للاسترداد ({program.min_redeem})")
    if account.points < data.points:
        raise ValueError(f"رصيد النقاط غير كافٍ ({account.points} متاح، {data.points} مطلوب)")

    discount = Decimal(data.points) * program.redeem_rate
    txn = crud.redeem_points(
        db, account, data.points,
        data.source, data.source_id,
        reference=f"استرداد {data.points} نقطة",
        created_by=created_by,
    )
    db.commit()

    return LoyaltyRedeemResponse(
        points_redeemed=data.points,
        discount_amount=discount,
        new_balance=account.points,
        transaction_id=txn.id,
    )


def adjust_loyalty_points(
    db: Session,
    data: LoyaltyAdjustRequest,
    created_by: int | None = None,
) -> "LoyaltyAccount":
    """تعديل يدوي على رصيد النقاط (مدير+ فقط)."""
    program = crud.get_loyalty_program(db, data.branch_id)
    if not program:
        raise ValueError("لا يوجد برنامج نقاط لهذا الفرع")

    account = crud.get_or_create_loyalty_account(db, program, data.customer_id)
    new_balance = account.points + data.points
    if new_balance < 0:
        raise ValueError(f"لا يمكن خصم {abs(data.points)} نقطة — الرصيد الحالي {account.points}")

    crud.adjust_points(db, account, data, created_by)
    db.commit()
    db.refresh(account)
    return account


def get_loyalty_transactions(db: Session, branch_id: int, customer_id: int, limit: int = 50) -> list:
    account = crud.get_loyalty_account_by_customer(db, branch_id, customer_id)
    if not account:
        return []
    return crud.list_loyalty_transactions(db, account.id, limit=limit)
