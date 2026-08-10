"""RESET-01 — أداة إدارة موحّدة للتصفير وإعادة البداية النظيفة
(OPS-DATA-02 §9.4).

    ./scripts/resort-data backup        --target local|vps
    ./scripts/resort-data seed-july     --target local|vps --period 2026-07 [--apply --confirm ...] [--validate-only]
    ./scripts/resort-data validate      --target local|vps --period 2026-07
    ./scripts/resort-data reset-dataset --target local|vps --period 2026-07 [--apply --confirm ...]
    ./scripts/resort-data rebuild-trial --target local|vps [--apply --confirm ...]

العقد الإلزامي المطبَّق هنا فعليًا (§9.4):
- كل الأوامر dry-run افتراضيًا؛ الاتصال بيتقرأ من env بس (raise app.
  resort_data_targets.resolve_target — صفر DB URL/password كـCLI argument
  أو في أي log/print).
- قبل أي --apply: fingerprint حقيقي (host/database/instance oid/branch/
  migration head/row counts) بيتطبع، وعبارة التأكيد لازم تتضمنه بالظبط.
- `reset-dataset`: batch وصل لـposting (completed) يرفض الحذف نهائيًا —
  الطريق الوحيد restore من backup. batch فشل قبل أي posting (modules_run
  فاضية) بس هو المؤهّل للحذف الآلي المحدود (صف ImportBatch نفسه بس).
- `rebuild-trial`: بايبلاين حقيقي (backup→اختبار استعادة→DB جديدة→alembic)
  لحد ما يوصل لخطوات محتاجة actor بشري حقيقي بالتصميم — bootstrap admin +
  إنشاء الفرع الأول تفاعليان عمدًا (app.admin_bootstrap.create/init-first-
  branch، نفس نمط scripts/vps-init-first-branch.sh الحقيقي المُثبت على
  VPS بالظبط — "لا أسرار في args/env"، وbootstrap_first_branch محتاج actor
  موجود بالفعل)، وبالتبعية دليل حسابات/غرف/أسعار/July seed كلهم محتاجين
  نفس الـactor ده، والتحويل الذري النهائي — بيوقف هناك بوضوح ويطبع الخطوات
  المتبقية، مش أتمتة كاملة بلا مراجعة بشرية.
- vps target: مفيش أي تنفيذ حقيقي ضد سيرفر بعيد في الأداة دي — backup/
  rebuild-trial لـvps بيرفضوا صراحةً ويوجّهوا المشغّل لتنفيذ SSH يدوي.
  قرار أمان متعمد: الأداة دي معمولة/متأكد منها بس ضد PostgreSQL محلي/
  معزول، وميعملش أي اتصال SSH لسيرفر حقيقي من غير مراجعة بشرية مباشرة.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from app.resort_data_targets import (
    TargetConfig,
    TargetResolutionError,
    build_confirmation_phrase,
    compute_fingerprint,
    resolve_target,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_BACKEND_DIR = _REPO_ROOT / "backend"


class ResetToolError(RuntimeError):
    pass


def _print(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))


def _require_confirm(command: str, target: TargetConfig, confirm: Optional[str]) -> dict:
    """يطبع الـfingerprint ويتحقق من عبارة التأكيد قبل أي --apply — العقد
    اللي §9.4 بيفرضه صراحةً ("قبل --apply تعرض host/database/schema...
    وتاخد confirmation phrase يضم هذه القيم")."""
    fingerprint = compute_fingerprint(target.database_url, target.branch_code)
    expected = build_confirmation_phrase(command, target, fingerprint)
    if confirm != expected:
        raise ResetToolError(
            f"--apply requires --confirm matching this target's live fingerprint exactly.\n"
            f"Expected: {expected!r}\n"
            f"Got:      {confirm!r}\n"
            f"Fingerprint: {json.dumps(fingerprint, sort_keys=True, default=str)}"
        )
    return fingerprint


# ── backup ───────────────────────────────────────────────────────────

def cmd_backup(target: TargetConfig, *, apply: bool) -> dict:
    script = _REPO_ROOT / "scripts" / "backup_db.sh"
    if target.name != "local":
        raise ResetToolError(
            f"backup for target={target.name!r} is not implemented in this tool — "
            "this tool never executes commands against a remote host. Run "
            "scripts/backup_db.sh manually via SSH on that host, or configure a "
            "dedicated CI/ops job with real SSH credentials outside this tool."
        )
    if not apply:
        return {"mode": "dry-run", "target": target.name, "would_run": str(script)}

    result = subprocess.run(
        ["bash", str(script)], cwd=str(_REPO_ROOT), capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise ResetToolError(f"backup_db.sh failed (exit {result.returncode}): {result.stderr[-2000:]}")

    dump_line = next((ln for ln in result.stdout.splitlines() if "Backup complete" in ln), None)
    dump_file_match = re.search(r"Backup complete:\s*(\S+\.dump)", dump_line or "")
    dump_file = dump_file_match.group(1) if dump_file_match else None
    return {
        "mode": "apply", "target": target.name, "stdout_tail": result.stdout[-500:],
        "summary": dump_line, "dump_file": dump_file,
    }


# ── seed-july / validate ────────────────────────────────────────────

def cmd_seed_july(
    target: TargetConfig, *, period: str, apply: bool, confirm: Optional[str],
    validate_only_mode: bool, actor_id: Optional[int],
    period_end_day: Optional[int] = None,
) -> dict:
    import sqlalchemy as sa

    from app.operational_history_seed import (
        confirmation_phrase, run_seed_against_engine, validate_only as seed_validate_only,
    )

    engine = sa.create_engine(target.database_url)
    try:
        if validate_only_mode:
            from sqlalchemy.orm import Session
            with Session(bind=engine) as db:
                report = seed_validate_only(db, branch_code=target.branch_code, period=period)
                db.rollback()
                return report

        expected = confirmation_phrase(target.branch_code, period)
        if apply and confirm != expected:
            raise ResetToolError(f"--apply requires --confirm {expected!r}")

        result = run_seed_against_engine(
            engine, branch_code=target.branch_code, period=period, apply=apply, actor_id=actor_id,
            period_end_day=period_end_day,
        )
        return {
            "mode": "apply" if apply else "dry-run",
            "target": target.name,
            "branch_code": target.branch_code,
            "period": period,
            "already_applied": result.already_applied,
            "modules_run": result.modules_run,
            "counts": result.counts,
            "totals": result.totals,
        }
    finally:
        engine.dispose()


def cmd_validate(target: TargetConfig, *, period: str) -> dict:
    return cmd_seed_july(
        target, period=period, apply=False, confirm=None, validate_only_mode=True, actor_id=None,
    )


# ── reset-dataset ────────────────────────────────────────────────────

def cmd_reset_dataset(target: TargetConfig, *, period: str, apply: bool, confirm: Optional[str]) -> dict:
    """§9.4's guard: batch وصل لـposting (completed — كل مولّد HIST-01
    بيرحّل قيود حقيقية فعليًا، فأي batch completed معناه فيه posted
    journals بالتعريف) يرفض الحذف نهائيًا. batch فشل قبل أي posting
    (modules_run فاضية فعليًا في الـmanifest — راجع run_modules's تحديث
    تدريجي) هو الوحيد المؤهّل للحذف الآلي، ومحدود بصف ImportBatch نفسه بس
    (مفيش صف تاني اتكتب أصلاً لو أول موديول عمره ما خلص)."""
    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    from app.modules.core.models import ImportBatch
    from app.operational_history_seed import DATASET_VERSION

    engine = sa.create_engine(target.database_url)
    try:
        with Session(bind=engine) as db:
            from app.modules.core.models import Branch
            branch = db.query(Branch).filter(Branch.code == target.branch_code).first()
            if not branch:
                return {"status": "no_branch", "branch_code": target.branch_code}

            batch = (
                db.query(ImportBatch)
                .filter(
                    ImportBatch.branch_id == branch.id,
                    ImportBatch.dataset_version == DATASET_VERSION,
                    ImportBatch.period == period,
                )
                .first()
            )
            if not batch:
                return {"status": "no_batch", "branch_code": target.branch_code, "period": period}

            if batch.status == "completed":
                return {
                    "status": "refused",
                    "batch_id": batch.id,
                    "batch_status": batch.status,
                    "reason": (
                        "batch reached posting (completed batches always have posted "
                        "journal entries) — automated row deletion is never permitted here. "
                        "Restore the pre-apply backup instead (§9.3/§9.4)."
                    ),
                }

            modules_run = list(json.loads(batch.counts or "{}").keys())
            if modules_run:
                return {
                    "status": "refused",
                    "batch_id": batch.id,
                    "batch_status": batch.status,
                    "modules_run": modules_run,
                    "reason": (
                        f"batch partially applied — {modules_run} already committed real data "
                        "before it failed. Automated row deletion is not supported for a "
                        "partial application (no row-level tracking to scope a safe delete). "
                        "Restore the pre-apply backup instead."
                    ),
                }

            if not apply:
                return {
                    "status": "dry-run",
                    "batch_id": batch.id,
                    "batch_status": batch.status,
                    "would_delete": "ImportBatch row only (no modules ever committed data)",
                }

            expected = f"RESET-DATASET {target.name} {target.branch_code}/{period}/{DATASET_VERSION}"
            if confirm != expected:
                raise ResetToolError(f"--apply requires --confirm {expected!r}")

            db.delete(batch)
            db.commit()
            return {"status": "deleted", "batch_id": batch.id}
    finally:
        engine.dispose()


# ── rebuild-trial ────────────────────────────────────────────────────

def cmd_rebuild_trial(target: TargetConfig, *, apply: bool, confirm: Optional[str]) -> dict:
    """بايبلاين حقيقي لحد الخطوتين المحتاجين تدخّل بشري إجباري بالتصميم
    (bootstrap admin تفاعلي — app.admin_bootstrap متعمد ميقبلش أسرار في
    args/env، والتحويل الذري النهائي لقاعدة الإنتاج). الأداة دي بتوقف
    هناك بوضوح وبتطبع الخطوات المتبقية، مش أتمتة كاملة بلا مراجعة بشرية —
    قرار أمان متعمد مش قصور، مطابق لسلوك admin_bootstrap نفسه."""
    if not target.rebuild_trial_enabled:
        raise ResetToolError(
            f"rebuild-trial is disabled for target={target.name!r} "
            f"(RESORT_DATA_{target.name.upper()}_REBUILD_TRIAL_ENABLED=false) — "
            "per §9.4, this must stay disabled after a VPS target has graduated from "
            "Trial to real legal operation, and only be re-enabled with fresh, "
            "independent approval plus a maintenance window."
        )
    if target.name != "local":
        raise ResetToolError(
            f"rebuild-trial for target={target.name!r} is not implemented in this tool — "
            "this tool never executes destructive operations against a remote host."
        )

    import uuid
    from datetime import date

    import sqlalchemy as sa

    # ⚠️ باج حقيقي اتكشف وقت كتابة test_rebuild_trial_apply_creates_
    # migrated_db_with_accounts_and_branch: اسم عشوائي (uuid4) هنا كان
    # معناه dry-run بيقترح اسم، وبعدين --apply الحقيقي بيولّد اسم عشوائي
    # **تاني مختلف** داخليًا — عبارة التأكيد المتوقعة (اللي بتضم الاسم)
    # كانت مستحيل تتطابق أبدًا، لأن المشغّل مالوش أي طريقة يعرف مقدمًا
    # الاسم اللي --apply هيستخدمه فعليًا. الاسم لازم يكون deterministic
    # (نفس المدخلات = نفس الاسم) عشان dry-run's اقتراح يطابق --apply's
    # نداء الفعلي بالظبط — نفس فلسفة confirmation_phrase الحتمية في باقي
    # الأداة كلها.
    new_db_name = f"resort_os_trial_{target.branch_code.lower().replace('-', '')}_{date.today():%Y%m%d}"
    admin_url_base = target.database_url.rsplit("/", 1)[0]
    new_db_url = f"{admin_url_base}/{new_db_name}"

    if not apply:
        return {
            "mode": "dry-run", "target": target.name,
            "would_create_database": new_db_name,
            "steps": [
                "1. backup current database",
                "2. test-restore that backup into a throwaway database (integrity check)",
                f"3. CREATE DATABASE {new_db_name}",
                "4. alembic upgrade head against the new database",
                "5. STOP — print manual next steps (admin bootstrap create + init-first-branch, "
                "chart of accounts, room inventory/pricing, HIST-01 July seed, validation, and "
                "the atomic cutover all require a human actor and are intentionally not "
                "automated here — see cmd_rebuild_trial's docstring)",
            ],
        }

    expected = f"REBUILD-TRIAL {target.name} {new_db_name}"
    if confirm != expected:
        raise ResetToolError(f"--apply requires --confirm {expected!r}")

    # ── الخطوتين 1-2 (backup + اختبار استعادة) — لازم يتنفذوا فعليًا هنا،
    # مش بس يتوصفوا في dry-run — وإلا الـpreview بيكدب على اللي --apply
    # بيعمله فعليًا. بيرجّعوا نتيجة حقيقية (dump_file/restore_verified)
    # جوه manual_next_steps's سياق، مش مجرد نص. ─────────────────────────
    backup_result = cmd_backup(target, apply=True)
    dump_file = backup_result.get("dump_file")
    if not dump_file:
        raise ResetToolError(
            f"backup succeeded but the dump file path could not be parsed from its output "
            f"— refusing to proceed without a verifiable backup: {backup_result.get('summary')!r}"
        )

    restore_test_db = f"resort_os_backup_verify_{uuid.uuid4().hex[:8]}"
    restore_script = _REPO_ROOT / "scripts" / "restore_db.sh"
    restore_result = subprocess.run(
        ["bash", str(restore_script), dump_file, restore_test_db],
        cwd=str(_REPO_ROOT), capture_output=True, text=True, check=False,
    )
    verify_engine = sa.create_engine(admin_url_base + f"/{restore_test_db}")
    try:
        with verify_engine.connect() as conn:
            table_count = conn.execute(
                sa.text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'")
            ).scalar()
    finally:
        verify_engine.dispose()
    cleanup_engine = sa.create_engine(admin_url_base + "/postgres", isolation_level="AUTOCOMMIT")
    try:
        with cleanup_engine.connect() as conn:
            conn.execute(sa.text(
                f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{restore_test_db}' AND pid <> pg_backend_pid()"
            ))
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{restore_test_db}"'))
    finally:
        cleanup_engine.dispose()
    if restore_result.returncode != 0 or not table_count:
        raise ResetToolError(
            f"backup integrity check failed — restore_db.sh exit={restore_result.returncode}, "
            f"table_count={table_count}: {restore_result.stderr[-2000:]}"
        )

    admin_engine = sa.create_engine(admin_url_base + "/postgres", isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            conn.execute(sa.text(f'CREATE DATABASE "{new_db_name}"'))
    finally:
        admin_engine.dispose()

    # ⚠️ alembic/env.py بيعمل config.set_main_option("sqlalchemy.url",
    # settings.DATABASE_URL) من غير شرط — بتغلب على أي قيمة نحطها على
    # Config object هنا، لأن env.py بيتنفذ كـscript من جديد مع كل نداء
    # alembic (raجع util.load_python_file) وبيقرا app.core.config.
    # settings الحية كل مرة. نفس الباج بالظبط اللي test_dining_migration.
    # py's _upgrade_to موثّقه — لازم نغيّر settings.DATABASE_URL نفسها
    # مؤقتًا، مش بس الـConfig object.
    from alembic import command as alembic_command
    from alembic.config import Config

    from app.core.config import settings as _app_settings

    alembic_cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", new_db_url)

    _original_database_url = _app_settings.DATABASE_URL
    _app_settings.DATABASE_URL = new_db_url
    try:
        alembic_command.upgrade(alembic_cfg, "head")
    finally:
        _app_settings.DATABASE_URL = _original_database_url

    # ⚠️ قرار تصميمي اتصحّح قبل أول تشغيل حقيقي: النسخة الأولى من الدالة
    # دي كانت بتنشئ Branch مباشرة هنا (SQL/ORM خام) — بيتعارض مع
    # app.admin_bootstrap.bootstrap_first_branch الحقيقية (اللي
    # scripts/vps-init-first-branch.sh بيستخدمها فعليًا على VPS) لو
    # المشغّل بعدين شغّل admin_bootstrap init-first-branch بأي name/
    # name_ar مختلف عن اللي اتقفل هنا حرفيًا — bootstrap_first_branch
    # بترفض صراحةً ("existing first branch conflicts with the requested
    # values") لو فيه فرع واحد موجود بكود مطابق لكن باقي الحقول مختلفة.
    # الحل الصح: منسيبش أي فرع هنا خالص — admin_bootstrap init-first-
    # branch (خطوة يدوية تالية، مطابقة تمامًا لنمط VPS الحقيقي المُثبت)
    # هي المسؤولة الوحيدة عن إنشاء الفرع الأول، ودليل الحسابات بيتزرع
    # بعدها (idempotent، مش محتاج فرع معيّن بالاسم).
    #
    # ── متعمد: الأداة بتوقف هنا. bootstrap admin + إنشاء الفرع الأول
    # كلاهما تفاعلي عمدًا (app.admin_bootstrap: "لا أسرار في args/env"،
    # وbootstrap_first_branch محتاج actor موجود بالفعل) — وبالتبعية غرف/
    # أسعار/HIST-01 July seed كلهم محتاجين نفس الـactor ده. أتمتة كاملة
    # هنا معناها إما نتخطى قيد الأمان ده أو نخترع actor وهمي — الاتنين
    # مرفوضين. الخطوات المتبقية دي محتاجة إنسان عند الكونسول بالتصميم.
    return {
        "mode": "apply", "target": target.name, "new_database": new_db_name,
        "status": "automated_steps_complete",
        "manual_next_steps": [
            f"1. DATABASE_URL={new_db_url} python -m app.admin_bootstrap create "
            "--email <email> --full-name <name> (interactive — no secrets in args/env; "
            "prints a one-time temp password + 2FA enrollment token, copy immediately).",
            f"2. DATABASE_URL={new_db_url} python -m app.admin_bootstrap init-first-branch "
            f"--email <same email> --code {target.branch_code} --name <branch name> "
            "(interactive — creates the first branch, binds the admin, seeds nothing else).",
            "3. Seed the chart of accounts (app.seed._seed_chart_of_accounts — idempotent, "
            "finds the branch on its own) then room inventory + approved pricing "
            "(app.real_room_inventory.replace_room_inventory + "
            "app.approved_room_pricing.activate_room_pricing) with that admin's actor id.",
            f"4. Run: python -m app.operational_history_seed --branch-code {target.branch_code} "
            "--period 2026-07 --apply --confirm '...' against the new database.",
            "5. Validate, then perform the atomic cutover yourself "
            "(update DATABASE_URL, restart services) — this tool does not swap a live "
            "app's database connection out from under it unattended.",
        ],
    }


# ── CLI ──────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="resort-data", description="RESET-01 unified data-lifecycle tool")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("backup", "seed-july", "validate", "reset-dataset", "rebuild-trial"):
        p = sub.add_parser(name)
        p.add_argument("--target", required=True, choices=["local", "vps"])
        p.add_argument("--apply", action="store_true")
        p.add_argument("--confirm")
        if name in ("seed-july", "validate", "reset-dataset"):
            p.add_argument("--period", required=True, help="YYYY-MM")
        if name == "seed-july":
            p.add_argument("--validate-only", action="store_true")
            p.add_argument("--actor-id", type=int)
            p.add_argument(
                "--end-day", type=int, default=None,
                help=(
                    "آخر يوم في الشهر يتولّد له نشاط (افتراضيًا آخر يوم "
                    "تقويمي). لازم لأي فرع حي بيقفل لياليه أوتوماتيكيًا "
                    "كل يوم فعلي — مفيش رجوع نملأ يوم اتقفل بالفعل."
                ),
            )

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        # ⚠️ باج حقيقي اتكشف واتصلح وقت أول تشغيلة حقيقية (Phase 8 Local
        # apply): جداول زي bookings.customer_id → crm_customers محتاجة كل
        # الـmodels متسجّلة في SQLAlchemy's mapper registry قبل أي ORM
        # query/flush — بيحصل تلقائيًا وقت تشغيل الـFastAPI app الحقيقي
        # (app.main بيستورد كل الموديولات)، لكن الأداة دي standalone،
        # مبتعديش على app.main أبدًا. نفس المصدر الجاهز الوحيد الموجود:
        # app.seed._import_all_models().
        from app.seed import _import_all_models  # noqa: PLC0415
        _import_all_models()

        target = resolve_target(args.target)

        if args.command == "backup":
            result = cmd_backup(target, apply=args.apply)
        elif args.command == "seed-july":
            result = cmd_seed_july(
                target, period=args.period, apply=args.apply, confirm=args.confirm,
                validate_only_mode=args.validate_only, actor_id=args.actor_id,
                period_end_day=args.end_day,
            )
        elif args.command == "validate":
            result = cmd_validate(target, period=args.period)
        elif args.command == "reset-dataset":
            result = cmd_reset_dataset(target, period=args.period, apply=args.apply, confirm=args.confirm)
        elif args.command == "rebuild-trial":
            result = cmd_rebuild_trial(target, apply=args.apply, confirm=args.confirm)
        else:
            raise ResetToolError(f"unknown command {args.command!r}")

        _print(result)
        return 0
    except (ResetToolError, TargetResolutionError) as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
