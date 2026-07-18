"""Gate 2B3B — self-service session management + unified auth audit.

Covers the HTTP surface (list/revoke sessions, security activity) and the
secret-free, bounded audit behavior. Real-concurrency guarantees for replay
detection live in tests/test_refresh_family_concurrency.py (Postgres-only).
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.kernel.auth.service import AuthService
from app.core.kernel.models.user import RefreshToken, User
from app.core.kernel.security import create_access_token, decode_token, get_password_hash
from app.modules.core.models import AuditLog
from tests.conftest import TestingSessionLocal, _make_token


PASSWORD = "Current@12345"


def _create_user(*, role: str = "cashier", is_active: bool = True) -> tuple[int, str]:
    email = f"gate2b3b-{role}-{uuid.uuid4().hex}@test.local"
    db = TestingSessionLocal()
    try:
        user = User(
            email=email,
            password_hash=get_password_hash(PASSWORD),
            full_name="Gate 2B3B Test",
            role=role,
            is_active=is_active,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id, email
    finally:
        db.close()


def _headers(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_make_token(email)}"}


def _service(db=None) -> AuthService:
    return AuthService(db or TestingSessionLocal(), User, settings)


def _new_family(user_id: int) -> str:
    """Create one refresh family for the user and return its raw token."""
    db = TestingSessionLocal()
    try:
        return _service(db).create_refresh_token(user_id)
    finally:
        db.close()


def _audit_rows(user_id: int):
    db = TestingSessionLocal()
    try:
        return (
            db.query(AuditLog)
            .filter(
                AuditLog.user_id == user_id,
                AuditLog.entity_type == "user_authentication",
            )
            .all()
        )
    finally:
        db.close()


def _issue_step_up(client: TestClient, headers: dict, purpose: str, intent: dict) -> str:
    # The step-up grant is bound to the exact bearer token in ``headers`` —
    # the caller MUST reuse that same header dict when consuming, otherwise the
    # session binding (access_token_hash) will not match. (_make_token embeds a
    # second-granularity iat, so a freshly generated token can differ.)
    res = client.post(
        "/api/v1/auth/step-up",
        json={"current_password": PASSWORD, "purpose": purpose, "intent": intent},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return res.json()["step_up_token"]


# ── Unified auth audit ──────────────────────────────────────────────────

class TestUnifiedAuthAudit:
    def test_login_success_writes_secret_free_audit_row(self, setup_db):
        user_id, email = _create_user()
        db = TestingSessionLocal()
        try:
            _service(db).login(email, PASSWORD)
        finally:
            db.close()
        actions = {r.action for r in _audit_rows(user_id)}
        assert "login_succeeded" in actions

    def test_known_account_failure_and_lockout_are_audited(self, setup_db):
        user_id, email = _create_user()
        # Five wrong passwords → lockout on the fifth.
        for _ in range(5):
            db = TestingSessionLocal()
            try:
                with pytest.raises(Exception):
                    _service(db).login(email, "Wrong@99999")
            finally:
                db.close()
        actions = [r.action for r in _audit_rows(user_id)]
        assert "login_failed" in actions
        assert "login_locked_out" in actions

    def test_unknown_account_writes_no_audit_row(self, setup_db):
        unknown = f"nobody-{uuid.uuid4().hex}@test.local"
        db = TestingSessionLocal()
        try:
            with pytest.raises(Exception):
                _service(db).login(unknown, "Whatever@12345")
        finally:
            db.close()
        # No AuditLog row for a non-existent account — the anti-amplification
        # / anti-enumeration decision (structured log only).
        rows = TestingSessionLocal().query(AuditLog).filter(
            AuditLog.entity_type == "user_authentication",
        ).all()
        assert all(unknown not in ((r.new_data or "") + (r.old_data or "")) for r in rows)

    def test_repeated_locked_attempts_are_bounded_not_unbounded(self, setup_db):
        user_id, email = _create_user()
        for _ in range(5):  # trip the lockout
            db = TestingSessionLocal()
            try:
                with pytest.raises(Exception):
                    _service(db).login(email, "Wrong@99999")
            finally:
                db.close()
        # Now hammer the locked account 30 more times.
        for _ in range(30):
            db = TestingSessionLocal()
            try:
                with pytest.raises(Exception):
                    _service(db).login(email, "Wrong@99999")
            finally:
                db.close()
        blocked = [r for r in _audit_rows(user_id) if r.action == "login_blocked_locked"]
        assert len(blocked) < 30, "locked-attempt audit must be bounded, not one row per bot request"

    def test_no_secret_appears_in_any_auth_audit_row(self, setup_db):
        user_id, email = _create_user()
        db = TestingSessionLocal()
        try:
            _service(db).login(email, PASSWORD)
        finally:
            db.close()
        for row in _audit_rows(user_id):
            blob = "".join(str(x or "") for x in (row.old_data, row.new_data, row.ip_address, row.user_agent))
            assert PASSWORD not in blob
            assert email not in blob


# ── Session listing + revocation ────────────────────────────────────────

class TestSessionManagement:
    def test_http_login_and_refresh_bind_access_tokens_to_one_session(
        self, client: TestClient, setup_db,
    ):
        _user_id, email = _create_user()
        login = client.post(
            "/api/v1/auth/login",
            data={"username": email, "password": PASSWORD},
        )
        assert login.status_code == 200, login.text
        first_claims = decode_token(
            login.json()["access_token"], settings.SECRET_KEY, settings.ALGORITHM,
        )
        assert len(first_claims["sid"]) == 32

        refreshed = client.post("/api/v1/auth/refresh")
        assert refreshed.status_code == 200, refreshed.text
        next_claims = decode_token(
            refreshed.json()["access_token"], settings.SECRET_KEY, settings.ALGORITHM,
        )
        assert next_claims["sid"] == first_claims["sid"]

    def test_lists_only_own_sessions_with_current_flag(self, client: TestClient, setup_db):
        user_id, email = _create_user()
        token_a = _new_family(user_id)
        _new_family(user_id)  # a second, non-current family

        # Another user's session must never appear.
        other_id, _other_email = _create_user()
        _new_family(other_id)

        client.cookies.set("refresh_token", token_a)
        res = client.get("/api/v1/auth/sessions", headers=_headers(email))
        client.cookies.clear()
        assert res.status_code == 200, res.text
        sessions = res.json()["sessions"]
        assert len(sessions) == 2
        current = [s for s in sessions if s["current"]]
        assert len(current) == 1
        # No internal identifiers leak.
        for s in sessions:
            assert "family_id" not in s
            assert "token_hash" not in s

    def test_revoke_one_session_requires_step_up(self, client: TestClient, setup_db):
        user_id, email = _create_user()
        token_b = _new_family(user_id)
        ref = _service().current_session(token_b)[1]
        res = client.delete(f"/api/v1/auth/sessions/{ref}", headers=_headers(email))
        assert res.status_code == 428, res.text
        assert res.json()["detail"]["error_code"] == "STEP_UP_REQUIRED"

    def test_revoke_one_session_stops_that_refresh_only(self, client: TestClient, setup_db):
        user_id, email = _create_user()
        token_keep = _new_family(user_id)
        token_kill = _new_family(user_id)
        ref_kill = _service().current_session(token_kill)[1]

        hdr = _headers(email)
        step_up = _issue_step_up(client, hdr, "session_revoke", {"session_ref": ref_kill})
        res = client.delete(
            f"/api/v1/auth/sessions/{ref_kill}",
            headers={**hdr, "X-Step-Up-Token": step_up},
        )
        assert res.status_code == 200, res.text

        # Killed family cannot refresh; kept family still can.
        client.cookies.clear()
        assert client.post("/api/v1/auth/refresh", json={"refresh_token": token_kill}).status_code == 401
        client.cookies.clear()
        assert client.post("/api/v1/auth/refresh", json={"refresh_token": token_keep}).status_code == 200

    def test_revoke_one_session_invalidates_its_bound_access_token_immediately(
        self, client: TestClient, setup_db,
    ):
        """A session revoke is not merely a refresh-token stop: real HTTP
        access tokens carry ``sid`` and the shared auth dependency rejects
        them as soon as that family is revoked."""
        user_id, email = _create_user()
        raw_refresh = _new_family(user_id)
        session_ref = _service().current_session(raw_refresh, expected_user_id=user_id)[1]
        session_access = create_access_token(
            data={"sub": email, "sid": session_ref},
            secret_key=settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
            expires_delta=timedelta(minutes=30),
        )

        actor_headers = _headers(email)
        step_up = _issue_step_up(
            client, actor_headers, "session_revoke", {"session_ref": session_ref},
        )
        revoked = client.delete(
            f"/api/v1/auth/sessions/{session_ref}",
            headers={**actor_headers, "X-Step-Up-Token": step_up},
        )
        assert revoked.status_code == 200, revoked.text

        denied = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {session_access}"},
        )
        assert denied.status_code == 401

    def test_cannot_revoke_another_users_session(self, client: TestClient, setup_db):
        _victim_id, _ = _create_user()
        victim_token = _new_family(_victim_id)
        victim_ref = _service().current_session(victim_token)[1]

        attacker_id, attacker_email = _create_user()
        hdr = _headers(attacker_email)
        step_up = _issue_step_up(client, hdr, "session_revoke", {"session_ref": victim_ref})
        res = client.delete(
            f"/api/v1/auth/sessions/{victim_ref}",
            headers={**hdr, "X-Step-Up-Token": step_up},
        )
        assert res.status_code == 404, res.text
        # Victim session still alive.
        client.cookies.clear()
        assert client.post("/api/v1/auth/refresh", json={"refresh_token": victim_token}).status_code == 200

    def test_revoke_others_keeps_current_kills_the_rest(self, client: TestClient, setup_db):
        user_id, email = _create_user()
        token_current = _new_family(user_id)
        token_other1 = _new_family(user_id)
        token_other2 = _new_family(user_id)
        current_ref = _service().current_session(token_current)[1]

        hdr = _headers(email)
        step_up = _issue_step_up(client, hdr, "other_sessions_revoke", {"keep_session_ref": current_ref})
        client.cookies.set("refresh_token", token_current)
        res = client.post(
            "/api/v1/auth/sessions/revoke-others",
            headers={**hdr, "X-Step-Up-Token": step_up},
        )
        client.cookies.clear()
        assert res.status_code == 200, res.text
        assert res.json()["revoked_count"] == 2

        assert client.post("/api/v1/auth/refresh", json={"refresh_token": token_current}).status_code == 200
        client.cookies.clear()
        assert client.post("/api/v1/auth/refresh", json={"refresh_token": token_other1}).status_code == 401
        client.cookies.clear()
        assert client.post("/api/v1/auth/refresh", json={"refresh_token": token_other2}).status_code == 401

    def test_revoke_others_counts_families_not_rotation_rows(self, client: TestClient, setup_db):
        user_id, email = _create_user()
        token_current = _new_family(user_id)
        token_other = _new_family(user_id)

        # Rotate the other family once, leaving one consumed tombstone plus
        # one live successor. The API must report one revoked *session*, not
        # two affected database rows.
        db = TestingSessionLocal()
        try:
            rotated = _service(db).rotate_refresh_token(token_other)
        finally:
            db.close()
        assert rotated is not None
        _user, token_other_successor = rotated

        current_ref = _service().current_session(
            token_current, expected_user_id=user_id,
        )[1]
        hdr = _headers(email)
        step_up = _issue_step_up(
            client, hdr, "other_sessions_revoke", {"keep_session_ref": current_ref},
        )
        client.cookies.set("refresh_token", token_current)
        res = client.post(
            "/api/v1/auth/sessions/revoke-others",
            headers={**hdr, "X-Step-Up-Token": step_up},
        )
        client.cookies.clear()
        assert res.status_code == 200, res.text
        assert res.json()["revoked_count"] == 1
        assert client.post(
            "/api/v1/auth/refresh", json={"refresh_token": token_other_successor},
        ).status_code == 401

    def test_refresh_cookie_from_another_user_is_not_the_current_session(
        self, client: TestClient, setup_db,
    ):
        """The refresh cookie and bearer identity must belong to the same
        user. A mixed cookie can neither mark another user's family current
        nor become the keep-family for a bulk revoke."""
        owner_id, owner_email = _create_user()
        owner_token = _new_family(owner_id)

        other_id, _other_email = _create_user()
        other_token = _new_family(other_id)
        other_ref = _service().current_session(
            other_token, expected_user_id=other_id,
        )[1]

        headers = _headers(owner_email)
        client.cookies.set("refresh_token", other_token)
        listed = client.get("/api/v1/auth/sessions", headers=headers)
        assert listed.status_code == 200, listed.text
        assert all(not row["current"] for row in listed.json()["sessions"])

        # Even a correctly issued proof for the client-claimed foreign ref is
        # rejected before revocation because the server cannot derive a live
        # current session for the bearer user.
        step_up = _issue_step_up(
            client, headers, "other_sessions_revoke", {"keep_session_ref": other_ref},
        )
        result = client.post(
            "/api/v1/auth/sessions/revoke-others",
            headers={**headers, "X-Step-Up-Token": step_up},
        )
        client.cookies.clear()
        assert result.status_code == 400, result.text
        assert result.json()["detail"]["error_code"] == "NO_CURRENT_SESSION"

        # Neither user's real family was touched.
        assert client.post(
            "/api/v1/auth/refresh", json={"refresh_token": owner_token},
        ).status_code == 200
        client.cookies.clear()
        assert client.post(
            "/api/v1/auth/refresh", json={"refresh_token": other_token},
        ).status_code == 200

    def test_step_up_for_one_session_cannot_revoke_a_different_session(self, client: TestClient, setup_db):
        """The proof is scope-bound to a specific session_ref; presenting it
        against a different session's DELETE fails closed (STEP_UP_INVALID)."""
        user_id, email = _create_user()
        token_a = _new_family(user_id)
        token_b = _new_family(user_id)
        ref_a = _service().current_session(token_a)[1]
        ref_b = _service().current_session(token_b)[1]

        hdr = _headers(email)
        step_up_for_a = _issue_step_up(client, hdr, "session_revoke", {"session_ref": ref_a})
        res = client.delete(
            f"/api/v1/auth/sessions/{ref_b}",
            headers={**hdr, "X-Step-Up-Token": step_up_for_a},
        )
        assert res.status_code == 403, res.text
        assert res.json()["detail"]["error_code"] == "STEP_UP_INVALID"


# ── Security activity ───────────────────────────────────────────────────

class TestSecurityActivity:
    def test_lists_only_own_allowlisted_events_paginated(self, client: TestClient, setup_db):
        user_id, email = _create_user()
        db = TestingSessionLocal()
        try:
            _service(db).login(email, PASSWORD)
        finally:
            db.close()

        res = client.get("/api/v1/auth/security-activity?limit=10&offset=0", headers=_headers(email))
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["total"] >= 1
        assert any(item["action"] == "login_succeeded" for item in body["items"])
        # Whitelisted fields only — no raw payload.
        for item in body["items"]:
            assert set(item.keys()) <= {"id", "action", "at", "ip_address", "device", "request_id"}
