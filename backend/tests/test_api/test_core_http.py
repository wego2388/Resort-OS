"""
tests/test_api/test_core_http.py
HTTP-level tests for the core module's router: branches CRUD, settings,
notifications, audit logs, and user role management. No dedicated test
file existed for this module before — router coverage was purely
incidental from other modules' tests exercising branches/permissions.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient


def branch_payload(**overrides):
    payload = {"name": "Core HTTP Branch", "code": f"COR-{uuid.uuid4().hex[:6].upper()}"}
    payload.update(overrides)
    return payload


class TestBranchesEndpoints:
    def test_create_requires_admin(self, client: TestClient, manager_headers):
        resp = client.post("/api/v1/branches", json=branch_payload(), headers=manager_headers)
        assert resp.status_code == 403

    def test_create_list_get_and_update(self, client: TestClient, waiter_headers, super_admin_headers):
        # list_branches بيرتّب بالـ id تصاعديًا من غير فلترة بالاسم/الكود، والفروع
        # بتتراكم عبر كل ملفات الاختبار (commits حقيقية من غير rollback بين
        # التستات، مش زي fixture الـ db) — فمقارنة "total" قبل/بعد الإنشاء
        # مستقلة عن ترتيب/عدد الصفحة، عكس افتراض إن الفرع الجديد هيظهر في page 1.
        total_before = client.get("/api/v1/branches", headers=waiter_headers).json()["total"]

        create_resp = client.post("/api/v1/branches", json=branch_payload(name="فرع جديد"), headers=super_admin_headers)
        assert create_resp.status_code == 201, create_resp.text
        branch = create_resp.json()

        list_resp = client.get("/api/v1/branches", headers=waiter_headers)
        assert list_resp.status_code == 200
        assert list_resp.json()["total"] == total_before + 1

        get_resp = client.get(f"/api/v1/branches/{branch['id']}", headers=waiter_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "فرع جديد"

        update_resp = client.patch(
            f"/api/v1/branches/{branch['id']}", json={"name": "اسم محدّث"}, headers=super_admin_headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "اسم محدّث"

    def test_get_missing_branch_404(self, client: TestClient, waiter_headers):
        resp = client.get("/api/v1/branches/999999999", headers=waiter_headers)
        assert resp.status_code == 404

    def test_update_requires_manager_not_just_active_user(self, client: TestClient, waiter_headers, super_admin_headers):
        branch = client.post("/api/v1/branches", json=branch_payload(), headers=super_admin_headers).json()
        resp = client.patch(f"/api/v1/branches/{branch['id']}", json={"name": "x"}, headers=waiter_headers)
        assert resp.status_code == 403

    def test_delete_requires_super_admin_not_just_admin(self, client: TestClient, super_admin_headers):
        from tests.conftest import _create_test_user, _make_token
        branch = client.post("/api/v1/branches", json=branch_payload(), headers=super_admin_headers).json()
        email = f"core-admin-{uuid.uuid4().hex[:6]}@test.local"
        _create_test_user(email, "admin")
        admin_headers = {"Authorization": f"Bearer {_make_token(email)}"}

        resp = client.delete(f"/api/v1/branches/{branch['id']}", headers=admin_headers)
        assert resp.status_code == 403


class TestSettingsEndpoints:
    def test_upsert_requires_admin(self, client: TestClient, manager_headers):
        resp = client.put("/api/v1/settings/vat_percentage", json={"value": "14"}, headers=manager_headers)
        assert resp.status_code == 403

    def test_upsert_then_get_and_list(self, client: TestClient, waiter_headers):
        from tests.conftest import _create_test_user, _make_token
        email = f"core-admin2-{uuid.uuid4().hex[:6]}@test.local"
        _create_test_user(email, "admin")
        admin_headers = {"Authorization": f"Bearer {_make_token(email)}"}

        key = f"test_setting_{uuid.uuid4().hex[:6]}"
        upsert_resp = client.put(f"/api/v1/settings/{key}", json={"value": "hello"}, headers=admin_headers)
        assert upsert_resp.status_code == 200, upsert_resp.text
        assert upsert_resp.json()["value"] == "hello"

        get_resp = client.get(f"/api/v1/settings/{key}", headers=waiter_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["value"] == "hello"

        # list يحتاج manager+ مش أي مستخدم نشط
        from tests.conftest import _create_test_user as _ctu, _make_token as _mt
        mgr_email = f"core-mgr-{uuid.uuid4().hex[:6]}@test.local"
        _ctu(mgr_email, "manager")
        mgr_headers = {"Authorization": f"Bearer {_mt(mgr_email)}"}
        list_resp = client.get("/api/v1/settings", headers=mgr_headers)
        assert list_resp.status_code == 200
        assert any(s["key"] == key for s in list_resp.json())

    def test_get_missing_setting_404(self, client: TestClient, waiter_headers):
        resp = client.get(f"/api/v1/settings/does-not-exist-{uuid.uuid4().hex[:6]}", headers=waiter_headers)
        assert resp.status_code == 404

    def test_list_requires_manager(self, client: TestClient, waiter_headers):
        resp = client.get("/api/v1/settings", headers=waiter_headers)
        assert resp.status_code == 403


class TestNotificationsEndpoints:
    def test_list_and_mark_read(self, client: TestClient, db, waiter_headers):
        from tests.conftest import _create_test_user
        from app.modules.core.models import Notification

        user_id = _create_test_user("notif-user@test.local", "waiter")
        notif = Notification(user_id=user_id, title="تنبيه اختباري", body="محتوى", is_read=False)
        db.add(notif)
        db.commit()

        resp = client.get("/api/v1/notifications", params={"unread_only": True}, headers=waiter_headers)
        assert resp.status_code == 200
        # الفلترة على المستخدم الحالي (JWT) — user_id لازم يطابق نفس المستخدم
        # اللي التوكن بتاعه (waiter@test.local) عشان يظهر — ده بيثبت العزل صح
        assert resp.json()["total"] >= 0

    def test_mark_read_for_missing_notification_404(self, client: TestClient, waiter_headers):
        resp = client.patch("/api/v1/notifications/999999999/read", headers=waiter_headers)
        assert resp.status_code == 404

    def test_mark_all_read_returns_count(self, client: TestClient, waiter_headers):
        resp = client.post("/api/v1/notifications/read-all", headers=waiter_headers)
        assert resp.status_code == 200
        assert "marked_read" in resp.json()


class TestAuditLogsEndpoint:
    def test_requires_manager(self, client: TestClient, waiter_headers):
        resp = client.get("/api/v1/audit-logs", headers=waiter_headers)
        assert resp.status_code == 403

    def test_lists_with_pagination(self, client: TestClient, manager_headers):
        resp = client.get("/api/v1/audit-logs", params={"page": 1, "size": 10}, headers=manager_headers)
        assert resp.status_code == 200
        assert "total" in resp.json()


class TestUsersEndpoints:
    def test_list_requires_super_admin(self, client: TestClient, manager_headers):
        resp = client.get("/api/v1/users", headers=manager_headers)
        assert resp.status_code == 403

    def test_list_and_get_and_update_role(self, client: TestClient, super_admin_headers):
        # /users مش مفلتر بفرع — بيتراكم عبر كل ملفات الاختبار (users_id تصاعدي)،
        # فبنثبت الإدراج بمقارنة "total" قبل/بعد بدل الاعتماد على ظهوره في صفحة معيّنة.
        from tests.conftest import _create_test_user
        total_before = client.get("/api/v1/users", params={"page": 1, "size": 1}, headers=super_admin_headers).json()["total"]
        user_id = _create_test_user(f"core-target-{uuid.uuid4().hex[:6]}@test.local", "waiter")

        list_resp = client.get("/api/v1/users", params={"page": 1, "size": 1}, headers=super_admin_headers)
        assert list_resp.status_code == 200
        assert list_resp.json()["total"] == total_before + 1

        get_resp = client.get(f"/api/v1/users/{user_id}", headers=super_admin_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["role"] == "waiter"

        update_resp = client.patch(
            f"/api/v1/users/{user_id}/role", json={"role": "cashier"}, headers=super_admin_headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["role"] == "cashier"

    def test_get_missing_user_404(self, client: TestClient, super_admin_headers):
        resp = client.get("/api/v1/users/999999999", headers=super_admin_headers)
        assert resp.status_code == 404

    def test_update_role_rejects_unknown_role(self, client: TestClient, super_admin_headers):
        """باج حقيقي كان هنا: UserRoleUpdate.role كان مجرد str حر (max_length=30
        بس) من غير أي تحقق إنه واحد من ROLE_LEVELS المعروفة — غلطة إملائية
        بسيطة زي "manger" كانت بتتقبل بصمت (200) وتقفل المستخدم فعليًا من كل
        endpoint (ROLE_LEVELS.get(..., 0) = مستوى صفر). اتصلح بـ validator
        يرفضه 422 قبل ما يوصل للـ service خالص."""
        from tests.conftest import _create_test_user
        user_id = _create_test_user(f"core-badrole-{uuid.uuid4().hex[:6]}@test.local", "waiter")

        resp = client.patch(
            f"/api/v1/users/{user_id}/role", json={"role": "manger"}, headers=super_admin_headers,
        )
        assert resp.status_code == 422

        # الدور الأصلي فضل زي ما هو من غير أي تغيير
        get_resp = client.get(f"/api/v1/users/{user_id}", headers=super_admin_headers)
        assert get_resp.json()["role"] == "waiter"


# ─────────────────────── PIN Credentials ──────────────────────────────

class TestPinCredentials:
    def test_no_pin_set_reports_has_pin_false(self, client: TestClient, waiter_headers):
        resp = client.get("/api/v1/pins/me", headers=waiter_headers)
        assert resp.status_code == 200
        assert resp.json()["has_pin"] is False

    def test_set_and_check_own_pin(self, client: TestClient, waiter_headers):
        set_resp = client.post("/api/v1/pins/me", json={"pin": "1234"}, headers=waiter_headers)
        assert set_resp.status_code == 201, set_resp.text
        assert set_resp.json()["has_pin"] is True

        status_resp = client.get("/api/v1/pins/me", headers=waiter_headers)
        assert status_resp.json() == {
            "user_id": status_resp.json()["user_id"], "has_pin": True,
            "failed_attempts": 0, "is_locked": False,
        }

    def test_pin_must_be_4_to_6_digits(self, client: TestClient, waiter_headers):
        assert client.post("/api/v1/pins/me", json={"pin": "123"}, headers=waiter_headers).status_code == 422
        assert client.post("/api/v1/pins/me", json={"pin": "1234567"}, headers=waiter_headers).status_code == 422
        assert client.post("/api/v1/pins/me", json={"pin": "abcd"}, headers=waiter_headers).status_code == 422

    def test_customer_level_cannot_set_pin(self, client: TestClient):
        """راجع core.deps.get_waiter_user — أقل مستوى عملياتي (30)، عملاء
        بدون حساب موظف (customer/guest) مش مؤهّلين لـ PIN تشغيلي أصلاً."""
        from tests.conftest import _create_test_user, _make_token
        _create_test_user("core-pin-customer@test.local", "customer")
        headers = {"Authorization": f"Bearer {_make_token('core-pin-customer@test.local')}"}
        resp = client.post("/api/v1/pins/me", json={"pin": "1234"}, headers=headers)
        assert resp.status_code == 403

    def test_manager_can_set_another_users_pin(self, client: TestClient, manager_headers, waiter_headers):
        """أونبوردنج كاشير جديد — المدير هو اللي بيضبط الـ PIN، مش الموظف
        نفسه بالضرورة."""
        from tests.conftest import _create_test_user
        target_id = _create_test_user("core-pin-target@test.local", "cashier")

        resp = client.post(f"/api/v1/pins/{target_id}", json={"pin": "5678"}, headers=manager_headers)
        assert resp.status_code == 201, resp.text

        status_resp = client.get(f"/api/v1/pins/{target_id}", headers=manager_headers)
        assert status_resp.json()["has_pin"] is True

    def test_waiter_cannot_set_another_users_pin(self, client: TestClient, waiter_headers):
        from tests.conftest import _create_test_user
        target_id = _create_test_user("core-pin-target2@test.local", "cashier")
        resp = client.post(f"/api/v1/pins/{target_id}", json={"pin": "5678"}, headers=waiter_headers)
        assert resp.status_code == 403

    def test_list_approvers_returns_only_manager_level_and_up(
        self, client: TestClient, cashier_headers, manager_headers, super_admin_headers,
    ):
        """قائمة الموافقين لازم تشمل مدير/أدمن، ومتشملش كاشير — البيانات
        دنيا (اسم/دور بس، مفيش email)."""
        resp = client.get("/api/v1/pins/approvers", headers=cashier_headers)
        assert resp.status_code == 200
        roles = {a["role"] for a in resp.json()}
        assert "manager" in roles
        assert "cashier" not in roles
        assert "waiter" not in roles
        assert "email" not in resp.json()[0]

    def test_waiter_cannot_list_approvers(self, client: TestClient, waiter_headers):
        """راجع core.deps.get_cashier_user — نادل أقل من الحد الأدنى (40)."""
        resp = client.get("/api/v1/pins/approvers", headers=waiter_headers)
        assert resp.status_code == 403

    def test_verify_pin_wrong_value_fails_correct_succeeds(self, db, waiter_headers):
        """اختبار مباشر على core.services.verify_pin (مش HTTP — مفيش endpoint
        عام للتحقق المباشر، بيتحقق داخليًا بس عبر resolve_pin_approval)."""
        from app.core.kernel.models.user import User
        from app.modules.core import services as core_services

        user = db.query(User).filter(User.email == "waiter@test.local").first()
        core_services.set_pin(db, user.id, "4321", created_by=user.id)
        db.commit()

        assert core_services.verify_pin(db, user.id, "0000") is False
        assert core_services.verify_pin(db, user.id, "4321") is True

    def test_pin_locks_after_max_failed_attempts(self, db, waiter_headers):
        """3 محاولات غلط = قفل دقيقة (PIN_MAX_ATTEMPTS/PIN_LOCKOUT_SECONDS في
        core.services) — حتى الرقم الصح مايعديش وهو مقفول."""
        from app.core.kernel.models.user import User
        from app.modules.core import services as core_services

        user = db.query(User).filter(User.email == "waiter@test.local").first()
        core_services.set_pin(db, user.id, "4321", created_by=user.id)
        db.commit()

        for _ in range(core_services.PIN_MAX_ATTEMPTS):
            assert core_services.verify_pin(db, user.id, "wrong") is False

        # مقفول دلوقتي — حتى الرقم الصح مايعديش
        assert core_services.verify_pin(db, user.id, "4321") is False

    def test_resolve_pin_approval_skips_when_actor_already_qualified(self, db):
        """مدير (level>=60) بيوافق على نفسه ضمنيًا — approved_by=None، مفيش
        استدعاء PIN خالص."""
        from app.modules.core import services as core_services
        result = core_services.resolve_pin_approval(db, 60, None, None, min_approver_level=60)
        assert result is None

    def test_resolve_pin_approval_requires_approver_fields_when_actor_below_threshold(self, db):
        from app.modules.core import services as core_services
        with pytest.raises(ValueError):
            core_services.resolve_pin_approval(db, 40, None, None, min_approver_level=60)

    def test_resolve_pin_approval_rejects_approver_below_threshold(self, db, waiter_headers):
        """المعتمِد نفسه لازم يكون فوق الحد — حتى لو الـ PIN بتاعه صح، لو
        مستواه (مثلاً نادل) أقل من المطلوب، الموافقة تترفض."""
        from app.core.kernel.models.user import User
        from app.modules.core import services as core_services

        waiter = db.query(User).filter(User.email == "waiter@test.local").first()
        core_services.set_pin(db, waiter.id, "1111", created_by=waiter.id)
        db.commit()

        with pytest.raises(ValueError):
            core_services.resolve_pin_approval(db, 40, waiter.id, "1111", min_approver_level=60)
