"""app/modules/maintenance/api/router.py"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import (
    DbDep, get_admin_user,
    get_employee_user, get_manager_user,
)
from app.modules.maintenance import crud, services
from app.modules.maintenance.schemas import (
    AssetCreate, AssetRead, AssetUpdate,
    PreventiveScheduleCreate, PreventiveScheduleRead, PreventiveScheduleUpdate,
    WorkOrderCreate, WorkOrderPartCreate, WorkOrderRead, WorkOrderUpdate,
)
from app.modules.core import services as core_services
from app.modules.core.schemas import PaginatedResponse

router = APIRouter(tags=["maintenance"])


def _assert_maintenance_branch(db, user, branch_id: int, action_desc: str) -> None:
    """Gate 4B-style branch isolation — كانت غايبة بالكامل من موديول
    الصيانة (اتكشف 2026-07-28، نفس فئة الباج في CRM/timeshare/beach)."""
    try:
        core_services.assert_branch_access(db, user, branch_id, action_desc)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))


# ── Assets ────────────────────────────────────────────────────────────

@router.get("/maintenance/assets", response_model=PaginatedResponse)
def list_assets(
    db: DbDep,
    user=Depends(get_employee_user),
    branch_id: int = Query(...),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
):
    _assert_maintenance_branch(db, user, branch_id, "عرض الأصول")
    items, total = crud.list_assets(db, branch_id, category, status,
                                    skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[AssetRead.model_validate(a) for a in items])


@router.post("/maintenance/assets", response_model=AssetRead,
             status_code=status.HTTP_201_CREATED)
def create_asset(data: AssetCreate, db: DbDep, user=Depends(get_manager_user)):
    _assert_maintenance_branch(db, user, data.branch_id, "إنشاء أصل")
    try:
        return services.create_asset(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


def _get_asset_or_404(db, asset_id: int):
    asset = crud.get_asset(db, asset_id)
    if not asset:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الأصل غير موجود")
    return asset


@router.get("/maintenance/assets/{asset_id}", response_model=AssetRead)
def get_asset(asset_id: int, db: DbDep, user=Depends(get_employee_user)):
    asset = _get_asset_or_404(db, asset_id)
    _assert_maintenance_branch(db, user, asset.branch_id, "عرض أصل")
    return AssetRead.model_validate(asset)


@router.patch("/maintenance/assets/{asset_id}", response_model=AssetRead)
def update_asset(asset_id: int, data: AssetUpdate, db: DbDep, user=Depends(get_manager_user)):
    asset = _get_asset_or_404(db, asset_id)
    _assert_maintenance_branch(db, user, asset.branch_id, "تعديل أصل")
    try:
        return services.update_asset(db, asset_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.post("/maintenance/assets/{asset_id}/dispose",
             response_model=AssetRead)
def dispose_asset(asset_id: int, db: DbDep, user=Depends(get_admin_user)):
    asset = _get_asset_or_404(db, asset_id)
    _assert_maintenance_branch(db, user, asset.branch_id, "التخلص من أصل")
    try:
        return services.dispose_asset(db, asset_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ── Work Orders ───────────────────────────────────────────────────────

@router.get("/maintenance/work-orders", response_model=PaginatedResponse)
def list_work_orders(
    db: DbDep,
    user=Depends(get_employee_user),
    branch_id: int = Query(...),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    asset_id: Optional[int] = Query(None),
    assigned_to: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    _assert_maintenance_branch(db, user, branch_id, "عرض أوامر الصيانة")
    items, total = crud.list_work_orders(
        db, branch_id, status, priority, asset_id, assigned_to,
        skip=(page - 1) * size, limit=size,
    )
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[WorkOrderRead.model_validate(w) for w in items])


@router.post("/maintenance/work-orders", response_model=WorkOrderRead,
             status_code=status.HTTP_201_CREATED)
def create_work_order(data: WorkOrderCreate, db: DbDep, user=Depends(get_employee_user)):
    """wagdy.md #7: أمر صيانة priority=critical كان بينسجّل من غير أي إشعار
    واتساب فوري رغم إن الـ Celery task (notify_overdue_work_orders) والبنية
    التحتية (send_whatsapp_message/notify_admin) موجودين بالفعل — كانوا بس
    مستخدمين في تنبيه يومي مجدول، مش trigger فوري وقت الإنشاء. الإرسال عبر
    .delay() (نفس نمط send_visit_survey في analytics.router) — مش synchronous
    في مسار الـ request، عشان رد الـ API للموظف اللي بيسجّل الأمر ميتأخّرش."""
    _assert_maintenance_branch(db, user, data.branch_id, "إنشاء أمر صيانة")
    try:
        wo = services.create_work_order(db, data, reported_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    if wo.priority == "critical":
        from app.tasks.maintenance_tasks import notify_critical_work_order  # noqa: PLC0415
        notify_critical_work_order.delay(wo.id)
    return wo


def _get_work_order_or_404(db, order_id: int):
    wo = crud.get_work_order(db, order_id)
    if not wo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "أمر الصيانة غير موجود")
    return wo


@router.get("/maintenance/work-orders/{order_id}", response_model=WorkOrderRead)
def get_work_order(order_id: int, db: DbDep, user=Depends(get_employee_user)):
    wo = _get_work_order_or_404(db, order_id)
    _assert_maintenance_branch(db, user, wo.branch_id, "عرض أمر صيانة")
    return WorkOrderRead.model_validate(wo)


@router.patch("/maintenance/work-orders/{order_id}", response_model=WorkOrderRead)
def update_work_order(order_id: int, data: WorkOrderUpdate, db: DbDep, user=Depends(get_employee_user)):
    wo = _get_work_order_or_404(db, order_id)
    _assert_maintenance_branch(db, user, wo.branch_id, "تعديل أمر صيانة")
    try:
        return services.update_work_order(db, order_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/maintenance/work-orders/{order_id}/complete",
             response_model=WorkOrderRead)
def complete_work_order(order_id: int, db: DbDep, user=Depends(get_manager_user)):
    wo = _get_work_order_or_404(db, order_id)
    _assert_maintenance_branch(db, user, wo.branch_id, "إنهاء أمر صيانة")
    try:
        return services.complete_work_order(db, order_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/maintenance/work-orders/{order_id}/parts",
             response_model=WorkOrderRead,
             status_code=status.HTTP_201_CREATED)
def add_part(order_id: int, data: WorkOrderPartCreate, db: DbDep, user=Depends(get_employee_user)):
    wo = _get_work_order_or_404(db, order_id)
    _assert_maintenance_branch(db, user, wo.branch_id, "إضافة قطعة غيار")
    try:
        return services.add_part_to_wo(db, order_id, data, added_by=user.id)
    except services.InventoryConcurrencyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Preventive Schedules ──────────────────────────────────────────────

@router.get("/maintenance/preventive-schedules", response_model=PaginatedResponse)
def list_schedules(
    db: DbDep,
    user=Depends(get_employee_user),
    branch_id: int = Query(...),
    active_only: bool = Query(True),
    due_before: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    _assert_maintenance_branch(db, user, branch_id, "عرض جداول الصيانة الوقائية")
    items, total = crud.list_schedules(db, branch_id, active_only, due_before,
                                       skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[PreventiveScheduleRead.model_validate(s) for s in items])


@router.post("/maintenance/preventive-schedules",
             response_model=PreventiveScheduleRead,
             status_code=status.HTTP_201_CREATED)
def create_schedule(data: PreventiveScheduleCreate, db: DbDep, user=Depends(get_manager_user)):
    _assert_maintenance_branch(db, user, data.branch_id, "إنشاء جدول صيانة وقائية")
    try:
        return services.create_schedule(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


def _get_schedule_or_404(db, schedule_id: int):
    schedule = crud.get_schedule(db, schedule_id)
    if not schedule:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الجدول غير موجود")
    return schedule


@router.patch("/maintenance/preventive-schedules/{schedule_id}",
              response_model=PreventiveScheduleRead)
def update_schedule(schedule_id: int, data: PreventiveScheduleUpdate,
                    db: DbDep, user=Depends(get_manager_user)):
    schedule = _get_schedule_or_404(db, schedule_id)
    _assert_maintenance_branch(db, user, schedule.branch_id, "تعديل جدول صيانة وقائية")
    try:
        return services.update_schedule(db, schedule_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
