"""app/modules/pms/crud.py — CRUD خالص"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.pms.models import (
    Booking, BookingRoom, HousekeepingTask, NightAuditLog, RatePlan, Room, RoomType,
)
from app.modules.pms.schemas import (
    BookingCreate, RoomCreate, RoomTypeCreate,
)


# ── RoomType ──────────────────────────────────────────────────────────

def list_room_types(db: Session, branch_id: int, active_only: bool = True) -> list[RoomType]:
    q = db.query(RoomType).filter(RoomType.branch_id == branch_id)
    if active_only:
        q = q.filter(RoomType.is_active.is_(True))
    return q.order_by(RoomType.base_rate).all()


def get_room_type(db: Session, room_type_id: int) -> Optional[RoomType]:
    return db.query(RoomType).filter(RoomType.id == room_type_id).first()


def create_room_type(db: Session, data: RoomTypeCreate) -> RoomType:
    obj = RoomType(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


# ── Room ──────────────────────────────────────────────────────────────

def get_room(db: Session, room_id: int) -> Optional[Room]:
    return db.query(Room).filter(Room.id == room_id).first()


def lock_room_for_booking(db: Session, room_id: int) -> Optional[Room]:
    """SELECT ... FOR UPDATE NOWAIT — يقفل صف الغرفة طوال الـ transaction
    عشان يمنع double-booking. لو غرفة تانية ماسكاها (transaction متزامن)
    تطلع OperationalError فوراً بدل ما تستنى — الـ caller يترجمها لـ 409."""
    return (
        db.query(Room)
        .filter(Room.id == room_id)
        .with_for_update(nowait=True)
        .first()
    )


def list_rooms(
    db: Session,
    branch_id: int,
    status: Optional[str] = None,
    room_type_id: Optional[int] = None,
) -> list[Room]:
    q = db.query(Room).filter(Room.branch_id == branch_id)
    if status:
        q = q.filter(Room.status == status)
    if room_type_id:
        q = q.filter(Room.room_type_id == room_type_id)
    return q.order_by(Room.name).all()


def count_rooms(db: Session, branch_id: int) -> int:
    return db.query(func.count(Room.id)).filter(Room.branch_id == branch_id).scalar() or 0


def create_room(db: Session, data: RoomCreate) -> Room:
    obj = Room(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


def update_room_status(db: Session, room: Room, status: str, notes: Optional[str] = None) -> Room:
    room.status = status
    if notes is not None:
        room.notes = notes
    db.flush()
    return room


def get_available_rooms(
    db: Session,
    branch_id: int,
    check_in: date,
    check_out: date,
    room_type_id: Optional[int] = None,
) -> list[Room]:
    """يُرجع الغرف غير المحجوزة في الفترة المطلوبة."""
    # الغرف المحجوزة في هذه الفترة
    booked_room_ids = (
        db.query(BookingRoom.room_id)
        .join(Booking)
        .filter(
            Booking.branch_id == branch_id,
            Booking.status.in_(["confirmed", "checked_in"]),
            Booking.check_in < check_out,
            Booking.check_out > check_in,
        )
        .subquery()
    )
    q = db.query(Room).filter(
        Room.branch_id == branch_id,
        Room.status == "available",
        ~Room.id.in_(select(booked_room_ids.c.room_id)),
    )
    if room_type_id:
        q = q.filter(Room.room_type_id == room_type_id)
    return q.order_by(Room.name).all()


# ── Booking ───────────────────────────────────────────────────────────

def get_booking(db: Session, booking_id: int) -> Optional[Booking]:
    return db.query(Booking).filter(Booking.id == booking_id).first()


def get_booking_by_number(db: Session, number: str) -> Optional[Booking]:
    return db.query(Booking).filter(Booking.booking_number == number).first()


def list_bookings(
    db: Session,
    branch_id: int,
    status: Optional[str] = None,
    check_in_from: Optional[date] = None,
    check_in_to: Optional[date] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Booking], int]:
    q = db.query(Booking).filter(Booking.branch_id == branch_id)
    if status:
        q = q.filter(Booking.status == status)
    if check_in_from:
        q = q.filter(Booking.check_in >= check_in_from)
    if check_in_to:
        q = q.filter(Booking.check_in <= check_in_to)
    total = q.count()
    items = q.order_by(Booking.check_in.desc()).offset(skip).limit(limit).all()
    return items, total


def generate_booking_number(db: Session, branch_id: int) -> str:
    today = datetime.utcnow().strftime("%Y%m%d")
    prefix = f"BKG-{today}-"
    count = (
        db.query(Booking)
        .filter(Booking.booking_number.like(f"{prefix}%"))
        .count()
    )
    return f"{prefix}{count + 1:04d}"


def create_booking(
    db: Session,
    booking_number: str,
    data: BookingCreate,
    room_rates: list[tuple[int, Decimal, int]],  # (room_id, daily_rate, nights)
) -> Booking:
    total_rate = sum(r * n for _, r, n in room_rates)
    booking = Booking(
        branch_id=data.branch_id,
        booking_number=booking_number,
        guest_name=data.guest_name,
        guest_phone=data.guest_phone,
        guest_email=data.guest_email,
        guest_national_id=data.guest_national_id,
        check_in=data.check_in,
        check_out=data.check_out,
        adults=data.adults,
        children=data.children,
        source=data.source,
        notes=data.notes,
        total_rate=total_rate,
    )
    db.add(booking)
    db.flush()

    for room_id, daily_rate, nights in room_rates:
        db.add(BookingRoom(
            booking_id=booking.id,
            room_id=room_id,
            daily_rate=daily_rate,
            nights=nights,
            total=(daily_rate * nights),
        ))
    db.flush()
    return booking


def update_booking_status(
    db: Session,
    booking: Booking,
    status: str,
    cancelled_by: Optional[int] = None,
) -> Booking:
    booking.status = status
    if status == "cancelled":
        booking.cancelled_at = datetime.utcnow()
        booking.cancelled_by = cancelled_by
    db.flush()
    return booking


def get_bookings_for_night_audit(
    db: Session,
    branch_id: int,
    audit_date: date,
) -> dict:
    """يجمع الإحصاءات المطلوبة للـ Night Audit."""
    occupied = (
        db.query(func.count(Booking.id))
        .filter(
            Booking.branch_id == branch_id,
            Booking.status == "checked_in",
            Booking.check_in <= audit_date,
            Booking.check_out > audit_date,
        )
        .scalar() or 0
    )
    checkouts = (
        db.query(func.count(Booking.id))
        .filter(
            Booking.branch_id == branch_id,
            Booking.check_out == audit_date,
            Booking.status.in_(["checked_in", "checked_out"]),
        )
        .scalar() or 0
    )
    checkins = (
        db.query(func.count(Booking.id))
        .filter(
            Booking.branch_id == branch_id,
            Booking.check_in == audit_date,
            Booking.status.in_(["confirmed", "checked_in"]),
        )
        .scalar() or 0
    )
    no_shows = (
        db.query(func.count(Booking.id))
        .filter(
            Booking.branch_id == branch_id,
            Booking.check_in == audit_date,
            Booking.status == "confirmed",  # لم يصل
        )
        .scalar() or 0
    )
    room_revenue = (
        db.query(func.coalesce(func.sum(BookingRoom.daily_rate), 0))
        .join(Booking)
        .filter(
            Booking.branch_id == branch_id,
            Booking.status == "checked_in",
            Booking.check_in <= audit_date,
            Booking.check_out > audit_date,
        )
        .scalar() or Decimal("0")
    )
    return {
        "occupied_rooms":  occupied,
        "checkouts_today": checkouts,
        "checkins_today":  checkins,
        "no_shows":        no_shows,
        "room_revenue":    Decimal(str(room_revenue)),
    }


# ── NightAuditLog ─────────────────────────────────────────────────────

def get_night_audit(db: Session, branch_id: int, audit_date: date) -> Optional[NightAuditLog]:
    return (
        db.query(NightAuditLog)
        .filter(NightAuditLog.branch_id == branch_id, NightAuditLog.audit_date == audit_date)
        .first()
    )


def create_night_audit(db: Session, branch_id: int, audit_date: date, data: dict) -> NightAuditLog:
    log = NightAuditLog(branch_id=branch_id, audit_date=audit_date, **data)
    db.add(log)
    db.flush()
    return log


def update_night_audit(db: Session, log: NightAuditLog, data: dict) -> NightAuditLog:
    for k, v in data.items():
        setattr(log, k, v)
    db.flush()
    return log


def list_night_audits(
    db: Session,
    branch_id: int,
    skip: int = 0,
    limit: int = 30,
) -> list[NightAuditLog]:
    return (
        db.query(NightAuditLog)
        .filter(NightAuditLog.branch_id == branch_id)
        .order_by(NightAuditLog.audit_date.desc())
        .offset(skip).limit(limit).all()
    )


# ── HousekeepingTask ──────────────────────────────────────────────────

def create_housekeeping_task(db: Session, data: dict) -> HousekeepingTask:
    task = HousekeepingTask(**data)
    db.add(task)
    db.flush()
    return task


def list_housekeeping_tasks(
    db: Session,
    branch_id: int,
    status: Optional[str] = None,
    room_id: Optional[int] = None,
) -> list[HousekeepingTask]:
    q = db.query(HousekeepingTask).filter(HousekeepingTask.branch_id == branch_id)
    if status:
        q = q.filter(HousekeepingTask.status == status)
    if room_id:
        q = q.filter(HousekeepingTask.room_id == room_id)
    return q.order_by(HousekeepingTask.created_at.desc()).all()


def update_housekeeping_task(db: Session, task: HousekeepingTask, data: dict) -> HousekeepingTask:
    for k, v in data.items():
        setattr(task, k, v)
    db.flush()
    return task


def get_housekeeping_task(db: Session, task_id: int) -> Optional[HousekeepingTask]:
    return db.query(HousekeepingTask).filter(HousekeepingTask.id == task_id).first()


# ── RatePlan ──────────────────────────────────────────────────────────

def create_rate_plan(db: Session, data: dict) -> RatePlan:
    plan = RatePlan(**data)
    db.add(plan)
    db.flush()
    return plan


def list_rate_plans(
    db: Session,
    branch_id: int,
    active_only: bool = True,
    room_type_id: Optional[int] = None,
) -> list[RatePlan]:
    q = db.query(RatePlan).filter(RatePlan.branch_id == branch_id)
    if active_only:
        q = q.filter(RatePlan.is_active.is_(True))
    if room_type_id:
        q = q.filter(RatePlan.room_type_id == room_type_id)
    return q.order_by(RatePlan.valid_from).all()


def get_rate_plan(db: Session, plan_id: int) -> Optional[RatePlan]:
    return db.query(RatePlan).filter(RatePlan.id == plan_id).first()
