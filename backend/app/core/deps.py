"""
app/core/deps.py
═══════════════════════════════════════════════════════════════════════
FastAPI Dependencies — Auth
═══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db  # noqa: F401 — re-export; same callable the kernel auth router uses


DbDep = Annotated[Session, Depends(get_db)]


# ─────────────────────── Auth ────────────────────────────────────────

# app.core.kernel.models.user.User has no numeric `level` column — only `role`.
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
    # timeshare_agent: موظف تايم شير متخصص — صلاحيات عامة محدودة جداً (level 25)
    # لكن بيحصل على UserPermission صريح على timeshare.* عند إنشاء الحساب.
    # مفيش أي وصول لـ endpoints تانية تتطلب > 25 من غير منح صريح.
    "timeshare_agent": 25,
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
    from app.core.kernel.cache import set_cache  # noqa: PLC0415

    set_cache(f"{REVOKED_CACHE_PREFIX}:{user_id}", time.time(), ttl=settings_refresh_ttl_seconds())


def settings_refresh_ttl_seconds() -> int:
    return get_settings().REFRESH_TOKEN_EXPIRE_DAYS * 86_400


# ─────────────────────── Mandatory 2FA ─────────────────────────────────
# Per 08-SECURITY.md: "2FA إلزامي لـ super_admin وfinance". The kernel's
# login flow doesn't gate on two_factor_enabled, so it's enforced here —
# every request from these roles is blocked until 2FA is turned on, except
# the auth router's own endpoints (so the user can actually set it up).

MANDATORY_2FA_ROLES = {"super_admin", "accountant"}


def _resolve_user_from_token(token: str, db: Session):
    """المنطق المشترك بين get_current_user (Authorization header) وWebSocket
    auth (?token= query param — WebSocket API في المتصفح مايدعمش custom
    headers، فمفيش بديل غير query param هنا). يرجّع None عند أي فشل بدل ما
    يرمي HTTPException — الـ caller هو اللي يقرر شكل الرفض (401 HTTP أو
    قفل WebSocket)."""
    from jose import JWTError  # noqa: PLC0415
    from app.core.kernel.cache import get_cache  # noqa: PLC0415
    from app.core.kernel.models.user import RefreshToken, TokenBlacklist, User  # noqa: PLC0415
    from app.core.kernel.security import decode_token, hash_token  # noqa: PLC0415

    settings = get_settings()
    try:
        payload = decode_token(token, settings.SECRET_KEY, settings.ALGORITHM)
    except JWTError:
        return None

    blacklisted = (
        db.query(TokenBlacklist)
        .filter(TokenBlacklist.token_hash == hash_token(token))
        .first()
    )
    if blacklisted:
        return None

    email = payload.get("sub")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None

    # Gate 2B3B acceptance hardening: access tokens minted by the HTTP login
    # and refresh flows carry the public id of their refresh-token family.
    # Re-checking that family here makes a targeted session revoke immediate,
    # instead of leaving a stolen access token usable until its 30-minute TTL.
    # Tokens without ``sid`` remain valid for backward compatibility and for
    # the short-lived POS PIN-switch flow, which has no refresh session.
    session_ref = payload.get("sid")
    if session_ref:
        live_session = db.query(RefreshToken.id).filter(
            RefreshToken.user_id == user.id,
            RefreshToken.family_public_id == session_ref,
            RefreshToken.consumed_at.is_(None),
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(timezone.utc),
        ).first()
        if live_session is None:
            return None

    revoked_at = get_cache(f"{REVOKED_CACHE_PREFIX}:{user.id}")
    if revoked_at and payload.get("iat", 0) < revoked_at:
        return None

    return user


def get_current_user(request: Request, db: DbDep):
    """يُستخرج الـ user من JWT — يتحقق من التوقيع والـ token_blacklist والـ revocation."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "غير مصرح")
    token = auth_header.removeprefix("Bearer ")

    user = _resolve_user_from_token(token, db)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token غير صالح أو منتهي")
    return user


async def get_websocket_user(websocket, db: Session, min_level: int = 0):
    """بوابة تحقق موحّدة لكل WebSocket endpoint في المشروع (راجع A-01 في
    wagdy.md — كانت الاتصالات دي كلها بتتقبل من غير أي تحقق هوية خالص).
    التوكن بيوصل كـ query param (`?token=...`) مش header. بترجع الـ user
    لو التحقق نجح، أو تقفل الاتصال بـ code مناسب وترجع None لو فشل —
    الـ caller لازم يتأكد إن القيمة الراجعة مش None قبل `.accept()`."""
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)
        return None

    user = _resolve_user_from_token(token, db)
    if not user or not user.is_active:
        await websocket.close(code=4401)
        return None

    if getattr(user, "must_change_password", False):
        await websocket.close(code=4403)
        return None

    if user.role in MANDATORY_2FA_ROLES and not user.two_factor_enabled:
        await websocket.close(code=4403)
        return None

    if user_level(user) < min_level:
        await websocket.close(code=4403)
        return None

    return user


def get_current_active_user(request: Request, user=Depends(get_current_user)):
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "حساب غير نشط")

    if (
        getattr(user, "must_change_password", False)
        and not request.url.path.startswith(f"{get_settings().API_PREFIX}/auth")
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            {
                "code": "PASSWORD_CHANGE_REQUIRED",
                "message": "يجب استبدال كلمة المرور المؤقتة قبل استخدام النظام",
            },
        )

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


def get_timeshare_user(user=Depends(get_current_active_user), db: Session = Depends(get_db)):
    """بوابة التايم شير — يقبل:
      • أي مستخدم level >= 40 (cashier وفوق) بشكل تلقائي.
      • timeshare_agent (level=25) لو عنده UserPermission صريح
        على resource='timeshare.access' action='view' (ممنوح بشكل
        أوتوماتيكي عند إنشاء حساب بـ role=timeshare_agent).
    يمنع أي حساب آخر (employee/customer/guest) حتى لو حاول.
    """
    from app.modules.core.services import has_permission  # noqa: PLC0415

    lvl = user_level(user)
    if lvl >= 40:
        return user
    if lvl >= 25:
        # timeshare_agent: يلزم permission صريح
        if has_permission(db, user, "timeshare.access", "view", role_fallback=False):
            return user
    raise HTTPException(status.HTTP_403_FORBIDDEN, "لا تملك صلاحية الوصول لوحدة التايم شير")


def get_waiter_user(user=Depends(get_current_active_user)):
    if user_level(user) < 30:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "يتطلب صلاحية نادل")
    return user


def get_employee_user(user=Depends(get_current_active_user)):
    """أي موظف حقيقي (level >= 20) — يستثني customer/guest (level 0).
    للـ endpoints الداخلية التشغيلية (زي تعديل أمر صيانة) اللي المفروض
    تبقى مقفولة على الموظفين، مش أي حساب مسجّل من الموقع العام."""
    if user_level(user) < 20:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "يتطلب صلاحية موظف")
    return user


# ─────────────────────── Permission Matrix (fine-grained) ─────────────
# طبقة إضافية فوق ROLE_LEVELS — "screen/action permission" زي
# UsersScreenAccessDetails في نظام Trucker القديم، بس هنا additive مش
# breaking: مفيش أي مستخدم عليه صف UserPermission صريح → يسلك تماماً زي
# النظام الحالي (role level فقط). راجع app/modules/core/services.py::has_permission
# و app/modules/core/models.py::UserPermission للتفاصيل الكاملة.
#
# الاستخدام (defense-in-depth — بيتضاف جنب role dependency الموجودة، مش بدلها)
# — مطبَّق فعليًا على POST /finance/payments/{payment_id}/void
# (app/modules/finance/api/router.py):
#     @router.post(
#         "/finance/payments/{payment_id}/void",
#         dependencies=[Depends(require_permission("finance.void_payment", "execute", min_role_level=60))],
#     )
#     def void_payment(..., user=Depends(get_manager_user), ...):
#         ...
#
# min_role_level بيمثّل "الحد المعتاد" لهذا الـ resource.action تحديداً
# (ممكن يكون أعلى من role dependency الأساسية الموجودة على الـ endpoint —
# ده بالظبط اللي بيسمح بمنح استثناء لمستخدم أقل role من الحد المعتاد).

def require_permission(resource: str, action: str, min_role_level: int = 60):
    """
    Dependency للـ permission matrix — يُستخدم جنب role dependency الأساسية.

    المنطق (راجع app.modules.core.services._resolve_permission للتفصيل
    الكامل — هي المصدر الوحيد لهذا القرار، مش تكرار هنا):
        1. super_admin نشط ينجح دايمًا — أي منع صريح مسجّل يفضل "inert"
           بلا أثر (Gate 2A، Decision 0003 invariant #1).
        2. لو فيه UserPermission صريح (منح/منع) لهذا الـ user+resource+action
           → هو الحاكم، بغض النظر عن الـ role.
        3. لو مفيش استثناء صريح → fallback لـ role level العادي
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
    from app.core.kernel.cache import rate_limit  # noqa: PLC0415

    def _check(request: Request, user=Depends(get_current_active_user)) -> None:
        key_value = request.path_params.get(key_param) or user.id
        if not rate_limit(f"{prefix}:{key_value}", max_requests=max_requests, window_seconds=window_seconds):
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                {"code": "rate_limit_exceeded", "message": "محاولات كثيرة جداً — حاول لاحقاً"},
            )

    return _check
