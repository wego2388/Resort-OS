"""app/modules/crm/api/router.py"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import (
    DbDep, get_admin_user, get_booking_operator_user, get_crm_user,
    get_pos_customer_user, require_permission,
)
from app.modules.crm import crud, services
from app.modules.crm.schemas import (
    ActivityCreate, ActivityRead, ActivityUpdate,
    AssignCustomerGroupRequest,
    BlacklistRequest,
    CallNoteCreate, CallNoteRead,
    CampaignCreate, CampaignRead, CampaignUpdate,
    CustomerCreate, CustomerGroupCreate, CustomerGroupRead, CustomerGroupUpdate,
    CustomerRead, CustomerUpdate,
    GuestProfileRead,
    InteractionCreate, InteractionRead,
    LeadConvertRequest, LeadConvertResponse,
    LeadCreate, LeadRead, LeadSourceCreate, LeadSourceRead, LeadStageUpdate, LeadUpdate,
    LoyaltyAccountRead, LoyaltyAdjustRequest, LoyaltyProgramCreate, LoyaltyProgramRead,
    LoyaltyProgramUpdate, LoyaltyRedeemRequest, LoyaltyRedeemResponse, LoyaltyTransactionRead,
    OpportunityCreate, OpportunityRead, OpportunityUpdate,
)
from app.modules.core import services as core_services
from app.modules.core.schemas import PaginatedResponse

router = APIRouter(tags=["crm"])


def _assert_crm_branch(db, user, branch_id: int, action_desc: str) -> None:
    """Gate 4B-style branch isolation — كانت غايبة بالكامل من موديول CRM
    (اتكشف 2026-07-28، اتأكد بريبرو حي: كاشير فرع B كان يقدر يقرا/يعدّل
    عملاء/leads فرع A بمجرد تخمين الـid، حتى GET /crm/customers?branch_id=
    كان بيقبل أي branch_id من غير أي تحقق)."""
    try:
        core_services.assert_branch_access(db, user, branch_id, action_desc)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))


# ── Customer Groups (standing discount) ─────────────────────────────────
# نفس نمط /finance/discounts بالظبط (مرجع صريح): قراءة لمدير+، إنشاء/تعديل
# لـ admin+ فقط — تعيين مجموعة لعميل بيمنحه خصم دائم تلقائي على مبيعاته
# القادمة، فمفيش داعي يبقى مقيّد أوسع من إدارة الخصومات الشرطية نفسها.

@router.get("/crm/customer-groups", response_model=list[CustomerGroupRead])
def list_customer_groups(
    db: DbDep, user=Depends(get_crm_user),
    branch_id: int = Query(...), active_only: bool = Query(True),
):
    _assert_crm_branch(db, user, branch_id, "عرض مجموعات العملاء")
    return crud.list_customer_groups(db, branch_id, active_only)


@router.post("/crm/customer-groups", response_model=CustomerGroupRead,
             status_code=status.HTTP_201_CREATED)
def create_customer_group(data: CustomerGroupCreate, db: DbDep, user=Depends(get_admin_user)):
    _assert_crm_branch(db, user, data.branch_id, "إنشاء مجموعة عملاء")
    return services.create_customer_group(db, data)


@router.patch("/crm/customer-groups/{group_id}", response_model=CustomerGroupRead)
def update_customer_group(group_id: int, data: CustomerGroupUpdate, db: DbDep, user=Depends(get_admin_user)):
    group = crud.get_customer_group(db, group_id)
    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المجموعة غير موجودة")
    _assert_crm_branch(db, user, group.branch_id, "تعديل مجموعة عملاء")
    try:
        return services.update_customer_group(db, group_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ── Customers ─────────────────────────────────────────────────────────

@router.get("/crm/customers", response_model=PaginatedResponse)
def list_customers(
    db: DbDep,
    user=Depends(get_pos_customer_user),
    branch_id: int = Query(...),
    segment: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    blacklisted: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    _assert_crm_branch(db, user, branch_id, "عرض العملاء")
    items, total = crud.list_customers(db, branch_id, segment, search, blacklisted,
                                       skip=(page - 1) * size, limit=size)
    # تمكين الكاشير يشوف "العميل ده عنده خصم دائم X%" وقت الاختيار في POS،
    # مش بعد ما يحسب الإجمالي بس (راجع services.get_customer_group_
    # discount_percentage — مجموعة موقوفة = صفر خصم، فمفيش سبب نجيب غير
    # المجموعات النشطة هنا أصلًا).
    active_groups = {g.id: g for g in crud.list_customer_groups(db, branch_id, active_only=True)}
    read_items = []
    for c in items:
        read = CustomerRead.model_validate(c)
        group = active_groups.get(c.customer_group_id) if c.customer_group_id else None
        if group:
            read.group_name = group.name_ar or group.name
            read.group_discount_percentage = group.discount_percentage
        read_items.append(read)
    return PaginatedResponse(total=total, page=page, size=size, items=read_items)


@router.post("/crm/customers", response_model=CustomerRead,
             status_code=status.HTTP_201_CREATED)
def create_customer(data: CustomerCreate, db: DbDep, user=Depends(get_pos_customer_user)):
    _assert_crm_branch(db, user, data.branch_id, "إنشاء عميل")
    try:
        return services.create_customer(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


def _get_customer_or_404(db, customer_id: int):
    c = crud.get_customer(db, customer_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "العميل غير موجود")
    return c


@router.get("/crm/customers/{customer_id}", response_model=CustomerRead)
def get_customer(customer_id: int, db: DbDep, user=Depends(get_pos_customer_user)):
    c = _get_customer_or_404(db, customer_id)
    _assert_crm_branch(db, user, c.branch_id, "عرض عميل")
    return CustomerRead.model_validate(c)


@router.patch("/crm/customers/{customer_id}", response_model=CustomerRead)
def update_customer(customer_id: int, data: CustomerUpdate, db: DbDep,
                    user=Depends(get_pos_customer_user)):
    c = _get_customer_or_404(db, customer_id)
    _assert_crm_branch(db, user, c.branch_id, "تعديل عميل")
    try:
        return services.update_customer(db, customer_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.patch("/crm/customers/{customer_id}/group", response_model=CustomerRead)
def assign_customer_group(customer_id: int, req: AssignCustomerGroupRequest, db: DbDep,
                          user=Depends(get_crm_user)):
    """مقفول على مدير+ عمدًا (مش get_current_active_user زي PATCH العادي) —
    راجع تعليق AssignCustomerGroupRequest في schemas.py."""
    c = _get_customer_or_404(db, customer_id)
    _assert_crm_branch(db, user, c.branch_id, "تعيين مجموعة عميل")
    try:
        return services.assign_customer_group(db, customer_id, req.customer_group_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/crm/customers/{customer_id}/blacklist",
             response_model=CustomerRead)
def blacklist_customer(customer_id: int, req: BlacklistRequest, db: DbDep,
                       user=Depends(get_crm_user)):
    c = _get_customer_or_404(db, customer_id)
    _assert_crm_branch(db, user, c.branch_id, "إضافة عميل للقائمة السوداء")
    try:
        return services.blacklist_customer(db, customer_id, req)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.delete("/crm/customers/{customer_id}/blacklist",
               response_model=CustomerRead,
               dependencies=[Depends(require_permission("crm.unblacklist_customer", "execute", min_role_level=60))])
def unblacklist_customer(customer_id: int, db: DbDep, user=Depends(get_crm_user)):
    c = _get_customer_or_404(db, customer_id)
    _assert_crm_branch(db, user, c.branch_id, "إزالة عميل من القائمة السوداء")
    try:
        return services.unblacklist_customer(db, customer_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Campaigns ─────────────────────────────────────────────────────────
# نفس فئة الباج الموثّقة في § 11.6ish — Campaign model + crud + services
# كانوا موجودين بالكامل، بس مفيش router endpoint خالص، فمفيش حد يقدر
# يستخدم الميزة فعليًا (404 دايمًا على أي محاولة نداء).

@router.get("/crm/campaigns", response_model=PaginatedResponse)
def list_campaigns(
    db: DbDep,
    user=Depends(get_crm_user),
    branch_id: int = Query(...),
    status_filter: Optional[str] = Query(None, alias="status"),
    campaign_type: Optional[str] = Query(None),
    start_from: Optional[date] = Query(None),
    start_to: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    _assert_crm_branch(db, user, branch_id, "عرض الحملات التسويقية")
    items, total = crud.list_campaigns(db, branch_id, status_filter, campaign_type,
                                       start_from, start_to,
                                       skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[CampaignRead.model_validate(c) for c in items])


@router.post("/crm/campaigns", response_model=CampaignRead,
             status_code=status.HTTP_201_CREATED)
def create_campaign(data: CampaignCreate, db: DbDep, user=Depends(get_crm_user)):
    _assert_crm_branch(db, user, data.branch_id, "إنشاء حملة تسويقية")
    try:
        return services.create_campaign(db, data, created_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


def _get_campaign_or_404(db, campaign_id: int):
    campaign = crud.get_campaign(db, campaign_id)
    if not campaign:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الحملة غير موجودة")
    return campaign


@router.get("/crm/campaigns/{campaign_id}", response_model=CampaignRead)
def get_campaign(campaign_id: int, db: DbDep, user=Depends(get_crm_user)):
    campaign = _get_campaign_or_404(db, campaign_id)
    _assert_crm_branch(db, user, campaign.branch_id, "عرض حملة تسويقية")
    return campaign


@router.patch("/crm/campaigns/{campaign_id}", response_model=CampaignRead)
def update_campaign(campaign_id: int, data: CampaignUpdate, db: DbDep,
                     user=Depends(get_crm_user)):
    campaign = _get_campaign_or_404(db, campaign_id)
    _assert_crm_branch(db, user, campaign.branch_id, "تعديل حملة تسويقية")
    try:
        return services.update_campaign(db, campaign_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Lead Sources ──────────────────────────────────────────────────────
# نفس فئة الباج: LeadSource model وعمود Lead.source_id اللي بيشاور عليه
# كانوا موجودين بالكامل من زمان، بس صفر schema/crud/router — مفيش أي طريقة
# تسجّل بيها مصدر عميل محتمل جديد عن طريق الـ API.

@router.get("/crm/lead-sources", response_model=list[LeadSourceRead])
def list_lead_sources(
    db: DbDep, user=Depends(get_crm_user),
    branch_id: int = Query(...),
    active_only: bool = Query(True),
):
    _assert_crm_branch(db, user, branch_id, "عرض مصادر العملاء المحتملين")
    return [LeadSourceRead.model_validate(s) for s in crud.list_lead_sources(db, branch_id, active_only)]


@router.post("/crm/lead-sources", response_model=LeadSourceRead,
             status_code=status.HTTP_201_CREATED)
def create_lead_source(data: LeadSourceCreate, db: DbDep, user=Depends(get_crm_user)):
    _assert_crm_branch(db, user, data.branch_id, "إنشاء مصدر عملاء محتملين")
    return LeadSourceRead.model_validate(crud.create_lead_source(db, data.model_dump()))


# ── Leads ─────────────────────────────────────────────────────────────
# frontend/apps/admin/src/views/CRMView.vue بينادي GET /crm/leads و
# PATCH /crm/leads/{id} — الـ model (Lead) وكل crud functions بتاعته كانوا
# موجودين بالكامل من زمان، بس مفيش router endpoint خالص، فكان 404 حقيقي
# في الإنتاج. نفس فئة الباج الموثّقة في CLAUDE.md § 11.6.

@router.get("/crm/leads", response_model=list[LeadRead])
def list_leads(
    db: DbDep, user=Depends(get_crm_user),
    branch_id: int = Query(...),
    stage: Optional[str] = Query(None),
):
    _assert_crm_branch(db, user, branch_id, "عرض العملاء المحتملين")
    return [LeadRead.model_validate(lead) for lead in crud.list_leads(db, branch_id, stage)]


@router.post("/crm/leads", response_model=LeadRead,
             status_code=status.HTTP_201_CREATED)
def create_lead(data: LeadCreate, db: DbDep, user=Depends(get_crm_user)):
    _assert_crm_branch(db, user, data.branch_id, "إنشاء عميل محتمل")
    return LeadRead.model_validate(services.create_lead(db, data))


def _get_lead_or_404(db, lead_id: int):
    lead = crud.get_lead(db, lead_id)
    if not lead:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"العميل المحتمل {lead_id} غير موجود")
    return lead


@router.get("/crm/leads/{lead_id}", response_model=LeadRead)
def get_lead(lead_id: int, db: DbDep, user=Depends(get_crm_user)):
    lead = _get_lead_or_404(db, lead_id)
    _assert_crm_branch(db, user, lead.branch_id, "عرض عميل محتمل")
    return LeadRead.model_validate(lead)


@router.patch("/crm/leads/{lead_id}", response_model=LeadRead)
def update_lead_stage(lead_id: int, data: LeadStageUpdate, db: DbDep,
                      user=Depends(get_crm_user)):
    lead = _get_lead_or_404(db, lead_id)
    _assert_crm_branch(db, user, lead.branch_id, "تعديل مرحلة عميل محتمل")
    try:
        return LeadRead.model_validate(services.update_lead_stage(db, lead_id, data))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.patch("/crm/leads/{lead_id}/details", response_model=LeadRead)
def update_lead_details(lead_id: int, data: LeadUpdate, db: DbDep,
                        user=Depends(get_crm_user)):
    """يعدّل بيانات الـ lead الأساسية (الاسم/الهاتف/المصدر/الاهتمام...) —
    منفصل عمدًا عن تعديل الـ stage فوق (endpoint مختلف بمسؤولية مختلفة)."""
    lead = _get_lead_or_404(db, lead_id)
    _assert_crm_branch(db, user, lead.branch_id, "تعديل بيانات عميل محتمل")
    try:
        return LeadRead.model_validate(services.update_lead_details(db, lead_id, data))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/crm/leads/{lead_id}/convert", response_model=LeadConvertResponse,
             status_code=status.HTTP_201_CREATED)
async def convert_lead(lead_id: int, data: LeadConvertRequest, db: DbDep,
                       user=Depends(get_booking_operator_user)):
    """wagdy.md C-03 — تحويل lead لحجز مباشرة بضغطة واحدة. نفس مستوى صلاحية
    إنشاء حجز في PMS نفسه (get_cashier_user) عشان الطريق البديل ده (عبر CRM)
    ميبقاش أضعف أمنيًا من المسار المباشر POST /pms/bookings."""
    from app.modules.pms.services import BookingConflictError  # noqa: PLC0415
    lead_for_check = _get_lead_or_404(db, lead_id)
    _assert_crm_branch(db, user, lead_for_check.branch_id, "تحويل عميل محتمل لحجز")
    try:
        lead, booking = services.convert_lead_to_booking(db, lead_id, data)
    except BookingConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    # نفس بث "rooms_changed" اللي POST /pms/bookings بيعمله — بدونه شاشة
    # خريطة الغرف الحية متعرفش إن حجز جديد اتعمل غير بعد refresh يدوي.
    try:
        from app.modules.pms.api.router import pms_rooms_manager  # noqa: PLC0415
        await pms_rooms_manager.broadcast(str(lead.branch_id), {"type": "rooms_changed"})
    except Exception:
        pass  # بث لحظي ثانوي — فشله ميلغيش نجاح التحويل نفسه

    return LeadConvertResponse(
        lead=LeadRead.model_validate(lead),
        booking_id=booking.id,
        booking_number=booking.booking_number,
    )


# ── Call Notes ────────────────────────────────────────────────────────
# نفس فئة الباج: CallNote model كان موجود بالكامل، بس مفيش schema/crud/
# router خالص — 404 دايمًا على أي محاولة استخدام حقيقية.

@router.get("/crm/leads/{lead_id}/call-notes", response_model=list[CallNoteRead])
def list_call_notes(lead_id: int, db: DbDep, user=Depends(get_crm_user)):
    lead = _get_lead_or_404(db, lead_id)
    _assert_crm_branch(db, user, lead.branch_id, "عرض مذكرات مكالمات")
    return [CallNoteRead.model_validate(n) for n in crud.list_call_notes_for_lead(db, lead_id)]


@router.post("/crm/leads/{lead_id}/call-notes", response_model=CallNoteRead,
             status_code=status.HTTP_201_CREATED)
def create_call_note(lead_id: int, data: CallNoteCreate, db: DbDep,
                     user=Depends(get_crm_user)):
    lead = _get_lead_or_404(db, lead_id)
    _assert_crm_branch(db, user, lead.branch_id, "تسجيل مذكرة مكالمة")
    if data.lead_id != lead_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "lead_id غير مطابق للمسار")
    return CallNoteRead.model_validate(crud.create_call_note(db, data, called_by=user.id))


# ── Guest Profiles ────────────────────────────────────────────────────
# GuestProfile كان model + crud كاملين (get_or_create_guest_profile/
# update_guest_profile_on_checkout — دي كانت بتتوصف "تتحدّث عند كل checkout"
# بس مفيش أي موديول بينادي عليها فعليًا) من غير أي schema/router — نفس
# فئة الباج الموثّقة فوق. اتوصلت بـ pms.services.checkout_booking (راجع
# app/modules/pms/services.py) + endpoints قراءة هنا.

@router.get("/crm/guest-profiles", response_model=list[GuestProfileRead])
def list_guest_profiles(
    db: DbDep, user=Depends(get_crm_user),
    branch_id: int = Query(...),
    vip_only: bool = Query(False),
):
    _assert_crm_branch(db, user, branch_id, "عرض ملفات الضيوف")
    return [GuestProfileRead.model_validate(p) for p in crud.list_guest_profiles(db, branch_id, vip_only)]


@router.get("/crm/guest-profiles/by-phone/{phone}", response_model=GuestProfileRead)
def get_guest_profile_by_phone(phone: str, db: DbDep,
                               user=Depends(get_crm_user),
                               branch_id: int = Query(...)):
    _assert_crm_branch(db, user, branch_id, "البحث عن ملف ضيف")
    profile = crud.get_guest_profile_by_phone(db, branch_id, phone)
    if not profile:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "لا يوجد ملف ضيف بهذا الرقم")
    return GuestProfileRead.model_validate(profile)


# ── Interactions ──────────────────────────────────────────────────────

@router.get("/crm/customers/{customer_id}/interactions",
            response_model=PaginatedResponse)
def list_interactions(
    customer_id: int, db: DbDep,
    user=Depends(get_pos_customer_user),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    c = _get_customer_or_404(db, customer_id)
    _assert_crm_branch(db, user, c.branch_id, "عرض تفاعلات عميل")
    items, total = crud.list_interactions(db, customer_id,
                                          skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[InteractionRead.model_validate(i) for i in items])


@router.post("/crm/interactions", response_model=InteractionRead,
             status_code=status.HTTP_201_CREATED)
def log_interaction(data: InteractionCreate, db: DbDep, user=Depends(get_pos_customer_user)):
    _assert_crm_branch(db, user, data.branch_id, "تسجيل تفاعل عميل")
    try:
        return services.log_interaction(db, data, handled_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Opportunities ─────────────────────────────────────────────────────

@router.get("/crm/opportunities", response_model=PaginatedResponse)
def list_opportunities(
    db: DbDep,
    user=Depends(get_crm_user),
    branch_id: int = Query(...),
    stage: Optional[str] = Query(None),
    assigned_to: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    _assert_crm_branch(db, user, branch_id, "عرض الفرص البيعية")
    items, total = crud.list_opportunities(db, branch_id, stage, assigned_to,
                                           skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[OpportunityRead.model_validate(o) for o in items])


@router.post("/crm/opportunities", response_model=OpportunityRead,
             status_code=status.HTTP_201_CREATED)
def create_opportunity(data: OpportunityCreate, db: DbDep, user=Depends(get_crm_user)):
    _assert_crm_branch(db, user, data.branch_id, "إنشاء فرصة بيعية")
    try:
        return services.create_opportunity(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.patch("/crm/opportunities/{opp_id}", response_model=OpportunityRead)
def update_opportunity(opp_id: int, data: OpportunityUpdate, db: DbDep,
                       user=Depends(get_crm_user)):
    opp = crud.get_opportunity(db, opp_id)
    if not opp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الفرصة غير موجودة")
    _assert_crm_branch(db, user, opp.branch_id, "تعديل فرصة بيعية")
    try:
        return services.update_opportunity(db, opp_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Activities ────────────────────────────────────────────────────────

@router.get("/crm/activities", response_model=PaginatedResponse)
def list_activities(
    db: DbDep,
    user=Depends(get_crm_user),
    branch_id: int = Query(...),
    customer_id: Optional[int] = Query(None),
    assigned_to: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    due_before: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    _assert_crm_branch(db, user, branch_id, "عرض الأنشطة")
    items, total = crud.list_activities(
        db, branch_id, customer_id, assigned_to, status, due_before,
        skip=(page - 1) * size, limit=size,
    )
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[ActivityRead.model_validate(a) for a in items])


@router.post("/crm/activities", response_model=ActivityRead,
             status_code=status.HTTP_201_CREATED)
def create_activity(data: ActivityCreate, db: DbDep, user=Depends(get_crm_user)):
    _assert_crm_branch(db, user, data.branch_id, "إنشاء نشاط")
    try:
        return services.create_activity(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.patch("/crm/activities/{activity_id}", response_model=ActivityRead)
def update_activity(activity_id: int, data: ActivityUpdate, db: DbDep,
                    user=Depends(get_crm_user)):
    activity = crud.get_activity(db, activity_id)
    if not activity:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "النشاط غير موجود")
    _assert_crm_branch(db, user, activity.branch_id, "تعديل نشاط")
    try:
        return services.update_activity(db, activity_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Loyalty Program ───────────────────────────────────────────────────────────

@router.get("/crm/loyalty/program", response_model=Optional[LoyaltyProgramRead])
def get_loyalty_program(branch_id: int = Query(...), db: DbDep = ...,
                        user=Depends(get_crm_user)):
    _assert_crm_branch(db, user, branch_id, "عرض برنامج النقاط")
    return services.get_or_create_loyalty_program(db, branch_id)


@router.post("/crm/loyalty/program", response_model=LoyaltyProgramRead,
             status_code=status.HTTP_201_CREATED)
def create_loyalty_program(data: LoyaltyProgramCreate, db: DbDep,
                           user=Depends(get_admin_user)):
    _assert_crm_branch(db, user, data.branch_id, "إنشاء برنامج نقاط")
    try:
        return services.setup_loyalty_program(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.patch("/crm/loyalty/program", response_model=LoyaltyProgramRead)
def update_loyalty_program(branch_id: int = Query(...),
                           data: LoyaltyProgramUpdate = ...,
                           db: DbDep = ...,
                           user=Depends(get_admin_user)):
    _assert_crm_branch(db, user, branch_id, "تعديل برنامج نقاط")
    try:
        return services.update_loyalty_program(db, branch_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Loyalty Account (per customer) ───────────────────────────────────────────

@router.get("/crm/loyalty/account", response_model=Optional[LoyaltyAccountRead])
def get_customer_loyalty(
    customer_id: int = Query(...),
    branch_id: int = Query(...),
    db: DbDep = ...,
    user=Depends(get_pos_customer_user),
):
    _assert_crm_branch(db, user, branch_id, "عرض رصيد نقاط عميل")
    return services.get_customer_loyalty_account(db, branch_id, customer_id)


@router.get("/crm/loyalty/account/transactions", response_model=list[LoyaltyTransactionRead])
def get_loyalty_transactions(
    customer_id: int = Query(...),
    branch_id: int = Query(...),
    limit: int = Query(50, ge=1, le=200),
    db: DbDep = ...,
    user=Depends(get_pos_customer_user),
):
    _assert_crm_branch(db, user, branch_id, "عرض حركات نقاط عميل")
    return services.get_loyalty_transactions(db, branch_id, customer_id, limit)


# ── Loyalty Operations ────────────────────────────────────────────────────────

@router.post("/crm/loyalty/redeem", response_model=LoyaltyRedeemResponse)
def redeem_loyalty_points(
    data: LoyaltyRedeemRequest,
    db: DbDep,
    user=Depends(get_pos_customer_user),
):
    """يسترد نقاط عميل ويرجع قيمة الخصم — كاشير+."""
    _assert_crm_branch(db, user, data.branch_id, "استرداد نقاط عميل")
    try:
        return services.redeem_loyalty_points(db, data, created_by=user.id)
    except services.LoyaltyConcurrencyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/crm/loyalty/adjust", response_model=LoyaltyAccountRead)
def adjust_loyalty_points(
    data: LoyaltyAdjustRequest,
    db: DbDep,
    user=Depends(get_crm_user),
):
    """تعديل يدوي على رصيد النقاط — مدير+."""
    _assert_crm_branch(db, user, data.branch_id, "تعديل رصيد نقاط عميل")
    try:
        account = services.adjust_loyalty_points(db, data, created_by=user.id)
        return LoyaltyAccountRead.model_validate(account)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
