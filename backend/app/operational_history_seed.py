"""HIST-01 — محرك استيراد البيانات التشغيلية التاريخية (OPS-DATA-02 §9).

هيكل الأداة (dry-run افتراضي، PostgreSQL advisory lock، ImportBatch
manifest، نفس نمط app.approved_room_pricing بالظبط) — مسجّل حاليًا **بلا
أي مولّد بيانات فعلي** (SCENARIO_MODULES فاضية عمدًا). كل جزء لاحق من خطة
يوليو 2026 (§10: PMS/Hub/Dining/Beach/Leasing/Timeshare/HR/Inventory/
Assets/GL opening balance) هيتسجّل هنا كدفعة منفصلة قابلة للمراجعة، مش
commit واحد ضخم لكل حاجة مرة واحدة (OPS-DATA-02 §12: "لا تنفذ المراحل
كلها في commit واحد. كل migration أو تغيير عقد API أو importer له commit
ومراجعة منفصلان").

الاستخدام:
    python -m app.operational_history_seed --branch-code ELK-001 --period 2026-07
    python -m app.operational_history_seed --branch-code ELK-001 --period 2026-07 \\
        --apply --confirm "SEED ELK-001/2026-07/july-2026-v1"
    python -m app.operational_history_seed --branch-code ELK-001 --period 2026-07 --validate-only

الخصائص الإلزامية (§9.1) المطبَّقة هنا فعليًا:
- dry-run افتراضي؛ `--apply` يحتاج confirmation phrase يتضمن branch/period/version.
- dataset version + SHA256 checksum لمحتوى الـ manifest المسجَّل.
- PostgreSQL advisory lock (نفس نمط approved_room_pricing.py).
- ImportBatch (actor/counts/totals/started/completed) — منع rerun حتى بعد
  crash (batch لسه status="running" بيرفض أي محاولة تانية، محتاج تدخّل يدوي).
- فحص preconditions أساسي (دليل الحسابات) — كل مولّد لاحق هيضيف فحوصه
  الخاصة (غرف/أسعار/مينيو/مخزون/ممثلين) وقت ما يتسجّل في SCENARIO_MODULES.
- مفيش أي PII أو أسرار في الـ output — بيانات الفرع/العداد/الإجمالي بس.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.resort_os.clock import scenario_clock

DATASET_VERSION = "july-2026-v1"
_ADVISORY_LOCK_KEY = 4_502_026_090_100


@dataclass
class ScenarioContext:
    branch_id: int
    period_year: int
    period_month: int
    tz_name: str


@dataclass
class ScenarioModule:
    """مولّد بيانات واحد قابل للتسجيل (زي "pms_bookings" أو "dining_orders").
    `generate(db, ctx)` بيرجع {"counts": {...}, "totals": {...}} لتقرير الـ
    manifest — مفروض يعمل flush بس (مش commit)، الـ CLI هو مالك الـ
    transaction الواحدة الشاملة."""
    name: str
    generate: Callable[[Session, ScenarioContext], dict]


def _gl_opening_balance_module(db: Session, ctx: ScenarioContext) -> dict:
    from app.hist_gl_opening_balance import generate as generate_gl_opening_balance  # noqa: PLC0415

    return generate_gl_opening_balance(db, ctx)


def _pms_bookings_module(db: Session, ctx: ScenarioContext) -> dict:
    from app.hist_pms_bookings import generate as generate_pms_bookings  # noqa: PLC0415

    return generate_pms_bookings(db, ctx)


def _leasing_module(db: Session, ctx: ScenarioContext) -> dict:
    from app.hist_leasing import generate as generate_leasing  # noqa: PLC0415

    return generate_leasing(db, ctx)


def _timeshare_module(db: Session, ctx: ScenarioContext) -> dict:
    from app.hist_timeshare import generate as generate_timeshare  # noqa: PLC0415

    return generate_timeshare(db, ctx)


def _dining_beach_module(db: Session, ctx: ScenarioContext) -> dict:
    from app.hist_dining_beach import generate as generate_dining_beach  # noqa: PLC0415

    return generate_dining_beach(db, ctx)


def _hr_module(db: Session, ctx: ScenarioContext) -> dict:
    from app.hist_hr import generate as generate_hr  # noqa: PLC0415

    return generate_hr(db, ctx)


def _hub_module(db: Session, ctx: ScenarioContext) -> dict:
    from app.hist_hub import generate as generate_hub  # noqa: PLC0415

    return generate_hub(db, ctx)


def _inventory_module(db: Session, ctx: ScenarioContext) -> dict:
    from app.hist_inventory import generate as generate_inventory  # noqa: PLC0415

    return generate_inventory(db, ctx)


def _fixed_assets_module(db: Session, ctx: ScenarioContext) -> dict:
    from app.hist_fixed_assets import generate as generate_fixed_assets  # noqa: PLC0415

    return generate_fixed_assets(db, ctx)


SCENARIO_MODULES: list[ScenarioModule] = [
    ScenarioModule(name="gl_opening_balance", generate=_gl_opening_balance_module),
    ScenarioModule(name="pms_bookings", generate=_pms_bookings_module),
    ScenarioModule(name="leasing", generate=_leasing_module),
    ScenarioModule(name="timeshare", generate=_timeshare_module),
    ScenarioModule(name="dining_beach", generate=_dining_beach_module),
    ScenarioModule(name="hub", generate=_hub_module),
    ScenarioModule(name="hr", generate=_hr_module),
    ScenarioModule(name="inventory", generate=_inventory_module),
    ScenarioModule(name="fixed_assets", generate=_fixed_assets_module),
]
# ⚠️ باقي الموديولات (Inventory/Assets/GL opening balance) هتتسجّل هنا
# واحدة واحدة، كل واحدة دفعة منفصلة. dining_beach مسجَّل بعد pms_bookings
# عمدًا (مش قبله) — عشان سيناريو "الدفع على حساب الغرفة" يقدر يلاقي فوليو
# مفتوح حقيقي لو الاتنين اشتغلوا في نفس الدفعة. hub مسجَّل بعد pms_bookings
# عمدًا برضو — راجع hist_hub.py's docstring: packer بتاع pms_bookings
# بيستخدم occupied dict محلي فاضي من الأول (مش بيقرأ الداتابيز)، فلازم
# يخلص حجزه الأول قبل ما Hub يحجز أي غرفة حقيقية.


@dataclass
class SeedResult:
    branch_code: str
    period: str
    version: str
    mode: str
    already_applied: bool
    modules_run: list[str]
    counts: dict
    totals: dict


def _acquire_lock(db: Session) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": _ADVISORY_LOCK_KEY})


def _resolve_branch(db: Session, branch_code: str):
    from app.modules.core.models import Branch  # noqa: PLC0415

    branch = db.query(Branch).filter(Branch.code == branch_code).first()
    if not branch:
        raise RuntimeError(f"Branch {branch_code!r} not found")
    if not branch.is_active:
        raise RuntimeError(f"Branch {branch_code!r} is not active")
    return branch


def _resolve_actor(db: Session, actor_id: Optional[int]) -> str:
    from app.core.kernel.models.user import User  # noqa: PLC0415

    query = db.query(User).filter(User.is_active.is_(True))
    if actor_id is not None:
        query = query.filter(User.id == actor_id)
    actors = [u for u in query.all() if getattr(u.role, "value", u.role) == "super_admin"]
    if len(actors) != 1:
        raise RuntimeError("Resolve exactly one active super_admin actor, or pass --actor-id")
    return actors[0].email


def _check_preconditions(db: Session, branch_id: int) -> list[str]:
    """يرجّع قايمة مشاكل تمنع الاستيراد — فاضية يعني كله جاهز. كل مولّد
    مسجَّل في SCENARIO_MODULES بيضيف فحوصه الخاصة هنا وقت ما يتسجّل (فحص
    مبكر وواضح، إضافةً لأي تحقق أدق داخل المولّد نفسه)."""
    from app.modules.finance.crud import get_account_by_code  # noqa: PLC0415

    problems = []
    for code in ("1100", "2160", "2165", "4100"):
        if not get_account_by_code(db, branch_id, code):
            problems.append(f"missing required account {code} for branch {branch_id}")

    if any(m.name == "pms_bookings" for m in SCENARIO_MODULES):
        from app.modules.pms.models import Room, RoomBundle, RoomType  # noqa: PLC0415

        room_count = (
            db.query(Room).join(RoomType, Room.room_type_id == RoomType.id)
            .filter(Room.branch_id == branch_id).count()
        )
        bundle_count = (
            db.query(RoomBundle)
            .filter(RoomBundle.branch_id == branch_id, RoomBundle.is_active.is_(True))
            .count()
        )
        if room_count != 14:
            problems.append(f"pms_bookings requires exactly 14 rooms; found {room_count}")
        if bundle_count != 5:
            problems.append(f"pms_bookings requires exactly 5 active room bundles; found {bundle_count}")

    if any(m.name == "leasing" for m in SCENARIO_MODULES):
        for code in ("1110", "1260", "2150", "4500"):
            if not get_account_by_code(db, branch_id, code):
                problems.append(f"leasing requires account {code} for branch {branch_id}")

    if any(m.name == "timeshare" for m in SCENARIO_MODULES):
        for code in ("4600", "4650"):
            if not get_account_by_code(db, branch_id, code):
                problems.append(f"timeshare requires account {code} for branch {branch_id}")

    if any(m.name == "dining_beach" for m in SCENARIO_MODULES):
        for code in ("1100", "1110", "2160", "2165", "4200", "4300", "4400"):
            if not get_account_by_code(db, branch_id, code):
                problems.append(f"dining_beach requires account {code} for branch {branch_id}")

    if any(m.name == "hr" for m in SCENARIO_MODULES):
        for code in ("5100", "2100", "2110", "2120", "1180"):
            if not get_account_by_code(db, branch_id, code):
                problems.append(f"hr requires account {code} for branch {branch_id}")

    if any(m.name == "gl_opening_balance" for m in SCENARIO_MODULES):
        for code in (
            "1100", "1110", "1150", "1170", "1200", "1210", "1500", "1510", "1515",
            "1520", "1530", "1540", "1590", "2200", "2160", "2170", "2150", "2310",
            "2180", "3100", "3200",
        ):
            if not get_account_by_code(db, branch_id, code):
                problems.append(f"gl_opening_balance requires account {code} for branch {branch_id}")

    return problems


def _existing_batch(db: Session, branch_id: int, period: str):
    from app.modules.core.models import ImportBatch  # noqa: PLC0415

    return (
        db.query(ImportBatch)
        .filter(
            ImportBatch.branch_id == branch_id,
            ImportBatch.dataset_version == DATASET_VERSION,
            ImportBatch.period == period,
        )
        .first()
    )


def confirmation_phrase(branch_code: str, period: str) -> str:
    return f"SEED {branch_code}/{period}/{DATASET_VERSION}"


def run_seed(
    db: Session, *, branch_code: str, period: str, actor_id: Optional[int] = None,
) -> SeedResult:
    """يشتغل جوه transaction المستدعي (staged بس، مش commit) — الـ caller
    (main تحت) هو اللي بيقرر commit ولا rollback حسب --apply."""
    try:
        year_str, month_str = period.split("-")
        period_year, period_month = int(year_str), int(month_str)
    except ValueError as exc:
        raise RuntimeError(f"--period must be YYYY-MM, got {period!r}") from exc

    _acquire_lock(db)
    branch = _resolve_branch(db, branch_code)
    actor_email = _resolve_actor(db, actor_id)

    existing = _existing_batch(db, branch.id, period)
    if existing and existing.status == "completed":
        return SeedResult(
            branch_code, period, DATASET_VERSION, "apply", True,
            [], json.loads(existing.counts or "{}"), json.loads(existing.totals or "{}"),
        )
    if existing and existing.status == "running":
        raise RuntimeError(
            f"Import batch {existing.id} for {branch_code}/{period} is still 'running' — "
            "likely crashed mid-run. Investigate manually before re-running (no auto-resume)."
        )

    problems = _check_preconditions(db, branch.id)
    if problems:
        raise RuntimeError("Preconditions failed: " + "; ".join(problems))

    from app.modules.core.models import ImportBatch  # noqa: PLC0415

    manifest_source = json.dumps(
        {"version": DATASET_VERSION, "modules": [m.name for m in SCENARIO_MODULES]},
        sort_keys=True,
    )
    checksum = hashlib.sha256(manifest_source.encode()).hexdigest()
    batch = ImportBatch(
        branch_id=branch.id, dataset_version=DATASET_VERSION, period=period,
        checksum=checksum, status="running", actor=actor_email,
        started_at=datetime.now(timezone.utc),
    )
    db.add(batch)
    db.flush()

    ctx = ScenarioContext(
        branch_id=branch.id, period_year=period_year, period_month=period_month,
        tz_name=settings.TIMEZONE,
    )
    counts: dict = {}
    totals: dict = {}
    modules_run: list[str] = []
    # الساعة 8 صباحًا يوم 1 الشهر — بداية معقولة لسيناريو تشغيلي، كل مولّد
    # بيحرّك الوقت بنفسه جوه الـ scenario_clock context لتوزيع الأحداث
    # على الشهر (راجع resort_os/clock.py).
    scenario_start = datetime(period_year, period_month, 1, 8, 0, tzinfo=ZoneInfo(settings.TIMEZONE))
    try:
        with scenario_clock(scenario_start):
            for module in SCENARIO_MODULES:
                result = module.generate(db, ctx)
                counts[module.name] = result.get("counts", {})
                totals[module.name] = result.get("totals", {})
                modules_run.append(module.name)
    except Exception as exc:
        batch.status = "failed"
        batch.failure_reason = str(exc)[:2000]
        batch.completed_at = datetime.now(timezone.utc)
        db.flush()
        raise

    batch.status = "completed"
    batch.counts = json.dumps(counts, sort_keys=True, default=str)
    batch.totals = json.dumps(totals, sort_keys=True, default=str)
    batch.completed_at = datetime.now(timezone.utc)
    db.flush()

    return SeedResult(branch_code, period, DATASET_VERSION, "apply", False, modules_run, counts, totals)


def validate_only(db: Session, *, branch_code: str, period: str) -> dict:
    """يعرض الـ manifest المخزَّن لدفعة اتطبّقت بالفعل — مش re-run، بس قراءة
    read-only لآخر حالة معروفة. لو مفيش batch، بيرجّع applied=False صراحةً."""
    branch = _resolve_branch(db, branch_code)
    batch = _existing_batch(db, branch.id, period)
    if not batch:
        return {"applied": False, "branch_code": branch_code, "period": period}
    return {
        "applied": batch.status == "completed",
        "status": batch.status,
        "branch_code": branch_code,
        "period": period,
        "version": batch.dataset_version,
        "checksum": batch.checksum,
        "started_at": batch.started_at.isoformat() if batch.started_at else None,
        "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
        "counts": json.loads(batch.counts or "{}"),
        "totals": json.loads(batch.totals or "{}"),
        "failure_reason": batch.failure_reason,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run or apply the July 2026 operational history scenario (HIST-01)."
    )
    parser.add_argument("--branch-code", required=True)
    parser.add_argument("--period", required=True, help="YYYY-MM, e.g. 2026-07")
    parser.add_argument("--actor-id", type=int)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm")
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.apply and args.validate_only:
        raise SystemExit("--apply and --validate-only are mutually exclusive")

    with SessionLocal() as db:
        if args.validate_only:
            report = validate_only(db, branch_code=args.branch_code, period=args.period)
            db.rollback()
            print(json.dumps(report, ensure_ascii=False, sort_keys=True, default=str))
            return 0

        expected_confirm = confirmation_phrase(args.branch_code, args.period)
        if args.apply and args.confirm != expected_confirm:
            raise SystemExit(f"--apply requires --confirm {expected_confirm!r}")

        try:
            result = run_seed(
                db, branch_code=args.branch_code, period=args.period, actor_id=args.actor_id,
            )
            if args.apply:
                db.commit()
            else:
                db.rollback()
            print(
                json.dumps(
                    {
                        "mode": "apply" if args.apply else "dry-run",
                        "branch_code": result.branch_code,
                        "period": result.period,
                        "version": result.version,
                        "already_applied": result.already_applied,
                        "registered_modules": [m.name for m in SCENARIO_MODULES],
                        "modules_run": result.modules_run,
                        "counts": result.counts,
                        "totals": result.totals,
                    },
                    ensure_ascii=False, sort_keys=True, default=str,
                )
            )
            return 0
        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    raise SystemExit(main())
