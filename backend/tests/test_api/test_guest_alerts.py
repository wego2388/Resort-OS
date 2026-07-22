"""
tests/test_api/test_guest_alerts.py
HTTP-level tests for the guest-alerts feature — a guest-initiated,
unauthenticated staff-alert channel ("call waiter" / "ready to order" /
"assistance" / "request bill") with live WebSocket delivery to staff. No
auth needed for the create call (mirrors tests/test_api/
test_cafe_public_orders.py's public-endpoint pattern); the staff list/
resolve endpoints are role-gated (get_waiter_user).

راجع app/modules/core/models.py::GuestAlert للشرح الكامل عن التصميم (generic
context_type/context_id بدون FK).

Gate 8 Phase 1 Batch A (2026-07-21): context_type كان لسه restaurant_table/
cafe_table القديمين (الموديولين اتحذفوا 2026-07-13) — بقى dining_table،
وcontext_id بقى محتاج يتحقق فعليًا إنه ينتمي لنفس الفرع (مش رقم عشوائي زي
كان قبل كده). زائد dedup/cooldown جديد واختباراته الخاصة.

Gate 8 Phase 1 Batch C (2026-07-21): POST /public/alerts بقى token-based
بالكامل (Decision 0001 بند 6) — الضيف بيبعت {token, alert_type, message}
بس، مش branch_id/context_type/context_id خام. التستات هنا بتولّد رمز
حقيقي عبر make_service_location_token (نفس نمط ServiceLocationToken في
core.crud) قبل أي استدعاء POST /public/alerts.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.conftest import ws_url


def make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(name="Guest Alert Branch", name_ar="فرع اختبار التنبيهات",
               code=f"ALERT-{uuid.uuid4().hex[:6].upper()}")
    db.add(b)
    db.commit()
    return b


def make_dining_table(db, branch):
    """Gate 8 Phase 1: context_id لازم يبقى VenueTable حقيقي تابع لنفس
    الفرع — الطاولة مشتركة بين كل المنافذ (راجع dining.models.VenueTable's
    docstring، 2026-07-21)، فمفيش outlet_id هنا خالص."""
    from app.modules.dining.models import VenueTable
    t = VenueTable(branch_id=branch.id, table_number=f"T-{uuid.uuid4().hex[:6].upper()}", capacity=4)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def make_service_location_token(db, branch, location_id, location_type="dining_table") -> str:
    """Gate 8 Phase 1 Batch C: POST /public/alerts بقى token-based — بيولّد
    رمز حقيقي مباشرة عبر core.crud (بدل استدعاء POST /service-location-tokens
    الكامل بمستخدم مدير)، نفس نمط make_dining_table's raw model creation."""
    import secrets
    from app.modules.core import crud as core_crud
    token = secrets.token_urlsafe(16)
    core_crud.create_service_location_token(
        db, token=token, branch_id=branch.id, location_type=location_type,
        location_id=location_id, created_by=None,
    )
    db.commit()
    return token


def guest_session_headers(client: TestClient, token: str) -> dict[str, str]:
    response = client.post("/api/v1/public/guest-sessions", json={"token": token})
    assert response.status_code == 201, response.text
    return {"X-Guest-Session": response.json()["session_token"]}


def alert_id_from_response(db, response) -> int:
    from app.modules.core.models import GuestAlert
    reference = response.json()["public_reference"]
    row = db.query(GuestAlert).filter(GuestAlert.public_reference == reference).one()
    return row.id


def enable_guest_alerts(db, branch):
    """Gate 1 containment: POST /public/alerts مقفول افتراضيًا خلف بوابتين
    معًا (جولة مراجعة Codex الثالثة) — settings.GUEST_ALERTS_ENABLED
    (typed، deployment-level) + core.Setting "core.guest_alerts_enabled"
    (الفرع). لازم يتفعّل الاتنين صراحةً في أي تست بيختبر مسار الإنشاء
    نفسه، مش سلوك القفل."""
    from app.core.config import settings
    from app.modules.core.crud import upsert_setting
    settings.GUEST_ALERTS_ENABLED = True
    upsert_setting(db, "core.guest_alerts_enabled", "true", branch_id=branch.id)
    db.commit()


def make_branch_linked_waiter_headers(db, branch) -> dict[str, str]:
    """Gate 1 containment: GET /alerts بقى بيفرض إن الفرع المطلوب هو فرع
    المستخدم نفسه (core.services.assert_branch_access عبر HR.Employee) —
    الـwaiter_headers المشترك (conftest.py) بلا Employee/فرع خالص، فبيترفض
    دلوقتي (403) لو استُخدم مباشرة على GET /alerts. نفس نمط
    test_hr_me_http.py's make_linked_user_headers/link بالظبط."""
    from datetime import date, timedelta
    from decimal import Decimal

    from tests.conftest import _create_test_user, _make_token
    from app.modules.hr.models import Employee

    email = f"waiter-{uuid.uuid4().hex[:10]}@test.local"
    user_id = _create_test_user(email, "waiter")
    emp = Employee(
        branch_id=branch.id, employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
        full_name="نادل اختبار التنبيهات", national_id="29001011234567",
        position="Waiter", department="F&B", basic_salary=Decimal("4000.00"),
        hire_date=date.today() - timedelta(days=365), user_id=user_id,
    )
    db.add(emp)
    db.commit()
    return {"Authorization": f"Bearer {_make_token(email)}"}


class TestCreateGuestAlertPublic:
    def test_create_alert_disabled_by_default(self, client: TestClient, db):
        """Gate 1 containment (جولة تصحيح ثانية): بدون core.guest_alerts_enabled
        صريح، الإنشاء يترفض 400 — مش 201."""
        branch = make_branch(db)
        table = make_dining_table(db, branch)
        token = make_service_location_token(db, branch, table.id)
        headers = guest_session_headers(client, token)
        resp = client.post("/api/v1/public/guest-requests", json={
            "alert_type": "call_waiter",
        }, headers=headers)
        assert resp.status_code == 400, resp.text

    def test_create_call_waiter_alert_no_auth(self, client: TestClient, db):
        branch = make_branch(db)
        table = make_dining_table(db, branch)
        enable_guest_alerts(db, branch)
        token = make_service_location_token(db, branch, table.id)
        headers = guest_session_headers(client, token)
        resp = client.post("/api/v1/public/guest-requests", json={
            "alert_type": "call_waiter",
        }, headers=headers)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["public_reference"].startswith("req_")
        assert data["status"] == "open"
        assert data["message"]

    def test_create_request_bill_alert_gets_bill_specific_message(self, client: TestClient, db):
        branch = make_branch(db)
        table = make_dining_table(db, branch)
        enable_guest_alerts(db, branch)
        token = make_service_location_token(db, branch, table.id)
        headers = guest_session_headers(client, token)
        resp = client.post("/api/v1/public/guest-requests", json={
            "alert_type": "request_bill", "message": "الحساب من فضلكم",
        }, headers=headers)
        assert resp.status_code == 201, resp.text
        assert "الفاتورة" in resp.json()["message"]

    def test_create_ready_to_order_and_assistance_alerts(self, client: TestClient, db):
        """Gate 8 Phase 1 — النوعين الجداد من Decision 0001's الأربع أفعال
        (call waiter / ready to order / assistance / request bill)."""
        branch = make_branch(db)
        table = make_dining_table(db, branch)
        enable_guest_alerts(db, branch)
        token = make_service_location_token(db, branch, table.id)

        headers = guest_session_headers(client, token)
        ready_resp = client.post("/api/v1/public/guest-requests", json={
            "alert_type": "ready_to_order",
        }, headers=headers)
        assert ready_resp.status_code == 201, ready_resp.text

        assist_resp = client.post("/api/v1/public/guest-requests", json={
            "alert_type": "assistance",
        }, headers=headers)
        assert assist_resp.status_code == 201, assist_resp.text

    def test_create_alert_rejects_unknown_alert_type(self, client: TestClient, db):
        branch = make_branch(db)
        table = make_dining_table(db, branch)
        enable_guest_alerts(db, branch)
        token = make_service_location_token(db, branch, table.id)
        headers = guest_session_headers(client, token)
        resp = client.post("/api/v1/public/guest-requests", json={
            "alert_type": "not_a_real_type",
        }, headers=headers)
        assert resp.status_code == 422

    def test_public_body_cannot_override_location_ids(self, client: TestClient, db):
        branch = make_branch(db)
        table = make_dining_table(db, branch)
        token = make_service_location_token(db, branch, table.id)
        headers = guest_session_headers(client, token)
        response = client.post(
            "/api/v1/public/guest-requests",
            json={
                "alert_type": "call_waiter",
                "branch_id": branch.id,
                "context_type": "dining_table",
                "context_id": table.id,
            },
            headers=headers,
        )
        assert response.status_code == 422

    def test_create_alert_rejects_unknown_token(self, client: TestClient, db):
        """Gate 8 Phase 1 Batch C: الرمز نفسه هو مصدر الثقة الوحيد دلوقتي —
        رمز غير موجود/ملغي يترفض 400، بديل test_create_alert_rejects_
        missing_branch القديم (branch_id مش client-supplied تاني)."""
        resp = client.post("/api/v1/public/guest-sessions", json={"token": "does-not-exist"})
        assert resp.status_code in (404, 422), resp.text

    def test_create_alert_rejects_deactivated_token(self, client: TestClient, db):
        """رمز اتلغى بالتدوير (ServiceLocationToken.is_active=False) —
        بديل test_create_alert_rejects_table_from_different_branch/
        _nonexistent_table القديمين؛ الفحصين دول اتنقلوا فعليًا لوقت
        توليد الرمز (راجع test_service_location_tokens.py) بدل وقت
        الإنشاء، لأن الرمز دلوقتي هو الغلاف الوحيد حول أي location."""
        branch = make_branch(db)
        table = make_dining_table(db, branch)
        enable_guest_alerts(db, branch)
        token = make_service_location_token(db, branch, table.id)
        # تدوير رمز جديد لنفس الموقع يلغي القديم فورًا (crud.deactivate_
        # service_location_tokens، راجع services.create_or_rotate_service_
        # location_token).
        from app.modules.core import crud as core_crud
        core_crud.deactivate_service_location_tokens(db, branch.id, "dining_table", table.id)
        db.commit()

        resp = client.post("/api/v1/public/guest-sessions", json={"token": token})
        assert resp.status_code == 404, resp.text

    def test_context_type_other_is_not_a_qr_location(self, client: TestClient, db):
        """Gate 8 QR codes represent verified physical resources only."""
        branch = make_branch(db)
        enable_guest_alerts(db, branch)
        token = make_service_location_token(db, branch, 999999999, location_type="other")
        resp = client.post("/api/v1/public/guest-sessions", json={"token": token})
        assert resp.status_code == 404, resp.text

    def test_duplicate_alert_within_cooldown_returns_existing(self, client: TestClient, db):
        """Gate 8 Phase 1 — dedup/idempotency: نفس (الطاولة، نوع الطلب)
        مرتين خلال نافذة التهدئة يرجّع نفس الطلب المفتوح، مش صف جديد."""
        branch = make_branch(db)
        table = make_dining_table(db, branch)
        enable_guest_alerts(db, branch)
        token = make_service_location_token(db, branch, table.id)

        headers = guest_session_headers(client, token)
        first = client.post("/api/v1/public/guest-requests", json={
            "alert_type": "call_waiter",
        }, headers=headers)
        assert first.status_code == 201, first.text

        second = client.post("/api/v1/public/guest-requests", json={
            "alert_type": "call_waiter",
        }, headers=headers)
        assert second.status_code == 201, second.text
        assert second.json()["public_reference"] == first.json()["public_reference"]
        assert second.json()["deduplicated"] is True

    def test_duplicate_alert_after_cooldown_creates_new(self, client: TestClient, db):
        """نفس الطلب بعد ما نافذة التهدئة تخلص (أو الطلب القديم اتقفل)
        لازم يعمل صف جديد — مش idempotent للأبد."""
        branch = make_branch(db)
        table = make_dining_table(db, branch)
        enable_guest_alerts(db, branch)
        token = make_service_location_token(db, branch, table.id)
        branch_waiter_headers = make_branch_linked_waiter_headers(db, branch)

        headers = guest_session_headers(client, token)
        first = client.post("/api/v1/public/guest-requests", json={
            "alert_type": "call_waiter",
        }, headers=headers)
        first_id = alert_id_from_response(db, first)
        resolve = client.patch(
            f"/api/v1/alerts/{first_id}/status", json={"status": "resolved"}, headers=branch_waiter_headers,
        )
        assert resolve.status_code == 200, resolve.text

        second = client.post("/api/v1/public/guest-requests", json={
            "alert_type": "call_waiter",
        }, headers=headers)
        assert second.status_code == 201, second.text
        assert alert_id_from_response(db, second) != first_id

    def test_different_alert_types_same_table_both_created(self, client: TestClient, db):
        """dedup بيقارن alert_type كمان — طلب "نادِ الجرسون" و"هات الفاتورة"
        على نفس الطاولة في نفس اللحظة لازم يبقوا صفّين منفصلين، مش يبتلع
        التاني كـ"تكرار"."""
        branch = make_branch(db)
        table = make_dining_table(db, branch)
        enable_guest_alerts(db, branch)
        token = make_service_location_token(db, branch, table.id)

        headers = guest_session_headers(client, token)
        call = client.post("/api/v1/public/guest-requests", json={
            "alert_type": "call_waiter",
        }, headers=headers)
        bill = client.post("/api/v1/public/guest-requests", json={
            "alert_type": "request_bill",
        }, headers=headers)
        assert call.json()["public_reference"] != bill.json()["public_reference"]

    def test_public_status_is_bound_to_issuing_session(self, client: TestClient, db):
        branch = make_branch(db)
        table = make_dining_table(db, branch)
        enable_guest_alerts(db, branch)
        token = make_service_location_token(db, branch, table.id)
        issuing_headers = guest_session_headers(client, token)
        other_table = make_dining_table(db, branch)
        other_token = make_service_location_token(db, branch, other_table.id)
        other_headers = guest_session_headers(client, other_token)
        created = client.post(
            "/api/v1/public/guest-requests", json={"alert_type": "assistance"},
            headers=issuing_headers,
        )
        reference = created.json()["public_reference"]
        own = client.get(
            f"/api/v1/public/guest-requests/{reference}", headers=issuing_headers,
        )
        assert own.status_code == 200
        assert own.json()["status"] == "open"
        foreign = client.get(
            f"/api/v1/public/guest-requests/{reference}", headers=other_headers,
        )
        assert foreign.status_code == 404

    def test_stale_request_expires_and_no_longer_blocks_new_request(self, client: TestClient, db):
        from datetime import datetime, timedelta
        from app.modules.core.models import GuestAlert
        from app.core.config import settings

        branch = make_branch(db)
        table = make_dining_table(db, branch)
        enable_guest_alerts(db, branch)
        token = make_service_location_token(db, branch, table.id)
        headers = guest_session_headers(client, token)
        first = client.post(
            "/api/v1/public/guest-requests", json={"alert_type": "call_waiter"},
            headers=headers,
        )
        first_id = alert_id_from_response(db, first)
        row = db.query(GuestAlert).filter(GuestAlert.id == first_id).one()
        row.created_at = datetime.utcnow() - timedelta(minutes=settings.GUEST_REQUEST_TTL_MINUTES + 1)
        db.commit()

        second = client.post(
            "/api/v1/public/guest-requests", json={"alert_type": "call_waiter"},
            headers=headers,
        )
        assert second.status_code == 201, second.text
        assert second.json()["public_reference"] != first.json()["public_reference"]
        db.refresh(row)
        assert row.status == "expired"


class TestStaffAlertsFeed:
    def test_list_alerts_requires_auth(self, client: TestClient, db):
        branch = make_branch(db)
        resp = client.get("/api/v1/alerts", params={"branch_id": branch.id})
        assert resp.status_code == 401

    def test_list_alerts_cross_branch_waiter_rejected(self, client: TestClient, db):
        """Gate 1 containment: GET /alerts كان بيقبل branch_id من العميل
        بلا أي تحقق ملكية — نادل من فرع تاني كان يقدر يشوف تنبيهات فرع
        مختلف تمامًا بمجرد تمرير رقمه في الـquery. اتصلح عبر
        core.services.assert_branch_access."""
        home_branch  = make_branch(db)
        other_branch = make_branch(db)
        other_branch_waiter_headers = make_branch_linked_waiter_headers(db, other_branch)

        resp = client.get(
            "/api/v1/alerts", params={"branch_id": home_branch.id},
            headers=other_branch_waiter_headers,
        )
        assert resp.status_code == 403, resp.text

    def test_list_alerts_manager_without_matching_branch_rejected(self, client: TestClient, db, manager_headers):
        """تصحيح (جولة مراجعة Codex الثانية): manager (level=60) **لا**
        يتخطى فحص الفرع بعد كده — الاستثناء الوحيد المعتمد هو super_admin
        (Decision 0003)، مش أي دور بمستوى عالٍ. manager_headers المشترك
        بلا Employee/فرع، فيترفض 403 زي أي دور تاني بدون فرع مطابق."""
        branch = make_branch(db)
        resp = client.get(
            "/api/v1/alerts", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert resp.status_code == 403, resp.text

    def test_list_alerts_super_admin_bypasses_branch_check(self, client: TestClient, db, super_admin_headers):
        """super_admin (level=100) هو الاستثناء المعتمد الوحيد للتخطي
        الكامل عبر الفروع (Decision 0003) — يفضل 200 حتى بلا Employee مرتبط."""
        branch = make_branch(db)
        resp = client.get(
            "/api/v1/alerts", params={"branch_id": branch.id}, headers=super_admin_headers,
        )
        assert resp.status_code == 200, resp.text

    def test_list_alerts_returns_created_open_alert(self, client: TestClient, db, waiter_headers):
        branch = make_branch(db)
        table = make_dining_table(db, branch)
        enable_guest_alerts(db, branch)
        branch_waiter_headers = make_branch_linked_waiter_headers(db, branch)
        token = make_service_location_token(db, branch, table.id)
        guest_headers = guest_session_headers(client, token)
        client.post(
            "/api/v1/public/guest-requests", json={"alert_type": "call_waiter"},
            headers=guest_headers,
        )

        resp = client.get("/api/v1/alerts", params={"branch_id": branch.id}, headers=branch_waiter_headers)
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["status"] == "open"
        assert items[0]["context_type"] == "dining_table"
        assert items[0]["context_id"] == table.id

    def test_resolve_alert_requires_auth(self, client: TestClient, db):
        branch = make_branch(db)
        table = make_dining_table(db, branch)
        enable_guest_alerts(db, branch)
        token = make_service_location_token(db, branch, table.id)
        guest_headers = guest_session_headers(client, token)
        create_resp = client.post(
            "/api/v1/public/guest-requests", json={"alert_type": "request_bill"},
            headers=guest_headers,
        )
        alert_id = alert_id_from_response(db, create_resp)

        resp = client.patch(f"/api/v1/alerts/{alert_id}/status", json={"status": "resolved"})
        assert resp.status_code == 401

    def test_acknowledge_then_resolve_alert(self, client: TestClient, db, waiter_headers):
        branch = make_branch(db)
        table = make_dining_table(db, branch)
        enable_guest_alerts(db, branch)
        branch_waiter_headers = make_branch_linked_waiter_headers(db, branch)
        token = make_service_location_token(db, branch, table.id)
        guest_headers = guest_session_headers(client, token)
        create_resp = client.post(
            "/api/v1/public/guest-requests", json={"alert_type": "call_waiter"},
            headers=guest_headers,
        )
        alert_id = alert_id_from_response(db, create_resp)

        # Gate 1 containment (جولة تصحيح ثانية): PATCH بقى بيفرض تطابق الفرع
        # زي GET بالظبط — waiter_headers المشترك بلا فرع بيترفض هنا دلوقتي.
        ack_resp = client.patch(
            f"/api/v1/alerts/{alert_id}/status", json={"status": "acknowledged"}, headers=branch_waiter_headers,
        )
        assert ack_resp.status_code == 200, ack_resp.text
        assert ack_resp.json()["status"] == "acknowledged"
        assert ack_resp.json()["resolved_at"] is None
        assert ack_resp.json()["assigned_to"] is not None

        # لسه فاضل في الفيد (acknowledged مش resolved)
        list_resp = client.get("/api/v1/alerts", params={"branch_id": branch.id}, headers=branch_waiter_headers)
        assert any(a["id"] == alert_id for a in list_resp.json()["items"])

        arrived_resp = client.patch(
            f"/api/v1/alerts/{alert_id}/status", json={"status": "arrived"}, headers=branch_waiter_headers,
        )
        assert arrived_resp.status_code == 200, arrived_resp.text
        assert arrived_resp.json()["arrived_at"] is not None

        resolve_resp = client.patch(
            f"/api/v1/alerts/{alert_id}/status", json={"status": "resolved"}, headers=branch_waiter_headers,
        )
        assert resolve_resp.status_code == 200, resolve_resp.text
        body = resolve_resp.json()
        assert body["status"] == "resolved"
        assert body["resolved_at"] is not None
        assert body["resolved_by"] is not None

        # اتشال من الفيد بعد ما اتقفل
        list_resp2 = client.get("/api/v1/alerts", params={"branch_id": branch.id}, headers=branch_waiter_headers)
        assert not any(a["id"] == alert_id for a in list_resp2.json()["items"])

    def test_resolve_cross_branch_waiter_rejected(self, client: TestClient, db, waiter_headers):
        """Gate 1 containment (جولة تصحيح ثانية): نادل من فرع تاني كان
        يقدر يقفل/يأكد تنبيه فرع مختلف تمامًا (نفس باج GET القديم، بس على
        PATCH). اتصلح عبر core.services.assert_branch_access."""
        home_branch  = make_branch(db)
        other_branch = make_branch(db)
        home_table = make_dining_table(db, home_branch)
        enable_guest_alerts(db, home_branch)
        other_branch_waiter_headers = make_branch_linked_waiter_headers(db, other_branch)
        token = make_service_location_token(db, home_branch, home_table.id)

        guest_headers = guest_session_headers(client, token)
        create_resp = client.post(
            "/api/v1/public/guest-requests", json={"alert_type": "call_waiter"},
            headers=guest_headers,
        )
        alert_id = alert_id_from_response(db, create_resp)

        resp = client.patch(
            f"/api/v1/alerts/{alert_id}/status", json={"status": "acknowledged"},
            headers=other_branch_waiter_headers,
        )
        assert resp.status_code == 403, resp.text

    def test_assigned_request_cannot_be_taken_by_another_waiter(self, client: TestClient, db):
        branch = make_branch(db)
        table = make_dining_table(db, branch)
        enable_guest_alerts(db, branch)
        first_waiter = make_branch_linked_waiter_headers(db, branch)
        second_waiter = make_branch_linked_waiter_headers(db, branch)
        token = make_service_location_token(db, branch, table.id)
        guest_headers = guest_session_headers(client, token)
        created = client.post(
            "/api/v1/public/guest-requests", json={"alert_type": "assistance"},
            headers=guest_headers,
        )
        alert_id = alert_id_from_response(db, created)
        acknowledged = client.patch(
            f"/api/v1/alerts/{alert_id}/status", json={"status": "acknowledged"},
            headers=first_waiter,
        )
        assert acknowledged.status_code == 200

        stolen = client.patch(
            f"/api/v1/alerts/{alert_id}/status", json={"status": "resolved"},
            headers=second_waiter,
        )
        assert stolen.status_code == 403, stolen.text

    def test_resolve_already_resolved_alert_rejected(self, client: TestClient, db, waiter_headers):
        branch = make_branch(db)
        enable_guest_alerts(db, branch)
        branch_waiter_headers = make_branch_linked_waiter_headers(db, branch)
        table = make_dining_table(db, branch)
        token = make_service_location_token(db, branch, table.id)
        guest_headers = guest_session_headers(client, token)
        create_resp = client.post(
            "/api/v1/public/guest-requests",
            json={"alert_type": "other", "message": "محتاج كرسي إضافي"},
            headers=guest_headers,
        )
        alert_id = alert_id_from_response(db, create_resp)

        first = client.patch(f"/api/v1/alerts/{alert_id}/status", json={"status": "resolved"}, headers=branch_waiter_headers)
        assert first.status_code == 200

        second = client.patch(f"/api/v1/alerts/{alert_id}/status", json={"status": "resolved"}, headers=branch_waiter_headers)
        assert second.status_code == 400

    def test_resolve_missing_alert_404_equivalent_400(self, client: TestClient, db, waiter_headers):
        resp = client.patch("/api/v1/alerts/999999999/status", json={"status": "resolved"}, headers=waiter_headers)
        assert resp.status_code == 400


class TestGuestAlertsWebSocket:
    def test_websocket_client_receives_new_alert_broadcast(self, client: TestClient, db, waiter_headers):
        """يتأكد إن اتصال WebSocket حقيقي بيستلم فعليًا التنبيه الجديد لحظة
        إنشائه — نفس فكرة test_kds_websocket_client_actually_receives_broadcast_message
        في المطعم (مش بس mock للـ broadcast، اتصال حقيقي)."""
        branch = make_branch(db)
        table = make_dining_table(db, branch)
        enable_guest_alerts(db, branch)
        # Gate 1 containment (جولة تصحيح ثانية): الاتصال بقى بيفرض تطابق
        # الفرع (core.services.assert_branch_access) — waiter_headers
        # المشترك بلا فرع هيتقفل بـ4403.
        branch_waiter_headers = make_branch_linked_waiter_headers(db, branch)
        token = make_service_location_token(db, branch, table.id)
        guest_headers = guest_session_headers(client, token)

        with client.websocket_connect(ws_url(f"/api/v1/ws/alerts/{branch.id}", branch_waiter_headers)) as ws:
            create_resp = client.post(
                "/api/v1/public/guest-requests", json={"alert_type": "call_waiter"},
                headers=guest_headers,
            )
            assert create_resp.status_code == 201, create_resp.text

            message = ws.receive_json()
            assert message["type"] == "new_alert"
            assert message["alert"]["context_id"] == table.id
            assert message["alert"]["alert_type"] == "call_waiter"
            assert message["alert"]["status"] == "open"

    def test_websocket_receives_status_change_broadcast(self, client: TestClient, db, waiter_headers):
        branch = make_branch(db)
        table = make_dining_table(db, branch)
        enable_guest_alerts(db, branch)
        branch_waiter_headers = make_branch_linked_waiter_headers(db, branch)
        token = make_service_location_token(db, branch, table.id)
        guest_headers = guest_session_headers(client, token)
        create_resp = client.post(
            "/api/v1/public/guest-requests", json={"alert_type": "request_bill"},
            headers=guest_headers,
        )
        alert_id = alert_id_from_response(db, create_resp)

        with client.websocket_connect(ws_url(f"/api/v1/ws/alerts/{branch.id}", branch_waiter_headers)) as ws:
            resp = client.patch(
                f"/api/v1/alerts/{alert_id}/status", json={"status": "acknowledged"}, headers=branch_waiter_headers,
            )
            assert resp.status_code == 200, resp.text

            message = ws.receive_json()
            assert message["type"] == "alert_status_changed"
            assert message["alert"]["id"] == alert_id
            assert message["alert"]["status"] == "acknowledged"

    def test_websocket_cross_branch_connection_rejected(self, client: TestClient, db):
        """Gate 1 containment (جولة تصحيح ثانية): نادل من فرع تاني كان
        يقدر يشترك في بث تنبيهات فرع مختلف تمامًا عبر WebSocket — اتصلح
        بإغلاق الاتصال بـ4403 عند عدم تطابق الفرع."""
        from starlette.websockets import WebSocketDisconnect
        home_branch  = make_branch(db)
        other_branch = make_branch(db)
        other_branch_waiter_headers = make_branch_linked_waiter_headers(db, other_branch)

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(ws_url(f"/api/v1/ws/alerts/{home_branch.id}", other_branch_waiter_headers)):
                pass
        assert exc_info.value.code == 4403

    def test_websocket_rejects_connection_without_token(self, client: TestClient, db):
        """wagdy.md A-01: كل WebSocket في المشروع كان بيتقبل من غير أي تحقق
        هوية خالص. get_websocket_user (app/core/deps.py) بيقفل الاتصال بـ
        code 4401 لو مفيش ?token= صالح — هنا بنتأكد إن ده بيحصل فعليًا على
        اتصال حقيقي، مش بس قراءة كود."""
        from starlette.websockets import WebSocketDisconnect
        branch = make_branch(db)

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/api/v1/ws/alerts/{branch.id}"):
                pass
        assert exc_info.value.code == 4401

    def test_websocket_rejects_invalid_token(self, client: TestClient, db):
        from starlette.websockets import WebSocketDisconnect
        branch = make_branch(db)

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/api/v1/ws/alerts/{branch.id}?token=garbage-not-a-real-jwt"):
                pass
        assert exc_info.value.code == 4401
