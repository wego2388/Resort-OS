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


# ── 6b: Gate 2A — AuthService.update_user() can't bypass the super_admin
#        control-plane invariants (Codex review, 2026-07-18) ───────────────

class TestUpdateUserCannotBypassSuperAdminSafeguards:
    """AuthService.update_user() is a generic repo.update() path with none of
    app.modules.core.services.update_user_role()'s Gate 2A protections
    (ordered row locking, self-lockout, last-active-super-admin, full
    AuditLog). No caller currently reaches it, but it must fail closed on
    any role/is_active payload rather than silently demoting/deactivating
    a super_admin if something calls it later.

    Uses one shared session per test (not _svc()'s fresh session) so the
    ORM objects returned by _mk_user() stay attached — TestingSessionLocal
    has the default expire_on_commit=True, so touching an attribute on an
    object returned from a function that already closed its own session
    raises DetachedInstanceError, not the exception under test."""

    def test_role_change_rejected_even_for_super_admin_actor(self, setup_db):
        target_email = f"g2a-bypass-target-{uuid.uuid4().hex}@test.local"
        actor_email = f"g2a-bypass-actor-{uuid.uuid4().hex}@test.local"
        _mk_user(target_email, role="super_admin", is_active=True)
        _mk_user(actor_email, role="super_admin", is_active=True)

        db = TestingSessionLocal()
        try:
            target = db.query(User).filter(User.email == target_email).first()
            actor = db.query(User).filter(User.email == actor_email).first()
            auth = AuthService(db, User, settings)

            with pytest.raises(Exception) as exc:
                auth.update_user(target.id, {"role": "manager"}, actor)
            assert exc.value.status_code == 403
            assert exc.value.detail["error_code"] == "USE_SUPER_ADMIN_CONTROL_PLANE"

            db.expire_all()
            reloaded = db.query(User).filter(User.email == target_email).first()
            assert reloaded.role == "super_admin"
        finally:
            db.close()

    def test_deactivation_rejected_even_for_super_admin_actor(self, setup_db):
        target_email = f"g2a-bypass-target2-{uuid.uuid4().hex}@test.local"
        actor_email = f"g2a-bypass-actor2-{uuid.uuid4().hex}@test.local"
        _mk_user(target_email, role="super_admin", is_active=True)
        _mk_user(actor_email, role="super_admin", is_active=True)

        db = TestingSessionLocal()
        try:
            target = db.query(User).filter(User.email == target_email).first()
            actor = db.query(User).filter(User.email == actor_email).first()
            auth = AuthService(db, User, settings)

            with pytest.raises(Exception) as exc:
                auth.update_user(target.id, {"is_active": False}, actor)
            assert exc.value.status_code == 403
            assert exc.value.detail["error_code"] == "USE_SUPER_ADMIN_CONTROL_PLANE"

            db.expire_all()
            reloaded = db.query(User).filter(User.email == target_email).first()
            assert reloaded.is_active is True
        finally:
            db.close()

    def test_non_privilege_fields_still_update_normally(self, setup_db):
        """Regression guard: the fail-closed check must be scoped to role/
        is_active only — ordinary profile fields (and password hashing)
        still have to work through this path."""
        target_email = f"g2a-bypass-normal-{uuid.uuid4().hex}@test.local"
        actor_email = f"g2a-bypass-actor3-{uuid.uuid4().hex}@test.local"
        _mk_user(target_email, role="cashier", is_active=True)
        _mk_user(actor_email, role="super_admin", is_active=True)

        db = TestingSessionLocal()
        try:
            target = db.query(User).filter(User.email == target_email).first()
            actor = db.query(User).filter(User.email == actor_email).first()
            auth = AuthService(db, User, settings)

            updated = auth.update_user(target.id, {"full_name": "New Name"}, actor)
            assert updated.full_name == "New Name"
        finally:
            db.close()


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


# ── 7b: Gate 1 containment kill switches rejected in production (جولة
#        مراجعة Codex الثالثة) — نفس نمط TestSecretKeyValidation بالظبط ────

_STRONG_SECRET = "Zk9x2Lm7Qw4Tv8Yb1Rn6Pj3Fh5Gd0Sc8Ae2Wu4Io7Kp1Nq9Mz"


class TestContainmentSwitchValidation:
    def test_dining_self_order_enabled_rejected_in_production(self):
        from pydantic import ValidationError
        from app.core.config import Settings
        with pytest.raises(ValidationError, match="DINING_SELF_ORDER_ENABLED"):
            Settings(
                ENVIRONMENT="production", SECRET_KEY=_STRONG_SECRET,
                DATABASE_URL="sqlite://", DINING_SELF_ORDER_ENABLED=True,
            )

    def test_guest_alerts_enabled_rejected_in_production(self):
        from pydantic import ValidationError
        from app.core.config import Settings
        with pytest.raises(ValidationError, match="GUEST_ALERTS_ENABLED"):
            Settings(
                ENVIRONMENT="production", SECRET_KEY=_STRONG_SECRET,
                DATABASE_URL="sqlite://", GUEST_ALERTS_ENABLED=True,
            )

    def test_dining_self_order_enabled_rejected_with_capitalized_production(self):
        """تصحيح (جولة مراجعة Codex الرابعة): fail-closed حقيقي — 'Production'
        بحرف كبير كان بيعدّي من غير فحص مع المطابقة الحرفية القديمة
        (ENVIRONMENT == "production"). دلوقتي allow-list صريح بعد
        strip().lower()، فأي شكل تاني لـ"production" بيترفض برضو."""
        from pydantic import ValidationError
        from app.core.config import Settings
        with pytest.raises(ValidationError, match="DINING_SELF_ORDER_ENABLED"):
            Settings(
                ENVIRONMENT="Production", SECRET_KEY=_STRONG_SECRET,
                DATABASE_URL="sqlite://", DINING_SELF_ORDER_ENABLED=True,
            )

    def test_guest_alerts_enabled_rejected_in_staging(self):
        from pydantic import ValidationError
        from app.core.config import Settings
        with pytest.raises(ValidationError, match="GUEST_ALERTS_ENABLED"):
            Settings(
                ENVIRONMENT="staging", SECRET_KEY=_STRONG_SECRET,
                DATABASE_URL="sqlite://", GUEST_ALERTS_ENABLED=True,
            )

    def test_dining_self_order_enabled_rejected_in_unknown_environment(self):
        """fail-closed: قيمة ENVIRONMENT غير معروفة خالص (typo، بيئة جديدة
        محدش عرّفها هنا) لازم تترفض برضو — مش تعدّي بالصدفة لأنها مش
        "production" حرفيًا."""
        from pydantic import ValidationError
        from app.core.config import Settings
        with pytest.raises(ValidationError, match="DINING_SELF_ORDER_ENABLED"):
            Settings(
                ENVIRONMENT="some-typo-env", SECRET_KEY=_STRONG_SECRET,
                DATABASE_URL="sqlite://", DINING_SELF_ORDER_ENABLED=True,
            )

    def test_both_switches_default_false_and_accepted_in_production(self):
        from app.core.config import Settings
        s = Settings(
            ENVIRONMENT="production", SECRET_KEY=_STRONG_SECRET,
            DATABASE_URL="sqlite://",
        )
        assert s.DINING_SELF_ORDER_ENABLED is False
        assert s.GUEST_ALERTS_ENABLED is False

    def test_switches_enabled_accepted_outside_production(self):
        """development مسموح فيه تفعّل الاثنين عمدًا لتجربة المسار —
        allow-list صريح."""
        from app.core.config import Settings
        s = Settings(
            ENVIRONMENT="development", SECRET_KEY=_STRONG_SECRET,
            DATABASE_URL="sqlite://", DINING_SELF_ORDER_ENABLED=True,
            GUEST_ALERTS_ENABLED=True,
        )
        assert s.DINING_SELF_ORDER_ENABLED is True
        assert s.GUEST_ALERTS_ENABLED is True

    def test_switches_enabled_accepted_with_mixed_case_and_whitespace_test_env(self):
        """strip().lower() بيطبّع " Test "/"TESTING" وغيرها لنفس القيمة
        الآمنة — الـallow-list بيتطابق بالمعنى مش بالحروف الحرفية."""
        from app.core.config import Settings
        s = Settings(
            ENVIRONMENT=" Test ", SECRET_KEY=_STRONG_SECRET,
            DATABASE_URL="sqlite://", DINING_SELF_ORDER_ENABLED=True,
        )
        assert s.DINING_SELF_ORDER_ENABLED is True


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
        ضيف وهمية عبر QR كان ممكن يحصل بدون أي حد أقصى خالص.

        باج تاني اتصلح (Gate 1 containment، 2026-07-17): بعد حذف restaurant/
        cafe نهائيًا (dining cutover، 2026-07-13) فضلت المسارات القديمة دي
        مسجّلة هنا كخريطة ميتة، بينما مسارات dining/public/* الجديدة (اللي
        حلّت محلهم فعليًا) عمرها ما اتسجّلت — يعني /dining/public/orders كان
        بدون أي حد أقصى فعلي من يوم الـcutover لحد الإصلاح ده."""
        from app.core.rate_limit import _LIMITED_ROUTES
        assert ("GET", "/api/v1/dining/public/outlets") in _LIMITED_ROUTES
        assert ("GET", "/api/v1/dining/public/menu") in _LIMITED_ROUTES
        assert ("POST", "/api/v1/dining/public/orders") in _LIMITED_ROUTES
        # المسارات القديمة المحذوفة ماينفعش تفضل في الخريطة — dead entries.
        assert ("GET", "/api/v1/restaurant/public/menu") not in _LIMITED_ROUTES
        assert ("POST", "/api/v1/restaurant/public/orders") not in _LIMITED_ROUTES
        assert ("GET", "/api/v1/cafe/public/menu") not in _LIMITED_ROUTES
        assert ("POST", "/api/v1/cafe/public/orders") not in _LIMITED_ROUTES

    def test_dining_public_outlets_actually_returns_429(self, client, db):
        """اختبار وظيفي حقيقي (مش بس فحص وجود المسار في dictionary) — يثبت
        إن الطلب الحادي والثلاثين خلال 60 ثانية بيرجع 429 فعليًا، مش بس إن
        الإعداد مسجّل. الحد المسجّل لـ dining/public/outlets هو 30/60s.
        branch_id عشوائي كافٍ (list_outlets بترجع [] لو مش موجود، 200
        برضو) — الهدف هنا الحد نفسه مش محتوى الاستجابة."""
        statuses = [
            client.get("/api/v1/dining/public/outlets", params={"branch_id": 999999}).status_code
            for _ in range(31)
        ]
        assert statuses[:30] == [200] * 30, statuses
        assert statuses[30] == 429, statuses


# ── 8b: rate-limit identity resists X-Forwarded-For spoofing (Codex security
#        review، 2026-07-17) ────────────────────────────────────────────────

class TestClientIPProxySpoofResistance:
    """_client_ip الوحدة نفسها — راجع app.core.rate_limit._client_ip's
    docstring للتفاصيل الكاملة عن الباج والإصلاح."""

    @staticmethod
    def _make_request(headers: dict[str, str] | None = None, client_host: str = "203.0.113.9"):
        from starlette.requests import Request
        scope = {
            "type": "http",
            "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
            "client": (client_host, 54321),
        }
        return Request(scope)

    def test_zero_trusted_hops_ignores_forwarded_header_entirely(self):
        """الإعداد الافتراضي (0) — X-Forwarded-For بيتجاهل كليًا، حتى لو
        العميل بعت واحد، ومهما كانت قيمته."""
        from app.core.config import settings
        from app.core.rate_limit import _client_ip
        settings.RATE_LIMIT_TRUSTED_PROXY_HOPS = 0
        req = self._make_request({"x-forwarded-for": "9.9.9.9"}, client_host="203.0.113.9")
        assert _client_ip(req) == "203.0.113.9"

    def test_two_trusted_hops_selects_second_from_right_regardless_of_spoofed_prefix(self):
        """مع 2 hops موثوقين، القيمة المُختارة هي التانية من اليمين
        (اللي edge nginx فعليًا شافها كـpeer له) — مش أول قيمة (اللي
        العميل بيتحكم فيها بالكامل). تدوير قيمة الشمال المزوّرة عبر
        محاولات مختلفة **ملهوش أي تأثير** على الاختيار."""
        from app.core.config import settings
        from app.core.rate_limit import _client_ip
        settings.RATE_LIMIT_TRUSTED_PROXY_HOPS = 2
        real_client, edge_nginx_ip = "198.51.100.7", "172.18.0.3"
        for spoofed_prefix in ("9.9.9.9", "1.1.1.1", "not-even-an-ip", "127.0.0.1"):
            req = self._make_request({
                "x-forwarded-for": f"{spoofed_prefix}, {real_client}, {edge_nginx_ip}",
            })
            assert _client_ip(req) == real_client, spoofed_prefix

    def test_too_short_chain_falls_back_to_direct_peer(self):
        """مع 2 hops موثوقين، سلسلة بقيمة واحدة بس (أقصر من المتوقع —
        proxy وسيط فشل يضيف قيمته، أو تلاعب) لازم fail-closed لـ
        request.client.host، مش قبول القيمة الوحيدة الموجودة كأنها موثوقة."""
        from app.core.config import settings
        from app.core.rate_limit import _client_ip
        settings.RATE_LIMIT_TRUSTED_PROXY_HOPS = 2
        req = self._make_request({"x-forwarded-for": "9.9.9.9"}, client_host="203.0.113.9")
        assert _client_ip(req) == "203.0.113.9"

    def test_missing_header_falls_back_to_direct_peer(self):
        from app.core.config import settings
        from app.core.rate_limit import _client_ip
        settings.RATE_LIMIT_TRUSTED_PROXY_HOPS = 2
        req = self._make_request(client_host="203.0.113.9")
        assert _client_ip(req) == "203.0.113.9"

    def test_malformed_ip_in_trusted_position_falls_back_to_direct_peer(self):
        """القيمة في المكان المتوقع (2nd-from-right) نفسها مش IP صالح —
        fail-closed، مش قبولها كأنها عنوان حقيقي."""
        from app.core.config import settings
        from app.core.rate_limit import _client_ip
        settings.RATE_LIMIT_TRUSTED_PROXY_HOPS = 2
        req = self._make_request(
            {"x-forwarded-for": "9.9.9.9, not-an-ip-at-all, 172.18.0.3"},
            client_host="203.0.113.9",
        )
        assert _client_ip(req) == "203.0.113.9"

    def test_direct_request_cannot_change_rate_limit_identity_via_header(self, client, db):
        """اختبار وظيفي حقيقي عبر HTTP — hops=0 (الافتراضي)، كل طلب من الـ31
        ببعت X-Forwarded-For مختلف تمامًا. لو الهيدر كان بيتقبل، كل طلب
        كان هيتحسب كـ"IP" مختلف فيتهرّب من الحد تمامًا. بما إن كل الـ31
        فعليًا نفس الـTestClient (نفس request.client.host الحقيقي)، لازم
        الطلب رقم 31 يرجع 429 برضو — يعني تزوير الهيدر متغيّرش الهوية."""
        from app.core.config import settings
        settings.RATE_LIMIT_TRUSTED_PROXY_HOPS = 0
        statuses = [
            client.get(
                "/api/v1/dining/public/outlets", params={"branch_id": 999999},
                headers={"X-Forwarded-For": f"10.0.{i}.{i}"},
            ).status_code
            for i in range(31)
        ]
        assert statuses[:30] == [200] * 30, statuses
        assert statuses[30] == 429, statuses

    def test_two_trusted_hops_rotating_spoofed_prefix_still_hits_429(self, client, db):
        """نفس الفكرة، بس hops=2 وXFF بشكل الإنتاج الحقيقي (3 قيم) — قيمة
        الشمال (المزوّرة) بتتغيّر كل طلب، القيمتين التانيتين (الممثّلتين
        لـedge/frontend nginx) ثابتتين. لازم برضو يوصل 429 عند الطلب 31،
        لأن الاختيار الفعلي (2nd-from-right) ثابت رغم التزوير."""
        from app.core.config import settings
        settings.RATE_LIMIT_TRUSTED_PROXY_HOPS = 2
        stable_suffix = "198.51.100.7, 172.18.0.3"
        statuses = [
            client.get(
                "/api/v1/dining/public/outlets", params={"branch_id": 999999},
                headers={"X-Forwarded-For": f"10.0.{i}.{i}, {stable_suffix}"},
            ).status_code
            for i in range(31)
        ]
        assert statuses[:30] == [200] * 30, statuses
        assert statuses[30] == 429, statuses
