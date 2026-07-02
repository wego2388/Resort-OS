"""app/modules/maintenance/crud.py — CRUD خالص، لا business logic"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.modules.maintenance.models import Asset, PreventiveSchedule, WorkOrder, WorkOrderPart
from app.modules.maintenance.schemas import (
    AssetCreate, AssetUpdate,
    WorkOrderCreate, WorkOrderUpdate, WorkOrderPartCreate,
    PreventiveScheduleCreate, PreventiveScheduleUpdate,
)


# ── Asset ─────────────────────────────────────────────────────────────

def get_asset(db: Session, asset_id: int) -> Optional[Asset]:
    return db.query(Asset).filter(Asset.id == asset_id).first()


def get_asset_by_code(db: Session, code: str) -> Optional[Asset]:
    return db.query(Asset).filter(Asset.code == code).first()


def list_assets(
    db: Session,
    branch_id: int,
    category: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Asset], int]:
    q = db.query(Asset).filter(Asset.branch_id == branch_id)
    if category:
        q = q.filter(Asset.category == category)
    if status:
        q = q.filter(Asset.status == status)
    total = q.count()
    items = q.order_by(Asset.name).offset(skip).limit(limit).all()
    return items, total


def create_asset(db: Session, data: AssetCreate) -> Asset:
    obj = Asset(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


def update_asset(db: Session, asset: Asset, data: AssetUpdate) -> Asset:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(asset, field, value)
    db.flush()
    return asset


# ── WorkOrder ─────────────────────────────────────────────────────────

_WO_COUNTER_KEY = "wo_counter"


def _next_order_number(db: Session) -> str:
    from datetime import datetime  # noqa: PLC0415
    today = datetime.utcnow().strftime("%Y%m%d")
    count = db.query(WorkOrder).filter(
        WorkOrder.order_number.like(f"WO-{today}-%")
    ).count()
    return f"WO-{today}-{count + 1:04d}"


def get_work_order(db: Session, order_id: int) -> Optional[WorkOrder]:
    return db.query(WorkOrder).filter(WorkOrder.id == order_id).first()


def list_work_orders(
    db: Session,
    branch_id: int,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    asset_id: Optional[int] = None,
    assigned_to: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[WorkOrder], int]:
    q = db.query(WorkOrder).filter(WorkOrder.branch_id == branch_id)
    if status:
        q = q.filter(WorkOrder.status == status)
    if priority:
        q = q.filter(WorkOrder.priority == priority)
    if asset_id:
        q = q.filter(WorkOrder.asset_id == asset_id)
    if assigned_to:
        q = q.filter(WorkOrder.assigned_to == assigned_to)
    total = q.count()
    items = q.order_by(WorkOrder.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def create_work_order(db: Session, data: WorkOrderCreate, reported_by: int) -> WorkOrder:
    obj = WorkOrder(
        **data.model_dump(),
        order_number=_next_order_number(db),
        reported_by=reported_by,
    )
    db.add(obj)
    db.flush()
    return obj


def update_work_order(db: Session, wo: WorkOrder, data: WorkOrderUpdate) -> WorkOrder:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(wo, field, value)
    db.flush()
    return wo


def complete_work_order(db: Session, wo: WorkOrder) -> WorkOrder:
    from datetime import datetime  # noqa: PLC0415
    wo.status = "completed"
    wo.completed_at = datetime.utcnow()
    db.flush()
    return wo


# ── WorkOrderPart ─────────────────────────────────────────────────────

def add_part(db: Session, work_order_id: int, data: WorkOrderPartCreate) -> WorkOrderPart:
    total = data.quantity * data.unit_cost
    part = WorkOrderPart(
        work_order_id=work_order_id,
        **data.model_dump(),
        total_cost=total,
    )
    db.add(part)
    db.flush()
    return part


def recalculate_parts_cost(db: Session, wo: WorkOrder) -> WorkOrder:
    wo.parts_cost = sum(
        (p.total_cost for p in wo.parts),
        Decimal("0"),
    )
    db.flush()
    return wo


# ── PreventiveSchedule ────────────────────────────────────────────────

def get_schedule(db: Session, schedule_id: int) -> Optional[PreventiveSchedule]:
    return db.query(PreventiveSchedule).filter(PreventiveSchedule.id == schedule_id).first()


def list_schedules(
    db: Session,
    branch_id: int,
    active_only: bool = True,
    due_before: Optional[date] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[PreventiveSchedule], int]:
    q = db.query(PreventiveSchedule).filter(PreventiveSchedule.branch_id == branch_id)
    if active_only:
        q = q.filter(PreventiveSchedule.is_active.is_(True))
    if due_before:
        q = q.filter(PreventiveSchedule.next_due <= due_before)
    total = q.count()
    items = q.order_by(PreventiveSchedule.next_due).offset(skip).limit(limit).all()
    return items, total


def create_schedule(db: Session, data: PreventiveScheduleCreate) -> PreventiveSchedule:
    obj = PreventiveSchedule(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


def update_schedule(
    db: Session,
    schedule: PreventiveSchedule,
    data: PreventiveScheduleUpdate,
) -> PreventiveSchedule:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(schedule, field, value)
    db.flush()
    return schedule


def mark_schedule_done(db: Session, schedule: PreventiveSchedule, done_date: date) -> PreventiveSchedule:
    from datetime import timedelta  # noqa: PLC0415
    schedule.last_done = done_date
    schedule.next_due = done_date + timedelta(days=schedule.frequency_days)
    db.flush()
    return schedule
