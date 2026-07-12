"""
tests/test_dining_migration.py
Postgres-only verification of the D-02 data-copy migration
(alembic/versions/0bd6f63e5446_dining_unified_module_initial_schema.py) —
proves that seeded restaurant/cafe data survives the copy into the new
dining_* tables losslessly.

Why this lives outside the normal `pytest tests/` SQLite run: the copy
migration is written in raw Postgres SQL (correlated subqueries, an
explicit ``::text`` cast for JSON equality, etc. — see the migration
file's own docstring) and there is no existing precedent in this project
for running Alembic's full ~59-migration chain against the SQLite
in-memory test database (conftest.py builds test tables directly via
``Base.metadata.create_all``, it never invokes Alembic). Forcing this
migration to also be SQLite-compatible would mean rewriting it in a
weaker, more portable dialect for a copy that will only ever run once,
against real Postgres, in this project's actual deployment. Same
category of "verified live" as CLAUDE.md §13 ⓫'s row-locking note (only
Postgres actually enforces the behavior being tested).

Usage — set an admin Postgres DSN before running:

    DINING_MIGRATION_TEST_ADMIN_URL=postgresql+psycopg://postgres:resort_dev_pass@localhost:5436/postgres \\
        pytest tests/test_dining_migration.py -v

Skips automatically (does not fail, does not affect `pytest tests/`'s
100%-green requirement) when that env var is unset — which is the
default, so this file has zero effect on the normal SQLite-based suite.

This exact scenario (seed restaurant + cafe data covering variants,
recipe lines, extras, a held order, a fully-refunded order → run the
migration → assert exact row-count parity + spot-check key
relationships → assert an idempotent re-run creates zero duplicates →
assert downgrade/upgrade round-trips cleanly) was already run manually,
successfully, against a real disposable Postgres database before this
file existed (see the D-02 commit message for the full manual
transcript). This file automates that same scenario as a reusable,
checked-in artifact.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest

DINING_MIGRATION_TEST_ADMIN_URL = os.environ.get("DINING_MIGRATION_TEST_ADMIN_URL")

pytestmark = pytest.mark.skipif(
    not DINING_MIGRATION_TEST_ADMIN_URL,
    reason=(
        "Postgres-only migration test — set DINING_MIGRATION_TEST_ADMIN_URL "
        "(admin DSN, e.g. postgresql+psycopg://postgres:pass@localhost:5436/postgres) "
        "to run. Skipped by default; does not affect `pytest tests/`."
    ),
)


@pytest.fixture
def migrated_db_url():
    """Creates a throwaway Postgres database and yields its (unmigrated)
    URL — function-scoped so each test gets a fully isolated database and
    seeds its own data independently (no cross-test collisions on
    order_number/warehouse code/etc, and no assumption about which
    revision an earlier test left the shared DB at). Dropped at the end
    regardless of outcome. Applying the actual Alembic chain is each
    test's own job (some need data seeded mid-chain, before the dining
    migration runs)."""
    import sqlalchemy as sa

    admin_engine = sa.create_engine(DINING_MIGRATION_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT")
    db_name = f"resort_os_dining_migtest_{uuid.uuid4().hex[:10]}"
    base_url = DINING_MIGRATION_TEST_ADMIN_URL.rsplit("/", 1)[0]
    target_url = f"{base_url}/{db_name}"

    with admin_engine.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))

    try:
        yield target_url
    finally:
        admin_engine.dispose()
        # New connection — can't DROP DATABASE while other connections to it
        # might still be pooled on this same engine.
        cleanup_engine = sa.create_engine(DINING_MIGRATION_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT")
        with cleanup_engine.connect() as conn:
            conn.execute(sa.text(f'SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
                                  f"WHERE datname = '{db_name}' AND pid <> pg_backend_pid()"))
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        cleanup_engine.dispose()


def _alembic_config(db_url: str):
    from alembic.config import Config

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


class _upgrade_to:
    """alembic/env.py unconditionally does
    ``config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)`` —
    it always wins over whatever this test set on the Config object,
    because env.py is re-executed as a script on every alembic invocation
    (see util.load_python_file) and reads the *live* app.core.config.settings
    singleton fresh each time. conftest.py forces that singleton to the
    SQLite test URL for the rest of the suite, so migration commands here
    would silently run against SQLite instead of the throwaway Postgres
    database without this: temporarily point settings.DATABASE_URL at the
    real target for the duration of a single upgrade/downgrade call, then
    restore it — the normal SQLite-based suite must never observe this
    module's Postgres URL."""

    def __init__(self, db_url: str):
        self.db_url = db_url
        self._original = None

    def __enter__(self):
        from app.core.config import settings
        self._original = settings.DATABASE_URL
        settings.DATABASE_URL = self.db_url
        return self

    def __exit__(self, *exc_info):
        from app.core.config import settings
        settings.DATABASE_URL = self._original


PRE_DINING_REVISION = "b3c7d9e1f2a4"  # last head before the dining migration
DINING_REVISION = "0bd6f63e5446"      # this migration's own revision id


def _seed_restaurant_and_cafe(engine) -> None:
    """Raw-SQL seed covering every shape the copy migration has to handle:
    a category → item → recipe line → variant → variant recipe line
    chain, an extras group + extra, a table, a paid dine-in order with an
    extra, a held order with no table, and a fully-refunded cafe order —
    the exact same scenario verified manually before this file existed."""
    import sqlalchemy as sa

    unique = uuid.uuid4().hex[:8].upper()  # warehouses.code / products.sku are globally unique
    with engine.begin() as conn:
        branch_id = conn.execute(sa.text(
            "INSERT INTO branches (name, name_ar, code, is_active, created_at, updated_at) "
            "VALUES ('Migration Test Branch', 'فرع اختبار', :code, true, now(), now()) RETURNING id"
        ), {"code": f"MIG-{unique}"}).scalar_one()

        wh_id = conn.execute(sa.text(
            "INSERT INTO warehouses (branch_id, name, code, is_active, created_at, updated_at) "
            "VALUES (:b, 'Main WH', :code, true, now(), now()) RETURNING id"
        ), {"b": branch_id, "code": f"WH-{unique}"}).scalar_one()

        beef_id = conn.execute(sa.text(
            "INSERT INTO products (branch_id, name, sku, unit, cost_price, current_stock, min_stock, "
            "reorder_point, warehouse_id, is_active, created_at, updated_at) "
            "VALUES (:b, 'Beef', :sku, 'kg', 180.00, 0, 0, 0, :wh, true, now(), now()) RETURNING id"
        ), {"b": branch_id, "wh": wh_id, "sku": f"BEEF-{unique}"}).scalar_one()

        cat_id = conn.execute(sa.text(
            "INSERT INTO menu_categories (branch_id, name, sort_order, is_active, created_at, updated_at) "
            "VALUES (:b, 'Mains', 1, true, now(), now()) RETURNING id"
        ), {"b": branch_id}).scalar_one()

        item_id = conn.execute(sa.text(
            "INSERT INTO menu_items (branch_id, category_id, name, price, is_available, "
            "preparation_minutes, station, created_at, updated_at) "
            "VALUES (:b, :c, 'Burger', 80.00, true, 10, 'grill', now(), now()) RETURNING id"
        ), {"b": branch_id, "c": cat_id}).scalar_one()

        conn.execute(sa.text(
            "INSERT INTO menu_item_recipe_lines (menu_item_id, product_id, quantity_per_unit, created_at, updated_at) "
            "VALUES (:i, :p, 0.2, now(), now())"
        ), {"i": item_id, "p": beef_id})

        variant_id = conn.execute(sa.text(
            "INSERT INTO menu_item_variants (menu_item_id, name, price, is_available, sort_order, created_at, updated_at) "
            "VALUES (:i, 'Double', 110.00, true, 0, now(), now()) RETURNING id"
        ), {"i": item_id}).scalar_one()

        conn.execute(sa.text(
            "INSERT INTO menu_item_variant_recipe_lines (variant_id, product_id, quantity_per_unit, created_at, updated_at) "
            "VALUES (:v, :p, 0.4, now(), now())"
        ), {"v": variant_id, "p": beef_id})

        group_id = conn.execute(sa.text(
            "INSERT INTO menu_item_extra_groups (menu_item_id, name, min_select, max_select, sort_order, created_at, updated_at) "
            "VALUES (:i, 'Extras', 0, 2, 0, now(), now()) RETURNING id"
        ), {"i": item_id}).scalar_one()

        extra_id = conn.execute(sa.text(
            "INSERT INTO menu_item_extras (group_id, name, price_addition, is_available, sort_order, created_at, updated_at) "
            "VALUES (:g, 'Cheese', 5.00, true, 0, now(), now()) RETURNING id"
        ), {"g": group_id}).scalar_one()

        table_id = conn.execute(sa.text(
            "INSERT INTO dining_tables (branch_id, table_number, capacity, status, created_at, updated_at) "
            "VALUES (:b, 'T1', 4, 'available', now(), now()) RETURNING id"
        ), {"b": branch_id}).scalar_one()

        order_id = conn.execute(sa.text(
            "INSERT INTO orders (branch_id, table_id, order_number, status, order_type, subtotal, vat_amount, "
            "service_charge, discount_amount, total, refunded_amount, guests_count, waiter_id, payment_method, "
            "created_at, updated_at) "
            "VALUES (:b, :t, 'ORD-MIGTEST-0001', 'paid', 'dine_in', 80.00, 11.20, 9.60, 0, 100.80, 0, 2, 1, "
            "'cash', now(), now()) RETURNING id"
        ), {"b": branch_id, "t": table_id}).scalar_one()

        order_item_id = conn.execute(sa.text(
            "INSERT INTO order_items (order_id, menu_item_id, name, unit_price, quantity, status, created_at, updated_at) "
            "VALUES (:o, :i, 'Burger', 80.00, 1, 'served', now(), now()) RETURNING id"
        ), {"o": order_id, "i": item_id}).scalar_one()

        conn.execute(sa.text(
            "INSERT INTO order_item_extras (order_item_id, extra_id, extra_name, price_addition, created_at, updated_at) "
            "VALUES (:oi, :e, 'Cheese', 5.00, now(), now())"
        ), {"oi": order_item_id, "e": extra_id})

        # Held order, no table — must survive with NULL table_id.
        conn.execute(sa.text(
            "INSERT INTO orders (branch_id, order_number, status, order_type, subtotal, vat_amount, "
            "service_charge, discount_amount, total, refunded_amount, guests_count, created_at, updated_at) "
            "VALUES (:b, 'ORD-MIGTEST-0002', 'held', 'takeaway', 0, 0, 0, 0, 0, 0, 1, now(), now())"
        ), {"b": branch_id})

        # Cafe side — a fully-refunded order must survive with matching
        # refunded_amount and a voided_reason on its item.
        ccat_id = conn.execute(sa.text(
            "INSERT INTO cafe_categories (branch_id, name, sort_order, is_active, created_at, updated_at) "
            "VALUES (:b, 'Coffee', 1, true, now(), now()) RETURNING id"
        ), {"b": branch_id}).scalar_one()

        citem_id = conn.execute(sa.text(
            "INSERT INTO cafe_items (branch_id, category_id, name, price, is_available, "
            "preparation_minutes, station, created_at, updated_at) "
            "VALUES (:b, :c, 'Cappuccino', 30.00, true, 5, 'bar', now(), now()) RETURNING id"
        ), {"b": branch_id, "c": ccat_id}).scalar_one()

        corder_id = conn.execute(sa.text(
            "INSERT INTO cafe_orders (branch_id, order_number, status, order_type, subtotal, vat_amount, "
            "service_charge, discount_amount, total, refunded_amount, created_at, updated_at) "
            "VALUES (:b, 'ORD-MIGTEST-0003', 'refunded', 'takeaway', 30.00, 4.20, 3.60, 0, 37.80, 37.80, now(), now()) RETURNING id"
        ), {"b": branch_id}).scalar_one()

        conn.execute(sa.text(
            "INSERT INTO cafe_order_items (order_id, item_id, name, unit_price, quantity, status, "
            "voided_reason, voided_by, voided_at, created_at, updated_at) "
            "VALUES (:o, :i, 'Cappuccino', 30.00, 1, 'refunded', 'guest not happy', 1, now(), now(), now())"
        ), {"o": corder_id, "i": citem_id})

    return branch_id


class TestDiningMigrationDataCopy:

    def test_seeded_data_survives_copy_losslessly(self, migrated_db_url):
        import sqlalchemy as sa
        from alembic import command

        cfg = _alembic_config(migrated_db_url)
        with _upgrade_to(migrated_db_url):
            command.upgrade(cfg, PRE_DINING_REVISION)

        engine = sa.create_engine(migrated_db_url)
        try:
            branch_id = _seed_restaurant_and_cafe(engine)
        finally:
            engine.dispose()

        with _upgrade_to(migrated_db_url):
            command.upgrade(cfg, DINING_REVISION)

        engine = sa.create_engine(migrated_db_url)
        try:
            with engine.connect() as conn:
                def count(table, **where):
                    clause = " AND ".join(f"{k} = :{k}" for k in where) or "true"
                    return conn.execute(sa.text(f"SELECT count(*) FROM {table} WHERE {clause}"), where).scalar_one()

                # ── Exact row-count parity, source vs. copy ─────────────
                assert count("menu_categories") == count("dining_categories", legacy_module="restaurant")
                assert count("cafe_categories") == count("dining_categories", legacy_module="cafe")
                assert count("menu_items") == count("dining_items", legacy_module="restaurant")
                assert count("cafe_items") == count("dining_items", legacy_module="cafe")
                assert count("menu_item_variants") == count("dining_item_variants", legacy_module="restaurant")
                assert count("menu_item_recipe_lines") == count("dining_item_recipe_lines")
                assert count("menu_item_variant_recipe_lines") == count("dining_item_variant_recipe_lines")
                assert count("menu_item_extra_groups") == count("dining_item_extra_groups", legacy_module="restaurant")
                assert count("menu_item_extras") == count("dining_item_extras")
                assert count("dining_tables") == count("dining_venue_tables", legacy_module="restaurant")
                assert count("orders") == count("dining_orders", legacy_module="restaurant")
                assert count("cafe_orders") == count("dining_orders", legacy_module="cafe")
                assert count("order_items") == count("dining_order_items", legacy_module="restaurant")
                assert count("cafe_order_items") == count("dining_order_items", legacy_module="cafe")
                assert count("order_item_extras") == count("dining_order_item_extras")

                # ── Relationships resolved correctly ────────────────────
                paid = conn.execute(sa.text(
                    "SELECT do2.status, do2.total, do2.refunded_amount, vt.table_number, out.outlet_type "
                    "FROM dining_orders do2 "
                    "JOIN dining_venue_tables vt ON vt.id = do2.table_id "
                    "JOIN dining_outlets out ON out.id = do2.outlet_id "
                    "WHERE do2.legacy_module = 'restaurant' AND do2.order_number = 'ORD-MIGTEST-0001'"
                )).one()
                assert paid.status == "paid"
                assert paid.total == Decimal("100.80")
                assert paid.refunded_amount == Decimal("0.00")
                assert paid.table_number == "T1"
                assert paid.outlet_type == "restaurant"

                held = conn.execute(sa.text(
                    "SELECT status, table_id, total FROM dining_orders "
                    "WHERE legacy_module = 'restaurant' AND order_number = 'ORD-MIGTEST-0002'"
                )).one()
                assert held.status == "held"
                assert held.table_id is None

                refunded = conn.execute(sa.text(
                    "SELECT status, total, refunded_amount FROM dining_orders "
                    "WHERE legacy_module = 'cafe' AND order_number = 'ORD-MIGTEST-0003'"
                )).one()
                assert refunded.status == "refunded"
                assert refunded.total == refunded.refunded_amount == Decimal("37.80")

                refunded_item = conn.execute(sa.text(
                    "SELECT doi.status, doi.voided_reason FROM dining_order_items doi "
                    "JOIN dining_orders do2 ON do2.id = doi.order_id "
                    "WHERE do2.legacy_module = 'cafe' AND do2.order_number = 'ORD-MIGTEST-0003'"
                )).one()
                assert refunded_item.status == "refunded"
                assert refunded_item.voided_reason == "guest not happy"

                variant_recipe = conn.execute(sa.text(
                    "SELECT p.name AS product_name, dvrl.quantity_per_unit "
                    "FROM dining_item_variant_recipe_lines dvrl "
                    "JOIN dining_item_variants dv ON dv.id = dvrl.variant_id "
                    "JOIN products p ON p.id = dvrl.product_id "
                    "WHERE dv.name = 'Double'"
                )).one()
                assert variant_recipe.product_name == "Beef"
                assert variant_recipe.quantity_per_unit == Decimal("0.400")

                extra_row = conn.execute(sa.text(
                    "SELECT doie.extra_name, doie.price_addition, de.id IS NOT NULL AS extra_resolved "
                    "FROM dining_order_item_extras doie "
                    "LEFT JOIN dining_item_extras de ON de.id = doie.extra_id "
                    "JOIN dining_order_items doi ON doi.id = doie.order_item_id "
                    "JOIN dining_orders do2 ON do2.id = doi.order_id "
                    "WHERE do2.order_number = 'ORD-MIGTEST-0001'"
                )).one()
                assert extra_row.extra_name == "Cheese"
                assert extra_row.extra_resolved is True

                # ── Outlets seeded with the exact pre-existing account codes ──
                outlets = {r.outlet_type: r.revenue_account_code for r in conn.execute(sa.text(
                    "SELECT outlet_type, revenue_account_code FROM dining_outlets WHERE branch_id = :b"
                ), {"b": branch_id})}
                assert outlets == {"restaurant": "4200", "cafe": "4400"}
        finally:
            engine.dispose()

    def test_copy_is_idempotent_on_rerun(self, migrated_db_url):
        """Re-running the migration's data-copy function must create zero
        duplicate rows — every INSERT is guarded by NOT EXISTS keyed off
        legacy_module/legacy_id."""
        import importlib.util
        import sqlalchemy as sa
        from alembic import command

        cfg = _alembic_config(migrated_db_url)
        with _upgrade_to(migrated_db_url):
            command.upgrade(cfg, PRE_DINING_REVISION)

        engine = sa.create_engine(migrated_db_url)
        try:
            _seed_restaurant_and_cafe(engine)
        finally:
            engine.dispose()

        with _upgrade_to(migrated_db_url):
            command.upgrade(cfg, DINING_REVISION)

        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        migration_path = os.path.join(
            backend_dir, "alembic", "versions",
            "0bd6f63e5446_dining_unified_module_initial_schema.py",
        )
        spec = importlib.util.spec_from_file_location("dining_migration_0bd6f63e5446", migration_path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)

        engine = sa.create_engine(migrated_db_url)
        try:
            with engine.connect() as conn:
                before = conn.execute(sa.text("SELECT count(*) FROM dining_orders")).scalar_one()

            with engine.begin() as conn:
                migration._copy_restaurant_and_cafe_data_into_dining(conn)

            with engine.connect() as conn:
                after = conn.execute(sa.text("SELECT count(*) FROM dining_orders")).scalar_one()

            assert before == after == 3
        finally:
            engine.dispose()

    def test_downgrade_upgrade_round_trip_is_clean(self, migrated_db_url):
        from alembic import command

        cfg = _alembic_config(migrated_db_url)
        with _upgrade_to(migrated_db_url):
            command.upgrade(cfg, DINING_REVISION)
            command.downgrade(cfg, PRE_DINING_REVISION)
            command.upgrade(cfg, DINING_REVISION)
        # No assertion needed beyond "did not raise" — a failed downgrade
        # (FK left dangling, table not dropped in dependency order, etc.)
        # would have thrown before reaching this line.
