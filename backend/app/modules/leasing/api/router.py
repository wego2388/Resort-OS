"""app/modules/leasing/api/router.py"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from app.core.config import settings
from app.core.deps import DbDep, get_cashier_user, get_current_active_user, get_manager_user
from app.modules.leasing import crud, services
from app.modules.leasing.schemas import (
    LeaseContractCreate, LeaseContractRead, LeaseContractUpdate,
    LeasePaymentRead, PayLeaseRequest, TenantCashLogCreate, TenantCashLogRead,
)
from app.modules.core.schemas import PaginatedResponse
from app.resort_os.timezone_utils import local_today

router = APIRouter(tags=["leasing"])


def _to_read(contract, today) -> LeaseContractRead:
    """LeaseContractRead + `days_until_expiry` محسوب لحظيًا (مش عمود مخزّن)."""
    data = LeaseContractRead.model_validate(contract).model_dump()
    data["days_until_expiry"] = services.days_until_expiry(contract, today)
    return LeaseContractRead(**data)


@router.get("/leasing/contracts", response_model=PaginatedResponse)
def list_contracts(
    db: DbDep, _=Depends(get_current_active_user),
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
    try:
        contract = services.create_contract(db, data, signed_by=user.id)
        return _to_read(contract, local_today(settings.TIMEZONE))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/leasing/contracts/{contract_id}", response_model=LeaseContractRead)
def get_contract(contract_id: int, db: DbDep, _=Depends(get_current_active_user)):
    c = crud.get_contract(db, contract_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "العقد غير موجود")
    return _to_read(c, local_today(settings.TIMEZONE))


@router.patch("/leasing/contracts/{contract_id}", response_model=LeaseContractRead)
def update_contract(contract_id: int, data: LeaseContractUpdate, db: DbDep,
                    _=Depends(get_manager_user)):
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
                _=Depends(get_cashier_user)):
    try:
        return services.pay_payment(db, payment_id, req)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/leasing/contracts/{contract_id}/apply-penalties")
def apply_penalties(contract_id: int, db: DbDep, _=Depends(get_manager_user)):
    updated = services.apply_penalties(db, contract_id)
    return {"updated": len(updated)}


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
    try:
        return services.record_cash_log(db, data, recorded_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/leasing/contracts/{contract_id}/cash-logs", response_model=list[TenantCashLogRead])
def list_cash_logs(contract_id: int, db: DbDep, _=Depends(get_current_active_user)):
    try:
        return services.list_cash_logs(db, contract_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.get("/leasing/payments/{payment_id}/receipt")
def download_receipt(payment_id: int, db: DbDep, _=Depends(get_current_active_user)):
    try:
        pdf = services.generate_rent_receipt_pdf(db, payment_id)
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename=lease-receipt-{payment_id}.pdf"},
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
