"""app/modules/leasing/api/router.py"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from app.core.config import settings
from app.core.deps import DbDep, get_cashier_user, get_current_active_user, get_manager_user
from app.modules.leasing import crud, services
from app.modules.leasing.schemas import (
    ConfirmDepositRequest, LeaseContractCreate, LeaseContractRead, LeaseContractUpdate,
    LeasePaymentRead, PayLeaseRequest, TenantAgingRow, TenantCashLogCreate, TenantCashLogRead,
    ApplyPenaltiesResponse,
)
from app.modules.core import services as core_services
from app.modules.core.schemas import PaginatedResponse
from app.modules.finance.services import FinancialConfigurationError
from app.resort_os.timezone_utils import local_today

router = APIRouter(tags=["leasing"])


def _to_read(contract, today) -> LeaseContractRead:
    """LeaseContractRead + `days_until_expiry` محسوب لحظيًا (مش عمود مخزّن)."""
    data = LeaseContractRead.model_validate(contract).model_dump()
    data["days_until_expiry"] = services.days_until_expiry(contract, today)
    return LeaseContractRead(**data)


def _assert_leasing_branch(db, user, branch_id: int, action_desc: str) -> None:
    """Gate 4B-style branch isolation — كانت غايبة بالكامل من موديول
    الإيجارات (اتكشف 2026-07-28، نفس فئة الباج في timeshare/beach/CRM)."""
    try:
        core_services.assert_branch_access(db, user, branch_id, action_desc)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))


def _get_contract_or_404(db, contract_id: int):
    c = crud.get_contract(db, contract_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "العقد غير موجود")
    return c


@router.get("/leasing/contracts", response_model=PaginatedResponse)
def list_contracts(
    db: DbDep, user=Depends(get_current_active_user),
    branch_id: int = Query(...),
    contract_status: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    expiring_within_days: Optional[int] = Query(
        None, ge=1, le=365,
        description="بدل الفلترة العادية: يرجّع العقود النشطة اللي هتنتهي خلال "
                    "N يوم القادمة بس (مرتبة بالأقرب انتهاءً) — wagdy.md بند #28.",
    ),
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
):
    _assert_leasing_branch(db, user, branch_id, "عرض عقود الإيجار")
    today = local_today(settings.TIMEZONE)
    if expiring_within_days is not None:
        items = services.list_expiring_soon(db, branch_id, expiring_within_days)
        total = len(items)
    else:
        items, total = crud.list_contracts(db, branch_id, contract_status, search,
                                           skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[_to_read(c, today) for c in items])


@router.post("/leasing/contracts", response_model=LeaseContractRead,
             status_code=status.HTTP_201_CREATED)
def create_contract(data: LeaseContractCreate, db: DbDep, user=Depends(get_manager_user)):
    _assert_leasing_branch(db, user, data.branch_id, "إنشاء عقد إيجار")
    try:
        contract = services.create_contract(db, data, signed_by=user.id)
        return _to_read(contract, local_today(settings.TIMEZONE))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/leasing/contracts/{contract_id}", response_model=LeaseContractRead)
def get_contract(contract_id: int, db: DbDep, user=Depends(get_current_active_user)):
    c = _get_contract_or_404(db, contract_id)
    _assert_leasing_branch(db, user, c.branch_id, "عرض عقد إيجار")
    return _to_read(c, local_today(settings.TIMEZONE))


@router.patch("/leasing/contracts/{contract_id}", response_model=LeaseContractRead)
def update_contract(contract_id: int, data: LeaseContractUpdate, db: DbDep,
                    user=Depends(get_manager_user)):
    c = _get_contract_or_404(db, contract_id)
    _assert_leasing_branch(db, user, c.branch_id, "تعديل عقد إيجار")
    try:
        contract = services.update_contract(db, contract_id, data)
        return _to_read(contract, local_today(settings.TIMEZONE))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/leasing/payments/{payment_id}/pay", response_model=LeasePaymentRead)
def pay_payment(payment_id: int, req: PayLeaseRequest, db: DbDep,
                # ⚠️ باج صلاحيات حقيقي كان هنا: get_current_active_user (أي دور،
                # حتى level 0 — customer/guest) بدل get_cashier_user زي
                # finance.add_payment (العملية المكافئة بالظبط — تسجيل دفعة
                # فعلية) — أي حساب عميل/ضيف كان يقدر نظريًا يسجّل دفعة إيجار
                # لأي عقد برقم إيصال ومبلغ مُلفَّق.
                user=Depends(get_cashier_user)):
    payment = crud.get_payment(db, payment_id)
    if not payment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"الدفعة {payment_id} غير موجودة")
    _assert_leasing_branch(db, user, payment.contract.branch_id, "تحصيل دفعة إيجار")
    try:
        return services.pay_payment(db, payment_id, req)
    except services.PaymentConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except FinancialConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {
            "code": "FINANCIAL_CONFIGURATION_ERROR", "message": str(exc),
        })
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/leasing/contracts/{contract_id}/apply-penalties", response_model=ApplyPenaltiesResponse)
def apply_penalties(contract_id: int, db: DbDep, user=Depends(get_manager_user)):
    c = _get_contract_or_404(db, contract_id)
    _assert_leasing_branch(db, user, c.branch_id, "تطبيق غرامات تأخير")
    updated = services.apply_penalties(db, contract_id)
    return {"updated": len(updated)}


@router.post("/leasing/contracts/{contract_id}/confirm-deposit", response_model=LeaseContractRead)
def confirm_deposit_received(contract_id: int, data: ConfirmDepositRequest, db: DbDep,
                             user=Depends(get_cashier_user)):
    """يرحّل قيد التأمين فعليًا بس عند التأكيد الصريح للاستلام — راجع
    OPS-DATA-02 §10.5: التأمين ميترحّلش تلقائيًا عند التوقيع."""
    c = _get_contract_or_404(db, contract_id)
    _assert_leasing_branch(db, user, c.branch_id, "تأكيد استلام تأمين إيجار")
    try:
        contract = services.confirm_deposit_received(db, contract_id, data.payment_method, received_by=user.id)
        return _to_read(contract, local_today(settings.TIMEZONE))
    except FinancialConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {
            "code": "FINANCIAL_CONFIGURATION_ERROR", "message": str(exc),
        })
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/leasing/aging", response_model=list[TenantAgingRow])
def get_tenant_aging(db: DbDep, user=Depends(get_manager_user), branch_id: int = Query(...)):
    _assert_leasing_branch(db, user, branch_id, "عرض تقادم ذمم المستأجرين")
    return services.get_tenant_aging(db, branch_id)


# ── TenantCashLog ─────────────────────────────────────────────────────
# resort-os-docs/06-MODULES.md § LEASING: "TenantCashLog: للمستأجرين الذين
# يسوّون كاش يومي مع المنتجع (مركز غوص/واتر سبورت)". الـ model كان موجود
# بالكامل من زمان (وعنده migration حقيقي) بس من غير أي schemas/crud/services/
# router — نفس فئة الباج الموثّقة في § 11.6 من CLAUDE.md، اتصلحت في مراجعة Task B.

@router.post("/leasing/contracts/{contract_id}/cash-logs", response_model=TenantCashLogRead,
             status_code=status.HTTP_201_CREATED)
def create_cash_log(contract_id: int, data: TenantCashLogCreate, db: DbDep,
                    user=Depends(get_manager_user)):
    if data.contract_id != contract_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "contract_id في الـ body لازم يطابق الـ path")
    c = _get_contract_or_404(db, contract_id)
    _assert_leasing_branch(db, user, c.branch_id, "تسجيل حركة كاش مستأجر")
    try:
        return services.record_cash_log(db, data, recorded_by=user.id)
    except FinancialConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {
            "code": "FINANCIAL_CONFIGURATION_ERROR", "message": str(exc),
        })
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/leasing/contracts/{contract_id}/cash-logs", response_model=list[TenantCashLogRead])
def list_cash_logs(contract_id: int, db: DbDep, user=Depends(get_current_active_user)):
    c = _get_contract_or_404(db, contract_id)
    _assert_leasing_branch(db, user, c.branch_id, "عرض حركات كاش مستأجر")
    try:
        return services.list_cash_logs(db, contract_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.get("/leasing/payments/{payment_id}/receipt", response_model=None)
def download_receipt(payment_id: int, db: DbDep, user=Depends(get_current_active_user)):
    payment = crud.get_payment(db, payment_id)
    if not payment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"الدفعة {payment_id} غير موجودة")
    _assert_leasing_branch(db, user, payment.contract.branch_id, "تحميل إيصال إيجار")
    try:
        pdf = services.generate_rent_receipt_pdf(db, payment_id)
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename=lease-receipt-{payment_id}.pdf"},
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
