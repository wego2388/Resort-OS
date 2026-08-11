"""app/modules/timeshare/api/router.py

نظام الصلاحيات (معزول تمامًا عن باقي المنتجع، طلب Mohamed 2026-08-03 —
راجع docstring get_timeshare_user/get_timeshare_admin_user في deps.py
للتفاصيل الكاملة، خصوصًا الباج القديم اللي كان بيدّي أي كاشير/مدير في أي
موديول وصول تلقائي لبيانات عملاء الملكية الجزئية):
  - get_timeshare_user       : الحد الأدنى لأي endpoint في الوحدة —
                                super_admin، أو timeshare_admin، أو
                                timeshare_agent مع permission صريح بس.
                                مفيش أي bypass لمستوى عام (cashier/manager
                                عاديين مبقاش عندهم وصول تلقائي خالص).
  - get_timeshare_admin_user : عمليات الإدارة (إنشاء/تعديل/إلغاء/نقل وحدة/
                                تقارير/الموافقة على طلبات الزيارة/إدارة
                                موظفي الملكية الجزئية) — role='timeshare_admin'
                                فقط (أو super_admin)، مش get_manager_user
                                العام.
  - require_permission       : عمليات حساسة تستحق override فردي

timeshare_agent workflow:
  1. timeshare_admin (أو super_admin) ينشئ حساب عبر POST /timeshare/staff
     (role='timeshare_agent' ثابت، مش قابل للاختيار — راجع
     services.provision_timeshare_agent) — بيحصل تلقائيًا على
     timeshare.access/view زي ما هو موضّح تحت.
  2. صلاحيات إضافية اختيارية عبر POST /api/v1/permissions (timeshare_admin
     أو super_admin بس):
       timeshare.contracts / view       ← عرض العقود
       timeshare.installments / view    ← عرض الأقساط
       timeshare.installments / collect ← تحصيل قسط (اختياري)
       timeshare.visits / view          ← عرض الزيارات
       timeshare.visits / create        ← جدولة زيارة (اختياري)
       timeshare.visits / edit          ← تحديث حالة زيارة (اختياري)
       timeshare.calendar / view        ← الكالندر
       timeshare.waitlist / view        ← قائمة الانتظار
       timeshare.waitlist / create      ← إضافة لقائمة الانتظار (اختياري)
       timeshare.visit_requests / view    ← عرض طلبات زيارة العملاء
       timeshare.support_tickets / view    ← عرض تذاكر دعم العملاء
       timeshare.support_tickets / respond ← الرد على تذكرة دعم
  3. العمليات الإدارية (إنشاء عقد، إلغاء، نقل وحدة، تقارير، الموافقة/رفض
     طلب زيارة، إدارة موظفي الملكية الجزئية) تبقى timeshare_admin فقط — طلب
     Mohamed صريح: "المسؤول هو اللي يوافق ويحدد الأسبوع".

الإيرادات المالية لسه بترحّل وتظهر للمحاسبة/الإدارة العامة زي ما هي بالظبط
(post_simple_revenue_journal، حسابات 4600/4650) — العزل هنا للبيانات
التشغيلية/بيانات العملاء بس، مش الأثر المحاسبي.

بوابة العميل العامة (/timeshare/public/*، 2026-08-03): endpoints بدون auth
خالص، محمية بـOTP (رقم عقد + رقم موبايل مسجّل → كود واتساب) بعدها JWT
قصير العمر (X-Timeshare-Owner-Token header، مش query param — جلسة بتتعاد
استخدامها لأكتر من نداء، مش رابط استُخدم مرة واحدة زي survey token). راجع
services.py's "Owner Portal" section للتفاصيل الكاملة.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import Response

from app.core.deps import (
    DbDep,
    get_timeshare_admin_user,
    get_timeshare_user,
    require_permission,
)
from app.modules.timeshare import crud, services
from app.modules.timeshare.schemas import (
    PayInstallmentRequest, InstallmentRead,
    PayMaintenanceDueRequest, TimeshareMaintenanceDueRead,
    MaintenanceFeeSuggestionResponse,
    TimeshareMaintenanceFeeRuleCreate, TimeshareMaintenanceFeeRuleRead,
    TimesharePeakSeasonCreate, TimesharePeakSeasonRead,
    TimeshareCancelRequest, TimeshareUnitTransferRequest,
    TimeshareContractCreate, TimeshareContractRead, TimeshareContractUpdate,
    TimeshareOwnerContractRead, TimeshareOwnerVerifyConfirm, TimeshareOwnerVerifyRequest,
    TimeshareOwnerPortalToken,
    TimeshareStaffCreate, TimeshareStaffProvisioned, TimeshareStaffRead, TimeshareStaffStatusUpdate,
    TimeshareSupportTicketCreate, TimeshareSupportTicketRead,
    TimeshareTicketReplyCreate, TimeshareTicketStatusUpdate,
    TimeshareUnitCreate, TimeshareUnitPairCreate, TimeshareUnitPairRead,
    TimeshareUnitRead, TimeshareUnitUpdate,
    TimeshareVisitCreate, TimeshareVisitRead, TimeshareVisitUpdate,
    TimeshareVisitRequestApprove, TimeshareVisitRequestCreate,
    TimeshareVisitRequestReject, TimeshareVisitRequestRead,
    WaitlistCreate, WaitlistRead, WaitlistStatusUpdate,
    ImportContractsResponse,
)
from app.modules.core import services as core_services
from app.modules.core.schemas import PaginatedResponse
from app.modules.finance.services import FinancialConfigurationError

router = APIRouter(tags=["timeshare"])


def _assert_timeshare_branch(db, user, branch_id: int, action_desc: str) -> None:
    """Gate 4B-style branch isolation — كانت غايبة بالكامل من موديول
    الملكية الجزئية (اتكشف 2026-07-28: get_contract/get_installment/get_visit
    كل واحد فيهم بيدوّر بالـid بس من غير أي فلترة فرع، ومفيش أي
    assert_branch_access في الراوتر كله). كاشير فرع A كان يقدر يحصّل قسط/
    يلغي عقد/ينقل وحدة فرع B بمجرد تخمين الرقم."""
    try:
        core_services.assert_branch_access(db, user, branch_id, action_desc)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))


# ── Contracts ────────────────────────────────────────────────────────

def _get_contract_or_404(db, contract_id: int):
    c = crud.get_contract(db, contract_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "العقد غير موجود")
    return c


@router.get("/timeshare/contracts", response_model=PaginatedResponse)
def list_contracts(
    db: DbDep, user=Depends(get_timeshare_user),
    branch_id: int = Query(...),
    contract_status: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
):
    _assert_timeshare_branch(db, user, branch_id, "عرض عقود الملكية الجزئية")
    items, total = crud.list_contracts(db, branch_id, contract_status, search,
                                       skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[TimeshareContractRead.model_validate(c) for c in items])


@router.post("/timeshare/contracts", response_model=TimeshareContractRead,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission("timeshare.contracts", "create", min_role_level=55))])
def create_contract(data: TimeshareContractCreate, db: DbDep, user=Depends(get_timeshare_admin_user)):
    _assert_timeshare_branch(db, user, data.branch_id, "إنشاء عقد ملكية جزئية")
    try:
        return services.create_contract(
            db,
            data,
            signed_by=user.id,
            collection_actor_id=user.id,
        )
    except FinancialConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {
            "code": "FINANCIAL_CONFIGURATION_ERROR", "message": str(exc),
        })
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/timeshare/contracts/{contract_id}", response_model=TimeshareContractRead)
def get_contract(contract_id: int, db: DbDep, user=Depends(get_timeshare_user)):
    c = _get_contract_or_404(db, contract_id)
    _assert_timeshare_branch(db, user, c.branch_id, "عرض عقد ملكية جزئية")
    return TimeshareContractRead.model_validate(c)


@router.patch("/timeshare/contracts/{contract_id}", response_model=TimeshareContractRead,
              dependencies=[Depends(require_permission("timeshare.contracts", "edit", min_role_level=55))])
def update_contract(contract_id: int, data: TimeshareContractUpdate, db: DbDep,
                    user=Depends(get_timeshare_admin_user)):
    c = _get_contract_or_404(db, contract_id)
    _assert_timeshare_branch(db, user, c.branch_id, "تعديل عقد ملكية جزئية")
    try:
        return services.update_contract(db, contract_id, data, updated_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Installments ─────────────────────────────────────────────────────

@router.get("/timeshare/installments", response_model=None)
def list_installments(
    db: DbDep, user=Depends(get_timeshare_user),
    branch_id: int = Query(...),
    status_filter: Optional[str] = Query(None, alias="status"),
    contract_id: Optional[int] = Query(None),
    month: Optional[str] = Query(None, description="YYYY-MM"),
    search: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    _assert_timeshare_branch(db, user, branch_id, "عرض أقساط الملكية الجزئية")
    result = services.list_installments(db, branch_id, status_filter, contract_id, month, search, limit)
    installments = []
    for i in result["installments"]:
        read = InstallmentRead.model_validate(i)
        if i.contract is not None:
            read.customer_name = i.contract.customer_name
            read.customer_phone = i.contract.customer_phone
            read.room_type = i.contract.room_type
        installments.append(read)
    return {
        "installments": installments,
        "total": result["total"],
        "summary": {k: float(v) for k, v in result["summary"].items()},
    }


@router.post("/timeshare/installments/{inst_id}/pay", response_model=InstallmentRead,
             dependencies=[Depends(require_permission("timeshare.installments", "collect", min_role_level=40))])
def pay_installment(inst_id: int, req: PayInstallmentRequest, db: DbDep,
                    user=Depends(get_timeshare_user)):
    inst = crud.get_installment(db, inst_id)
    if not inst:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"القسط {inst_id} غير موجود")
    _assert_timeshare_branch(db, user, inst.contract.branch_id, "تحصيل قسط ملكية جزئية")
    try:
        return services.pay_installment(db, inst_id, req, collected_by=user.id)
    except services.PaymentConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except FinancialConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {
            "code": "FINANCIAL_CONFIGURATION_ERROR", "message": str(exc),
        })
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/timeshare/installments/monthly-report", response_model=None)
def download_monthly_collection_report(
    db: DbDep,
    user=Depends(get_timeshare_admin_user),
    branch_id: int = Query(...),
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"),
):
    _assert_timeshare_branch(db, user, branch_id, "تحميل تقرير التحصيل الشهري")
    try:
        year_s, month_s = month.split("-")
        if not (1 <= int(month_s) <= 12):
            raise ValueError("الشهر يجب أن يكون بين 01 و12")
    except (ValueError, AttributeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "صيغة الشهر غير صحيحة — استخدم YYYY-MM")

    xlsx = services.generate_monthly_collection_report(db, branch_id, month)
    filename = f"timeshare-collection-{month}.xlsx"
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Maintenance Dues (رسوم الصيانة السنوية) ───────────────────────────

@router.get("/timeshare/maintenance-dues", response_model=None)
def list_maintenance_dues_for_branch(
    db: DbDep, user=Depends(get_timeshare_user),
    branch_id: int = Query(...),
    status_filter: Optional[str] = Query(None, alias="status"),
    contract_id: Optional[int] = Query(None),
    fee_year: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    """مرآة GET /timeshare/installments — قايمة مستحقات صيانة عبر الفرع كله
    لشاشة تاب "الصيانة" الإدارية."""
    _assert_timeshare_branch(db, user, branch_id, "عرض مستحقات صيانة")
    result = services.list_maintenance_dues_for_branch(db, branch_id, status_filter, contract_id, fee_year, search, limit)
    dues = []
    for d in result["maintenance_dues"]:
        read = TimeshareMaintenanceDueRead.model_validate(d)
        if d.contract is not None:
            read.customer_name = d.contract.customer_name
            read.customer_phone = d.contract.customer_phone
            read.room_type = d.contract.room_type
        dues.append(read)
    return {
        "maintenance_dues": dues,
        "total": result["total"],
        "summary": {k: float(v) for k, v in result["summary"].items()},
    }


@router.get("/timeshare/contracts/{contract_id}/maintenance-dues", response_model=list[TimeshareMaintenanceDueRead])
def list_maintenance_dues(contract_id: int, db: DbDep, user=Depends(get_timeshare_user)):
    c = _get_contract_or_404(db, contract_id)
    _assert_timeshare_branch(db, user, c.branch_id, "عرض مستحقات صيانة عقد")
    return [TimeshareMaintenanceDueRead.model_validate(d) for d in crud.list_maintenance_dues(db, contract_id)]


@router.post("/timeshare/maintenance-dues/{due_id}/pay", response_model=TimeshareMaintenanceDueRead,
             dependencies=[Depends(require_permission("timeshare.maintenance_dues", "collect", min_role_level=40))])
def pay_maintenance_due(due_id: int, req: PayMaintenanceDueRequest, db: DbDep,
                        user=Depends(get_timeshare_user)):
    due = crud.get_maintenance_due(db, due_id)
    if not due:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"مستحق الصيانة {due_id} غير موجود")
    _assert_timeshare_branch(db, user, due.contract.branch_id, "تحصيل مستحق صيانة")
    try:
        return services.pay_maintenance_due(db, due_id, req, collected_by=user.id)
    except services.PaymentConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except FinancialConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {
            "code": "FINANCIAL_CONFIGURATION_ERROR", "message": str(exc),
        })
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/timeshare/maintenance-dues/generate", response_model=None,
             dependencies=[Depends(require_permission("timeshare.maintenance_dues", "generate", min_role_level=55))])
def generate_maintenance_dues(
    db: DbDep, user=Depends(get_timeshare_admin_user),
    branch_id: int = Query(...),
    fee_year: int = Query(..., ge=2026, le=2100),
):
    """تشغيل يدوي لتوليد مستحقات الصيانة السنوية — نفس دور Celery task
    generate_annual_maintenance_dues (1 يناير تلقائيًا)، هنا لإعادة التشغيل
    أو التوليد الفوري لسنة معيّنة. fee_year >= 2026 عمدًا — بلا أي تتبّع
    تاريخي قبل كده (قرار Mohamed)."""
    _assert_timeshare_branch(db, user, branch_id, "توليد مستحقات صيانة")
    created = services.generate_annual_maintenance_dues(db, branch_id, fee_year)
    return {"fee_year": fee_year, "created": created}


# ── قواعد صيانة effective-dated/versioned (OPS-DATA-02 §8 نقطة 3) ────────

@router.get("/timeshare/maintenance-fee-suggestion", response_model=MaintenanceFeeSuggestionResponse)
def get_maintenance_fee_suggestion(
    db: DbDep, user=Depends(get_timeshare_user),
    branch_id: int = Query(...),
    contract_date: date = Query(...),
    unit_capacity: int = Query(..., description="2 أو 4 أو 6"),
    fee_year: int = Query(2026, ge=2026, le=2100),
):
    """للعرض/التحقق فقط وقت إنشاء عقد جديد أو مراجعة عقد قديم — القرار
    النهائي يفضل maintenance_fee المُدخَل يدويًا على العقد نفسه."""
    _assert_timeshare_branch(db, user, branch_id, "استعلام مبلغ صيانة مقترح")
    fee, version = services.get_recommended_maintenance_fee(db, branch_id, fee_year, contract_date, unit_capacity)
    return MaintenanceFeeSuggestionResponse(suggested_fee=fee, rule_version=version)


@router.get("/timeshare/maintenance-fee-rules", response_model=list[TimeshareMaintenanceFeeRuleRead])
def list_maintenance_fee_rules(
    db: DbDep, user=Depends(get_timeshare_user),
    branch_id: int = Query(...), fee_year: Optional[int] = Query(None),
):
    _assert_timeshare_branch(db, user, branch_id, "عرض قواعد الصيانة")
    return crud.list_maintenance_fee_rules(db, branch_id, fee_year, active_only=False)


@router.post("/timeshare/maintenance-fee-rules", response_model=TimeshareMaintenanceFeeRuleRead,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission("timeshare.maintenance_fee_rules", "create", min_role_level=55))])
def create_maintenance_fee_rule(
    data: TimeshareMaintenanceFeeRuleCreate, db: DbDep, user=Depends(get_timeshare_admin_user),
):
    _assert_timeshare_branch(db, user, data.branch_id, "إضافة قاعدة صيانة")
    rule = crud.create_maintenance_fee_rule(db, data, created_by=user.id)
    db.commit()
    db.refresh(rule)
    return rule


@router.post("/timeshare/maintenance-fee-rules/{rule_id}/deactivate", response_model=TimeshareMaintenanceFeeRuleRead,
             dependencies=[Depends(require_permission("timeshare.maintenance_fee_rules", "deactivate", min_role_level=55))])
def deactivate_maintenance_fee_rule(rule_id: int, db: DbDep, user=Depends(get_timeshare_admin_user)):
    """soft فقط — لا حذف حقيقي (راجع models.TimeshareMaintenanceFeeRule)."""
    rule = crud.get_maintenance_fee_rule(db, rule_id)
    if not rule:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"قاعدة الصيانة {rule_id} غير موجودة")
    _assert_timeshare_branch(db, user, rule.branch_id, "إلغاء تفعيل قاعدة صيانة")
    crud.deactivate_maintenance_fee_rule(db, rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.post("/timeshare/maintenance-fee-rules/seed-2026", response_model=list[TimeshareMaintenanceFeeRuleRead],
             dependencies=[Depends(require_permission("timeshare.maintenance_fee_rules", "create", min_role_level=55))])
def seed_maintenance_fee_rules_2026(db: DbDep, user=Depends(get_timeshare_admin_user), branch_id: int = Query(...)):
    """يزرع تعميم 2026 الرسمي (6 صفوف: قبل/بعد 1 مايو × 2/4/6 أفراد) —
    idempotent، آمن يتنادى أكتر من مرة."""
    _assert_timeshare_branch(db, user, branch_id, "زرع قواعد صيانة 2026")
    return services.seed_2026_maintenance_fee_rules(db, branch_id, created_by=user.id)


# ── مواسم الذروة (OPS-DATA-02 §8 نقطة 5) ─────────────────────────────

@router.get("/timeshare/peak-seasons", response_model=list[TimesharePeakSeasonRead])
def list_peak_seasons(
    db: DbDep, user=Depends(get_timeshare_user),
    branch_id: int = Query(...), year: Optional[int] = Query(None),
    active_only: bool = Query(True),
):
    _assert_timeshare_branch(db, user, branch_id, "عرض مواسم الذروة")
    return crud.list_peak_seasons(db, branch_id, year, active_only)


@router.post("/timeshare/peak-seasons", response_model=TimesharePeakSeasonRead,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission("timeshare.peak_seasons", "create", min_role_level=55))])
def create_peak_season(data: TimesharePeakSeasonCreate, db: DbDep, user=Depends(get_timeshare_admin_user)):
    _assert_timeshare_branch(db, user, data.branch_id, "إضافة موسم ذروة")
    season = crud.create_peak_season(db, data, created_by=user.id)
    db.commit()
    db.refresh(season)
    return season


@router.post("/timeshare/peak-seasons/{season_id}/deactivate", response_model=TimesharePeakSeasonRead,
             dependencies=[Depends(require_permission("timeshare.peak_seasons", "deactivate", min_role_level=55))])
def deactivate_peak_season(season_id: int, db: DbDep, user=Depends(get_timeshare_admin_user)):
    """soft فقط — لا حذف حقيقي (راجع models.TimesharePeakSeason)."""
    season = crud.get_peak_season(db, season_id)
    if not season:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"موسم الذروة {season_id} غير موجود")
    _assert_timeshare_branch(db, user, season.branch_id, "إلغاء تفعيل موسم ذروة")
    crud.deactivate_peak_season(db, season)
    db.commit()
    db.refresh(season)
    return season


# ── Waitlist ─────────────────────────────────────────────────────────

@router.get("/timeshare/waitlist", response_model=list[WaitlistRead])
def list_waitlist(db: DbDep, user=Depends(get_timeshare_user), branch_id: int = Query(...)):
    _assert_timeshare_branch(db, user, branch_id, "عرض قائمة الانتظار")
    return [WaitlistRead.model_validate(w) for w in crud.list_waitlist(db, branch_id)]


@router.post("/timeshare/waitlist", response_model=WaitlistRead,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission("timeshare.waitlist", "create", min_role_level=40))])
def add_to_waitlist(data: WaitlistCreate, db: DbDep, user=Depends(get_timeshare_user)):
    _assert_timeshare_branch(db, user, data.branch_id, "إضافة لقائمة الانتظار")
    try:
        return services.add_to_waitlist(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.patch("/timeshare/waitlist/{waitlist_id}", response_model=WaitlistRead)
def update_waitlist_status(
    waitlist_id: int, data: WaitlistStatusUpdate, db: DbDep, user=Depends(get_timeshare_admin_user),
):
    entry = crud.get_waitlist_entry(db, waitlist_id)
    if not entry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "عنصر قائمة الانتظار غير موجود")
    _assert_timeshare_branch(db, user, entry.branch_id, "تحديث حالة قائمة الانتظار")
    try:
        return services.update_waitlist_status(db, waitlist_id, data.status)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Contract PDF ─────────────────────────────────────────────────────

@router.get("/timeshare/contracts/{contract_id}/pdf", response_model=None)
def download_contract_pdf(contract_id: int, db: DbDep, user=Depends(get_timeshare_user)):
    c = _get_contract_or_404(db, contract_id)
    _assert_timeshare_branch(db, user, c.branch_id, "تحميل PDF عقد ملكية جزئية")
    try:
        pdf = services.generate_contract_pdf(db, contract_id)
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename=timeshare-{contract_id}.pdf"},
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ── CS Dashboard ─────────────────────────────────────────────────────

@router.get("/timeshare/cs-summary", response_model=None)
def get_cs_summary(db: DbDep, user=Depends(get_timeshare_user), branch_id: int = Query(...)):
    _assert_timeshare_branch(db, user, branch_id, "عرض لوحة خدمة العملاء")
    return services.get_cs_summary(db, branch_id)


@router.get("/timeshare/sales-dashboard", response_model=None)
def get_sales_dashboard(db: DbDep, user=Depends(get_timeshare_user), branch_id: int = Query(...)):
    _assert_timeshare_branch(db, user, branch_id, "عرض لوحة المبيعات")
    return services.get_sales_dashboard(db, branch_id)


@router.get("/timeshare/sales-dashboard/export", response_model=None)
def download_sales_dashboard_excel(db: DbDep, user=Depends(get_timeshare_admin_user), branch_id: int = Query(...)):
    _assert_timeshare_branch(db, user, branch_id, "تصدير لوحة المبيعات")
    xlsx = services.generate_sales_dashboard_excel(db, branch_id)
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=sales-dashboard.xlsx"},
    )


# ── Calendar & Availability ───────────────────────────────────────────

@router.get("/timeshare/calendar", response_model=None)
def get_calendar(
    db: DbDep, user=Depends(get_timeshare_user),
    branch_id: int = Query(...), year: Optional[int] = Query(None),
):
    _assert_timeshare_branch(db, user, branch_id, "عرض كالندر الملكية الجزئية")
    return services.get_calendar(db, branch_id, year)


@router.get("/timeshare/available-weeks", response_model=None)
def get_available_weeks(
    db: DbDep, user=Depends(get_timeshare_user),
    branch_id: int = Query(...),
    year: int = Query(..., ge=2020, le=2100),
    room_type: Optional[str] = Query(None, pattern=r"^(Studio|Chalet)$"),
):
    _assert_timeshare_branch(db, user, branch_id, "عرض الأسابيع المتاحة")
    return services.get_available_weeks(db, branch_id, year, room_type)


@router.get("/timeshare/upcoming-visits", response_model=None)
def get_upcoming_visits(
    db: DbDep, user=Depends(get_timeshare_user),
    branch_id: int = Query(...), days: int = Query(30, ge=1, le=365),
):
    _assert_timeshare_branch(db, user, branch_id, "عرض الزيارات القادمة")
    return services.get_upcoming_visits(db, branch_id, days)


# ── Stats ─────────────────────────────────────────────────────────────

@router.get("/timeshare/stats", response_model=None)
def get_stats(db: DbDep, user=Depends(get_timeshare_user), branch_id: int = Query(...)):
    _assert_timeshare_branch(db, user, branch_id, "عرض إحصائيات الملكية الجزئية")
    return services.get_stats(db, branch_id)


# ── Contract Actions (manager only) ─────────────────────────────────

@router.post("/timeshare/contracts/{contract_id}/cancel", response_model=TimeshareContractRead,
             dependencies=[Depends(require_permission("timeshare.cancel_contract", "execute", min_role_level=55))])
def cancel_contract(
    contract_id: int, data: TimeshareCancelRequest, db: DbDep,
    user=Depends(get_timeshare_admin_user),
):
    c = _get_contract_or_404(db, contract_id)
    _assert_timeshare_branch(db, user, c.branch_id, "إلغاء عقد ملكية جزئية")
    try:
        return services.cancel_contract(
            db,
            contract_id,
            data.cancel_amount,
            refund_method=data.refund_method,
            cancelled_by=user.id,
        )
    except FinancialConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {
            "code": "FINANCIAL_CONFIGURATION_ERROR", "message": str(exc),
        })
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/timeshare/contracts/{contract_id}/transfer-unit", response_model=TimeshareContractRead)
def transfer_unit(
    contract_id: int, data: TimeshareUnitTransferRequest, db: DbDep,
    user=Depends(get_timeshare_admin_user),
):
    c = _get_contract_or_404(db, contract_id)
    _assert_timeshare_branch(db, user, c.branch_id, "نقل وحدة عقد ملكية جزئية")
    try:
        return services.transfer_unit(db, contract_id, data, transferred_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Visits ────────────────────────────────────────────────────────────

@router.get("/timeshare/visits", response_model=list[TimeshareVisitRead])
def list_visits(
    db: DbDep, user=Depends(get_timeshare_user),
    branch_id: int = Query(...),
    contract_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    _assert_timeshare_branch(db, user, branch_id, "عرض زيارات الملكية الجزئية")
    return [TimeshareVisitRead.model_validate(v) for v in crud.list_visits(db, branch_id, contract_id, status_filter)]


@router.post("/timeshare/visits", response_model=TimeshareVisitRead,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission("timeshare.visits", "create", min_role_level=40))])
def create_visit(data: TimeshareVisitCreate, db: DbDep, user=Depends(get_timeshare_user)):
    _assert_timeshare_branch(db, user, data.branch_id, "إنشاء زيارة ملكية جزئية")
    try:
        return services.create_visit(db, data)
    except services.VisitConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.patch("/timeshare/visits/{visit_id}", response_model=TimeshareVisitRead,
              dependencies=[Depends(require_permission("timeshare.visits", "edit", min_role_level=25))])
def update_visit(visit_id: int, data: TimeshareVisitUpdate, db: DbDep,
                 user=Depends(get_timeshare_user)):
    visit = crud.get_visit(db, visit_id)
    if not visit:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"الزيارة {visit_id} غير موجودة")
    _assert_timeshare_branch(db, user, visit.branch_id, "تعديل زيارة ملكية جزئية")
    try:
        return services.update_visit(db, visit_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ── Units ─────────────────────────────────────────────────────────────

@router.get("/timeshare/units", response_model=list[TimeshareUnitRead])
def list_units(
    db: DbDep, user=Depends(get_timeshare_user),
    branch_id: int = Query(...),
    unit_type: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    _assert_timeshare_branch(db, user, branch_id, "عرض وحدات الملكية الجزئية")
    return [TimeshareUnitRead.model_validate(u) for u in crud.list_units(db, branch_id, unit_type, status_filter)]


@router.post("/timeshare/units", response_model=TimeshareUnitRead,
             status_code=status.HTTP_201_CREATED)
def create_unit(data: TimeshareUnitCreate, db: DbDep, user=Depends(get_timeshare_admin_user)):
    """2026-08-03: مخزون الوحدات كان بدون أي مسار إنشاء خالص — وحدة جديدة
    كانت تحتاج تعديل مباشر في قاعدة البيانات."""
    _assert_timeshare_branch(db, user, data.branch_id, "إضافة وحدة ملكية جزئية")
    try:
        return services.create_unit(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.patch("/timeshare/units/{unit_id}", response_model=TimeshareUnitRead)
def update_unit(unit_id: int, data: TimeshareUnitUpdate, db: DbDep, user=Depends(get_timeshare_admin_user)):
    unit = crud.get_unit(db, unit_id)
    if not unit:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الوحدة غير موجودة")
    _assert_timeshare_branch(db, user, unit.branch_id, "تعديل وحدة ملكية جزئية")
    try:
        return services.update_unit(db, unit_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Unit Pairs — سعة 6 Family Compound entitlement (OPS-DATA-02 §8 نقطة 11) ──

@router.get("/timeshare/unit-pairs", response_model=list[TimeshareUnitPairRead])
def list_unit_pairs(
    db: DbDep, user=Depends(get_timeshare_user),
    branch_id: int = Query(...), active_only: bool = Query(True),
):
    _assert_timeshare_branch(db, user, branch_id, "عرض أزواج وحدات الملكية الجزئية")
    return crud.list_unit_pairs(db, branch_id, active_only)


@router.post("/timeshare/unit-pairs", response_model=TimeshareUnitPairRead,
             status_code=status.HTTP_201_CREATED)
def create_unit_pair(data: TimeshareUnitPairCreate, db: DbDep, user=Depends(get_timeshare_admin_user)):
    """ربط شاليه+استوديو كزوج Family Compound معتمد — لازم قبل أي زيارة
    استحقاق فعلية لعقد سعة 6 (راجع services._create_entitlement_pair_visit)."""
    _assert_timeshare_branch(db, user, data.branch_id, "إضافة زوج وحدات ملكية جزئية")
    try:
        return services.create_unit_pair(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/timeshare/unit-pairs/{pair_id}/deactivate", response_model=TimeshareUnitPairRead)
def deactivate_unit_pair(pair_id: int, db: DbDep, user=Depends(get_timeshare_admin_user)):
    """soft فقط — لا حذف حقيقي (نفس نمط TimesharePeakSeason)."""
    pair = crud.get_unit_pair(db, pair_id)
    if not pair:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"زوج الوحدات {pair_id} غير موجود")
    _assert_timeshare_branch(db, user, pair.branch_id, "إلغاء تفعيل زوج وحدات ملكية جزئية")
    try:
        return services.deactivate_unit_pair(db, pair_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ── Excel Import ──────────────────────────────────────────────────────

@router.post("/timeshare/contracts/import-excel", response_model=ImportContractsResponse)
async def import_contracts_excel(
    file: UploadFile, db: DbDep,
    branch_id: int = Query(...),
    user=Depends(get_timeshare_admin_user),
):
    _assert_timeshare_branch(db, user, branch_id, "استيراد عقود من Excel")
    try:
        content = await file.read()
        return services.import_contracts_excel(db, branch_id, content, signed_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ═══════════════════════════════════════════════════════════════════════════
# Owner Portal — بوابة صاحب العقد العامة (بدون auth، محمية بـOTP + JWT)
# راجع docstring services.py's "Owner Portal" section للتصميم الكامل.
# ═══════════════════════════════════════════════════════════════════════════

def _resolve_owner_token(x_owner_token: str) -> int:
    try:
        return services.verify_owner_portal_token(x_owner_token)
    except services.OwnerVerificationError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc))


@router.post("/timeshare/public/verify-request", response_model=None)
def owner_portal_verify_request(data: TimeshareOwnerVerifyRequest, db: DbDep):
    """⚠️ الرد دايمًا نفس الرسالة العامة بغض النظر عن صحة البيانات —
    راجع services.request_owner_otp لمنطق الحماية من enumeration."""
    services.request_owner_otp(db, data.contract_number.strip(), data.phone.strip())
    return {"message": "لو البيانات صحيحة، وصلك كود تحقق على واتساب الآن"}


@router.post("/timeshare/public/verify-confirm", response_model=TimeshareOwnerPortalToken)
def owner_portal_verify_confirm(data: TimeshareOwnerVerifyConfirm, db: DbDep):
    from app.core.config import settings  # noqa: PLC0415

    try:
        token = services.confirm_owner_otp(db, data.contract_number.strip(), data.otp_code.strip())
    except services.OwnerVerificationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return TimeshareOwnerPortalToken(
        token=token, expires_in_minutes=settings.TIMESHARE_PORTAL_TOKEN_TTL_MINUTES,
    )


@router.get("/timeshare/public/my-contract", response_model=TimeshareOwnerContractRead)
def owner_portal_my_contract(
    db: DbDep, x_owner_token: str = Header(..., alias="X-Timeshare-Owner-Token"),
):
    contract_id = _resolve_owner_token(x_owner_token)
    contract = crud.get_contract(db, contract_id)
    if not contract:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "العقد غير موجود")
    read = TimeshareOwnerContractRead.model_validate(contract)
    read.unit_number = contract.unit.unit_number if contract.unit else None
    return read


@router.get("/timeshare/public/my-payments", response_model=None)
def owner_portal_my_payments(
    db: DbDep, x_owner_token: str = Header(..., alias="X-Timeshare-Owner-Token"),
):
    contract_id = _resolve_owner_token(x_owner_token)
    contract = crud.get_contract(db, contract_id)
    if not contract:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "العقد غير موجود")
    return {
        "installments": [InstallmentRead.model_validate(i) for i in contract.installments_list],
        "maintenance_dues": [TimeshareMaintenanceDueRead.model_validate(d) for d in contract.maintenance_dues_list],
    }


@router.get("/timeshare/public/my-contract/pdf", response_model=None)
def owner_portal_my_contract_pdf(
    db: DbDep, x_owner_token: str = Header(..., alias="X-Timeshare-Owner-Token"),
):
    """2026-08-04: نفس PDF العقد المتاح للموظف (generate_contract_pdf) —
    مفيش نسخة للعميل نفسه خالص، رغم إنه أول حاجة عميل يتوقعها من بوابة
    "تابع عقدك"."""
    contract_id = _resolve_owner_token(x_owner_token)
    try:
        pdf = services.generate_contract_pdf(db, contract_id)
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename=timeshare-{contract_id}.pdf"},
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.post("/timeshare/public/visit-requests", response_model=TimeshareVisitRequestRead,
             status_code=status.HTTP_201_CREATED)
def owner_portal_create_visit_request(
    data: TimeshareVisitRequestCreate, db: DbDep,
    x_owner_token: str = Header(..., alias="X-Timeshare-Owner-Token"),
):
    contract_id = _resolve_owner_token(x_owner_token)
    try:
        return services.request_visit(db, contract_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/timeshare/public/visit-requests", response_model=list[TimeshareVisitRequestRead])
def owner_portal_list_visit_requests(
    db: DbDep, x_owner_token: str = Header(..., alias="X-Timeshare-Owner-Token"),
):
    contract_id = _resolve_owner_token(x_owner_token)
    return [
        TimeshareVisitRequestRead.model_validate(r)
        for r in crud.list_visit_requests_for_contract(db, contract_id)
    ]


@router.post("/timeshare/public/support-tickets", response_model=TimeshareSupportTicketRead,
             status_code=status.HTTP_201_CREATED)
def owner_portal_create_support_ticket(
    data: TimeshareSupportTicketCreate, db: DbDep,
    x_owner_token: str = Header(..., alias="X-Timeshare-Owner-Token"),
):
    contract_id = _resolve_owner_token(x_owner_token)
    try:
        return services.submit_support_ticket(db, contract_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/timeshare/public/support-tickets", response_model=list[TimeshareSupportTicketRead])
def owner_portal_list_support_tickets(
    db: DbDep, x_owner_token: str = Header(..., alias="X-Timeshare-Owner-Token"),
):
    contract_id = _resolve_owner_token(x_owner_token)
    return [
        TimeshareSupportTicketRead.model_validate(t)
        for t in crud.list_support_tickets_for_contract(db, contract_id)
    ]


@router.post("/timeshare/public/support-tickets/{ticket_id}/reply", response_model=TimeshareSupportTicketRead)
def owner_portal_reply_to_ticket(
    ticket_id: int, data: TimeshareTicketReplyCreate, db: DbDep,
    x_owner_token: str = Header(..., alias="X-Timeshare-Owner-Token"),
):
    contract_id = _resolve_owner_token(x_owner_token)
    ticket = crud.get_support_ticket(db, ticket_id)
    if not ticket or ticket.contract_id != contract_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "التذكرة غير موجودة")
    try:
        services.reply_to_ticket(db, ticket_id, data.message, author_type="owner")
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.refresh(ticket)
    return TimeshareSupportTicketRead.model_validate(ticket)


# ── Visit Requests (staff review) ────────────────────────────────────

@router.get("/timeshare/visit-requests", response_model=list[TimeshareVisitRequestRead],
            dependencies=[Depends(require_permission("timeshare.visit_requests", "view", min_role_level=25))])
def list_visit_requests(
    db: DbDep, user=Depends(get_timeshare_user),
    branch_id: int = Query(...),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    _assert_timeshare_branch(db, user, branch_id, "عرض طلبات زيارة العملاء")
    result = []
    for r in crud.list_visit_requests_for_branch(db, branch_id, status_filter):
        read = TimeshareVisitRequestRead.model_validate(r)
        if r.contract is not None:
            read.customer_name = r.contract.customer_name
            read.customer_phone = r.contract.customer_phone
            read.contract_number = r.contract.contract_number
        result.append(read)
    return result


@router.post("/timeshare/visit-requests/{request_id}/approve", response_model=TimeshareVisitRequestRead,
             dependencies=[Depends(require_permission("timeshare.visit_requests", "approve", min_role_level=55))])
def approve_visit_request(request_id: int, data: TimeshareVisitRequestApprove, db: DbDep,
                          user=Depends(get_timeshare_admin_user)):
    req = crud.get_visit_request(db, request_id)
    if not req:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"طلب الزيارة {request_id} غير موجود")
    _assert_timeshare_branch(db, user, req.branch_id, "الموافقة على طلب زيارة")
    try:
        return services.approve_visit_request(db, request_id, data.check_in, data.check_out, approved_by=user.id)
    except services.VisitConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/timeshare/visit-requests/{request_id}/reject", response_model=TimeshareVisitRequestRead,
             dependencies=[Depends(require_permission("timeshare.visit_requests", "approve", min_role_level=55))])
def reject_visit_request(request_id: int, data: TimeshareVisitRequestReject, db: DbDep,
                         user=Depends(get_timeshare_admin_user)):
    req = crud.get_visit_request(db, request_id)
    if not req:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"طلب الزيارة {request_id} غير موجود")
    _assert_timeshare_branch(db, user, req.branch_id, "رفض طلب زيارة")
    try:
        return services.reject_visit_request(db, request_id, data.reason, reviewed_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Support Tickets (خدمة عملاء الملكية الجزئية، staff) ───────────────────

@router.get("/timeshare/support-tickets", response_model=list[TimeshareSupportTicketRead],
            dependencies=[Depends(require_permission("timeshare.support_tickets", "view", min_role_level=25))])
def list_support_tickets(
    db: DbDep, user=Depends(get_timeshare_user),
    branch_id: int = Query(...),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    _assert_timeshare_branch(db, user, branch_id, "عرض تذاكر دعم الملكية الجزئية")
    result = []
    for t in crud.list_support_tickets_for_branch(db, branch_id, status_filter):
        read = TimeshareSupportTicketRead.model_validate(t)
        if t.contract is not None:
            read.customer_name = t.contract.customer_name
            read.contract_number = t.contract.contract_number
        result.append(read)
    return result


@router.post("/timeshare/support-tickets/{ticket_id}/reply", response_model=TimeshareSupportTicketRead,
             dependencies=[Depends(require_permission("timeshare.support_tickets", "respond", min_role_level=25))])
def staff_reply_to_ticket(ticket_id: int, data: TimeshareTicketReplyCreate, db: DbDep,
                          user=Depends(get_timeshare_user)):
    ticket = crud.get_support_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"تذكرة الدعم {ticket_id} غير موجودة")
    _assert_timeshare_branch(db, user, ticket.branch_id, "الرد على تذكرة دعم")
    try:
        services.reply_to_ticket(db, ticket_id, data.message, author_type="staff", author_user_id=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.refresh(ticket)
    return TimeshareSupportTicketRead.model_validate(ticket)


@router.patch("/timeshare/support-tickets/{ticket_id}", response_model=TimeshareSupportTicketRead,
              dependencies=[Depends(require_permission("timeshare.support_tickets", "respond", min_role_level=25))])
def update_support_ticket_status(ticket_id: int, data: TimeshareTicketStatusUpdate, db: DbDep,
                                 user=Depends(get_timeshare_user)):
    ticket = crud.get_support_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"تذكرة الدعم {ticket_id} غير موجودة")
    _assert_timeshare_branch(db, user, ticket.branch_id, "تعديل حالة تذكرة دعم")
    try:
        return services.update_ticket_status(db, ticket_id, data.status)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ═══════════════════════════════════════════════════════════════════════════
# Timeshare Staff — مدير الملكية الجزئية بيدير موظفي وحدته (طلب Mohamed 2026-08-03).
# timeshare_admin فقط (أو super_admin) — مفيش أي مسار تفويض لـtimeshare_agent
# نفسه، فمفيش داعي لـrequire_permission override هنا زي باقي الـendpoints —
# get_timeshare_admin_user وحدها كافية، نفس نمط download_contract_pdf.
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/timeshare/staff", response_model=TimeshareStaffProvisioned,
             status_code=status.HTTP_201_CREATED)
def create_timeshare_staff(data: TimeshareStaffCreate, db: DbDep, user=Depends(get_timeshare_admin_user)):
    _assert_timeshare_branch(db, user, data.branch_id, "إنشاء حساب موظف ملكية جزئية")
    try:
        return services.provision_timeshare_agent(
            db, email=data.email, full_name=data.full_name, phone=data.phone,
            branch_id=data.branch_id, created_by=user.id,
            preferred_language=data.preferred_language,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/timeshare/staff", response_model=list[TimeshareStaffRead])
def list_timeshare_staff(db: DbDep, user=Depends(get_timeshare_admin_user), branch_id: int = Query(...)):
    _assert_timeshare_branch(db, user, branch_id, "عرض موظفي الملكية الجزئية")
    return [TimeshareStaffRead.model_validate(u) for u in services.list_timeshare_staff(db, branch_id)]


@router.patch("/timeshare/staff/{staff_user_id}", response_model=TimeshareStaffRead)
def update_timeshare_staff_status(staff_user_id: int, data: TimeshareStaffStatusUpdate, db: DbDep,
                                  user=Depends(get_timeshare_admin_user)):
    try:
        return services.set_timeshare_staff_active(db, staff_user_id, data.is_active)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
