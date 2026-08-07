"""
app/modules/owner/owner_policy.py
═══════════════════════════════════════════════════════════════════════
Owner Request Policy — Decision 0004, Isolation model item 4.

الفكرة: طبقة حظر الكتابة المركزية للـ owner session.
بدلاً من sweep بعد الحقيقة، هذا Registry يعمل كـ allowlist داخل
سلسلة التوثيق نفسها (dependency chain).

القاعدة: fail-closed بشكل صريح.
• أي route ليس في OWNER_WRITE_ALLOWLIST → 403 لـ owner.
• أي route جديد يُضاف لاحقاً إلى المشروع → محظور تلقائياً على owner
  بدون أي تعديل هنا (هذا هو المطلوب بالضبط).
• WebSocket endpoints غير موجودة في OpenAPI schema — تُرفض صراحةً
  عبر OWNER_BLOCKED_WS_PATHS المستخدم في get_websocket_user.

OWNER_WRITE_ALLOWLIST يحتوي route names (FastAPI r.name) بالضبط:
• auth routes — profile، 2FA، session management للـ owner نفسه.
• OwnerWatchlist writes — الـ owner يضيف/يحذف metrics مثبّتة.
• OwnerAllocationRule draft endpoints — مسودة قواعد التوزيع فقط
  (ليس activate — activation مقصورة على super_admin/accountant).

لا يمنع GET requests — يمنع فقط POST/PUT/PATCH/DELETE.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from app.core.deps import get_current_active_user, user_level

# ── الـ allowlist: route names المسموح بها للـ owner كـ writes ──────────────
# Route name = FastAPI's APIRoute.name (snake_case بالعادة اسم الدالة).
# نستخدم route name مش URL string — أكثر أماناً ضد تغييرات path parameters.
# راجع Decision 0004 §Isolation model item 4.
OWNER_WRITE_ALLOWLIST: frozenset[str] = frozenset({
    # ── Auth & session (للـ owner نفسه فقط) ──────────────────────────────
    "login",
    "logout",
    "refresh",
    "change_password",
    "setup_2fa",
    "enable_2fa",
    "disable_2fa",
    "regenerate_recovery_codes",
    "password_reset_request",
    "password_reset_confirm",
    "issue_step_up",
    "revoke_other_sessions",
    "revoke_session",
    "change_active_branch",
    "update_my_preferences",
    # ── Owner module writes (OwnerWatchlist) ──────────────────────────────
    "create_owner_watchlist_item",
    "delete_owner_watchlist_item",
    # ── Owner module writes (OwnerAllocationRule — drafts only) ───────────
    # NOTE: "activate_owner_allocation_rule" مش هنا عمداً — activation
    # مقصورة على super_admin/accountant فقط (راجع Decision 0004 §Unit
    # economics governance). لو حد حاول يضيفها هنا بدون تعديل Decision 0004
    # أولاً، التست fail-closed اللي بيتأكد من إن activate مش في الـ allowlist
    # هيفشل ويوقف الـ commit.
    "create_owner_allocation_rule_draft",
    "update_owner_allocation_rule_draft",
    "delete_owner_allocation_rule_draft",
})

# ── WebSocket paths محظورة صراحةً على owner ──────────────────────────────────
# مش موجودة في OpenAPI schema فمش تنفع فيها route-name check.
# تُستخدم في get_websocket_user في deps.py.
OWNER_BLOCKED_WS_PATHS: frozenset[str] = frozenset({
    "/dining/ws/kds/{branch_id}",   # KDS ticket stream
    "/beach/ws/map/{branch_id}",    # beach live map
    "/ws/analytics/kpis/{branch_id}",  # analytics KPIs websocket
})


def _is_owner_session(user) -> bool:
    """هل الـ user ده owner (مش super_admin الذي يتجاوز كل القيود)."""
    return user.role == "owner" and user_level(user) < 100


def enforce_owner_write_policy(request: Request, user=Depends(get_current_active_user)):
    """Dependency تُضاف على مستوى router.include_router للـ owner module.

    لو المستخدم owner:
      - GET/HEAD/OPTIONS → يعدي دائماً.
      - POST/PUT/PATCH/DELETE → يعدي فقط لو route name في OWNER_WRITE_ALLOWLIST.
      - أي route مجهول أو جديد → 403 (fail-closed).

    لو super_admin → يعدي دائماً (Decision 0003 invariant #1).
    لو أي دور آخر → هذا الـ dependency لا يُفعَّل على routes غير owner عادةً،
    لكن حتى لو استُدعي بالغلط → يمر (الحماية الأساسية على الـ routes الأخرى
    هي get_current_active_user + role dependencies الموجودة).
    """
    if not _is_owner_session(user):
        return  # super_admin أو غير owner → الـ dependency لا تتدخل

    method = request.method.upper()
    if method in ("GET", "HEAD", "OPTIONS"):
        return  # قراءة — مسموح دائماً

    # كتابة — نتحقق من الـ route name
    route = request.scope.get("route")
    route_name: str = getattr(route, "name", "") or ""

    if route_name not in OWNER_WRITE_ALLOWLIST:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "OWNER_WRITE_BLOCKED",
                "message": "حساب المالك للقراءة فقط — هذه العملية غير مسموحة",
                "route": route_name or "(unknown)",
            },
        )
