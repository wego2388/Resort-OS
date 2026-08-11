"""
tests/test_owner_db_session_privileges.py
Postgres-only proof that OwnerReadSession/OwnerMetadataWriteSession are
genuinely restricted at the database level, not just in application code.
Decision 0004 §Isolation model item 5 ("A required acceptance test runs
against real PostgreSQL... and proves that an INSERT/UPDATE/DELETE
attempted through OwnerReadSession's grants fails at the database level,
not merely at the application layer").

This requires the restricted roles from scripts/provision_owner_db_roles.sql
to actually exist on the target Postgres instance — it provisions them
itself (idempotently) against a disposable per-test database so the test
is self-contained and does not depend on a specific deployment having
already run the provisioning script.

Usage — set an admin Postgres DSN before running:

    OWNER_DB_PRIVILEGE_TEST_ADMIN_URL=postgresql+psycopg://postgres:resort_dev_pass@localhost:5436/postgres \\
        pytest tests/test_owner_db_session_privileges.py -v

Skips automatically (does not fail, does not affect `pytest tests/`'s
100%-green requirement) when that env var is unset.
"""
from __future__ import annotations

import os
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

OWNER_DB_PRIVILEGE_TEST_ADMIN_URL = os.environ.get("OWNER_DB_PRIVILEGE_TEST_ADMIN_URL")

pytestmark = pytest.mark.skipif(
    not OWNER_DB_PRIVILEGE_TEST_ADMIN_URL,
    reason=(
        "Postgres-only real-privilege test — set OWNER_DB_PRIVILEGE_TEST_ADMIN_URL "
        "(admin DSN, e.g. postgresql+psycopg://postgres:pass@localhost:5436/postgres) "
        "to run. Skipped by default; does not affect `pytest tests/`."
    ),
)


@pytest.fixture
def pg_setup():
    admin_engine = sa.create_engine(OWNER_DB_PRIVILEGE_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT")
    db_name = f"resort_os_owner_priv_test_{uuid.uuid4().hex[:10]}"
    admin_url_obj = sa.engine.make_url(OWNER_DB_PRIVILEGE_TEST_ADMIN_URL)
    admin_db_url = admin_url_obj.set(database=db_name).render_as_string(hide_password=False)
    read_pw = uuid.uuid4().hex
    write_pw = uuid.uuid4().hex

    with admin_engine.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
    admin_engine.dispose()

    from app.core.database import Base
    import app.core.kernel.models.user      # noqa: F401
    import app.modules.core.models          # noqa: F401
    import app.modules.owner.models         # noqa: F401

    schema_engine = sa.create_engine(admin_db_url, pool_pre_ping=True)
    Base.metadata.create_all(bind=schema_engine)
    schema_engine.dispose()

    # Provision the two restricted roles directly against the throwaway
    # database — mirrors scripts/provision_owner_db_roles.sql exactly (kept
    # in sync manually since psql's `:'var'` substitution isn't usable from
    # SQLAlchemy's text()).
    provision_engine = sa.create_engine(admin_db_url, isolation_level="AUTOCOMMIT")
    with provision_engine.connect() as conn:
        conn.execute(sa.text(f"""
            DO $$
            BEGIN
              IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'owner_read_role_test') THEN
                CREATE ROLE owner_read_role_test LOGIN PASSWORD '{read_pw}';
              END IF;
              IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'owner_meta_write_role_test') THEN
                CREATE ROLE owner_meta_write_role_test LOGIN PASSWORD '{write_pw}';
              END IF;
            END
            $$;
        """))
        conn.execute(sa.text(f'GRANT CONNECT ON DATABASE "{db_name}" TO owner_read_role_test'))
        conn.execute(sa.text("GRANT USAGE ON SCHEMA public TO owner_read_role_test"))
        conn.execute(sa.text("GRANT SELECT ON ALL TABLES IN SCHEMA public TO owner_read_role_test"))
        # Decision 0004 §Isolation model item 5's one deliberate exception —
        # audit-writer needs INSERT-only on audit_logs (see
        # scripts/provision_owner_db_roles.sql and router.py's
        # _log_owner_audit). Everything else stays SELECT-only, proven by
        # the tests below.
        conn.execute(sa.text("GRANT INSERT ON audit_logs TO owner_read_role_test"))
        conn.execute(sa.text("GRANT USAGE ON audit_logs_id_seq TO owner_read_role_test"))
        conn.execute(sa.text(f'GRANT CONNECT ON DATABASE "{db_name}" TO owner_meta_write_role_test'))
        conn.execute(sa.text("GRANT USAGE ON SCHEMA public TO owner_meta_write_role_test"))
        conn.execute(sa.text(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON owner_watchlist, owner_allocation_rules "
            "TO owner_meta_write_role_test"
        ))
        conn.execute(sa.text(
            "GRANT USAGE ON owner_watchlist_id_seq, owner_allocation_rules_id_seq "
            "TO owner_meta_write_role_test"
        ))
    provision_engine.dispose()

    read_url = admin_url_obj.set(
        database=db_name, username="owner_read_role_test", password=read_pw,
    ).render_as_string(hide_password=False)
    write_url = admin_url_obj.set(
        database=db_name, username="owner_meta_write_role_test", password=write_pw,
    ).render_as_string(hide_password=False)

    try:
        yield {"admin_db_url": admin_db_url, "read_url": read_url, "write_url": write_url}
    finally:
        cleanup_engine = sa.create_engine(OWNER_DB_PRIVILEGE_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT")
        with cleanup_engine.connect() as conn:
            conn.execute(sa.text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{db_name}' AND pid <> pg_backend_pid()"
            ))
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}"'))
            conn.execute(sa.text("DROP ROLE IF EXISTS owner_read_role_test"))
            conn.execute(sa.text("DROP ROLE IF EXISTS owner_meta_write_role_test"))
        cleanup_engine.dispose()


class TestOwnerReadSessionCannotWrite:
    def test_insert_fails_at_db_level_through_read_role(self, pg_setup):
        """INSERT حقيقي عبر owner_read_role لازم يترفض من الـPostgres
        نفسه (permission denied)، مش validation في الكود — ده بالظبط
        اللي Decision 0004 بيطلبه: "proves that an INSERT/UPDATE/DELETE
        attempted through OwnerReadSession's grants fails at the database
        level, not merely at the application layer."""
        engine = sa.create_engine(pg_setup["read_url"])
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            with pytest.raises(Exception) as exc_info:
                db.execute(sa.text(
                    "INSERT INTO owner_watchlist "
                    "(owner_user_id, metric_key, display_order, branch_id, created_at, updated_at) "
                    "VALUES (1, 'x', 0, 1, now(), now())"
                ))
                db.commit()
            db.rollback()
            assert "permission denied" in str(exc_info.value).lower()
        finally:
            db.close()
            engine.dispose()

    def test_update_fails_at_db_level_through_read_role(self, pg_setup):
        engine = sa.create_engine(pg_setup["read_url"])
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            with pytest.raises(Exception) as exc_info:
                db.execute(sa.text("UPDATE owner_watchlist SET display_order = 1 WHERE id = 1"))
                db.commit()
            db.rollback()
            assert "permission denied" in str(exc_info.value).lower()
        finally:
            db.close()
            engine.dispose()

    def test_audit_log_insert_succeeds_through_read_role(self, pg_setup):
        """الاستثناء الوحيد المتعمّد (Decision 0004 §Isolation model item 5)
        — INSERT-only على audit_logs تحديدًا، عشان _log_owner_audit
        يشتغل من نفس الـsession. مفيش أي جدول تاني بيقبل كتابة من الدور ده."""
        engine = sa.create_engine(pg_setup["read_url"])
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            db.execute(sa.text(
                "INSERT INTO audit_logs (action, entity_type, created_at, updated_at) "
                "VALUES ('owner_drill_down', 'test', now(), now())"
            ))
            db.commit()
            count = db.execute(sa.text("SELECT COUNT(*) FROM audit_logs")).scalar()
            assert count == 1
        finally:
            db.close()
            engine.dispose()

    def test_select_succeeds_through_read_role(self, pg_setup):
        """تأكيد إيجابي — القراءة نفسها لازم تشتغل، مش بس الكتابة اللي بترفض."""
        engine = sa.create_engine(pg_setup["read_url"])
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            result = db.execute(sa.text("SELECT COUNT(*) FROM owner_watchlist")).scalar()
            assert result == 0
        finally:
            db.close()
            engine.dispose()


class TestOwnerMetadataWriteSessionScopedToOwnerTables:
    def test_write_to_owner_watchlist_succeeds(self, pg_setup):
        engine = sa.create_engine(pg_setup["write_url"])
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            db.execute(sa.text(
                "INSERT INTO owner_watchlist "
                "(owner_user_id, metric_key, display_order, branch_id, created_at, updated_at) "
                "VALUES (1, 'x', 0, 1, now(), now())"
            ))
            db.commit()
            count = db.execute(sa.text("SELECT COUNT(*) FROM owner_watchlist")).scalar()
            assert count == 1
        finally:
            db.close()
            engine.dispose()

    def test_write_to_operational_table_fails_at_db_level(self, pg_setup):
        """أهم اختبار في الملف ده: OwnerMetadataWriteSession — رغم إن
        اسمها "write" — لازم ميقدرش يكتب على أي جدول تشغيلي خالص (هنا:
        core_users، جدول المستخدمين نفسه)، مش بس جداول owner. الصلاحية
        الوحيدة الممنوحة فعليًا هي owner_watchlist/owner_allocation_rules."""
        engine = sa.create_engine(pg_setup["write_url"])
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            with pytest.raises(Exception) as exc_info:
                db.execute(sa.text(
                    "INSERT INTO branches (name, name_ar, code) "
                    "VALUES ('hack', 'اختراق', 'HACK1')"
                ))
                db.commit()
            db.rollback()
            assert "permission denied" in str(exc_info.value).lower()
        finally:
            db.close()
            engine.dispose()
