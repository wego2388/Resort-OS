"""
tests/test_operational_history_seed_dry_run.py
Postgres-only verification of a critical safety fix in
app/operational_history_seed.py::main() — see that file's docstring in
main() for the full incident writeup.

Why this lives outside the normal `pytest tests/` SQLite run: every real
HIST-01 generator calls production services (create_employee,
run_payroll_for_branch, post_journal_entry, ...) that call db.commit()
internally, per this project's standard services.py convention. Plain
SQLAlchemy `Session.rollback()` cannot undo an already-committed DB
transaction — the fix relies on binding the Session to an explicit
connection-level transaction with `join_transaction_mode="create_savepoint"`
so internal commits only close a SAVEPOINT, and PostgreSQL's real savepoint
semantics are what make the final rollback actually discard everything.
SQLite's pysqlite driver does not reproduce this without extra
begin/isolation-level event-listener wiring the app itself never needs
(this tool only ever targets real Postgres) — same category as
test_dining_migration.py's rationale for living outside the SQLite suite.

Usage — set an admin Postgres DSN before running:

    HIST01_DRY_RUN_TEST_ADMIN_URL=postgresql+psycopg://postgres:resort_dev_pass@localhost:5436/postgres \\
        pytest tests/test_operational_history_seed_dry_run.py -v

Skips automatically (does not fail, does not affect `pytest tests/`'s
100%-green requirement) when that env var is unset — which is the
default, so this file has zero effect on the normal SQLite-based suite.

This exact scenario (run a real HIST-01-style generator against a
savepoint-mode session bound to an explicit connection transaction, then
roll the outer transaction back) was manually reproduced against a real
disposable Postgres database before this file existed, confirming both
the bug (plain db.rollback() left 14 committed Employee rows behind) and
the fix (outer_txn.rollback() leaves zero rows, including the Branch
itself) — this file automates that same scenario as a reusable, checked-in
artifact.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest

HIST01_DRY_RUN_TEST_ADMIN_URL = os.environ.get("HIST01_DRY_RUN_TEST_ADMIN_URL")

pytestmark = pytest.mark.skipif(
    not HIST01_DRY_RUN_TEST_ADMIN_URL,
    reason=(
        "Postgres-only dry-run safety test — set HIST01_DRY_RUN_TEST_ADMIN_URL "
        "(admin DSN, e.g. postgresql+psycopg://postgres:pass@localhost:5436/postgres) "
        "to run. Skipped by default; does not affect `pytest tests/`."
    ),
)


@pytest.fixture
def throwaway_db_url():
    """Creates a throwaway Postgres database with the full app schema
    (Base.metadata.create_all — same approach test_hist_pms_bookings.py's
    isolated-engine fixture uses, just against real Postgres instead of
    SQLite here) and yields its URL. Dropped at the end regardless of
    outcome."""
    import sqlalchemy as sa

    admin_engine = sa.create_engine(HIST01_DRY_RUN_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT")
    db_name = f"resort_os_hist01_dryrun_{uuid.uuid4().hex[:10]}"
    base_url = HIST01_DRY_RUN_TEST_ADMIN_URL.rsplit("/", 1)[0]
    target_url = f"{base_url}/{db_name}"

    with admin_engine.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))

    try:
        yield target_url
    finally:
        admin_engine.dispose()
        cleanup_engine = sa.create_engine(HIST01_DRY_RUN_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT")
        with cleanup_engine.connect() as conn:
            conn.execute(sa.text(f'SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
                                  f"WHERE datname = '{db_name}' AND pid <> pg_backend_pid()"))
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        cleanup_engine.dispose()


def _create_schema(engine) -> None:
    from app.core.database import Base
    import app.core.kernel.models.user           # noqa: F401
    import app.modules.core.models                # noqa: F401
    import app.modules.finance.models              # noqa: F401
    import app.modules.hr.models                   # noqa: F401
    import app.modules.pms.models                  # noqa: F401
    import app.modules.beach.models                # noqa: F401
    import app.modules.maintenance.models           # noqa: F401
    import app.modules.crm.models                   # noqa: F401
    import app.modules.hub.models                   # noqa: F401
    import app.modules.inventory.models             # noqa: F401
    import app.modules.timeshare.models              # noqa: F401
    import app.modules.leasing.models                # noqa: F401
    import app.modules.analytics.models              # noqa: F401
    import app.modules.dining.models                 # noqa: F401
    import app.modules.owner.models                  # noqa: F401
    import app.modules.credit.models                 # noqa: F401
    Base.metadata.create_all(bind=engine)


class TestDryRunActuallyRollsBackServiceLevelCommits:
    def test_savepoint_mode_session_discards_internal_commits_on_outer_rollback(self, throwaway_db_url):
        """يستخدم hr_services.create_employee (بينادي db.commit() داخليًا،
        نفس اصطلاح كل services.py في المشروع) كمثال حقيقي — نفس بالظبط
        الآلية اللي main() بيستخدمها للـHIST-01 كله."""
        import sqlalchemy as sa
        from sqlalchemy.orm import Session

        from app.core.kernel.models.user import User, UserRole
        from app.core.kernel.security import get_password_hash
        from app.modules.core.models import Branch
        from app.modules.hr import services as hr_services
        from app.modules.hr.models import Employee
        from app.modules.hr.schemas import EmployeeCreate

        engine = sa.create_engine(throwaway_db_url)
        _create_schema(engine)

        setup_session = Session(bind=engine)
        setup_session.add(User(
            id=1, email="dryrun-actor@test.invalid", password_hash=get_password_hash("x"),
            full_name="actor", role=UserRole.SUPER_ADMIN, is_active=True, two_factor_enabled=False,
        ))
        setup_session.commit()
        setup_session.close()

        connection = engine.connect()
        outer_txn = connection.begin()
        db = Session(bind=connection, join_transaction_mode="create_savepoint")

        branch_code = f"DR-{uuid.uuid4().hex[:6].upper()}"
        branch = Branch(name="DryRun Test", name_ar="اختبار dry-run",
                         code=branch_code, timezone="Africa/Cairo", is_active=True)
        db.add(branch)
        db.commit()  # internal commit #1 — savepoint only

        hr_services.create_employee(db, EmployeeCreate(
            branch_id=branch.id, employee_code="DRYRUN-01", full_name="Test",
            position="Test", basic_salary=Decimal("10000.00"), hire_date="2024-01-01",
        ))  # internal commit #2 (inside create_employee) — savepoint only

        outer_txn.rollback()
        connection.close()
        db.close()

        verify_session = Session(bind=engine)
        try:
            assert verify_session.query(Employee).count() == 0
            assert verify_session.query(Branch).filter(Branch.code == branch_code).count() == 0
        finally:
            verify_session.close()
        engine.dispose()

    def test_apply_mode_commits_survive(self, throwaway_db_url):
        """نفس الآلية، لكن outer_txn.commit() — البيانات لازم تفضل موجودة
        (مطابق لسلوك --apply الحقيقي في main())."""
        import sqlalchemy as sa
        from sqlalchemy.orm import Session

        from app.core.kernel.models.user import User, UserRole
        from app.core.kernel.security import get_password_hash
        from app.modules.core.models import Branch
        from app.modules.hr import services as hr_services
        from app.modules.hr.models import Employee
        from app.modules.hr.schemas import EmployeeCreate

        engine = sa.create_engine(throwaway_db_url)
        _create_schema(engine)

        setup_session = Session(bind=engine)
        setup_session.add(User(
            id=1, email="dryrun-actor@test.invalid", password_hash=get_password_hash("x"),
            full_name="actor", role=UserRole.SUPER_ADMIN, is_active=True, two_factor_enabled=False,
        ))
        setup_session.commit()
        setup_session.close()

        connection = engine.connect()
        outer_txn = connection.begin()
        db = Session(bind=connection, join_transaction_mode="create_savepoint")

        branch_code = f"AP-{uuid.uuid4().hex[:6].upper()}"
        branch = Branch(name="Apply Test", name_ar="اختبار apply",
                         code=branch_code, timezone="Africa/Cairo", is_active=True)
        db.add(branch)
        db.commit()
        hr_services.create_employee(db, EmployeeCreate(
            branch_id=branch.id, employee_code="APPLYTEST-01", full_name="Test",
            position="Test", basic_salary=Decimal("10000.00"), hire_date="2024-01-01",
        ))

        outer_txn.commit()
        connection.close()
        db.close()

        verify_session = Session(bind=engine)
        try:
            assert verify_session.query(Employee).filter_by(employee_code="APPLYTEST-01").count() == 1
            assert verify_session.query(Branch).filter(Branch.code == branch_code).count() == 1
        finally:
            verify_session.close()
        engine.dispose()


class TestApplyModeSurvivesMidRunCrash:
    """main()'s --apply path uses a 3-phase checkpoint precisely because a
    single all-in-one transaction (correct for dry-run) would also wipe
    the ImportBatch(status="running") crash-recovery marker on any real
    failure — silently defeating §9.1's "منع rerun حتى بعد crash" (prevent
    rerun even after a crash) requirement. This replicates main()'s exact
    phase-1/phase-2/phase-3 structure directly against operational_
    history_seed.prepare_batch/run_modules (not through main() itself,
    which binds to the app's real configured engine) using a module that
    deliberately raises partway through."""

    def test_failed_batch_status_persists_durably_while_partial_writes_roll_back(self, throwaway_db_url):
        import sqlalchemy as sa
        from sqlalchemy.orm import Session

        from app.core.kernel.models.user import User, UserRole
        from app.core.kernel.security import get_password_hash
        from app.modules.core.models import Branch, ImportBatch
        from app.modules.finance.models import Account
        import app.operational_history_seed as seed_module

        engine = sa.create_engine(throwaway_db_url)
        _create_schema(engine)

        setup_session = Session(bind=engine)
        setup_session.add(User(
            id=1, email="crash-actor@test.invalid", password_hash=get_password_hash("x"),
            full_name="actor", role=UserRole.SUPER_ADMIN, is_active=True, two_factor_enabled=False,
        ))
        branch = Branch(name="Crash Test", name_ar="اختبار انهيار",
                         code=f"CR-{uuid.uuid4().hex[:6].upper()}", timezone="Africa/Cairo", is_active=True)
        setup_session.add(branch)
        setup_session.commit()
        branch_id = branch.id
        branch_code = branch.code
        # _check_preconditions يفحص الحسابات الأساسية دي بغض النظر عن أي
        # موديولات مسجَّلة فعليًا (نفس منطق dining_beach/pms_bookings).
        for code, name, acc_type in [
            ("1100", "Cash", "asset"), ("2160", "VAT", "liability"),
            ("2165", "Service", "liability"), ("4100", "Room Revenue", "revenue"),
        ]:
            setup_session.add(Account(branch_id=branch_id, code=code, name=name, account_type=acc_type))
        setup_session.commit()
        setup_session.close()

        def _succeeding_module(db, ctx):
            db.add(Account(branch_id=ctx.branch_id, code="9999", name="probe", account_type="asset"))
            db.commit()  # savepoint only, per the fix
            return {"counts": {"probes": 1}, "totals": {}}

        def _failing_module(db, ctx):
            raise RuntimeError("simulated crash mid-run")

        original_modules = seed_module.SCENARIO_MODULES
        seed_module.SCENARIO_MODULES = [
            seed_module.ScenarioModule(name="probe_ok", generate=_succeeding_module),
            seed_module.ScenarioModule(name="probe_fail", generate=_failing_module),
        ]
        try:
            # ── phase 1: checkpoint, real commit ──
            connection = engine.connect()
            checkpoint_txn = connection.begin()
            checkpoint_db = Session(bind=connection)
            prepared = seed_module.prepare_batch(
                checkpoint_db, branch_code=branch_code, period="2026-07", actor_id=1,
            )
            checkpoint_txn.commit()
            checkpoint_db.close()
            batch_id = prepared.batch.id

            # ── phase 2: the actual work, fails ──
            work_txn = connection.begin()
            db = Session(bind=connection, join_transaction_mode="create_savepoint")
            try:
                batch = db.get(ImportBatch, batch_id)
                seed_module.run_modules(db, batch, prepared.ctx)
                work_txn.commit()
                raise AssertionError("expected run_modules to raise")
            except RuntimeError:
                work_txn.rollback()
                # ── phase 3: durable failure marker ──
                fail_txn = connection.begin()
                fail_db = Session(bind=connection)
                failed_batch = fail_db.get(ImportBatch, batch_id)
                failed_batch.status = "failed"
                failed_batch.failure_reason = "simulated crash mid-run"
                fail_db.flush()  # راجع الباج الحقيقي الموثّق في main()'s phase 3
                fail_txn.commit()
                fail_db.close()
            finally:
                db.close()
            connection.close()
        finally:
            seed_module.SCENARIO_MODULES = original_modules

        verify_session = Session(bind=engine)
        try:
            # الـbatch نفسه فضل موجود وبحالة "failed" حقيقية — الـcheckpoint نجا
            persisted_batch = verify_session.query(ImportBatch).filter_by(id=batch_id).first()
            assert persisted_batch is not None
            assert persisted_batch.status == "failed"
            assert "simulated crash" in persisted_batch.failure_reason

            # لكن الشغل الجزئي اللي عمله probe_ok (اتعمله commit كـsavepoint
            # بس) اترجع فعليًا — مفيش حساب 9999 باقي
            assert verify_session.query(Account).filter_by(
                branch_id=branch_id, code="9999",
            ).count() == 0
        finally:
            verify_session.close()
        engine.dispose()
