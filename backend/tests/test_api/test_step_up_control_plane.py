"""
tests/test_api/test_step_up_control_plane.py
Gate 2B3A — Step-Up Control Plane (Decision 0003 follow-up).

يغطي هذا الملف المسارات اللي مش مغطاة بالفعل في test_super_admin_invariants.py
وtest_permissions.py (رفض/قبول step-up على الأربعة endpoints المحمية) —
هنا التركيز على:
  1. إصدار الإثبات نفسه (POST /auth/step-up): باسورد غلط، TOTP/recovery
     صحيح، منع الاستخدام المزدوج (totp+recovery)، دور إجباري 2FA بلا 2FA
     مفعّل مرفوض دايمًا، إعادة استخدام كود TOTP بين تسجيل الدخول والـstep-up.
  2. استهلاك الإثبات: توكن ناقص (428)، منتهي/مُعاد استخدامه/لمستخدم أو جلسة
     أو purpose أو scope مختلف (403 STEP_UP_INVALID موحّد)، تغيير الـpayload
     الفعلي بعد الإصدار بيُبطل الإثبات.
  3. عدم تسرّب أي سر (باسورد/TOTP/recovery/التوكن الخام) لا في step_up_grants
     ولا في AuditLog.
  4. عزل الفروع للإعدادات (branch isolation) — قراءة/كتابة فرع حقيقي،
     الإعدادات العامة (Global) مقصورة على super_admin، والـfallback الداخلي
     (get_setting_value) محفوظ زي ما هو للخدمات الداخلية.

راجع docs/decisions/0003-super-admin-control-plane.md ثم
docs/audits/gate-2b3a-step-up-control-plane.md للتصميم الكامل.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pyotp
import pytest
from fastapi.testclient import TestClient

from tests.conftest import _create_test_user, _fresh_super_admin, _issue_step_up, _make_token


# ─────────────────────── Shared fixtures/helpers ──────────────────────────

def _fresh_manager_no_2fa(email_prefix: str = "mgr") -> tuple[int, dict[str, str]]:
    """manager عادي (مش من الأدوار الإجبارية لـ2FA) — لاختبار مسار
    password_only assurance."""
    email = f"{email_prefix}-{uuid.uuid4().hex[:8]}@test.local"
    user_id = _create_test_user(email, "manager")
    return user_id, {"Authorization": f"Bearer {_make_token(email)}"}


def _branch(db, name: str = "Step-Up Branch"):
    from app.modules.core.models import Branch
    b = Branch(name=name, name_ar="فرع اختبار step-up", code=f"SU-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def _branch_linked_manager(db, branch) -> tuple[int, dict[str, str]]:
    """manager مربوط فعليًا بـHR.Employee.branch_id — لازم لاختبار عزل
    الفروع الحقيقي (assert_branch_access)."""
    from app.modules.hr.models import Employee

    email = f"branch-mgr-{uuid.uuid4().hex[:8]}@test.local"
    user_id = _create_test_user(email, "manager")
    emp = Employee(
        branch_id=branch.id, employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
        full_name="مدير فرع اختبار step-up", position="Manager", department="Admin",
        basic_salary=Decimal("8000.00"), hire_date=date.today() - timedelta(days=200),
        user_id=user_id,
    )
    db.add(emp)
    db.commit()
    return user_id, {"Authorization": f"Bearer {_make_token(email)}"}


def _sample_role_update_intent(user_id: int, reason: str) -> dict:
    return {"user_id": user_id, "role": "manager", "is_active": None, "reason": reason}


# ═════════════════════ Part A — إصدار الإثبات (issuance) ═══════════════════

class TestStepUpIssuance:
    def test_wrong_password_does_not_issue_proof(self, client: TestClient):
        _sa_id, sa_headers, sa_secret = _fresh_super_admin("issue-wrongpw")
        resp = client.post(
            "/api/v1/auth/step-up",
            json={
                "current_password": "not-the-real-password",
                "purpose": "user_role_update",
                "intent": {"user_id": _sa_id, "role": "manager", "is_active": None, "reason": "سبب"},
                "totp_code": pyotp.TOTP(sa_secret).now(),
            },
            headers=sa_headers,
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "CURRENT_PASSWORD_REQUIRED"

    def test_correct_totp_issues_proof_with_totp_assurance(self, client: TestClient):
        _sa_id, sa_headers, sa_secret = _fresh_super_admin("issue-totp-ok")
        token = _issue_step_up(
            client, sa_headers, purpose="user_role_update",
            intent=_sample_role_update_intent(_sa_id, "تجربة إصدار عادي"),
            totp_secret=sa_secret,
        )
        assert token

    def test_correct_recovery_code_issues_proof_and_is_single_use(self, client: TestClient, db):
        """كود استرداد بيُستهلك من نفس المخزون المستخدم في تسجيل الدخول —
        مفيش استخدام تاني ليه، لا في login ولا في step-up تاني."""
        from app.core.kernel.auth.service import AuthService
        from app.core.kernel.models.user import TwoFactorRecoveryCode, User

        _sa_id, sa_headers, sa_secret = _fresh_super_admin("issue-recovery")
        raw_code = AuthService._new_recovery_code()
        user = db.query(User).filter(User.id == _sa_id).first()
        db.add(TwoFactorRecoveryCode(user_id=user.id, code_hash=AuthService._recovery_code_hash(raw_code)))
        db.commit()

        intent1 = _sample_role_update_intent(_sa_id, "أول استخدام لكود الاسترداد")
        resp1 = client.post(
            "/api/v1/auth/step-up",
            json={
                "current_password": "Test@12345", "purpose": "user_role_update",
                "intent": intent1, "recovery_code": raw_code,
            },
            headers=sa_headers,
        )
        assert resp1.status_code == 200, resp1.text
        assert resp1.json()["assurance_method"] == "recovery_code"

        # نفس كود الاسترداد تاني — لازم يترفض (مُستهلَك بالفعل)
        intent2 = _sample_role_update_intent(_sa_id, "محاولة إعادة استخدام نفس الكود")
        resp2 = client.post(
            "/api/v1/auth/step-up",
            json={
                "current_password": "Test@12345", "purpose": "user_role_update",
                "intent": intent2, "recovery_code": raw_code,
            },
            headers=sa_headers,
        )
        assert resp2.status_code == 401
        assert resp2.json()["detail"]["code"] == "2FA_CODE_INVALID"

    def test_totp_and_recovery_code_together_is_rejected(self, client: TestClient):
        _sa_id, sa_headers, sa_secret = _fresh_super_admin("issue-ambiguous")
        resp = client.post(
            "/api/v1/auth/step-up",
            json={
                "current_password": "Test@12345", "purpose": "user_role_update",
                "intent": _sample_role_update_intent(_sa_id, "سبب"),
                "totp_code": pyotp.TOTP(sa_secret).now(), "recovery_code": "AAAA-BBBB-CCCC",
            },
            headers=sa_headers,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "STEP_UP_PROOF_AMBIGUOUS"

    def test_mandatory_role_without_2fa_never_gets_password_only_bypass(self, client: TestClient):
        """super_admin بدون 2FA مفعّل خالص — get_current_user (المستخدم في
        /auth/*) بيسمحله يوصل للـendpoint (عكس get_current_active_user)،
        لكن issue_step_up لازم يرفضه صراحةً، مش يوافق على password-only."""
        email = f"sa-no2fa-{uuid.uuid4().hex[:8]}@test.local"
        user_id = _create_test_user(email, "super_admin")  # two_factor_enabled=False افتراضيًا
        headers = {"Authorization": f"Bearer {_make_token(email)}"}

        resp = client.post(
            "/api/v1/auth/step-up",
            json={
                "current_password": "Test@12345", "purpose": "user_role_update",
                "intent": _sample_role_update_intent(user_id, "محاولة تجاوز 2FA الإجباري"),
            },
            headers=headers,
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "MANDATORY_2FA_REQUIRED"

    def test_non_mandatory_role_without_2fa_gets_password_only_assurance(self, client: TestClient):
        _mgr_id, mgr_headers = _fresh_manager_no_2fa("issue-pwonly")
        resp = client.post(
            "/api/v1/auth/step-up",
            json={
                "current_password": "Test@12345", "purpose": "user_role_update",
                "intent": _sample_role_update_intent(_mgr_id, "مدير بلا 2FA — password-only مسموح"),
            },
            headers=mgr_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["assurance_method"] == "password_only"

    def test_totp_code_reused_from_login_is_rejected_at_step_up(self, client: TestClient):
        """نفس عدّاد TOTP (two_factor_last_used_step) مشترك بين login
        وstep-up — كود اتستخدم في تسجيل الدخول ميتقبلش تاني هنا."""
        _sa_id, sa_headers, sa_secret = _fresh_super_admin("issue-totp-replay")
        code = pyotp.TOTP(sa_secret).now()

        from tests.conftest import TestingSessionLocal
        from app.core.kernel.auth.service import AuthService
        from app.core.kernel.models.user import User as _KernelUser
        from app.core.config import settings as app_settings

        db = TestingSessionLocal()
        try:
            auth = AuthService(db, _KernelUser, app_settings)
            user = db.query(_KernelUser).filter(_KernelUser.id == _sa_id).first()
            assert auth._consume_totp_code(user, code) is True
            db.commit()
        finally:
            db.close()

        resp = client.post(
            "/api/v1/auth/step-up",
            json={
                "current_password": "Test@12345", "purpose": "user_role_update",
                "intent": _sample_role_update_intent(_sa_id, "محاولة إعادة استخدام كود من تسجيل دخول"),
                "totp_code": code,
            },
            headers=sa_headers,
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "2FA_CODE_INVALID"

    def test_unknown_purpose_rejected(self, client: TestClient):
        _sa_id, sa_headers, sa_secret = _fresh_super_admin("issue-badpurpose")
        resp = client.post(
            "/api/v1/auth/step-up",
            json={
                "current_password": "Test@12345", "purpose": "finance.void_payment",
                "intent": {}, "totp_code": pyotp.TOTP(sa_secret).now(),
            },
            headers=sa_headers,
        )
        assert resp.status_code == 422

    def test_string_allowed_value_is_rejected_before_consuming_totp(self, client: TestClient, db):
        """The step-up contract is deliberately strict: a JSON string is not
        a JSON boolean. Rejection happens before identity proof consumption,
        so the same TOTP counter remains usable by a valid request."""
        sa_id, sa_headers, sa_secret = _fresh_super_admin("issue-string-allowed")
        target_id = _create_test_user(f"target-{uuid.uuid4().hex[:6]}@test.local", "waiter")
        reason = "تحقق من تحويل allowed الآمن"

        code = pyotp.TOTP(sa_secret).now()
        malformed = client.post(
            "/api/v1/auth/step-up",
            json={
                "current_password": "Test@12345",
                "purpose": "permission_override_upsert",
                "intent": {"user_id": target_id, "resource": "dining.void_order_item",
                           "action": "execute", "allowed": "false", "branch_id": None,
                           "reason": reason},
                "totp_code": code,
            },
            headers=sa_headers,
        )
        assert malformed.status_code == 422

        valid = client.post(
            "/api/v1/auth/step-up",
            json={
                "current_password": "Test@12345",
                "purpose": "permission_override_upsert",
                "intent": {"user_id": target_id, "resource": "dining.void_order_item",
                           "action": "execute", "allowed": False, "branch_id": None,
                           "reason": reason},
                "totp_code": code,
            },
            headers=sa_headers,
        )
        assert valid.status_code == 200, valid.text

    def test_unknown_role_intent_is_rejected_before_consuming_totp(self, client: TestClient):
        sa_id, sa_headers, sa_secret = _fresh_super_admin("issue-unknown-role")
        code = pyotp.TOTP(sa_secret).now()
        malformed = client.post(
            "/api/v1/auth/step-up",
            json={
                "current_password": "Test@12345", "purpose": "user_role_update",
                "intent": {"user_id": sa_id, "role": "manger", "is_active": None,
                           "reason": "دور غير معروف"},
                "totp_code": code,
            },
            headers=sa_headers,
        )
        assert malformed.status_code == 422

        valid = client.post(
            "/api/v1/auth/step-up",
            json={
                "current_password": "Test@12345", "purpose": "user_role_update",
                "intent": _sample_role_update_intent(sa_id, "دور صحيح بعد الرفض"),
                "totp_code": code,
            },
            headers=sa_headers,
        )
        assert valid.status_code == 200, valid.text

    def test_intent_with_unexpected_extra_field_rejected(self, client: TestClient):
        _sa_id, sa_headers, sa_secret = _fresh_super_admin("issue-extra-field")
        resp = client.post(
            "/api/v1/auth/step-up",
            json={
                "current_password": "Test@12345", "purpose": "user_role_update",
                "intent": {
                    "user_id": _sa_id, "role": "manager", "is_active": None,
                    "reason": "سبب", "unexpected_field": "should be rejected",
                },
                "totp_code": pyotp.TOTP(sa_secret).now(),
            },
            headers=sa_headers,
        )
        assert resp.status_code == 422


# ═════════════════════ Part B — استهلاك الإثبات (consumption) ═════════════

class TestStepUpConsumption:
    def test_missing_token_returns_428(self, client: TestClient):
        _sa_id, sa_headers, _secret = _fresh_super_admin("consume-missing")
        target_id = _create_test_user(f"target-{uuid.uuid4().hex[:6]}@test.local", "waiter")
        resp = client.patch(
            f"/api/v1/users/{target_id}/role",
            json={"role": "manager", "reason": "بدون أي step-up token"},
            headers=sa_headers,
        )
        assert resp.status_code == 428
        assert resp.json()["detail"]["error_code"] == "STEP_UP_REQUIRED"

    def test_expired_token_is_rejected_generically(self, client: TestClient, db):
        _sa_id, sa_headers, sa_secret = _fresh_super_admin("consume-expired")
        target_id = _create_test_user(f"target-{uuid.uuid4().hex[:6]}@test.local", "waiter")
        reason = "محاولة استخدام إثبات منتهي الصلاحية"
        token = _issue_step_up(
            client, sa_headers, purpose="user_role_update",
            intent={"user_id": target_id, "role": "manager", "is_active": None, "reason": reason},
            totp_secret=sa_secret,
        )
        from app.core.kernel.models.user import StepUpGrant
        grant = db.query(StepUpGrant).filter(StepUpGrant.user_id == _sa_id).first()
        assert grant is not None
        grant.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()

        resp = client.patch(
            f"/api/v1/users/{target_id}/role",
            json={"role": "manager", "reason": reason},
            headers={**sa_headers, "X-Step-Up-Token": token},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error_code"] == "STEP_UP_INVALID"

    def test_replayed_token_only_succeeds_once(self, client: TestClient):
        _sa_id, sa_headers, sa_secret = _fresh_super_admin("consume-replay")
        target_id = _create_test_user(f"target-{uuid.uuid4().hex[:6]}@test.local", "waiter")
        reason = "تجربة إعادة استخدام نفس الإثبات مرتين"
        token = _issue_step_up(
            client, sa_headers, purpose="user_role_update",
            intent={"user_id": target_id, "role": "manager", "is_active": None, "reason": reason},
            totp_secret=sa_secret,
        )
        body = {"role": "manager", "reason": reason}
        first = client.patch(
            f"/api/v1/users/{target_id}/role", json=body,
            headers={**sa_headers, "X-Step-Up-Token": token},
        )
        assert first.status_code == 200, first.text

        second = client.patch(
            f"/api/v1/users/{target_id}/role", json=body,
            headers={**sa_headers, "X-Step-Up-Token": token},
        )
        assert second.status_code == 403
        assert second.json()["detail"]["error_code"] == "STEP_UP_INVALID"

    def test_token_for_different_user_is_rejected(self, client: TestClient):
        """توكن أُصدر لحساب A ما ينفعش يُستهلك من طلب مصدَّق باسم حساب B —
        حتى لو الاتنين super_admin نشطين."""
        a_id, a_headers, a_secret = _fresh_super_admin("consume-user-a")
        _b_id, b_headers, _b_secret = _fresh_super_admin("consume-user-b")
        target_id = _create_test_user(f"target-{uuid.uuid4().hex[:6]}@test.local", "waiter")
        reason = "توكن حساب تاني"
        token = _issue_step_up(
            client, a_headers, purpose="user_role_update",
            intent={"user_id": target_id, "role": "manager", "is_active": None, "reason": reason},
            totp_secret=a_secret,
        )
        resp = client.patch(
            f"/api/v1/users/{target_id}/role", json={"role": "manager", "reason": reason},
            headers={**b_headers, "X-Step-Up-Token": token},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error_code"] == "STEP_UP_INVALID"

    def test_token_bound_to_different_session_is_rejected(self, client: TestClient):
        """نفس المستخدم بالظبط، لكن access token مختلف (جلسة تانية) —
        access_token_hash المُخزَّن وقت الإصدار ميطابقش."""
        sa_id, sa_headers, sa_secret = _fresh_super_admin("consume-session")
        target_id = _create_test_user(f"target-{uuid.uuid4().hex[:6]}@test.local", "waiter")
        reason = "توكن جلسة تانية لنفس المستخدم"
        token = _issue_step_up(
            client, sa_headers, purpose="user_role_update",
            intent={"user_id": target_id, "role": "manager", "is_active": None, "reason": reason},
            totp_secret=sa_secret,
        )
        # نفس الإيميل، JWT مختلف تمامًا (iat مُزاح صراحةً بثانية كاملة —
        # _make_token بيقرّب الزمن لثوانٍ، فاستدعاءين متتاليين ممكن ينتجوا
        # نفس التوكن حرفيًا لو حصلوا في نفس الثانية، ده كان بيخلي هذا
        # الاختبار يمر بالغلط من غير ما يفحص حاجة فعلية)
        email = _email_from_jwt(sa_headers)
        other_session_headers = {"Authorization": f"Bearer {_make_token_at_offset(email, offset_seconds=5)}"}
        resp = client.patch(
            f"/api/v1/users/{target_id}/role", json={"role": "manager", "reason": reason},
            headers={**other_session_headers, "X-Step-Up-Token": token},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error_code"] == "STEP_UP_INVALID"

    def test_token_for_wrong_purpose_is_rejected(self, client: TestClient):
        sa_id, sa_headers, sa_secret = _fresh_super_admin("consume-wrongpurpose")
        target_id = _create_test_user(f"target-{uuid.uuid4().hex[:6]}@test.local", "waiter")
        reason = "إثبات لعملية تانية تمامًا"
        # اتصدر لـpermission_override_revoke مش user_role_update
        token = _issue_step_up(
            client, sa_headers, purpose="permission_override_revoke",
            intent={"permission_id": 999999, "reason": reason},
            totp_secret=sa_secret,
        )
        resp = client.patch(
            f"/api/v1/users/{target_id}/role", json={"role": "manager", "reason": reason},
            headers={**sa_headers, "X-Step-Up-Token": token},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error_code"] == "STEP_UP_INVALID"

    def test_changing_role_after_issuance_invalidates_the_proof(self, client: TestClient):
        """الإثبات اتصدر لـrole="manager"، لكن الطلب الفعلي بيطلب role="admin"
        — الـscope_hash يختلف، فالاستهلاك يترفض."""
        sa_id, sa_headers, sa_secret = _fresh_super_admin("consume-scopechange")
        target_id = _create_test_user(f"target-{uuid.uuid4().hex[:6]}@test.local", "waiter")
        reason = "تغيير الدور المطلوب بعد إصدار الإثبات"
        token = _issue_step_up(
            client, sa_headers, purpose="user_role_update",
            intent={"user_id": target_id, "role": "manager", "is_active": None, "reason": reason},
            totp_secret=sa_secret,
        )
        resp = client.patch(
            f"/api/v1/users/{target_id}/role", json={"role": "admin", "reason": reason},
            headers={**sa_headers, "X-Step-Up-Token": token},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error_code"] == "STEP_UP_INVALID"

    def test_changing_setting_value_after_issuance_invalidates_the_proof(self, client: TestClient):
        sa_id, sa_headers, sa_secret = _fresh_super_admin("consume-settingchange")
        key = f"setting-{uuid.uuid4().hex[:6]}"
        reason = "تغيير القيمة الفعلية بعد إصدار الإثبات"
        token = _issue_step_up(
            client, sa_headers, purpose="setting_upsert",
            intent={"key": key, "branch_id": None, "value": "original", "reason": reason},
            totp_secret=sa_secret,
        )
        resp = client.put(
            f"/api/v1/settings/{key}", json={"value": "tampered", "reason": reason},
            headers={**sa_headers, "X-Step-Up-Token": token},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error_code"] == "STEP_UP_INVALID"

    def test_changing_allowed_flag_after_issuance_invalidates_the_proof(self, client: TestClient):
        sa_id, sa_headers, sa_secret = _fresh_super_admin("consume-allowedchange")
        target_id = _create_test_user(f"target-{uuid.uuid4().hex[:6]}@test.local", "waiter")
        reason = "تغيير allowed بعد إصدار الإثبات"
        token = _issue_step_up(
            client, sa_headers, purpose="permission_override_upsert",
            intent={"user_id": target_id, "resource": "dining.void_order_item",
                    "action": "execute", "allowed": True, "branch_id": None, "reason": reason},
            totp_secret=sa_secret,
        )
        resp = client.post(
            "/api/v1/permissions",
            json={"user_id": target_id, "resource": "dining.void_order_item",
                  "action": "execute", "allowed": False, "reason": reason},
            headers={**sa_headers, "X-Step-Up-Token": token},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error_code"] == "STEP_UP_INVALID"

    def test_reason_appears_in_audit_log(self, client: TestClient, db):
        sa_id, sa_headers, sa_secret = _fresh_super_admin("consume-auditreason")
        target_id = _create_test_user(f"target-{uuid.uuid4().hex[:6]}@test.local", "waiter")
        reason = "سبب واضح لازم يظهر في سجل التدقيق"
        token = _issue_step_up(
            client, sa_headers, purpose="user_role_update",
            intent={"user_id": target_id, "role": "manager", "is_active": None, "reason": reason},
            totp_secret=sa_secret,
        )
        resp = client.patch(
            f"/api/v1/users/{target_id}/role", json={"role": "manager", "reason": reason},
            headers={**sa_headers, "X-Step-Up-Token": token},
        )
        assert resp.status_code == 200, resp.text

        import json as _json
        from app.modules.core.models import AuditLog
        log = (
            db.query(AuditLog)
            .filter(AuditLog.entity_type == "user", AuditLog.entity_id == target_id,
                    AuditLog.action == "update_role")
            .order_by(AuditLog.id.desc()).first()
        )
        assert log is not None
        new_data = _json.loads(log.new_data)
        assert new_data["reason"] == reason
        assert "step_up_public_reference" in new_data


def _email_from_jwt(headers: dict[str, str]) -> str:
    """بيفكّ الـsub (الإيميل) من JWT موجود بالفعل — لتوليد توكن *تاني* لنفس
    المستخدم (جلسة مختلفة) بدون تخزين الإيميل بشكل منفصل في التست."""
    from jose import jwt as _jwt
    raw = headers["Authorization"].split()[-1]
    payload = _jwt.get_unverified_claims(raw)
    return payload["sub"]


def _make_token_at_offset(email: str, *, offset_seconds: int) -> str:
    """زي tests.conftest._make_token بالظبط، لكن بـiat مُزاح صراحةً — يضمن
    JWT مختلف حرفيًا (وبالتالي access_token_hash مختلف) لنفس المستخدم، بدل
    الاعتماد على فرق زمني طبيعي بين استدعاءين قد يقعا في نفس الثانية."""
    import os
    from jose import jwt as _jwt

    secret = os.environ["SECRET_KEY"]
    now = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=offset_seconds)
    payload = {"sub": email, "iat": now, "exp": now + timedelta(hours=1)}
    return _jwt.encode(payload, secret, algorithm="HS256")


# ═════════════════════ Part C — لا تسرّب لأي سر ════════════════════════════

class TestStepUpSecretHygiene:
    def test_no_plaintext_token_or_password_anywhere_in_db(self, client: TestClient, db):
        sa_id, sa_headers, sa_secret = _fresh_super_admin("secrecy")
        target_id = _create_test_user(f"target-{uuid.uuid4().hex[:6]}@test.local", "waiter")
        reason = "فحص عدم تسرب الأسرار"
        totp_code = pyotp.TOTP(sa_secret).now()
        resp = client.post(
            "/api/v1/auth/step-up",
            json={
                "current_password": "Test@12345", "purpose": "user_role_update",
                "intent": {"user_id": target_id, "role": "manager", "is_active": None, "reason": reason},
                "totp_code": totp_code,
            },
            headers=sa_headers,
        )
        assert resp.status_code == 200
        plaintext_token = resp.json()["step_up_token"]

        client.patch(
            f"/api/v1/users/{target_id}/role", json={"role": "manager", "reason": reason},
            headers={**sa_headers, "X-Step-Up-Token": plaintext_token},
        )

        # step_up_grants: الصف اتحذف عند الاستهلاك (لا يوجد أي أثر متبقٍ)
        from app.core.kernel.models.user import StepUpGrant
        assert db.query(StepUpGrant).filter(StepUpGrant.user_id == sa_id).count() == 0

        # AuditLog: مفيش plaintext_token ولا كلمة السر ولا كود TOTP في أي عمود نصي
        from app.modules.core.models import AuditLog
        rows = db.query(AuditLog).all()
        for row in rows:
            for field in (row.old_data, row.new_data):
                if not field:
                    continue
                assert plaintext_token not in field
                assert "Test@12345" not in field
                assert totp_code not in field


# ═════════════════════ Part D — عزل الفروع للإعدادات ═══════════════════════
# Part 1 من مواصفة Gate 2B3A: قراءة/كتابة فرع حقيقية عبر assert_branch_access
# (مش الثقة في branch_id القادم من العميل)، والإعدادات العامة (Global،
# branch_id غير مُرسَل) مقصورة على super_admin قراءةً وكتابةً.

class TestSettingsBranchIsolation:
    def test_manager_cannot_read_another_branch_settings(self, client: TestClient, db):
        branch_a = _branch(db, "Branch A")
        branch_b = _branch(db, "Branch B")
        _mgr_a_id, mgr_a_headers = _branch_linked_manager(db, branch_a)

        resp = client.get(
            "/api/v1/settings", params={"branch_id": branch_b.id}, headers=mgr_a_headers,
        )
        assert resp.status_code == 403

    def test_manager_does_not_receive_global_fallback_for_own_branch(self, client: TestClient, db):
        """مراجعة Codex المستقلة (2026-07-18، High #1): مدير فرع حقيقي
        بيطلب مفتاح مش موجود لفرعه — قبل التصحيح كان GET /settings/{key}
        بيستخدم crud.get_setting() (بترجع fallback ضمني للإعداد العام)،
        يعني كان بياخد قيمة الإعداد العام بصمت رغم إنه محدد branch_id
        صريح خاص بيه. بعد التصحيح: get_setting_exact() بدون أي fallback
        — لازم يرجع 404، مش 200 بقيمة الإعداد العام."""
        branch = _branch(db, "Fallback Leak Branch")
        sa_id, sa_headers, sa_secret = _fresh_super_admin("global-fallback-leak-actor")
        _mgr_id, mgr_headers = _branch_linked_manager(db, branch)

        key = f"global-only-{uuid.uuid4().hex[:6]}"
        reason = "إعداد عام بدون أي صف خاص بأي فرع"
        token = _issue_step_up(
            client, sa_headers, purpose="setting_upsert",
            intent={"key": key, "branch_id": None, "value": "global-secret-value", "reason": reason},
            totp_secret=sa_secret,
        )
        create_resp = client.put(
            f"/api/v1/settings/{key}",
            json={"value": "global-secret-value", "reason": reason},
            headers={**sa_headers, "X-Step-Up-Token": token},
        )
        assert create_resp.status_code == 200, create_resp.text

        # مدير الفرع بيطلب نفس المفتاح صراحةً لفرعه — مفيش صف خاص بالفرع
        # ده خالص، فمفروض 404، مش 200 بقيمة الإعداد العام المتسرّبة.
        leak_resp = client.get(
            f"/api/v1/settings/{key}", params={"branch_id": branch.id}, headers=mgr_headers,
        )
        assert leak_resp.status_code == 404, (
            f"تسرّب قيمة إعداد عام لمدير فرع عبر fallback ضمني: {leak_resp.text}"
        )

    def test_manager_cannot_write_another_branch_settings(self, client: TestClient, db):
        branch_a = _branch(db, "Branch A")
        branch_b = _branch(db, "Branch B")
        _mgr_a_id, mgr_a_headers = _branch_linked_manager(db, branch_a)

        resp = client.put(
            f"/api/v1/settings/some-key", params={"branch_id": branch_b.id},
            json={"value": "x", "reason": "محاولة كتابة عبر فروع"},
            headers=mgr_a_headers,
        )
        assert resp.status_code == 403

    def test_manager_can_read_and_write_own_branch_settings(self, client: TestClient, db):
        branch = _branch(db, "Own Branch")
        sa_id, sa_headers, sa_secret = _fresh_super_admin("settings-own-branch-actor")
        _mgr_id, mgr_headers = _branch_linked_manager(db, branch)

        key = f"branch-setting-{uuid.uuid4().hex[:6]}"
        reason = "تعديل إعداد الفرع الخاص بالمدير"
        token = _issue_step_up(
            client, sa_headers, purpose="setting_upsert",
            intent={"key": key, "branch_id": branch.id, "value": "42", "reason": reason},
            totp_secret=sa_secret,
        )
        # الكتابة محتاجة admin+ — manager مش كفاية بغض النظر عن الفرع (السلوك
        # الأصلي قبل Gate 2B3A لسه محفوظ، الجديد بس عزل الفرع فوقه)
        write_resp = client.put(
            f"/api/v1/settings/{key}", params={"branch_id": branch.id},
            json={"value": "42", "reason": reason},
            headers={**sa_headers, "X-Step-Up-Token": token},
        )
        assert write_resp.status_code == 200, write_resp.text

        read_resp = client.get(
            f"/api/v1/settings/{key}", params={"branch_id": branch.id}, headers=mgr_headers,
        )
        assert read_resp.status_code == 200
        assert read_resp.json()["value"] == "42"

    def test_global_settings_unreadable_by_non_super_admin(self, client: TestClient, db):
        branch = _branch(db, "Some Branch")
        _mgr_id, mgr_headers = _branch_linked_manager(db, branch)
        # branch_id مش مُرسَل خالص → Global
        resp = client.get("/api/v1/settings", headers=mgr_headers)
        assert resp.status_code == 403

    def test_global_settings_unwritable_by_non_super_admin(self, client: TestClient, db):
        branch = _branch(db, "Some Branch")
        _mgr_id, mgr_headers = _branch_linked_manager(db, branch)
        from tests.conftest import _create_test_user, _make_token
        admin_email = f"global-write-admin-{uuid.uuid4().hex[:6]}@test.local"
        _create_test_user(admin_email, "admin")
        admin_headers = {"Authorization": f"Bearer {_make_token(admin_email)}"}

        resp = client.put(
            "/api/v1/settings/vat_percentage",
            json={"value": "15", "reason": "محاولة كتابة إعداد عام من admin عادي"},
            headers=admin_headers,
        )
        assert resp.status_code == 403

    def test_super_admin_bypasses_branch_isolation(self, client: TestClient, db):
        branch_a = _branch(db, "Branch A")
        branch_b = _branch(db, "Branch B")
        sa_id, sa_headers, sa_secret = _fresh_super_admin("settings-sa-bypass")

        key = f"cross-branch-setting-{uuid.uuid4().hex[:6]}"
        reason = "super_admin بيقدر يعدّل إعدادات أي فرع"
        token = _issue_step_up(
            client, sa_headers, purpose="setting_upsert",
            intent={"key": key, "branch_id": branch_b.id, "value": "7", "reason": reason},
            totp_secret=sa_secret,
        )
        resp = client.put(
            f"/api/v1/settings/{key}", params={"branch_id": branch_b.id},
            json={"value": "7", "reason": reason},
            headers={**sa_headers, "X-Step-Up-Token": token},
        )
        assert resp.status_code == 200, resp.text
        assert branch_a.id != branch_b.id  # sanity: فرعين مختلفين فعليًا

    def test_internal_global_fallback_still_works_for_get_setting_value(self, db):
        """get_setting_value() الداخلية (تسعير الشاطئ وغيره) لازم تفضل
        بترجع القيمة العامة تلقائيًا لما مفيش صف خاص بالفرع — الفحص الجديد
        (Part 1) على مستوى الـHTTP endpoint بس، مش جوه الدالة الداخلية دي."""
        from app.modules.core import crud, services

        branch = _branch(db, "Fallback Branch")
        key = f"fallback-setting-{uuid.uuid4().hex[:6]}"
        crud.upsert_setting(db, key, "global-value", branch_id=None)
        db.commit()

        # مفيش صف خاص بالفرع خالص — لازم يرجع القيمة العامة (fallback)
        value = services.get_setting_value(db, key, branch_id=branch.id)
        assert value == "global-value"


# ═════════ Part E — تصحيحات مراجعة Codex المستقلة (2026-07-18) ═════════
# High #2: سباق TOCTOU — المنفّذ ممكن يفقد صلاحيته (أو الهدف يترقّى
# لـsuper_admin) في النافذة بين استهلاك step-up والـmutation الفعلي.
# التستات دي حتمية (thread واحد، بتحاكي السباق يدويًا بتعديل مباشر على
# الحالة) — مكمّلة، مش بديلة، لإثبات التزامن الحقيقي على Postgres في
# tests/test_step_up_concurrency.py.

class TestActorAuthorizationChangedDeterministic:
    def test_grant_permission_rejected_if_actor_demoted_after_step_up(self, db):
        from app.core.kernel.models.user import User
        from app.modules.core import services as core_services
        from app.modules.core.schemas import UserPermissionCreate

        sa_id, _headers, _secret = _fresh_super_admin("toctou-grant-actor")
        target_id = _create_test_user(f"toctou-target-{uuid.uuid4().hex[:6]}@test.local", "waiter")

        # يحاكي: step-up استهلاك نجح، وقبل تنفيذ grant_permission الفعلي
        # (لسه في نفس الطلب) معاملة متزامنة خفّضت المنفّذ بالفعل.
        actor = db.query(User).filter(User.id == sa_id).first()
        actor.role = "manager"
        db.commit()

        with pytest.raises(core_services.ActorAuthorizationChangedError):
            core_services.grant_permission(
                db, target_id,
                UserPermissionCreate(resource="dining.void_order_item", action="execute", allowed=True),
                granted_by=sa_id,
            )
        db.rollback()

        from app.modules.core import crud as core_crud
        assert core_crud.find_explicit_permission(db, target_id, "dining.void_order_item", "execute") is None

    def test_revoke_permission_rejected_if_actor_deactivated_after_step_up(self, db):
        from app.core.kernel.models.user import User
        from app.modules.core import crud as core_crud
        from app.modules.core import services as core_services
        from app.modules.core.schemas import UserPermissionCreate

        sa_id, _headers, _secret = _fresh_super_admin("toctou-revoke-actor")
        target_id = _create_test_user(f"toctou-target2-{uuid.uuid4().hex[:6]}@test.local", "waiter")
        legacy = core_crud.upsert_user_permission(
            db, target_id,
            UserPermissionCreate(resource="dining.void_order_item", action="execute", allowed=True),
            granted_by=sa_id,
        )
        db.commit()
        legacy_id = legacy.id

        actor = db.query(User).filter(User.id == sa_id).first()
        actor.is_active = False
        db.commit()

        with pytest.raises(core_services.ActorAuthorizationChangedError):
            core_services.revoke_permission(db, legacy_id, revoked_by=sa_id)
        db.rollback()

        assert core_crud.get_user_permission(db, legacy_id) is not None

    def test_upsert_setting_rejected_if_actor_demoted_after_step_up(self, db):
        from app.core.kernel.models.user import User
        from app.modules.core import services as core_services

        sa_id, _headers, _secret = _fresh_super_admin("toctou-setting-actor")
        key = f"toctou-setting-{uuid.uuid4().hex[:6]}"

        actor = db.query(User).filter(User.id == sa_id).first()
        actor.role = "waiter"  # تحت مستوى admin المطلوب حتى للإعدادات الفرعية
        db.commit()

        with pytest.raises(core_services.ActorAuthorizationChangedError):
            core_services.upsert_setting(db, key, "tampered", branch_id=None, updated_by=sa_id)
        db.rollback()

        from app.modules.core import crud as core_crud
        assert core_crud.get_setting_exact(db, key, None) is None

    # ملحوظة: لا يوجد اختبار HTTP-level مكافئ هنا — TestClient بيشغّل الطلب
    # كله بالتتابع، وDepends(get_super_admin_user) بيعمل DB lookup طازة في
    # *بداية* نفس الطلب، فأي تخفيض للمنفّذ قبل إرسال الطلب بيترفض من
    # الـdependency نفسها (403 عادي) قبل ما يوصل لاستهلاك step-up أو
    # للـservice خالص — مينفعش يثبت مسار ActorAuthorizationChangedError
    # عبر HTTP بدون threads حقيقية. الإثبات الحقيقي للسباق (نافذة زمنية
    # فعلية بين نجاح الـdependency وتنفيذ الـmutation) في
    # tests/test_step_up_concurrency.py على PostgreSQL حي.


# ═════════════ Part F — تدقيق محدود لفشل الإصدار/الاستهلاك ═════════════
# مراجعة Codex المستقلة (2026-07-18، Medium): فشل إصدار الإثبات
# (باسورد/TOTP غلط) ما كانش بيتسجّل في AuditLog خالص، ومحاولات الاستهلاك
# المرفوضة كانت بتتسجّل بلا أي حد أقصى — جلسة موثّقة خبيثة كانت تقدر
# تضخّم AuditLog بتكرار محاولات فاشلة عمدًا (مفيش rate limit على الأربعة
# endpoints المحمية، بعكس POST /auth/step-up نفسها).

class TestStepUpFailureAuditBounded:
    def test_issuance_failure_now_appends_secret_free_audit_row(self, client: TestClient, db):
        sa_id, sa_headers, sa_secret = _fresh_super_admin("audit-issue-fail")
        resp = client.post(
            "/api/v1/auth/step-up",
            json={
                "current_password": "definitely-wrong-password", "purpose": "user_role_update",
                "intent": {"user_id": sa_id, "role": "manager", "is_active": None, "reason": "سبب"},
                "totp_code": pyotp.TOTP(sa_secret).now(),
            },
            headers=sa_headers,
        )
        assert resp.status_code == 403

        from app.modules.core.models import AuditLog
        log = (
            db.query(AuditLog)
            .filter(AuditLog.user_id == sa_id, AuditLog.action == "step_up_issuance_rejected")
            .order_by(AuditLog.id.desc()).first()
        )
        assert log is not None
        import json as _json
        details = _json.loads(log.new_data)
        assert details["purpose"] == "user_role_update"
        assert details["reason_code"] == "CURRENT_PASSWORD_REQUIRED"
        # مفيش أي سر في الصف خالص
        assert "definitely-wrong-password" not in log.new_data
        assert "Test@12345" not in log.new_data

    def test_repeated_invalid_consumption_attempts_are_bounded_not_unlimited(self, client: TestClient, db):
        """جلسة موثّقة (super_admin) بتكرر محاولة استهلاك بتوكن وهمي —
        الطلب نفسه لازم يفضل يترفض 403 STEP_UP_INVALID في كل مرة (الرفض
        الفعلي مايتأثرش)، لكن عدد صفوف step_up_rejected في AuditLog لازم
        يفضل محدود، مش بيكبر بلا نهاية مع كل محاولة."""
        sa_id, sa_headers, _secret = _fresh_super_admin("audit-consume-bound")
        target_id = _create_test_user(f"target-{uuid.uuid4().hex[:6]}@test.local", "waiter")

        for _ in range(30):
            resp = client.patch(
                f"/api/v1/users/{target_id}/role",
                json={"role": "manager", "reason": "محاولة استهلاك بتوكن وهمي متكررة"},
                headers={**sa_headers, "X-Step-Up-Token": "not-a-real-token"},
            )
            assert resp.status_code == 403
            assert resp.json()["detail"]["error_code"] == "STEP_UP_INVALID"

        from app.modules.core.models import AuditLog
        rejected_count = (
            db.query(AuditLog)
            .filter(AuditLog.user_id == sa_id, AuditLog.action == "step_up_rejected")
            .count()
        )
        assert rejected_count < 30, (
            f"AuditLog لازم يكون محدود مش نسخة واحدة لكل محاولة رفض — rejected_count={rejected_count}"
        )
