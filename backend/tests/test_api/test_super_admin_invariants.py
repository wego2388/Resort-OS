"""
tests/test_api/test_super_admin_invariants.py
Gate 2A — Super Admin backend safeguards (Decision 0003).

يغطي 4 ثوابت مُنفَّذة في هذه الشريحة:
  1. super_admin نشط بيعدّي أي explicit UserPermission deny (has_permission +
     get_effective_permissions — نفس القرار المركزي _resolve_permission).
  2. مفيش override صريح جديد يقدر يستهدف super_admin (نشط أو غير نشط).
  3. self-demotion/self-deactivation الفعليين مرفوضين دايمًا عبر PATCH
     /users/{id}/role (no-op مسموح).
  4. أكواد HTTP دقيقة (409/404) بدل ValueError عام بيتحول 404 أو يهرب 500.

راجع docs/audits/gate-2a-super-admin-invariants.md للتفاصيل الكاملة —
بما فيها ليه "آخر super_admin نشط" ضد actor مختلف بيتغطى فعليًا عبر
ActorSuperAdminPrivilegesChangedError تحت تزامن حقيقي (tests/
test_super_admin_concurrency.py)، مش عبر HTTP هنا (مستحيل رياضيًا نبنيه
هنا بدون لمس حساب super_admin@test.local المشترك بين كل التستات).

Gate 2B3A: PATCH /users/{id}/role وPOST/DELETE /permissions بقوا محتاجين
reason إجباري + step-up token صالح (X-Step-Up-Token) — كل اختبار HTTP هنا
بيصدر step-up token حقيقي عبر tests.conftest._issue_step_up قبل الطلب
الفعلي، بنفس الـintent اللي الـendpoint المُستهلِك هيبنيه من الـpayload.
_fresh_super_admin بترجع سرّ TOTP حقيقي (pyotp) عشان step-up يقدر يتصدّر
فعليًا لحساب super_admin (دور 2FA إجباري — مفيش password-only bypass له).
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.conftest import _fresh_super_admin, _issue_step_up
from tests.test_api.test_permissions import (
    _branch_committed,
    _create_order,
    _outlet_and_item_committed,
)

# _fresh_super_admin (tests.conftest): super_admin جديد ومعزول (uuid عشوائي،
# سرّ TOTP خاص بيه) — عمدًا **مش** super_admin@test.local المشترك بين كل
# ملفات التستات، عشان أي تعديل (خصوصًا self-lockout/last-active) ميأثرش
# على تستات تانية، وعشان كل اختبار يقدر يصدر step-up token حقيقي (Gate
# 2B3A) بدون تصادم إعادة استخدام كود TOTP مع اختبار تاني بيشتغل في نفس
# اللحظة تقريبًا.


class TestActiveSuperAdminBypassesExplicitDeny:
    """Decision 0003 invariant #1 — منع صريح مايسقطش صلاحية super_admin
    نشط، سواء عبر has_permission (endpoint حقيقي مربوط بـrequire_permission)
    أو get_effective_permissions (/permissions/me)."""

    def test_explicit_deny_stays_inert_for_active_super_admin_real_endpoint(
        self, client: TestClient, db,
    ):
        sa_id, sa_headers, _sa_secret = _fresh_super_admin("deny-target")
        another_sa_id, _another_sa_headers, _ = _fresh_super_admin("deny-granter")

        branch = _branch_committed(db)
        outlet, item = _outlet_and_item_committed(db, branch)
        order = _create_order(client, outlet.id, item.id, sa_headers)
        order_item_id = order["items"][0]["id"]

        # يحاكي صف "deny" قديم اتسجل على حساب super_admin قبل Gate 2A (مش
        # عبر POST /permissions — دي بقت مرفوضة دلوقتي، راجع الكلاس التاني)
        # — استخدام crud مباشرة يمثّل بيانات legacy موجودة بالفعل.
        from app.modules.core import crud as core_crud
        from app.modules.core.schemas import UserPermissionCreate
        core_crud.upsert_user_permission(
            db, sa_id,
            UserPermissionCreate(resource="dining.void_order_item", action="execute", allowed=False),
            granted_by=another_sa_id,
        )
        db.commit()

        # super_admin نشط، مفيش حاجة تمنعه — حتى مع صف deny صريح موجود.
        # (void order item مش من الأربعة عمليات المحمية بـstep-up — مفيش
        # X-Step-Up-Token هنا عمدًا.)
        resp = client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{order_item_id}/void",
            json={"reason": "تجربة تجاوز المنع الصريح لـ super_admin"},
            headers=sa_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"][0]["status"] == "cancelled"

        # صف الـdeny القديم لسه موجود في الداتابيز — مش بيتحذف تلقائيًا،
        # هو "inert" (بلا أثر) بس، مش ملغي فعليًا.
        from app.modules.core import crud as core_crud2
        remaining = core_crud2.find_explicit_permission(db, sa_id, "dining.void_order_item", "execute")
        assert remaining is not None
        assert remaining.allowed is False

    def test_inactive_super_admin_does_not_get_the_bypass(self, db):
        """دفاع في العمق على مستوى service مباشرة — الـHTTP path مستحيل
        يوصل هنا أصلاً (get_current_active_user بيرفض is_active=False بـ403
        قبل ما يوصل لـhas_permission خالص)، لكن الفحص الصريح جوه
        _resolve_permission لازم يبقى موجود ومختبر لوحده."""
        from app.core.kernel.models.user import User
        from app.modules.core import crud as core_crud
        from app.modules.core.schemas import UserPermissionCreate
        from app.modules.core.services import has_permission

        sa_id, _headers, _secret = _fresh_super_admin("inactive-sa")
        user = db.query(User).filter(User.id == sa_id).first()

        core_crud.upsert_user_permission(
            db, sa_id,
            UserPermissionCreate(resource="dining.void_order_item", action="execute", allowed=False),
            granted_by=sa_id,
        )
        db.commit()

        # نشط: المنع الصريح "inert" — has_permission ترجع True دايمًا.
        db.refresh(user)
        assert has_permission(db, user, "dining.void_order_item", "execute", role_fallback=True) is True

        # غير نشط: الاستثناء بيتشال — المنع الصريح يرجع ياخد أثره الطبيعي.
        user.is_active = False
        db.commit()
        db.refresh(user)
        assert has_permission(db, user, "dining.void_order_item", "execute", role_fallback=True) is False

    def test_effective_permissions_me_shows_super_admin_source(self, client: TestClient, db):
        sa_id, sa_headers, _secret = _fresh_super_admin("me-source")
        from app.modules.core import crud as core_crud
        from app.modules.core.schemas import UserPermissionCreate
        core_crud.upsert_user_permission(
            db, sa_id,
            UserPermissionCreate(resource="hr.approve_payroll_run", action="approve", allowed=False),
            granted_by=sa_id,
        )
        db.commit()

        resp = client.get("/api/v1/permissions/me", headers=sa_headers)
        assert resp.status_code == 200
        by_resource = {e["resource"]: e for e in resp.json()}
        assert by_resource["hr.approve_payroll_run"]["allowed"] is True
        assert by_resource["hr.approve_payroll_run"]["source"] == "super_admin"
        # كل صف تاني (بلا أي deny صريح) لازم يبقى برضو super_admin/True.
        assert by_resource["dining.void_order_item"]["allowed"] is True
        assert by_resource["dining.void_order_item"]["source"] == "super_admin"


class TestPermissionOverrideCannotTargetSuperAdmin:
    """Decision 0003 invariant #2."""

    def test_grant_rejects_active_super_admin_target(self, client: TestClient, db):
        sa_id, _headers, _sa_secret = _fresh_super_admin("override-active")
        actor_id, actor_headers, actor_secret = _fresh_super_admin("override-actor")

        reason = "محاولة (يجب رفضها) تقييد صلاحية super_admin نشط"
        intent = {
            "user_id": sa_id, "resource": "dining.void_order_item",
            "action": "execute", "allowed": False, "branch_id": None, "reason": reason,
        }
        token = _issue_step_up(
            client, actor_headers, purpose="permission_override_upsert",
            intent=intent, totp_secret=actor_secret,
        )
        resp = client.post(
            "/api/v1/permissions",
            json={"user_id": sa_id, "resource": "dining.void_order_item",
                  "action": "execute", "allowed": False, "reason": reason},
            headers={**actor_headers, "X-Step-Up-Token": token},
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"]["error_code"] == "SUPER_ADMIN_PERMISSION_OVERRIDE_FORBIDDEN"

        from app.modules.core import crud as core_crud
        assert core_crud.find_explicit_permission(db, sa_id, "dining.void_order_item", "execute") is None

    def test_grant_rejects_inactive_super_admin_target(self, client: TestClient, db):
        from app.core.kernel.models.user import User
        sa_id, _headers, _sa_secret = _fresh_super_admin("override-inactive")
        _actor_id, actor_headers, actor_secret = _fresh_super_admin("override-actor2")

        user = db.query(User).filter(User.id == sa_id).first()
        user.is_active = False
        db.commit()

        reason = "محاولة (يجب رفضها) منح صلاحية super_admin غير نشط"
        intent = {
            "user_id": sa_id, "resource": "dining.void_order_item",
            "action": "execute", "allowed": True, "branch_id": None, "reason": reason,
        }
        token = _issue_step_up(
            client, actor_headers, purpose="permission_override_upsert",
            intent=intent, totp_secret=actor_secret,
        )
        resp = client.post(
            "/api/v1/permissions",
            json={"user_id": sa_id, "resource": "dining.void_order_item",
                  "action": "execute", "allowed": True, "reason": reason},
            headers={**actor_headers, "X-Step-Up-Token": token},
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["error_code"] == "SUPER_ADMIN_PERMISSION_OVERRIDE_FORBIDDEN"

    def test_grant_rejects_nonexistent_target_with_404(self, client: TestClient):
        """الـkernel's global 404 handler بيفلطح كل 404 في المشروع لنفس
        الشكل ({"error_code": "not_found", ...}) — راجع app/core/kernel/
        errors.py. المهم هنا كود 404 نفسه ورسالة واضحة، مش error_code مخصص
        (مستحيل تقنيًا من غير تعديل هندلر عام خارج نطاق Gate 2A)."""
        _actor_id, actor_headers, actor_secret = _fresh_super_admin("override-actor3")
        reason = "محاولة (يجب رفضها) منح صلاحية لمستخدم غير موجود"
        intent = {
            "user_id": 9_999_999, "resource": "dining.void_order_item",
            "action": "execute", "allowed": True, "branch_id": None, "reason": reason,
        }
        token = _issue_step_up(
            client, actor_headers, purpose="permission_override_upsert",
            intent=intent, totp_secret=actor_secret,
        )
        resp = client.post(
            "/api/v1/permissions",
            json={"user_id": 9_999_999, "resource": "dining.void_order_item",
                  "action": "execute", "allowed": True, "reason": reason},
            headers={**actor_headers, "X-Step-Up-Token": token},
        )
        assert resp.status_code == 404
        assert "غير موجود" in resp.json()["message"]

    def test_grant_still_works_for_non_super_admin_target(self, client: TestClient, db):
        """تأكيد إن الإصلاح مايكسرش السلوك الموجود لغير super_admin —
        نفس TestExplicitOverrideEndToEnd في test_permissions.py."""
        from tests.conftest import _create_test_user as _mk
        _actor_id, actor_headers, actor_secret = _fresh_super_admin("override-actor4")
        waiter_id = _mk(f"override-waiter-{uuid.uuid4().hex[:6]}@test.local", "waiter")

        reason = "منح صلاحية إلغاء صنف لنادل بعد غياب مدير متكرر"
        intent = {
            "user_id": waiter_id, "resource": "dining.void_order_item",
            "action": "execute", "allowed": True, "branch_id": None, "reason": reason,
        }
        token = _issue_step_up(
            client, actor_headers, purpose="permission_override_upsert",
            intent=intent, totp_secret=actor_secret,
        )
        resp = client.post(
            "/api/v1/permissions",
            json={"user_id": waiter_id, "resource": "dining.void_order_item",
                  "action": "execute", "allowed": True, "reason": reason},
            headers={**actor_headers, "X-Step-Up-Token": token},
        )
        assert resp.status_code == 201, resp.text

    def test_revoke_still_allows_cleanup_of_legacy_super_admin_override(self, client: TestClient, db):
        """الحذف (تنظيف) لازم يفضل مسموح حتى لو الهدف super_admin — مش
        مثل الإنشاء/التعديل."""
        sa_id, _headers, _sa_secret = _fresh_super_admin("override-cleanup")
        _actor_id, actor_headers, actor_secret = _fresh_super_admin("override-actor5")

        from app.modules.core import crud as core_crud
        from app.modules.core.schemas import UserPermissionCreate
        legacy = core_crud.upsert_user_permission(
            db, sa_id,
            UserPermissionCreate(resource="dining.void_order_item", action="execute", allowed=False),
            granted_by=sa_id,
        )
        db.commit()
        legacy_id = legacy.id

        reason = "تنظيف صف deny قديم على super_admin (Legacy، قبل Gate 2A)"
        token = _issue_step_up(
            client, actor_headers, purpose="permission_override_revoke",
            intent={"permission_id": legacy_id, "reason": reason},
            totp_secret=actor_secret,
        )
        resp = client.request(
            "DELETE", f"/api/v1/permissions/{legacy_id}",
            json={"reason": reason},
            headers={**actor_headers, "X-Step-Up-Token": token},
        )
        assert resp.status_code == 204, resp.text
        assert core_crud.find_explicit_permission(db, sa_id, "dining.void_order_item", "execute") is None


class TestSelfLockoutForbidden:
    """Decision 0003 invariant #3 — self-demotion/self-deactivation
    الفعليين مرفوضين دايمًا؛ no-op مسموح."""

    def test_self_role_change_rejected(self, client: TestClient, db):
        sa_id, sa_headers, sa_secret = _fresh_super_admin("self-role")
        reason = "محاولة (يجب رفضها) تخفيض دور الحساب الحالي بنفسه"
        token = _issue_step_up(
            client, sa_headers, purpose="user_role_update",
            intent={"user_id": sa_id, "role": "manager", "is_active": None, "reason": reason},
            totp_secret=sa_secret,
        )
        resp = client.patch(
            f"/api/v1/users/{sa_id}/role", json={"role": "manager", "reason": reason},
            headers={**sa_headers, "X-Step-Up-Token": token},
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"]["error_code"] == "SUPER_ADMIN_SELF_LOCKOUT_FORBIDDEN"

        from app.core.kernel.models.user import User
        db.expire_all()
        user = db.query(User).filter(User.id == sa_id).first()
        assert user.role == "super_admin"
        assert user.is_active is True

    def test_self_deactivation_rejected(self, client: TestClient, db):
        sa_id, sa_headers, sa_secret = _fresh_super_admin("self-deactivate")
        reason = "محاولة (يجب رفضها) تعطيل الحساب الحالي بنفسه"
        token = _issue_step_up(
            client, sa_headers, purpose="user_role_update",
            intent={"user_id": sa_id, "role": None, "is_active": False, "reason": reason},
            totp_secret=sa_secret,
        )
        resp = client.patch(
            f"/api/v1/users/{sa_id}/role", json={"is_active": False, "reason": reason},
            headers={**sa_headers, "X-Step-Up-Token": token},
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["error_code"] == "SUPER_ADMIN_SELF_LOCKOUT_FORBIDDEN"

        from app.core.kernel.models.user import User
        db.expire_all()
        user = db.query(User).filter(User.id == sa_id).first()
        assert user.is_active is True

    def test_self_noop_is_allowed(self, client: TestClient):
        """تعديل بلا أثر فعلي (نفس role الحالي صراحةً، أو role/is_active
        غير مُرسَلين خالص) — مش self-lockout، لازم ينجح 200. reason لسه
        إجباري في الحالتين (Gate 2B3A — بلا استثناء no-op)."""
        sa_id, sa_headers, sa_secret = _fresh_super_admin("self-noop")
        reason1 = "تأكيد الحالة الحالية دون تغيير فعلي"
        token1 = _issue_step_up(
            client, sa_headers, purpose="user_role_update",
            intent={"user_id": sa_id, "role": "super_admin", "is_active": True, "reason": reason1},
            totp_secret=sa_secret,
        )
        resp = client.patch(
            f"/api/v1/users/{sa_id}/role",
            json={"role": "super_admin", "is_active": True, "reason": reason1},
            headers={**sa_headers, "X-Step-Up-Token": token1},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["role"] == "super_admin"

        reason2 = "لا تغيير مطلوب — تأكيد إجرائي فقط"
        token2 = _issue_step_up(
            client, sa_headers, purpose="user_role_update",
            intent={"user_id": sa_id, "role": None, "is_active": None, "reason": reason2},
            totp_secret=sa_secret, totp_offset_steps=1,
        )
        resp_empty = client.patch(
            f"/api/v1/users/{sa_id}/role", json={"reason": reason2},
            headers={**sa_headers, "X-Step-Up-Token": token2},
        )
        assert resp_empty.status_code == 200, resp_empty.text

    def test_rejected_self_lockout_does_not_revoke_tokens(self, client: TestClient, db):
        """رفض self-lockout لازم يفضل بلا أثر جانبي خالص — الرفض بيحصل
        قبل أي revoke_user_tokens/commit، فنفس التوكن يفضل شغال بعد المحاولة
        المرفوضة."""
        sa_id, sa_headers, sa_secret = _fresh_super_admin("self-noeffect")
        reason = "محاولة (يجب رفضها) ترقية/تخفيض الحساب الحالي بنفسه"
        token = _issue_step_up(
            client, sa_headers, purpose="user_role_update",
            intent={"user_id": sa_id, "role": "admin", "is_active": None, "reason": reason},
            totp_secret=sa_secret,
        )
        resp = client.patch(
            f"/api/v1/users/{sa_id}/role", json={"role": "admin", "reason": reason},
            headers={**sa_headers, "X-Step-Up-Token": token},
        )
        assert resp.status_code == 409

        # نفس التوكن القديم لازم يفضل صالح — لو كان في revoke غير لازم
        # كان هيترفض هنا بـ401.
        me = client.get("/api/v1/permissions/me", headers=sa_headers)
        assert me.status_code == 200


class TestUpdateUserRoleErrorContract:
    def test_unknown_user_returns_404_user_not_found(self, client: TestClient):
        _actor_id, actor_headers, actor_secret = _fresh_super_admin("404-actor")
        reason = "تجربة تعديل دور مستخدم غير موجود"
        token = _issue_step_up(
            client, actor_headers, purpose="user_role_update",
            intent={"user_id": 9999999, "role": "manager", "is_active": None, "reason": reason},
            totp_secret=actor_secret,
        )
        resp = client.patch(
            "/api/v1/users/9999999/role", json={"role": "manager", "reason": reason},
            headers={**actor_headers, "X-Step-Up-Token": token},
        )
        assert resp.status_code == 404
        assert "غير موجود" in resp.json()["message"]

    def test_normal_other_user_demotion_still_works_and_audits_final_state(self, client: TestClient, db):
        """تأكيد إن الإصلاح مايكسرش المسار العادي (super_admin بيغيّر role
        مستخدم تاني غير super_admin) — وإن AuditLog.new_data بيسجل الحالة
        النهائية الفعلية زائد سياق step-up (Gate 2B3A)، مش قيم payload خام
        قد تكون None."""
        from tests.conftest import _create_test_user as _mk
        actor_id, actor_headers, actor_secret = _fresh_super_admin("normal-actor")
        target_id = _mk(f"normal-target-{uuid.uuid4().hex[:6]}@test.local", "waiter")

        reason = "تعطيل حساب نادل غادر المنتجع نهائيًا"
        token = _issue_step_up(
            client, actor_headers, purpose="user_role_update",
            intent={"user_id": target_id, "role": None, "is_active": False, "reason": reason},
            totp_secret=actor_secret,
        )
        resp = client.patch(
            f"/api/v1/users/{target_id}/role", json={"is_active": False, "reason": reason},
            headers={**actor_headers, "X-Step-Up-Token": token},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["role"] == "waiter"        # مالمسناهوش
        assert body["is_active"] is False

        import json as _json
        from app.modules.core.models import AuditLog
        log = (
            db.query(AuditLog)
            .filter(AuditLog.entity_type == "user", AuditLog.entity_id == target_id,
                    AuditLog.action == "update_role")
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert log is not None
        assert log.user_id == actor_id
        new_data = _json.loads(log.new_data)
        # الحالة النهائية الفعلية (role اتحسب من الصف الحالي، مش None خام)
        assert new_data["role"] == "waiter"
        assert new_data["is_active"] is False
        # سياق step-up (Gate 2B3A) — بلا أي سر (لا كلمة سر، لا TOTP، لا token خام)
        assert new_data["reason"] == reason
        assert new_data["assurance_method"] == "totp"
        assert "step_up_public_reference" in new_data
        assert "current_password" not in new_data
        assert "totp_code" not in new_data


class TestActorNoLongerActiveSuperAdminRejectedDeterministic:
    """إثبات حتمي (بدون threads) لمسار إعادة تحقق المنفّذ تحت القفل —
    مكمّل لإثبات التزامن الحقيقي في test_super_admin_concurrency.py، مش
    بديل عنه. يحاكي "المنفّذ اتغيّرت صلاحيته في نفس اللحظة" بتعديل حالته
    مباشرة بين لحظة المصادقة ولحظة تنفيذ service.update_user_role.

    استدعاء مباشر لـservice (مش HTTP) — reason/step-up اختياريان على
    مستوى service (راجع core/services.py::update_user_role)، فمفيش داعي
    ليهم هنا."""

    def test_actor_demoted_between_auth_and_execution_is_rejected(self, db):
        from app.core.kernel.models.user import User
        from app.modules.core import services as core_services

        actor_id, _, _ = _fresh_super_admin("race-actor")
        target_id, _, _ = _fresh_super_admin("race-target")

        # بمحاكاة سباق حقيقي: المنفّذ عدّى get_super_admin_user (كان نشط
        # وقتها)، لكن بحلول لحظة تنفيذ service الفعلي، حساب تاني كان غيّر
        # حالته بالفعل (commit سابق مباشرة، مش نفس الـtransaction).
        actor = db.query(User).filter(User.id == actor_id).first()
        actor.is_active = False
        db.commit()

        with pytest.raises(core_services.ActorSuperAdminPrivilegesChangedError):
            core_services.update_user_role(
                db, target_id, role="manager", is_active=None, updated_by=actor_id,
            )
        db.rollback()

        target = db.query(User).filter(User.id == target_id).first()
        assert target.role == "super_admin"
