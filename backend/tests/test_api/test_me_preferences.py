"""Gate 3A — current-user preferences (staff language).

Covers the ``PATCH /auth/me/preferences`` self-service contract:
ownership (token-derived target), the ``ar|en`` staff allow-list, no-op
audit suppression, real-change audit, mass-assignment rejection, and the
``preferred_language`` field on the ``GET /auth/me`` DTO.

Money/business behavior is deliberately out of scope: language is a personal
display preference and must never change currency or financial config.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.kernel.models.user import User
from app.core.kernel.security import get_password_hash
from app.modules.core.models import AuditLog
from tests.conftest import TestingSessionLocal, _make_token


PASSWORD = "Current@12345"
_AUDIT_ACTION = "user.preferences.language_changed"


def _create_user(*, role: str = "cashier", language: str | None = "ar") -> tuple[int, str]:
    email = f"gate3a-{role}-{uuid.uuid4().hex}@test.local"
    db = TestingSessionLocal()
    try:
        user = User(
            email=email,
            password_hash=get_password_hash(PASSWORD),
            full_name="Gate 3A Test",
            role=role,
            is_active=True,
            preferred_language=language,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id, email
    finally:
        db.close()


def _headers(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_make_token(email)}"}


def _language_of(user_id: int) -> str | None:
    db = TestingSessionLocal()
    try:
        return db.query(User).filter(User.id == user_id).first().preferred_language
    finally:
        db.close()


def _audit_count(user_id: int) -> int:
    db = TestingSessionLocal()
    try:
        return (
            db.query(AuditLog)
            .filter(AuditLog.user_id == user_id, AuditLog.action == _AUDIT_ACTION)
            .count()
        )
    finally:
        db.close()


# ─────────────────────────── GET /auth/me ──────────────────────────────

def test_me_exposes_preferred_language(client: TestClient) -> None:
    _, email = _create_user(language="en")
    res = client.get("/api/v1/auth/me", headers=_headers(email))
    assert res.status_code == 200
    assert res.json()["preferred_language"] == "en"


def test_me_normalizes_null_language_to_default(client: TestClient) -> None:
    _, email = _create_user(language=None)
    res = client.get("/api/v1/auth/me", headers=_headers(email))
    assert res.status_code == 200
    # Legacy null normalizes to the safe staff default, never leaks to the UI.
    assert res.json()["preferred_language"] == "ar"


def test_me_normalizes_public_only_language_to_default(client: TestClient) -> None:
    # A public-only language (ru/it) is not staff-renderable → safe default.
    _, email = _create_user(language="ru")
    res = client.get("/api/v1/auth/me", headers=_headers(email))
    assert res.json()["preferred_language"] == "ar"


# ────────────────────── PATCH /auth/me/preferences ─────────────────────

def test_update_own_language_succeeds_and_audits(client: TestClient) -> None:
    user_id, email = _create_user(language="ar")
    res = client.patch(
        "/api/v1/auth/me/preferences",
        json={"preferred_language": "en"},
        headers=_headers(email),
    )
    assert res.status_code == 200
    assert res.json()["preferred_language"] == "en"
    assert _language_of(user_id) == "en"
    assert _audit_count(user_id) == 1


def test_update_is_case_insensitive_and_trimmed(client: TestClient) -> None:
    user_id, email = _create_user(language="ar")
    res = client.patch(
        "/api/v1/auth/me/preferences",
        json={"preferred_language": "  EN "},
        headers=_headers(email),
    )
    assert res.status_code == 200
    assert _language_of(user_id) == "en"


def test_noop_update_writes_no_audit(client: TestClient) -> None:
    user_id, email = _create_user(language="ar")
    res = client.patch(
        "/api/v1/auth/me/preferences",
        json={"preferred_language": "ar"},
        headers=_headers(email),
    )
    assert res.status_code == 200
    assert _audit_count(user_id) == 0


def test_normalizing_change_from_legacy_value_audits_once(client: TestClient) -> None:
    # Stored value is a public-only language; setting it to a real staff value
    # is a genuine change and must persist + audit exactly once.
    user_id, email = _create_user(language="ru")
    res = client.patch(
        "/api/v1/auth/me/preferences",
        json={"preferred_language": "ar"},
        headers=_headers(email),
    )
    assert res.status_code == 200
    assert _language_of(user_id) == "ar"
    assert _audit_count(user_id) == 1


@pytest.mark.parametrize("bad", ["ru", "it", "fr", "de", "", "arabic", "EN-US"])
def test_unsupported_language_rejected(client: TestClient, bad: str) -> None:
    user_id, email = _create_user(language="ar")
    res = client.patch(
        "/api/v1/auth/me/preferences",
        json={"preferred_language": bad},
        headers=_headers(email),
    )
    assert res.status_code == 422
    assert _language_of(user_id) == "ar"  # unchanged
    assert _audit_count(user_id) == 0


def test_mass_assignment_extra_fields_rejected(client: TestClient) -> None:
    # Attempts to smuggle privileged fields must fail (extra="forbid"), and
    # never touch role/is_active.
    user_id, email = _create_user(role="cashier", language="ar")
    res = client.patch(
        "/api/v1/auth/me/preferences",
        json={"preferred_language": "en", "role": "super_admin", "is_active": True},
        headers=_headers(email),
    )
    assert res.status_code == 422
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        assert user.role == "cashier"
        assert user.preferred_language == "ar"  # rejected as a whole
    finally:
        db.close()


def test_no_user_id_targeting_possible(client: TestClient) -> None:
    # Even if a user_id is supplied, it is an unknown field → rejected; the
    # endpoint only ever mutates the token's own user.
    victim_id, _ = _create_user(language="ar")
    _, attacker_email = _create_user(language="ar")
    res = client.patch(
        "/api/v1/auth/me/preferences",
        json={"preferred_language": "en", "user_id": victim_id},
        headers=_headers(attacker_email),
    )
    assert res.status_code == 422
    assert _language_of(victim_id) == "ar"


def test_requires_authentication(client: TestClient) -> None:
    res = client.patch(
        "/api/v1/auth/me/preferences",
        json={"preferred_language": "en"},
    )
    assert res.status_code == 401
