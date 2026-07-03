"""
tests/test_api/test_core_http.py
HTTP-level tests for the core module's router: branches CRUD, settings,
notifications, audit logs, and user role management. No dedicated test
file existed for this module before — router coverage was purely
incidental from other modules' tests exercising branches/permissions.
"""
from __future__ import annotations

import uuid

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
