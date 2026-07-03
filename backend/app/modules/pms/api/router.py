"""app/modules/pms/api/router.py"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import (
    DbDep, get_admin_user, get_current_active_user,
    get_manager_user, require_permission,
)
from app.modules.pms import crud, services
from app.modules.pms.schemas import (
    BookingCreate, BookingRead, HousekeepingTaskRead, HousekeepingTaskStatusUpdate,
    NightAuditLogRead, RoomCreate, RoomRead,
    RoomStatusUpdate, RoomTypeCreate, RoomTypeRead,
)
from app.modules.core.schemas import PaginatedResponse

router = APIRouter(tags=["pms"])


# ── Room Types ────────────────────────────────────────────────────────

@router.get("/pms/room-types", response_model=list[RoomTypeRead])
def list_room_types(db: DbDep, _=Depends(get_current_active_user), branch_id: int = Query(...)):
    return [RoomTypeRead.model_validate(rt) for rt in crud.list_room_types(db, branch_id)]


@router.post("/pms/room-types", response_model=RoomTypeRead,
             status_code=status.HTTP_201_CREATED)
def create_room_type(data: RoomTypeCreate, db: DbDep, _=Depends(get_admin_user)):
    obj = crud.create_room_type(db, data)
    db.commit(); db.refresh(obj)
    return RoomTypeRead.model_validate(obj)


# ── Rooms ─────────────────────────────────────────────────────────────

@router.get("/pms/rooms", response_model=list[RoomRead])
def list_rooms(
    db: DbDep,
    _=Depends(get_current_active_user),
    branch_id:    int           = Query(...),
    status_filter: Optional[str] = Query(None, alias="status"),
    room_type_id:  Optional[int] = Query(None),
):
    return [RoomRead.model_validate(r) for r in crud.list_rooms(db, branch_id, status_filter, room_type_id)]


@router.get("/pms/rooms/available", response_model=list[RoomRead])
def available_rooms(
    db: DbDep,
    _=Depends(get_current_active_user),
    branch_id:    int           = Query(...),
    check_in:     date          = Query(...),
    check_out:    date          = Query(...),
    room_type_id: Optional[int] = Query(None),
):
    return [RoomRead.model_validate(r)
            for r in crud.get_available_rooms(db, branch_id, check_in, check_out, room_type_id)]


@router.post("/pms/rooms", response_model=RoomRead,
             status_code=status.HTTP_201_CREATED)
def create_room(data: RoomCreate, db: DbDep, _=Depends(get_admin_user)):
    obj = crud.create_room(db, data)
    db.commit(); db.refresh(obj)
    return RoomRead.model_validate(obj)


@router.patch("/pms/rooms/{room_id}/status", response_model=RoomRead)
def update_room_status(room_id: int, data: RoomStatusUpdate, db: DbDep, _=Depends(get_manager_user)):
    room = crud.get_room(db, room_id)
    if not room:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الغرفة غير موجودة")
    crud.update_room_status(db, room, data.status, data.notes)
    db.commit(); db.refresh(room)
    return RoomRead.model_validate(room)


# ── Bookings ──────────────────────────────────────────────────────────

@router.get("/pms/bookings", response_model=PaginatedResponse)
def list_bookings(
    db: DbDep,
    _=Depends(get_current_active_user),
    branch_id:     int           = Query(...),
    status_filter: Optional[str] = Query(None, alias="status"),
    check_in_from: Optional[date] = Query(None),
    check_in_to:   Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    items, total = crud.list_bookings(db, branch_id, status_filter,
                                      check_in_from, check_in_to,
                                      (page-1)*size, size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[BookingRead.model_validate(b) for b in items])


@router.post("/pms/bookings", response_model=BookingRead,
             status_code=status.HTTP_201_CREATED)
def create_booking(data: BookingCreate, db: DbDep, _=Depends(get_manager_user)):
    try:
        return services.create_booking(db, data)
    except services.BookingConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/pms/bookings/{booking_id}", response_model=BookingRead)
def get_booking(booking_id: int, db: DbDep, _=Depends(get_current_active_user)):
    b = crud.get_booking(db, booking_id)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الحجز غير موجود")
    return BookingRead.model_validate(b)


@router.post("/pms/bookings/{booking_id}/checkin",
             response_model=BookingRead)
def checkin(booking_id: int, db: DbDep, _=Depends(get_manager_user)):
    try:
        return services.checkin_booking(db, booking_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/pms/bookings/{booking_id}/checkout",
             response_model=BookingRead)
def checkout(booking_id: int, db: DbDep, _=Depends(get_manager_user)):
    try:
        return services.checkout_booking(db, booking_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/pms/bookings/{booking_id}/cancel",
             dependencies=[Depends(require_permission("pms.cancel_booking", "execute", min_role_level=60))],
             response_model=BookingRead)
def cancel_booking(booking_id: int, db: DbDep, user=Depends(get_current_active_user)):
    try:
        return services.cancel_booking(db, booking_id, cancelled_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Housekeeping ──────────────────────────────────────────────────────
# frontend/apps/ops/src/views/HousekeepingView.vue بينادي على الـ endpoints
# دول، والـ crud/model كانوا موجودين من زمان (checkout_booking بيعمل
# HousekeepingTask تلقائياً) — بس مفيش route كان متوصّل، فكان 404 حقيقي
# في الإنتاج زي حالة GET /restaurant/menu/categories المذكورة في § 11.6.

@router.get("/pms/housekeeping/tasks", response_model=list[HousekeepingTaskRead])
def list_housekeeping_tasks(
    db: DbDep,
    _=Depends(get_current_active_user),
    branch_id: int = Query(...),
    status_filter: Optional[str] = Query(None, alias="status"),
    room_id: Optional[int] = Query(None),
):
    return [HousekeepingTaskRead.model_validate(t)
            for t in crud.list_housekeeping_tasks(db, branch_id, status_filter, room_id)]


@router.patch("/pms/housekeeping/tasks/{task_id}", response_model=HousekeepingTaskRead)
def update_housekeeping_task_status(
    task_id: int, data: HousekeepingTaskStatusUpdate, db: DbDep,
    _=Depends(get_current_active_user),
):
    try:
        task = services.update_housekeeping_task_status(db, task_id, data.status, data.notes)
        return HousekeepingTaskRead.model_validate(task)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ── Night Audit ───────────────────────────────────────────────────────

@router.get("/pms/night-audit", response_model=list[NightAuditLogRead])
def list_night_audits(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int = Query(...),
    page: int = Query(1, ge=1), size: int = Query(30, ge=1, le=90),
):
    return [NightAuditLogRead.model_validate(l)
            for l in crud.list_night_audits(db, branch_id, (page-1)*size, size)]


@router.post("/pms/night-audit/run", response_model=NightAuditLogRead)
def run_night_audit(
    db: DbDep,
    _=Depends(get_admin_user),
    branch_id:  int  = Query(...),
    audit_date: date = Query(...),
):
    try:
        return services.run_night_audit(db, branch_id, audit_date)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
