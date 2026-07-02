"""app/modules/maintenance/api/router.py"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import (
    DbDep, get_admin_user, get_current_active_user,
    get_manager_user,
)
from app.modules.maintenance import crud, services
from app.modules.maintenance.schemas import (
    AssetCreate, AssetRead, AssetUpdate,
    PreventiveScheduleCreate, PreventiveScheduleRead, PreventiveScheduleUpdate,
    WorkOrderCreate, WorkOrderPartCreate, WorkOrderRead, WorkOrderUpdate,
)
from app.modules.core.schemas import PaginatedResponse

router = APIRouter(tags=["maintenance"])


# ── Assets ────────────────────────────────────────────────────────────

@router.get("/maintenance/assets", response_model=PaginatedResponse)
def list_assets(
    db: DbDep,
    _=Depends(get_current_active_user),
    branch_id: int = Query(...),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    items, total = crud.list_assets(db, branch_id, category, status,
                                    skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[AssetRead.model_validate(a) for a in items])


@router.post("/maintenance/assets", response_model=AssetRead,
             status_code=status.HTTP_201_CREATED)
def create_asset(data: AssetCreate, db: DbDep, _=Depends(get_manager_user)):
    try:
        return services.create_asset(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/maintenance/assets/{asset_id}", response_model=AssetRead)
def get_asset(asset_id: int, db: DbDep, _=Depends(get_current_active_user)):
    asset = crud.get_asset(db, asset_id)
    if not asset:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الأصل غير موجود")
    return AssetRead.model_validate(asset)


@router.patch("/maintenance/assets/{asset_id}", response_model=AssetRead)
def update_asset(asset_id: int, data: AssetUpdate, db: DbDep, _=Depends(get_manager_user)):
    try:
        return services.update_asset(db, asset_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.post("/maintenance/assets/{asset_id}/dispose",
             response_model=AssetRead)
def dispose_asset(asset_id: int, db: DbDep, _=Depends(get_admin_user)):
    try:
        return services.dispose_asset(db, asset_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ── Work Orders ───────────────────────────────────────────────────────

@router.get("/maintenance/work-orders", response_model=PaginatedResponse)
def list_work_orders(
    db: DbDep,
    _=Depends(get_current_active_user),
    branch_id: int = Query(...),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    asset_id: Optional[int] = Query(None),
    assigned_to: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    items, total = crud.list_work_orders(
        db, branch_id, status, priority, asset_id, assigned_to,
        skip=(page - 1) * size, limit=size,
    )
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[WorkOrderRead.model_validate(w) for w in items])


@router.post("/maintenance/work-orders", response_model=WorkOrderRead,
             status_code=status.HTTP_201_CREATED)
def create_work_order(data: WorkOrderCreate, db: DbDep, user=Depends(get_current_active_user)):
    try:
        return services.create_work_order(db, data, reported_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/maintenance/work-orders/{order_id}", response_model=WorkOrderRead)
def get_work_order(order_id: int, db: DbDep, _=Depends(get_current_active_user)):
    wo = crud.get_work_order(db, order_id)
    if not wo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "أمر الصيانة غير موجود")
    return WorkOrderRead.model_validate(wo)


@router.patch("/maintenance/work-orders/{order_id}", response_model=WorkOrderRead)
def update_work_order(order_id: int, data: WorkOrderUpdate, db: DbDep, _=Depends(get_current_active_user)):
    try:
        return services.update_work_order(db, order_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/maintenance/work-orders/{order_id}/complete",
             response_model=WorkOrderRead)
def complete_work_order(order_id: int, db: DbDep, _=Depends(get_manager_user)):
    try:
        return services.complete_work_order(db, order_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/maintenance/work-orders/{order_id}/parts",
             response_model=WorkOrderRead,
             status_code=status.HTTP_201_CREATED)
def add_part(order_id: int, data: WorkOrderPartCreate, db: DbDep, _=Depends(get_current_active_user)):
    try:
        return services.add_part_to_wo(db, order_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Preventive Schedules ──────────────────────────────────────────────

@router.get("/maintenance/preventive-schedules", response_model=PaginatedResponse)
def list_schedules(
    db: DbDep,
    _=Depends(get_current_active_user),
    branch_id: int = Query(...),
    active_only: bool = Query(True),
    due_before: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    items, total = crud.list_schedules(db, branch_id, active_only, due_before,
                                       skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[PreventiveScheduleRead.model_validate(s) for s in items])


@router.post("/maintenance/preventive-schedules",
             response_model=PreventiveScheduleRead,
             status_code=status.HTTP_201_CREATED)
def create_schedule(data: PreventiveScheduleCreate, db: DbDep, _=Depends(get_manager_user)):
    try:
        return services.create_schedule(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.patch("/maintenance/preventive-schedules/{schedule_id}",
              response_model=PreventiveScheduleRead)
def update_schedule(schedule_id: int, data: PreventiveScheduleUpdate,
                    db: DbDep, _=Depends(get_manager_user)):
    try:
        return services.update_schedule(db, schedule_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
