"""app/modules/dining/api/router.py — HTTP layer فقط (يترجم الأخطاء، لا business logic).

مسار موحّد: /api/v1/dining/outlets/{outlet_id}/... (wagdy.md D-04) — يخدم كل
الـ outlets (مطعم/كافيه/بار/بوفيه...) بنفس الكود، الاختلاف Configuration
(Outlet.outlet_type) بس. إضافي بالكامل جنب restaurant/cafe الأصليين —
راجع DINING_CUTOVER_PLAN.md في جذر المشروع لقرار عدم عمل alias حرفي على
مسارات /restaurant و/cafe القديمة (وليه ده أأمن من الالتفاف عليهم دلوقتي).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import Response

from app.core.config import settings
from app.core.deps import (
    DbDep, get_cashier_user, get_current_active_user, get_websocket_user,
    get_manager_user, get_waiter_user, require_permission, user_level,
)
from app.modules.dining import crud, services
from app.modules.dining.schemas import (
    ApplyDiscountRequest,
    DiningCategoryCreate, DiningCategoryRead, DiningCategoryUpdate,
    DiningItemCreate, DiningItemExtraGroupCreate, DiningItemExtraGroupRead,
    DiningItemRead, DiningItemUpdate,
    DiningItemRecipeLineCreate, DiningItemRecipeLineRead, DiningItemRecipeLineUpdate,
    DiningItemVariantCreate, DiningItemVariantRead, DiningItemVariantRecipeLineCreate,
    DiningItemVariantRecipeLineRead, DiningItemVariantRecipeLineUpdate, DiningItemVariantUpdate,
    DiningTableRead, DiningTableCreate, DiningTableUpdate, DiningTableGridUpdate,
    FoodCostReportResponse,
    KDSScreenCreate, KDSScreenRead,
    KitchenTicketRead, TicketStatusUpdate,
    OrderCreate, OrderItemCreate, OrderItemRead, OrderItemStatusUpdate, OrderItemVoidRequest,
    OrderRead, OrderStatusUpdate, OrderTransferRequest,
    OrderSyncRequest, OrderSyncResponse,
    OutletCreate, OutletRead, OutletUpdate,
    GuestOrderCreate, GuestOrderRead, PublicMenuCategoryRead, PublicMenuItemRead, PublicMenuResponse,
    PublicOutletRead,
)
from app.modules.core.schemas import PaginatedResponse
from app.resort_os.food_cost_engine import DEFAULT_FOOD_COST_THRESHOLD_PCT
from app.resort_os.timezone_utils import business_today

router = APIRouter(tags=["dining"])


# ── WebSocket KDS Manager ──────────────────────────────────────────────
# dining بيبث لمشتركي /dining/ws/* لوحده — restaurant/cafe اتحذفوا بالكامل
# (DINING_CUTOVER_PLAN.md Batch 6)، dining هو مصدر البث اللحظي الوحيد دلوقتي.

class ConnectionManager:
    def __init__(self):
        self.active: dict[str, list[WebSocket]] = {}

    async def connect(self, ws: WebSocket, key: str):
        await ws.accept()
        self.active.setdefault(key, []).append(ws)

    def disconnect(self, ws: WebSocket, key: str):
        connections = self.active.get(key, [])
        if ws in connections:
            connections.remove(ws)

    async def broadcast(self, key: str, data: dict):
        for ws in list(self.active.get(key, [])):
            try:
                await ws.send_json(data)
            except Exception:
                pass


dining_manager = ConnectionManager()


@router.websocket("/dining/ws/kds/{branch_id}")
async def kds_websocket(ws: WebSocket, branch_id: int, db: DbDep):
    if not await get_websocket_user(ws, db):
        return
    await dining_manager.connect(ws, str(branch_id))
    try:
        while True:
            await ws.receive_text()
            await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        dining_manager.disconnect(ws, str(branch_id))


@router.websocket("/dining/ws/tables/{branch_id}")
async def tables_websocket(ws: WebSocket, branch_id: int, db: DbDep):
    if not await get_websocket_user(ws, db):
        return
    await dining_manager.connect(ws, f"tables-{branch_id}")
    try:
        while True:
            await ws.receive_text()
            await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        dining_manager.disconnect(ws, f"tables-{branch_id}")


# ── Outlets ───────────────────────────────────────────────────────────

@router.get("/dining/outlets", response_model=list[OutletRead])
def list_outlets(db: DbDep, _=Depends(get_current_active_user),
                  branch_id: int = Query(...), active_only: bool = Query(False)):
    return [OutletRead.model_validate(o) for o in crud.list_outlets(db, branch_id, active_only)]


@router.post("/dining/outlets", response_model=OutletRead, status_code=status.HTTP_201_CREATED)
def create_outlet(data: OutletCreate, db: DbDep, _=Depends(get_manager_user)):
    outlet = services.create_outlet(db, data)
    return OutletRead.model_validate(outlet)


@router.get("/dining/outlets/{outlet_id}", response_model=OutletRead)
def get_outlet(outlet_id: int, db: DbDep, _=Depends(get_current_active_user)):
    outlet = crud.get_outlet(db, outlet_id)
    if not outlet:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المنفذ غير موجود")
    return OutletRead.model_validate(outlet)


@router.patch("/dining/outlets/{outlet_id}", response_model=OutletRead)
def update_outlet(outlet_id: int, data: OutletUpdate, db: DbDep, _=Depends(get_manager_user)):
    try:
        outlet = services.update_outlet(db, outlet_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return OutletRead.model_validate(outlet)


# ── Menu — Categories ─────────────────────────────────────────────────

@router.get("/dining/outlets/{outlet_id}/categories", response_model=list[DiningCategoryRead])
def get_categories(outlet_id: int, db: DbDep, _=Depends(get_current_active_user)):
    return [DiningCategoryRead.model_validate(c) for c in crud.list_categories(db, outlet_id)]


@router.post("/dining/outlets/{outlet_id}/categories", response_model=DiningCategoryRead,
             status_code=status.HTTP_201_CREATED)
def create_category(outlet_id: int, data: DiningCategoryCreate, db: DbDep, _=Depends(get_manager_user)):
    if data.outlet_id != outlet_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "outlet_id في الجسم لازم يطابق المسار")
    obj = crud.create_category(db, data)
    db.commit()
    db.refresh(obj)
    return DiningCategoryRead.model_validate(obj)


@router.patch("/dining/categories/{category_id}", response_model=DiningCategoryRead)
def update_category(category_id: int, data: DiningCategoryUpdate, db: DbDep, _=Depends(get_manager_user)):
    cat = crud.get_category(db, category_id)
    if not cat:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الفئة غير موجودة")
    cat = crud.update_category(db, cat, data)
    db.commit()
    db.refresh(cat)
    return DiningCategoryRead.model_validate(cat)


@router.delete("/dining/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, db: DbDep, _=Depends(get_manager_user)):
    if not crud.delete_category(db, category_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الفئة غير موجودة")
    db.commit()


# ── Menu — Items ──────────────────────────────────────────────────────

@router.get("/dining/outlets/{outlet_id}/items", response_model=list[DiningItemRead])
def get_items(
    outlet_id: int, db: DbDep, _=Depends(get_current_active_user),
    category_id: Optional[int] = Query(None), available_only: bool = Query(True),
):
    items = crud.list_items(db, outlet_id, category_id, available_only)
    return [DiningItemRead.model_validate(i) for i in items]


@router.post("/dining/outlets/{outlet_id}/items", response_model=DiningItemRead,
             status_code=status.HTTP_201_CREATED)
def create_item(outlet_id: int, data: DiningItemCreate, db: DbDep, _=Depends(get_manager_user)):
    if data.outlet_id != outlet_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "outlet_id في الجسم لازم يطابق المسار")
    obj = crud.create_item(db, data)
    db.commit()
    db.refresh(obj)
    return DiningItemRead.model_validate(obj)


@router.patch("/dining/items/{item_id}", response_model=DiningItemRead)
def update_item(item_id: int, data: DiningItemUpdate, db: DbDep, _=Depends(get_manager_user)):
    item = crud.get_item(db, item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الصنف غير موجود")
    obj = crud.update_item(db, item, data)
    db.commit()
    db.refresh(obj)
    return DiningItemRead.model_validate(obj)


@router.delete("/dining/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int, db: DbDep, _=Depends(get_manager_user)):
    if not crud.delete_item(db, item_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الصنف غير موجود")
    db.commit()


@router.post("/dining/items/{item_id}/extra-groups", response_model=DiningItemExtraGroupRead,
             status_code=status.HTTP_201_CREATED)
def create_extra_group(item_id: int, data: DiningItemExtraGroupCreate, db: DbDep, _=Depends(get_manager_user)):
    item = crud.get_item(db, item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الصنف غير موجود")
    group = crud.create_extra_group(db, item_id, data)
    db.commit()
    db.refresh(group)
    return DiningItemExtraGroupRead.model_validate(group)


@router.delete("/dining/extra-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_extra_group(group_id: int, db: DbDep, _=Depends(get_manager_user)):
    if not crud.delete_extra_group(db, group_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المجموعة غير موجودة")
    db.commit()


# ── Recipe / BOM ──────────────────────────────────────────────────────

@router.post("/dining/items/{item_id}/recipe-lines", response_model=DiningItemRecipeLineRead,
             status_code=status.HTTP_201_CREATED)
def add_recipe_line(item_id: int, data: DiningItemRecipeLineCreate, db: DbDep, _=Depends(get_manager_user)):
    try:
        line = services.add_recipe_line(db, item_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return DiningItemRecipeLineRead.model_validate(services.build_recipe_line_read(line))


@router.patch("/dining/recipe-lines/{line_id}", response_model=DiningItemRecipeLineRead)
def update_recipe_line(line_id: int, data: DiningItemRecipeLineUpdate, db: DbDep, _=Depends(get_manager_user)):
    try:
        line = services.update_recipe_line(db, line_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return DiningItemRecipeLineRead.model_validate(services.build_recipe_line_read(line))


@router.delete("/dining/recipe-lines/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe_line(line_id: int, db: DbDep, _=Depends(get_manager_user)):
    try:
        services.remove_recipe_line(db, line_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ── Variants ──────────────────────────────────────────────────────────

@router.post("/dining/items/{item_id}/variants", response_model=DiningItemVariantRead,
             status_code=status.HTTP_201_CREATED)
def add_variant(item_id: int, data: DiningItemVariantCreate, db: DbDep, _=Depends(get_manager_user)):
    try:
        variant = services.add_variant(db, item_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return DiningItemVariantRead.model_validate(services.build_variant_read(variant))


@router.patch("/dining/variants/{variant_id}", response_model=DiningItemVariantRead)
def update_variant(variant_id: int, data: DiningItemVariantUpdate, db: DbDep, _=Depends(get_manager_user)):
    try:
        variant = services.update_variant(db, variant_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return DiningItemVariantRead.model_validate(services.build_variant_read(variant))


@router.delete("/dining/variants/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_variant(variant_id: int, db: DbDep, _=Depends(get_manager_user)):
    try:
        services.remove_variant(db, variant_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.post("/dining/variants/{variant_id}/recipe-lines", response_model=DiningItemVariantRecipeLineRead,
             status_code=status.HTTP_201_CREATED)
def add_variant_recipe_line(variant_id: int, data: DiningItemVariantRecipeLineCreate, db: DbDep, _=Depends(get_manager_user)):
    try:
        line = services.add_variant_recipe_line(db, variant_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return DiningItemVariantRecipeLineRead.model_validate(services.build_variant_recipe_line_read(line))


@router.patch("/dining/variant-recipe-lines/{line_id}", response_model=DiningItemVariantRecipeLineRead)
def update_variant_recipe_line(line_id: int, data: DiningItemVariantRecipeLineUpdate, db: DbDep, _=Depends(get_manager_user)):
    try:
        line = services.update_variant_recipe_line(db, line_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return DiningItemVariantRecipeLineRead.model_validate(services.build_variant_recipe_line_read(line))


@router.delete("/dining/variant-recipe-lines/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_variant_recipe_line(line_id: int, db: DbDep, _=Depends(get_manager_user)):
    try:
        services.remove_variant_recipe_line(db, line_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ── Reporting / Food Cost ─────────────────────────────────────────────

@router.get("/dining/outlets/{outlet_id}/reports/food-cost", response_model=FoodCostReportResponse)
def get_food_cost_report(
    outlet_id: int, db: DbDep, _=Depends(get_manager_user),
    date_from: date = Query(default_factory=lambda: business_today(settings.TIMEZONE) - timedelta(days=30)),
    date_to: date = Query(default_factory=lambda: business_today(settings.TIMEZONE)),
    threshold_pct: Decimal = Query(DEFAULT_FOOD_COST_THRESHOLD_PCT, gt=0, le=100),
):
    outlet = crud.get_outlet(db, outlet_id)
    if not outlet:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المنفذ غير موجود")
    if date_from > date_to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "date_from لازم يكون قبل أو يساوي date_to")
    return services.get_food_cost_report(db, outlet.branch_id, date_from, date_to, outlet_id, threshold_pct)


@router.get("/dining/outlets/{outlet_id}/reports/food-cost/export")
def download_food_cost_report_excel(
    outlet_id: int, db: DbDep, _=Depends(get_manager_user),
    date_from: date = Query(default_factory=lambda: business_today(settings.TIMEZONE) - timedelta(days=30)),
    date_to: date = Query(default_factory=lambda: business_today(settings.TIMEZONE)),
    threshold_pct: Decimal = Query(DEFAULT_FOOD_COST_THRESHOLD_PCT, gt=0, le=100),
):
    outlet = crud.get_outlet(db, outlet_id)
    if not outlet:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المنفذ غير موجود")
    if date_from > date_to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "date_from لازم يكون قبل أو يساوي date_to")
    xlsx = services.generate_food_cost_excel(db, outlet.branch_id, date_from, date_to, outlet_id, threshold_pct)
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=dining-food-cost-report.xlsx"},
    )


@router.get("/dining/reports/food-cost", response_model=FoodCostReportResponse)
def get_branch_food_cost_report(
    db: DbDep, _=Depends(get_manager_user), branch_id: int = Query(...),
    date_from: date = Query(default_factory=lambda: business_today(settings.TIMEZONE) - timedelta(days=30)),
    date_to: date = Query(default_factory=lambda: business_today(settings.TIMEZONE)),
    threshold_pct: Decimal = Query(DEFAULT_FOOD_COST_THRESHOLD_PCT, gt=0, le=100),
):
    """نفس تقرير المنفذ الواحد فوق، بس على مستوى الفرع كله (كل الـ outlets
    مجمّعين معًا) — تقرير موحّد كان مستحيل قبل الدمج من غير استعلامين
    منفصلين + دمج يدوي (راجع wagdy.md "ما يكسبه الدمج: تقارير موحدة")."""
    if date_from > date_to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "date_from لازم يكون قبل أو يساوي date_to")
    return services.get_food_cost_report(db, branch_id, date_from, date_to, None, threshold_pct)


# ── Tables ────────────────────────────────────────────────────────────

@router.get("/dining/outlets/{outlet_id}/tables", response_model=list[DiningTableRead])
def list_tables(outlet_id: int, db: DbDep, _=Depends(get_current_active_user)):
    return [DiningTableRead.model_validate(t) for t in crud.list_tables(db, outlet_id)]


@router.post("/dining/outlets/{outlet_id}/tables", response_model=DiningTableRead,
             status_code=status.HTTP_201_CREATED)
def create_table(outlet_id: int, data: DiningTableCreate, db: DbDep, _=Depends(get_manager_user)):
    if data.outlet_id != outlet_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "outlet_id في الجسم لازم يطابق المسار")
    table = crud.create_table(db, data)
    db.commit()
    db.refresh(table)
    return DiningTableRead.model_validate(table)


@router.patch("/dining/tables/{table_id}", response_model=DiningTableRead)
def update_table(table_id: int, data: DiningTableUpdate, db: DbDep, _=Depends(get_manager_user)):
    table = crud.get_table(db, table_id)
    if not table:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الطاولة غير موجودة")
    table = crud.update_table(db, table, data)
    db.commit()
    db.refresh(table)
    return DiningTableRead.model_validate(table)


@router.patch("/dining/tables/{table_id}/grid", response_model=DiningTableRead)
async def update_table_grid(table_id: int, data: DiningTableGridUpdate, db: DbDep, _=Depends(get_manager_user)):
    table = crud.get_table(db, table_id)
    if not table:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الطاولة غير موجودة")
    table = crud.update_table_grid(db, table, data.grid_row, data.grid_col)
    db.commit()
    db.refresh(table)
    await dining_manager.broadcast(str(table.branch_id), {"type": "table_updated", "table_id": table.id})
    return DiningTableRead.model_validate(table)


@router.delete("/dining/tables/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_table(table_id: int, db: DbDep, _=Depends(get_manager_user)):
    table = crud.get_table(db, table_id)
    if not table:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الطاولة غير موجودة")
    if table.status == "occupied":
        raise HTTPException(status.HTTP_409_CONFLICT, "لا يمكن حذف طاولة مشغولة")
    crud.delete_table(db, table_id)
    db.commit()


# ── Orders ────────────────────────────────────────────────────────────

@router.get("/dining/orders", response_model=PaginatedResponse)
def list_orders(
    db: DbDep, _=Depends(get_cashier_user),
    branch_id: int = Query(...), outlet_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    order_date: Optional[date] = Query(None),
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
):
    items, total = crud.list_orders(db, branch_id, outlet_id, status_filter, order_date,
                                    (page - 1) * size, size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[OrderRead.model_validate(o) for o in items])


@router.post("/dining/outlets/{outlet_id}/orders", response_model=OrderRead,
             status_code=status.HTTP_201_CREATED)
def create_order(outlet_id: int, data: OrderCreate, db: DbDep, user=Depends(get_waiter_user)):
    if data.outlet_id != outlet_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "outlet_id في الجسم لازم يطابق المسار")
    outlet = crud.get_outlet(db, outlet_id)
    if not outlet:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المنفذ غير موجود")
    try:
        return services.create_order(db, outlet.branch_id, data, waiter_id=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/dining/outlets/{outlet_id}/orders/hold", response_model=OrderRead,
             status_code=status.HTTP_201_CREATED)
def hold_order(outlet_id: int, data: OrderCreate, db: DbDep, user=Depends(get_waiter_user)):
    """طلب معلّق — راجع restaurant.hold_order. ⚠️ مسجّل قبل /{order_id} عمداً."""
    if data.outlet_id != outlet_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "outlet_id في الجسم لازم يطابق المسار")
    outlet = crud.get_outlet(db, outlet_id)
    if not outlet:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المنفذ غير موجود")
    try:
        return services.create_order(db, outlet.branch_id, data, waiter_id=user.id, hold=True)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/dining/outlets/{outlet_id}/orders/held", response_model=list[OrderRead])
def list_held_orders(outlet_id: int, db: DbDep, _=Depends(get_waiter_user)):
    outlet = crud.get_outlet(db, outlet_id)
    if not outlet:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المنفذ غير موجود")
    items, _total = crud.list_orders(db, outlet.branch_id, outlet_id, status="held", limit=100)
    return [OrderRead.model_validate(o) for o in items]


@router.post("/dining/outlets/{outlet_id}/orders/sync", response_model=OrderSyncResponse)
def sync_offline_order(outlet_id: int, data: OrderSyncRequest, db: DbDep, user=Depends(get_waiter_user)):
    """Offline POS sync — راجع restaurant.services.sync_offline_order.
    ⚠️ مسجّل قبل /{order_id} عمداً."""
    if data.outlet_id != outlet_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "outlet_id في الجسم لازم يطابق المسار")
    outlet = crud.get_outlet(db, outlet_id)
    if not outlet:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المنفذ غير موجود")
    result = services.sync_offline_order(db, outlet.branch_id, data, waiter_id=user.id)
    return OrderSyncResponse(
        order_id=result["order_id"],
        status=result["status"],
        fulfilled_items=[OrderItemRead.model_validate(i) for i in result["fulfilled_items"]],
        rejected_items=result["rejected_items"],
        message=result["message"],
    )


@router.get("/dining/orders/{order_id}", response_model=OrderRead)
def get_order(order_id: int, db: DbDep, _=Depends(get_current_active_user)):
    order = crud.get_order(db, order_id)
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"الطلب {order_id} غير موجود")
    return OrderRead.model_validate(order)


@router.patch("/dining/orders/{order_id}/status", response_model=OrderRead)
async def update_order_status(order_id: int, data: OrderStatusUpdate, db: DbDep, user=Depends(get_waiter_user)):
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
        await dining_manager.broadcast(str(order.branch_id), {"type": "tickets_updated", "order_id": order.id})
    if data.status in ("in_kitchen", "served", "paid", "cancelled") and order.table_id:
        await dining_manager.broadcast(f"tables-{order.branch_id}", {
            "type": "table_updated", "table_id": order.table_id,
        })
    return order


@router.patch("/dining/orders/{order_id}/transfer", response_model=OrderRead)
async def transfer_order_table(order_id: int, data: OrderTransferRequest,
                               db: DbDep, user=Depends(get_waiter_user)):
    """نقل طلب مفتوح لطاولة تانية (الضيوف اتحركوا فعليًا) — نفس مستوى صلاحية
    باقي عمليات التشغيل اليومية على الطلب (get_waiter_user)، مش إجراء مالي.
    راجع restaurant.api.router.transfer_order_table — نفس المنطق بالظبط."""
    try:
        order = services.transfer_order_table(db, order_id, data.table_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    await dining_manager.broadcast(f"tables-{order.branch_id}", {
        "type": "table_updated", "table_id": order.table_id,
    })
    return order


@router.patch("/dining/orders/{order_id}/items/{item_id}/status", response_model=OrderRead)
async def update_order_item_status(order_id: int, item_id: int, data: OrderItemStatusUpdate,
                                    db: DbDep, _=Depends(get_current_active_user)):
    """تأكيد صنف واحد داخل تذكرة مطبخ (bump فردي من شاشة KDS) — نفس مستوى
    صلاحية تأكيد التذكرة كلها (get_current_active_user، أي موظف مسجّل دخول
    زي طاقم المطبخ)، مش إجراء مالي. راجع
    restaurant.api.router.update_order_item_status — نفس المنطق بالظبط."""
    try:
        order = services.bump_order_item_status(db, order_id, item_id, data.status)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    await dining_manager.broadcast(str(order.branch_id), {"type": "tickets_updated", "order_id": order.id})
    return order


@router.patch("/dining/orders/{order_id}/items/{item_id}/void", response_model=OrderRead,
              dependencies=[Depends(require_permission("dining.void_order_item", "execute", min_role_level=40))])
def void_order_item(order_id: int, item_id: int, data: OrderItemVoidRequest, db: DbDep, user=Depends(get_current_active_user)):
    """إلغاء صنف واحد بسبب إجباري — نفس مستوى restaurant/cafe
    void_order_item (كاشير+، PIN موافقة مدير لو أقل من مدير)."""
    try:
        return services.void_order_item(
            db, order_id, item_id, data.reason, voided_by=user.id,
            acting_user_level=user_level(user),
            approver_user_id=data.approver_user_id, approver_pin=data.approver_pin,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/dining/orders/{order_id}/items", response_model=OrderRead, status_code=status.HTTP_200_OK)
async def add_items_to_order(order_id: int, items: list[OrderItemCreate], db: DbDep, user=Depends(get_waiter_user)):
    if not items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "لازم تضيف صنف واحد على الأقل")
    try:
        order = services.add_items_to_order(db, order_id, items)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    if order.status == "in_kitchen":
        await dining_manager.broadcast(str(order.branch_id), {"type": "tickets_updated", "order_id": order.id})
    return order


@router.patch("/dining/orders/{order_id}/items/{item_id}/refund", response_model=OrderRead,
              dependencies=[Depends(require_permission("dining.refund_order_item", "execute", min_role_level=60))])
def refund_order_item(order_id: int, item_id: int, data: OrderItemVoidRequest, db: DbDep, user=Depends(get_current_active_user)):
    """مرتجع بعد الدفع — مستوى مدير (60)، نفس restaurant/cafe.refund_order_item."""
    try:
        return services.refund_order_item(db, order_id, item_id, data.reason, refunded_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/dining/orders/{order_id}/receipt")
def download_receipt(order_id: int, db: DbDep, _=Depends(get_cashier_user)):
    try:
        pdf = services.generate_receipt_pdf(db, order_id)
        return Response(
            content=pdf, media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename=dining-receipt-{order_id}.pdf"},
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.post("/dining/orders/{order_id}/discount", response_model=OrderRead)
def apply_discount(
    order_id: int, data: ApplyDiscountRequest, db: DbDep, user=Depends(get_cashier_user),
):
    """تطبيق أفضل قاعدة خصم سارية (كاشير+) — الكاشير صفر صلاحية خصم فعليًا،
    فالطلب محتاج موافقة PIN مدير/محاسب حاضر (resolve_pin_approval، مدير+
    مؤهّل بنفسه من غير موافقة). راجع services.apply_order_discount."""
    try:
        return services.apply_order_discount(
            db, order_id, applied_by=user.id,
            acting_user_level=user_level(user),
            approver_user_id=data.approver_user_id, approver_pin=data.approver_pin,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Kitchen / KDS ────────────────────────────────────────────────────

@router.get("/dining/kitchen/tickets", response_model=list[KitchenTicketRead])
def list_kitchen_tickets(
    db: DbDep, _=Depends(get_current_active_user),
    branch_id: int = Query(...), outlet_id: Optional[int] = Query(None),
    stations: Optional[str] = Query(None, description="Comma-separated list of stations"),
):
    """قائمة تذاكر الـ KDS المعلقة — outlet_id اختياري (None = كل الـ
    outlets في الفرع، الرؤية الموحّدة اللي بررتها مذكرة Mohamed المعمارية:
    "نفس المطبخ (KDS)" لكل الـ outlets)."""
    station_list = [s.strip() for s in stations.split(",")] if stations else None
    tickets = services.get_kds_tickets(db, branch_id, outlet_id=outlet_id, stations=station_list)
    return [KitchenTicketRead.model_validate(t) for t in tickets]


@router.patch("/dining/kitchen/tickets/{ticket_id}/status", response_model=KitchenTicketRead)
async def update_ticket_status(ticket_id: int, data: TicketStatusUpdate, db: DbDep, _=Depends(get_current_active_user)):
    """يحدّث حالة تذكرة الـ KDS كاملة (pending → in_progress → done) — تأكيد
    دفعة واحدة. لو التذكرة اتأكدت done، أي صنف لسه pending/in_kitchen جواها
    بيترقّى لـ ready تلقائيًا (راجع services.update_kitchen_ticket_status)."""
    try:
        ticket_dict = services.update_kitchen_ticket_status(db, ticket_id, data.status)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    await dining_manager.broadcast(str(ticket_dict["branch_id"]), {"type": "tickets_updated", "ticket_id": ticket_dict["id"]})
    return KitchenTicketRead.model_validate(ticket_dict)


@router.get("/dining/kds-screens", response_model=list[KDSScreenRead])
def list_kds_screens(db: DbDep, _=Depends(get_current_active_user), branch_id: int = Query(...)):
    screens = crud.list_kds_screens(db, branch_id)
    return [KDSScreenRead.model_validate(s) for s in screens]


@router.post("/dining/kds-screens", response_model=KDSScreenRead, status_code=status.HTTP_201_CREATED)
def create_kds_screen(data: KDSScreenCreate, db: DbDep, _=Depends(get_manager_user)):
    screen = crud.create_kds_screen(db, data.model_dump())
    db.commit()
    db.refresh(screen)
    return KDSScreenRead.model_validate(screen)


# ── Sales Dashboard (موحّد — راجع cafe.api.router.get_cafe_sales_report) ──

@router.get("/dining/outlets/{outlet_id}/reports/sales")
def get_outlet_sales_report(
    outlet_id: int, db: DbDep, _=Depends(get_manager_user),
    date_from: date = Query(default_factory=lambda: business_today(settings.TIMEZONE) - timedelta(days=7)),
    date_to: date = Query(default_factory=lambda: business_today(settings.TIMEZONE)),
):
    """لوحة مبيعات منفذ واحد — إجماليات + breakdown طريقة الدفع + أكثر
    الأصناف مبيعًا. راجع cafe.api.router.get_cafe_sales_report — نفس
    المنطق بالظبط، بس شغّال لأي outlet_type بدل الكافيه بس (وده بالظبط
    الهدف من الدمج: تقرير واحد لكل المنافذ)."""
    if date_from > date_to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "date_from لازم يكون قبل أو يساوي date_to")

    outlet = crud.get_outlet(db, outlet_id)
    if not outlet:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المنفذ غير موجود")

    from app.modules.dining.models import DiningOrder, DiningOrderItem  # noqa: PLC0415
    from app.resort_os.timezone_utils import local_date_to_utc_range  # noqa: PLC0415
    from sqlalchemy import func  # noqa: PLC0415

    range_start, _ = local_date_to_utc_range(date_from, settings.TIMEZONE)
    _, range_end = local_date_to_utc_range(date_to, settings.TIMEZONE)

    paid_orders = db.query(DiningOrder).filter(
        DiningOrder.outlet_id == outlet_id,
        DiningOrder.status == "paid",
        DiningOrder.created_at >= range_start,
        DiningOrder.created_at <= range_end,
    ).all()

    total_orders = len(paid_orders)
    total_revenue = sum(o.total for o in paid_orders)
    total_vat = sum(o.vat_amount for o in paid_orders)
    total_discount = sum(o.discount_amount for o in paid_orders)

    payment_breakdown: dict[str, dict] = {}
    for o in paid_orders:
        method = o.payment_method or "cash"
        payment_breakdown.setdefault(method, {"orders": 0, "total": Decimal("0")})
        payment_breakdown[method]["orders"] += 1
        payment_breakdown[method]["total"] += o.total

    order_ids = [o.id for o in paid_orders]
    top_items = []
    if order_ids:
        rows = (
            db.query(DiningOrderItem.name,
                     func.sum(DiningOrderItem.quantity).label("qty"),
                     func.sum(DiningOrderItem.unit_price * DiningOrderItem.quantity).label("revenue"))
            .filter(DiningOrderItem.order_id.in_(order_ids), DiningOrderItem.status != "cancelled")
            .group_by(DiningOrderItem.name)
            .order_by(func.sum(DiningOrderItem.quantity).desc())
            .limit(10)
            .all()
        )
        top_items = [{"name": r.name, "qty": int(r.qty), "revenue": float(r.revenue)} for r in rows]

    return {
        "period": {"from": str(date_from), "to": str(date_to)},
        "outlet_id": outlet_id,
        "branch_id": outlet.branch_id,
        "total_orders": total_orders,
        "total_revenue": float(total_revenue),
        "total_vat": float(total_vat),
        "total_discount": float(total_discount),
        "avg_order_value": float(total_revenue / total_orders) if total_orders else 0,
        "payment_breakdown": {k: {"orders": v["orders"], "total": float(v["total"])} for k, v in payment_breakdown.items()},
        "top_items": top_items,
    }


# ══════════════════════════════════════════════════════════════════════
# Public Endpoints — للضيوف عبر QR (بدون auth)
# ══════════════════════════════════════════════════════════════════════
# راجع restaurant.api.router's نفس القسم (المصدر الأصلي قبل الدمج) — نفس
# المنطق بالظبط، outlet_id بدل الفصل بين restaurant/cafe. DINING_CUTOVER_PLAN.md
# Batch 6: فجوة تكافؤ حقيقية اتقفلت هنا قبل حذف restaurant/cafe — موقع
# الحجز العام (`public` app's OrderView.vue) كان بيكلّم /restaurant/public/*
# و/cafe/public/* حصريًا، بدون أي بديل هنا، فحذفهم من غير الإضافة دي كان
# هيكسر طلب الضيف عبر QR بالكامل (ميزة حقيقية شغالة، مش تجريبية).
#
# أمان: rate limited بالـ middleware (30 req/60s per IP)
#        order_type ثابت "dine_in" — نفس تقييد restaurant/cafe الأصليين
#        لا يوجد تعديل أو حذف من هنا — read + create فقط
# ══════════════════════════════════════════════════════════════════════


def _guest_status_message(order_status: str) -> str:
    # نُرجع مفتاح i18n — الـ frontend (OrderView.vue) بيترجمه عبر statusMessage().
    return {
        "open":       "status_pending",
        "held":       "status_pending",
        "in_kitchen": "status_in_kitchen",
        "served":     "status_served",
        "paid":       "status_paid",
        "cancelled":  "status_cancelled",
        "refunded":   "status_cancelled",
    }.get(order_status, "status_pending")


@router.get(
    "/dining/public/outlets",
    response_model=list[PublicOutletRead],
    tags=["dining-public"],
    summary="منافذ الفرع النشطة — بدون auth (لموقع الحجز العام)",
)
def list_public_outlets(db: DbDep, branch_id: int = Query(...)):
    """Public endpoint — لا يحتاج login. يُستدعى من apps/public's DiningView.vue
    (صفحة المنيو التسويقية) عشان تعرف outlet_id لكل منفذ قبل ما تنادي
    GET /dining/public/menu لكل واحد. راجع docstring PublicOutletRead —
    حقول محدودة عمدًا، بدون بيانات داخلية زي revenue_account_code."""
    outlets = crud.list_outlets(db, branch_id, active_only=True)
    return [PublicOutletRead.model_validate(o) for o in outlets]


@router.get(
    "/dining/public/menu",
    response_model=PublicMenuResponse,
    tags=["dining-public"],
    summary="قائمة المنفذ للضيف (QR) — بدون auth",
)
def get_public_menu(
    db: DbDep,
    outlet_id: int = Query(..., description="رقم المنفذ (مطعم/كافيه/...) — مضمّن في الـ QR"),
    table_id: Optional[int] = Query(None, description="رقم الطاولة — مضمّن في الـ QR"),
):
    """Public endpoint — لا يحتاج login. يُستدعى من apps/public's OrderView
    عند مسح QR الطاولة. يُرجع categories + items في طلب واحد لتقليل round trips."""
    outlet = crud.get_outlet(db, outlet_id)
    if not outlet:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المنفذ غير موجود")

    categories = crud.list_categories(db, outlet_id)
    items = crud.list_items(db, outlet_id, available_only=True)

    return PublicMenuResponse(
        branch_id=outlet.branch_id,
        outlet_id=outlet_id,
        outlet_name=outlet.name,
        outlet_name_ar=outlet.name_ar,
        table_id=table_id,
        categories=[PublicMenuCategoryRead.model_validate(c) for c in categories],
        items=[PublicMenuItemRead.model_validate(i) for i in items],
    )


@router.post(
    "/dining/public/orders",
    response_model=GuestOrderRead,
    status_code=status.HTTP_201_CREATED,
    tags=["dining-public"],
    summary="تقديم طلب من الضيف (QR) — بدون auth",
)
def create_guest_order(data: GuestOrderCreate, db: DbDep):
    """Public endpoint — لا يحتاج login. الضيف يطلب من القائمة عبر QR الطاولة.
    - order_type ثابت dine_in
    - waiter_id = None (النادل يتولى التذكرة من KDS/POS بعدين)
    - مفيش customer_id (ضيف مجهول، مفيش تسجيل دخول)"""
    try:
        order_data = OrderCreate(
            outlet_id=data.outlet_id,
            table_id=data.table_id,
            order_type="dine_in",
            guests_count=data.guests_count,
            notes=data.notes,
            items=[OrderItemCreate(**i.model_dump()) for i in data.items],
        )
        outlet = crud.get_outlet(db, data.outlet_id)
        if not outlet:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "المنفذ غير موجود")
        order = services.create_order(db, branch_id=outlet.branch_id, data=order_data, waiter_id=None)
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
    "/dining/public/orders/{order_id}",
    response_model=GuestOrderRead,
    tags=["dining-public"],
    summary="حالة الطلب للضيف (QR) — بدون auth",
)
def get_guest_order_status(order_id: int, db: DbDep):
    """Public endpoint — لا يحتاج login. الضيف يتابع حالة طلبه بعد التقديم
    (polling كل 10 ثواني). لا يُظهر بيانات مالية داخلية — status فقط."""
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
