"""Gate 2B2 regression tests for secure privileged onboarding and TOTP recovery."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.kernel.auth.service import AuthService
from app.core.kernel.models.user import TwoFactorRecoveryCode, User
from app.core.kernel.security import get_password_hash, validate_password_strength, verify_password
from app.modules.core.models import AuditLog
from tests.conftest import TestingSessionLocal, _make_token


def _service(db=None) -> AuthService:
    return AuthService(db or TestingSessionLocal(), User, settings)


def _create_user(*, role: str = "manager", enabled: bool = False) -> tuple[int, str, str]:
    email = f"gate2b2-{role}-{uuid.uuid4().hex}@test.local"
    password = "Current@12345"
    db = TestingSessionLocal()
    try:
        user = User(
            email=email,
            password_hash=get_password_hash(password),
            full_name="Gate 2B2 Test Operator",
            role=role,
            is_active=True,
            two_factor_enabled=enabled,
            two_factor_secret=pyotp.random_base32() if enabled else None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id, email, password
    finally:
        db.close()


class TestPrivilegedBootstrap:
    def test_create_issues_random_secrets_once_and_persists_only_hashes(self, setup_db):
        email = f"named-admin-{uuid.uuid4().hex}@test.local"
        db = TestingSessionLocal()
        try:
            result = _service(db).provision_account_bootstrap(
                email=email,
                full_name="Named Resort Operator",
                create=True,
            )
        finally:
            db.close()

        valid, _message = validate_password_strength(result["temporary_password"])
        assert valid
        assert len(result["enrollment_token"]) >= 40

        db = TestingSessionLocal()
        try:
            user = db.query(User).filter(User.email == email).one()
            assert user.role == "super_admin"
            assert user.must_change_password is True
            assert user.two_factor_bootstrap_required is True
            assert user.two_factor_enabled is False
            assert verify_password(result["temporary_password"], user.password_hash)
            assert user.two_factor_enrollment_token_hash == hashlib.sha256(
                result["enrollment_token"].encode(),
            ).hexdigest()
            assert result["enrollment_token"] not in user.two_factor_enrollment_token_hash

            audit = db.query(AuditLog).filter(
                AuditLog.entity_id == user.id,
                AuditLog.action == "super_admin_bootstrap_created",
            ).one()
            assert result["temporary_password"] not in (audit.new_data or "")
            assert result["enrollment_token"] not in (audit.new_data or "")
        finally:
            db.close()

    def test_recovery_preserves_a_lower_role_instead_of_escalating_it(self, setup_db):
        user_id, email, _password = _create_user(role="manager")
        db = TestingSessionLocal()
        try:
            result = _service(db).provision_account_bootstrap(
                email=email,
                full_name=None,
                create=False,
            )
            user = db.query(User).filter(User.id == user_id).one()
            assert user.role == "manager"
            assert user.must_change_password is True
            assert result["email"] == email
        finally:
            db.close()

    def test_bootstrap_login_requires_independent_token_and_gets_no_refresh_cookie(
        self,
        client: TestClient,
        setup_db,
        monkeypatch,
    ):
        email = f"bootstrap-login-{uuid.uuid4().hex}@test.local"
        db = TestingSessionLocal()
        try:
            issued = _service(db).provision_account_bootstrap(
                email=email,
                full_name="Bootstrap Login Operator",
                create=True,
            )
        finally:
            db.close()
        monkeypatch.setattr(settings, "LOGIN_2FA_ENFORCED", True)
        client.cookies.clear()

        missing = client.post(
            "/api/v1/auth/login",
            data={"username": email, "password": issued["temporary_password"]},
        )
        assert missing.status_code == 401, missing.text
        assert missing.json()["detail"]["code"] == "2FA_ENROLLMENT_TOKEN_REQUIRED"

        accepted = client.post(
            "/api/v1/auth/login",
            data={
                "username": email,
                "password": issued["temporary_password"],
                "enrollment_token": issued["enrollment_token"],
            },
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["access_token"]
        assert client.cookies.get("refresh_token") is None


class TestBootstrapEnrollmentLifecycle:
    def test_password_then_totp_enrollment_returns_one_time_recovery_codes(
        self,
        setup_db,
        monkeypatch,
    ):
        email = f"bootstrap-flow-{uuid.uuid4().hex}@test.local"
        db = TestingSessionLocal()
        try:
            auth = _service(db)
            issued = auth.provision_account_bootstrap(
                email=email,
                full_name="Full Bootstrap Operator",
                create=True,
            )
            user = auth.repo.get_by_email(email)

            with pytest.raises(Exception) as missing_token:
                auth.change_password(user, issued["temporary_password"], "Permanent@12345")
            assert missing_token.value.detail["code"] == "2FA_ENROLLMENT_TOKEN_REQUIRED"

            auth.change_password(
                user,
                issued["temporary_password"],
                "Permanent@12345",
                enrollment_token=issued["enrollment_token"],
            )
            db.refresh(user)
            assert user.must_change_password is False
            assert user.two_factor_bootstrap_required is True

            with pytest.raises(Exception) as post_password_login_without_token:
                auth.login(email, "Permanent@12345")
            assert (
                post_password_login_without_token.value.detail["code"]
                == "2FA_ENROLLMENT_TOKEN_REQUIRED"
            )
            restricted_login = auth.login(
                email,
                "Permanent@12345",
                enrollment_token=issued["enrollment_token"],
            )
            assert restricted_login["_allow_refresh"] is False

            with pytest.raises(Exception) as setup_without_token:
                auth.setup_2fa(user)
            assert setup_without_token.value.detail["code"] == "2FA_ENROLLMENT_TOKEN_REQUIRED"

            setup = auth.setup_2fa(user, enrollment_token=issued["enrollment_token"])
            enabled = auth.enable_2fa(
                user,
                pyotp.TOTP(setup["secret"]).now(),
                enrollment_token=issued["enrollment_token"],
            )
            assert enabled["reauthentication_required"] is True
            assert len(enabled["recovery_codes"]) == 8
            assert len(set(enabled["recovery_codes"])) == 8
            assert all(len(code.replace("-", "")) == 24 for code in enabled["recovery_codes"])

            db.expire_all()
            enrolled = auth.repo.get_by_email(email)
            assert enrolled.two_factor_enabled is True
            assert enrolled.two_factor_bootstrap_required is False
            assert enrolled.two_factor_enrollment_token_hash is None
            stored_hashes = {
                row.code_hash
                for row in db.query(TwoFactorRecoveryCode).filter(
                    TwoFactorRecoveryCode.user_id == enrolled.id,
                )
            }
            assert len(stored_hashes) == 8
            assert not stored_hashes.intersection(enabled["recovery_codes"])

            monkeypatch.setattr(settings, "LOGIN_2FA_ENFORCED", True)
            recovery_code = enabled["recovery_codes"][0]
            first_login = auth.login(
                email,
                "Permanent@12345",
                recovery_code=recovery_code,
            )
            assert first_login["access_token"]
            with pytest.raises(Exception) as replay:
                auth.login(email, "Permanent@12345", recovery_code=recovery_code)
            assert replay.value.detail["code"] == "2FA_CODE_INVALID"
            remaining = db.query(TwoFactorRecoveryCode).filter(
                TwoFactorRecoveryCode.user_id == enrolled.id,
            ).count()
            assert remaining == 7
        finally:
            db.close()

    def test_optional_role_must_reauthenticate_before_setup(self, setup_db):
        _user_id, email, password = _create_user(role="manager")
        db = TestingSessionLocal()
        try:
            auth = _service(db)
            user = auth.repo.get_by_email(email)
            with pytest.raises(Exception) as missing_password:
                auth.setup_2fa(user)
            assert missing_password.value.detail["code"] == "CURRENT_PASSWORD_REQUIRED"

            result = auth.setup_2fa(user, current_password=password)
            assert result["secret"]
        finally:
            db.close()

    def test_legacy_demo_marker_does_not_strand_safe_environment_accounts(
        self,
        setup_db,
        monkeypatch,
    ):
        """A migration marker protects copied data outside development.

        It is not itself a temporary credential in an explicitly safe
        environment, so the local demo super-admin can still bind TOTP using
        its current password and receive a normal refresh token afterwards.
        """
        _user_id, email, password = _create_user(role="super_admin")
        db = TestingSessionLocal()
        try:
            monkeypatch.setattr(settings, "ENVIRONMENT", "test")
            monkeypatch.setattr(settings, "LOGIN_2FA_ENFORCED", False)
            auth = _service(db)
            user = auth.repo.get_by_email(email)
            user.two_factor_bootstrap_required = True
            db.commit()

            setup = auth.setup_2fa(user, current_password=password)
            enabled = auth.enable_2fa(user, pyotp.TOTP(setup["secret"]).now())
            assert enabled["reauthentication_required"] is True

            db.expire_all()
            enrolled = auth.repo.get_by_email(email)
            assert enrolled.two_factor_bootstrap_required is False
            assert auth.login(email, password)["_allow_refresh"] is True
            assert auth.create_refresh_token(enrolled.id)
        finally:
            db.close()

    def test_legacy_demo_marker_remains_fail_closed_outside_safe_environments(
        self,
        setup_db,
        monkeypatch,
    ):
        _user_id, email, password = _create_user(role="manager")
        db = TestingSessionLocal()
        try:
            monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
            auth = _service(db)
            user = auth.repo.get_by_email(email)
            user.two_factor_bootstrap_required = True
            db.commit()

            with pytest.raises(Exception) as blocked:
                auth.setup_2fa(user, current_password=password)
            assert blocked.value.detail["code"] == "2FA_ENROLLMENT_NOT_PROVISIONED"
            assert auth._refresh_allowed_for_user(user) is False
        finally:
            db.close()

    def test_expired_enrollment_token_is_fail_closed(self, setup_db):
        _user_id, email, _password = _create_user(role="super_admin")
        db = TestingSessionLocal()
        try:
            user = db.query(User).filter(User.email == email).one()
            user.two_factor_bootstrap_required = True
            user.must_change_password = True
            user.two_factor_enrollment_token_hash = hashlib.sha256(b"expired-token").hexdigest()
            user.two_factor_enrollment_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
            with pytest.raises(Exception) as expired:
                _service(db).login(email, "Current@12345", enrollment_token="expired-token")
            assert expired.value.detail["code"] == "2FA_ENROLLMENT_TOKEN_EXPIRED"
        finally:
            db.close()


class TestRecoveryCodeManagement:
    def test_regeneration_requires_password_and_totp_and_replaces_old_codes(self, setup_db):
        user_id, email, password = _create_user(role="manager", enabled=True)
        db = TestingSessionLocal()
        try:
            auth = _service(db)
            user = auth.repo.get_by_email(email)
            old_codes = auth._replace_recovery_codes(user.id)
            db.commit()

            with pytest.raises(Exception):
                auth.regenerate_recovery_codes(
                    user,
                    current_password="Wrong@12345",
                    code=pyotp.TOTP(user.two_factor_secret).now(),
                )

            result = auth.regenerate_recovery_codes(
                user,
                current_password=password,
                code=pyotp.TOTP(user.two_factor_secret).now(),
            )
            assert len(result["recovery_codes"]) == 8
            current_hashes = {
                row.code_hash
                for row in db.query(TwoFactorRecoveryCode).filter(
                    TwoFactorRecoveryCode.user_id == user_id,
                )
            }
            assert all(auth._recovery_code_hash(code) not in current_hashes for code in old_codes)
        finally:
            db.close()


class TestControlPlaneAndSeedGuards:
    def test_mandatory_role_promotion_requires_existing_2fa(self, setup_db):
        from app.modules.core import services

        actor_id, _actor_email, _actor_password = _create_user(
            role="super_admin",
            enabled=True,
        )
        target_id, _target_email, _target_password = _create_user(role="manager")
        db = TestingSessionLocal()
        try:
            with pytest.raises(services.MandatoryTwoFactorEnrollmentRequiredError):
                services.update_user_role(
                    db,
                    target_id,
                    role="accountant",
                    is_active=None,
                    updated_by=actor_id,
                )
        finally:
            db.rollback()
            db.close()

    def test_demo_seed_is_rejected_outside_explicit_safe_environments(
        self,
        setup_db,
        monkeypatch,
    ):
        from app import seed

        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        db = TestingSessionLocal()
        try:
            with pytest.raises(RuntimeError, match="restricted"):
                seed.seed_all(db)
        finally:
            db.close()


class TestHttpOnboardingContract:
    def test_me_exposes_onboarding_state_and_business_routes_are_blocked(
        self,
        client: TestClient,
        setup_db,
    ):
        _user_id, email, _password = _create_user(role="manager")
        db = TestingSessionLocal()
        try:
            user = db.query(User).filter(User.email == email).one()
            user.must_change_password = True
            db.commit()
        finally:
            db.close()
        headers = {"Authorization": f"Bearer {_make_token(email)}"}

        me = client.get("/api/v1/auth/me", headers=headers)
        assert me.status_code == 200, me.text
        assert me.json()["must_change_password"] is True

        blocked = client.get("/api/v1/branches", headers=headers)
        assert blocked.status_code == 403, blocked.text
        assert blocked.json()["detail"]["code"] == "PASSWORD_CHANGE_REQUIRED"
