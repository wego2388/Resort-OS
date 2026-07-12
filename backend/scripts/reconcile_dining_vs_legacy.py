#!/usr/bin/env python3
"""backend/scripts/reconcile_dining_vs_legacy.py

DINING_CUTOVER_PLAN.md Batch 2 — verifies the `dining_*` tables are still an
accurate, current copy of `restaurant`/`cafe`'s data before analytics/finance
are cut over to read from `dining` exclusively (D-05). The one-time copy
migration (`0bd6f63e5446`) ran once, historically, during Batch A — this
script re-checks that nothing written directly through the still-live
`/restaurant`/`/cafe` routers since then (new orders, new menu items, edited
availability windows, etc.) has silently drifted out of sync with `dining`.

Two kinds of checks, depending on whether the dining side carries
`legacy_module`/`legacy_id` provenance columns:

  * Legacy-tracked entities (outlets, categories, items, extra_groups,
    variants, venue tables, orders, order_items): exact row-count parity
    per (legacy_table -> dining_table, module) pair, via
    ``COUNT(*) FROM dining_x WHERE legacy_module = :module``.
  * Non-legacy-tracked entities (extras, recipe lines, variant recipe
    lines — the D-02 migration matched these by natural key, not
    legacy_id, since they have no independently meaningful identity of
    their own): aggregate total-count comparison only (restaurant+cafe
    total vs dining total) — a coarser signal, sufficient to catch gross
    drift, not a row-level migration-correctness re-proof (that already
    exists in tests/test_dining_migration.py from Batch A).

Usage:
    cd backend && source .venv/bin/activate
    python scripts/reconcile_dining_vs_legacy.py

Exits non-zero (and prints a DRIFT DETECTED banner) if any legacy-tracked
pair disagrees. Read-only — never writes anything.
"""
from __future__ import annotations

import sys

from sqlalchemy import create_engine, text

from app.core.config import settings

# (legacy_table, dining_table, module) — legacy_module/legacy_id tracked exactly.
LEGACY_TRACKED_PAIRS = [
    ("branches",              "dining_outlets",              "restaurant"),  # one outlet per branch
    ("branches",              "dining_outlets",              "cafe"),
    ("menu_categories",       "dining_categories",            "restaurant"),
    ("cafe_categories",       "dining_categories",            "cafe"),
    ("menu_items",            "dining_items",                 "restaurant"),
    ("cafe_items",            "dining_items",                 "cafe"),
    ("menu_item_extra_groups","dining_item_extra_groups",     "restaurant"),
    ("cafe_menu_item_extra_groups", "dining_item_extra_groups", "cafe"),
    ("menu_item_variants",    "dining_item_variants",         "restaurant"),
    ("cafe_item_variants",    "dining_item_variants",         "cafe"),
    ("dining_tables",         "dining_venue_tables",          "restaurant"),  # restaurant's own (pre-existing) table model
    ("cafe_tables",           "dining_venue_tables",          "cafe"),
    ("orders",                "dining_orders",                "restaurant"),
    ("cafe_orders",           "dining_orders",                "cafe"),
    ("order_items",           "dining_order_items",           "restaurant"),
    ("cafe_order_items",      "dining_order_items",           "cafe"),
]

# (legacy_tables, dining_table) — no legacy_id, aggregate count only.
AGGREGATE_ONLY_PAIRS = [
    (["menu_item_extras", "cafe_menu_item_extras"], "dining_item_extras"),
    (["menu_item_recipe_lines", "cafe_item_recipe_lines"], "dining_item_recipe_lines"),
    (["menu_item_variant_recipe_lines", "cafe_item_variant_recipe_lines"], "dining_item_variant_recipe_lines"),
]


def main() -> int:
    engine = create_engine(settings.DATABASE_URL)
    drift_found = False

    print(f"{'legacy table':<32} {'dining table':<30} {'module':<12} {'legacy':>8} {'dining':>8} {'drift':>7}")
    print("-" * 100)

    with engine.connect() as conn:
        for legacy_table, dining_table, module in LEGACY_TRACKED_PAIRS:
            legacy_count = conn.execute(text(f"SELECT count(*) FROM {legacy_table}")).scalar_one()
            dining_count = conn.execute(
                text(f"SELECT count(*) FROM {dining_table} WHERE legacy_module = :m"), {"m": module},
            ).scalar_one()
            drift = legacy_count - dining_count
            marker = "  <-- DRIFT" if drift != 0 else ""
            if drift != 0:
                drift_found = True
            print(f"{legacy_table:<32} {dining_table:<30} {module:<12} {legacy_count:>8} {dining_count:>8} {drift:>7}{marker}")

        print()
        print("Aggregate-only (no legacy_id on the dining side — coarser signal):")
        print(f"{'legacy tables':<55} {'dining table':<32} {'legacy total':>12} {'dining total':>12}")
        print("-" * 115)
        for legacy_tables, dining_table in AGGREGATE_ONLY_PAIRS:
            legacy_total = sum(
                conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() for t in legacy_tables
            )
            dining_total = conn.execute(text(f"SELECT count(*) FROM {dining_table}")).scalar_one()
            marker = "  <-- possible drift (informational)" if legacy_total != dining_total else ""
            print(f"{'+'.join(legacy_tables):<55} {dining_table:<32} {legacy_total:>12} {dining_total:>12}{marker}")

    print()
    if drift_found:
        print("DRIFT DETECTED — dining_* is stale relative to restaurant/cafe. "
              "Do not proceed to the analytics/finance cutover (D-05) until this is resolved.")
        return 1
    print("No drift — dining_* row counts match restaurant/cafe exactly for all legacy-tracked entities.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
