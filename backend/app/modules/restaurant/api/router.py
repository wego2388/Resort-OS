"""app/modules/restaurant/api/router.py"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import Response

from app.core.config import settings
from app.core.deps import (
    DbDep, get_cashier_user, get_current_active_user,
    get_manager_user, get_waiter_user, require_permission, user_level,
)
from app.modules.restaurant import crud, services
from app.modules.restaurant.schemas import (
    DiningTableRead, DiningTableCreate, DiningTableUpdate, DiningTableGridUpdate,
    KDSScreenCreate, KDSScreenRead,
    KitchenTicketRead, TicketStatusUpdate,
    MenuCategoryCreate, MenuCategoryRead, MenuCategoryUpdate,
    MenuItemCreate, MenuItemExtraGroupCreate, MenuItemExtraGroupRead, MenuItemRead, MenuItemUpdate,
    MenuItemRecipeLineCreate, MenuItemRecipeLineRead, MenuItemRecipeLineUpdate,
    MenuItemVariantCreate, MenuItemVariantRead, MenuItemVariantRecipeLineCreate,
    MenuItemVariantRecipeLineRead, MenuItemVariantRecipeLineUpdate, MenuItemVariantUpdate,
    OrderCreate, OrderItemCreate, OrderItemRead, OrderItemStatusUpdate, OrderItemVoidRequest,
    OrderRead, OrderStatusUpdate, OrderTransferRequest,
    OrderSyncRequest, OrderSyncResponse,
    # Reporting / Food Cost
    FoodCostReportResponse,
    # Public (Guest QR) schemas
    GuestOrderCreate, GuestOrderRead, PublicMenuResponse,
    PublicMenuCategoryRead, PublicMenuItemRead,
)
from app.modules.core.schemas import PaginatedResponse
from app.resort_os.food_cost_engine import DEFAULT_FOOD_COST_THRESHOLD_PCT
from app.resort_os.timezone_utils import business_today

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
    """اتصال WebSocket لشاشات الـ KDS."""
    await restaurant_manager.connect(ws, str(branch_id))
    try:
        while True:
            await ws.receive_text()
            await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        restaurant_manager.disconnect(ws, str(branch_id))


@router.websocket("/restaurant/ws/tables/{branch_id}")
async def tables_websocket(ws: WebSocket, branch_id: int):
    """اتصال WebSocket لخريطة الطاولات الحية — يبث تحديثات حالة
    الطاولات لحظيًا (table_updated) عند أي تغيير في الموضع أو الحالة."""
    await restaurant_manager.connect(ws, f"tables-{branch_id}")
    try:
        while True:
            await ws.receive_text()
            await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        restaurant_manager.disconnect(ws, f"tables-{branch_id}")


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


@router.patch("/restaurant/menu/categories/{category_id}", response_model=MenuCategoryRead,
              operation_id="restaurant_update_category")
def update_category(category_id: int, data: MenuCategoryUpdate, db: DbDep,
                    _=Depends(get_manager_user)):
    cat = crud.get_category(db, category_id)
    if not cat:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الفئة غير موجودة")
    cat = crud.update_category(db, cat, data)
    db.commit()
    db.refresh(cat)
    return MenuCategoryRead.model_validate(cat)


@router.delete("/restaurant/menu/categories/{category_id}",
               status_code=status.HTTP_204_NO_CONTENT,
               operation_id="restaurant_delete_category")
def delete_category(category_id: int, db: DbDep, _=Depends(get_manager_user)):
    if not crud.delete_category(db, category_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الفئة غير موجودة")
    db.commit()


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


@router.delete("/restaurant/menu/items/{item_id}",
               status_code=status.HTTP_204_NO_CONTENT)
def delete_menu_item(item_id: int, db: DbDep, _=Depends(get_manager_user)):
    if not crud.delete_menu_item(db, item_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الصنف غير موجود")
    db.commit()


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


# ── Recipe / BOM ──────────────────────────────────────────────────────
# نفس مستوى صلاحية تعديل الصنف نفسه (get_manager_user) — الوصفة جزء من
# تعريف الصنف، مش عملية تشغيلية يومية.

@router.post("/restaurant/menu/items/{item_id}/recipe-lines",
             response_model=MenuItemRecipeLineRead,
             status_code=status.HTTP_201_CREATED)
def add_recipe_line(item_id: int, data: MenuItemRecipeLineCreate, db: DbDep, _=Depends(get_manager_user)):
    try:
        line = services.add_recipe_line(db, item_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return MenuItemRecipeLineRead.model_validate(services.build_recipe_line_read(line))


@router.patch("/restaurant/menu/recipe-lines/{line_id}", response_model=MenuItemRecipeLineRead)
def update_recipe_line(line_id: int, data: MenuItemRecipeLineUpdate, db: DbDep, _=Depends(get_manager_user)):
    try:
        line = services.update_recipe_line(db, line_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return MenuItemRecipeLineRead.model_validate(services.build_recipe_line_read(line))


@router.delete("/restaurant/menu/recipe-lines/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe_line(line_id: int, db: DbDep, _=Depends(get_manager_user)):
    try:
        services.remove_recipe_line(db, line_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ── Variants (حجم/نوع حقيقي) ─────────────────────────────────────────
# نفس مستوى صلاحية الوصفة/الصنف (get_manager_user) — راجع
# app.modules.restaurant.models.MenuItemVariant للتبرير الكامل.

@router.post("/restaurant/menu/items/{item_id}/variants",
             response_model=MenuItemVariantRead,
             status_code=status.HTTP_201_CREATED)
def add_variant(item_id: int, data: MenuItemVariantCreate, db: DbDep, _=Depends(get_manager_user)):
    try:
        variant = services.add_variant(db, item_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return MenuItemVariantRead.model_validate(services.build_variant_read(variant))


@router.patch("/restaurant/menu/variants/{variant_id}", response_model=MenuItemVariantRead)
def update_variant(variant_id: int, data: MenuItemVariantUpdate, db: DbDep, _=Depends(get_manager_user)):
    try:
        variant = services.update_variant(db, variant_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return MenuItemVariantRead.model_validate(services.build_variant_read(variant))


@router.delete("/restaurant/menu/variants/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_variant(variant_id: int, db: DbDep, _=Depends(get_manager_user)):
    try:
        services.remove_variant(db, variant_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.post("/restaurant/menu/variants/{variant_id}/recipe-lines",
             response_model=MenuItemVariantRecipeLineRead,
             status_code=status.HTTP_201_CREATED)
def add_variant_recipe_line(variant_id: int, data: MenuItemVariantRecipeLineCreate, db: DbDep, _=Depends(get_manager_user)):
    try:
        line = services.add_variant_recipe_line(db, variant_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return MenuItemVariantRecipeLineRead.model_validate(services.build_variant_recipe_line_read(line))


@router.patch("/restaurant/menu/variant-recipe-lines/{line_id}", response_model=MenuItemVariantRecipeLineRead)
def update_variant_recipe_line(line_id: int, data: MenuItemVariantRecipeLineUpdate, db: DbDep, _=Depends(get_manager_user)):
    try:
        line = services.update_variant_recipe_line(db, line_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return MenuItemVariantRecipeLineRead.model_validate(services.build_variant_recipe_line_read(line))


@router.delete("/restaurant/menu/variant-recipe-lines/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_variant_recipe_line(line_id: int, db: DbDep, _=Depends(get_manager_user)):
    try:
        services.remove_variant_recipe_line(db, line_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ── Reporting / Food Cost ─────────────────────────────────────────────
# مستوى مدير (get_manager_user) — نفس مستوى تعديل الوصفة نفسها (§ Recipe/BOM
# أعلاه)، لأن التقرير ده بيكشف تكلفة/هامش ربح حقيقي، مش عملية تشغيلية يومية.

@router.get("/restaurant/reports/food-cost", response_model=FoodCostReportResponse)
def get_food_cost_report(
    db: DbDep,
    _=Depends(get_manager_user),
    branch_id: int = Query(...),
    date_from: date = Query(default_factory=lambda: business_today(settings.TIMEZONE) - timedelta(days=30)),
    date_to: date = Query(default_factory=lambda: business_today(settings.TIMEZONE)),
    threshold_pct: Decimal = Query(DEFAULT_FOOD_COST_THRESHOLD_PCT, gt=0, le=100),
):
    """تقرير تكلفة الطعام (Food Cost / COGS): تكلفة نظرية (وصفة × كمية
    مباعة فعليًا) مقابل الإيراد الفعلي، لكل صنف + اتجاه يومي + ملخص الفرع.
    ``alerts`` جزء من نفس الرد (الأصناف اللي تخطّت threshold_pct) — مش
    endpoint منفصل، لأنها اشتقاق من نفس بيانات ``lines`` بدون استعلام إضافي."""
    if date_from > date_to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "date_from لازم يكون قبل أو يساوي date_to")
    return services.get_food_cost_report(db, branch_id, date_from, date_to, threshold_pct)


@router.get("/restaurant/reports/food-cost/export")
def download_food_cost_report_excel(
    db: DbDep,
    _=Depends(get_manager_user),
    branch_id: int = Query(...),
    date_from: date = Query(default_factory=lambda: business_today(settings.TIMEZONE) - timedelta(days=30)),
    date_to: date = Query(default_factory=lambda: business_today(settings.TIMEZONE)),
    threshold_pct: Decimal = Query(DEFAULT_FOOD_COST_THRESHOLD_PCT, gt=0, le=100),
):
    """تصدير Excel لتقرير تكلفة الطعام (wagdy.md #16)."""
    if date_from > date_to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "date_from لازم يكون قبل أو يساوي date_to")
    xlsx = services.generate_food_cost_excel(db, branch_id, date_from, date_to, threshold_pct)
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=food-cost-report.xlsx"},
    )


# ── Tables ────────────────────────────────────────────────────────────

@router.get("/restaurant/tables", response_model=list[DiningTableRead])
def list_tables(db: DbDep, _=Depends(get_current_active_user), branch_id: int = Query(...)):
    return [DiningTableRead.model_validate(t) for t in crud.list_tables(db, branch_id)]


@router.post("/restaurant/tables", response_model=DiningTableRead,
             status_code=status.HTTP_201_CREATED)
def create_table(data: DiningTableCreate, db: DbDep, _=Depends(get_manager_user)):
    table = crud.create_table(db, data)
    db.commit()
    db.refresh(table)
    return DiningTableRead.model_validate(table)


@router.patch("/restaurant/tables/{table_id}", response_model=DiningTableRead)
def update_table(table_id: int, data: DiningTableUpdate, db: DbDep, _=Depends(get_manager_user)):
    table = crud.get_table(db, table_id)
    if not table:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الطاولة غير موجودة")
    table = crud.update_table(db, table, data)
    db.commit()
    db.refresh(table)
    return DiningTableRead.model_validate(table)


@router.patch("/restaurant/tables/{table_id}/grid", response_model=DiningTableRead)
async def update_table_grid(table_id: int, data: DiningTableGridUpdate, db: DbDep,
                      _=Depends(get_manager_user)):
    """تحديث موضع الطاولة على الخريطة (drag & drop من صفحة الإعدادات)."""
    table = crud.get_table(db, table_id)
    if not table:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الطاولة غير موجودة")
    table = crud.update_table_grid(db, table, data.grid_row, data.grid_col)
    db.commit()
    db.refresh(table)
    await restaurant_manager.broadcast(str(table.branch_id), {
        "type": "table_updated", "table_id": table.id,
    })
    return DiningTableRead.model_validate(table)


@router.delete("/restaurant/tables/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_table(table_id: int, db: DbDep, _=Depends(get_manager_user)):
    table = crud.get_table(db, table_id)
    if not table:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الطاولة غير موجودة")
    if table.status == "occupied":
        raise HTTPException(status.HTTP_409_CONFLICT, "لا يمكن حذف طاولة مشغولة")
    crud.delete_table(db, table_id)
    db.commit()


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
        order = services.update_order_status(
            db, order_id, data.status,
            charge_to_room_id=data.charge_to_room_id,
            payment_method=data.payment_method,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    if data.status == "in_kitchen":
        await restaurant_manager.broadcast(str(order.branch_id), {"type": "tickets_updated", "order_id": order.id})
    if data.status in ("in_kitchen", "served", "paid", "cancelled") and order.table_id:
        # بث تحديث خريطة الطاولات عند أي تغيير يأثر على حالة الطاولة
        await restaurant_manager.broadcast(f"tables-{order.branch_id}", {
            "type": "table_updated", "table_id": order.table_id,
        })
    return order


@router.patch("/restaurant/orders/{order_id}/transfer", response_model=OrderRead)
async def transfer_order_table(order_id: int, data: OrderTransferRequest,
                               db: DbDep, user=Depends(get_waiter_user)):
    """نقل طلب مفتوح لطاولة تانية (الضيوف اتحركوا فعليًا) — نفس مستوى صلاحية
    باقي عمليات التشغيل اليومية على الطلب (get_waiter_user)، مش إجراء مالي."""
    try:
        order = services.transfer_order_table(db, order_id, data.table_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    await restaurant_manager.broadcast(f"tables-{order.branch_id}", {
        "type": "table_updated", "table_id": order.table_id,
    })
    return order


@router.patch("/restaurant/orders/{order_id}/items/{item_id}/status", response_model=OrderRead)
async def update_order_item_status(order_id: int, item_id: int, data: OrderItemStatusUpdate,
                                   db: DbDep, _=Depends(get_current_active_user)):
    """تأكيد صنف واحد داخل تذكرة مطبخ (bump فردي من شاشة KDS) — نفس مستوى
    صلاحية تأكيد التذكرة كلها (get_current_active_user، أي موظف مسجّل دخول
    زي طاقم المطبخ)، مش إجراء مالي."""
    try:
        order = services.bump_order_item_status(db, order_id, item_id, data.status)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    await restaurant_manager.broadcast(str(order.branch_id), {"type": "tickets_updated", "order_id": order.id})
    return order


@router.patch("/restaurant/orders/{order_id}/items/{item_id}/void",
              response_model=OrderRead,
              dependencies=[Depends(require_permission("restaurant.void_order_item", "execute", min_role_level=40))])
def void_order_item(order_id: int, item_id: int, data: OrderItemVoidRequest,
                    db: DbDep, user=Depends(get_current_active_user)):
    """إلغاء صنف واحد بسبب إجباري — كاشير أو أعلى بس (مش الجرسون)، زي أي
    إجراء مالي تاني في النظام ده (نفس مستوى apply_discount). لو المنفّذ أقل
    من مدير، لازم موافقة PIN من مدير (data.approver_user_id/approver_pin)
    — راجع core.services.resolve_pin_approval."""
    try:
        return services.void_order_item(
            db, order_id, item_id, data.reason, voided_by=user.id,
            acting_user_level=user_level(user),
            approver_user_id=data.approver_user_id, approver_pin=data.approver_pin,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/restaurant/orders/{order_id}/items",
             response_model=OrderRead,
             status_code=status.HTTP_200_OK)
async def add_items_to_order(
    order_id: int,
    items: list[OrderItemCreate],
    db: DbDep,
    user=Depends(get_waiter_user),
):
    """إضافة أصناف جديدة لطلب مفتوح موجود — بدون حذف الأصناف الحالية.
    مسموح لأي waiter+ على طلبات بحالة open|held|in_kitchen|served.
    يُعيد الطلب كاملاً بعد إضافة الأصناف مع المجاميع المحدّثة.
    لو الطلب كان in_kitchen، يُرسل broadcast للـ KDS تلقائياً."""
    if not items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "لازم تضيف صنف واحد على الأقل")
    try:
        order = services.add_items_to_order(db, order_id, items)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    # لو الطلب كان in_kitchen، أعلم المطبخ بالأصناف الجديدة
    if order.status == "in_kitchen":
        await restaurant_manager.broadcast(
            str(order.branch_id),
            {"type": "tickets_updated", "order_id": order.id},
        )
    return order


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
    """قائمة تذاكر الـ KDS المعلقة — لكل شاشة KDS (مطبخ/بار/...) حسب المحطة والموديول.
    لتذاكر المطعم، كل صنف جوه items_snapshot بيرجع مع status لحظي حقيقي من
    OrderItem.status (راجع services._ticket_read_dict) — عشان الشاشة تقدر
    تعرض صنف اتأكد لوحده (bump فردي) من غير ما تنتظر تأكيد التذكرة كلها."""
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
    """يحدّث حالة تذكرة الـ KDS كاملة (pending → in_progress → done) — تأكيد
    دفعة واحدة. لو تذكرة مطعم اتأكدت done، أي صنف لسه pending/in_kitchen
    جواها بيترقّى لـ ready تلقائيًا (راجع services.update_kitchen_ticket_status)."""
    try:
        ticket_dict = services.update_kitchen_ticket_status(db, ticket_id, data.status)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    await restaurant_manager.broadcast(str(ticket_dict["branch_id"]), {"type": "tickets_updated", "ticket_id": ticket_dict["id"]})
    return KitchenTicketRead.model_validate(ticket_dict)


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
    # نُرجع مفتاح i18n — الـ frontend (OrderView.vue) بيترجمه عبر statusMessage().
    return {
        "open":       "status_pending",
        "in_kitchen": "status_in_kitchen",
        "served":     "status_served",
        "paid":       "status_paid",
        "cancelled":  "status_cancelled",
        "held":       "status_pending",
    }.get(order_status, "status_pending")
