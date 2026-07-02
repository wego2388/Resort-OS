"""
app/core/module_loader.py
═══════════════════════════════════════════════════════════════════════
Module System — بسيط، احترافي، بدون restart

المبدأ:
  - كل الـ routes مسجّلة دائماً عند startup
  - ModuleState في DB يتحكم في السماح/الرفض
  - Redis cache لـ 60 ثانية لتقليل DB hits
  - Toggle فوري — يمسح الـ cache فقط

لا process state، لا route rebuilding، لا تعقيد.
═══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import importlib
import json
import logging
from dataclasses import dataclass

import redis as redis_lib
from fastapi import FastAPI
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

CACHE_TTL = 60  # ثانية


# ───────────────────────── Registry ──────────────────────────────────

@dataclass(frozen=True)
class ModuleDefinition:
    key: str
    name_ar: str
    name_en: str
    always_on: bool = False
    depends_on: tuple = ()
    default_enabled: bool = True
    icon: str = ""
    nav_order: int = 100


MODULE_REGISTRY: dict[str, ModuleDefinition] = {
    "core":        ModuleDefinition("core",        "النظام الأساسي",    "Core",        always_on=True,  nav_order=0),
    "finance":     ModuleDefinition("finance",     "المالية والمحاسبة", "Finance",     always_on=True,  nav_order=10),
    "inventory":   ModuleDefinition("inventory",   "المخازن",          "Inventory",   always_on=True,  nav_order=20),
    "hr":          ModuleDefinition("hr",          "الموارد البشرية",  "HR",          always_on=True,  nav_order=25),
    "restaurant":  ModuleDefinition("restaurant",  "المطاعم",          "Restaurant",  depends_on=("inventory",), default_enabled=True,  icon="fire",              nav_order=30),
    "cafe":        ModuleDefinition("cafe",        "الكافيهات",        "Cafe",        depends_on=("inventory",), default_enabled=False, icon="coffee",            nav_order=40),
    "pms":         ModuleDefinition("pms",         "إدارة الفندق",     "Hotel PMS",   depends_on=("finance",),   default_enabled=False, icon="building-office-2", nav_order=50),
    "timeshare":   ModuleDefinition("timeshare",   "التايم شير",       "Timeshare",   depends_on=("pms",),       default_enabled=False, icon="calendar-days",     nav_order=60),
    "beach":       ModuleDefinition("beach",       "إدارة الشاطئ",     "Beach",       depends_on=("finance",),   default_enabled=False, icon="sun",               nav_order=70),
    "maintenance": ModuleDefinition("maintenance", "الصيانة والأصول", "Maintenance", depends_on=("core",),      default_enabled=True,  icon="wrench",            nav_order=80),
    "crm":         ModuleDefinition("crm",         "إدارة العملاء",   "CRM",         depends_on=("core",),      default_enabled=False, icon="user-group",        nav_order=90),
    "analytics":   ModuleDefinition("analytics",   "التحليلات",        "Analytics",   depends_on=("core",),      default_enabled=True,  icon="chart-bar",         nav_order=100),
    "hub":         ModuleDefinition("hub",         "المنصة الرقمية",  "Digital Hub", depends_on=("core",),      default_enabled=False, icon="globe-alt",         nav_order=110),
    "leasing":     ModuleDefinition("leasing",     "الإيجارات",        "Leasing",     depends_on=("finance",),   default_enabled=False, icon="key",               nav_order=120),
}


# ──────────────── Cache Key Helpers ──────────────────────────────────

def _cache_key(branch_id: int | None) -> str:
    return f"resort:modules:{branch_id or 'global'}"


# ──────────────── DB Read ─────────────────────────────────────────────

def _load_from_db(db: Session, branch_id: int | None) -> set[str]:
    """
    يقرأ الـ enabled modules من DB بالمنطق التالي:
    1. يبدأ من global defaults (branch_id IS NULL)
    2. يُطبّق per-branch overrides إن وُجدت
    3. يحل dependencies
    """
    from app.modules.core.models import ModuleState  # noqa: PLC0415

    # global states
    global_rows = db.query(ModuleState).filter(ModuleState.branch_id.is_(None)).all()
    states: dict[str, bool] = {r.module_key: r.enabled for r in global_rows}

    # per-branch overrides
    if branch_id:
        branch_rows = db.query(ModuleState).filter(ModuleState.branch_id == branch_id).all()
        for row in branch_rows:
            states[row.module_key] = row.enabled

    # resolve with defaults + always_on
    enabled: set[str] = set()
    for key, defn in MODULE_REGISTRY.items():
        if defn.always_on:
            enabled.add(key)
            continue
        if states.get(key, defn.default_enabled):
            enabled.add(key)

    return enabled


# ──────────────── Public API ──────────────────────────────────────────

def is_module_enabled(
    module_key: str,
    db: Session,
    redis_client: redis_lib.Redis,
    branch_id: int | None = None,
) -> bool:
    """
    السؤال الوحيد: هل هذا الـ module مفعّل لهذا الـ branch؟

    يُستخدم كـ FastAPI Dependency داخل كل endpoint يحتاج حماية.
    النتيجة cached في Redis لـ 60 ثانية.
    """
    defn = MODULE_REGISTRY.get(module_key)
    if defn and defn.always_on:
        return True  # always_on لا يحتاج DB

    cache_key = _cache_key(branch_id)
    try:
        cached = redis_client.get(cache_key)
        if cached:
            return module_key in json.loads(cached)
    except Exception:
        pass  # Redis down → fallback to DB

    enabled = _load_from_db(db, branch_id)

    try:
        redis_client.setex(cache_key, CACHE_TTL, json.dumps(list(enabled)))
    except Exception:
        pass

    return module_key in enabled


def get_enabled_modules(
    db: Session,
    redis_client: redis_lib.Redis,
    branch_id: int | None = None,
) -> set[str]:
    """يُرجع كل الـ modules المفعّلة — للـ nav endpoint."""
    cache_key = _cache_key(branch_id)
    try:
        cached = redis_client.get(cache_key)
        if cached:
            return set(json.loads(cached))
    except Exception:
        pass

    enabled = _load_from_db(db, branch_id)

    try:
        redis_client.setex(cache_key, CACHE_TTL, json.dumps(list(enabled)))
    except Exception:
        pass

    return enabled


def invalidate_cache(redis_client: redis_lib.Redis, branch_id: int | None = None) -> None:
    """يُستدعى بعد toggle — يمسح الـ cache فوراً."""
    try:
        if branch_id:
            redis_client.delete(_cache_key(branch_id))
        # دائماً امسح الـ global cache (يؤثر على الكل)
        redis_client.delete(_cache_key(None))
        # امسح كل branch caches (branch قد تعتمد على global)
        for key in redis_client.scan_iter("resort:modules:*"):
            redis_client.delete(key)
    except Exception as exc:
        logger.warning("Cache invalidation failed: %s", exc)


def toggle_module(
    key: str,
    enable: bool,
    db: Session,
    redis_client: redis_lib.Redis,
    branch_id: int | None = None,
    changed_by: int | None = None,
) -> dict:
    """
    Toggle فوري:
    1. يُحدّث DB
    2. يمسح الـ cache
    3. الـ request التالي يقرأ الـ state الجديد
    """
    from app.modules.core.models import ModuleState  # noqa: PLC0415

    defn = MODULE_REGISTRY.get(key)
    if not defn:
        raise ValueError(f"Module '{key}' غير موجود")
    if defn.always_on:
        raise ValueError(f"Module '{key}' لا يمكن تعطيله")

    if enable:
        # فعّل dependencies تلقائياً
        for dep in defn.depends_on:
            if not MODULE_REGISTRY[dep].always_on:
                _upsert(db, dep, True, branch_id, changed_by)

    else:
        # تحقق من dependents
        current = get_enabled_modules(db, redis_client, branch_id)
        dependents = [k for k, d in MODULE_REGISTRY.items() if key in d.depends_on and k in current]
        if dependents:
            raise ValueError(f"يعتمد عليه: {', '.join(dependents)} — عطّلهم أولاً")

    _upsert(db, key, enable, branch_id, changed_by)
    db.commit()
    invalidate_cache(redis_client, branch_id)

    return {
        "module": key,
        "enabled": enable,
        "scope": f"branch:{branch_id}" if branch_id else "global",
        "effective": "immediate",
    }


def _upsert(
    db: Session,
    key: str,
    enabled: bool,
    branch_id: int | None,
    changed_by: int | None,
) -> None:
    from app.modules.core.models import ModuleState  # noqa: PLC0415

    row = (
        db.query(ModuleState)
        .filter(ModuleState.module_key == key, ModuleState.branch_id == branch_id)
        .first()
    )
    if row:
        row.enabled = enabled
        row.changed_by = changed_by
    else:
        db.add(ModuleState(module_key=key, enabled=enabled,
                           branch_id=branch_id, changed_by=changed_by))


# ──────────────── Startup: Register ALL Routes ───────────────────────

def register_all_routes(app: FastAPI) -> None:
    """
    يُسجّل routes كل الـ modules عند startup — بدون شروط.

    لماذا كل الـ routes؟
    - FastAPI لا تدعم إضافة/حذف routes بعد startup
    - التحكم يكون في الـ endpoint نفسه عبر require_module dependency
    - DB tables دائماً موجودة — routes كذلك
    """
    for key, defn in sorted(MODULE_REGISTRY.items(), key=lambda x: x[1].nav_order):
        try:
            mod = importlib.import_module(f"app.modules.{key}.api.router")
            app.include_router(mod.router, prefix="/api/v1")
            logger.info("✓ Router registered: %s", key)
        except ModuleNotFoundError:
            logger.debug("Router not yet implemented: %s — skipped", key)
