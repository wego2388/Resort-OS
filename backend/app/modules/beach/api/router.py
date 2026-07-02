"""app/modules/beach/api/router.py"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from app.core.deps import (
    DbDep, get_admin_user, get_cashier_user,
    get_current_active_user, get_manager_user, require_module,
)
from app.modules.beach import crud, services
from app.modules.beach.schemas import (
    B2BCheckinRequest, B2BContractCreate, B2BContractRead,
    BeachDailySummary, BeachInventoryRead, BeachReservationCreate,
    BeachReservationPublic, BeachReservationRead, BeachSellRequest,
    BeachSurgeSet, BeachTransactionRead,
)
from app.modules.core.schemas import PaginatedResponse

router = APIRouter(tags=["beach"])
_guard = Depends(require_module("beach"))


# ── Inventory ─────────────────────────────────────────────────────────

@router.get("/beach/inventory", response_model=BeachInventoryRead, dependencies=[_guard])
def get_inventory(
    db: DbDep,
    _=Depends(get_current_active_user),
    branch_id: int  = Query(...),
    inv_date:  date = Query(default_factory=date.today),
):
    row = crud.get_or_create_inventory(db, branch_id, inv_date)
    db.commit()
    return BeachInventoryRead.model_validate(row)


# ── Surge toggle (Manager only) ───────────────────────────────────

@router.patch("/beach/surge", response_model=BeachInventoryRead, dependencies=[_guard])
def set_surge(
    data: BeachSurgeSet, db: DbDep,
    _=Depends(get_manager_user),
    branch_id: int = Query(...),
):
    try:
        row = services.set_surge(db, branch_id, data.surge_pct, data.inv_date)
        return BeachInventoryRead.model_validate(row)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Sell ──────────────────────────────────────────────────────────────

@router.post("/beach/sell", response_model=BeachTransactionRead,
             status_code=status.HTTP_201_CREATED, dependencies=[_guard])
def sell_ticket(
    data: BeachSellRequest, db: DbDep,
    user=Depends(get_cashier_user),
    branch_id: int = Query(...),
):
    if not data.cashier_id:
        data = data.model_copy(update={"cashier_id": user.id})
    try:
        return services.sell_ticket(db, branch_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/beach/b2b-checkin", response_model=BeachTransactionRead,
             status_code=status.HTTP_201_CREATED, dependencies=[_guard])
def b2b_checkin(
    data: B2BCheckinRequest, db: DbDep,
    user=Depends(get_cashier_user),
    branch_id: int = Query(...),
):
    if not data.cashier_id:
        data = data.model_copy(update={"cashier_id": user.id})
    try:
        return services.b2b_checkin(db, branch_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Transactions ──────────────────────────────────────────────────────

@router.get("/beach/transactions", response_model=PaginatedResponse, dependencies=[_guard])
def list_transactions(
    db: DbDep, _=Depends(get_cashier_user),
    branch_id: int           = Query(...),
    tx_date:   Optional[date] = Query(None),
    page: int = Query(1, ge=1), size: int = Query(100, ge=1, le=500),
):
    items, total = crud.list_transactions(db, branch_id, tx_date, (page-1)*size, size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[BeachTransactionRead.model_validate(t) for t in items])


@router.get("/beach/transactions/{tx_id}/ticket", dependencies=[_guard])
def download_ticket(tx_id: int, db: DbDep, _=Depends(get_cashier_user)):
    try:
        pdf = services.generate_ticket_pdf(db, tx_id)
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename=beach-ticket-{tx_id}.pdf"},
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.post("/beach/transactions/{tx_id}/void",
             response_model=BeachTransactionRead, dependencies=[_guard])
def void_transaction(tx_id: int, db: DbDep, user=Depends(get_manager_user)):
    try:
        return services.void_transaction(db, tx_id, voided_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Daily Summary ─────────────────────────────────────────────────────

@router.get("/beach/summary", response_model=BeachDailySummary, dependencies=[_guard])
def daily_summary(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int  = Query(...),
    tx_date:   date = Query(default_factory=date.today),
):
    inv = crud.get_or_create_inventory(db, branch_id, tx_date)
    summary = crud.get_daily_summary(db, branch_id, tx_date)
    cap_pct = (
        min(100, int(inv.capacity_used / inv.capacity_max * 100))
        if inv.capacity_max > 0 else 100
    )
    return BeachDailySummary(
        date=tx_date,
        total_entries=summary["total_entries"],
        total_revenue=summary["total_revenue"],
        b2b_entries=summary["b2b_entries"],
        b2b_revenue=summary["b2b_revenue"],
        capacity_pct=cap_pct,
        surge_active=inv.surge_pct > 0,
        towels_rented=summary["towels_rented"],
    )


# ── Daily EOD Report ────────────────────────────────────────────────────

@router.get("/beach/eod-report", dependencies=[_guard])
def get_eod_report(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int = Query(...), report_date: Optional[date] = Query(None),
):
    """تقرير نهاية اليوم — إجمالي الدخول حسب النوع، إيرادات الفوط، مقارنة
    بالأمس وبالأسبوع الماضي."""
    return services.get_eod_report(db, branch_id, report_date)


@router.get("/beach/eod-report/pdf", dependencies=[_guard])
def download_eod_report_pdf(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int = Query(...), report_date: Optional[date] = Query(None),
):
    pdf = services.generate_eod_report_pdf(db, branch_id, report_date)
    fname = f"beach-eod-{report_date or date.today()}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={fname}"},
    )


# ── B2B Contracts ─────────────────────────────────────────────────────

@router.get("/beach/b2b-contracts", response_model=list[B2BContractRead], dependencies=[_guard])
def list_contracts(db: DbDep, _=Depends(get_manager_user),
                   branch_id: int = Query(...), active_only: bool = Query(True)):
    return [B2BContractRead.model_validate(c)
            for c in crud.list_b2b_contracts(db, branch_id, active_only)]


@router.get("/beach/b2b-contracts/status", dependencies=[_guard])
def get_b2b_quota_status(
    db: DbDep, _=Depends(get_current_active_user),
    branch_id: int = Query(...), day: Optional[date] = Query(None),
):
    """حالة حصة كل فندق B2B اليوم — بيظهر quota_warning (≤5 متبقين) لعرضه
    كتنبيه في اللوحة الحيّة."""
    return services.get_b2b_quota_status(db, branch_id, day)


# ── Live Dashboard ────────────────────────────────────────────────────

@router.get("/beach/live-dashboard", dependencies=[_guard])
def get_live_dashboard(
    db: DbDep, _=Depends(get_current_active_user),
    branch_id: int = Query(...),
):
    """السعة الحالية + حصص فنادق B2B + تنبيهات — للوحة حيّة (polling كل شوية)."""
    inv = crud.get_or_create_inventory(db, branch_id, date.today())
    db.commit()
    b2b_status = services.get_b2b_quota_status(db, branch_id)
    alerts = [s for s in b2b_status if s["quota_warning"]]
    return {
        "capacity_used":   inv.capacity_used,
        "capacity_max":    inv.capacity_max,
        "capacity_pct":    (min(100, int(inv.capacity_used / inv.capacity_max * 100))
                            if inv.capacity_max > 0 else 100),
        "towels_available": inv.towels_available,
        "towels_used":       inv.towels_used,
        "surge_active":      inv.surge_pct > 0,
        "surge_pct":         float(inv.surge_pct),
        "b2b_contracts":     b2b_status,
        "quota_alerts":      alerts,
    }


@router.post("/beach/b2b-contracts", response_model=B2BContractRead,
             status_code=status.HTTP_201_CREATED, dependencies=[_guard])
def create_contract(data: B2BContractCreate, db: DbDep, _=Depends(get_admin_user)):
    obj = crud.create_b2b_contract(db, data)
    db.commit(); db.refresh(obj)
    return B2BContractRead.model_validate(obj)


# ── Reservations ──────────────────────────────────────────────────────

@router.get("/beach/reservations", response_model=PaginatedResponse, dependencies=[_guard])
def list_reservations(
    db: DbDep, _=Depends(get_cashier_user),
    branch_id:    int           = Query(...),
    res_date:     Optional[date] = Query(None),
    status_filter:Optional[str]  = Query(None, alias="status"),
    page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
):
    items, total = crud.list_reservations(db, branch_id, res_date, status_filter,
                                          (page-1)*size, size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[BeachReservationRead.model_validate(r) for r in items])


@router.post("/beach/reservations", response_model=BeachReservationRead,
             status_code=status.HTTP_201_CREATED, dependencies=[_guard])
def create_reservation(data: BeachReservationCreate, db: DbDep, _=Depends(get_cashier_user)):
    try:
        return services.create_reservation(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── QR Check-in ───────────────────────────────────────────────────────
# صفحة الـ QR (frontend/apps/qr) بتفتح بدون تسجيل دخول عشان تعرض بيانات
# الحجز (public) — بس تسجيل الدخول الفعلي (checkin) بيستهلك سعة/فوط حقيقية
# فلازم يكون كاشير مسجّل دخول (زي كل عمليات البيع التانية في الموديول ده).

@router.get("/beach/reservations/{reservation_id}/public", response_model=BeachReservationPublic)
def get_reservation_public(reservation_id: int, db: DbDep):
    res = crud.get_reservation(db, reservation_id)
    if not res:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"الحجز {reservation_id} غير موجود")
    return BeachReservationPublic.model_validate(res)


@router.post("/beach/reservations/{reservation_id}/checkin",
             response_model=BeachReservationRead, dependencies=[_guard])
def checkin_reservation(reservation_id: int, db: DbDep, user=Depends(get_cashier_user)):
    try:
        return services.check_in_reservation(db, reservation_id, cashier_id=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
