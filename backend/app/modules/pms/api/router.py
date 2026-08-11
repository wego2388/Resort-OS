"""app/modules/pms/api/router.py"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import (
    APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect,
    status,
)

from app.core.deps import (
    DbDep, get_current_active_user, get_websocket_user, require_permission,
)
from app.modules.pms import crud, services
from app.modules.core import services as core_services
from app.modules.finance.services import FinancialConfigurationError
from app.modules.pms.schemas import (
    BookingCreate, BookingRead, BundleBookingCreate, CheckinRequest, EarlyLateRequest,
    HousekeepingTaskRead, HousekeepingTaskStatusUpdate,
    NightAuditLogRead, RatePlanCreate, RatePlanRead, RatePlanUpdate, RoomBundleRead, RoomCreate,
    RoomRead, RoomStatusUpdate, RoomTypeCreate, RoomTypeRead,
)
from app.modules.core.schemas import PaginatedResponse

router = APIRouter(tags=["pms"])


def _assert_pms_branch(db, user, branch_id: int, action_desc: str) -> None:
    """PMS branch boundary shared by query/body/object routes.

    Permission checks answer *what* the account may do; this check answers
    *where* it may do it. Only an active super-admin has global branch access.
    """
    try:
        core_services.assert_branch_access(db, user, branch_id, action_desc)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))


def _booking_for_access(db, user, booking_id: int, action_desc: str):
    booking = crud.get_booking(db, booking_id)
    if not booking:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الحجز غير موجود")
    _assert_pms_branch(db, user, booking.branch_id, action_desc)
    return booking


def _rate_plan_for_access(db, user, plan_id: int, action_desc: str):
    plan = crud.get_rate_plan(db, plan_id)
    if not plan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "خطة الأسعار غير موجودة")
    _assert_pms_branch(db, user, plan.branch_id, action_desc)
    return plan


# ── WebSocket Room Map Manager ──────────────────────────────────────────
# نفس نمط beach_map_manager (beach/api/router.py) بالظبط — بث بسيط بالفرع،
# من غير أي بروتوكول ثنائي الاتجاه حقيقي. auth بقى موحّد عبر get_websocket_user
# (app/core/deps.py، wagdy.md A-01) — ?token= JWT صالح إجباري قبل .accept().
#
# الفجوة اللي بيسدّها ده: RoomsView.vue (خريطة الغرف) كانت بتجيب حالة الغرف
# مرة واحدة عند فتح الشاشة + polling كل 60 ثانية بس — لو كاشير تاني سجّل
# دخول/خروج ضيف أو غيّر حالة تنظيف، شاشة المدير الفاتحها من قبل كانت بتفضل
# قديمة لحد الـ polling التالي أو تحديث يدوي.

class PmsRoomsConnectionManager:
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


pms_rooms_manager = PmsRoomsConnectionManager()


@router.websocket("/pms/ws/rooms/{branch_id}")
async def pms_rooms_websocket(ws: WebSocket, branch_id: int, db: DbDep):
    """اتصال WebSocket لخريطة الغرف الحية (RoomsView.vue) — بث "rooms_changed"
    لأي تغيير في حالة الغرف (تشيك-إن/تشيك-أوت/إلغاء حجز/تغيير حالة يدوي/
    تحديث مهمة تنظيف) لكل الموظفين الفاتحين الشاشة في نفس الوقت. الرسالة
    عامة عمدًا (مفيش بيانات غرفة كاملة داخلها) — الشاشة أصلاً عندها
    fetchRooms() اللي بتجيب الغرف + الحجوزات الحالية النشطة مع بعض من
    endpoint-ين مختلفين، فمفيش داعي نبني DTO مختلط (Room+Booking) جديد
    للبث نفسه؛ نفس فكرة "locations_changed" في beach/api/router.py (اللي
    فيها كمان تغيير مركّب مش سهل تمثيله في رسالة واحدة). بيرد بـ pong
    كـ heartbeat فقط، زي KDS وخريطة الشاطئ. محتاج ?token= JWT صالح بمستوى
    كاشير+ (نفس مستوى create_booking تحت)."""
    user = await get_websocket_user(ws, db, min_level=40)
    if not user:
        return
    try:
        core_services.assert_branch_access(db, user, branch_id, "متابعة خريطة غرف")
    except PermissionError:
        await ws.close(code=4403)
        return
    await pms_rooms_manager.connect(ws, str(branch_id))
    try:
        while True:
            await ws.receive_text()
            await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pms_rooms_manager.disconnect(ws, str(branch_id))


# ── Room Types ────────────────────────────────────────────────────────

@router.get(
    "/pms/room-types",
    response_model=list[RoomTypeRead],
    dependencies=[Depends(require_permission("pms.rooms", "view", min_role_level=40))],
)
def list_room_types(
    db: DbDep,
    branch_id: int = Query(...),
    user=Depends(get_current_active_user),
):
    _assert_pms_branch(db, user, branch_id, "عرض أنواع غرف")
    return [RoomTypeRead.model_validate(rt) for rt in crud.list_room_types(db, branch_id)]


@router.post(
    "/pms/room-types",
    response_model=RoomTypeRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("pms.room_configuration", "manage", min_role_level=80))],
)
def create_room_type(
    data: RoomTypeCreate,
    db: DbDep,
    user=Depends(get_current_active_user),
):
    _assert_pms_branch(db, user, data.branch_id, "إنشاء نوع غرفة")
    obj = crud.create_room_type(db, data)
    db.commit(); db.refresh(obj)
    return RoomTypeRead.model_validate(obj)


# ══════════════════════════════════════════════════════════════════════
# Public Endpoint — للموقع العام (بدون auth)
# ══════════════════════════════════════════════════════════════════════
# ⚠️ عمداً بدون authentication — نفس نمط restaurant/public/menu:
#   GET /pms/public/room-types → عرض أنواع الغرف للزوار (read-only)
# أمان: rate limited بالـ middleware (30 req/60s per IP، app/core/rate_limit.py)
#        لا يوجد تعديل أو حذف من هنا — read فقط، ومفيش حقول حساسة في RoomTypeRead
#        (name/name_ar/base_rate/max_occupancy/amenities — كل ده أصلاً معروض
#        للزوار على أي موقع حجوزات حقيقي).
# ══════════════════════════════════════════════════════════════════════

@router.get(
    "/pms/public/room-types",
    response_model=list[RoomTypeRead],
    tags=["pms-public"],
    summary="أنواع الغرف للموقع العام — بدون auth",
)
def get_public_room_types(db: DbDep, branch_id: int = Query(...)):
    return [RoomTypeRead.model_validate(rt) for rt in crud.list_room_types(db, branch_id, active_only=True)]


# ── Rooms ─────────────────────────────────────────────────────────────

@router.get(
    "/pms/rooms",
    response_model=list[RoomRead],
    dependencies=[Depends(require_permission("pms.rooms", "view", min_role_level=40))],
)
def list_rooms(
    db: DbDep,
    branch_id:    int           = Query(...),
    status_filter: Optional[str] = Query(None, alias="status"),
    room_type_id:  Optional[int] = Query(None),
    user=Depends(get_current_active_user),
):
    _assert_pms_branch(db, user, branch_id, "عرض الغرف")
    return [RoomRead.model_validate(r) for r in crud.list_rooms(db, branch_id, status_filter, room_type_id)]


@router.get(
    "/pms/rooms/available",
    response_model=list[RoomRead],
    dependencies=[Depends(require_permission("pms.rooms", "view", min_role_level=40))],
)
def available_rooms(
    db: DbDep,
    branch_id:    int           = Query(...),
    check_in:     date          = Query(...),
    check_out:    date          = Query(...),
    room_type_id: Optional[int] = Query(None),
    user=Depends(get_current_active_user),
):
    _assert_pms_branch(db, user, branch_id, "عرض إتاحة الغرف")
    return [RoomRead.model_validate(r)
            for r in crud.get_available_rooms(db, branch_id, check_in, check_out, room_type_id)]


@router.post(
    "/pms/rooms",
    response_model=RoomRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("pms.room_configuration", "manage", min_role_level=80))],
)
def create_room(
    data: RoomCreate,
    db: DbDep,
    user=Depends(get_current_active_user),
):
    _assert_pms_branch(db, user, data.branch_id, "إنشاء غرفة")
    room_type = crud.get_room_type(db, data.room_type_id)
    if not room_type or room_type.branch_id != data.branch_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "نوع الغرفة غير موجود في الفرع المطلوب",
        )
    obj = crud.create_room(db, data)
    db.commit(); db.refresh(obj)
    return RoomRead.model_validate(obj)


@router.patch(
    "/pms/rooms/{room_id}/status",
    response_model=RoomRead,
    dependencies=[Depends(require_permission("pms.rooms", "update_status", min_role_level=60))],
)
async def update_room_status(
    room_id: int,
    data: RoomStatusUpdate,
    db: DbDep,
    user=Depends(get_current_active_user),
):
    room = crud.get_room(db, room_id)
    if not room:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الغرفة غير موجودة")
    _assert_pms_branch(db, user, room.branch_id, "تحديث حالة غرفة")
    crud.update_room_status(db, room, data.status, data.notes)
    db.commit(); db.refresh(room)
    await pms_rooms_manager.broadcast(str(room.branch_id), {"type": "rooms_changed"})
    return RoomRead.model_validate(room)


# ── Bookings ──────────────────────────────────────────────────────────

@router.get(
    "/pms/bookings",
    response_model=PaginatedResponse,
    dependencies=[Depends(require_permission("pms.bookings", "view", min_role_level=40))],
)
def list_bookings(
    db: DbDep,
    branch_id:     int           = Query(...),
    status_filter: Optional[str] = Query(None, alias="status"),
    check_in_from: Optional[date] = Query(None),
    check_in_to:   Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user=Depends(get_current_active_user),
):
    _assert_pms_branch(db, user, branch_id, "عرض حجوزات")
    items, total = crud.list_bookings(db, branch_id, status_filter,
                                      check_in_from, check_in_to,
                                      (page-1)*size, size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[BookingRead.model_validate(b) for b in items])


@router.post(
    "/pms/bookings",
    response_model=BookingRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("pms.bookings", "create", min_role_level=40))],
)
async def create_booking(
    data: BookingCreate,
    db: DbDep,
    user=Depends(get_current_active_user),
):
    # ⚠️ باج صلاحيات حقيقي اتكشف حي (2026-07-06، اختبار استقبال كامل):
    # إنشاء حجز/تسجيل دخول/تسجيل خروج كانوا الثلاثة محتاجين get_manager_user
    # (level 60+) — يعني موظف الاستقبال (receptionist، level 40) اللي شغلته
    # الأساسي بالظبط هو الثلاث عمليات دي، كان عمليًا يشوف زرار "تسجيل دخول"
    # في الشاشة ويضغط عليه فيرجّعله 403 كل مرة، من غير أي طريقة حقيقية
    # يسجّل بيها نزيل. نفس فئة الباج الموثّقة في §18/CLAUDE.md لتحصيل قسط
    # التايم شير (كانت محتاجة get_manager_user برضه رغم إن الكاشير level 40
    # المفروض يقدر يحصّل) — هنا get_cashier_user (level 40+) هو الحد الأدنى
    # الصحيح فعليًا لعمليات الاستقبال اليومية.
    _assert_pms_branch(db, user, data.branch_id, "إنشاء حجز")
    try:
        booking = services.create_booking(db, data)
    except services.BookingConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    await pms_rooms_manager.broadcast(str(data.branch_id), {"type": "rooms_changed"})
    return booking


@router.get(
    "/pms/room-bundles",
    response_model=list[RoomBundleRead],
    dependencies=[Depends(require_permission("pms.bookings", "view", min_role_level=40))],
)
def list_room_bundles(
    db: DbDep,
    branch_id: int = Query(...),
    active_only: bool = Query(True),
    user=Depends(get_current_active_user),
):
    _assert_pms_branch(db, user, branch_id, "عرض باقات الحجز")
    bundles = crud.list_room_bundles(db, branch_id, active_only)
    return [RoomBundleRead.model_validate(b) for b in bundles]


@router.post(
    "/pms/bookings/bundle",
    response_model=BookingRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("pms.bookings", "create", min_role_level=40))],
)
async def create_bundle_booking(
    data: BundleBookingCreate,
    db: DbDep,
    user=Depends(get_current_active_user),
):
    """حجز باقة Family Compound 6P — راجع services.create_bundle_booking
    للمنطق الذري الكامل (نفس مستوى صلاحية الحجز العادي، pms.bookings/create)."""
    _assert_pms_branch(db, user, data.branch_id, "إنشاء حجز باقة")
    try:
        booking = services.create_bundle_booking(db, data)
    except services.BookingConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    await pms_rooms_manager.broadcast(str(data.branch_id), {"type": "rooms_changed"})
    return booking


@router.get(
    "/pms/bookings/{booking_id}",
    response_model=BookingRead,
    dependencies=[Depends(require_permission("pms.bookings", "view", min_role_level=40))],
)
def get_booking(
    booking_id: int,
    db: DbDep,
    user=Depends(get_current_active_user),
):
    b = _booking_for_access(db, user, booking_id, "عرض حجز")
    return BookingRead.model_validate(b)


@router.post(
    "/pms/bookings/{booking_id}/checkin",
    response_model=BookingRead,
    dependencies=[Depends(require_permission("pms.bookings", "check_in", min_role_level=40))],
)
async def checkin(
    booking_id: int,
    db: DbDep,
    body: Optional[CheckinRequest] = None,
    user=Depends(get_current_active_user),
):
    _booking_for_access(db, user, booking_id, "تسجيل وصول حجز")
    try:
        booking = services.checkin_booking(
            db, booking_id,
            id_number=body.id_number if body else None,
            payment_method=body.payment_method if body else None,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    await pms_rooms_manager.broadcast(str(booking.branch_id), {"type": "rooms_changed"})
    return booking


@router.post(
    "/pms/bookings/{booking_id}/checkout",
    response_model=BookingRead,
    dependencies=[Depends(require_permission("pms.bookings", "check_out", min_role_level=40))],
)
async def checkout(
    booking_id: int,
    db: DbDep,
    user=Depends(get_current_active_user),
):
    _booking_for_access(db, user, booking_id, "تسجيل مغادرة حجز")
    try:
        booking = services.checkout_booking(db, booking_id)
    except FinancialConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {
            "code": "FINANCIAL_CONFIGURATION_ERROR", "message": str(exc),
        })
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    await pms_rooms_manager.broadcast(str(booking.branch_id), {"type": "rooms_changed"})
    return booking


@router.post("/pms/bookings/{booking_id}/cancel",
             dependencies=[Depends(require_permission("pms.cancel_booking", "execute", min_role_level=60))],
             response_model=BookingRead)
async def cancel_booking(booking_id: int, db: DbDep, user=Depends(get_current_active_user)):
    _booking_for_access(db, user, booking_id, "إلغاء حجز")
    try:
        booking = services.cancel_booking(db, booking_id, cancelled_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    await pms_rooms_manager.broadcast(str(booking.branch_id), {"type": "rooms_changed"})
    return booking



@router.post(
    "/pms/bookings/{booking_id}/early-late",
    response_model=BookingRead,
    summary="طلب وصول مبكر أو مغادرة متأخرة",
    dependencies=[Depends(require_permission("pms.bookings", "early_late", min_role_level=40))],
)
def request_early_late(
    booking_id: int, data: EarlyLateRequest,
    db: DbDep,
    user=Depends(get_current_active_user),
):
    """يسجّل وصول مبكر و/أو مغادرة متأخرة على الحجز.
    لو charge > 0 بيضيف FolioCharge تلقائياً على حساب الضيف.
    """
    _booking_for_access(db, user, booking_id, "تعديل موعد حجز")
    try:
        return services.request_early_late(db, booking_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Housekeeping ──────────────────────────────────────────────────────
# frontend/apps/ops/src/views/HousekeepingView.vue بينادي على الـ endpoints
# دول، والـ crud/model كانوا موجودين من زمان (checkout_booking بيعمل
# HousekeepingTask تلقائياً) — بس مفيش route كان متوصّل، فكان 404 حقيقي
# في الإنتاج زي حالة GET /restaurant/menu/categories المذكورة في § 11.6.

@router.get(
    "/pms/housekeeping/tasks",
    response_model=list[HousekeepingTaskRead],
    dependencies=[Depends(require_permission("pms.housekeeping", "view", min_role_level=40))],
)
def list_housekeeping_tasks(
    db: DbDep,
    branch_id: int = Query(...),
    status_filter: Optional[str] = Query(None, alias="status"),
    room_id: Optional[int] = Query(None),
    user=Depends(get_current_active_user),
):
    _assert_pms_branch(db, user, branch_id, "عرض مهام التنظيف")
    return [HousekeepingTaskRead.model_validate(t)
            for t in crud.list_housekeeping_tasks(db, branch_id, status_filter, room_id)]


@router.patch(
    "/pms/housekeeping/tasks/{task_id}",
    response_model=HousekeepingTaskRead,
    dependencies=[Depends(require_permission("pms.housekeeping", "update", min_role_level=40))],
)
async def update_housekeeping_task_status(
    task_id: int, data: HousekeepingTaskStatusUpdate, db: DbDep,
    user=Depends(get_current_active_user),
):
    task_for_access = crud.get_housekeeping_task(db, task_id)
    if not task_for_access:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"مهمة التنظيف {task_id} غير موجودة")
    _assert_pms_branch(db, user, task_for_access.branch_id, "تحديث مهمة تنظيف")
    try:
        task = services.update_housekeeping_task_status(
            db, task_id, data.status, data.notes, data.assigned_to,
        )
    except ValueError as exc:
        # The object was already loaded above. Remaining failures are invalid
        # cross-branch relationships or state transitions, not "not found".
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    await pms_rooms_manager.broadcast(str(task.branch_id), {"type": "rooms_changed"})
    return HousekeepingTaskRead.model_validate(task)


# ── Rate Plans ────────────────────────────────────────────────────────
# ⚠️ باج "الموديل موجود، الـ API صفر" حقيقي كان هنا: RatePlan (موسمية —
# high-season override/multiplier) كان عنده model + crud كاملين من زمان
# (create_rate_plan/list_rate_plans/get_rate_plan) بدون أي schema ولا أي
# route متوصّل — يعني مستحيل تعمل خطة أسعار موسمية عن طريق الـ API خالص،
# نفس فئة باج CallNote/RotaTemplate/RevenueAuditLog اللي اتصلحت قبل كده.
# ⚠️ متابعة حقيقية للباج ده (نفس اليوم): توصيل الـ API لوحده ماكانش كافي —
# create_booking (POST /pms/bookings) كانت لسه بتسعّر كل غرفة بـ
# room_type.base_rate الخام دايمًا، من غير أي طريقة تدّي الخطة فرصة تتطبّق.
# BookingCreate.rate_plan_id + services._resolve_rate_plan/_room_rate_for
# هما اللي بيوصّلوا الخطة فعليًا للسعر النهائي دلوقتي.

@router.get(
    "/pms/rate-plans",
    response_model=list[RatePlanRead],
    dependencies=[Depends(require_permission("pms.rate_plans", "view", min_role_level=40))],
)
def list_rate_plans(
    db: DbDep,
    branch_id:    int           = Query(...),
    room_type_id: Optional[int] = Query(None),
    active_only:  bool          = Query(True),
    user=Depends(get_current_active_user),
):
    _assert_pms_branch(db, user, branch_id, "عرض خطط الأسعار")
    return [RatePlanRead.model_validate(p)
            for p in crud.list_rate_plans(db, branch_id, active_only, room_type_id)]


@router.get(
    "/pms/rate-plans/{plan_id}",
    response_model=RatePlanRead,
    dependencies=[Depends(require_permission("pms.rate_plans", "view", min_role_level=40))],
)
def get_rate_plan(
    plan_id: int,
    db: DbDep,
    user=Depends(get_current_active_user),
):
    plan = _rate_plan_for_access(db, user, plan_id, "عرض خطة أسعار")
    return RatePlanRead.model_validate(plan)


@router.post(
    "/pms/rate-plans",
    response_model=RatePlanRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("pms.rate_plans", "manage", min_role_level=80))],
)
def create_rate_plan(
    data: RatePlanCreate,
    db: DbDep,
    user=Depends(get_current_active_user),
):
    _assert_pms_branch(db, user, data.branch_id, "إنشاء خطة أسعار")
    try:
        obj = services.create_rate_plan(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return RatePlanRead.model_validate(obj)


@router.patch(
    "/pms/rate-plans/{plan_id}",
    response_model=RatePlanRead,
    dependencies=[Depends(require_permission("pms.rate_plans", "manage", min_role_level=80))],
)
def update_rate_plan(
    plan_id: int,
    data: RatePlanUpdate,
    db: DbDep,
    user=Depends(get_current_active_user),
):
    """تعديل خطة أسعار موجودة — بما فيها إلغاء تفعيلها (`is_active=false`)،
    مفيش endpoint حذف منفصل (زي باقي المشروع: خطة قديمة بتتعطّل مش بتتشال،
    عشان الحجوزات التاريخية المرتبطة بيها (BookingRoom.rate_plan_id) تفضل
    قابلة للتتبّع)."""
    _rate_plan_for_access(db, user, plan_id, "تحديث خطة أسعار")
    try:
        obj = services.update_rate_plan(db, plan_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return RatePlanRead.model_validate(obj)


# ── Night Audit ───────────────────────────────────────────────────────

@router.get(
    "/pms/night-audit",
    response_model=list[NightAuditLogRead],
    dependencies=[Depends(require_permission("pms.night_audit", "view", min_role_level=60))],
)
def list_night_audits(
    db: DbDep,
    branch_id: int = Query(...),
    page: int = Query(1, ge=1), size: int = Query(30, ge=1, le=90),
    user=Depends(get_current_active_user),
):
    _assert_pms_branch(db, user, branch_id, "عرض المراجعة الليلية")
    return [NightAuditLogRead.model_validate(log)
            for log in crud.list_night_audits(db, branch_id, (page-1)*size, size)]


@router.post(
    "/pms/night-audit/run",
    response_model=NightAuditLogRead,
    dependencies=[Depends(require_permission("pms.night_audit", "run", min_role_level=80))],
)
def run_night_audit(
    db: DbDep,
    branch_id:  int  = Query(...),
    audit_date: date = Query(...),
    user=Depends(get_current_active_user),
):
    _assert_pms_branch(db, user, branch_id, "تشغيل المراجعة الليلية")
    try:
        return services.run_night_audit(db, branch_id, audit_date)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
