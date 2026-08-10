"""tests/test_remember_me.py — "تذكرني على هذا الجهاز" (Task #19's login/TOTP
UX batch). refresh-token expiry أطول لو المستخدم اختارها صراحةً وقت
/auth/login، وبيفضل نفس العمر ده مع كل rotation لاحق (مش يرجع للـdefault
القصير كل refresh)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.kernel.auth.service import AuthService
from app.core.kernel.models.user import RefreshToken, User
from app.core.kernel.security import get_password_hash
from tests.conftest import TestingSessionLocal


PASSWORD = "RememberMe@12345"


def _create_user(*, role: str = "cashier") -> tuple[int, str]:
    email = f"remember-me-{uuid.uuid4().hex}@test.local"
    db = TestingSessionLocal()
    try:
        user = User(
            email=email, password_hash=get_password_hash(PASSWORD),
            full_name="Remember Me Test", role=role, is_active=True,
            two_factor_enabled=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id, email
    finally:
        db.close()


def _service(db=None) -> AuthService:
    return AuthService(db or TestingSessionLocal(), User, settings)


class TestRememberMeServiceLayer:
    def test_default_expiry_unchanged_when_expire_days_omitted(self, setup_db):
        user_id, _ = _create_user()
        auth = _service()
        before = datetime.now(timezone.utc)
        token = auth.create_refresh_token(user_id)
        rt = auth.db.query(RefreshToken).filter_by(token_hash=auth._hash_token(token)).first()
        span_days = (rt.expires_at.replace(tzinfo=timezone.utc) - before).days
        assert span_days == settings.REFRESH_TOKEN_EXPIRE_DAYS

    def test_remember_me_expire_days_produces_longer_token(self, setup_db):
        user_id, _ = _create_user()
        auth = _service()
        before = datetime.now(timezone.utc)
        token = auth.create_refresh_token(user_id, expire_days=settings.REMEMBER_ME_EXPIRE_DAYS)
        rt = auth.db.query(RefreshToken).filter_by(token_hash=auth._hash_token(token)).first()
        span_days = (rt.expires_at.replace(tzinfo=timezone.utc) - before).days
        assert span_days == settings.REMEMBER_ME_EXPIRE_DAYS
        assert settings.REMEMBER_ME_EXPIRE_DAYS > settings.REFRESH_TOKEN_EXPIRE_DAYS

    def test_rotation_preserves_remember_me_span_not_default(self, setup_db):
        """أهم اختبار هنا: العمر الأطول لازم يفضل موجود مع كل refresh
        لاحق، وإلا "تذكرني" هتنتهي فعليًا بعد أول refresh صامت زي أي جلسة
        عادية — بالظبط الباج اللي كان ممكن يحصل لو رجّعنا للـdefault
        الثابت جوه rotate_refresh_token."""
        user_id, _ = _create_user()
        auth = _service()
        long_token = auth.create_refresh_token(user_id, expire_days=settings.REMEMBER_ME_EXPIRE_DAYS)

        before_rotation = datetime.now(timezone.utc)
        result = auth.rotate_refresh_token(long_token)
        assert result is not None
        _user, rotated_token = result

        rt = auth.db.query(RefreshToken).filter_by(token_hash=auth._hash_token(rotated_token)).first()
        span_days = (rt.expires_at.replace(tzinfo=timezone.utc) - before_rotation).days
        assert span_days == settings.REMEMBER_ME_EXPIRE_DAYS

    def test_rotation_of_normal_session_stays_short(self, setup_db):
        user_id, _ = _create_user()
        auth = _service()
        normal_token = auth.create_refresh_token(user_id)

        before_rotation = datetime.now(timezone.utc)
        _user, rotated_token = auth.rotate_refresh_token(normal_token)
        rt = auth.db.query(RefreshToken).filter_by(token_hash=auth._hash_token(rotated_token)).first()
        span_days = (rt.expires_at.replace(tzinfo=timezone.utc) - before_rotation).days
        assert span_days == settings.REFRESH_TOKEN_EXPIRE_DAYS

    def test_get_refresh_token_expiry_matches_persisted_row(self, setup_db):
        user_id, _ = _create_user()
        auth = _service()
        token = auth.create_refresh_token(user_id, expire_days=settings.REMEMBER_ME_EXPIRE_DAYS)
        expiry = auth.get_refresh_token_expiry(token)
        assert expiry is not None
        expected = datetime.now(timezone.utc) + timedelta(days=settings.REMEMBER_ME_EXPIRE_DAYS)
        assert abs((expiry - expected).total_seconds()) < 5

    def test_get_refresh_token_expiry_returns_none_for_unknown_token(self, setup_db):
        auth = _service()
        assert auth.get_refresh_token_expiry("not-a-real-token") is None


class TestRememberMeHttpFlow:
    def test_login_without_remember_me_sets_short_lived_cookie(self, client: TestClient, setup_db):
        _user_id, email = _create_user()
        client.cookies.clear()
        res = client.post("/api/v1/auth/login", data={"username": email, "password": PASSWORD})
        assert res.status_code == 200, res.text
        set_cookie = res.headers.get("set-cookie", "")
        assert f"Max-Age={settings.REFRESH_TOKEN_EXPIRE_DAYS * 86_400}" in set_cookie

    def test_login_with_remember_me_sets_long_lived_cookie(self, client: TestClient, setup_db):
        _user_id, email = _create_user()
        client.cookies.clear()
        res = client.post(
            "/api/v1/auth/login",
            data={"username": email, "password": PASSWORD, "remember_me": "true"},
        )
        assert res.status_code == 200, res.text
        set_cookie = res.headers.get("set-cookie", "")
        assert f"Max-Age={settings.REMEMBER_ME_EXPIRE_DAYS * 86_400}" in set_cookie

    def test_refresh_after_remember_me_login_keeps_long_lived_cookie(self, client: TestClient, setup_db):
        _user_id, email = _create_user()
        client.cookies.clear()
        login_res = client.post(
            "/api/v1/auth/login",
            data={"username": email, "password": PASSWORD, "remember_me": "true"},
        )
        assert login_res.status_code == 200, login_res.text

        refresh_res = client.post("/api/v1/auth/refresh")
        assert refresh_res.status_code == 200, refresh_res.text
        set_cookie = refresh_res.headers.get("set-cookie", "")
        assert f"Max-Age={settings.REMEMBER_ME_EXPIRE_DAYS * 86_400}" in set_cookie
