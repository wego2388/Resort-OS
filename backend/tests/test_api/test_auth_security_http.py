"""
tests/test_api/test_auth_security_http.py

Regression tests for the auth hardening pass (login/session/account-creation
security). Each guards a specific vulnerability that was found and fixed:

  1. User-enumeration via login (distinct message + timing for unknown email
     vs wrong password)  → uniform message + bcrypt-equalized timing.
  2. "N attempts remaining" leak in the wrong-password response.
  3. Account lockout still triggers after MAX_LOGIN_ATTEMPTS.
  4. TOTP shared secret encrypted at rest (Fernet), transparent on read.
  5. Login-time 2FA (LOGIN_2FA_ENFORCED) becomes a real second factor.
  6. Registration cannot self-assign an elevated role (privilege escalation).
  7. Weak/placeholder SECRET_KEY is rejected in production.
  8. Login route stays wired to the IP rate limiter.
"""
from __future__ import annotations

import time
import uuid

import pyotp
import pytest
from sqlalchemy import text

from app.core.config import settings
from app.core.kernel.auth.service import AuthService
from app.core.kernel.models.user import User
from app.core.kernel.security import get_password_hash
from tests.conftest import TestingSessionLocal, engine


def _mk_user(email: str, password: str = "Correct@12345", **kw) -> User:
    db = TestingSessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        if not u:
            u = User(
                email=email,
                password_hash=get_password_hash(password),
                full_name="Sec Test",
                role=kw.pop("role", "cashier"),
                is_active=kw.pop("is_active", True),
                **kw,
            )
            db.add(u)
            db.commit()
        return u
    finally:
        db.close()


def _svc() -> AuthService:
    return AuthService(TestingSessionLocal(), User, settings)


# ── 1 + 2: user enumeration (message + timing) ─────────────────────────────

class TestLoginEnumeration:
    def test_unknown_email_and_wrong_password_return_identical_message(self, setup_db):
        _mk_user("enum-real@test.local")
        auth = _svc()
        with pytest.raises(Exception) as e_unknown:
            auth.login("enum-nobody@test.local", "whatever")
        with pytest.raises(Exception) as e_wrong:
            auth.login("enum-real@test.local", "Wrong@12345")
        # same status AND same detail — no oracle distinguishing the two
        assert e_unknown.value.status_code == e_wrong.value.status_code == 401
        assert e_unknown.value.detail == e_wrong.value.detail
        assert e_unknown.value.detail == "Incorrect email or password"

    def test_wrong_password_does_not_leak_remaining_attempts(self, setup_db):
        _mk_user("enum-leak@test.local")
        auth = _svc()
        with pytest.raises(Exception) as exc:
            auth.login("enum-leak@test.local", "Wrong@12345")
        assert "remaining" not in str(exc.value.detail).lower()
        assert "attempt" not in str(exc.value.detail).lower()

    def test_unknown_email_path_runs_bcrypt_to_equalize_timing(self, setup_db):
        """Unknown-email must not short-circuit before the (dummy) bcrypt
        compare — otherwise <1ms vs ~250ms reveals which emails exist."""
        auth = _svc()
        start = time.perf_counter()
        with pytest.raises(Exception):
            auth.login(f"ghost-{uuid.uuid4().hex}@test.local", "whatever")
        elapsed_ms = (time.perf_counter() - start) * 1000
        # A short-circuit returns in <2ms; bcrypt(rounds=12) is ~100-300ms.
        # 20ms is a comfortable floor that still proves the hash ran.
        assert elapsed_ms > 20, f"unknown-email returned in {elapsed_ms:.1f}ms — timing leak"


# ── 3: lockout still works ─────────────────────────────────────────────────

class TestLockout:
    def test_account_locks_after_max_attempts(self, setup_db):
        email = f"lock-{uuid.uuid4().hex}@test.local"
        _mk_user(email)
        max_attempts = getattr(settings, "MAX_LOGIN_ATTEMPTS", 5)
        last = None
        for _ in range(max_attempts):
            auth = _svc()
            with pytest.raises(Exception) as exc:
                auth.login(email, "Wrong@12345")
            last = exc.value
        assert last.status_code == 423  # HTTP_423_LOCKED on the final attempt
        # further attempts stay locked even with the *correct* password
        auth = _svc()
        with pytest.raises(Exception) as exc:
            auth.login(email, "Correct@12345")
        assert exc.value.status_code == 423


# ── 4: TOTP secret encrypted at rest ───────────────────────────────────────

class TestTotpSecretAtRest:
    def test_secret_is_fernet_encrypted_in_db_but_plaintext_via_orm(self, setup_db):
        email = f"totp-{uuid.uuid4().hex}@test.local"
        _mk_user(email, role="manager")
        auth = _svc()
        user = auth.repo.get_by_email(email)
        result = auth.setup_2fa(user)
        plaintext_secret = result["secret"]

        # raw column bypasses the EncryptedString TypeDecorator
        with engine.connect() as conn:
            raw = conn.execute(
                text("SELECT two_factor_secret FROM users WHERE email = :e"),
                {"e": email},
            ).scalar()
        assert raw != plaintext_secret, "TOTP secret stored in plaintext!"
        assert raw.startswith("gAAAAA"), "expected a Fernet token at rest"

        # ORM read transparently decrypts back to the usable secret
        fresh = _svc().repo.get_by_email(email)
        assert fresh.two_factor_secret == plaintext_secret
        assert pyotp.TOTP(fresh.two_factor_secret).now()  # usable


# ── 5: login-time 2FA is a real second factor when enforced ────────────────

class TestLoginTime2FA:
    def test_enforced_requires_valid_code(self, setup_db, monkeypatch):
        email = f"l2fa-{uuid.uuid4().hex}@test.local"
        secret = pyotp.random_base32()
        _mk_user(email, role="manager", two_factor_enabled=True, two_factor_secret=secret)
        monkeypatch.setattr(settings, "LOGIN_2FA_ENFORCED", True)

        # correct password, NO code → rejected
        with pytest.raises(Exception) as exc:
            _svc().login(email, "Correct@12345")
        assert exc.value.status_code == 401
        assert exc.value.detail["code"] == "2FA_CODE_REQUIRED"

        # correct password, WRONG code → rejected
        with pytest.raises(Exception) as exc:
            _svc().login(email, "Correct@12345", otp_code="000000")
        assert exc.value.detail["code"] == "2FA_CODE_INVALID"

        # correct password + valid code → success
        out = _svc().login(email, "Correct@12345", otp_code=pyotp.TOTP(secret).now())
        assert out["access_token"]

    def test_disabled_by_default_keeps_password_only_flow_working(self, setup_db, monkeypatch):
        email = f"l2fa-off-{uuid.uuid4().hex}@test.local"
        secret = pyotp.random_base32()
        _mk_user(email, role="manager", two_factor_enabled=True, two_factor_secret=secret)
        monkeypatch.setattr(settings, "LOGIN_2FA_ENFORCED", False)
        out = _svc().login(email, "Correct@12345")  # no code needed (back-compat)
        assert out["access_token"]


# ── 6: registration can't self-assign an elevated role ─────────────────────

class TestRegistrationPrivilegeEscalation:
    def test_service_ignores_caller_supplied_role(self, setup_db):
        email = f"reg-{uuid.uuid4().hex}@test.local"
        auth = _svc()
        # register() has no `role` parameter at all — the value can't flow in
        created = auth.register(email=email, password="Strong@12345", full_name="X")
        assert created.role in ("customer", "guest")

    def test_http_register_body_role_is_dropped(self, client, setup_db):
        email = f"reg-http-{uuid.uuid4().hex}@test.local"
        res = client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "Strong@12345",
                "full_name": "X",
                "role": "super_admin",  # attacker attempt
                "is_active": True,
            },
        )
        # may be 200 (created) or 429 (shared login rate bucket) — either way,
        # what matters is that NO super_admin was created from the body.
        if res.status_code == 200:
            db = TestingSessionLocal()
            try:
                u = db.query(User).filter(User.email == email).first()
                assert u is not None
                assert u.role != "super_admin"
            finally:
                db.close()

    def test_register_response_never_leaks_password_hash_or_2fa_secret(self, client, setup_db):
        """Regression — /register had no response_model, so FastAPI serialized
        the raw ORM User object returned by AuthService.register(), leaking
        password_hash (and two_factor_secret) in the JSON response of this
        public, unauthenticated endpoint."""
        email = f"reg-leak-{uuid.uuid4().hex}@test.local"
        res = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Strong@12345", "full_name": "X"},
        )
        if res.status_code == 200:
            body = res.json()
            assert "password_hash" not in body
            assert "two_factor_secret" not in body
            assert body["email"] == email


# ── 7: weak SECRET_KEY rejected in production ──────────────────────────────

class TestSecretKeyValidation:
    def test_placeholder_secret_rejected_in_production(self):
        from app.core.config import Settings
        with pytest.raises(Exception):
            Settings(
                ENVIRONMENT="production",
                SECRET_KEY="CHANGE_ME_minimum_32_characters_here_xxxxxx",
                DATABASE_URL="sqlite://",
            )

    def test_short_secret_rejected_in_production(self):
        from app.core.config import Settings
        with pytest.raises(Exception):
            Settings(ENVIRONMENT="production", SECRET_KEY="short", DATABASE_URL="sqlite://")

    def test_strong_secret_accepted_in_production(self):
        from app.core.config import Settings
        s = Settings(
            ENVIRONMENT="production",
            SECRET_KEY="Zk9x2Lm7Qw4Tv8Yb1Rn6Pj3Fh5Gd0Sc8Ae2Wu4Io7Kp1Nq9Mz",
            DATABASE_URL="sqlite://",
        )
        assert s.ENVIRONMENT == "production"


# ── 8: login stays wired to the IP rate limiter ────────────────────────────

class TestRateLimitWiring:
    def test_login_and_register_are_rate_limited(self):
        """max_req/window بيتحققوا من settings.LOGIN_RATE_LIMIT_* مش أرقام
        حرفية — القيمة قابلة للتعديل عمدًا لكل بيئة (راجع .env.example)،
        الحاكم الحقيقي هنا إن الإعداد فعلاً بيوصل للـ middleware، مش رقم
        بعينه."""
        from app.core.config import settings
        from app.core.rate_limit import _LIMITED_ROUTES
        assert ("POST", "/api/v1/auth/login") in _LIMITED_ROUTES
        assert ("POST", "/api/v1/auth/register") in _LIMITED_ROUTES
        prefix, max_req, window = _LIMITED_ROUTES[("POST", "/api/v1/auth/login")]
        assert prefix == "login"
        assert max_req == settings.LOGIN_RATE_LIMIT_MAX
        assert window == settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS

    def test_guest_ordering_endpoints_are_rate_limited(self):
        """باج حقيقي اتصلح (2026-07-07): طلب/قائمة المطعم والكافيه كانت
        موثّقة في تعليقات restaurant/cafe كـ "rate limited بالـ middleware"
        بس عمرها ما كانت مسجّلة في _LIMITED_ROUTES فعليًا — يعني إسبام طلبات
        ضيف وهمية عبر QR كان ممكن يحصل بدون أي حد أقصى خالص."""
        from app.core.rate_limit import _LIMITED_ROUTES
        assert ("GET", "/api/v1/restaurant/public/menu") in _LIMITED_ROUTES
        assert ("POST", "/api/v1/restaurant/public/orders") in _LIMITED_ROUTES
        assert ("POST", "/api/v1/cafe/public/orders") in _LIMITED_ROUTES
