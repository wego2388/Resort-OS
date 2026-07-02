"""app/modules/beach/crud.py — CRUD خالص"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.modules.beach.models import (
    B2BContract, B2BContractDay,
    BeachInventory, BeachReservation, BeachTransaction,
)
from app.modules.beach.schemas import (
    B2BContractCreate, BeachReservationCreate,
)


# ── BeachInventory ────────────────────────────────────────────────────

def get_or_create_inventory(
    db: Session,
    branch_id: int,
    inv_date: date,
    capacity_max: int = 200,
    towels_total: int = 200,
) -> BeachInventory:
    row = (
        db.query(BeachInventory)
        .filter(BeachInventory.branch_id == branch_id, BeachInventory.inventory_date == inv_date)
        .first()
    )
    if not row:
        row = BeachInventory(
            branch_id=branch_id,
            inventory_date=inv_date,
            capacity_max=capacity_max,
            towels_total=towels_total,
            towels_available=towels_total,
        )
        db.add(row)
        db.flush()
    return row


def set_surge_manual(
    db: Session,
    branch_id: int,
    inv_date: date,
    surge_pct: Decimal,
) -> BeachInventory:
    """يضبط surge_pct يدوياً (0 = إيقاف)."""
    row = get_or_create_inventory(db, branch_id, inv_date)
    row.surge_pct = surge_pct
    db.flush()
    return row


def apply_inventory_delta(
    db: Session,
    inventory: BeachInventory,
    capacity_delta: int,
    towel_delta: int,
) -> BeachInventory:
    # سالب delta = إضافة (شخص يدخل) — مطابق لنمط الفوط
    inventory.capacity_used    = max(0, inventory.capacity_used    - capacity_delta)
    inventory.towels_used      = max(0, inventory.towels_used      - towel_delta)
    inventory.towels_available = max(0, inventory.towels_available + towel_delta)

    # surge تلقائي عند capacity > 80%
    if inventory.capacity_max > 0:
        pct = inventory.capacity_used / inventory.capacity_max * 100
        inventory.surge_pct = Decimal("50.0") if pct >= 80 else Decimal("0.0")

    db.flush()
    return inventory


# ── BeachTransaction ──────────────────────────────────────────────────

def create_transaction(db: Session, data: dict) -> BeachTransaction:
    tx = BeachTransaction(**data)
    db.add(tx)
    db.flush()
    return tx


def get_transaction(db: Session, tx_id: int) -> Optional[BeachTransaction]:
    return db.query(BeachTransaction).filter(BeachTransaction.id == tx_id).first()


def void_transaction(db: Session, tx: BeachTransaction, voided_by: int, reason: str) -> BeachTransaction:
    tx.voided_at = datetime.utcnow()
    tx.voided_by = voided_by
    tx.voided_reason = reason
    db.flush()
    return tx


def list_transactions(
    db: Session,
    branch_id: int,
    tx_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 100,
) -> tuple[list[BeachTransaction], int]:
    q = db.query(BeachTransaction).filter(
        BeachTransaction.branch_id == branch_id,
        BeachTransaction.voided_at.is_(None),
    )
    if tx_date:
        q = q.filter(BeachTransaction.tx_date == tx_date)
    total = q.count()
    items = q.order_by(BeachTransaction.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def get_daily_summary(db: Session, branch_id: int, tx_date: date) -> dict:
    rows = (
        db.query(BeachTransaction)
        .filter(
            BeachTransaction.branch_id == branch_id,
            BeachTransaction.tx_date == tx_date,
            BeachTransaction.voided_at.is_(None),
        )
        .all()
    )
    entries       = sum(r.quantity for r in rows if r.tx_type in ("entry", "entry_towel"))
    b2b_entries   = sum(r.quantity for r in rows if r.b2b_contract_id and r.tx_type in ("entry", "entry_towel"))
    total_revenue = sum(r.total_amount for r in rows if r.tx_type != "towel_return")
    b2b_revenue   = sum(r.total_amount for r in rows if r.b2b_contract_id)
    towels_rented = sum(r.quantity for r in rows if r.tx_type in ("entry_towel", "towel_rent"))
    surge_active  = any(r.surge_applied for r in rows)
    return {
        "date":          tx_date,
        "total_entries": entries,
        "total_revenue": total_revenue,
        "b2b_entries":   b2b_entries,
        "b2b_revenue":   b2b_revenue,
        "towels_rented": towels_rented,
        "surge_active":  surge_active,
    }


def get_eod_breakdown(db: Session, branch_id: int, tx_date: date) -> dict:
    """تفصيل يوم كامل حسب نوع العملية — للتقرير اليومي (End of Day)."""
    rows = (
        db.query(BeachTransaction)
        .filter(
            BeachTransaction.branch_id == branch_id,
            BeachTransaction.tx_date == tx_date,
            BeachTransaction.voided_at.is_(None),
        )
        .all()
    )
    voided_count = (
        db.query(BeachTransaction)
        .filter(
            BeachTransaction.branch_id == branch_id,
            BeachTransaction.tx_date == tx_date,
            BeachTransaction.voided_at.isnot(None),
        )
        .count()
    )

    by_type: dict[str, dict] = {}
    for r in rows:
        d = by_type.setdefault(r.tx_type, {"quantity": 0, "total_amount": Decimal("0"), "count": 0})
        d["quantity"] += r.quantity
        d["total_amount"] += r.total_amount
        d["count"] += 1

    b2b_rows = [r for r in rows if r.b2b_contract_id]
    entry_types = ("entry", "entry_child", "entry_resident", "entry_towel")

    return {
        "by_type":       by_type,
        "total_entries": sum(r.quantity for r in rows if r.tx_type in entry_types),
        "total_revenue": sum((r.total_amount for r in rows if r.tx_type != "towel_return"), Decimal("0")),
        "b2b_entries":   sum(r.quantity for r in b2b_rows if r.tx_type in entry_types),
        "b2b_revenue":   sum((r.total_amount for r in b2b_rows), Decimal("0")),
        "voided_count":  voided_count,
    }


# ── B2BContract ───────────────────────────────────────────────────────

def get_b2b_contract(db: Session, contract_id: int) -> Optional[B2BContract]:
    return db.query(B2BContract).filter(B2BContract.id == contract_id).first()


def list_b2b_contracts(
    db: Session, branch_id: int, active_only: bool = True
) -> list[B2BContract]:
    q = db.query(B2BContract).filter(B2BContract.branch_id == branch_id)
    if active_only:
        q = q.filter(B2BContract.is_active.is_(True))
    return q.order_by(B2BContract.hotel_name).all()


def create_b2b_contract(db: Session, data: B2BContractCreate) -> B2BContract:
    obj = B2BContract(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


def list_b2b_contracts_with_today_usage(
    db: Session, branch_id: int, day: date,
) -> list[tuple[B2BContract, int]]:
    """كل عقود B2B النشطة مع عدد اللي دخلوا اليوم — بدون إنشاء أي صف
    (read-only، عكس get_or_create_contract_day)."""
    contracts = list_b2b_contracts(db, branch_id, active_only=True)
    rows: list[tuple[B2BContract, int]] = []
    for c in contracts:
        day_row = (
            db.query(B2BContractDay)
            .filter(B2BContractDay.contract_id == c.id, B2BContractDay.day == day)
            .first()
        )
        rows.append((c, day_row.checked_in_count if day_row else 0))
    return rows


def get_or_create_contract_day(
    db: Session, contract_id: int, day: date
) -> B2BContractDay:
    row = (
        db.query(B2BContractDay)
        .filter(B2BContractDay.contract_id == contract_id, B2BContractDay.day == day)
        .first()
    )
    if not row:
        row = B2BContractDay(contract_id=contract_id, day=day)
        db.add(row)
        db.flush()
    return row


def increment_b2b_checkins(
    db: Session, contract_id: int, day: date, count: int, amount: Decimal
) -> B2BContractDay:
    row = get_or_create_contract_day(db, contract_id, day)
    row.checked_in_count += count
    row.total_amount += amount
    db.flush()
    return row


# ── BeachReservation ──────────────────────────────────────────────────

def get_reservation(db: Session, reservation_id: int) -> Optional[BeachReservation]:
    return db.query(BeachReservation).filter(BeachReservation.id == reservation_id).first()


def create_reservation(db: Session, data: BeachReservationCreate) -> BeachReservation:
    obj = BeachReservation(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


def list_reservations(
    db: Session,
    branch_id: int,
    res_date: Optional[date] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[BeachReservation], int]:
    q = db.query(BeachReservation).filter(BeachReservation.branch_id == branch_id)
    if res_date:
        q = q.filter(BeachReservation.reservation_date == res_date)
    if status:
        q = q.filter(BeachReservation.status == status)
    total = q.count()
    items = q.order_by(BeachReservation.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def update_reservation_status(
    db: Session, res: BeachReservation, status: str, tx_id: Optional[int] = None
) -> BeachReservation:
    res.status = status
    if tx_id:
        res.tx_id = tx_id
    db.flush()
    return res
