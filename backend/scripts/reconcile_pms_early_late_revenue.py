"""Dry-run-first reconciliation for historical PMS early/late fees.

The application posts every room_extra folio charge as room revenue
(Dr 1150 / Cr 4100) at charge time. Historical checked-out bookings may
have the folio charge and checkout settlement but no matching revenue journal.

Default mode is read-only and prints only booking numbers, row ids and money;
no guest PII. Applying requires both an explicit flag and the real actor id:

    .venv/bin/python -m scripts.reconcile_pms_early_late_revenue
    .venv/bin/python -m scripts.reconcile_pms_early_late_revenue \
        --apply --actor-id <SUPER_ADMIN_USER_ID>

Never run --apply on production before a fresh backup and review of the
dry-run output. Re-running is safe: the stable source is the immutable
FolioCharge.id, and the finance posting primitive returns an existing entry
for the same (branch, source, source_id, reference).
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.finance.models import FolioCharge, JournalEntry
from app.modules.finance.services import post_simple_revenue_journal
from app.core.kernel.models.user import User
from app.modules.pms.models import Booking
from app.resort_os.timezone_utils import utc_naive_to_local_date


SOURCE = "pms_early_late"


@dataclass(frozen=True)
class ReconciliationItem:
    booking_id: int
    booking_number: str
    branch_id: int
    charge_id: int
    amount: Decimal
    reference: str
    already_posted: bool


def _reference(booking: Booking, charge: FolioCharge) -> str:
    return f"PMS-EL-{booking.booking_number}-{charge.id}"


def list_reconciliation_items(db: Session) -> list[ReconciliationItem]:
    """Return every checked-out room-extra charge and its posting state."""
    rows = (
        db.query(Booking, FolioCharge)
        .join(FolioCharge, FolioCharge.folio_id == Booking.folio_id)
        .filter(
            Booking.status == "checked_out",
            FolioCharge.charge_type == "room_extra",
            FolioCharge.amount > 0,
        )
        .order_by(Booking.id, FolioCharge.id)
        .all()
    )

    items: list[ReconciliationItem] = []
    for booking, charge in rows:
        reference = _reference(booking, charge)
        already_posted = (
            db.query(JournalEntry.id)
            .filter(
                JournalEntry.branch_id == booking.branch_id,
                JournalEntry.source == SOURCE,
                JournalEntry.source_id == charge.id,
                JournalEntry.reference == reference,
            )
            .first()
            is not None
        )
        items.append(ReconciliationItem(
            booking_id=booking.id,
            booking_number=booking.booking_number,
            branch_id=booking.branch_id,
            charge_id=charge.id,
            amount=Decimal(charge.amount),
            reference=reference,
            already_posted=already_posted,
        ))
    return items


def apply_reconciliation(db: Session, *, actor_id: int) -> list[JournalEntry]:
    """Post all missing entries atomically and return the created rows."""
    if actor_id <= 0 or db.query(User.id).filter(User.id == actor_id).scalar() is None:
        raise ValueError("actor_id يجب أن يحدد مستخدمًا حقيقيًا موجودًا")

    # يمنع عمليتي backfill متزامنتين من اجتياز فحص existing قبل أن تكتب أي
    # منهما. SQLite في الاختبارات لا يدعم advisory locks؛ المعاملة المتسلسلة
    # هناك كافية، بينما الإنتاج PostgreSQL يأخذ القفل حتى نهاية transaction.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text(
            "SELECT pg_advisory_xact_lock("
            "hashtext('pms_early_late_reconciliation'))"
        ))

    items = [item for item in list_reconciliation_items(db) if not item.already_posted]
    entries: list[JournalEntry] = []
    try:
        for item in items:
            charge = db.query(FolioCharge).filter(FolioCharge.id == item.charge_id).one()
            entry = post_simple_revenue_journal(
                db,
                item.branch_id,
                utc_naive_to_local_date(charge.posted_at, settings.TIMEZONE),
                debit_account_code="1150",
                credit_account_code="4100",
                amount=item.amount,
                reference=item.reference,
                description=f"تسوية إيراد رسوم وصول/مغادرة — {item.booking_number}",
                source=SOURCE,
                source_id=item.charge_id,
                created_by=actor_id,
                cost_center_code="ROOM",
                strict=True,
                commit_cost_centers=False,
            )
            if entry is None:  # strict=True contract; defensive guard
                raise RuntimeError(f"لم يُنشأ قيد للشحنة {item.charge_id}")
            entries.append(entry)
        db.commit()
        return entries
    except Exception:
        db.rollback()
        raise


def _print_report(items: list[ReconciliationItem]) -> None:
    missing = [item for item in items if not item.already_posted]
    already = [item for item in items if item.already_posted]
    print("=== PMS early/late revenue reconciliation ===")
    for item in items:
        state = "already-posted" if item.already_posted else "PROPOSED"
        print(
            f"[{state}] booking={item.booking_number} booking_id={item.booking_id} "
            f"charge_id={item.charge_id} branch_id={item.branch_id} "
            f"amount={item.amount:.2f} reference={item.reference}"
        )
    proposed_total = sum((item.amount for item in missing), Decimal("0"))
    print(f"proposed_count={len(missing)} proposed_total={proposed_total:.2f}")
    print(f"already_posted_count={len(already)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="نفّذ القيود المقترحة (الافتراضي dry-run)",
    )
    parser.add_argument(
        "--actor-id",
        type=int,
        help="User.id الحقيقي لمن اعتمد التنفيذ",
    )
    args = parser.parse_args()
    if args.apply and not args.actor_id:
        parser.error("--actor-id مطلوب مع --apply")

    db = SessionLocal()
    try:
        items = list_reconciliation_items(db)
        _print_report(items)
        if not args.apply:
            print("DRY-RUN ONLY — no rows changed")
            return
        entries = apply_reconciliation(db, actor_id=args.actor_id)
        print(f"APPLIED entries={len(entries)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
