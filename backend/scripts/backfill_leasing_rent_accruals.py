"""Dry-run-first backfill for due leasing rent accrual journals.

The daily Celery task only processes rows after the task is deployed. This
command reconciles older ``lease_payments`` that are already due but still
have ``accrued = false``. The default invocation is read-only::

    .venv/bin/python -m scripts.backfill_leasing_rent_accruals

Applying requires a real user id and must only happen after a verified fresh
production backup and review of the dry-run output::

    .venv/bin/python -m scripts.backfill_leasing_rent_accruals \
        --apply --actor-id <SUPER_ADMIN_USER_ID>

The write path uses a PostgreSQL advisory transaction lock plus row locks,
strict journal posting, one outer transaction, and stable journal references.
It is safe to rerun: already accrued rows are excluded and an existing journal
for an interrupted historical run is reused by the finance idempotency guard.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.finance.models import JournalEntry
from app.seed import _import_all_models
from app.modules.leasing import services
from app.modules.leasing.models import LeaseContract, LeasePayment
from app.core.kernel.models.user import User
from app.resort_os.timezone_utils import local_today

_import_all_models()


@dataclass(frozen=True)
class BackfillItem:
    payment_id: int
    contract_id: int
    contract_number: str
    branch_id: int
    due_date: date
    amount: Decimal
    existing_journal_id: int | None


def _reference(payment_id: int) -> str:
    return f"LSE-ACR-{payment_id:06d}"


def list_backfill_items(db: Session, *, as_of: date) -> list[BackfillItem]:
    rows = (
        db.query(LeasePayment, LeaseContract)
        .join(LeaseContract, LeaseContract.id == LeasePayment.contract_id)
        .filter(
            LeasePayment.due_date <= as_of,
            LeasePayment.accrued.is_(False),
        )
        .order_by(LeaseContract.branch_id, LeasePayment.due_date, LeasePayment.id)
        .all()
    )
    items: list[BackfillItem] = []
    for payment, contract in rows:
        existing = (
            db.query(JournalEntry.id)
            .filter(
                JournalEntry.branch_id == contract.branch_id,
                JournalEntry.source == "leasing",
                JournalEntry.source_id == payment.id,
                JournalEntry.reference == _reference(payment.id),
            )
            .scalar()
        )
        items.append(BackfillItem(
            payment_id=payment.id,
            contract_id=contract.id,
            contract_number=contract.contract_number,
            branch_id=contract.branch_id,
            due_date=payment.due_date,
            amount=Decimal(payment.amount),
            existing_journal_id=existing,
        ))
    return items


def find_broken_accruals(db: Session, *, as_of: date) -> list[int]:
    """Return accrued due rows whose linked journal is absent."""
    return [
        row[0]
        for row in (
            db.query(LeasePayment.id)
            .outerjoin(
                JournalEntry,
                JournalEntry.id == LeasePayment.accrual_journal_entry_id,
            )
            .filter(
                LeasePayment.due_date <= as_of,
                LeasePayment.accrued.is_(True),
                JournalEntry.id.is_(None),
            )
            .order_by(LeasePayment.id)
            .all()
        )
    ]


def apply_backfill(db: Session, *, as_of: date, actor_id: int) -> list[int]:
    if actor_id <= 0 or db.query(User.id).filter(User.id == actor_id).scalar() is None:
        raise ValueError("actor_id must identify an existing production user")

    if db.get_bind().dialect.name == "postgresql":
        db.execute(text(
            "SELECT pg_advisory_xact_lock("
            "hashtext('leasing_rent_accrual_backfill'))"
        ))

    broken = find_broken_accruals(db, as_of=as_of)
    if broken:
        raise RuntimeError(
            "accrued lease payments have no linked journal; manual review required: "
            + ",".join(str(payment_id) for payment_id in broken[:50])
        )

    branch_ids = [
        row[0]
        for row in (
            db.query(LeaseContract.branch_id)
            .join(LeasePayment, LeasePayment.contract_id == LeaseContract.id)
            .filter(
                LeasePayment.due_date <= as_of,
                LeasePayment.accrued.is_(False),
            )
            .distinct()
            .order_by(LeaseContract.branch_id)
            .all()
        )
    ]

    accrued_ids: list[int] = []
    try:
        for branch_id in branch_ids:
            rows = services.accrue_due_rents(
                db,
                branch_id,
                as_of,
                created_by=actor_id,
                raise_on_error=True,
                commit=False,
            )
            accrued_ids.extend(row.id for row in rows)
        db.commit()
        return accrued_ids
    except Exception:
        db.rollback()
        raise


def _print_report(db: Session, *, as_of: date) -> None:
    items = list_backfill_items(db, as_of=as_of)
    broken = find_broken_accruals(db, as_of=as_of)
    print("=== Leasing rent accrual backfill ===")
    print(f"as_of={as_of.isoformat()}")
    for item in items:
        state = "STATE-REPAIR" if item.existing_journal_id else "PROPOSED"
        print(
            f"[{state}] payment_id={item.payment_id} contract_id={item.contract_id} "
            f"contract={item.contract_number} branch_id={item.branch_id} "
            f"due_date={item.due_date.isoformat()} amount={item.amount:.2f} "
            f"existing_journal_id={item.existing_journal_id or '-'}"
        )
    total = sum((item.amount for item in items), Decimal("0"))
    print(f"proposed_count={len(items)} proposed_total={total:.2f}")
    print(f"broken_accrual_count={len(broken)}")
    if broken:
        print("broken_payment_ids=" + ",".join(str(value) for value in broken[:50]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--actor-id", type=int)
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=local_today(settings.TIMEZONE),
        help="Cairo business date, YYYY-MM-DD (default: today)",
    )
    args = parser.parse_args()
    if args.apply and not args.actor_id:
        parser.error("--actor-id is required with --apply")

    db = SessionLocal()
    try:
        _print_report(db, as_of=args.as_of)
        if not args.apply:
            print("DRY-RUN ONLY — no rows changed")
            return
        accrued_ids = apply_backfill(db, as_of=args.as_of, actor_id=args.actor_id)
        print(f"APPLIED count={len(accrued_ids)} ids={','.join(map(str, accrued_ids))}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
