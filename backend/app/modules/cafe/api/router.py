"""app/modules/cafe/api/router.py"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from app.core.deps import DbDep, get_cashier_user, get_current_active_user, get_manager_user, get_waiter_user, require_module
from app.modules.cafe import crud, services
from app.modules.cafe.schemas import (
    CafeCategoryCreate, CafeCategoryRead,
    CafeItemCreate, CafeItemRead, CafeItemUpdate,
    CafeOrderCreate, CafeOrderRead, CafeOrderStatusUpdate,
    CafeTableRead,
)
from app.modules.core.schemas import PaginatedResponse

router = APIRouter(tags=["cafe"])
_guard = Depends(require_module("cafe"))


@router.get("/cafe/categories", response_model=list[CafeCategoryRead], dependencies=[_guard])
def list_categories(db: DbDep, _=Depends(get_current_active_user), branch_id: int = Query(...)):
    return crud.list_categories(db, branch_id)


@router.post("/cafe/categories", response_model=CafeCategoryRead,
             status_code=status.HTTP_201_CREATED, dependencies=[_guard])
def create_category(data: CafeCategoryCreate, db: DbDep, _=Depends(get_manager_user)):
    obj = crud.create_category(db, data)
    db.commit(); db.refresh(obj)
    return obj


@router.get("/cafe/items", response_model=list[CafeItemRead], dependencies=[_guard])
def list_items(db: DbDep, _=Depends(get_current_active_user),
               branch_id: int = Query(...), category_id: Optional[int] = Query(None),
               available_only: bool = Query(True)):
    return crud.list_items(db, branch_id, category_id, available_only)


@router.post("/cafe/items", response_model=CafeItemRead,
             status_code=status.HTTP_201_CREATED, dependencies=[_guard])
def create_item(data: CafeItemCreate, db: DbDep, _=Depends(get_manager_user)):
    obj = crud.create_item(db, data)
    db.commit(); db.refresh(obj)
    return obj


@router.patch("/cafe/items/{item_id}", response_model=CafeItemRead, dependencies=[_guard])
def update_item(item_id: int, data: CafeItemUpdate, db: DbDep, _=Depends(get_manager_user)):
    item = crud.get_item(db, item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الصنف غير موجود")
    obj = crud.update_item(db, item, data)
    db.commit(); db.refresh(obj)
    return obj


@router.get("/cafe/tables", response_model=list[CafeTableRead], dependencies=[_guard])
def list_tables(db: DbDep, _=Depends(get_current_active_user), branch_id: int = Query(...)):
    return crud.list_tables(db, branch_id)


@router.get("/cafe/orders", response_model=PaginatedResponse, dependencies=[_guard])
def list_orders(
    db: DbDep, _=Depends(get_current_active_user),
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
             status_code=status.HTTP_201_CREATED, dependencies=[_guard])
def create_order(data: CafeOrderCreate, db: DbDep, user=Depends(get_waiter_user)):
    try:
        return services.create_order(db, data, waiter_id=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/cafe/orders/{order_id}", response_model=CafeOrderRead, dependencies=[_guard])
def get_order(order_id: int, db: DbDep, _=Depends(get_current_active_user)):
    order = crud.get_order(db, order_id)
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الطلب غير موجود")
    return CafeOrderRead.model_validate(order)


@router.patch("/cafe/orders/{order_id}/status", response_model=CafeOrderRead, dependencies=[_guard])
def update_order_status(order_id: int, data: CafeOrderStatusUpdate, db: DbDep,
                        _=Depends(get_waiter_user)):
    try:
        return services.update_order_status(db, order_id, data.status)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/cafe/orders/{order_id}/receipt", dependencies=[_guard])
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
