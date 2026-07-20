"""
tests/test_api/test_permissions.py
HTTP-level tests for the screen-level permission system: the catalog
endpoint, the /me effective-permissions endpoint, and — most importantly —
proof that an explicit UserPermission grant/deny actually changes the
behavior of a real endpoint wired with require_permission(), not just a
row sitting unused in the database.

راجع DINING_CUTOVER_PLAN.md Batch 6 — كان بيستخدم restaurant.void_order_item
كمثال حي (endpoint حقيقي مربوط بـ require_permission، min_role_level=40)،
اتحول لـ dining.void_order_item (نفس min_role_level بالظبط، بعد حذف
restaurant/cafe من المشروع).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient

from app.modules.core.permission_catalog import PERMISSION_CATALOG
from tests.conftest import _fresh_super_admin, _issue_step_up


def _branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="Perm Test Branch", name_ar="فرع اختبار الصلاحيات",
               code=f"PT-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def _link_user_to_branch(db, user_id: int, branch_id: int) -> None:
    """High 5 (جولة مراجعة Codex الأولى): void/refund/... بقوا يفرضوا
    assert_branch_access — أي actor بيلمس طلب لازم يكون Employee مربوط بفرع
    الطلب، وإلا 403 قبل ما يوصل لمنطق الصلاحية/الـ PIN اللي التست بيختبره."""
    from datetime import date, timedelta
    from decimal import Decimal as _D
    from app.modules.hr.models import Employee

    emp = db.query(Employee).filter(Employee.user_id == user_id).first()
    if emp:
        emp.branch_id = branch_id
    else:
        db.add(Employee(
            branch_id=branch_id, employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
            full_name=f"perm-user-{user_id}", national_id=f"2900101{uuid.uuid4().hex[:7]}",
            position="waiter", department="F&B", basic_salary=_D("4000.00"),
            hire_date=date.today() - timedelta(days=365), user_id=user_id,
        ))
    db.commit()


def _outlet_and_item_committed(db, branch):
    from app.modules.dining import services as dining_services
    from app.modules.dining.models import DiningItem
    from app.modules.dining.schemas import OutletCreate

    outlet = dining_services.create_outlet(db, OutletCreate(
        branch_id=branch.id, name="مطعم اختبار الصلاحيات", outlet_type="restaurant",
        revenue_account_code="4200",
    ))
    item = DiningItem(branch_id=branch.id, outlet_id=outlet.id,
                       name="صنف اختبار الصلاحيات", price=Decimal("80.00"), is_available=True)
    db.add(item)
    db.commit()
    return outlet, item


def _set_manager_pin(db, pin: str) -> int:
    """راجع test_restaurant_http.py::_set_pin لنفس المنطق — بيستخدم حساب
    manager@test.local (بيتعمل عبر fixture manager_headers)."""
    from app.core.kernel.models.user import User
    from app.modules.core import services as core_services

    user = db.query(User).filter(User.email == "manager@test.local").first()
    core_services.set_pin(db, user.id, pin, created_by=user.id)
    db.commit()
    return user.id


def _create_order(client: TestClient, outlet_id: int, item_id: int, headers: dict) -> dict:
    resp = client.post(
        f"/api/v1/dining/outlets/{outlet_id}/orders",
        json={"outlet_id": outlet_id, "order_type": "takeaway", "guests_count": 1,
              "items": [{"item_id": item_id, "quantity": 1}]},
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
        assert "dining.void_order_item" in resources
        assert "hr.approve_payroll_run" in resources
        # كل صف لازم يكون فيه label_ar وlabel_en حقيقيين مش فاضيين (مراجعة
        # Codex المستقلة، 2026-07-18: كانت الشاشة بتعرض label_ar حتى في
        # الوضع الإنجليزي لعدم وجود label_en أصلاً في الكتالوج)
        assert all(e["label_ar"] for e in body)
        assert all(e["label_en"] for e in body)

    def test_catalog_requires_manager_level(self, client: TestClient, waiter_headers):
        resp = client.get("/api/v1/permissions/catalog", headers=waiter_headers)
        assert resp.status_code == 403


class TestEffectivePermissions:
    def test_manager_me_reflects_role_fallback(self, client: TestClient, manager_headers):
        resp = client.get("/api/v1/permissions/me", headers=manager_headers)
        assert resp.status_code == 200
        by_resource = {e["resource"]: e for e in resp.json()}

        # manager (level 60) >= dining.void_order_item الحد الأدنى (40) → مسموح
        assert by_resource["dining.void_order_item"]["allowed"] is True
        assert by_resource["dining.void_order_item"]["source"] == "role"

        # manager (level 60) < hr.approve_payroll_run الحد الأدنى (80) → ممنوع
        assert by_resource["hr.approve_payroll_run"]["allowed"] is False
        assert by_resource["hr.approve_payroll_run"]["source"] == "role"

    def test_waiter_me_reflects_lower_role(self, client: TestClient, waiter_headers):
        resp = client.get("/api/v1/permissions/me", headers=waiter_headers)
        by_resource = {e["resource"]: e for e in resp.json()}
        # waiter (level 30) < dining.void_order_item الحد الأدنى (40) → ممنوع
        assert by_resource["dining.void_order_item"]["allowed"] is False
        assert by_resource["dining.void_order_item"]["source"] == "role"


class TestExplicitOverrideEndToEnd:
    """يثبت إن الاستثناء الصريح (UserPermission) فعليًا بيغيّر سلوك endpoint حقيقي
    مربوط بيه require_permission — مش مجرد جدول في الداتابيز من غير أي أثر."""

    def test_grant_lets_waiter_void_despite_role(self, client: TestClient, db, manager_headers):
        """⚠️ ملحوظة مهمة (2026-07-07): منح استثناء صريح (UserPermission) بيغيّر
        "مين مسموح له يحاول العملية" (require_permission gate) — ده مفهوم
        منفصل تمامًا عن موافقة PIN (core.services.resolve_pin_approval)، اللي
        بتتحقق من "فيه مدير حاضر وموافق فعليًا على العملية دي بالذات دلوقتي".
        استثناء صريح من super_admin لواتر واحد مش بديل عن إشراف مدير لحظي —
        لو حصل العكس (استثناء يلغي احتياج PIN كمان) كان هيبقى ثغرة: أي واتر
        معاه استثناء واحد قديم يقدر يلغي أي حاجة للأبد من غير أي إشراف فعلي.

        Gate 2B3A: super_admin هنا حساب منعزل بسرّ TOTP خاص بيه (مش
        super_admin_headers المشترك) — يصدر step-up token واحد بس هنا،
        فمفيش خطر تصادم إعادة استخدام كود مع اختبار تاني."""
        from tests.conftest import _create_test_user, _make_token
        email = f"perm-waiter-{uuid.uuid4().hex[:6]}@test.local"
        waiter_id = _create_test_user(email, "waiter")
        custom_headers = {"Authorization": f"Bearer {_make_token(email)}"}
        manager_id = _set_manager_pin(db, "1234")
        _sa_id, sa_headers, sa_secret = _fresh_super_admin("grant-actor")

        branch = _branch_committed(db)
        _link_user_to_branch(db, waiter_id, branch.id)  # High 5: void بيفرض فحص الفرع
        outlet, item = _outlet_and_item_committed(db, branch)
        order = _create_order(client, outlet.id, item.id, custom_headers)
        order_item_id = order["items"][0]["id"]

        # قبل المنح: واتر (level 30) أقل من الحد الأدنى (40) للـ endpoint ده → 403
        resp = client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{order_item_id}/void",
            json={"reason": "تجربة قبل المنح"}, headers=custom_headers,
        )
        assert resp.status_code == 403

        # منح استثناء صريح من super_admin (Gate 2B3A: reason + step-up إجباريان)
        reason = "منح استثناء صريح لواتر يقدر يلغي صنف"
        token = _issue_step_up(
            client, sa_headers, purpose="permission_override_upsert",
            intent={"user_id": waiter_id, "resource": "dining.void_order_item",
                    "action": "execute", "allowed": True, "branch_id": None, "reason": reason},
            totp_secret=sa_secret,
        )
        grant = client.post(
            "/api/v1/permissions",
            json={"user_id": waiter_id, "resource": "dining.void_order_item",
                  "action": "execute", "allowed": True, "reason": reason},
            headers={**sa_headers, "X-Step-Up-Token": token},
        )
        assert grant.status_code == 201, grant.text

        # بعد المنح: مسموح له يحاول (role gate اتخطّى)، بس لسه محتاج موافقة
        # PIN من مدير حقيقي (waiter مش مدير، حتى مع الاستثناء)
        resp_no_pin = client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{order_item_id}/void",
            json={"reason": "بدون موافقة PIN"}, headers=custom_headers,
        )
        assert resp_no_pin.status_code == 400

        resp2 = client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{order_item_id}/void",
            json={"reason": "تجربة بعد المنح", "approver_user_id": manager_id, "approver_pin": "1234"},
            headers=custom_headers,
        )
        assert resp2.status_code == 200, resp2.text
        assert resp2.json()["items"][0]["status"] == "cancelled"

    def test_explicit_deny_blocks_manager_despite_role(self, client: TestClient, db):
        from tests.conftest import _create_test_user, _make_token
        email = f"perm-mgr-{uuid.uuid4().hex[:6]}@test.local"
        mgr_id = _create_test_user(email, "manager")
        custom_headers = {"Authorization": f"Bearer {_make_token(email)}"}
        _sa_id, sa_headers, sa_secret = _fresh_super_admin("deny-actor")

        branch = _branch_committed(db)
        _link_user_to_branch(db, mgr_id, branch.id)  # High 5: عشان الـ403 يبقى من المنع مش الفرع
        outlet, item = _outlet_and_item_committed(db, branch)
        order = _create_order(client, outlet.id, item.id, custom_headers)
        order_item_id = order["items"][0]["id"]

        reason = "منع صريح لمدير بسبب سوء استخدام سابق لإلغاء الأصناف"
        token = _issue_step_up(
            client, sa_headers, purpose="permission_override_upsert",
            intent={"user_id": mgr_id, "resource": "dining.void_order_item",
                    "action": "execute", "allowed": False, "branch_id": None, "reason": reason},
            totp_secret=sa_secret,
        )
        deny = client.post(
            "/api/v1/permissions",
            json={"user_id": mgr_id, "resource": "dining.void_order_item",
                  "action": "execute", "allowed": False, "reason": reason},
            headers={**sa_headers, "X-Step-Up-Token": token},
        )
        assert deny.status_code == 201, deny.text

        # المدير ده عادةً يقدر (level 60 >= 40) بس اتمنع صراحةً — لازم يتمنع
        resp = client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{order_item_id}/void",
            json={"reason": "تجربة منع صريح"}, headers=custom_headers,
        )
        assert resp.status_code == 403

    def test_revoke_restores_role_fallback(self, client: TestClient, db, manager_headers):
        from tests.conftest import _create_test_user, _make_token
        email = f"perm-revoke-{uuid.uuid4().hex[:6]}@test.local"
        waiter_id = _create_test_user(email, "waiter")
        custom_headers = {"Authorization": f"Bearer {_make_token(email)}"}
        manager_id = _set_manager_pin(db, "1234")
        _sa_id, sa_headers, sa_secret = _fresh_super_admin("revoke-actor")

        branch = _branch_committed(db)
        _link_user_to_branch(db, waiter_id, branch.id)  # High 5: void بيفرض فحص الفرع
        outlet, item = _outlet_and_item_committed(db, branch)

        order1 = _create_order(client, outlet.id, item.id, custom_headers)
        order1_item_id = order1["items"][0]["id"]

        grant_reason = "منح استثناء صريح مؤقت لواتر"
        grant_token = _issue_step_up(
            client, sa_headers, purpose="permission_override_upsert",
            intent={"user_id": waiter_id, "resource": "dining.void_order_item",
                    "action": "execute", "allowed": True, "branch_id": None, "reason": grant_reason},
            totp_secret=sa_secret,
        )
        grant = client.post(
            "/api/v1/permissions",
            json={"user_id": waiter_id, "resource": "dining.void_order_item",
                  "action": "execute", "allowed": True, "reason": grant_reason},
            headers={**sa_headers, "X-Step-Up-Token": grant_token},
        ).json()

        # الاستثناء شغال فعلاً — بس لسه محتاج موافقة PIN (راجع تعليق
        # test_grant_lets_waiter_void_despite_role للتفصيل الكامل)
        assert client.patch(
            f"/api/v1/dining/orders/{order1['id']}/items/{order1_item_id}/void",
            json={"reason": "أول مرة", "approver_user_id": manager_id, "approver_pin": "1234"},
            headers=custom_headers,
        ).status_code == 200

        # يلغي الاستثناء (Gate 2B3A: reason + step-up إجباريان هنا كمان —
        # totp_offset_steps=1 عشان الكود التاني في نفس نافذة الـ30 ثانية
        # اللي فوق ميتترفضش كـreplay)
        revoke_reason = "إلغاء الاستثناء المؤقت بعد انتهاء الغرض منه"
        revoke_token = _issue_step_up(
            client, sa_headers, purpose="permission_override_revoke",
            intent={"permission_id": grant["id"], "reason": revoke_reason},
            totp_secret=sa_secret, totp_offset_steps=1,
        )
        revoke = client.request(
            "DELETE", f"/api/v1/permissions/{grant['id']}",
            json={"reason": revoke_reason},
            headers={**sa_headers, "X-Step-Up-Token": revoke_token},
        )
        assert revoke.status_code == 204, revoke.text

        # طلب تاني، بعد الإلغاء، لازم يرجع لسلوك الـ role الافتراضي (ممنوع)
        order2 = _create_order(client, outlet.id, item.id, custom_headers)
        order2_item_id = order2["items"][0]["id"]
        resp = client.patch(
            f"/api/v1/dining/orders/{order2['id']}/items/{order2_item_id}/void",
            json={"reason": "بعد الإلغاء"}, headers=custom_headers,
        )
        assert resp.status_code == 403
