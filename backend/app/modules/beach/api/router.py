"""app/modules/beach/api/router.py"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import (
    APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect,
    status,
)
from fastapi.responses import Response

from app.core.config import settings
from app.core.deps import (
    DbDep, get_admin_user, get_cashier_user,
    get_current_active_user, get_manager_user, get_websocket_user, require_permission,
)
from app.modules.beach import crud, services
from app.modules.beach.schemas import (
    B2BCheckinRequest, B2BContractCreate, B2BContractRead, B2BContractUpdate,
    B2BSettleRequest, BeachDailySummary, BeachInventoryRead,
    BeachLocationBulkCreate, BeachLocationBulkRemove, BeachLocationCheckinRequest,
    BeachLocationRead, BeachLocationUpdate,
    BeachReservationCreate, BeachReservationPublic, BeachReservationRead,
    BeachSellRequest, BeachSurgeSet, BeachTransactionRead,
    VoidTransactionRequest,
)
from app.modules.core.schemas import PaginatedResponse
from app.resort_os.timezone_utils import local_today

router = APIRouter(tags=["beach"])


# ── WebSocket Live Map Manager ──────────────────────────────────────────
# نفس نمط restaurant_manager (restaurant/api/router.py) وalerts_manager
# (core/api/router.py) بالظبط — بث بسيط بالفرع، من غير أي بروتوكول ثنائي
# الاتجاه حقيقي. auth بقى موحّد عبر get_websocket_user (app/core/deps.py،
# wagdy.md A-01) — ?token= JWT صالح إجباري قبل .accept().

class BeachMapConnectionManager:
    def __init__(self):
        self.active: dict[str, list[WebSocket]] = {}  # branch_id → قائمة اتصالات WS

    async def connect(self, ws: WebSocket, branch_id: str):
        await ws.accept()
        self.active.setdefault(branch_id, []).append(ws)

    def disconnect(self, ws: WebSocket, branch_id: str):
        connections = self.active.get(branch_id, [])
        if ws in connections:
            connections.remove(ws)

    async def broadcast(self, branch_id: str, data: dict):
        for ws in list(self.active.get(branch_id, [])):
            try:
                await ws.send_json(data)
            except Exception:
                pass


beach_map_manager = BeachMapConnectionManager()


@router.websocket("/beach/ws/map/{branch_id}")
async def beach_map_websocket(ws: WebSocket, branch_id: int, db: DbDep):
    """اتصال WebSocket لطاقم الشاطئ — بث تحديثات الخريطة الحية (تشيك-إن/
    تشيك-أوت/إضافة أو حذف مواقع/تغيير حالة) لحظيًا لكل الكاشيرين/المشرفين
    الفاتحين الشاشة في نفس الوقت. بيرد بـ pong كـ heartbeat فقط، زي KDS
    وتنبيهات الضيوف. محتاج ?token= JWT صالح بمستوى كاشير+."""
    if not await get_websocket_user(ws, db, min_level=40):
        return
    await beach_map_manager.connect(ws, str(branch_id))
    try:
        while True:
            await ws.receive_text()
            await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        beach_map_manager.disconnect(ws, str(branch_id))


def _business_today() -> date:
    """تاريخ "النهاردة" بتوقيت المنتجع (settings.TIMEZONE) — مش توقيت
    السيرفر. ⚠️ باج حقيقي كان هنا: كل حدود اليوم في الشاطئ (إعادة ضبط
    السعة اليومية، تصفير حصة B2B، تقرير نهاية اليوم) كانت بتتحسب بـ
    `date.today()` العادية (توقيت نظام تشغيل السيرفر، UTC غالبًا في
    الإنتاج) بدل توقيت القاهرة — يعني في أي وقت بين منتصف الليل بتوقيت
    القاهرة والساعة 3 صباحًا (فرق UTC+3)، أي عملية بيع/تشيك-إن كانت
    بتتسجّل على `inventory_date`/`day` اليوم اللي فات بدل النهاردة فعليًا:
    سعة اليوم الجديد ما كانتش اتصفرت، وحصة الفندق القديمة كانت لسه سارية.
    نفس فئة الباج اللي اتكشفت قبل كده في HR/PMS/Timeshare — beach كان
    الموديول الوحيد الباقي من غير الإصلاح ده."""
    return local_today(settings.TIMEZONE)


# ── Inventory ─────────────────────────────────────────────────────────

@router.get("/beach/inventory", response_model=BeachInventoryRead)
def get_inventory(
    db: DbDep,
    _=Depends(get_current_active_user),
    branch_id: int  = Query(...),
    inv_date:  date = Query(default_factory=_business_today),
):
    row = crud.get_or_create_inventory(db, branch_id, inv_date)
    db.commit()
    prices = services.get_base_prices(db, branch_id)
    data = {
        "id": row.id, "branch_id": row.branch_id, "inventory_date": row.inventory_date,
        "capacity_max": row.capacity_max, "capacity_used": row.capacity_used,
        "towels_total": row.towels_total, "towels_available": row.towels_available,
        "towels_used": row.towels_used, "surge_pct": row.surge_pct,
        "adult_price": prices["entry"], "child_price": prices["entry_child"],
        "resident_price": prices["entry_resident"], "towel_price": prices["towel_rent"],
    }
    return BeachInventoryRead.model_validate(data)


# ── Surge toggle (Manager only) ───────────────────────────────────

@router.patch("/beach/surge", response_model=BeachInventoryRead)
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
             status_code=status.HTTP_201_CREATED)
async def sell_ticket(
    data: BeachSellRequest, db: DbDep,
    user=Depends(get_cashier_user),
    branch_id: int = Query(...),
):
    if not data.cashier_id:
        data = data.model_copy(update={"cashier_id": user.id})
    try:
        tx = services.sell_ticket(db, branch_id, data)
    except services.BeachConcurrencyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    if tx.shift_id:
        from app.modules.finance.api.router import shift_manager  # noqa: PLC0415
        await shift_manager.broadcast(str(tx.branch_id), {
            "type": "shift_sale", "shift_id": tx.shift_id,
        })
    return tx


@router.post("/beach/b2b-checkin", response_model=BeachTransactionRead,
             status_code=status.HTTP_201_CREATED)
def b2b_checkin(
    data: B2BCheckinRequest, db: DbDep,
    user=Depends(get_cashier_user),
    branch_id: int = Query(...),
):
    if not data.cashier_id:
        data = data.model_copy(update={"cashier_id": user.id})
    try:
        return services.b2b_checkin(db, branch_id, data)
    except services.BeachConcurrencyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Transactions ──────────────────────────────────────────────────────

@router.get("/beach/transactions", response_model=PaginatedResponse)
def list_transactions(
    db: DbDep, _=Depends(get_cashier_user),
    branch_id: int           = Query(...),
    tx_date:   Optional[date] = Query(None),
    page: int = Query(1, ge=1), size: int = Query(100, ge=1, le=500),
):
    items, total = crud.list_transactions(db, branch_id, tx_date, (page-1)*size, size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[BeachTransactionRead.model_validate(t) for t in items])


@router.get("/beach/transactions/{tx_id}/ticket")
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
             dependencies=[Depends(require_permission("beach.void_transaction", "execute", min_role_level=60))],
             response_model=BeachTransactionRead)
def void_transaction(tx_id: int, data: VoidTransactionRequest, db: DbDep, user=Depends(get_current_active_user)):
    try:
        return services.void_transaction(db, tx_id, voided_by=user.id, reason=data.reason)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Daily Summary ─────────────────────────────────────────────────────

@router.get("/beach/summary", response_model=BeachDailySummary)
def daily_summary(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int  = Query(...),
    tx_date:   date = Query(default_factory=_business_today),
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

@router.get("/beach/eod-report")
def get_eod_report(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int = Query(...), report_date: Optional[date] = Query(None),
):
    """تقرير نهاية اليوم — إجمالي الدخول حسب النوع، إيرادات الفوط، مقارنة
    بالأمس وبالأسبوع الماضي."""
    return services.get_eod_report(db, branch_id, report_date)


@router.get("/beach/eod-report/pdf")
def download_eod_report_pdf(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int = Query(...), report_date: Optional[date] = Query(None),
):
    pdf = services.generate_eod_report_pdf(db, branch_id, report_date)
    fname = f"beach-eod-{report_date or _business_today()}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={fname}"},
    )


# ── B2B Contracts ─────────────────────────────────────────────────────

@router.get("/beach/b2b-contracts", response_model=list[B2BContractRead])
def list_contracts(db: DbDep, _=Depends(get_manager_user),
                   branch_id: int = Query(...), active_only: bool = Query(True)):
    return [B2BContractRead.model_validate(c)
            for c in crud.list_b2b_contracts(db, branch_id, active_only)]


@router.get("/beach/b2b-contracts/status")
def get_b2b_quota_status(
    db: DbDep, _=Depends(get_current_active_user),
    branch_id: int = Query(...), day: Optional[date] = Query(None),
):
    """حالة حصة كل فندق B2B اليوم — بيظهر quota_warning (≤5 متبقين) لعرضه
    كتنبيه في اللوحة الحيّة."""
    return services.get_b2b_quota_status(db, branch_id, day)


# ── Live Dashboard ────────────────────────────────────────────────────

@router.get("/beach/live-dashboard")
def get_live_dashboard(
    db: DbDep, _=Depends(get_current_active_user),
    branch_id: int = Query(...),
):
    """السعة الحالية + حصص فنادق B2B + تنبيهات — للوحة حيّة (polling كل شوية)."""
    inv = crud.get_or_create_inventory(db, branch_id, _business_today())
    db.commit()
    b2b_status = services.get_b2b_quota_status(db, branch_id)
    alerts = [s for s in b2b_status if s["quota_warning"]]
    overdue_alerts = [s for s in b2b_status if s["is_overdue"]]
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
        "overdue_alerts":    overdue_alerts,
    }


@router.post("/beach/b2b-contracts", response_model=B2BContractRead,
             status_code=status.HTTP_201_CREATED)
def create_contract(data: B2BContractCreate, db: DbDep, _=Depends(get_admin_user)):
    obj = crud.create_b2b_contract(db, data)
    db.commit(); db.refresh(obj)
    return B2BContractRead.model_validate(obj)


@router.patch("/beach/b2b-contracts/{contract_id}", response_model=B2BContractRead)
def update_contract_credit(
    contract_id: int, data: B2BContractUpdate, db: DbDep, _=Depends(get_admin_user),
):
    """تعديل إعدادات ائتمان عقد B2B (حد الائتمان/مهلة السداد) — راجع شاشة
    إدارة عقود B2B في الفرونت إند."""
    obj = crud.get_b2b_contract(db, contract_id)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"العقد {contract_id} غير موجود")
    fields = data.model_dump(exclude_unset=True)
    obj = crud.update_b2b_contract_credit(
        db, obj,
        credit_limit=fields.get("credit_limit"),
        payment_terms_days=fields.get("payment_terms_days"),
        credit_limit_set="credit_limit" in fields,
    )
    db.commit(); db.refresh(obj)
    return B2BContractRead.model_validate(obj)


@router.post("/beach/b2b-contracts/{contract_id}/settle", response_model=B2BContractRead)
def settle_contract(
    contract_id: int, data: B2BSettleRequest, db: DbDep, _=Depends(get_manager_user),
):
    """يسجّل إن رصيد الفندق الشريك اتحصّل (تسوية دورية) — بيصفّر الرصيد
    المستحق فعليًا وبيلغي علم التأخر."""
    try:
        obj = services.settle_b2b_contract(db, contract_id, data.settled_through)
        return B2BContractRead.model_validate(obj)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Reservations ──────────────────────────────────────────────────────

@router.get("/beach/reservations", response_model=PaginatedResponse)
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
             status_code=status.HTTP_201_CREATED)
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
             response_model=BeachReservationRead)
def checkin_reservation(reservation_id: int, db: DbDep, user=Depends(get_cashier_user)):
    try:
        return services.check_in_reservation(db, reservation_id, cashier_id=user.id)
    except services.BeachConcurrencyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Beach Locations (live map) ────────────────────────────────────────
# شاشة "خريطة الشاطئ الحية" (/pos/beach-map) — يشوفها الكاشير/المشرف طول
# اليوم، مقابلة لـ TablesView.vue بتاعة المطعم بس لمواقع الشاطئ الفعلية
# (شمسية/برجولة...) مع حالة ضيف حقيقية بدل مجرد "مشغولة/فاضية".

@router.get("/beach/locations", response_model=list[BeachLocationRead])
def list_locations(
    db: DbDep, _=Depends(get_cashier_user),
    branch_id: int = Query(...), location_type: Optional[str] = Query(None),
):
    return [BeachLocationRead.model_validate(loc)
            for loc in services.list_locations(db, branch_id, location_type)]


@router.post("/beach/locations/bulk", response_model=list[BeachLocationRead],
             status_code=status.HTTP_201_CREATED)
async def bulk_add_locations(data: BeachLocationBulkCreate, db: DbDep, _=Depends(get_manager_user)):
    try:
        created = services.bulk_add_locations(db, data.branch_id, data.location_type, data.count)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    await beach_map_manager.broadcast(str(data.branch_id), {"type": "locations_changed"})
    return [BeachLocationRead.model_validate(loc) for loc in created]


@router.post("/beach/locations/reduce", response_model=list[BeachLocationRead])
async def reduce_locations(data: BeachLocationBulkRemove, db: DbDep, _=Depends(get_manager_user)):
    try:
        removed = services.bulk_remove_locations(db, data.branch_id, data.location_type, data.count)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    await beach_map_manager.broadcast(str(data.branch_id), {"type": "locations_changed"})
    return [BeachLocationRead.model_validate(loc) for loc in removed]


@router.patch("/beach/locations/{location_id}", response_model=BeachLocationRead)
async def update_location(
    location_id: int, data: BeachLocationUpdate, db: DbDep,
    _=Depends(get_manager_user), branch_id: int = Query(...),
):
    try:
        loc = services.update_location(
            db, location_id,
            status=data.status, grid_row=data.grid_row, grid_col=data.grid_col,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    await beach_map_manager.broadcast(str(branch_id), {"type": "map_update", "location": BeachLocationRead.model_validate(loc).model_dump(mode="json")})
    return loc


@router.post("/beach/locations/{location_id}/checkin", response_model=BeachLocationRead,
             status_code=status.HTTP_201_CREATED)
async def checkin_location(
    location_id: int, data: BeachLocationCheckinRequest, db: DbDep,
    user=Depends(get_cashier_user), branch_id: int = Query(...),
):
    if not data.cashier_id:
        data = data.model_copy(update={"cashier_id": user.id})
    try:
        loc = services.checkin_location(db, branch_id, location_id, data, cashier_id=data.cashier_id)
    except services.BeachConcurrencyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    await beach_map_manager.broadcast(str(branch_id), {"type": "map_update", "location": BeachLocationRead.model_validate(loc).model_dump(mode="json")})
    return loc


@router.post("/beach/locations/{location_id}/checkout", response_model=BeachLocationRead)
async def checkout_location(
    location_id: int, db: DbDep,
    user=Depends(get_cashier_user), branch_id: int = Query(...),
):
    try:
        loc = services.checkout_location(db, branch_id, location_id, cashier_id=user.id)
    except services.BeachConcurrencyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    await beach_map_manager.broadcast(str(branch_id), {"type": "map_update", "location": BeachLocationRead.model_validate(loc).model_dump(mode="json")})
    return loc
