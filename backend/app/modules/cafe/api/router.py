"""app/modules/cafe/api/router.py"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from app.core.config import settings
from app.core.deps import (
    DbDep, get_cashier_user, get_current_active_user, get_manager_user,
    get_waiter_user, require_permission, user_level,
)
from app.modules.cafe import crud, services
from app.modules.cafe.schemas import (
    CafeCategoryCreate, CafeCategoryRead,
    CafeFoodCostReportResponse,
    CafeGuestOrderCreate, CafeGuestOrderRead,
    CafeItemCreate, CafeItemRead, CafeItemUpdate,
    CafeItemRecipeLineCreate, CafeItemRecipeLineRead, CafeItemRecipeLineUpdate,
    CafeItemVariantCreate, CafeItemVariantRead, CafeItemVariantRecipeLineCreate,
    CafeItemVariantRecipeLineRead, CafeItemVariantRecipeLineUpdate, CafeItemVariantUpdate,
    CafeMenuItemExtraGroupCreate, CafeMenuItemExtraGroupRead,
    CafeOrderCreate, CafeOrderItemCreate, CafeOrderItemVoidRequest, CafeOrderRead, CafeOrderStatusUpdate,
    CafePublicMenuCategoryRead, CafePublicMenuItemRead, CafePublicMenuResponse,
    CafeTableRead,
)
from app.modules.core.schemas import PaginatedResponse
from app.resort_os.food_cost_engine import DEFAULT_FOOD_COST_THRESHOLD_PCT
from app.resort_os.timezone_utils import business_today

router = APIRouter(tags=["cafe"])


@router.get("/cafe/categories", response_model=list[CafeCategoryRead])
def list_categories(db: DbDep, _=Depends(get_current_active_user), branch_id: int = Query(...)):
    return crud.list_categories(db, branch_id)


@router.post("/cafe/categories", response_model=CafeCategoryRead,
             status_code=status.HTTP_201_CREATED)
def create_category(data: CafeCategoryCreate, db: DbDep, _=Depends(get_manager_user)):
    obj = crud.create_category(db, data)
    db.commit(); db.refresh(obj)
    return obj


@router.get("/cafe/items", response_model=list[CafeItemRead])
def list_items(db: DbDep, _=Depends(get_current_active_user),
               branch_id: int = Query(...), category_id: Optional[int] = Query(None),
               available_only: bool = Query(True)):
    return crud.list_items(db, branch_id, category_id, available_only)


@router.post("/cafe/items", response_model=CafeItemRead,
             status_code=status.HTTP_201_CREATED)
def create_item(data: CafeItemCreate, db: DbDep, _=Depends(get_manager_user)):
    obj = crud.create_item(db, data)
    db.commit(); db.refresh(obj)
    return obj


@router.patch("/cafe/items/{item_id}", response_model=CafeItemRead)
def update_item(item_id: int, data: CafeItemUpdate, db: DbDep, _=Depends(get_manager_user)):
    item = crud.get_item(db, item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الصنف غير موجود")
    obj = crud.update_item(db, item, data)
    db.commit(); db.refresh(obj)
    return obj


@router.post("/cafe/menu/items/{item_id}/extra-groups",
             response_model=CafeMenuItemExtraGroupRead,
             status_code=status.HTTP_201_CREATED)
def create_extra_group(item_id: int, data: CafeMenuItemExtraGroupCreate, db: DbDep, _=Depends(get_manager_user)):
    item = crud.get_item(db, item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الصنف غير موجود")
    group = crud.create_extra_group(db, item_id, data)
    db.commit()
    db.refresh(group)
    return CafeMenuItemExtraGroupRead.model_validate(group)


@router.delete("/cafe/menu/extra-groups/{group_id}",
               status_code=status.HTTP_204_NO_CONTENT)
def delete_extra_group(group_id: int, db: DbDep, _=Depends(get_manager_user)):
    if not crud.delete_extra_group(db, group_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المجموعة غير موجودة")
    db.commit()


# ── Recipe / BOM ──────────────────────────────────────────────────────
# نفس نمط restaurant.router بالضبط — راجع التعليقات هناك.

@router.post("/cafe/items/{item_id}/recipe-lines",
             response_model=CafeItemRecipeLineRead,
             status_code=status.HTTP_201_CREATED)
def add_recipe_line(item_id: int, data: CafeItemRecipeLineCreate, db: DbDep, _=Depends(get_manager_user)):
    try:
        line = services.add_recipe_line(db, item_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return CafeItemRecipeLineRead.model_validate(services.build_recipe_line_read(line))


@router.patch("/cafe/recipe-lines/{line_id}", response_model=CafeItemRecipeLineRead)
def update_recipe_line(line_id: int, data: CafeItemRecipeLineUpdate, db: DbDep, _=Depends(get_manager_user)):
    try:
        line = services.update_recipe_line(db, line_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return CafeItemRecipeLineRead.model_validate(services.build_recipe_line_read(line))


@router.delete("/cafe/recipe-lines/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe_line(line_id: int, db: DbDep, _=Depends(get_manager_user)):
    try:
        services.remove_recipe_line(db, line_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ── Variants (حجم/نوع حقيقي) ─────────────────────────────────────────
# نفس نمط restaurant.router بالضبط — راجع التعليقات هناك.

@router.post("/cafe/items/{item_id}/variants",
             response_model=CafeItemVariantRead,
             status_code=status.HTTP_201_CREATED)
def add_variant(item_id: int, data: CafeItemVariantCreate, db: DbDep, _=Depends(get_manager_user)):
    try:
        variant = services.add_variant(db, item_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return CafeItemVariantRead.model_validate(services.build_variant_read(variant))


@router.patch("/cafe/variants/{variant_id}", response_model=CafeItemVariantRead)
def update_variant(variant_id: int, data: CafeItemVariantUpdate, db: DbDep, _=Depends(get_manager_user)):
    try:
        variant = services.update_variant(db, variant_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return CafeItemVariantRead.model_validate(services.build_variant_read(variant))


@router.delete("/cafe/variants/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_variant(variant_id: int, db: DbDep, _=Depends(get_manager_user)):
    try:
        services.remove_variant(db, variant_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.post("/cafe/variants/{variant_id}/recipe-lines",
             response_model=CafeItemVariantRecipeLineRead,
             status_code=status.HTTP_201_CREATED)
def add_variant_recipe_line(variant_id: int, data: CafeItemVariantRecipeLineCreate, db: DbDep, _=Depends(get_manager_user)):
    try:
        line = services.add_variant_recipe_line(db, variant_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return CafeItemVariantRecipeLineRead.model_validate(services.build_variant_recipe_line_read(line))


@router.patch("/cafe/variant-recipe-lines/{line_id}", response_model=CafeItemVariantRecipeLineRead)
def update_variant_recipe_line(line_id: int, data: CafeItemVariantRecipeLineUpdate, db: DbDep, _=Depends(get_manager_user)):
    try:
        line = services.update_variant_recipe_line(db, line_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return CafeItemVariantRecipeLineRead.model_validate(services.build_variant_recipe_line_read(line))


@router.delete("/cafe/variant-recipe-lines/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_variant_recipe_line(line_id: int, db: DbDep, _=Depends(get_manager_user)):
    try:
        services.remove_variant_recipe_line(db, line_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ── Reporting / Food Cost ─────────────────────────────────────────────
# نفس منطق restaurant.api.router.get_food_cost_report بالضبط.

@router.get("/cafe/reports/food-cost", response_model=CafeFoodCostReportResponse)
def get_food_cost_report(
    db: DbDep,
    _=Depends(get_manager_user),
    branch_id: int = Query(...),
    date_from: date = Query(default_factory=lambda: business_today(settings.TIMEZONE) - timedelta(days=30)),
    date_to: date = Query(default_factory=lambda: business_today(settings.TIMEZONE)),
    threshold_pct: Decimal = Query(DEFAULT_FOOD_COST_THRESHOLD_PCT, gt=0, le=100),
):
    if date_from > date_to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "date_from لازم يكون قبل أو يساوي date_to")
    return services.get_food_cost_report(db, branch_id, date_from, date_to, threshold_pct)


@router.get("/cafe/tables", response_model=list[CafeTableRead])
def list_tables(db: DbDep, _=Depends(get_current_active_user), branch_id: int = Query(...)):
    return crud.list_tables(db, branch_id)


@router.get("/cafe/orders", response_model=PaginatedResponse)
def list_orders(
    db: DbDep, _=Depends(get_cashier_user),
    branch_id: int = Query(...),
    order_status: Optional[str] = Query(None, alias="status"),
    order_date: Optional[date] = Query(None),
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
):
    items, total = crud.list_orders(db, branch_id, order_status, order_date,
                                    skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[CafeOrderRead.model_validate(o) for o in items])


@router.post("/cafe/orders", response_model=CafeOrderRead,
             status_code=status.HTTP_201_CREATED)
def create_order(data: CafeOrderCreate, db: DbDep, user=Depends(get_waiter_user)):
    try:
        return services.create_order(db, data, waiter_id=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/cafe/orders/hold", response_model=CafeOrderRead,
             status_code=status.HTTP_201_CREATED)
def hold_order(data: CafeOrderCreate, db: DbDep, user=Depends(get_waiter_user)):
    """طلب معلّق — الجرسون يحفظ الأوردر من غير ما يبعته للمطبخ، يرجعله
    بعدين بـ PATCH .../status → open. مسجّل قبل /{order_id} عمداً — نفس
    سبب restaurant.hold_order."""
    try:
        return services.create_order(db, data, waiter_id=user.id, hold=True)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/cafe/orders/held", response_model=list[CafeOrderRead])
def list_held_orders(db: DbDep, _=Depends(get_waiter_user), branch_id: int = Query(...)):
    """الجرسون يقدر يشوف الطلبات المعلّقة بس (مش كل الأوردرات — دي للكاشير)."""
    items, _total = crud.list_orders(db, branch_id, status="held", limit=100)
    return [CafeOrderRead.model_validate(o) for o in items]


@router.get("/cafe/orders/{order_id}", response_model=CafeOrderRead)
def get_order(order_id: int, db: DbDep, _=Depends(get_current_active_user)):
    order = crud.get_order(db, order_id)
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الطلب غير موجود")
    return CafeOrderRead.model_validate(order)


@router.patch("/cafe/orders/{order_id}/status", response_model=CafeOrderRead)
async def update_order_status(order_id: int, data: CafeOrderStatusUpdate, db: DbDep,
                        user=Depends(get_waiter_user)):
    # نفس القاعدة في restaurant.update_order_status: "مدفوع" فعل مالي
    # (charge على فوليو، قيد إيراد، خصم مخزون) — كاشير أو أعلى بس.
    if data.status == "paid" and user_level(user) < 40:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "إتمام الدفع يتطلب صلاحية كاشير على الأقل")
    try:
        order = services.update_order_status(db, order_id, data.status, charge_to_room_id=data.charge_to_room_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    if data.status == "in_kitchen":
        from app.modules.restaurant.api.router import restaurant_manager  # noqa: PLC0415
        await restaurant_manager.broadcast(str(order.branch_id), {"type": "tickets_updated", "order_id": order.id})
    return order


@router.patch("/cafe/orders/{order_id}/items/{item_id}/void",
              response_model=CafeOrderRead,
              dependencies=[Depends(require_permission("cafe.void_order_item", "execute", min_role_level=40))])
def void_order_item(order_id: int, item_id: int, data: CafeOrderItemVoidRequest,
                    db: DbDep, user=Depends(get_current_active_user)):
    """إلغاء صنف واحد بسبب إجباري — كاشير أو أعلى بس (مش الجرسون)، نفس
    مستوى restaurant.void_order_item — بما فيه موافقة PIN لو المنفّذ أقل
    من مدير."""
    try:
        return services.void_order_item(
            db, order_id, item_id, data.reason, voided_by=user.id,
            acting_user_level=user_level(user),
            approver_user_id=data.approver_user_id, approver_pin=data.approver_pin,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.patch("/cafe/orders/{order_id}/items/{item_id}/refund",
              response_model=CafeOrderRead,
              dependencies=[Depends(require_permission("cafe.refund_order_item", "execute", min_role_level=60))])
def refund_order_item(order_id: int, item_id: int, data: CafeOrderItemVoidRequest,
                      db: DbDep, user=Depends(get_current_active_user)):
    """مرتجع بعد الدفع — مستوى مدير (60)، نفس مستوى restaurant.refund_order_item."""
    try:
        return services.refund_order_item(db, order_id, item_id, data.reason, refunded_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/cafe/orders/{order_id}/discount", response_model=CafeOrderRead)
def apply_discount(order_id: int, db: DbDep, _=Depends(get_cashier_user)):
    """يطبّق أفضل ConditionalDiscount منطبقة (finance module) على الطلب —
    نفس مستوى وشكل restaurant.apply_discount بالظبط."""
    try:
        return services.apply_order_discount(db, order_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/cafe/orders/{order_id}/receipt")
def download_receipt(order_id: int, db: DbDep, _=Depends(get_current_active_user)):
    try:
        pdf = services.generate_receipt_pdf(db, order_id)
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename=cafe-receipt-{order_id}.pdf"},
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ══════════════════════════════════════════════════════════════════════
# Public Endpoint — للموقع العام (بدون auth)
# ══════════════════════════════════════════════════════════════════════
# ⚠️ هذا الـ endpoint بدون authentication عمداً — نفس نمط restaurant/public/menu:
#   GET /cafe/public/menu → قائمة الكافيه للزائر على الموقع العام (read-only)
#
# أمان: rate limited بالـ middleware (30 req/60s per IP، app/core/rate_limit.py)
#        لا يوجد تعديل أو حذف من هنا — read فقط
# ══════════════════════════════════════════════════════════════════════

@router.get(
    "/cafe/public/menu",
    response_model=CafePublicMenuResponse,
    tags=["cafe-public"],
    summary="قائمة الكافيه للزائر (الموقع العام) — بدون auth",
)
def get_public_menu(
    db: DbDep,
    branch_id: int = Query(..., description="رقم الفرع"),
):
    """
    Public endpoint — لا يحتاج login.
    يُستدعى من الموقع العام (apps/public) لعرض قائمة الكافيه قبل الحجز.
    يُرجع categories + items في طلب واحد لتقليل round trips.
    """
    categories = crud.list_categories(db, branch_id)
    items = crud.list_items(db, branch_id, available_only=True)

    return CafePublicMenuResponse(
        branch_id=branch_id,
        categories=[CafePublicMenuCategoryRead.model_validate(c) for c in categories],
        items=[CafePublicMenuItemRead.model_validate(i) for i in items],
    )


# ⚠️ الاثنين تحت دول بدون authentication عمداً — نفس نمط
#   restaurant/public/orders بالضبط (كان ناقص هنا، وده اللي كان بيمنع
#   الضيف من الطلب فعليًا من قائمة الكافيه عبر QR — القراءة (public/menu)
#   كانت موجودة من غير أي طريقة تقديم طلب حقيقية):
#   POST /cafe/public/orders → طلب جديد من الضيف (طاولة كافيه أو شمسية)
#   GET  /cafe/public/orders/{id} → حالة الطلب للضيف (polling)
#
# أمان: rate limited بالـ middleware (30 req/60s per IP)
#        order_type ثابت "dine_in" — لا تعديل/حذف من هنا، create + read فقط

@router.post(
    "/cafe/public/orders",
    response_model=CafeGuestOrderRead,
    status_code=status.HTTP_201_CREATED,
    tags=["cafe-public"],
    summary="تقديم طلب من الضيف (QR) — بدون auth",
)
def create_guest_order(data: CafeGuestOrderCreate, db: DbDep):
    """
    Public endpoint — لا يحتاج login.
    الضيف يطلب من قائمة الكافيه عبر QR الطاولة/الشمسية.
    - order_type مقيّد: dine_in فقط
    - waiter_id = None (الـ waiter module يتولى)
    """
    try:
        order = services.create_order(
            db,
            data=CafeOrderCreate(
                branch_id=data.branch_id,
                table_id=data.table_id,
                order_type="dine_in",
                notes=data.notes,
                items=[CafeOrderItemCreate(**i.model_dump()) for i in data.items],
            ),
            waiter_id=None,
        )
        return CafeGuestOrderRead(
            order_id=order.id,
            order_number=order.order_number,
            status=order.status,
            total=order.total,
            items_count=sum(i.quantity for i in order.items),
            message="تم استلام طلبك! سيصل إليك قريباً ☕",
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get(
    "/cafe/public/orders/{order_id}",
    response_model=CafeGuestOrderRead,
    tags=["cafe-public"],
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

    status_messages = {
        "held":       "طلبك قيد المراجعة",
        "open":       "طلبك قيد التحضير",
        "in_kitchen": "جاري تحضير طلبك 👨‍🍳",
        "served":     "تم تقديم طلبك 🎉",
        "paid":       "تم الدفع — شكراً لزيارتك ✨",
        "cancelled":  "تم إلغاء الطلب",
    }
    return CafeGuestOrderRead(
        order_id=order.id,
        order_number=order.order_number,
        status=order.status,
        total=order.total,
        items_count=sum(i.quantity for i in order.items),
        message=status_messages.get(order.status, ""),
    )
