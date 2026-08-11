"""
app/modules/owner/owner_policy.py
═══════════════════════════════════════════════════════════════════════
Owner Request Policy — Decision 0004, Isolation model item 4.

الفكرة: طبقة حظر مركزية لجلسة الـ owner، لكل الـAPI مش بس موديول owner.
بدلاً من sweep بعد الحقيقة، هذا Registry يعمل كـ allowlist داخل سلسلة
التوثيق نفسها (dependency chain) — مربوطة على مستوى التطبيق كله
(``FastAPI(dependencies=[...])`` في ``app/main.py``)، مش على owner router
بس.

⚠️ 2026-08-11 — إصلاح باج أمني حقيقي: enforce_owner_write_policy كانت
موجودة من فترة (Decision 0004 Phase 2) لكن **مالهاش أي استدعاء في أي
مكان في المشروع خالص** — لا على مستوى owner router، ولا على مستوى
التطبيق. يعني owner كان يقدر يوصل لأي endpoint في المشروع (CRM/PMS/
Hub/HR...) وتتحقق فعليًا إمكانية إنشاء CRM Customer بطلب صالح. سبب
إضافي ليه الباج فضل مخفي: كل تستات "fail-closed" الموجودة كانت بتقبل
403 **أو 422 أو 404** كنجاح — والـpayloads المُرسلة كانت أصلاً غير
صالحة (ناقصة حقول إجبارية) فكانت بترجع 422 من Pydantic قبل ما توصل لأي
policy check خالص، بغض النظر عن وجود الـpolicy من عدمه. راجع
tests/test_owner_phase2.py وtests/test_owner_phase10.py — اتصلحوا في
نفس الدفعة دي بـpayloads صالحة وتأكيد 403 صريح فقط.

القاعدة: fail-closed بشكل صريح، للقراءة والكتابة معًا:
• owner على GET/HEAD/OPTIONS → مسموح فقط تحت مسار موديول owner نفسه
  (تقارير التجميع) أو /auth (إدارة الحساب الشخصي/الجلسة) أو /health.
  أي مسار تاني (CRM/PMS/HR/Hub/Inventory/...) محظور حتى لو قراءة بس —
  الفرونت إند الخاص بالمالك (frontend/apps/owner) أصلاً بينادي بس /owner
  و/auth (اتأكد بفحص الكود مباشرة)، فمفيش استخدام شرعي لأي حاجة تانية؛
  حماية إضافية ضد توكن owner مسروق/مُستخدَم مباشرة عبر API client خام.
• owner على POST/PUT/PATCH/DELETE → يعدي فقط لو route name في
  OWNER_WRITE_ALLOWLIST (نفس القاعدة القديمة، دلوقتي فعليًا مفعّلة).
• أي route جديد يُضاف لاحقاً إلى المشروع → محظور تلقائياً على owner
  بدون أي تعديل هنا (هذا هو المطلوب بالضبط — allowlist مش denylist).
• WebSocket endpoints غير موجودة في OpenAPI schema — تُرفض صراحةً
  عبر OWNER_BLOCKED_WS_PATHS المستخدم في get_websocket_user (منفصل
  تمامًا عن الـdependency هنا، مسار تحقق مختلف بالكامل).
• super_admin يعدّي دايمًا (Decision 0003 invariant #1) — بيمر من غير
  أي تدخل من الـpolicy دي خالص.
• أي حد مش owner (بما فيهم زوار غير مسجّلين على مسارات عامة) → الـpolicy
  دي no-op تمامًا، باقي الـauth chain بتاعة الـendpoint نفسه هو المسؤول.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Request, WebSocket, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import user_level

logger = logging.getLogger(__name__)

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

# ── مسارات القراءة المسموحة لـ owner ────────────────────────────────────────
# سطح موديول owner نفسه (تقارير التجميع كلها) + إدارة الحساب الشخصي/الجلسة
# + health check العام (بيانات غير حساسة). أي مسار تاني محظور حتى GET.
OWNER_READ_PATH_PREFIXES: tuple[str, ...] = (
    "/api/v1/owner",
    "/api/v1/auth",
    "/health",
)


def _is_owner_session(user) -> bool:
    """هل الـ user ده owner (مش super_admin الذي يتجاوز كل القيود)."""
    return user.role == "owner" and user_level(user) < 100


def _resolve_owner_session(request: Request, db: Session):
    """يحلّ الـ user من الـ Authorization header لو موجود، من غير ما يفرض
    مصادقة على مسارات عامة (عكس get_current_user اللي بترمي 401 لو مفيش
    token). الـpolicy دي إضافية فوق auth chain كل endpoint، مش بديل عنها —
    لو مفيش token خالص أو التوكن مش owner، ترجع None وتسيب الـendpoint
    يتصرف بمنطقه العادي (سواء كان عام أو عنده بوابة role تانية)."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.removeprefix("Bearer ")
    try:
        from app.core.deps import _resolve_user_from_token  # noqa: PLC0415
        return _resolve_user_from_token(token, db)
    except Exception:
        logger.exception("owner_policy: unexpected error resolving session token")
        return None


def enforce_owner_access_policy(request: Request = None, websocket: WebSocket = None, db: Session = Depends(get_db)):
    """Dependency مربوطة على مستوى التطبيق كله (``FastAPI(dependencies=...)``
    في app/main.py) — مش على owner router بس، ومش sweep بعد الحقيقة.

    السبب: الثغرة الحقيقية المُكتشفة كانت في راوترات موديولات تانية
    (crm/beach/hub/inventory) من غير أي بوابة owner-aware خالص — ربط الـ
    dependency دي على owner router بس كان هيسيبها بلا فايدة تمامًا، لأن
    owner أصلاً مش بيمر من خلاله وهو بيضرب /crm/customers مباشرة.

    ⚠️ dependency مربوطة على مستوى التطبيق بترتبط بكل route بما فيها
    WebSocket routes. باراميترين منفصلين (``request``/``websocket``، كل
    واحد بنوعه الحرفي مش Union) هو النمط الموثّق في FastAPI لـdependency
    مشتركة بين HTTP وWebSocket — FastAPI بيحقن الموجود فعليًا حسب نوع
    الـscope ويسيب التاني None، من غير كسر توليد OpenAPI schema (باج حقيقي
    حي اتكشف: تجربة ``Request | None`` كسرت كل route في المشروع بـ
    "Invalid args for response field"، وRequest إجباري بس كسر كل
    WebSocket route بـTypeError). حماية WebSocket لـowner موجودة أصلاً
    ومنفصلة تمامًا (get_websocket_user + OWNER_BLOCKED_WS_PATHS في
    deps.py) — الـpolicy هنا HTTP-only بتصميمها، فـno-op صحيح تمامًا لما
    request تبقى None (يعني السياق ده WebSocket).
    """
    if request is None:
        return
    user = _resolve_owner_session(request, db)
    if user is None or not _is_owner_session(user):
        return  # مش owner session — الـpolicy دي لا تتدخل خالص

    method = request.method.upper()

    if method in ("GET", "HEAD", "OPTIONS"):
        path = request.url.path
        if not path.startswith(OWNER_READ_PATH_PREFIXES):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "OWNER_READ_BLOCKED",
                    "message": "حساب المالك مقصور على شاشات المالك فقط",
                    "path": path,
                },
            )
        return

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
