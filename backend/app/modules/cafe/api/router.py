"""app/modules/cafe/api/router.py"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from app.core.deps import DbDep, get_cashier_user, get_current_active_user, get_manager_user, get_waiter_user, require_permission
from app.modules.cafe import crud, services
from app.modules.cafe.schemas import (
    CafeCategoryCreate, CafeCategoryRead,
    CafeItemCreate, CafeItemRead, CafeItemUpdate,
    CafeMenuItemExtraGroupCreate, CafeMenuItemExtraGroupRead,
    CafeOrderCreate, CafeOrderItemVoidRequest, CafeOrderRead, CafeOrderStatusUpdate,
    CafeTableRead,
)
from app.modules.core.schemas import PaginatedResponse

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
                        _=Depends(get_waiter_user)):
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
    مستوى restaurant.void_order_item."""
    try:
        return services.void_order_item(db, order_id, item_id, data.reason, voided_by=user.id)
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
