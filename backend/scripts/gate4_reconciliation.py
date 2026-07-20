"""scripts/gate4_reconciliation.py — Gate 4 read-only reconciliation report.

Lists, without mutating anything, the exact data conditions the Gate 4
execution brief (§4) requires surfaced before/after the settlement/shift/order
integrity work:

  1. paid dining orders with no provable settlement/Payment (historical direct
     sales that predate the Payment-writing code — must NOT be backfilled with
     invented cashier/shift data; they belong in this report);
  2. duplicate ACTIVE orders per table (held|open|in_kitchen|served);
  3. duplicate OPEN shifts per (branch_id, cashier_id);
  4. dining orders with an unknown/unmapped payment_method;
  5. legacy `correction` cash movements with no explicit direction.

Read-only: opens a session, runs SELECTs, prints counts + a bounded sample of
ids. No personal data is printed (only ids / numbers / methods). Run:

    .venv/bin/python -m scripts.gate4_reconciliation
"""
from __future__ import annotations

from sqlalchemy import text

from app.core.database import SessionLocal

_ACTIVE = "('held','open','in_kitchen','served')"
_KNOWN_METHODS = ("cash", "card", "wallet", "room")


def _rows(db, sql: str):
    return db.execute(text(sql)).fetchall()


def main() -> None:
    db = SessionLocal()
    try:
        print("=== Gate 4 reconciliation (read-only) ===\n")

        # 1) paid dining orders with no provable Payment (direct, non-folio)
        orphan = _rows(db, """
            SELECT o.id, o.order_number
            FROM dining_orders o
            WHERE o.status = 'paid' AND o.folio_id IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM payments p
                WHERE p.ref_order_id = o.id AND p.folio_id IS NULL
                  AND p.voided_at IS NULL AND p.amount > 0
              )
            ORDER BY o.id
        """)
        print(f"[1] paid direct dining orders WITHOUT a Payment row: {len(orphan)}")
        for oid, onum in orphan[:20]:
            print(f"      order #{oid}  {onum}")
        if len(orphan) > 20:
            print(f"      … (+{len(orphan) - 20} more)")

        # 2) duplicate active orders per table
        dup_orders = _rows(db, f"""
            SELECT table_id, count(*) AS n
            FROM dining_orders
            WHERE table_id IS NOT NULL AND status IN {_ACTIVE}
            GROUP BY table_id HAVING count(*) > 1
        """)
        print(f"\n[2] tables with >1 active order: {len(dup_orders)}")
        for tid, n in dup_orders[:20]:
            print(f"      table #{tid}: {n} active orders")

        # 3) duplicate open shifts
        dup_shifts = _rows(db, """
            SELECT branch_id, cashier_id, count(*) AS n
            FROM cashier_shifts WHERE status = 'open'
            GROUP BY branch_id, cashier_id HAVING count(*) > 1
        """)
        print(f"\n[3] (branch,cashier) with >1 OPEN shift: {len(dup_shifts)}")
        for bid, cid, n in dup_shifts[:20]:
            print(f"      branch #{bid} cashier #{cid}: {n} open shifts")

        # 4) unknown payment methods on dining orders
        methods = _rows(db, """
            SELECT payment_method, count(*) FROM dining_orders
            WHERE payment_method IS NOT NULL GROUP BY payment_method
        """)
        unknown = [
            (m, n) for m, n in methods
            if m not in _KNOWN_METHODS and not str(m).startswith("split:")
        ]
        print(f"\n[4] dining orders with unknown payment_method: {len(unknown)} distinct value(s)")
        for m, n in unknown:
            print(f"      {m!r}: {n} orders")

        # 5) legacy corrections with no explicit direction
        legacy_corr = _rows(db, """
            SELECT id, shift_id FROM cash_movements
            WHERE movement_type = 'correction'
              AND (direction IS NULL OR direction NOT IN ('increase','decrease'))
            ORDER BY id
        """)
        print(f"\n[5] legacy correction cash movements WITHOUT a direction: {len(legacy_corr)}")
        for mid, sid in legacy_corr[:20]:
            print(f"      movement #{mid} (shift #{sid})")

        print("\n=== end reconciliation ===")
    finally:
        db.close()


if __name__ == "__main__":
    main()
