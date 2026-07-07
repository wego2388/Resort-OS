"""
tests/test_api/test_permissions.py
HTTP-level tests for the screen-level permission system: the catalog
endpoint, the /me effective-permissions endpoint, and — most importantly —
proof that an explicit UserPermission grant/deny actually changes the
behavior of a real endpoint wired with require_permission(), not just a
row sitting unused in the database.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient

from app.modules.core.permission_catalog import PERMISSION_CATALOG


def _branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="Perm Test Branch", name_ar="فرع اختبار الصلاحيات",
               code=f"PT-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def _menu_item_committed(db, branch):
    from app.modules.restaurant.models import MenuItem
    item = MenuItem(branch_id=branch.id, name="صنف اختبار الصلاحيات", price=Decimal("80.00"), is_available=True)
    db.add(item)
    db.commit()
    return item


def _set_manager_pin(db, pin: str) -> int:
    """راجع test_restaurant_http.py::_set_pin لنفس المنطق — بيستخدم حساب
    manager@test.local (بيتعمل عبر fixture manager_headers)."""
    from app.core.kernel.models.user import User
    from app.modules.core import services as core_services

    user = db.query(User).filter(User.email == "manager@test.local").first()
    core_services.set_pin(db, user.id, pin, created_by=user.id)
    db.commit()
    return user.id


def _create_order(client: TestClient, branch_id: int, item_id: int, headers: dict) -> dict:
    resp = client.post(
        "/api/v1/restaurant/orders", params={"branch_id": branch_id},
        json={"order_type": "takeaway", "guests_count": 1,
              "items": [{"menu_item_id": item_id, "quantity": 1}]},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestPermissionCatalog:
    def test_catalog_lists_all_entries(self, client: TestClient, manager_headers):
        resp = client.get("/api/v1/permissions/catalog", headers=manager_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == len(PERMISSION_CATALOG)
        resources = {e["resource"] for e in body}
        assert "restaurant.void_order_item" in resources
        assert "hr.approve_payroll_run" in resources
        # كل صف لازم يكون فيه label_ar حقيقي مش فاضي
        assert all(e["label_ar"] for e in body)

    def test_catalog_requires_manager_level(self, client: TestClient, waiter_headers):
        resp = client.get("/api/v1/permissions/catalog", headers=waiter_headers)
        assert resp.status_code == 403


class TestEffectivePermissions:
    def test_manager_me_reflects_role_fallback(self, client: TestClient, manager_headers):
        resp = client.get("/api/v1/permissions/me", headers=manager_headers)
        assert resp.status_code == 200
        by_resource = {e["resource"]: e for e in resp.json()}

        # manager (level 60) >= restaurant.void_order_item الحد الأدنى (40) → مسموح
        assert by_resource["restaurant.void_order_item"]["allowed"] is True
        assert by_resource["restaurant.void_order_item"]["source"] == "role"

        # manager (level 60) < hr.approve_payroll_run الحد الأدنى (80) → ممنوع
        assert by_resource["hr.approve_payroll_run"]["allowed"] is False
        assert by_resource["hr.approve_payroll_run"]["source"] == "role"

    def test_waiter_me_reflects_lower_role(self, client: TestClient, waiter_headers):
        resp = client.get("/api/v1/permissions/me", headers=waiter_headers)
        by_resource = {e["resource"]: e for e in resp.json()}
        # waiter (level 30) < restaurant.void_order_item الحد الأدنى (40) → ممنوع
        assert by_resource["restaurant.void_order_item"]["allowed"] is False
        assert by_resource["restaurant.void_order_item"]["source"] == "role"


class TestExplicitOverrideEndToEnd:
    """يثبت إن الاستثناء الصريح (UserPermission) فعليًا بيغيّر سلوك endpoint حقيقي
    مربوط بيه require_permission — مش مجرد جدول في الداتابيز من غير أي أثر."""

    def test_grant_lets_waiter_void_despite_role(self, client: TestClient, db, super_admin_headers, manager_headers):
        """⚠️ ملحوظة مهمة (2026-07-07): منح استثناء صريح (UserPermission) بيغيّر
        "مين مسموح له يحاول العملية" (require_permission gate) — ده مفهوم
        منفصل تمامًا عن موافقة PIN (core.services.resolve_pin_approval)، اللي
        بتتحقق من "فيه مدير حاضر وموافق فعليًا على العملية دي بالذات دلوقتي".
        استثناء صريح من super_admin لواتر واحد مش بديل عن إشراف مدير لحظي —
        لو حصل العكس (استثناء يلغي احتياج PIN كمان) كان هيبقى ثغرة: أي واتر
        معاه استثناء واحد قديم يقدر يلغي أي حاجة للأبد من غير أي إشراف فعلي."""
        from tests.conftest import _create_test_user, _make_token
        email = f"perm-waiter-{uuid.uuid4().hex[:6]}@test.local"
        waiter_id = _create_test_user(email, "waiter")
        custom_headers = {"Authorization": f"Bearer {_make_token(email)}"}
        manager_id = _set_manager_pin(db, "1234")

        branch = _branch_committed(db)
        item = _menu_item_committed(db, branch)
        order = _create_order(client, branch.id, item.id, custom_headers)
        order_item_id = order["items"][0]["id"]

        # قبل المنح: واتر (level 30) أقل من الحد الأدنى (40) للـ endpoint ده → 403
        resp = client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/items/{order_item_id}/void",
            json={"reason": "تجربة قبل المنح"}, headers=custom_headers,
        )
        assert resp.status_code == 403

        # منح استثناء صريح من super_admin
        grant = client.post(
            "/api/v1/permissions",
            json={"user_id": waiter_id, "resource": "restaurant.void_order_item",
                  "action": "execute", "allowed": True},
            headers=super_admin_headers,
        )
        assert grant.status_code == 201, grant.text

        # بعد المنح: مسموح له يحاول (role gate اتخطّى)، بس لسه محتاج موافقة
        # PIN من مدير حقيقي (waiter مش مدير، حتى مع الاستثناء)
        resp_no_pin = client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/items/{order_item_id}/void",
            json={"reason": "بدون موافقة PIN"}, headers=custom_headers,
        )
        assert resp_no_pin.status_code == 400

        resp2 = client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/items/{order_item_id}/void",
            json={"reason": "تجربة بعد المنح", "approver_user_id": manager_id, "approver_pin": "1234"},
            headers=custom_headers,
        )
        assert resp2.status_code == 200, resp2.text
        assert resp2.json()["items"][0]["status"] == "cancelled"

    def test_explicit_deny_blocks_manager_despite_role(self, client: TestClient, db, super_admin_headers):
        from tests.conftest import _create_test_user, _make_token
        email = f"perm-mgr-{uuid.uuid4().hex[:6]}@test.local"
        mgr_id = _create_test_user(email, "manager")
        custom_headers = {"Authorization": f"Bearer {_make_token(email)}"}

        branch = _branch_committed(db)
        item = _menu_item_committed(db, branch)
        order = _create_order(client, branch.id, item.id, custom_headers)
        order_item_id = order["items"][0]["id"]

        deny = client.post(
            "/api/v1/permissions",
            json={"user_id": mgr_id, "resource": "restaurant.void_order_item",
                  "action": "execute", "allowed": False},
            headers=super_admin_headers,
        )
        assert deny.status_code == 201, deny.text

        # المدير ده عادةً يقدر (level 60 >= 40) بس اتمنع صراحةً — لازم يتمنع
        resp = client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/items/{order_item_id}/void",
            json={"reason": "تجربة منع صريح"}, headers=custom_headers,
        )
        assert resp.status_code == 403

    def test_revoke_restores_role_fallback(self, client: TestClient, db, super_admin_headers, manager_headers):
        from tests.conftest import _create_test_user, _make_token
        email = f"perm-revoke-{uuid.uuid4().hex[:6]}@test.local"
        waiter_id = _create_test_user(email, "waiter")
        custom_headers = {"Authorization": f"Bearer {_make_token(email)}"}
        manager_id = _set_manager_pin(db, "1234")

        branch = _branch_committed(db)
        item = _menu_item_committed(db, branch)

        order1 = _create_order(client, branch.id, item.id, custom_headers)
        order1_item_id = order1["items"][0]["id"]

        grant = client.post(
            "/api/v1/permissions",
            json={"user_id": waiter_id, "resource": "restaurant.void_order_item",
                  "action": "execute", "allowed": True},
            headers=super_admin_headers,
        ).json()

        # الاستثناء شغال فعلاً — بس لسه محتاج موافقة PIN (راجع تعليق
        # test_grant_lets_waiter_void_despite_role للتفصيل الكامل)
        assert client.patch(
            f"/api/v1/restaurant/orders/{order1['id']}/items/{order1_item_id}/void",
            json={"reason": "أول مرة", "approver_user_id": manager_id, "approver_pin": "1234"},
            headers=custom_headers,
        ).status_code == 200

        # يلغي الاستثناء
        revoke = client.delete(f"/api/v1/permissions/{grant['id']}", headers=super_admin_headers)
        assert revoke.status_code == 204

        # طلب تاني، بعد الإلغاء، لازم يرجع لسلوك الـ role الافتراضي (ممنوع)
        order2 = _create_order(client, branch.id, item.id, custom_headers)
        order2_item_id = order2["items"][0]["id"]
        resp = client.patch(
            f"/api/v1/restaurant/orders/{order2['id']}/items/{order2_item_id}/void",
            json={"reason": "بعد الإلغاء"}, headers=custom_headers,
        )
        assert resp.status_code == 403
