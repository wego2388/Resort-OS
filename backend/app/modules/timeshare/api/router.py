"""app/modules/timeshare/api/router.py

نظام الصلاحيات:
  - get_timeshare_user   : الحد الأدنى لأي endpoint في الوحدة
                           (cashier+ تلقائياً، أو timeshare_agent مع permission صريح)
  - get_manager_user     : عمليات الإدارة (إنشاء/تعديل/إلغاء/نقل وحدة/تقارير)
  - require_permission   : عمليات حساسة تستحق override فردي

timeshare_agent workflow:
  1. admin ينشئ user بـ role='timeshare_agent'
  2. admin يمنحه الصلاحيات المطلوبة عبر POST /api/v1/permissions:
       timeshare.access / view          ← إلزامي (بوابة get_timeshare_user)
       timeshare.contracts / view       ← عرض العقود
       timeshare.installments / view    ← عرض الأقساط
       timeshare.installments / collect ← تحصيل قسط (اختياري)
       timeshare.visits / view          ← عرض الزيارات
       timeshare.visits / create        ← جدولة زيارة (اختياري)
       timeshare.visits / edit          ← تحديث حالة زيارة (اختياري)
       timeshare.calendar / view        ← الكالندر
       timeshare.waitlist / view        ← قائمة الانتظار
       timeshare.waitlist / create      ← إضافة لقائمة الانتظار (اختياري)
  3. العمليات الإدارية (إنشاء عقد، إلغاء، نقل وحدة، تقارير) تبقى manager فقط.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import Response

from app.core.deps import (
    DbDep,
    get_cashier_user,
    get_current_active_user,
    get_manager_user,
    get_timeshare_user,
    require_permission,
)
from app.modules.timeshare import crud, services
from app.modules.timeshare.schemas import (
    PayInstallmentRequest, InstallmentRead,
    TimeshareCancelRequest, TimeshareUnitTransferRequest,
    TimeshareContractCreate, TimeshareContractRead, TimeshareContractUpdate,
    TimeshareUnitRead,
    TimeshareVisitCreate, TimeshareVisitRead, TimeshareVisitUpdate,
    WaitlistCreate, WaitlistRead,
)
from app.modules.core.schemas import PaginatedResponse

router = APIRouter(tags=["timeshare"])


# ── Contracts ────────────────────────────────────────────────────────

@router.get("/timeshare/contracts", response_model=PaginatedResponse)
def list_contracts(
    db: DbDep, _=Depends(get_timeshare_user),
    branch_id: int = Query(...),
    contract_status: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
):
    items, total = crud.list_contracts(db, branch_id, contract_status, search,
                                       skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[TimeshareContractRead.model_validate(c) for c in items])


@router.post("/timeshare/contracts", response_model=TimeshareContractRead,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission("timeshare.contracts", "create", min_role_level=60))])
def create_contract(data: TimeshareContractCreate, db: DbDep, user=Depends(get_manager_user)):
    try:
        return services.create_contract(db, data, signed_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/timeshare/contracts/{contract_id}", response_model=TimeshareContractRead)
def get_contract(contract_id: int, db: DbDep, _=Depends(get_timeshare_user)):
    c = crud.get_contract(db, contract_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "العقد غير موجود")
    return TimeshareContractRead.model_validate(c)


@router.patch("/timeshare/contracts/{contract_id}", response_model=TimeshareContractRead,
              dependencies=[Depends(require_permission("timeshare.contracts", "edit", min_role_level=60))])
def update_contract(contract_id: int, data: TimeshareContractUpdate, db: DbDep,
                    _=Depends(get_manager_user)):
    try:
        return services.update_contract(db, contract_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Installments ─────────────────────────────────────────────────────

@router.get("/timeshare/installments")
def list_installments(
    db: DbDep, _=Depends(get_timeshare_user),
    branch_id: int = Query(...),
    status_filter: Optional[str] = Query(None, alias="status"),
    contract_id: Optional[int] = Query(None),
    month: Optional[str] = Query(None, description="YYYY-MM"),
    search: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
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
                    _=Depends(get_timeshare_user)):
    try:
        return services.pay_installment(db, inst_id, req)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/timeshare/installments/monthly-report")
def download_monthly_collection_report(
    db: DbDep,
    _=Depends(get_manager_user),
    branch_id: int = Query(...),
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"),
):
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


# ── Waitlist ─────────────────────────────────────────────────────────

@router.get("/timeshare/waitlist", response_model=list[WaitlistRead])
def list_waitlist(db: DbDep, _=Depends(get_timeshare_user), branch_id: int = Query(...)):
    return [WaitlistRead.model_validate(w) for w in crud.list_waitlist(db, branch_id)]


@router.post("/timeshare/waitlist", response_model=WaitlistRead,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission("timeshare.waitlist", "create", min_role_level=40))])
def add_to_waitlist(data: WaitlistCreate, db: DbDep, _=Depends(get_timeshare_user)):
    try:
        return services.add_to_waitlist(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Contract PDF ─────────────────────────────────────────────────────

@router.get("/timeshare/contracts/{contract_id}/pdf")
def download_contract_pdf(contract_id: int, db: DbDep, _=Depends(get_timeshare_user)):
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

@router.get("/timeshare/cs-summary")
def get_cs_summary(db: DbDep, _=Depends(get_timeshare_user), branch_id: int = Query(...)):
    return services.get_cs_summary(db, branch_id)


@router.get("/timeshare/sales-dashboard")
def get_sales_dashboard(db: DbDep, _=Depends(get_timeshare_user), branch_id: int = Query(...)):
    return services.get_sales_dashboard(db, branch_id)


@router.get("/timeshare/sales-dashboard/export")
def download_sales_dashboard_excel(db: DbDep, _=Depends(get_manager_user), branch_id: int = Query(...)):
    xlsx = services.generate_sales_dashboard_excel(db, branch_id)
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=sales-dashboard.xlsx"},
    )


# ── Calendar & Availability ───────────────────────────────────────────

@router.get("/timeshare/calendar")
def get_calendar(
    db: DbDep, _=Depends(get_timeshare_user),
    branch_id: int = Query(...), year: Optional[int] = Query(None),
):
    return services.get_calendar(db, branch_id, year)


@router.get("/timeshare/available-weeks")
def get_available_weeks(
    db: DbDep, _=Depends(get_timeshare_user),
    branch_id: int = Query(...),
    year: int = Query(..., ge=2020, le=2100),
    room_type: Optional[str] = Query(None, pattern=r"^(2R|4R|6R)$"),
):
    return services.get_available_weeks(db, branch_id, year, room_type)


@router.get("/timeshare/upcoming-visits")
def get_upcoming_visits(
    db: DbDep, _=Depends(get_timeshare_user),
    branch_id: int = Query(...), days: int = Query(30, ge=1, le=365),
):
    return services.get_upcoming_visits(db, branch_id, days)


# ── Stats ─────────────────────────────────────────────────────────────

@router.get("/timeshare/stats")
def get_stats(db: DbDep, _=Depends(get_timeshare_user), branch_id: int = Query(...)):
    return services.get_stats(db, branch_id)


# ── Contract Actions (manager only) ─────────────────────────────────

@router.post("/timeshare/contracts/{contract_id}/cancel", response_model=TimeshareContractRead,
             dependencies=[Depends(require_permission("timeshare.cancel_contract", "execute", min_role_level=60))])
def cancel_contract(
    contract_id: int, data: TimeshareCancelRequest, db: DbDep,
    _=Depends(get_manager_user),
):
    try:
        return services.cancel_contract(db, contract_id, data.cancel_amount)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/timeshare/contracts/{contract_id}/transfer-unit", response_model=TimeshareContractRead)
def transfer_unit(
    contract_id: int, data: TimeshareUnitTransferRequest, db: DbDep,
    user=Depends(get_manager_user),
):
    try:
        return services.transfer_unit(db, contract_id, data, transferred_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Visits ────────────────────────────────────────────────────────────

@router.get("/timeshare/visits", response_model=list[TimeshareVisitRead])
def list_visits(
    db: DbDep, _=Depends(get_timeshare_user),
    branch_id: int = Query(...),
    contract_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    return [TimeshareVisitRead.model_validate(v) for v in crud.list_visits(db, branch_id, contract_id, status_filter)]


@router.post("/timeshare/visits", response_model=TimeshareVisitRead,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission("timeshare.visits", "create", min_role_level=40))])
def create_visit(data: TimeshareVisitCreate, db: DbDep, _=Depends(get_timeshare_user)):
    try:
        return services.create_visit(db, data)
    except services.VisitConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.patch("/timeshare/visits/{visit_id}", response_model=TimeshareVisitRead,
              dependencies=[Depends(require_permission("timeshare.visits", "edit", min_role_level=25))])
def update_visit(visit_id: int, data: TimeshareVisitUpdate, db: DbDep,
                 _=Depends(get_timeshare_user)):
    try:
        return services.update_visit(db, visit_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ── Units ─────────────────────────────────────────────────────────────

@router.get("/timeshare/units", response_model=list[TimeshareUnitRead])
def list_units(
    db: DbDep, _=Depends(get_timeshare_user),
    branch_id: int = Query(...),
    unit_type: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    return [TimeshareUnitRead.model_validate(u) for u in crud.list_units(db, branch_id, unit_type, status_filter)]


# ── Excel Import ──────────────────────────────────────────────────────

@router.post("/timeshare/contracts/import-excel")
async def import_contracts_excel(
    file: UploadFile, db: DbDep,
    branch_id: int = Query(...),
    user=Depends(get_manager_user),
):
    try:
        content = await file.read()
        return services.import_contracts_excel(db, branch_id, content, signed_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
