"""
tests/test_resort_data_cli.py
Postgres-only verification of RESET-01 (app/resort_data_cli.py +
app/resort_data_targets.py, OPS-DATA-02 §9.4).

Why this lives outside the normal `pytest tests/` SQLite run: this tool
only ever targets real Postgres (join_transaction_mode="create_savepoint"
via operational_history_seed.run_seed_against_engine, real advisory locks,
real CREATE DATABASE for rebuild-trial) — same rationale as
test_operational_history_seed_dry_run.py, which this file builds on.

Usage — set an admin Postgres DSN before running:

    RESORT_DATA_CLI_TEST_ADMIN_URL=postgresql+psycopg://postgres:resort_dev_pass@localhost:5436/postgres \\
        pytest tests/test_resort_data_cli.py -v

Skips automatically when that env var is unset — the default, zero effect
on the normal SQLite-based suite.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

RESORT_DATA_CLI_TEST_ADMIN_URL = os.environ.get("RESORT_DATA_CLI_TEST_ADMIN_URL")

pytestmark = pytest.mark.skipif(
    not RESORT_DATA_CLI_TEST_ADMIN_URL,
    reason=(
        "Postgres-only RESET-01 test — set RESORT_DATA_CLI_TEST_ADMIN_URL "
        "(admin DSN) to run. Skipped by default; does not affect `pytest tests/`."
    ),
)


@pytest.fixture
def throwaway_db_url():
    import sqlalchemy as sa

    admin_engine = sa.create_engine(RESORT_DATA_CLI_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT")
    db_name = f"resort_os_resetcli_{uuid.uuid4().hex[:10]}"
    base_url = RESORT_DATA_CLI_TEST_ADMIN_URL.rsplit("/", 1)[0]
    target_url = f"{base_url}/{db_name}"

    with admin_engine.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))

    try:
        yield target_url
    finally:
        admin_engine.dispose()
        cleanup_engine = sa.create_engine(RESORT_DATA_CLI_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT")
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


class TestTargetResolution:
    def test_unknown_target_raises(self, monkeypatch):
        from app.resort_data_targets import TargetResolutionError, resolve_target

        with pytest.raises(TargetResolutionError):
            resolve_target("staging")

    def test_vps_without_env_var_fails_closed(self, monkeypatch):
        from app.resort_data_targets import TargetResolutionError, resolve_target

        monkeypatch.delenv("RESORT_DATA_VPS_DATABASE_URL", raising=False)
        with pytest.raises(TargetResolutionError):
            resolve_target("vps")

    def test_vps_with_env_var_resolves(self, monkeypatch):
        from app.resort_data_targets import resolve_target

        monkeypatch.setenv("RESORT_DATA_VPS_DATABASE_URL", "postgresql://x:y@vps-host:5432/resort_os")
        monkeypatch.setenv("RESORT_DATA_VPS_BRANCH_CODE", "ELK-001")
        target = resolve_target("vps")
        assert target.name == "vps"
        assert target.database_url == "postgresql://x:y@vps-host:5432/resort_os"

    def test_local_falls_back_to_env_file_when_var_unset(self, monkeypatch):
        from app.resort_data_targets import resolve_target

        monkeypatch.delenv("RESORT_DATA_LOCAL_DATABASE_URL", raising=False)
        target = resolve_target("local")
        assert "postgresql" in target.database_url

    def test_local_explicit_env_var_wins_over_env_file(self, monkeypatch):
        from app.resort_data_targets import resolve_target

        monkeypatch.setenv("RESORT_DATA_LOCAL_DATABASE_URL", "postgresql://explicit:explicit@host/db")
        target = resolve_target("local")
        assert target.database_url == "postgresql://explicit:explicit@host/db"


class TestBackupVpsFailsClosed:
    def test_backup_for_vps_raises_never_touches_ssh(self, monkeypatch):
        from app.resort_data_cli import ResetToolError, cmd_backup
        from app.resort_data_targets import resolve_target

        monkeypatch.setenv("RESORT_DATA_VPS_DATABASE_URL", "postgresql://x:y@vps-host:5432/resort_os")
        target = resolve_target("vps")
        with pytest.raises(ResetToolError, match="never executes commands against a remote host"):
            cmd_backup(target, apply=True)


class TestRebuildTrialSafety:
    def test_rebuild_trial_for_vps_raises(self, monkeypatch):
        from app.resort_data_cli import ResetToolError, cmd_rebuild_trial
        from app.resort_data_targets import resolve_target

        monkeypatch.setenv("RESORT_DATA_VPS_DATABASE_URL", "postgresql://x:y@vps-host:5432/resort_os")
        target = resolve_target("vps")
        with pytest.raises(ResetToolError, match="never executes destructive operations"):
            cmd_rebuild_trial(target, apply=True, confirm=None)

    def test_rebuild_trial_disabled_flag_blocks_even_local(self, monkeypatch, throwaway_db_url):
        from app.resort_data_cli import ResetToolError, cmd_rebuild_trial
        from app.resort_data_targets import resolve_target

        monkeypatch.setenv("RESORT_DATA_LOCAL_DATABASE_URL", throwaway_db_url)
        monkeypatch.setenv("RESORT_DATA_LOCAL_REBUILD_TRIAL_ENABLED", "false")
        target = resolve_target("local")
        with pytest.raises(ResetToolError, match="disabled"):
            cmd_rebuild_trial(target, apply=False, confirm=None)

    def test_rebuild_trial_apply_creates_migrated_db_with_accounts_and_branch(self, monkeypatch):
        """الجزء الآمن للأتمتة الكاملة (CREATE DATABASE → alembic upgrade
        head → دليل حسابات + فرع) — بيتأكد إن الـmigration فعليًا اشتغلت
        ضد الـDB الجديدة (مش الـshared test DB، راجع الباج اللي
        test_dining_migration.py's _upgrade_to موثّقه وrésort_data_cli.
        cmd_rebuild_trial بيتفاداه بنفس الطريقة)."""
        import sqlalchemy as sa

        from app.resort_data_cli import cmd_rebuild_trial
        from app.resort_data_targets import resolve_target

        monkeypatch.setenv("RESORT_DATA_LOCAL_DATABASE_URL", f"{RESORT_DATA_CLI_TEST_ADMIN_URL}")
        target = resolve_target("local")

        dry = cmd_rebuild_trial(target, apply=False, confirm=None)
        assert dry["mode"] == "dry-run"
        new_db_name = dry["would_create_database"]

        try:
            expected_confirm = f"REBUILD-TRIAL local {new_db_name}"
            result = cmd_rebuild_trial(target, apply=True, confirm=expected_confirm)
            assert result["status"] == "automated_steps_complete"
            assert result["new_database"] == new_db_name
            assert len(result["manual_next_steps"]) == 4

            base_url = RESORT_DATA_CLI_TEST_ADMIN_URL.rsplit("/", 1)[0]
            new_engine = sa.create_engine(f"{base_url}/{new_db_name}")
            with new_engine.connect() as conn:
                migration_head = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
                assert migration_head is not None

                branch_row = conn.execute(
                    sa.text("SELECT code FROM branches WHERE code = 'ELK-001'")
                ).first()
                assert branch_row is not None

                account_count = conn.execute(sa.text("SELECT COUNT(*) FROM accounts")).scalar()
                assert account_count > 0
            new_engine.dispose()
        finally:
            cleanup_engine = sa.create_engine(RESORT_DATA_CLI_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT")
            with cleanup_engine.connect() as conn:
                conn.execute(sa.text(
                    f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    f"WHERE datname = '{new_db_name}' AND pid <> pg_backend_pid()"
                ))
                conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{new_db_name}"'))
            cleanup_engine.dispose()


class TestSeedJulyEndToEnd:
    def test_dry_run_leaves_zero_trace_apply_persists(self, monkeypatch, throwaway_db_url):
        """يستخدم موديول خفيف (probe) مسجَّل مؤقتًا بدل SCENARIO_MODULES
        الحقيقية الكاملة (اللي محتاجة preconditions تقيلة: غرف/أسعار/
        مينيو/مخزون) — بيثبت مسار seed-july الكامل (target resolution →
        run_seed_against_engine) شغال صح، مش تكرار لتغطية كل مولّد على
        حدة (متغطاة بالفعل في ملفات test_hist_*.py الخاصة بيها)."""
        import sqlalchemy as sa
        from sqlalchemy.orm import Session

        from app.core.kernel.models.user import User, UserRole
        from app.core.kernel.security import get_password_hash
        from app.modules.core.models import Branch
        from app.modules.hr.models import Employee
        import app.operational_history_seed as seed_module
        from app.resort_data_cli import cmd_seed_july
        from app.resort_data_targets import resolve_target

        engine = sa.create_engine(throwaway_db_url)
        _create_schema(engine)

        setup_session = Session(bind=engine)
        setup_session.add(User(
            id=1, email="cli-actor@test.invalid", password_hash=get_password_hash("x"),
            full_name="actor", role=UserRole.SUPER_ADMIN, is_active=True, two_factor_enabled=False,
        ))
        branch = Branch(name="CLI Test", name_ar="اختبار الأداة",
                         code="ELK-001", timezone="Africa/Cairo", is_active=True)
        setup_session.add(branch)
        setup_session.commit()
        # _check_preconditions يفحص الحسابات الأساسية دي بغض النظر عن أي
        # موديولات مسجَّلة فعليًا (نفس منطق dining_beach/pms_bookings).
        from app.modules.finance.models import Account
        for code, name, acc_type in [
            ("1100", "Cash", "asset"), ("2160", "VAT", "liability"),
            ("2165", "Service", "liability"), ("4100", "Room Revenue", "revenue"),
        ]:
            setup_session.add(Account(branch_id=branch.id, code=code, name=name, account_type=acc_type))
        setup_session.commit()
        setup_session.close()

        def _probe_module(db, ctx):
            from app.modules.hr import services as hr_services
            from app.modules.hr.schemas import EmployeeCreate
            hr_services.create_employee(db, EmployeeCreate(
                branch_id=ctx.branch_id, employee_code="CLI-PROBE-01", full_name="Probe",
                position="Test", basic_salary=Decimal("10000.00"), hire_date="2024-01-01",
            ))
            return {"counts": {"probes": 1}, "totals": {}}

        original_modules = seed_module.SCENARIO_MODULES
        seed_module.SCENARIO_MODULES = [
            seed_module.ScenarioModule(name="probe", generate=_probe_module),
        ]
        monkeypatch.setenv("RESORT_DATA_LOCAL_DATABASE_URL", throwaway_db_url)
        monkeypatch.setenv("RESORT_DATA_LOCAL_BRANCH_CODE", "ELK-001")
        try:
            target = resolve_target("local")

            # ── dry-run: zero trace ──
            dry_result = cmd_seed_july(
                target, period="2026-07", apply=False, confirm=None,
                validate_only_mode=False, actor_id=1,
            )
            assert dry_result["mode"] == "dry-run"
            assert dry_result["modules_run"] == ["probe"]

            verify = Session(bind=engine)
            assert verify.query(Employee).count() == 0
            verify.close()

            # ── apply: persists ──
            expected_confirm = f"SEED ELK-001/2026-07/{seed_module.DATASET_VERSION}"
            apply_result = cmd_seed_july(
                target, period="2026-07", apply=True, confirm=expected_confirm,
                validate_only_mode=False, actor_id=1,
            )
            assert apply_result["mode"] == "apply"
            assert apply_result["modules_run"] == ["probe"]

            verify = Session(bind=engine)
            assert verify.query(Employee).filter_by(employee_code="CLI-PROBE-01").count() == 1
            verify.close()

            # ── validate: reports applied ──
            validate_result = cmd_seed_july(
                target, period="2026-07", apply=False, confirm=None,
                validate_only_mode=True, actor_id=None,
            )
            assert validate_result["applied"] is True
            assert validate_result["status"] == "completed"
        finally:
            seed_module.SCENARIO_MODULES = original_modules
        engine.dispose()


class TestResetDatasetGuard:
    def test_completed_batch_refuses_deletion(self, monkeypatch, throwaway_db_url):
        import sqlalchemy as sa
        from sqlalchemy.orm import Session

        from app.core.kernel.models.user import User, UserRole
        from app.core.kernel.security import get_password_hash
        from app.modules.core.models import Branch, ImportBatch
        from app.operational_history_seed import DATASET_VERSION
        from app.resort_data_cli import cmd_reset_dataset
        from app.resort_data_targets import resolve_target

        engine = sa.create_engine(throwaway_db_url)
        _create_schema(engine)

        session = Session(bind=engine)
        session.add(User(
            id=1, email="guard-actor@test.invalid", password_hash=get_password_hash("x"),
            full_name="actor", role=UserRole.SUPER_ADMIN, is_active=True, two_factor_enabled=False,
        ))
        branch = Branch(name="Guard Test", name_ar="اختبار حماية",
                         code="ELK-001", timezone="Africa/Cairo", is_active=True)
        session.add(branch)
        session.commit()
        session.add(ImportBatch(
            branch_id=branch.id, dataset_version=DATASET_VERSION, period="2026-07",
            checksum="x", status="completed", actor="guard-actor@test.invalid",
            started_at=datetime.now(timezone.utc),
            counts=json.dumps({"pms_bookings": {}}),
        ))
        session.commit()
        session.close()

        monkeypatch.setenv("RESORT_DATA_LOCAL_DATABASE_URL", throwaway_db_url)
        target = resolve_target("local")

        result = cmd_reset_dataset(target, period="2026-07", apply=False, confirm=None)
        assert result["status"] == "refused"
        assert "posting" in result["reason"]
        engine.dispose()

    def test_failed_batch_with_partial_modules_refuses_deletion(self, monkeypatch, throwaway_db_url):
        import sqlalchemy as sa
        from sqlalchemy.orm import Session

        from app.core.kernel.models.user import User, UserRole
        from app.core.kernel.security import get_password_hash
        from app.modules.core.models import Branch, ImportBatch
        from app.operational_history_seed import DATASET_VERSION
        from app.resort_data_cli import cmd_reset_dataset
        from app.resort_data_targets import resolve_target

        engine = sa.create_engine(throwaway_db_url)
        _create_schema(engine)

        session = Session(bind=engine)
        session.add(User(
            id=1, email="guard-actor2@test.invalid", password_hash=get_password_hash("x"),
            full_name="actor", role=UserRole.SUPER_ADMIN, is_active=True, two_factor_enabled=False,
        ))
        branch = Branch(name="Guard Test 2", name_ar="اختبار حماية 2",
                         code="ELK-001", timezone="Africa/Cairo", is_active=True)
        session.add(branch)
        session.commit()
        session.add(ImportBatch(
            branch_id=branch.id, dataset_version=DATASET_VERSION, period="2026-07",
            checksum="x", status="failed", actor="guard-actor2@test.invalid",
            started_at=datetime.now(timezone.utc),
            counts=json.dumps({"pms_bookings": {"bookings_total": 38}}),
            failure_reason="simulated",
        ))
        session.commit()
        session.close()

        monkeypatch.setenv("RESORT_DATA_LOCAL_DATABASE_URL", throwaway_db_url)
        target = resolve_target("local")

        result = cmd_reset_dataset(target, period="2026-07", apply=False, confirm=None)
        assert result["status"] == "refused"
        assert "pms_bookings" in result["modules_run"]
        engine.dispose()

    def test_failed_batch_with_zero_modules_is_deletable(self, monkeypatch, throwaway_db_url):
        import sqlalchemy as sa
        from sqlalchemy.orm import Session

        from app.core.kernel.models.user import User, UserRole
        from app.core.kernel.security import get_password_hash
        from app.modules.core.models import Branch, ImportBatch
        from app.operational_history_seed import DATASET_VERSION
        from app.resort_data_cli import cmd_reset_dataset
        from app.resort_data_targets import resolve_target

        engine = sa.create_engine(throwaway_db_url)
        _create_schema(engine)

        session = Session(bind=engine)
        session.add(User(
            id=1, email="guard-actor3@test.invalid", password_hash=get_password_hash("x"),
            full_name="actor", role=UserRole.SUPER_ADMIN, is_active=True, two_factor_enabled=False,
        ))
        branch = Branch(name="Guard Test 3", name_ar="اختبار حماية 3",
                         code="ELK-001", timezone="Africa/Cairo", is_active=True)
        session.add(branch)
        session.commit()
        batch = ImportBatch(
            branch_id=branch.id, dataset_version=DATASET_VERSION, period="2026-07",
            checksum="x", status="failed", actor="guard-actor3@test.invalid",
            started_at=datetime.now(timezone.utc),
            counts=None, failure_reason="crashed before first module committed anything",
        )
        session.add(batch)
        session.commit()
        batch_id = batch.id
        session.close()

        monkeypatch.setenv("RESORT_DATA_LOCAL_DATABASE_URL", throwaway_db_url)
        target = resolve_target("local")

        dry = cmd_reset_dataset(target, period="2026-07", apply=False, confirm=None)
        assert dry["status"] == "dry-run"
        assert dry["batch_id"] == batch_id

        expected_confirm = f"RESET-DATASET local ELK-001/2026-07/{DATASET_VERSION}"
        applied = cmd_reset_dataset(target, period="2026-07", apply=True, confirm=expected_confirm)
        assert applied["status"] == "deleted"

        verify = Session(bind=engine)
        assert verify.query(ImportBatch).filter_by(id=batch_id).count() == 0
        verify.close()
        engine.dispose()

    def test_wrong_confirmation_phrase_rejected(self, monkeypatch, throwaway_db_url):
        import sqlalchemy as sa
        from sqlalchemy.orm import Session

        from app.core.kernel.models.user import User, UserRole
        from app.core.kernel.security import get_password_hash
        from app.modules.core.models import Branch, ImportBatch
        from app.operational_history_seed import DATASET_VERSION
        from app.resort_data_cli import ResetToolError, cmd_reset_dataset
        from app.resort_data_targets import resolve_target

        engine = sa.create_engine(throwaway_db_url)
        _create_schema(engine)

        session = Session(bind=engine)
        session.add(User(
            id=1, email="guard-actor4@test.invalid", password_hash=get_password_hash("x"),
            full_name="actor", role=UserRole.SUPER_ADMIN, is_active=True, two_factor_enabled=False,
        ))
        branch = Branch(name="Guard Test 4", name_ar="اختبار حماية 4",
                         code="ELK-001", timezone="Africa/Cairo", is_active=True)
        session.add(branch)
        session.commit()
        session.add(ImportBatch(
            branch_id=branch.id, dataset_version=DATASET_VERSION, period="2026-07",
            checksum="x", status="failed", actor="guard-actor4@test.invalid",
            started_at=datetime.now(timezone.utc),
            counts=None, failure_reason="crashed early",
        ))
        session.commit()
        session.close()

        monkeypatch.setenv("RESORT_DATA_LOCAL_DATABASE_URL", throwaway_db_url)
        target = resolve_target("local")

        with pytest.raises(ResetToolError):
            cmd_reset_dataset(target, period="2026-07", apply=True, confirm="wrong phrase")
        engine.dispose()
