"""
tests/test_api/test_auth_2fa_http.py
اختبارات HTTP حقيقية لمسار الـ 2FA الكامل (setup → enable → disable) عبر
app/core/kernel/auth/router.py — وتحديدًا الباج اللي اتصلح هنا: super_admin/
accountant (MANDATORY_2FA_ROLES في app/core/deps.py) كان يقدر يعطّل الـ 2FA
بتاعه من endpoint /2fa/disable العام من غير أي مانع، رغم إن /2fa/gate بيمنعه
من استخدام أي endpoint تاني لحد ما يفعّله — يعني كان ممكن يفعّل ثم يعطّل فورًا
ويفضل من غير 2FA فعليًا.
"""
from __future__ import annotations

import os

import pyotp
from jose import jwt


def _make_token(email: str) -> str:
    from datetime import datetime, timedelta

    secret = os.environ["SECRET_KEY"]
    now = datetime.utcnow()
    payload = {"sub": email, "iat": now, "exp": now + timedelta(hours=1)}
    return jwt.encode(payload, secret, algorithm="HS256")


def _create_user_with_secret(email: str, role: str, *, enabled: bool):
    """ينشئ مستخدم حقيقي بسر TOTP حقيقي (مش بس is-enabled بدون سر) عشان نقدر
    نولّد كود صحيح فعلي زي أي تطبيق مصادقة حقيقي."""
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    from tests.conftest import TestingSessionLocal

    secret = pyotp.random_base32()
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                email=email, password_hash=get_password_hash("Test@12345"),
                full_name=f"Test {role}", role=role, is_active=True,
                two_factor_enabled=enabled, two_factor_secret=secret,
            )
            db.add(user)
        else:
            user.two_factor_enabled = enabled
            user.two_factor_secret = secret
        db.commit()
        return secret
    finally:
        db.close()


class TestTwoFactorSetupFlow:
    def test_setup_returns_secret_and_provisioning_uri(self, client, setup_db):
        _create_user_with_secret("2fa-setup@test.local", "manager", enabled=False)
        headers = {"Authorization": f"Bearer {_make_token('2fa-setup@test.local')}"}
        res = client.post("/api/v1/auth/2fa/setup", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert "secret" in body and len(body["secret"]) > 0
        assert "provisioning_uri" in body

    def test_enable_with_valid_code_succeeds(self, client, setup_db):
        secret = _create_user_with_secret("2fa-enable@test.local", "manager", enabled=False)
        # setup محتاج يتنفّذ الأول عشان الـ secret يتخزن — لكن هنا زوّدنا الـ
        # secret يدويًا فوق فنقدر نولّد كود صحيح من غيره مباشرة.
        headers = {"Authorization": f"Bearer {_make_token('2fa-enable@test.local')}"}
        code = pyotp.TOTP(secret).now()
        res = client.post("/api/v1/auth/2fa/enable", json={"code": code}, headers=headers)
        assert res.status_code == 200

    def test_enable_with_invalid_code_rejected(self, client, setup_db):
        _create_user_with_secret("2fa-enable-bad@test.local", "manager", enabled=False)
        headers = {"Authorization": f"Bearer {_make_token('2fa-enable-bad@test.local')}"}
        res = client.post("/api/v1/auth/2fa/enable", json={"code": "000000"}, headers=headers)
        assert res.status_code == 400

    def test_operational_role_can_disable_2fa(self, client, setup_db):
        """manager مش في MANDATORY_2FA_ROLES — التعطيل الطوعي المفروض يشتغل عادي."""
        secret = _create_user_with_secret("2fa-disable-mgr@test.local", "manager", enabled=True)
        headers = {"Authorization": f"Bearer {_make_token('2fa-disable-mgr@test.local')}"}
        code = pyotp.TOTP(secret).now()
        res = client.post("/api/v1/auth/2fa/disable", json={"code": code}, headers=headers)
        assert res.status_code == 200

    def test_super_admin_cannot_disable_mandatory_2fa(self, client, setup_db):
        """الباج المُصلَح: super_admin (MANDATORY_2FA_ROLES) لازم ميقدرش يعطّل
        2FA بتاعه حتى بكود صحيح — التعطيل كان بيشتغل عادي قبل الإصلاح."""
        secret = _create_user_with_secret("2fa-disable-sa@test.local", "super_admin", enabled=True)
        headers = {"Authorization": f"Bearer {_make_token('2fa-disable-sa@test.local')}"}
        code = pyotp.TOTP(secret).now()
        res = client.post("/api/v1/auth/2fa/disable", json={"code": code}, headers=headers)
        assert res.status_code == 400

        # تأكيد إضافي: لسه مفعّل فعليًا في الداتابيز بعد المحاولة.
        from app.core.kernel.models.user import User
        from tests.conftest import TestingSessionLocal
        db = TestingSessionLocal()
        try:
            user = db.query(User).filter(User.email == "2fa-disable-sa@test.local").first()
            assert user.two_factor_enabled is True
        finally:
            db.close()

    def test_accountant_cannot_disable_mandatory_2fa(self, client, setup_db):
        secret = _create_user_with_secret("2fa-disable-acc@test.local", "accountant", enabled=True)
        headers = {"Authorization": f"Bearer {_make_token('2fa-disable-acc@test.local')}"}
        code = pyotp.TOTP(secret).now()
        res = client.post("/api/v1/auth/2fa/disable", json={"code": code}, headers=headers)
        assert res.status_code == 400
