"""Regression tests for Gate 2B1 credential and session lifecycle safety.

These tests cover concrete production defects found during the read-only
authentication audit: the broken change-password contract, privileged-role
password bypass, incomplete logout/session revocation, stale refresh-token
acceptance, and reusable/plaintext password-reset tokens.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.deps import revoke_user_tokens
from app.core.kernel.auth.service import AuthService
from app.core.kernel.models.user import RefreshToken, TokenBlacklist, User
from app.core.kernel.security import get_password_hash, verify_password
from tests.conftest import TestingSessionLocal, _make_token


CURRENT_PASSWORD = "Current@12345"
NEW_PASSWORD = "Changed@12345"


def _create_user(*, role: str = "cashier", is_active: bool = True) -> tuple[int, str]:
    email = f"gate2b-{role}-{uuid.uuid4().hex}@test.local"
    db = TestingSessionLocal()
    try:
        user = User(
            email=email,
            password_hash=get_password_hash(CURRENT_PASSWORD),
            full_name="Gate 2B Session Test",
            role=role,
            is_active=is_active,
            two_factor_enabled=role in {"super_admin", "accountant"},
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id, email
    finally:
        db.close()


def _auth_headers(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_make_token(email)}"}


def _service(db=None) -> AuthService:
    return AuthService(db or TestingSessionLocal(), User, settings)


class TestChangePasswordContractAndVerification:
    @pytest.mark.parametrize("role", ["cashier", "admin", "super_admin"])
    def test_every_role_must_supply_the_correct_current_password(
        self, client: TestClient, setup_db, role: str,
    ):
        user_id, email = _create_user(role=role)

        response = client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "Wrong@12345", "new_password": NEW_PASSWORD},
            headers=_auth_headers(email),
        )

        assert response.status_code == 400, response.text
        db = TestingSessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).one()
            assert verify_password(CURRENT_PASSWORD, user.password_hash)
            assert not verify_password(NEW_PASSWORD, user.password_hash)
        finally:
            db.close()

    def test_frontend_current_password_contract_works(self, client: TestClient, setup_db):
        user_id, email = _create_user()

        response = client.post(
            "/api/v1/auth/change-password",
            json={"current_password": CURRENT_PASSWORD, "new_password": NEW_PASSWORD},
            headers=_auth_headers(email),
        )

        assert response.status_code == 200, response.text
        db = TestingSessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).one()
            assert verify_password(NEW_PASSWORD, user.password_hash)
        finally:
            db.close()

    def test_legacy_old_password_field_remains_compatible(self, client: TestClient, setup_db):
        _user_id, email = _create_user()

        response = client.post(
            "/api/v1/auth/change-password",
            json={"old_password": CURRENT_PASSWORD, "new_password": NEW_PASSWORD},
            headers=_auth_headers(email),
        )

        assert response.status_code == 200, response.text

    def test_conflicting_current_and_legacy_password_fields_are_rejected(
        self, client: TestClient, setup_db,
    ):
        _user_id, email = _create_user()

        response = client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": CURRENT_PASSWORD,
                "old_password": "Different@12345",
                "new_password": NEW_PASSWORD,
            },
            headers=_auth_headers(email),
        )

        assert response.status_code == 422, response.text


class TestCredentialChangesRevokeSessions:
    def test_change_password_revokes_access_and_every_refresh_token(
        self, app, setup_db,
    ):
        user_id, email = _create_user()
        access_token = _make_token(email)
        db = TestingSessionLocal()
        try:
            auth = _service(db)
            refresh_one = auth.create_refresh_token(user_id)
            refresh_two = auth.create_refresh_token(user_id)
        finally:
            db.close()

        with TestClient(app) as isolated_client:
            response = isolated_client.post(
                "/api/v1/auth/change-password",
                json={"current_password": CURRENT_PASSWORD, "new_password": NEW_PASSWORD},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert response.status_code == 200, response.text

            assert isolated_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {access_token}"},
            ).status_code == 401
            isolated_client.cookies.clear()
            assert isolated_client.post(
                "/api/v1/auth/refresh", json={"refresh_token": refresh_one},
            ).status_code == 401
            assert isolated_client.post(
                "/api/v1/auth/refresh", json={"refresh_token": refresh_two},
            ).status_code == 401

        db = TestingSessionLocal()
        try:
            assert db.query(RefreshToken).filter(RefreshToken.user_id == user_id).count() == 0
        finally:
            db.close()

    def test_immediate_login_after_password_change_is_not_rejected_by_cutoff_precision(
        self, app, setup_db,
    ):
        """A fresh token issued later in the same wall-clock second must pass.

        The old JWT helper stored integer-second ``iat`` while the revocation
        cache stored a float. That could make a genuinely new token look older
        than the cutoff until the next second tick.
        """
        _user_id, email = _create_user()
        db = TestingSessionLocal()
        try:
            auth = _service(db)
            user = auth.repo.get_by_email(email)
            auth.change_password(user, CURRENT_PASSWORD, NEW_PASSWORD)
            new_access = auth.login(email, NEW_PASSWORD)["access_token"]
        finally:
            db.close()

        with TestClient(app) as isolated_client:
            response = isolated_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {new_access}"},
            )
        assert response.status_code == 200, response.text

    def test_role_change_revokes_every_refresh_token(self, client: TestClient, setup_db):
        target_id, _target_email = _create_user(role="manager")
        _actor_id, actor_email = _create_user(role="super_admin")
        db = TestingSessionLocal()
        try:
            refresh_token = _service(db).create_refresh_token(target_id)
        finally:
            db.close()

        response = client.patch(
            f"/api/v1/users/{target_id}/role",
            json={"role": "supervisor"},
            headers=_auth_headers(actor_email),
        )
        assert response.status_code == 200, response.text

        db = TestingSessionLocal()
        try:
            assert db.query(RefreshToken).filter(
                RefreshToken.user_id == target_id,
            ).count() == 0
        finally:
            db.close()

        # Body fallback is intentionally retained for old non-browser clients.
        client.cookies.clear()
        assert client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh_token},
        ).status_code == 401

    def test_password_reset_revokes_access_and_every_refresh_token(self, app, setup_db):
        user_id, email = _create_user()
        access_token = _make_token(email)
        db = TestingSessionLocal()
        try:
            auth = _service(db)
            refresh_token = auth.create_refresh_token(user_id)
            reset_token = auth.create_password_reset_token(email)
            assert reset_token
            auth.confirm_password_reset(reset_token, NEW_PASSWORD)
        finally:
            db.close()

        with TestClient(app) as isolated_client:
            assert isolated_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {access_token}"},
            ).status_code == 401
            isolated_client.cookies.clear()
            assert isolated_client.post(
                "/api/v1/auth/refresh", json={"refresh_token": refresh_token},
            ).status_code == 401

        db = TestingSessionLocal()
        try:
            assert db.query(RefreshToken).filter(RefreshToken.user_id == user_id).count() == 0
        finally:
            db.close()


class TestRefreshTokenSafety:
    def test_rotation_replaces_the_token_and_old_token_cannot_be_replayed(
        self, app, setup_db,
    ):
        user_id, _email = _create_user()
        db = TestingSessionLocal()
        try:
            old_token = _service(db).create_refresh_token(user_id)
        finally:
            db.close()

        with TestClient(app) as isolated_client:
            isolated_client.cookies.clear()
            response = isolated_client.post(
                "/api/v1/auth/refresh", json={"refresh_token": old_token},
            )
            assert response.status_code == 200, response.text
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["pragma"] == "no-cache"
            replacement = isolated_client.cookies.get("refresh_token")
            assert replacement and replacement != old_token

            isolated_client.cookies.clear()
            assert isolated_client.post(
                "/api/v1/auth/refresh", json={"refresh_token": old_token},
            ).status_code == 401
            assert isolated_client.post(
                "/api/v1/auth/refresh", json={"refresh_token": replacement},
            ).status_code == 200

    def test_inactive_user_cannot_rotate_refresh_token(self, app, setup_db):
        user_id, _email = _create_user()
        db = TestingSessionLocal()
        try:
            refresh_token = _service(db).create_refresh_token(user_id)
            user = db.query(User).filter(User.id == user_id).one()
            user.is_active = False
            db.commit()
        finally:
            db.close()

        with TestClient(app) as isolated_client:
            isolated_client.cookies.clear()
            response = isolated_client.post(
                "/api/v1/auth/refresh", json={"refresh_token": refresh_token},
            )
        assert response.status_code == 401, response.text

    def test_soft_deleted_user_cannot_rotate_refresh_token(self, app, setup_db):
        """Preserve the pre-Gate-2B soft-delete rejection invariant."""
        user_id, _email = _create_user()
        db = TestingSessionLocal()
        try:
            refresh_token = _service(db).create_refresh_token(user_id)
            user = db.query(User).filter(User.id == user_id).one()
            user.deleted_at = datetime.now(timezone.utc)
            db.commit()
        finally:
            db.close()

        with TestClient(app) as isolated_client:
            isolated_client.cookies.clear()
            response = isolated_client.post(
                "/api/v1/auth/refresh", json={"refresh_token": refresh_token},
            )
        assert response.status_code == 401, response.text

    def test_legacy_refresh_token_issued_before_revocation_cutoff_is_rejected(
        self, app, setup_db,
    ):
        user_id, _email = _create_user()
        db = TestingSessionLocal()
        try:
            refresh_token = _service(db).create_refresh_token(user_id)
        finally:
            db.close()
        # Simulate a pre-Gate-2B role/status change: the access-token cutoff
        # exists, but an old refresh row was not deleted by the legacy code.
        revoke_user_tokens(user_id)

        with TestClient(app) as isolated_client:
            isolated_client.cookies.clear()
            response = isolated_client.post(
                "/api/v1/auth/refresh", json={"refresh_token": refresh_token},
            )
        assert response.status_code == 401, response.text

    def test_logout_revokes_header_access_token_and_cookie_refresh_token(
        self, app, setup_db,
    ):
        user_id, email = _create_user()
        access_token = _make_token(email)
        db = TestingSessionLocal()
        try:
            refresh_token = _service(db).create_refresh_token(user_id)
        finally:
            db.close()

        with TestClient(app) as isolated_client:
            isolated_client.cookies.set(
                "refresh_token", refresh_token, path="/api/v1/auth",
            )
            response = isolated_client.post(
                "/api/v1/auth/logout",
                json={},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert response.status_code == 200, response.text
            assert isolated_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {access_token}"},
            ).status_code == 401
            isolated_client.cookies.clear()
            assert isolated_client.post(
                "/api/v1/auth/refresh", json={"refresh_token": refresh_token},
            ).status_code == 401


class TestPasswordResetTokenSafety:
    def test_reset_token_is_hashed_at_rest_and_only_latest_link_is_valid(
        self, setup_db,
    ):
        user_id, email = _create_user()
        db = TestingSessionLocal()
        try:
            auth = _service(db)
            first = auth.create_password_reset_token(email)
            second = auth.create_password_reset_token(email)
            assert first and second and first != second

            stored = [
                value for (value,) in db.query(TokenBlacklist.token_hash)
                .filter(TokenBlacklist.user_id == user_id)
                .filter(TokenBlacklist.token_hash.like("reset_%"))
                .all()
            ]
            assert len(stored) == 1
            assert first not in stored[0]
            assert second not in stored[0]

            with pytest.raises(Exception) as exc:
                auth.confirm_password_reset(first, NEW_PASSWORD)
            assert exc.value.status_code == 400

            assert auth.confirm_password_reset(second, NEW_PASSWORD) is True
            assert db.query(TokenBlacklist).filter(
                TokenBlacklist.user_id == user_id,
                TokenBlacklist.token_hash.like("reset_%"),
            ).count() == 0
        finally:
            db.close()

    def test_account_scoped_reset_limit_is_generic_and_prevents_email_bombing(
        self, setup_db,
    ):
        _user_id, email = _create_user()
        db = TestingSessionLocal()
        try:
            auth = _service(db)
            issued = [
                auth.create_password_reset_token(email)
                for _ in range(settings.PASSWORD_RESET_ACCOUNT_RATE_LIMIT_MAX)
            ]
            assert all(issued)
            # The service returns None just like an unknown email; the public
            # endpoint therefore keeps its generic anti-enumeration response.
            assert auth.create_password_reset_token(email) is None
        finally:
            db.close()


class TestAuthRateLimitWiring:
    def test_sensitive_auth_routes_are_rate_limited(self):
        from app.core.rate_limit import _LIMITED_ROUTES

        for path in (
            "/api/v1/auth/refresh",
            "/api/v1/auth/password-reset/request",
            "/api/v1/auth/password-reset/confirm",
            "/api/v1/auth/change-password",
        ):
            assert ("POST", path) in _LIMITED_ROUTES
