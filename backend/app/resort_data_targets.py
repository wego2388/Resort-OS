"""RESET-01 — حل هوية الـtarget (OPS-DATA-02 §9.4). `local` وَ`vps` مش labels
قابلين للتبديل — كل واحد بيتحل لبيانات اتصال حقيقية مختلفة تمامًا، مقروءة
من secret/env بس (صفر DB URL أو password كـCLI argument، وصفر طباعة لهم في
أي log).

- `local`: افتراضيًا بيقرا نفس `backend/.env`'s DATABASE_URL اللي التطبيق
  نفسه بيستخدمه (zero-friction للتطوير المحلي) — لو `RESORT_DATA_LOCAL_
  DATABASE_URL` متظبط صراحةً، بياخد الأولوية.
- `vps`: **لازم** `RESORT_DATA_VPS_DATABASE_URL` يتظبط صراحةً — مفيش
  fallback خالص. عمدًا: أي غياب يفشل مغلق (fail closed) بدل ما يخمّن أو
  يستخدم قيمة local بالغلط."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ENV_FILE = _BACKEND_DIR / ".env"

VALID_TARGET_NAMES = ("local", "vps")


@dataclass(frozen=True)
class TargetConfig:
    name: str
    database_url: str
    branch_code: str
    rebuild_trial_enabled: bool
    ssh_host: "str | None" = None


class TargetResolutionError(RuntimeError):
    """Target غير معروف أو ناقص إعداد — دايمًا fail closed، صفر تخمين."""


def _read_env_file_var(path: Path, key: str) -> "str | None":
    if not path.exists():
        return None
    pattern = re.compile(rf"^{re.escape(key)}=(.*)$")
    for line in path.read_text().splitlines():
        m = pattern.match(line.strip())
        if m:
            return m.group(1)
    return None


def _env_bool(value: "str | None", default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in ("false", "0", "no", "off")


def resolve_target(name: str) -> TargetConfig:
    if name not in VALID_TARGET_NAMES:
        raise TargetResolutionError(
            f"Unknown target {name!r} — must be one of {VALID_TARGET_NAMES}. "
            "local/vps are not interchangeable labels; each resolves to distinct, "
            "explicitly-configured connection details."
        )

    prefix = f"RESORT_DATA_{name.upper()}_"
    database_url = os.environ.get(f"{prefix}DATABASE_URL")
    if not database_url and name == "local":
        database_url = _read_env_file_var(_ENV_FILE, "DATABASE_URL")
    if not database_url:
        raise TargetResolutionError(
            f"{prefix}DATABASE_URL is not set — resort-data refuses to guess a "
            f"connection for target={name!r}. Set it as an environment variable "
            "(never pass a DB URL as a CLI argument)."
        )

    branch_code = os.environ.get(f"{prefix}BRANCH_CODE", "ELK-001")
    rebuild_trial_enabled = _env_bool(os.environ.get(f"{prefix}REBUILD_TRIAL_ENABLED"), default=True)
    ssh_host = os.environ.get(f"{prefix}SSH_HOST")

    return TargetConfig(
        name=name, database_url=database_url, branch_code=branch_code,
        rebuild_trial_enabled=rebuild_trial_enabled, ssh_host=ssh_host,
    )


def compute_fingerprint(database_url: str, branch_code: str) -> dict:
    """يجمع هوية الـtarget الحقيقية وقت التشغيل — مفروض تتعرض للمشغّل قبل
    أي --apply (target mismatch protection حقيقي، مش افتراض)."""
    import sqlalchemy as sa

    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as conn:
            db_oid = conn.execute(
                sa.text("SELECT oid FROM pg_database WHERE datname = current_database()")
            ).scalar()
            try:
                migration_head = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
            except Exception:
                migration_head = None
            row_counts = {}
            for table in ("branches", "users", "journal_entries", "import_batches"):
                try:
                    row_counts[table] = conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()
                except Exception:
                    row_counts[table] = None
    finally:
        engine.dispose()

    return {
        "host": engine.url.host,
        "port": engine.url.port,
        "database": engine.url.database,
        "db_oid": db_oid,
        "branch_code": branch_code,
        "migration_head": migration_head,
        "row_counts": row_counts,
    }


def build_confirmation_phrase(command: str, target: TargetConfig, fingerprint: dict) -> str:
    """عبارة تأكيد صريحة بتضم host/database/branch/migration head — نفس
    اصطلاح `operational_history_seed.confirmation_phrase` بالظبط، موسّع
    عشان يضم هوية الـtarget نفسها (§9.4: local/vps مش labels)."""
    return (
        f"{command.upper()} {target.name} {fingerprint['host']}:{fingerprint['port']}/"
        f"{fingerprint['database']} branch={fingerprint['branch_code']} "
        f"head={fingerprint['migration_head']}"
    )
