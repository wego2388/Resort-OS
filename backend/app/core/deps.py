"""
app/core/deps.py
═══════════════════════════════════════════════════════════════════════
FastAPI Dependencies — Auth + Module Guard

الاستخدام:
    @router.get("/orders")
    async def list_orders(
        _: None = Depends(require_module("restaurant")),
        user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db),
    ):
        ...
═══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

import redis as redis_lib
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db  # noqa: F401 — re-export; same callable wego_core's auth router uses
from app.core.module_loader import MODULE_REGISTRY, is_module_enabled


DbDep = Annotated[Session, Depends(get_db)]


# ─────────────────────── Redis ───────────────────────────────────────

@lru_cache
def _get_redis_client() -> redis_lib.Redis:
    settings = get_settings()
    return redis_lib.from_url(settings.REDIS_URL, decode_responses=True)


def get_redis() -> redis_lib.Redis:
    return _get_redis_client()


RedisDep = Annotated[redis_lib.Redis, Depends(get_redis)]


# ─────────────────────── Auth ────────────────────────────────────────

# wego_core.models.user.User has no numeric `level` column — only `role`.
# Map roles to the numeric levels the rest of the app checks against.
ROLE_LEVELS: dict[str, int] = {
    "super_admin": 100,
    "admin":        80,
    "accountant":   70,
    "hr_manager":   70,
    "manager":      60,
    "supervisor":   50,
    "receptionist": 40,
    "cashier":      40,
    "waiter":       30,
    "chef":         30,
    "kitchen":      30,
    "employee":     20,
    "customer":      0,
    "guest":         0,
}


def user_level(user) -> int:
    return ROLE_LEVELS.get(user.role, 0)


# ─────────────────────── Token Revocation ──────────────────────────────
# Per 08-SECURITY.md: role/status changes must invalidate tokens already
# issued for that user — otherwise a demoted/deactivated user keeps acting
# at their old privilege level until the access token naturally expires.

REVOKED_CACHE_PREFIX = "user_revoked"


def revoke_user_tokens(user_id: int) -> None:
    """Call whenever a user's role/is_active changes — invalidates every
    token issued before this moment, forcing re-login on the new privileges."""
    import time  # noqa: PLC0415
    from wego_core.cache.store import set_cache  # noqa: PLC0415

    set_cache(f"{REVOKED_CACHE_PREFIX}:{user_id}", time.time(), ttl=settings_refresh_ttl_seconds())


def settings_refresh_ttl_seconds() -> int:
    return get_settings().REFRESH_TOKEN_EXPIRE_DAYS * 86_400


# ─────────────────────── Mandatory 2FA ─────────────────────────────────
# Per 08-SECURITY.md: "2FA إلزامي لـ super_admin وfinance". wego_core's
# login flow doesn't gate on two_factor_enabled, so it's enforced here —
# every request from these roles is blocked until 2FA is turned on, except
# the auth router's own endpoints (so the user can actually set it up).

MANDATORY_2FA_ROLES = {"super_admin", "accountant"}


def get_current_user(request: Request, db: DbDep):
    """يُستخرج الـ user من JWT — يتحقق من التوقيع والـ token_blacklist والـ revocation."""
    from jose import JWTError  # noqa: PLC0415
    from wego_core.cache.store import get_cache  # noqa: PLC0415
    from wego_core.models.user import TokenBlacklist, User  # noqa: PLC0415
    from wego_core.security import decode_token, hash_token  # noqa: PLC0415

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "غير مصرح")
    token = auth_header.removeprefix("Bearer ")

    settings = get_settings()
    try:
        payload = decode_token(token, settings.SECRET_KEY, settings.ALGORITHM)
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token غير صالح")

    blacklisted = (
        db.query(TokenBlacklist)
        .filter(TokenBlacklist.token_hash == hash_token(token))
        .first()
    )
    if blacklisted:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token ملغي")

    email = payload.get("sub")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User غير موجود")

    revoked_at = get_cache(f"{REVOKED_CACHE_PREFIX}:{user.id}")
    if revoked_at and payload.get("iat", 0) < revoked_at:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "تم تغيير الصلاحيات — سجّل دخول مرة أخرى")

    return user


def get_current_active_user(request: Request, user=Depends(get_current_user)):
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "حساب غير نشط")

    if (
        user.role in MANDATORY_2FA_ROLES
        and not user.two_factor_enabled
        and not request.url.path.startswith(f"{get_settings().API_PREFIX}/auth")
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            {
                "code": "2FA_REQUIRED",
                "message": "التحقق بخطوتين إلزامي لهذا الدور — فعّله من إعدادات الحساب أولاً",
            },
        )

    return user


def get_manager_user(user=Depends(get_current_active_user)):
    if user_level(user) < 60:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "يتطلب صلاحية مدير")
    return user


def get_admin_user(user=Depends(get_current_active_user)):
    if user_level(user) < 80:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "يتطلب صلاحية admin")
    return user


def get_super_admin_user(user=Depends(get_current_active_user)):
    if user_level(user) < 100:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "يتطلب صلاحية super_admin")
    return user


def get_cashier_user(user=Depends(get_current_active_user)):
    if user_level(user) < 40:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "يتطلب صلاحية كاشير")
    return user


def get_waiter_user(user=Depends(get_current_active_user)):
    if user_level(user) < 30:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "يتطلب صلاحية نادل")
    return user


# ─────────────────────── Module Guard ────────────────────────────────

def require_module(module_key: str):
    """
    Dependency يحمي أي endpoint بـ module check.

    الاستخدام:
        @router.get("/rooms")
        async def list_rooms(_=Depends(require_module("pms")), ...):

    المنطق:
        - always_on modules → تمر فوراً بدون DB
        - باقي modules → يتحقق من Redis/DB
        - super_admin يرى كل شيء (لأغراض الإدارة)
    """
    def _check(
        user=Depends(get_current_active_user),
        db: Session = Depends(get_db),
        redis_client: redis_lib.Redis = Depends(get_redis),
    ) -> None:
        # always_on لا تحتاج check
        defn = MODULE_REGISTRY.get(module_key)
        if defn and defn.always_on:
            return

        # super_admin يرى كل شيء
        if user_level(user) >= 100:
            return

        branch_id = getattr(user, "branch_id", None)

        if not is_module_enabled(module_key, db, redis_client, branch_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "MODULE_DISABLED",
                    "message": f"الخدمة '{module_key}' غير مفعّلة لهذا الفرع",
                    "module": module_key,
                },
            )

    return _check


# ─────────────────────── Resource-keyed rate limiting ─────────────────

def rate_limit_dep(prefix: str, max_requests: int, window_seconds: int, key_param: str = "branch_id"):
    """
    Per-resource rate limit dependency — for limits keyed by something only
    known once the request is authenticated/parsed (unlike login/public,
    which are IP-keyed and handled by app.core.rate_limit.RateLimitMiddleware).

    الاستخدام:
        @router.post("/eta/invoices", dependencies=[Depends(rate_limit_dep("eta", 100, 60))])
    """
    from wego_core.cache.store import rate_limit  # noqa: PLC0415

    def _check(request: Request, user=Depends(get_current_active_user)) -> None:
        key_value = request.path_params.get(key_param) or user.id
        if not rate_limit(f"{prefix}:{key_value}", max_requests=max_requests, window_seconds=window_seconds):
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                {"code": "rate_limit_exceeded", "message": "محاولات كثيرة جداً — حاول لاحقاً"},
            )

    return _check
