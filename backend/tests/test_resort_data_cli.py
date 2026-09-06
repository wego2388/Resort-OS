"""
tests/test_resort_data_cli.py
Postgres-only verification of RESET-01 (app/resort_data_cli.py +
app/resort_data_targets.py, OPS-DATA-02 §9.4).

Why this lives outside the normal `pytest tests/` SQLite run: this tool
only ever targets real Postgres (real advisory locks, real CREATE DATABASE
for rebuild-trial).

Usage — set an admin Postgres DSN before running:

    RESORT_DATA_CLI_TEST_ADMIN_URL=postgresql+psycopg://postgres:resort_dev_pass@localhost:5436/postgres \\
        pytest tests/test_resort_data_cli.py -v

Skips automatically when that env var is unset — the default, zero effect
on the normal SQLite-based suite.
"""
from __future__ import annotations

import os
import uuid

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

    def test_rebuild_trial_apply_creates_migrated_empty_db(self, monkeypatch):
        """الجزء الآمن للأتمتة الكاملة (CREATE DATABASE → alembic upgrade
        head) — بيتأكد إن الـmigration فعليًا اشتغلت ضد الـDB الجديدة
        (مش الـshared test DB، راجع الباج اللي test_dining_migration.py's
        _upgrade_to موثّقه وresort_data_cli.cmd_rebuild_trial بيتفاداه
        بنفس الطريقة). مفيش فرع أو حسابات هنا عمدًا — دي بقت مسؤولية
        admin_bootstrap init-first-branch اليدوية (راجع الباج التاني اللي
        اتصلح: إنشاء فرع مباشر هنا كان بيتعارض مع bootstrap_first_branch
        الحقيقية لو المشغّل بعدين استخدم اسم/name_ar مختلف)."""
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
            assert len(result["manual_next_steps"]) == 5
            assert "init-first-branch" in result["manual_next_steps"][1]

            base_url = RESORT_DATA_CLI_TEST_ADMIN_URL.rsplit("/", 1)[0]
            new_engine = sa.create_engine(f"{base_url}/{new_db_name}")
            with new_engine.connect() as conn:
                migration_head = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
                assert migration_head is not None

                branch_count = conn.execute(sa.text("SELECT COUNT(*) FROM branches")).scalar()
                assert branch_count == 0  # لسه معمولش init-first-branch
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


