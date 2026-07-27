"""PostgreSQL regression coverage for DB-01's historical dining cutover.

The default test suite creates tables directly on SQLite and therefore cannot
exercise PostgreSQL's catalog or the real Alembic chain.  Set an explicit admin
DSN to enable these disposable-database tests:

    DB01_MIGRATION_TEST_ADMIN_URL=postgresql+psycopg://.../postgres \
        pytest tests/test_db01_alembic_chain.py -v
"""
from __future__ import annotations

import importlib.util
import os
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest


DB01_MIGRATION_TEST_ADMIN_URL = os.environ.get(
    "DB01_MIGRATION_TEST_ADMIN_URL"
)
POSTGRES_ONLY = pytest.mark.skipif(
    not DB01_MIGRATION_TEST_ADMIN_URL,
    reason=(
        "PostgreSQL-only migration test; set "
        "DB01_MIGRATION_TEST_ADMIN_URL to an admin DSN."
    ),
)

PRE_CUTOVER_REVISION = "d2e4f6a8b1c3"
CUTOVER_REVISION = "e3f5a7b9c2d4"


@pytest.fixture
def migrated_db_url():
    """Yield a unique empty PostgreSQL database and always remove it."""
    import sqlalchemy as sa
    from sqlalchemy.engine import make_url

    source_url = make_url(DB01_MIGRATION_TEST_ADMIN_URL)
    admin_url = source_url
    db_name = f"resort_os_db01_{uuid.uuid4().hex[:12]}"
    target_url = source_url.set(database=db_name)
    admin_engine = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")

    with admin_engine.connect() as connection:
        connection.execute(sa.text(f'CREATE DATABASE "{db_name}"'))

    try:
        yield target_url.render_as_string(hide_password=False)
    finally:
        with admin_engine.connect() as connection:
            connection.execute(
                sa.text(
                    """
                    SELECT pg_terminate_backend(pid)
                      FROM pg_stat_activity
                     WHERE datname = :database_name
                       AND pid <> pg_backend_pid()
                    """
                ),
                {"database_name": db_name},
            )
            connection.execute(sa.text(f'DROP DATABASE "{db_name}"'))
        admin_engine.dispose()


def _alembic_config(db_url: str):
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", db_url)
    return config


@contextmanager
def _database_url(db_url: str):
    """Temporarily override the settings singleton used by alembic/env.py."""
    from app.core.config import settings

    original = settings.DATABASE_URL
    settings.DATABASE_URL = db_url
    try:
        yield
    finally:
        settings.DATABASE_URL = original


def _upgrade(db_url: str, revision: str) -> None:
    from alembic import command

    with _database_url(db_url):
        command.upgrade(_alembic_config(db_url), revision)


def _downgrade(db_url: str, revision: str) -> None:
    from alembic import command

    with _database_url(db_url):
        command.downgrade(_alembic_config(db_url), revision)


def _table_names(connection) -> set[str]:
    import sqlalchemy as sa

    return set(connection.execute(sa.text(
        """
        SELECT table_name
          FROM information_schema.tables
         WHERE table_schema = current_schema()
           AND table_type = 'BASE TABLE'
        """
    )).scalars())


@POSTGRES_ONLY
def test_fresh_postgresql_chain_reaches_current_head(migrated_db_url):
    """The clean chain must pass the drift-only e3 objects and reach head."""
    import sqlalchemy as sa
    from alembic.script import ScriptDirectory

    _upgrade(migrated_db_url, "head")

    engine = sa.create_engine(migrated_db_url)
    with engine.connect() as connection:
        actual_heads = set(connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalars())
        tables = _table_names(connection)
        split_column = connection.execute(sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_schema = current_schema()
                   AND table_name = 'dining_order_items'
                   AND column_name = 'split_id'
            )
            """
        )).scalar_one()

    expected_heads = set(
        ScriptDirectory.from_config(_alembic_config(migrated_db_url)).get_heads()
    )
    assert actual_heads == expected_heads
    assert "dining_orders" in tables
    assert "dining_order_items" in tables
    assert "dining_order_splits" not in tables
    assert "dining_order_payments" not in tables
    assert "orders" not in tables
    assert "cafe_orders" not in tables
    assert split_column is False

    # A database already stamped at head must remain a clean no-op.
    _upgrade(migrated_db_url, "head")
    engine.dispose()


@POSTGRES_ONLY
def test_cutover_cleans_the_original_deployment_drift_shape(migrated_db_url):
    """e3 must still clean the objects that only existed in the old live DB."""
    import sqlalchemy as sa

    _upgrade(migrated_db_url, PRE_CUTOVER_REVISION)
    engine = sa.create_engine(migrated_db_url)
    with engine.begin() as connection:
        connection.execute(sa.text(
            """
            CREATE TABLE dining_order_splits (
                id SERIAL PRIMARY KEY,
                order_id INTEGER REFERENCES dining_orders(id) ON DELETE CASCADE
            )
            """
        ))
        connection.execute(sa.text(
            """
            CREATE INDEX ix_dining_order_splits_order_id
                ON dining_order_splits (order_id)
            """
        ))
        connection.execute(sa.text(
            """
            ALTER TABLE dining_order_items
                ADD COLUMN split_id INTEGER
            """
        ))
        connection.execute(sa.text(
            """
            ALTER TABLE dining_order_items
                ADD CONSTRAINT fk_dining_order_items_split_id
                FOREIGN KEY (split_id)
                REFERENCES dining_order_splits(id)
                ON DELETE SET NULL
            """
        ))
        connection.execute(sa.text(
            """
            CREATE TABLE dining_order_payments (
                id SERIAL PRIMARY KEY,
                order_id INTEGER REFERENCES dining_orders(id) ON DELETE CASCADE,
                split_id INTEGER REFERENCES dining_order_splits(id)
                    ON DELETE CASCADE
            )
            """
        ))
        connection.execute(sa.text(
            """
            CREATE INDEX ix_dining_order_payments_order_id
                ON dining_order_payments (order_id)
            """
        ))
        connection.execute(sa.text(
            """
            CREATE INDEX ix_dining_order_payments_split_id
                ON dining_order_payments (split_id)
            """
        ))

    _upgrade(migrated_db_url, CUTOVER_REVISION)

    with engine.connect() as connection:
        tables = _table_names(connection)
        split_column = connection.execute(sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_schema = current_schema()
                   AND table_name = 'dining_order_items'
                   AND column_name = 'split_id'
            )
            """
        )).scalar_one()

    assert "dining_order_splits" not in tables
    assert "dining_order_payments" not in tables
    assert split_column is False

    # The cutover is intentionally destructive.  Alembic must surface that
    # clearly and leave the revision unchanged, rather than claiming a partial
    # downgrade that cannot restore the deleted legacy data.
    with pytest.raises(NotImplementedError, match="backup"):
        _downgrade(migrated_db_url, PRE_CUTOVER_REVISION)
    with engine.connect() as connection:
        assert connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one() == CUTOVER_REVISION

    # Prove later migrations remain compatible with the deployment-drift path.
    _upgrade(migrated_db_url, "head")
    engine.dispose()


def test_cutover_downgrade_is_explicitly_irreversible():
    """Destructive legacy-data removal must not pretend to be reversible."""
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "e3f5a7b9c2d4_drop_legacy_dining_cafe_restaurant_tables.py"
    )
    spec = importlib.util.spec_from_file_location("db01_cutover", migration_path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    with pytest.raises(NotImplementedError, match="backup"):
        migration.downgrade()
