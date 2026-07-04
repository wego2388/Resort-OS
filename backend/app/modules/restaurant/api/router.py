"""app/modules/restaurant/api/router.py"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import Response

from app.core.deps import (
    DbDep, get_cashier_user, get_current_active_user,
    get_manager_user, get_waiter_user, require_permission, user_level,
)
from app.modules.restaurant import crud, services
from app.modules.restaurant.schemas import (
    DiningTableRead, KDSScreenCreate, KDSScreenRead,
    KitchenTicketRead, TicketStatusUpdate,
    MenuCategoryCreate, MenuCategoryRead,
    MenuItemCreate, MenuItemExtraGroupCreate, MenuItemExtraGroupRead, MenuItemRead, MenuItemUpdate,
    OrderCreate, OrderItemCreate, OrderItemRead, OrderItemVoidRequest, OrderRead, OrderStatusUpdate,
    OrderSyncRequest, OrderSyncResponse,
    # Public (Guest QR) schemas
    GuestOrderCreate, GuestOrderRead, PublicMenuResponse,
    PublicMenuCategoryRead, PublicMenuItemRead,
)
from app.modules.core.schemas import PaginatedResponse

router = APIRouter(tags=["restaurant"])


# ── WebSocket KDS Manager ──────────────────────────────────────────────

class ConnectionManager:
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


restaurant_manager = ConnectionManager()


@router.websocket("/restaurant/ws/kds/{branch_id}")
async def kds_websocket(ws: WebSocket, branch_id: int):
    """اتصال WebSocket لشاشات الـ KDS — بث تحديثات التذاكر لحظيًا (server→client)،
    وبيرد على أي رسالة من العميل بـ pong كـ heartbeat فقط (مفيش بروتوكول ثنائي الاتجاه)."""
    await restaurant_manager.connect(ws, str(branch_id))
    try:
        while True:
            await ws.receive_text()
            await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        restaurant_manager.disconnect(ws, str(branch_id))


# ── Menu ──────────────────────────────────────────────────────────────
# ⚠️ لازم يفضل /menu/items (نفس مسار POST/PATCH تحت) — مش /menu بس. كان في
# mismatch حقيقي هنا خلّى RestaurantPOSView.vue يرجّعله 405 في الإنتاج.

@router.get("/restaurant/menu/categories", response_model=list[MenuCategoryRead])
def get_categories(db: DbDep, _=Depends(get_current_active_user), branch_id: int = Query(...)):
    """⚠️ RestaurantPOSView.vue كان بينادي المسار ده وهو مش موجود أصلاً (404 حقيقي في
    الإنتاج) — الـ import كان موجود من زمان بس الـ endpoint نفسه اتنسى."""
    return [MenuCategoryRead.model_validate(c) for c in crud.list_categories(db, branch_id)]


@router.post("/restaurant/menu/categories", response_model=MenuCategoryRead,
             status_code=status.HTTP_201_CREATED)
def create_category(data: MenuCategoryCreate, db: DbDep, _=Depends(get_manager_user)):
    obj = crud.create_category(db, data)
    db.commit()
    db.refresh(obj)
    return MenuCategoryRead.model_validate(obj)


@router.get("/restaurant/menu/items", response_model=list[MenuItemRead])
def get_menu(
    db: DbDep,
    _=Depends(get_current_active_user),
    branch_id:    int  = Query(...),
    category_id:  Optional[int]  = Query(None),
    available_only: bool = Query(True),
):
    items = crud.list_menu_items(db, branch_id, category_id, available_only)
    return [MenuItemRead.model_validate(i) for i in items]


@router.post("/restaurant/menu/items", response_model=MenuItemRead,
             status_code=status.HTTP_201_CREATED)
def create_menu_item(data: MenuItemCreate, db: DbDep, _=Depends(get_manager_user)):
    obj = crud.create_menu_item(db, data)
    db.commit()
    db.refresh(obj)
    return MenuItemRead.model_validate(obj)


@router.patch("/restaurant/menu/items/{item_id}",
              response_model=MenuItemRead)
def update_menu_item(item_id: int, data: MenuItemUpdate, db: DbDep, _=Depends(get_manager_user)):
    item = crud.get_menu_item(db, item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الصنف غير موجود")
    obj = crud.update_menu_item(db, item, data)
    db.commit()
    db.refresh(obj)
    return MenuItemRead.model_validate(obj)


@router.post("/restaurant/menu/items/{item_id}/extra-groups",
             response_model=MenuItemExtraGroupRead,
             status_code=status.HTTP_201_CREATED)
def create_extra_group(item_id: int, data: MenuItemExtraGroupCreate, db: DbDep, _=Depends(get_manager_user)):
    item = crud.get_menu_item(db, item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الصنف غير موجود")
    group = crud.create_extra_group(db, item_id, data)
    db.commit()
    db.refresh(group)
    return MenuItemExtraGroupRead.model_validate(group)


@router.delete("/restaurant/menu/extra-groups/{group_id}",
               status_code=status.HTTP_204_NO_CONTENT)
def delete_extra_group(group_id: int, db: DbDep, _=Depends(get_manager_user)):
    if not crud.delete_extra_group(db, group_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المجموعة غير موجودة")
    db.commit()


# ── Tables ────────────────────────────────────────────────────────────

@router.get("/restaurant/tables", response_model=list[DiningTableRead])
def list_tables(db: DbDep, _=Depends(get_current_active_user), branch_id: int = Query(...)):
    return [DiningTableRead.model_validate(t) for t in crud.list_tables(db, branch_id)]


# ── Orders ────────────────────────────────────────────────────────────

@router.get("/restaurant/orders", response_model=PaginatedResponse)
def list_orders(
    db: DbDep,
    _=Depends(get_cashier_user),
    branch_id:  int  = Query(...),
    status_filter: Optional[str]  = Query(None, alias="status"),
    order_date: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    items, total = crud.list_orders(db, branch_id, status_filter, order_date,
                                    (page - 1) * size, size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[OrderRead.model_validate(o) for o in items])


@router.post("/restaurant/orders", response_model=OrderRead,
             status_code=status.HTTP_201_CREATED)
def create_order(data: OrderCreate, db: DbDep, user=Depends(get_waiter_user),
                 branch_id: int = Query(...)):
    try:
        return services.create_order(db, branch_id, data, waiter_id=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/restaurant/orders/hold", response_model=OrderRead,
             status_code=status.HTTP_201_CREATED)
def hold_order(data: OrderCreate, db: DbDep, user=Depends(get_waiter_user),
               branch_id: int = Query(...)):
    """طلب معلّق (زي fb_hold عند Trucker) — الجرسون يحفظ الأوردر من غير ما
    يبعته للمطبخ، يرجعله بعدين بـ PATCH .../status → open.
    ⚠️ مسجّل قبل /{order_id} عمداً — نفس سبب /sync تحت."""
    try:
        return services.create_order(db, branch_id, data, waiter_id=user.id, hold=True)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/restaurant/orders/held", response_model=list[OrderRead])
def list_held_orders(db: DbDep, _=Depends(get_waiter_user), branch_id: int = Query(...)):
    """الجرسون يقدر يشوف الطلبات المعلّقة بس (مش كل الأوردرات — دي للكاشير)."""
    items, _total = crud.list_orders(db, branch_id, status="held", limit=100)
    return [OrderRead.model_validate(o) for o in items]


@router.post("/restaurant/orders/sync", response_model=OrderSyncResponse)
def sync_offline_order(data: OrderSyncRequest, db: DbDep, user=Depends(get_waiter_user),
                       branch_id: int = Query(...)):
    """Offline POS sync — يستقبل طلب اتعمل وهو offline ويسوّيه مع حالة
    المخزون الحالية. راجع 07-BUSINESS-RULES.md § 9.

    ⚠️ مسجّل قبل /{order_id} عمداً — وإلا "sync" هتتفسّر كـ order_id."""
    result = services.sync_offline_order(db, branch_id, data, waiter_id=user.id)
    return OrderSyncResponse(
        order_id=result["order_id"],
        status=result["status"],
        fulfilled_items=[OrderItemRead.model_validate(i) for i in result["fulfilled_items"]],
        rejected_items=result["rejected_items"],
        message=result["message"],
    )


@router.get("/restaurant/orders/{order_id}", response_model=OrderRead)
def get_order(order_id: int, db: DbDep, _=Depends(get_current_active_user)):
    order = crud.get_order(db, order_id)
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"الطلب {order_id} غير موجود")
    return OrderRead.model_validate(order)


@router.patch("/restaurant/orders/{order_id}/status",
              response_model=OrderRead)
async def update_order_status(order_id: int, data: OrderStatusUpdate,
                        db: DbDep, user=Depends(get_waiter_user)):
    # تحويل الطلب لـ "مدفوع" فعل مالي فعلي (يقفل الطاولة، ينشر charge على
    # الفوليو، يرحّل قيد إيراد، يخصم مخزون) — نفس مستوى void_order_item،
    # مش أي نادل يقدر يقفل الحساب. باقي الحالات (in_kitchen/served/...)
    # فضلت على مستوى النادل عمداً — دي حركات تشغيل يومية مش مالية.
    if data.status == "paid" and user_level(user) < 40:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "إتمام الدفع يتطلب صلاحية كاشير على الأقل")
    try:
        order = services.update_order_status(db, order_id, data.status, charge_to_room_id=data.charge_to_room_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    if data.status == "in_kitchen":
        # تذاكر جديدة اتعملت للمطبخ — نبث تحديث لأي شاشة KDS متصلة بدل ما
        # تستنى الـ polling الدوري (15 ثانية) عشان تشوفها
        await restaurant_manager.broadcast(str(order.branch_id), {"type": "tickets_updated", "order_id": order.id})
    return order


@router.patch("/restaurant/orders/{order_id}/items/{item_id}/void",
              response_model=OrderRead,
              dependencies=[Depends(require_permission("restaurant.void_order_item", "execute", min_role_level=40))])
def void_order_item(order_id: int, item_id: int, data: OrderItemVoidRequest,
                    db: DbDep, user=Depends(get_current_active_user)):
    """إلغاء صنف واحد بسبب إجباري — كاشير أو أعلى بس (مش الجرسون)، زي أي
    إجراء مالي تاني في النظام ده (نفس مستوى apply_discount)."""
    try:
        return services.void_order_item(db, order_id, item_id, data.reason, voided_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.patch("/restaurant/orders/{order_id}/items/{item_id}/refund",
              response_model=OrderRead,
              dependencies=[Depends(require_permission("restaurant.refund_order_item", "execute", min_role_level=60))])
def refund_order_item(order_id: int, item_id: int, data: OrderItemVoidRequest,
                      db: DbDep, user=Depends(get_current_active_user)):
    """مرتجع بعد الدفع — مستوى مدير (60) مش كاشير (40)، لأنها عكس مالي لأوردر
    اتقفل بالفعل (أعلى خطورة من void_order_item العادي قبل الدفع). زي
    void_order_item بالظبط: require_permission هو الحاكم الوحيد على الـ role
    (مش role dependency صلب جنب بعض — راجع §11 من CLAUDE.md لباج مشابه)."""
    try:
        return services.refund_order_item(db, order_id, item_id, data.reason, refunded_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/restaurant/orders/{order_id}/receipt")
def download_receipt(order_id: int, db: DbDep, _=Depends(get_cashier_user)):
    try:
        pdf = services.generate_receipt_pdf(db, order_id)
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename=receipt-{order_id}.pdf"},
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.post("/restaurant/orders/{order_id}/discount",
             response_model=OrderRead)
def apply_discount(order_id: int, db: DbDep, _=Depends(get_cashier_user)):
    try:
        return services.apply_order_discount(db, order_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Kitchen / KDS ────────────────────────────────────────────────────

@router.get("/restaurant/kitchen/tickets",
            response_model=list[KitchenTicketRead])
def list_kitchen_tickets(
    db: DbDep,
    _=Depends(get_current_active_user),
    branch_id: int = Query(...),
    stations: Optional[str] = Query(None, description="Comma-separated list of stations"),
    module: str = Query("restaurant", pattern=r"^(restaurant|cafe)$"),
):
    """قائمة تذاكر الـ KDS المعلقة — لكل شاشة KDS (مطبخ/بار/...) حسب المحطة والموديول."""
    station_list = [s.strip() for s in stations.split(",")] if stations else None
    tickets = services.get_kds_tickets(db, branch_id, stations=station_list, module=module)
    return [KitchenTicketRead.model_validate(t) for t in tickets]


@router.patch("/restaurant/kitchen/tickets/{ticket_id}/status",
              response_model=KitchenTicketRead)
async def update_ticket_status(
    ticket_id: int,
    data: TicketStatusUpdate,
    db: DbDep,
    _=Depends(get_current_active_user),
):
    """يحدّث حالة تذكرة الـ KDS (pending → in_progress → done)."""
    ticket = crud.update_ticket_status(db, ticket_id, data.status)
    if not ticket:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"التذكرة {ticket_id} غير موجودة")
    db.commit()
    db.refresh(ticket)
    await restaurant_manager.broadcast(str(ticket.branch_id), {"type": "tickets_updated", "ticket_id": ticket.id})
    return KitchenTicketRead.model_validate(ticket)


@router.get("/restaurant/kds-screens",
            response_model=list[KDSScreenRead])
def list_kds_screens(
    db: DbDep,
    _=Depends(get_current_active_user),
    branch_id: int = Query(...),
):
    """قائمة شاشات الـ KDS المُعدّة للفرع."""
    screens = crud.list_kds_screens(db, branch_id)
    return [KDSScreenRead.model_validate(s) for s in screens]


@router.post("/restaurant/kds-screens",
             response_model=KDSScreenRead,
             status_code=status.HTTP_201_CREATED)
def create_kds_screen(data: KDSScreenCreate, db: DbDep, _=Depends(get_manager_user)):
    """ينشئ شاشة KDS جديدة (مدير بس)."""
    screen = crud.create_kds_screen(db, data.model_dump())
    db.commit()
    db.refresh(screen)
    return KDSScreenRead.model_validate(screen)


# ══════════════════════════════════════════════════════════════════════
# Public Endpoints — للضيوف عبر QR (بدون auth)
# ══════════════════════════════════════════════════════════════════════
# ⚠️ هذه الـ endpoints بدون authentication عمداً:
#   - GET  /restaurant/public/menu  → قائمة الطعام للضيف (read-only)
#   - POST /restaurant/public/orders → طلب جديد من الضيف
#   - GET  /restaurant/public/orders/{id} → حالة الطلب للضيف
#
# أمان: rate limited بالـ middleware (30 req/60s per IP)
#        الـ order_type مقيّد بـ "dine_in" | "room_service" فقط
#        لا يوجد تعديل أو حذف من هنا — read + create فقط
# ══════════════════════════════════════════════════════════════════════


@router.get(
    "/restaurant/public/menu",
    response_model=PublicMenuResponse,
    tags=["restaurant-public"],
    summary="قائمة الطعام للضيف (QR) — بدون auth",
)
def get_public_menu(
    db: DbDep,
    branch_id: int = Query(..., description="رقم الفرع — مضمّن في الـ QR"),
    table_id: Optional[int] = Query(None, description="رقم الطاولة — مضمّن في الـ QR"),
):
    """
    Public endpoint — لا يحتاج login.
    يُستدعى من apps/qr/TableMenuView عند مسح QR الطاولة.
    يُرجع categories + items في طلب واحد لتقليل round trips.
    """
    categories = crud.list_categories(db, branch_id)
    items = crud.list_menu_items(db, branch_id, available_only=True)

    return PublicMenuResponse(
        branch_id=branch_id,
        table_id=table_id,
        categories=[PublicMenuCategoryRead.model_validate(c) for c in categories],
        items=[PublicMenuItemRead.model_validate(i) for i in items],
    )


@router.post(
    "/restaurant/public/orders",
    response_model=GuestOrderRead,
    status_code=status.HTTP_201_CREATED,
    tags=["restaurant-public"],
    summary="تقديم طلب من الضيف (QR) — بدون auth",
)
def create_guest_order(data: GuestOrderCreate, db: DbDep):
    """
    Public endpoint — لا يحتاج login.
    الضيف يطلب من القائمة عبر QR الطاولة.
    - order_type مقيّد: dine_in أو room_service فقط
    - waiter_id = None (الـ waiter module يتولى)
    - source = 'qr_guest'
    """
    try:
        order_data = OrderCreate(
            table_id=data.table_id,
            order_type="dine_in",
            guests_count=data.guests_count,
            notes=data.notes,
            items=[OrderItemCreate(**i.model_dump()) for i in data.items],
        )
        order = services.create_order(
            db,
            branch_id=data.branch_id,
            data=order_data,
            waiter_id=None,
        )
        db.commit()
        db.refresh(order)
        return GuestOrderRead(
            order_id=order.id,
            order_number=order.order_number,
            status=order.status,
            total=order.total,
            items_count=sum(i.quantity for i in order.items),
            message="تم استلام طلبك! سيصل إليك قريباً 🍽️",
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get(
    "/restaurant/public/orders/{order_id}",
    response_model=GuestOrderRead,
    tags=["restaurant-public"],
    summary="حالة الطلب للضيف (QR) — بدون auth",
)
def get_guest_order_status(order_id: int, db: DbDep):
    """
    Public endpoint — لا يحتاج login.
    الضيف يتابع حالة طلبه بعد التقديم (polling كل 10 ثواني).
    لا يُظهر بيانات مالية داخلية — status فقط.
    """
    order = crud.get_order(db, order_id)
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الطلب غير موجود")
    return GuestOrderRead(
        order_id=order.id,
        order_number=order.order_number,
        status=order.status,
        total=order.total,
        items_count=sum(i.quantity for i in order.items if i.status != "cancelled"),
        message=_guest_status_message(order.status),
    )


def _guest_status_message(order_status: str) -> str:
    return {
        "open":       "تم استلام طلبك ✓",
        "in_kitchen": "يتم تحضير طلبك الآن 👨‍🍳",
        "served":     "تم تقديم طلبك، بالهنا والشفا 🎉",
        "paid":       "شكراً لزيارتك ✨",
        "cancelled":  "تم إلغاء الطلب",
        "held":       "الطلب في الانتظار",
    }.get(order_status, "جاري المعالجة...")
