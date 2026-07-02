"""
app/core/deps.py
═══════════════════════════════════════════════════════════════════════
FastAPI Dependencies — Auth
═══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db  # noqa: F401 — re-export; same callable wego_core's auth router uses


DbDep = Annotated[Session, Depends(get_db)]


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


# ─────────────────────── Permission Matrix (fine-grained) ─────────────
# طبقة إضافية فوق ROLE_LEVELS — "screen/action permission" زي
# UsersScreenAccessDetails في نظام Trucker القديم، بس هنا additive مش
# breaking: مفيش أي مستخدم عليه صف UserPermission صريح → يسلك تماماً زي
# النظام الحالي (role level فقط). راجع app/modules/core/services.py::has_permission
# و app/modules/core/models.py::UserPermission للتفاصيل الكاملة.
#
# الاستخدام (defense-in-depth — بيتضاف جنب role dependency الموجودة، مش بدلها):
#     @router.post(
#         "/finance/payments/{id}/void",
#         dependencies=[Depends(require_permission("finance.void_payment", "execute"))],
#     )
#     def void_payment(..., user=Depends(get_cashier_user), ...):
#         ...
#
# min_role_level بيمثّل "الحد المعتاد" لهذا الـ resource.action تحديداً
# (ممكن يكون أعلى من role dependency الأساسية الموجودة على الـ endpoint —
# ده بالظبط اللي بيسمح بمنح استثناء لمستخدم أقل role من الحد المعتاد).

def require_permission(resource: str, action: str, min_role_level: int = 60):
    """
    Dependency للـ permission matrix — يُستخدم جنب role dependency الأساسية.

    المنطق:
        1. لو فيه UserPermission صريح (منح/منع) لهذا الـ user+resource+action
           → هو الحاكم، بغض النظر عن الـ role.
        2. لو مفيش استثناء صريح → fallback لـ role level العادي
           (user_level(user) >= min_role_level).
    """
    def _check(
        user=Depends(get_current_active_user),
        db: Session = Depends(get_db),
    ) -> None:
        from app.modules.core.services import has_permission  # noqa: PLC0415

        role_fallback = user_level(user) >= min_role_level
        if not has_permission(db, user, resource, action, role_fallback=role_fallback):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": f"لا تملك صلاحية '{action}' على '{resource}'",
                    "resource": resource,
                    "action": action,
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
