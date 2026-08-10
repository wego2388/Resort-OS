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
    manifest. مفروض يستخدم services حقيقية (زي كل المولّدات الموجودة
    فعليًا) — أي db.commit() داخلي آمن تمامًا دلوقتي، لأن main() بيربط
    الـSession بـconnection transaction خارجية عبر
    join_transaction_mode="create_savepoint" (راجع main()'s توثيق)، فأي
    commit داخلي بيقفل SAVEPOINT بس مش الـtransaction الفعلية — الـCLI
    برضو هو مالك القرار النهائي (commit/rollback) بغض النظر عن عدد
    الـcommits الداخلية دي."""
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


@dataclass
class _PreparedBatch:
    """نتيجة `prepare_batch` — إما batch جديد لسه "running" (لسه محتاج
    `run_modules`)، أو نتيجة نهائية جاهزة (batch سابق كان completed
    بالفعل، مفيش حاجة تتنفذ)."""
    batch: "object | None"  # ImportBatch | None
    branch_id: "int | None"
    ctx: "ScenarioContext | None"
    already_completed_result: "SeedResult | None"


def prepare_batch(
    db: Session, *, branch_code: str, period: str, actor_id: Optional[int] = None,
) -> _PreparedBatch:
    """المرحلة الأولى بس: قفل + تحقق + إنشاء ImportBatch(status="running")
    (flush بس هنا — الـ caller قرر يعمل commit فوري منفصل عشان علامة
    "running" تفضل موجودة فعليًا حتى لو حصل crash حقيقي في المرحلة
    التانية (`run_modules`) — راجع main()'s توثيق تحت لتفاصيل الـ
    checkpoint المزدوج ده وليه محتاج يبقى منفصل عن باقي الشغل."""
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
        return _PreparedBatch(
            batch=None, branch_id=None, ctx=None,
            already_completed_result=SeedResult(
                branch_code, period, DATASET_VERSION, "apply", True,
                [], json.loads(existing.counts or "{}"), json.loads(existing.totals or "{}"),
            ),
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
    return _PreparedBatch(batch=batch, branch_id=branch.id, ctx=ctx, already_completed_result=None)


def run_modules(db: Session, batch, ctx: ScenarioContext) -> SeedResult:
    """المرحلة التانية: تشغيل كل الموديولات المسجَّلة فعليًا. بتحدّث
    `batch.counts/totals` **تدريجيًا بعد كل موديول** (flush بس) — مش في
    الآخر بس زي قبل كده — عشان لو crash حقيقي حصل في نص التشغيلة، أي
    استعلام manual على الـImportBatch (أو reset-dataset's guard تحت)
    يقدر يعرف فعليًا وصل لحد فين، مش بس "failed" بلا تفاصيل."""
    counts: dict = {}
    totals: dict = {}
    modules_run: list[str] = []
    scenario_start = datetime(ctx.period_year, ctx.period_month, 1, 8, 0, tzinfo=ZoneInfo(ctx.tz_name))
    try:
        with scenario_clock(scenario_start):
            for module in SCENARIO_MODULES:
                result = module.generate(db, ctx)
                counts[module.name] = result.get("counts", {})
                totals[module.name] = result.get("totals", {})
                modules_run.append(module.name)
                batch.counts = json.dumps(counts, sort_keys=True, default=str)
                batch.totals = json.dumps(totals, sort_keys=True, default=str)
                db.flush()
    except Exception as exc:
        batch.status = "failed"
        batch.failure_reason = str(exc)[:2000]
        batch.completed_at = datetime.now(timezone.utc)
        db.flush()
        raise

    batch.status = "completed"
    batch.completed_at = datetime.now(timezone.utc)
    db.flush()

    # branch_code مش متاح هنا (batch عنده branch_id بس) — الـ caller
    # (main()/run_seed()) هو اللي عنده الـ string الأصلي ولازم يستخدمه
    # هو في أي output نهائي، مش الحقل ده.
    return SeedResult(
        "", batch.period, DATASET_VERSION, "apply", False, modules_run, counts, totals,
    )


def run_seed(
    db: Session, *, branch_code: str, period: str, actor_id: Optional[int] = None,
) -> SeedResult:
    """يشتغل جوه transaction المستدعي (staged بس، مش commit) — الـ caller
    (main تحت) هو اللي بيقرر commit ولا rollback حسب --apply.

    ⚠️ دي دالة راحة (convenience) بتجمّع `prepare_batch` + `run_modules` في
    نداء واحد — مناسبة لـdry-run (كل حاجة جوه transaction واحدة هترجع
    بالكامل beside الآخر) ولاستخدام مباشر/اختباري. لـ--apply الحقيقي في
    main() تحت، المرحلتين بيتنادوا منفصلين عمدًا (commit فوري بعد
    prepare_batch) — راجع main()'s توثيق."""
    prepared = prepare_batch(db, branch_code=branch_code, period=period, actor_id=actor_id)
    if prepared.already_completed_result:
        return prepared.already_completed_result
    result = run_modules(db, prepared.batch, prepared.ctx)
    return SeedResult(
        branch_code, period, DATASET_VERSION, "apply", False,
        result.modules_run, result.counts, result.totals,
    )


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

    if args.validate_only:
        with SessionLocal() as db:
            report = validate_only(db, branch_code=args.branch_code, period=args.period)
            db.rollback()
            print(json.dumps(report, ensure_ascii=False, sort_keys=True, default=str))
            return 0

    expected_confirm = confirmation_phrase(args.branch_code, args.period)
    if args.apply and args.confirm != expected_confirm:
        raise SystemExit(f"--apply requires --confirm {expected_confirm!r}")

    # ⚠️ باج أمان حقيقي اتصلح هنا: كل موديول HIST-01 بينادي services حقيقية
    # (create_employee/confirm_booking/receive_purchase_order/post_journal_
    # entry...)، وكل service بينادي db.commit() داخليًا — نفس اصطلاح
    # المشروع كله (راجع أي services.py). يعني `db.rollback()` القديمة في
    # وضع dry-run (الافتراضي!) كانت بترجع بس آخر جزء لسه pending، مش أي
    # حاجة اتكتبت فعليًا في التشغيلة كلها — "dry-run افتراضي" (§9.1، أول
    # بند في الحزمة) كان مكسور فعليًا من أول commit لأي مولّد، وبيانات
    # حقيقية كانت بتتكتب بصمت حتى من غير --apply خالص. اتأكد بريبرو حي ضد
    # PostgreSQL حقيقي قبل الإصلاح (14 موظف فضلوا في الداتابيز بعد
    # db.rollback() العادي)، وبعد الإصلاح (صفر بعد rollback الـconnection
    # الخارجية). الحل: نربط الـSession بـconnection واحدة صريحة عبر
    # join_transaction_mode="create_savepoint" — أي db.commit() داخل أي
    # service بقى بيقفل SAVEPOINT بس، مش الـtransaction الفعلية على مستوى
    # الـconnection.
    #
    # ⚠️ لكن ده كشف تعارض حقيقي تاني مع متطلب منفصل من §9.1: "منع rerun
    # حتى بعد crash باستخدام import batch/checkpoints" — لو كل التشغيلة
    # (بما فيها إنشاء ImportBatch(status="running") نفسه) جوه transaction
    # واحدة هترجع بالكامل عند أي استثناء، فأي crash حقيقي أثناء --apply
    # هيمسح علامة "running"/"failed" نفسها كمان، ويرجع الحماية من الـrerun
    # عديمة الفائدة بالظبط في اللحظة اللي محتاجينها فيها. الحل: لـ--apply
    # بس، بنعمل checkpoint حقيقي منفصل — نلتزم (commit فوري) بعلامة
    # "running" في transaction قصيرة لوحدها الأول، وبعدين نبدأ transaction
    # تانية (savepoint mode برضو) للشغل الفعلي؛ لو فشلت، نفتح transaction
    # ثالثة قصيرة تسجّل "failed" + السبب بشكل دائم. dry-run فضل زي ما هو
    # (transaction واحدة، rollback شامل حتى لو للـbatch نفسه — دري-ران
    # المفروض ميسيبش أي أثر خالص، مش حتى علامة).
    from app.core.database import get_engine  # noqa: PLC0415
    from app.modules.core.models import ImportBatch  # noqa: PLC0415

    engine = get_engine()

    if not args.apply:
        connection = engine.connect()
        outer_txn = connection.begin()
        db = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            result = run_seed(
                db, branch_code=args.branch_code, period=args.period, actor_id=args.actor_id,
            )
            outer_txn.rollback()
            _print_seed_result("dry-run", args, result)
            return 0
        except Exception:
            outer_txn.rollback()
            raise
        finally:
            db.close()
            connection.close()

    # ── --apply: مرحلة 1 — checkpoint حقيقي، commit فوري منفصل ──────────
    connection = engine.connect()
    checkpoint_txn = connection.begin()
    checkpoint_db = Session(bind=connection)
    try:
        prepared = prepare_batch(
            checkpoint_db, branch_code=args.branch_code, period=args.period, actor_id=args.actor_id,
        )
        checkpoint_txn.commit()
    except Exception:
        checkpoint_txn.rollback()
        connection.close()
        raise
    finally:
        checkpoint_db.close()

    if prepared.already_completed_result:
        connection.close()
        _print_seed_result("apply", args, prepared.already_completed_result)
        return 0

    batch_id = prepared.batch.id
    ctx = prepared.ctx

    # ── مرحلة 2 — الشغل الفعلي، savepoint mode، transaction منفصلة ──────
    # ⚠️ pg_advisory_xact_lock مربوط بعمر الـtransaction اللي اتاخد فيها —
    # القفل اتحرر تلقائيًا لما checkpoint_txn.commit() فوق حصل. لازم نعيد
    # أخذه هنا من جديد لحماية المرحلة الأطول والأهم (الشغل الفعلي) من أي
    # تشغيلة تانية متزامنة — وإلا الحماية بتفضل شغالة بس في أقصر/أقل جزء
    # حرج من العملية كلها.
    work_txn = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        _acquire_lock(db)
        batch = db.get(ImportBatch, batch_id)
        result = run_modules(db, batch, ctx)
        work_txn.commit()
        _print_seed_result("apply", args, SeedResult(
            args.branch_code, args.period, DATASET_VERSION, "apply", False,
            result.modules_run, result.counts, result.totals,
        ))
        return 0
    except Exception as exc:
        work_txn.rollback()
        # ── مرحلة 3 — تسجيل "failed" بشكل دائم في transaction قصيرة منفصلة ──
        fail_txn = connection.begin()
        fail_db = Session(bind=connection)
        try:
            failed_batch = fail_db.get(ImportBatch, batch_id)
            failed_batch.status = "failed"
            failed_batch.failure_reason = str(exc)[:2000]
            failed_batch.completed_at = datetime.now(timezone.utc)
            # ⚠️ باج حقيقي اتكشف واتصلح وقت كتابة test_apply_mode_survives_
            # mid_run_crash: fail_txn.commit() (على مستوى الـTransaction
            # الخام) بيلتزم بس بالـSQL اللي اتبعت فعليًا للـconnection —
            # التعديلات على failed_batch فوق (ORM attribute assignment)
            # كانت لسه staged جوه fail_db's unit-of-work، من غير flush،
            # يعني fail_txn.commit() كان بيقفل transaction فاضية فعليًا،
            # وعلامة "failed" عمرها ما كانت بتتسجّل حقيقي — بالظبط الباج
            # اللي checkpoint marker المفروض يحميه منه. لازم flush صريح
            # قبل الـcommit على مستوى الـTransaction.
            fail_db.flush()
            fail_txn.commit()
        except Exception:
            fail_txn.rollback()
            raise
        finally:
            fail_db.close()
        raise
    finally:
        db.close()
        connection.close()


def _print_seed_result(mode: str, args: argparse.Namespace, result: SeedResult) -> None:
    print(
        json.dumps(
            {
                "mode": mode,
                "branch_code": args.branch_code,
                "period": args.period,
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


if __name__ == "__main__":
    raise SystemExit(main())
