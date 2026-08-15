#!/usr/bin/env python3
"""Apply the approved no-VAT Beach policy and archive HIST dining outlets.

Dry-run is the default.  The apply path is guarded by exact expected counts
and performs one atomic transaction.  Historical, already-voided Beach sales
are deliberately preserved as originally posted; active sales are reconciled
across the transaction, direct payment, journal, customer total and stored
closed-shift totals.

The two HIST outlets are soft-archived instead of hard-deleted because their
orders are historical accounting/reporting rows.  Active outlet APIs and all
operational screens then expose only Restaurant and Cafe.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from app.modules.beach.models import BeachTransaction
from app.modules.core.models import AuditLog, Branch
from app.modules.credit.models import CreditTransaction
from app.modules.crm.models import Customer
from app.modules.dining.models import DiningOrder, DiningOrderItem, Outlet
from app.modules.finance.models import (
    Account,
    CashierShift,
    CashMovement,
    Folio,
    FolioCharge,
    JournalEntry,
    JournalLine,
    Payment,
)
from sqlalchemy import or_
from sqlalchemy.orm import Session

EXPECTED_BRANCH_NAME = "El Kheima Beach Resort"
HIST_OUTLET_NAMES = frozenset({"Restaurant HIST", "Cafe HIST"})
ACTIVE_ORDER_STATUSES = frozenset({"held", "open", "in_kitchen", "served"})
INACTIVE_ORDER_ITEM_STATUSES = frozenset({"cancelled", "refunded"})
CONFIRM_PHRASE = "DISABLE-BEACH-VAT-AND-ARCHIVE-HIST"


@dataclass(frozen=True)
class BeachVatRepairReport:
    branch_id: int
    transaction_count: int
    payment_count: int
    journal_count: int
    folio_charge_count: int
    customer_count: int
    shift_count: int
    outlet_count: int
    hist_active_order_count: int
    total_vat_removed: str
    applied: bool


def _movement_effect(row: CashMovement) -> Decimal:
    amount = row.amount or Decimal(0)
    if row.movement_type == "cash_in":
        return amount
    if row.movement_type in {"cash_out", "petty_cash", "safe_drop"}:
        return -amount
    if row.movement_type == "correction" and row.direction == "increase":
        return amount
    if row.movement_type == "correction" and row.direction == "decrease":
        return -amount
    return Decimal(0)


def _repair_journal(
    db: Session,
    *,
    tx: BeachTransaction,
    vat_account_id: int | None,
) -> int:
    source = "beach_folio_charge" if tx.folio_id else "beach"
    entries = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.branch_id == tx.branch_id,
            JournalEntry.source == source,
            JournalEntry.source_id == tx.id,
        )
        .order_by(JournalEntry.id)
        .with_for_update()
        .all()
    )
    if len(entries) > 1:
        raise ValueError(f"Beach transaction {tx.id} has duplicate original journals")
    if not entries:
        return 0

    entry = entries[0]
    lines = (
        db.query(JournalLine)
        .filter(JournalLine.entry_id == entry.id)
        .order_by(JournalLine.id)
        .with_for_update()
        .all()
    )
    old_vat = tx.vat_amount or Decimal(0)
    old_gross = (tx.total_amount + old_vat).quantize(Decimal("0.01"))
    debit_lines = [line for line in lines if line.debit > 0]
    if len(debit_lines) != 1 or debit_lines[0].debit != old_gross:
        raise ValueError(f"Beach journal {entry.id} debit does not match transaction {tx.id}")
    debit_lines[0].debit = tx.total_amount

    vat_lines = [
        line for line in lines
        if vat_account_id is not None and line.account_id == vat_account_id
    ]
    if old_vat > 0:
        if len(vat_lines) != 1 or vat_lines[0].credit != old_vat:
            raise ValueError(f"Beach journal {entry.id} VAT line does not match transaction {tx.id}")
        db.delete(vat_lines[0])

    remaining_credit = sum(
        (line.credit for line in lines if line not in vat_lines), Decimal(0)
    )
    if remaining_credit != tx.total_amount:
        raise ValueError(f"Beach journal {entry.id} revenue does not match transaction {tx.id}")
    return 1


def _recalculate_folio(db: Session, folio_id: int) -> None:
    folio = db.query(Folio).filter(Folio.id == folio_id).with_for_update().one()
    charges = db.query(FolioCharge).filter(FolioCharge.folio_id == folio_id).all()
    payments = db.query(Payment).filter(
        Payment.folio_id == folio_id,
        Payment.voided_at.is_(None),
    ).all()
    charge_total = sum(
        (
            row.amount
            + (row.vat_amount or Decimal(0))
            + (row.service_charge or Decimal(0))
            for row in charges
        ),
        Decimal(0),
    )
    payment_total = sum((row.amount for row in payments), Decimal(0))
    folio.total = (charge_total - payment_total).quantize(Decimal("0.01"))


def apply_beach_no_vat_policy(
    db: Session,
    *,
    expected_transaction_count: int,
    expected_payment_count: int,
    expected_outlet_count: int,
    expected_hist_active_order_count: int,
    apply: bool,
    reason: str | None,
) -> BeachVatRepairReport:
    """Build or atomically apply the single-branch Beach reconciliation."""
    if min(
        expected_transaction_count,
        expected_payment_count,
        expected_outlet_count,
        expected_hist_active_order_count,
    ) < 0:
        raise ValueError("Expected counts cannot be negative")
    if apply and (reason is None or len(reason.strip()) < 10):
        raise ValueError("A meaningful --reason of at least 10 characters is required")

    branches = (
        db.query(Branch)
        .filter(Branch.is_active.is_(True))
        .order_by(Branch.id)
        .with_for_update()
        .all()
    )
    if len(branches) != 1 or branches[0].name.strip() != EXPECTED_BRANCH_NAME:
        raise ValueError("Expected the single active El Kheima Beach Resort branch")
    branch = branches[0]

    transactions = (
        db.query(BeachTransaction)
        .filter(
            BeachTransaction.branch_id == branch.id,
            BeachTransaction.voided_at.is_(None),
            BeachTransaction.vat_amount > 0,
        )
        .order_by(BeachTransaction.id)
        .with_for_update()
        .all()
    )
    if len(transactions) != expected_transaction_count:
        raise ValueError(
            "Transaction-count guard failed: "
            f"expected {expected_transaction_count}, found {len(transactions)}"
        )

    tx_ids = [row.id for row in transactions]
    references = [f"BCH-{row.id:06d}" for row in transactions]
    payments = []
    folio_charges = []
    credit_count = 0
    if tx_ids:
        payments = (
            db.query(Payment)
            .filter(
                Payment.branch_id == branch.id,
                or_(Payment.source == "beach", Payment.source.is_(None)),
                Payment.reference.in_(references),
            )
            .order_by(Payment.id)
            .with_for_update()
            .all()
        )
        folio_charges = (
            db.query(FolioCharge)
            .filter(FolioCharge.ref_beach_tx_id.in_(tx_ids))
            .order_by(FolioCharge.id)
            .with_for_update()
            .all()
        )
        credit_count = (
            db.query(CreditTransaction)
            .filter(CreditTransaction.ref_beach_tx_id.in_(tx_ids))
            .count()
        )
    if len(payments) != expected_payment_count:
        raise ValueError(
            "Payment-count guard failed: "
            f"expected {expected_payment_count}, found {len(payments)}"
        )
    if credit_count:
        raise ValueError(
            "Active Beach credit-account transactions require a separate ledger reconciliation"
        )

    outlets = (
        db.query(Outlet)
        .filter(
            Outlet.branch_id == branch.id,
            Outlet.name.in_(HIST_OUTLET_NAMES),
            Outlet.is_active.is_(True),
        )
        .order_by(Outlet.id)
        .with_for_update()
        .all()
    )
    if len(outlets) != expected_outlet_count:
        raise ValueError(
            "Outlet-count guard failed: "
            f"expected {expected_outlet_count}, found {len(outlets)}"
        )
    hist_active_orders = []
    if outlets:
        hist_active_orders = (
            db.query(DiningOrder)
            .filter(
                DiningOrder.outlet_id.in_([row.id for row in outlets]),
                DiningOrder.status.in_(ACTIVE_ORDER_STATUSES),
            )
            .order_by(DiningOrder.id)
            .with_for_update()
            .all()
        )
    if len(hist_active_orders) != expected_hist_active_order_count:
        raise ValueError(
            "HIST-active-order-count guard failed: "
            f"expected {expected_hist_active_order_count}, found {len(hist_active_orders)}"
        )
    for order in hist_active_orders:
        active_item_count = (
            db.query(DiningOrderItem)
            .filter(
                DiningOrderItem.order_id == order.id,
                DiningOrderItem.status.notin_(INACTIVE_ORDER_ITEM_STATUSES),
            )
            .count()
        )
        if order.total != 0 or active_item_count:
            raise ValueError(
                f"HIST order {order.id} still has value or active items and cannot be auto-cancelled"
            )

    tx_by_reference = {f"BCH-{row.id:06d}": row for row in transactions}
    for payment in payments:
        tx = tx_by_reference.get(payment.reference or "")
        if tx is None:
            raise ValueError(f"Unexpected Beach payment {payment.id}")
        expected_old = (tx.total_amount + tx.vat_amount).quantize(Decimal("0.01"))
        if payment.amount != expected_old:
            raise ValueError(f"Beach payment {payment.id} does not match transaction {tx.id}")

    charges_by_tx = {row.ref_beach_tx_id: row for row in folio_charges}
    if len(charges_by_tx) != len(folio_charges):
        raise ValueError("A Beach transaction has duplicate folio charges")
    for charge in folio_charges:
        tx = next(row for row in transactions if row.id == charge.ref_beach_tx_id)
        if charge.amount != tx.total_amount or charge.vat_amount != tx.vat_amount:
            raise ValueError(f"Beach folio charge {charge.id} does not match transaction {tx.id}")

    vat_account = (
        db.query(Account)
        .filter(Account.branch_id == branch.id, Account.code == "2160")
        .one_or_none()
    )
    journal_count = sum(
        _repair_journal(db, tx=tx, vat_account_id=vat_account.id if vat_account else None)
        for tx in transactions
    )

    total_vat = sum((row.vat_amount for row in transactions), Decimal(0))
    customer_vat: dict[int, Decimal] = {}
    for tx in transactions:
        if tx.customer_id:
            customer_vat[tx.customer_id] = customer_vat.get(tx.customer_id, Decimal(0)) + tx.vat_amount
    customers = []
    if customer_vat:
        customers = (
            db.query(Customer)
            .filter(Customer.id.in_(customer_vat))
            .order_by(Customer.id)
            .with_for_update()
            .all()
        )
        if {row.id for row in customers} != set(customer_vat):
            raise ValueError("A Beach transaction references a missing customer")

    shift_ids = sorted({row.shift_id for row in payments if row.shift_id is not None})
    shifts = []
    if shift_ids:
        shifts = (
            db.query(CashierShift)
            .filter(CashierShift.id.in_(shift_ids))
            .order_by(CashierShift.id)
            .with_for_update()
            .all()
        )

    report = BeachVatRepairReport(
        branch_id=branch.id,
        transaction_count=len(transactions),
        payment_count=len(payments),
        journal_count=journal_count,
        folio_charge_count=len(folio_charges),
        customer_count=len(customers),
        shift_count=len(shifts),
        outlet_count=len(outlets),
        hist_active_order_count=len(hist_active_orders),
        total_vat_removed=f"{total_vat.quantize(Decimal('0.01')):.2f}",
        applied=apply,
    )

    if not apply:
        db.rollback()
        return report

    for payment in payments:
        payment.amount = tx_by_reference[payment.reference].total_amount
        payment.source = "beach"
    for charge in folio_charges:
        charge.vat_amount = Decimal("0.00")
    for customer in customers:
        corrected = (customer.total_spent or Decimal(0)) - customer_vat[customer.id]
        if corrected < 0:
            raise ValueError(f"Customer {customer.id} total_spent would become negative")
        customer.total_spent = corrected.quantize(Decimal("0.01"))
    for tx in transactions:
        tx.vat_amount = Decimal("0.00")
    for outlet in outlets:
        outlet.is_active = False
    for order in hist_active_orders:
        order.status = "cancelled"

    for folio_id in sorted({row.folio_id for row in folio_charges}):
        _recalculate_folio(db, folio_id)

    db.flush()
    for shift in shifts:
        active_cash = (
            db.query(Payment)
            .filter(
                Payment.shift_id == shift.id,
                Payment.method == "cash",
                Payment.voided_at.is_(None),
            )
            .all()
        )
        movements = db.query(CashMovement).filter(CashMovement.shift_id == shift.id).all()
        expected = (
            shift.opening_float
            + sum((row.amount for row in active_cash), Decimal(0))
            + sum((_movement_effect(row) for row in movements), Decimal(0))
        ).quantize(Decimal("0.01"))
        if shift.status == "closed":
            shift.expected_cash = expected
            shift.variance = (
                (shift.counted_cash - expected).quantize(Decimal("0.01"))
                if shift.counted_cash is not None else None
            )

    db.add(AuditLog(
        user_id=None,
        branch_id=branch.id,
        action="beach_vat_disabled_hist_outlets_archived",
        entity_type="branch",
        entity_id=branch.id,
        old_data=json.dumps({
            "beach_vat_policy": "configured_percentage",
            "active_hist_outlets": len(outlets),
        }, sort_keys=True),
        new_data=json.dumps({
            "beach_vat_policy": "zero",
            "active_hist_outlets": 0,
            "transaction_count": len(transactions),
            "payment_count": len(payments),
            "journal_count": journal_count,
            "hist_active_order_count": len(hist_active_orders),
            "reason": reason.strip(),
        }, sort_keys=True),
        ip_address=None,
        user_agent="backend/scripts/disable_beach_vat.py",
    ))
    db.commit()
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-transaction-count", type=int, required=True)
    parser.add_argument("--expected-payment-count", type=int, required=True)
    parser.add_argument("--expected-outlet-count", type=int, required=True)
    parser.add_argument("--expected-hist-active-order-count", type=int, required=True)
    parser.add_argument("--reason")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.apply and args.confirm != CONFIRM_PHRASE:
        raise SystemExit(f"--apply requires --confirm {CONFIRM_PHRASE}")
    with SessionLocal() as db:
        report = apply_beach_no_vat_policy(
            db,
            expected_transaction_count=args.expected_transaction_count,
            expected_payment_count=args.expected_payment_count,
            expected_outlet_count=args.expected_outlet_count,
            expected_hist_active_order_count=args.expected_hist_active_order_count,
            apply=args.apply,
            reason=args.reason,
        )
    print(json.dumps(asdict(report), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
