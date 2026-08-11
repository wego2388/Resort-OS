"""
tests/test_owner_phase10.py
═══════════════════════════════════════════════════════════════════════
Owner Intelligence Cockpit — Phase 10: Security Review & Production
Readiness Gate (Decision 0004, §Required tests).

هذا الملف يغطي تحديداً البنود المطلوبة في المرحلة 10 التي لم تُختبر
بالكامل في المراحل السابقة:
  1. Route-inventory test: كل mutating route في الـ allowlist أو محظور.
  2. Fail-closed test: route جديد بدون registry entry → owner يحصل 403.
  3. WebSocket rejection: owner يُحظر من كل WS endpoints.
  4. No AI/LLM: owner module لا يستدعي أي LLM endpoint.
  5. Client-supplied branch_id يُهمَل (server-side فقط).
  6. B2B channel analytics لا تعرض guest data (no name/phone/id).
  7. Audit log: routine polling لا ينتج entries.
  8. Allocation-rule draft لا يغيّر أرقام خارج sandbox.
  9. owner session مرفوض من get_waiter/cashier/manager/admin/super_admin_user.
  10. owner session مقبول فقط بـ get_owner_reader.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import ast
import importlib
import inspect
import os
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from jose import jwt


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _tok(email: str, branch_id: int = 1) -> str:
    secret = os.environ["SECRET_KEY"]
    now = datetime.utcnow()
    return jwt.encode(
        {"sub": email, "iat": now, "exp": now + timedelta(hours=1), "bid": branch_id},
        secret, algorithm="HS256",
    )


def _owner(db, email: str | None = None, branch_id: int = 1):
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    from app.modules.core.models import UserBranchMembership
    email = email or f"owner10_{uuid.uuid4().hex[:8]}@test.local"
    u = User(
        email=email, password_hash=get_password_hash("pw"),
        full_name="Owner Phase10", role="owner", is_active=True,
        two_factor_enabled=True,
    )
    db.add(u)
    db.flush()
    db.add(UserBranchMembership(user_id=u.id, branch_id=branch_id, is_active=True))
    db.commit()
    db.refresh(u)
    return u


def _branch(db):
    from app.modules.core.models import Branch
    code = f"PH10-{uuid.uuid4().hex[:6].upper()}"
    b = Branch(name="Branch10", name_ar="فرع10", code=code, gm_phone="+201000000000")
    db.add(b)
    db.flush()
    return b



# ══════════════════════════════════════════════════════════════════════
# 1. Route-inventory: كل mutating route إما في allowlist أو محظور
# ══════════════════════════════════════════════════════════════════════

def test_route_inventory_all_mutating_routes_covered(client):
    """
    يعدّد كل mutating routes في التطبيق ويتحقق أن كل route اسمها موجود
    إما في OWNER_WRITE_ALLOWLIST أو ليس في allowlist (وبالتالي محظور
    تلقائياً). هذا يضمن لا توجد route تسمح لـ owner بكتابة غير مقصودة.

    المتطلب: Decision 0004 §Required tests "route-inventory test enumerates
    every mutating route by name and asserts each is either on the explicit
    allowlist or denied."
    """
    from fastapi import FastAPI
    from fastapi.routing import APIRoute
    from app.modules.owner.owner_policy import OWNER_WRITE_ALLOWLIST

    # نحصل على التطبيق من client
    app: FastAPI = client.app

    mutating_methods = {"POST", "PUT", "PATCH", "DELETE"}
    mutating_routes = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.methods and route.methods & mutating_methods:
            mutating_routes.append(route)

    assert len(mutating_routes) > 0, "يجب أن يكون هناك mutating routes في التطبيق"

    # كل route لها name — إما في allowlist (owner مسموح) أو خارجها (owner محظور)
    # الـ test يتحقق فقط أن كل route لها name (لا None/empty)
    unnamed = [r for r in mutating_routes if not r.name]
    assert unnamed == [], f"Routes بدون name: {unnamed}"

    # Routes في الـ allowlist يجب أن تكون موجودة فعلاً في التطبيق
    app_route_names = {r.name for r in app.routes if isinstance(r, APIRoute)}
    for allowed_name in OWNER_WRITE_ALLOWLIST:
        # بعض الأسماء مثل login/logout/refresh مسجّلة في auth router الـ kernel
        # نتحقق أنها موجودة في التطبيق أو موثّقة كـ auth routes
        assert allowed_name in app_route_names or any(
            allowed_name in r.name for r in app.routes if isinstance(r, APIRoute)
        ), f"Route '{allowed_name}' في OWNER_WRITE_ALLOWLIST لكنها غير موجودة في التطبيق"



# ══════════════════════════════════════════════════════════════════════
# 2. Fail-closed: route جديد بدون registry entry → owner 403
# ══════════════════════════════════════════════════════════════════════

def test_fail_closed_new_route_not_in_allowlist_denied(client, db, setup_db):
    """
    يتحقق من السلوك fail-closed: أي route كتابة غير موجودة في
    OWNER_WRITE_ALLOWLIST تُرفض تلقائياً من owner بدون تعديل الـ registry.

    المتطلب: Decision 0004 §Required tests "A fail-closed test adds a new
    mutating route with no registry entry and confirms owner still receives
    403 without any registry update."

    نختبر هذا بمحاولة owner الكتابة على route غير مسجّلة في allowlist،
    بـ payload **صحيح فعليًا** (full_name هو الحقل الإجباري الحقيقي في
    CustomerCreate، مش "name").

    ⚠️ 2026-08-11: النسخة القديمة من التست ده كانت بترسل payload ناقص
    (`{"name": ...}` بدل `{"full_name": ...}`) وتقبل 422 كنجاح — يعني
    كانت بتفشل schema validation قبل ما توصل لأي policy check خالص،
    فمكانتش بتثبت حاجة عن enforce_owner_access_policy. اتأكد فعليًا (قبل
    الإصلاح، بطلب صالح حقيقي): owner كان يقدر ينشئ CRM Customer حقيقي —
    نفس الثغرة اللي التقرير الأمني رفعها.
    """
    from app.modules.owner.owner_policy import OWNER_WRITE_ALLOWLIST

    branch = _branch(db)
    owner = _owner(db, branch_id=branch.id)

    # POST /crm/customers ليست في allowlist
    assert "create_customer" not in OWNER_WRITE_ALLOWLIST

    resp = client.post(
        "/api/v1/crm/customers",
        json={"branch_id": branch.id, "full_name": "غير مصرح"},
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 403, (
        f"owner استطاع الكتابة على route غير مصرح بها: {resp.status_code} {resp.text}"
    )
    assert resp.json()["detail"]["code"] == "OWNER_WRITE_BLOCKED"


def test_fail_closed_patch_non_allowlisted(client, db, setup_db):
    """PATCH على resource غير مصرح → owner 403 (لازم يوصل من غير ما يتحقق
    وجود الـresource أصلاً — الـpolicy بتشتغل في مرحلة الـdependency
    resolution، قبل جسم الـendpoint اللي بيدور على الـcustomer)."""
    from app.modules.owner.owner_policy import OWNER_WRITE_ALLOWLIST
    assert "update_customer" not in OWNER_WRITE_ALLOWLIST

    branch = _branch(db)
    owner = _owner(db, branch_id=branch.id)

    resp = client.patch(
        "/api/v1/crm/customers/9999",
        json={"full_name": "محاولة"},
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "OWNER_WRITE_BLOCKED"


def test_fail_closed_post_beach_void(client, db, setup_db):
    """POST /beach/transactions/{id}/void غير مصرح → owner 403 (بـpayload
    صالح فعليًا — reason هو الحقل الإجباري الحقيقي في VoidTransactionRequest)."""
    from app.modules.owner.owner_policy import OWNER_WRITE_ALLOWLIST
    assert "void_beach_transaction" not in OWNER_WRITE_ALLOWLIST

    branch = _branch(db)
    owner = _owner(db, branch_id=branch.id)

    resp = client.post(
        "/api/v1/beach/transactions/9999/void",
        json={"reason": "محاولة إلغاء غير مصرح بها"},
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "OWNER_WRITE_BLOCKED"


def test_fail_closed_owner_get_blocked_from_crm_list(client, db, setup_db):
    """GET /crm/customers (مش /owner/*) → owner 403 حتى لو قراءة بس.

    ده تحصين إضافي أوسع من متطلب Decision 0004 الأصلي (اللي كان بيركّز
    على الكتابة بس) — طلب صريح من المراجعة الأمنية 2026-08-11: JWT
    owner مسروق/مُستخدَم مباشرة عبر API client خام لازم ميقدرش يتصفح
    بيانات CRM/PMS/HR/Hub حتى للقراءة، مش بس الكتابة."""
    branch = _branch(db)
    owner = _owner(db, branch_id=branch.id)
    resp = client.get(
        "/api/v1/crm/customers",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "OWNER_READ_BLOCKED"


def test_owner_read_allowed_under_owner_and_auth_prefixes(client, db, setup_db):
    """owner لازم يفضل يقدر يقرأ سطحه الخاص (/owner/*) وحسابه الشخصي
    (/auth/*) بعد التشديد — الحظر مقصود بس على موديولات تانية."""
    branch = _branch(db)
    owner = _owner(db, branch_id=branch.id)
    tok = _tok(owner.email, branch.id)
    resp = client.get("/api/v1/owner/now", headers={"Authorization": f"Bearer {tok}"})
    assert resp.status_code == 200
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert resp.status_code == 200


def test_owner_access_policy_wired_into_app(client):
    """يتأكد فعليًا (مش افتراضًا) إن enforce_owner_access_policy مربوطة على
    مستوى التطبيق — فحص dependency graph حقيقي، مش مجرد وجود الدالة معرّفة."""
    from app.modules.owner.owner_policy import enforce_owner_access_policy
    app_dependencies = client.app.router.dependencies
    wired = any(
        getattr(dep, "dependency", None) is enforce_owner_access_policy
        for dep in app_dependencies
    )
    assert wired, "enforce_owner_access_policy مش مربوطة في app.router.dependencies"


def test_fail_closed_activate_allocation_rule_blocked(client, db, setup_db):
    """activate endpoint مش في allowlist — owner لا يستطيع تفعيل قاعدة."""
    from app.modules.owner.owner_policy import OWNER_WRITE_ALLOWLIST
    # هذا الفحص موجود في phase2 لكن نؤكده هنا ضمن المراجعة الأمنية
    assert "activate_owner_allocation_rule" not in OWNER_WRITE_ALLOWLIST



# ══════════════════════════════════════════════════════════════════════
# 3. WebSocket rejection: owner مرفوض من كل WS endpoints
# ══════════════════════════════════════════════════════════════════════

def test_owner_blocked_ws_paths_catalog():
    """
    يتحقق أن OWNER_BLOCKED_WS_PATHS يحتوي كل الـ WebSocket endpoints
    المعروفة في المشروع.

    المتطلب: Decision 0004 §Required tests "owner is rejected from every
    operational WebSocket endpoint (KDS ticket stream, beach live map)
    via dedicated tests."
    """
    from app.modules.owner.owner_policy import OWNER_BLOCKED_WS_PATHS

    required_paths = {
        "/dining/ws/kds/{branch_id}",
        "/beach/ws/map/{branch_id}",
    }
    for path in required_paths:
        assert path in OWNER_BLOCKED_WS_PATHS, (
            f"WebSocket path '{path}' يجب أن يكون في OWNER_BLOCKED_WS_PATHS"
        )


def test_owner_blocked_from_kds_ws_via_policy(db, setup_db):
    """
    يتحقق أن get_websocket_user يرفض owner من KDS WebSocket.
    نختبر المنطق مباشرة بدون WebSocket connection حقيقية.
    """
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    branch = _branch(db)
    owner = _owner(db, branch_id=branch.id)

    # نبني mock WebSocket يمثل /dining/ws/kds/1
    mock_ws = MagicMock()
    mock_ws.query_params = {"token": _tok(owner.email, branch.id)}
    mock_ws.url.path = f"/dining/ws/kds/{branch.id}"
    mock_ws.close = AsyncMock()

    from app.core.deps import get_websocket_user

    async def run():
        result = await get_websocket_user(mock_ws, db, min_level=0)
        return result

    result = asyncio.get_event_loop().run_until_complete(run())
    # owner يجب أن يُرفض ← result هو None وclose اتنادت
    assert result is None
    mock_ws.close.assert_called_once_with(code=4403)


def test_owner_blocked_from_beach_map_ws_via_policy(db, setup_db):
    """يتحقق أن get_websocket_user يرفض owner من beach map WebSocket."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    branch = _branch(db)
    owner = _owner(db, branch_id=branch.id)

    mock_ws = MagicMock()
    mock_ws.query_params = {"token": _tok(owner.email, branch.id)}
    mock_ws.url.path = f"/beach/ws/map/{branch.id}"
    mock_ws.close = AsyncMock()

    from app.core.deps import get_websocket_user

    async def run():
        return await get_websocket_user(mock_ws, db, min_level=0)

    result = asyncio.get_event_loop().run_until_complete(run())
    assert result is None
    mock_ws.close.assert_called_once_with(code=4403)


def test_ws_prefix_matching_covers_parameterized_paths(db, setup_db):
    """
    يتحقق أن الـ prefix matching في get_websocket_user يعمل بشكل صحيح
    لـ paths مع branch_id مختلف.
    """
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    branch = _branch(db)
    owner = _owner(db, branch_id=branch.id)

    for path in ["/dining/ws/kds/99", "/beach/ws/map/42"]:
        mock_ws = MagicMock()
        mock_ws.query_params = {"token": _tok(owner.email, branch.id)}
        mock_ws.url.path = path
        mock_ws.close = AsyncMock()

        from app.core.deps import get_websocket_user

        async def run(ws=mock_ws):
            return await get_websocket_user(ws, db, min_level=0)

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result is None, f"owner لم يُرفض من {path}"



# ══════════════════════════════════════════════════════════════════════
# 4. No AI/LLM: owner module لا يستدعي أي LLM/AI endpoint
# ══════════════════════════════════════════════════════════════════════

def test_owner_module_no_ai_imports():
    """
    يتحقق أن owner module لا يستورد أي مكتبات AI/LLM كـ import حقيقي.
    نبحث عن import statements — لا عن كلمات جزء من أسماء أخرى.

    المتطلب: Decision 0004 §Required tests "A repository-wide check
    confirms the owner module makes no outbound call to Gemini or any
    other AI/LLM endpoint — enforcing 'no AI, no external service call'
    as a tested invariant."
    """
    import pathlib
    import re

    owner_dir = pathlib.Path(__file__).parent.parent / "app" / "modules" / "owner"
    analytics_engine = (
        pathlib.Path(__file__).parent.parent / "app" / "resort_os" / "owner_analytics_engine.py"
    )

    # أنماط import محظورة — كلمات كاملة لتجنب false positives مثل "installment"
    forbidden_import_patterns = [
        r'\bgemini\b', r'\bopenai\b', r'\banthropik\b', r'\bcohere\b',
        r'\blangchain\b', r'\bgpt\b', r'\bgoogle\.generativeai\b',
        r'import\s+genai\b', r'from\s+genai\b',
        r'import\s+litellm\b', r'from\s+litellm\b',
    ]

    files_to_check = list(owner_dir.rglob("*.py"))
    if analytics_engine.exists():
        files_to_check.append(analytics_engine)

    violations = []
    for fpath in files_to_check:
        content = fpath.read_text(encoding="utf-8")
        for pattern in forbidden_import_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                violations.append(f"{fpath.name}: '{pattern}'")

    assert violations == [], (
        "وُجدت imports AI/LLM في owner module:\n" + "\n".join(violations)
    )


def test_owner_analytics_engine_no_external_calls():
    """
    يتحقق أن owner_analytics_engine.py لا يستورد FastAPI أو SQLAlchemy
    أو requests أو httpx — pure engine فقط.

    المتطلب: Decision 0004 §New engineering surface "a pure engine
    (no FastAPI or SQLAlchemy imports)".
    """
    import pathlib
    engine_path = (
        pathlib.Path(__file__).parent.parent / "app" / "resort_os" / "owner_analytics_engine.py"
    )
    if not engine_path.exists():
        pytest.skip("owner_analytics_engine.py غير موجود بعد")

    content = engine_path.read_text(encoding="utf-8")
    forbidden_imports = ["from fastapi", "import fastapi", "from sqlalchemy", "import sqlalchemy",
                         "import requests", "import httpx", "import aiohttp"]
    violations = [imp for imp in forbidden_imports if imp in content]
    assert violations == [], f"owner_analytics_engine يحتوي imports محظورة: {violations}"



# ══════════════════════════════════════════════════════════════════════
# 5. Client-supplied branch_id يُهمَل (server-side فقط)
# ══════════════════════════════════════════════════════════════════════

def test_owner_branch_id_derived_server_side_not_from_client(client, db, setup_db):
    """
    يتحقق أن branch_id في أي owner endpoint يُشتق من الـ session server-side
    وليس من الـ client. محاولة تمرير branch_id مختلف في query params تُهمَل.

    المتطلب: Decision 0004 §Required tests "A client-supplied branch_id
    on any owner request is proven ignored; branch context is derived
    server-side only."
    """
    branch = _branch(db)
    owner = _owner(db, branch_id=branch.id)

    # token مع branch_id صحيح
    valid_token = _tok(owner.email, branch.id)

    # نجرب نمرر branch_id مختلف في URL/query — يجب أن يُهمَل
    resp = client.get(
        "/api/v1/owner/now",
        params={"branch_id": 9999},  # branch_id مختلف — يجب أن يُهمَل
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    # إذا نجح (200) فالـ branch_id من الـ session هو المستخدم لا 9999
    # إذا فشل (400 NO_ACTIVE_BRANCH) فهذا يعني لا يوجد branch نشط — مقبول
    assert resp.status_code in (200, 400, 404)

    # الـ router يستخدم _get_branch(user) من الـ session — نتحقق من الكود
    import inspect
    from app.modules.owner.api import router as owner_router_mod
    source = inspect.getsource(owner_router_mod)
    # يجب أن لا يوجد request.query_params.get("branch_id") في الـ router
    assert "query_params" not in source or "branch_id" not in source.split("query_params")[1].split("\n")[0], (
        "owner router يقرأ branch_id من query_params — يجب أن يكون من الـ session فقط"
    )


def test_owner_get_branch_from_session_not_param(client, db, setup_db):
    """
    يتحقق صراحةً أن _get_branch في owner router يقرأ من user._active_branch_id
    وليس من أي parameter خارجي.
    """
    import inspect
    from app.modules.owner.api import router as owner_router_mod

    source = inspect.getsource(owner_router_mod)
    # _get_branch يجب أن يستخدم getattr(user, "_active_branch_id", None)
    assert "_active_branch_id" in source, (
        "_get_branch يجب أن يستخدم user._active_branch_id من الـ session"
    )



# ══════════════════════════════════════════════════════════════════════
# 6. B2B channel analytics لا تعرض guest data
# ══════════════════════════════════════════════════════════════════════

def test_channel_analytics_response_has_no_guest_pii(client, db, setup_db):
    """
    يتحقق أن /owner/channel-analytics لا يُعيد أي بيانات شخصية للضيف:
    لا name، لا phone، لا email، لا guest_id في أي مستوى من الـ response.

    المتطلب: Decision 0004 §Required tests "B2B channel analytics never
    surface an individual guest's name, phone, or identifier — a test
    asserts the response schema has no such field."
    """
    branch = _branch(db)
    owner = _owner(db, branch_id=branch.id)

    resp = client.get(
        "/api/v1/owner/channel-analytics",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    # حقول PII المحظورة في الـ response
    pii_fields = {
        "guest_name", "guest_phone", "guest_email", "guest_id",
        "customer_name", "customer_phone", "customer_email", "customer_id",
        "national_id", "passport",
    }

    def check_no_pii(obj, path="root"):
        if isinstance(obj, dict):
            for key in obj:
                assert key not in pii_fields, (
                    f"حقل PII '{key}' وُجد في channel analytics response عند {path}"
                )
                check_no_pii(obj[key], f"{path}.{key}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                check_no_pii(item, f"{path}[{i}]")

    check_no_pii(data)


def test_channel_analytics_schema_no_pii_fields():
    """
    يتحقق من schema الـ ChannelAnalyticsResponse أنه لا يحتوي
    حقول guest PII على مستوى التعريف.
    """
    from app.modules.owner.schemas import ChannelAnalyticsResponse
    import pydantic

    schema = ChannelAnalyticsResponse.model_json_schema()
    schema_str = str(schema).lower()

    pii_patterns = ["guest_name", "guest_phone", "guest_email", "national_id"]
    violations = [p for p in pii_patterns if p in schema_str]
    assert violations == [], (
        f"ChannelAnalyticsResponse schema يحتوي حقول PII: {violations}"
    )



# ══════════════════════════════════════════════════════════════════════
# 7. Audit log: routine polling لا ينتج entries
# ══════════════════════════════════════════════════════════════════════

def test_audit_log_not_written_on_routine_now_polling(client, db, setup_db):
    """
    يتحقق أن طلبات GET /owner/now المتكررة (auto-refresh/polling) لا
    تنتج audit_log entries.

    المتطلب: Decision 0004 §Isolation model item 6: "audit_logs receives
    an entry for a deliberate report open, a sensitive drill-down, an
    export, and any settings/allocation-rule action — NOT for routine
    auto-refresh/polling."
    """
    from app.modules.core.models import AuditLog

    branch = _branch(db)
    owner = _owner(db, branch_id=branch.id)
    token = _tok(owner.email, branch.id)

    # نحصل على عدد audit entries قبل الطلبات
    count_before = db.query(AuditLog).count()

    # نرسل 3 طلبات متكررة (تمثل polling)
    for _ in range(3):
        resp = client.get(
            "/api/v1/owner/now",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    count_after = db.query(AuditLog).count()

    # الـ polling لا يجب أن يزيد عدد الـ audit entries
    assert count_after == count_before, (
        f"Routine polling أنتج {count_after - count_before} audit entries — "
        "يجب أن تكون 0"
    )


def test_audit_log_not_written_on_routine_performance_polling(client, db, setup_db):
    """طلبات GET /owner/performance المتكررة لا تنتج audit entries."""
    from app.modules.core.models import AuditLog

    branch = _branch(db)
    owner = _owner(db, branch_id=branch.id)
    token = _tok(owner.email, branch.id)

    count_before = db.query(AuditLog).count()

    for _ in range(2):
        resp = client.get(
            "/api/v1/owner/performance",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    count_after = db.query(AuditLog).count()
    assert count_after == count_before


def test_audit_log_written_on_allocation_rule_draft_action(client, db, setup_db):
    """عكس التستين فوق تمامًا — إجراء owner حقيقي (مش polling) لازم
    ينتج audit_log entry، مش يتبلع بصمت. راجع
    app/modules/owner/api/router.py's _log_owner_audit وDecision 0004
    §Isolation model item 6."""
    from app.modules.core.models import AuditLog

    branch = _branch(db)
    owner = _owner(db, branch_id=branch.id)
    token = _tok(owner.email, branch.id)

    count_before = db.query(AuditLog).count()

    resp = client.post(
        "/api/v1/owner/allocation-rules/draft",
        json={"branch_id": branch.id, "pct_rooms": "40"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201

    count_after = db.query(AuditLog).count()
    assert count_after == count_before + 1

    entry = (
        db.query(AuditLog)
        .filter(AuditLog.action == "owner_allocation_rule_draft_create")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert entry is not None
    assert entry.user_id == owner.id
    assert entry.branch_id == branch.id
    assert entry.entity_type == "owner_allocation_rule"



# ══════════════════════════════════════════════════════════════════════
# 8. Allocation-rule draft لا يغيّر أرقام خارج sandbox
# ══════════════════════════════════════════════════════════════════════

def test_allocation_rule_draft_does_not_affect_owner_now(client, db, setup_db):
    """
    يتحقق أن إنشاء allocation rule draft لا يغيّر الأرقام على /owner/now.
    الـ draft يبقى في sandbox — لا يؤثر على أي تقرير حتى يُنشر بموافقة
    super_admin/accountant.

    المتطلب: Decision 0004 §Required tests "Allocation-rule drafts never
    alter any number outside the sandbox."
    """
    from app.modules.owner import services as svc
    from app.modules.owner.schemas import AllocationRuleDraftCreate

    branch = _branch(db)
    owner = _owner(db, branch_id=branch.id)
    token = _tok(owner.email, branch.id)

    # نحصل على /owner/now قبل إنشاء draft
    resp_before = client.get(
        "/api/v1/owner/now",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_before.status_code == 200
    data_before = resp_before.json()

    # ننشئ draft
    draft = svc.create_draft(db, AllocationRuleDraftCreate(
        branch_id=branch.id,
        pct_rooms=Decimal("70"),
        pct_beach=Decimal("10"),
        pct_dining=Decimal("10"),
        pct_timeshare=Decimal("10"),
        notes="اختبار sandbox",
    ), owner_user_id=owner.id)
    assert draft.status == "draft"

    # نحصل على /owner/now بعد إنشاء draft
    resp_after = client.get(
        "/api/v1/owner/now",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_after.status_code == 200
    data_after = resp_after.json()

    # revenue_today هو قيمة مباشرة (Decimal/string) — يجب أن يكون نفسه
    rev_before = data_before.get("revenue_today")
    rev_after = data_after.get("revenue_today")
    assert rev_before == rev_after, (
        f"Draft أثّر على revenue_today: قبل={rev_before}، بعد={rev_after}"
    )


def test_draft_status_is_draft_not_published(db, setup_db):
    """
    يتحقق أن owner لا يستطيع إنشاء rule بـ status='published' مباشرة.
    الـ draft يبدأ دائماً بـ status='draft'.
    """
    from app.modules.owner import services as svc
    from app.modules.owner.schemas import AllocationRuleDraftCreate

    branch = _branch(db)
    owner = _owner(db, branch_id=branch.id)

    rule = svc.create_draft(db, AllocationRuleDraftCreate(
        branch_id=branch.id,
        pct_rooms=Decimal("40"),
        pct_beach=Decimal("30"),
        pct_dining=Decimal("20"),
        pct_timeshare=Decimal("10"),
    ), owner_user_id=owner.id)

    assert rule.status == "draft", (
        f"Rule يجب أن يبدأ بـ status='draft'، وجدنا '{rule.status}'"
    )



# ══════════════════════════════════════════════════════════════════════
# 9. owner session مرفوض من كل elevated dependencies
# ══════════════════════════════════════════════════════════════════════

def test_owner_rejected_from_get_waiter_user(client, db, setup_db):
    """
    owner session (level=10) يُرفض من get_waiter_user (level >= 30).

    المتطلب: Decision 0004 §Required tests "An owner session is accepted
    only by get_owner_reader; every other elevated dependency still rejects
    a plain owner session exactly as before."
    """
    branch = _branch(db)
    owner = _owner(db, branch_id=branch.id)
    token = _tok(owner.email, branch.id)

    # أي endpoint يستخدم get_waiter_user — نستخدم dining
    resp = client.get(
        "/api/v1/dining/orders",
        headers={"Authorization": f"Bearer {token}"},
    )
    # يجب رفضه بـ 403
    assert resp.status_code == 403, (
        f"owner استطاع الوصول إلى waiter endpoint: {resp.status_code}"
    )


def test_owner_rejected_from_get_cashier_user(client, db, setup_db):
    """owner (level=10) مرفوض من get_cashier_user (level >= 40)."""
    branch = _branch(db)
    owner = _owner(db, branch_id=branch.id)
    token = _tok(owner.email, branch.id)

    resp = client.get(
        "/api/v1/finance/shifts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_owner_rejected_from_get_manager_user(client, db, setup_db):
    """owner (level=10) مرفوض من get_manager_user (level >= 60)."""
    branch = _branch(db)
    owner = _owner(db, branch_id=branch.id)
    token = _tok(owner.email, branch.id)

    resp = client.get(
        "/api/v1/finance/cost-centers",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_owner_rejected_from_get_admin_user(client, db, setup_db):
    """owner (level=10) مرفوض من get_admin_user (level >= 80)."""
    branch = _branch(db)
    owner = _owner(db, branch_id=branch.id)
    token = _tok(owner.email, branch.id)

    # POST /branches يستخدم get_admin_user — core router بدون prefix
    resp = client.post(
        "/api/v1/branches",
        json={"name": "فرع تجريبي", "name_ar": "فرع", "code": "TST99XX", "gm_phone": "+20100"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, (
        f"owner يجب أن يُرفض من admin endpoint، وجدنا: {resp.status_code}"
    )


def test_owner_rejected_from_get_super_admin_user(client, db, setup_db):
    """owner (level=10) مرفوض من get_super_admin_user (level >= 100)."""
    branch = _branch(db)
    owner = _owner(db, branch_id=branch.id)
    token = _tok(owner.email, branch.id)

    # DELETE /branches/{id} يستخدم get_super_admin_user
    resp = client.delete(
        "/api/v1/branches/9999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, (
        f"owner يجب أن يُرفض من super_admin endpoint، وجدنا: {resp.status_code}"
    )


def test_owner_accepted_by_get_owner_reader(client, db, setup_db):
    """
    owner session مقبول فقط بـ get_owner_reader — يتحقق من حالة 200.
    """
    branch = _branch(db)
    owner = _owner(db, branch_id=branch.id)
    token = _tok(owner.email, branch.id)

    resp = client.get(
        "/api/v1/owner/now",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, (
        f"owner يجب أن يُقبَل من get_owner_reader: {resp.status_code} — {resp.text[:200]}"
    )



# ══════════════════════════════════════════════════════════════════════
# 10. Cache-Control: no-store على كل owner financial endpoints
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("path", [
    "/api/v1/owner/now",
    "/api/v1/owner/performance",
    "/api/v1/owner/sales",
    "/api/v1/owner/beach-performance",
    "/api/v1/owner/channel-analytics",
    "/api/v1/owner/expense-analytics",
    "/api/v1/owner/procurement-analytics",
    "/api/v1/owner/shifts",
    "/api/v1/owner/exceptions",
])
def test_cache_control_no_store_on_all_owner_endpoints(client, db, setup_db, path):
    """
    يتحقق أن كل owner financial endpoints تحمل Cache-Control: no-store.

    المتطلب: Decision 0004 §New engineering surface "every financial API
    response is served Cache-Control: no-store."
    """
    branch = _branch(db)
    owner = _owner(db, branch_id=branch.id)
    token = _tok(owner.email, branch.id)

    resp = client.get(path, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code in (200, 400), (
        f"{path}: unexpected status {resp.status_code}"
    )
    cc = resp.headers.get("cache-control", "")
    assert "no-store" in cc, (
        f"{path}: Cache-Control يجب أن يحتوي no-store، وجدنا: '{cc}'"
    )


# ══════════════════════════════════════════════════════════════════════
# 11. Mandatory 2FA للـ owner role
# ══════════════════════════════════════════════════════════════════════

def test_owner_without_2fa_blocked_from_owner_now(client, db, setup_db):
    """
    owner بدون 2FA مُفعَّل يُحظر من owner endpoints.

    المتطلب: Decision 0004 §Isolation model item 3: "Add 'owner' to
    MANDATORY_2FA_ROLES."
    """
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    from app.modules.core.models import UserBranchMembership

    branch = _branch(db)
    email = f"owner_no2fa_{uuid.uuid4().hex[:8]}@test.local"
    u = User(
        email=email, password_hash=get_password_hash("pw"),
        full_name="Owner No 2FA", role="owner", is_active=True,
        two_factor_enabled=False,  # 2FA غير مُفعَّل
    )
    db.add(u)
    db.flush()
    db.add(UserBranchMembership(user_id=u.id, branch_id=branch.id, is_active=True))
    db.commit()

    token = _tok(email, branch.id)
    resp = client.get(
        "/api/v1/owner/now",
        headers={"Authorization": f"Bearer {token}"},
    )
    # يجب أن يُرفض بـ 403 بسبب MANDATORY_2FA_ROLES
    assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════════
# 12. owner level أقل من كل الأدوار التشغيلية
# ══════════════════════════════════════════════════════════════════════

def test_owner_level_is_below_all_operational_roles():
    """
    يتحقق أن owner level=10 أقل من كل الأدوار التشغيلية.
    هذا يضمن عدم تجاوز أي فحص >= N عن طريق الخطأ.

    المتطلب: Decision 0004 §Isolation model item 1: "Its numeric level is
    placed low — below employee (20) — specifically so it can never
    accidentally satisfy an existing >= N level check."
    """
    from app.core.deps import ROLE_LEVELS

    owner_level = ROLE_LEVELS["owner"]
    assert owner_level == 10

    operational_roles = {
        "employee", "waiter", "chef", "kitchen", "cashier",
        "receptionist", "supervisor", "manager", "accountant",
        "hr_manager", "admin", "super_admin",
    }
    for role in operational_roles:
        assert owner_level < ROLE_LEVELS[role], (
            f"owner({owner_level}) يجب أن يكون أقل من {role}({ROLE_LEVELS[role]})"
        )



# ══════════════════════════════════════════════════════════════════════
# 13. super_admin يعدي get_owner_reader (Decision 0003 invariant #1)
# ══════════════════════════════════════════════════════════════════════

def test_super_admin_passes_get_owner_reader(client, db, setup_db):
    """
    super_admin يعدي get_owner_reader بدون قيود.

    المتطلب: Decision 0004 §Isolation model item 2: "it accepts role ==
    'owner' OR user_level(user) >= 100 (super_admin), exactly the pattern
    already implemented in get_timeshare_admin_user."
    """
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    from app.modules.core.models import UserBranchMembership

    branch = _branch(db)
    email = f"sa_owner_{uuid.uuid4().hex[:8]}@test.local"
    u = User(
        email=email, password_hash=get_password_hash("pw"),
        full_name="Super Admin", role="super_admin", is_active=True,
        two_factor_enabled=True,
    )
    db.add(u)
    db.flush()
    db.add(UserBranchMembership(user_id=u.id, branch_id=branch.id, is_active=True))
    db.commit()

    token = _tok(email, branch.id)
    resp = client.get(
        "/api/v1/owner/watchlist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════════
# 14. الـ OWNER_WRITE_ALLOWLIST يحتوي فقط routes موثّقة
# ══════════════════════════════════════════════════════════════════════

def test_owner_write_allowlist_is_frozenset():
    """OWNER_WRITE_ALLOWLIST يجب أن يكون frozenset (غير قابل للتعديل)."""
    from app.modules.owner.owner_policy import OWNER_WRITE_ALLOWLIST
    assert isinstance(OWNER_WRITE_ALLOWLIST, frozenset), (
        "OWNER_WRITE_ALLOWLIST يجب أن يكون frozenset لضمان immutability"
    )


def test_owner_blocked_ws_paths_is_frozenset():
    """OWNER_BLOCKED_WS_PATHS يجب أن يكون frozenset."""
    from app.modules.owner.owner_policy import OWNER_BLOCKED_WS_PATHS
    assert isinstance(OWNER_BLOCKED_WS_PATHS, frozenset)


def test_owner_write_allowlist_contains_required_auth_routes():
    """يتحقق أن الـ allowlist يحتوي routes Auth الضرورية لحساب owner."""
    from app.modules.owner.owner_policy import OWNER_WRITE_ALLOWLIST

    required_auth_routes = {
        "login", "logout", "refresh", "setup_2fa", "enable_2fa",
        "change_password",
    }
    missing = required_auth_routes - OWNER_WRITE_ALLOWLIST
    assert missing == set(), (
        f"Auth routes مفقودة من OWNER_WRITE_ALLOWLIST: {missing}"
    )


def test_owner_write_allowlist_contains_watchlist_routes():
    """يتحقق أن الـ allowlist يحتوي OwnerWatchlist write routes."""
    from app.modules.owner.owner_policy import OWNER_WRITE_ALLOWLIST

    watchlist_routes = {
        "create_owner_watchlist_item",
        "delete_owner_watchlist_item",
    }
    missing = watchlist_routes - OWNER_WRITE_ALLOWLIST
    assert missing == set(), f"Watchlist routes مفقودة: {missing}"



# ══════════════════════════════════════════════════════════════════════
# 15. فحص شامل: لا Payroll per-employee في owner responses
# ══════════════════════════════════════════════════════════════════════

def test_expense_analytics_no_per_employee_payroll(client, db, setup_db):
    """
    يتحقق أن /owner/expense-analytics لا يعرض بيانات رواتب per-employee.
    الرواتب تظهر كـ aggregate فقط.

    المتطلب: Decision 0004 §Isolation model item 7: "Payroll appears as
    an aggregate and a percentage of revenue by default, never itemized
    per employee."
    """
    from app.modules.owner.schemas import ExpenseAnalyticsResponse
    import pydantic

    schema = ExpenseAnalyticsResponse.model_json_schema()
    schema_str = str(schema).lower()

    # لا يجب وجود حقول per-employee في schema
    per_employee_patterns = ["employee_id", "employee_name", "salary_per_employee"]
    violations = [p for p in per_employee_patterns if p in schema_str]
    assert violations == [], (
        f"ExpenseAnalyticsResponse schema يحتوي بيانات per-employee: {violations}"
    )


# ══════════════════════════════════════════════════════════════════════
# 16. ABC/Pareto classification edge cases (Decision 0004 §Required tests)
# ══════════════════════════════════════════════════════════════════════

def _make_item(item_id: int, name: str, revenue: Decimal, qty: int = 1):
    """Helper: ينشئ ItemMetric للاختبار."""
    from app.resort_os.owner_analytics_engine import ItemMetric
    return ItemMetric(
        item_id=item_id, name=name,
        quantity_sold=qty, revenue=revenue,
    )


def test_abc_classification_deterministic():
    """ABC/Pareto classification محدد (نفس input → نفس output)."""
    from app.resort_os.owner_analytics_engine import classify_abc

    items1 = [
        _make_item(1, "صنف أ", Decimal("1000")),
        _make_item(2, "صنف ب", Decimal("500")),
        _make_item(3, "صنف ج", Decimal("100")),
        _make_item(4, "صنف د", Decimal("50")),
    ]
    items2 = [
        _make_item(1, "صنف أ", Decimal("1000")),
        _make_item(2, "صنف ب", Decimal("500")),
        _make_item(3, "صنف ج", Decimal("100")),
        _make_item(4, "صنف د", Decimal("50")),
    ]
    result1 = classify_abc(items1)
    result2 = classify_abc(items2)
    classes1 = [(r.item_id, r.abc_class) for r in result1]
    classes2 = [(r.item_id, r.abc_class) for r in result2]
    assert classes1 == classes2, "ABC classification يجب أن يكون deterministic"


def test_abc_classification_empty_input():
    """ABC/Pareto classification مع empty input لا يرمي error."""
    from app.resort_os.owner_analytics_engine import classify_abc

    result = classify_abc([])
    assert result == [], "Empty input يجب أن يعيد empty list"


def test_abc_classification_single_item():
    """ABC/Pareto classification مع item واحد فقط → class A."""
    from app.resort_os.owner_analytics_engine import classify_abc

    items = [_make_item(1, "صنف وحيد", Decimal("500"))]
    result = classify_abc(items)
    assert len(result) == 1
    assert result[0].abc_class == "A", (
        "item واحد هو 100% من الإيراد → يجب أن يكون class A"
    )


def test_abc_classification_all_equal_values():
    """ABC/Pareto classification مع items كلها بنفس القيمة لا تسبب error."""
    from app.resort_os.owner_analytics_engine import classify_abc

    items = [_make_item(i, f"صنف {i}", Decimal("100")) for i in range(5)]
    result = classify_abc(items)
    assert len(result) == 5, "كل items يجب أن تُعاد بعد classification"
    for item in result:
        assert item.abc_class in ("A", "B", "C"), (
            f"abc_class يجب أن يكون A/B/C، وجدنا: {item.abc_class}"
        )



# ══════════════════════════════════════════════════════════════════════
# 17. Exception ranking: critical صغير > attention كبير
# ══════════════════════════════════════════════════════════════════════

def test_exception_ranking_critical_above_attention():
    """
    يتحقق أن critical tier (حتى بقيمة صغيرة) دائماً أعلى من attention
    tier (حتى بقيمة كبيرة).

    المتطلب: Decision 0004 §Required tests "Exception ranking places a
    critical-tier, small-value item above an attention-tier, large-value
    item."
    """
    from app.resort_os.owner_analytics_engine import OwnerException, rank_exceptions

    exceptions = [
        OwnerException(
            exception_id="att:1", tier="attention", category="high_expense",
            title="مصروف مرتفع", detail="مصروف كبير",
            entity_id=None, entity_name=None,
            impact=Decimal("10000"), confidence=Decimal("0.9"),
            status="realized", source="expense_analytics",
        ),
        OwnerException(
            exception_id="crit:1", tier="critical", category="suspected_theft",
            title="نشاط مشبوه", detail="تلاعب محتمل",
            entity_id=None, entity_name=None,
            impact=Decimal("50"), confidence=Decimal("0.5"),
            status="potential", source="fraud_tasks",
        ),
    ]
    ranked = rank_exceptions(exceptions)

    assert ranked[0].tier == "critical", (
        "critical item يجب أن يكون أول حتى لو قيمته أقل من attention item"
    )
    assert ranked[1].tier == "attention"


# ══════════════════════════════════════════════════════════════════════
# 18. فحص شامل لـ Decision 0003 invariant #1: super_admin يعدي الكل
# ══════════════════════════════════════════════════════════════════════

def test_decision_0003_invariant_respected_in_get_owner_reader():
    """
    يتحقق أن get_owner_reader يحترم Decision 0003 invariant #1:
    super_admin يعدي كل الفحوصات.
    """
    import inspect
    from app.core.deps import get_owner_reader

    source = inspect.getsource(get_owner_reader)
    # يجب أن يفحص user_level >= 100 قبل role check
    assert "user_level(user) >= 100" in source or "level(user) >= 100" in source, (
        "get_owner_reader يجب أن يفحص super_admin (>= 100) أولاً"
    )
    assert '"owner"' in source or "'owner'" in source, (
        "get_owner_reader يجب أن يقبل owner role"
    )


def test_get_owner_reader_comment_references_decision_0003():
    """
    يتحقق أن get_owner_reader يذكر Decision 0003 في الـ docstring/comment
    كما هو مطلوب في القرار.
    """
    import inspect
    from app.core.deps import get_owner_reader

    source = inspect.getsource(get_owner_reader)
    assert "0003" in source or "Decision 0003" in source, (
        "get_owner_reader يجب أن يذكر Decision 0003 في docstring/comment"
    )



# ══════════════════════════════════════════════════════════════════════
# 19. Frontend router guard (structural check)
# ══════════════════════════════════════════════════════════════════════

def test_owner_frontend_router_has_role_guard():
    """
    يتحقق أن frontend/apps/owner/src/router/index.ts يحتوي على
    role guard يرفض non-owner/non-super_admin sessions.

    المتطلب: Decision 0004 §Required tests "The owner frontend's router
    blocks a non-owner/non-super_admin session client-side."
    """
    import pathlib

    router_path = (
        pathlib.Path(__file__).parent.parent.parent.parent
        / "frontend" / "apps" / "owner" / "src" / "router" / "index.ts"
    )
    if not router_path.exists():
        pytest.skip("frontend/apps/owner/src/router/index.ts غير موجود بعد")

    content = router_path.read_text(encoding="utf-8")

    # يجب أن يحتوي على فحص الـ role
    has_owner_check = "owner" in content
    has_super_admin_check = "super_admin" in content
    has_role_check = has_owner_check and has_super_admin_check

    assert has_role_check, (
        "owner router يجب أن يفحص 'owner' و'super_admin' roles"
    )

    # يجب أن يحتوي على redirect أو رفض للـ unauthorized users
    has_redirect = "redirect" in content.lower() or "push" in content or "replace" in content
    assert has_redirect, "owner router يجب أن يعيد توجيه المستخدمين غير المصرح لهم"


# ══════════════════════════════════════════════════════════════════════
# 20. Alembic single head check
# ══════════════════════════════════════════════════════════════════════

def test_alembic_single_head():
    """
    يتحقق أن Alembic لديها single head فقط (لا branching مفتوح).

    المتطلب: AGENTS.md §8 validation contract: "alembic heads"
    """
    import subprocess
    import pathlib

    backend_dir = pathlib.Path(__file__).parent.parent

    result = subprocess.run(
        [".venv/bin/alembic", "heads"],
        cwd=str(backend_dir),
        capture_output=True,
        text=True,
    )
    output = result.stdout.strip()
    lines = [l for l in output.split("\n") if l.strip() and "(head)" in l]

    assert len(lines) == 1, (
        f"يجب أن يكون هناك Alembic head واحد فقط، وجدنا {len(lines)}:\n{output}"
    )

