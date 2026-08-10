"""CX-02C — session-scoped active branch and fail-closed membership auth."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.kernel.auth.service import AuthService
from app.core.kernel.models.user import RefreshToken, User
from app.core.kernel.security import create_access_token, get_password_hash
from app.modules.core.models import AuditLog, Branch, UserBranchMembership
from app.modules.hr.models import Employee
from tests.conftest import TestingSessionLocal


def _user_and_branches(
    *,
    memberships: tuple[str, ...] = ("a", "b"),
) -> tuple[int, str, dict[str, int]]:
    db = TestingSessionLocal()
    try:
        marker = uuid.uuid4().hex[:10].upper()
        user = User(
            email=f"cx02c-{marker.lower()}@test.local",
            password_hash=get_password_hash("Branch@Test123"),
            full_name="CX-02C Manager",
            role="manager",
            is_active=True,
        )
        branches = {
            key: Branch(
                name=f"Branch {key.upper()}",
                name_ar=f"فرع {key.upper()}",
                code=f"C2-{key.upper()}-{marker}",
            )
            for key in ("a", "b", "c")
        }
        db.add_all([user, *branches.values()])
        db.flush()
        for key in memberships:
            db.add(UserBranchMembership(
                user_id=user.id,
                branch_id=branches[key].id,
                is_default=key == "a",
                is_active=True,
            ))
        db.commit()
        return user.id, user.email, {key: row.id for key, row in branches.items()}
    finally:
        db.close()


def _session_headers(user_id: int, email: str) -> tuple[dict[str, str], str]:
    db = TestingSessionLocal()
    try:
        auth = AuthService(db, User, settings)
        raw_refresh = auth.create_refresh_token(user_id)
        current = auth.current_session(raw_refresh, expected_user_id=user_id)
        assert current is not None
        access = create_access_token(
            {"sub": email, "sid": current[1], "bid": current[2]},
            settings.SECRET_KEY,
            settings.ALGORITHM,
        )
        return {"Authorization": f"Bearer {access}"}, current[1]
    finally:
        db.close()


def test_bootstrap_and_switch_are_scoped_to_one_refresh_family(
    client: TestClient,
):
    user_id, email, branch_ids = _user_and_branches()
    first_headers, first_ref = _session_headers(user_id, email)
    second_headers, second_ref = _session_headers(user_id, email)

    first = client.get("/api/v1/auth/bootstrap", headers=first_headers)
    assert first.status_code == 200, first.text
    assert first.headers["cache-control"] == "no-store"
    assert first.json()["active_branch_id"] == branch_ids["a"]
    assert first.json()["allowed_branch_ids"] == [branch_ids["a"], branch_ids["b"]]

    switched = client.put(
        "/api/v1/auth/active-branch",
        json={"branch_id": branch_ids["b"]},
        headers=first_headers,
    )
    assert switched.status_code == 200, switched.text
    assert switched.json()["active_branch_id"] == branch_ids["b"]

    # The second device/family stays on its own context.
    second = client.get("/api/v1/auth/bootstrap", headers=second_headers)
    assert second.status_code == 200, second.text
    assert second.json()["active_branch_id"] == branch_ids["a"]

    db = TestingSessionLocal()
    try:
        rows = {
            row.family_public_id: row.active_branch_id
            for row in db.query(RefreshToken).filter(
                RefreshToken.family_public_id.in_([first_ref, second_ref]),
                RefreshToken.consumed_at.is_(None),
            )
        }
        assert rows == {
            first_ref: branch_ids["b"],
            second_ref: branch_ids["a"],
        }
        audit = db.query(AuditLog).filter(
            AuditLog.user_id == user_id,
            AuditLog.action == "active_branch_switched",
        ).one()
        assert audit.branch_id == branch_ids["b"]
        assert first_ref in (audit.new_data or "")
    finally:
        db.close()


def test_switch_rejects_non_member_branch_without_mutating_session(
    client: TestClient,
):
    user_id, email, branch_ids = _user_and_branches(memberships=("a",))
    headers, session_ref = _session_headers(user_id, email)

    denied = client.put(
        "/api/v1/auth/active-branch",
        json={"branch_id": branch_ids["c"]},
        headers=headers,
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["error_code"] == "BRANCH_ACCESS_DENIED"

    db = TestingSessionLocal()
    try:
        live = db.query(RefreshToken).filter(
            RefreshToken.family_public_id == session_ref,
            RefreshToken.consumed_at.is_(None),
        ).one()
        assert live.active_branch_id == branch_ids["a"]
    finally:
        db.close()


def test_revoked_membership_invalidates_live_context_on_next_request(
    client: TestClient,
):
    user_id, email, branch_ids = _user_and_branches(memberships=("a",))
    headers, _session_ref = _session_headers(user_id, email)

    db = TestingSessionLocal()
    try:
        membership = db.query(UserBranchMembership).filter(
            UserBranchMembership.user_id == user_id,
            UserBranchMembership.branch_id == branch_ids["a"],
        ).one()
        membership.is_active = False
        membership.is_default = False
        membership.revoked_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

    bootstrap = client.get("/api/v1/auth/bootstrap", headers=headers)
    assert bootstrap.status_code == 200, bootstrap.text
    assert bootstrap.json()["active_branch_id"] is None
    assert bootstrap.json()["allowed_branch_ids"] == []
    assert bootstrap.json()["effective_permissions"] == []


def test_user_without_membership_fails_closed(
    client: TestClient,
):
    user_id, email, _branch_ids = _user_and_branches(memberships=())
    headers, _session_ref = _session_headers(user_id, email)

    bootstrap = client.get("/api/v1/auth/bootstrap", headers=headers)
    assert bootstrap.status_code == 200, bootstrap.text
    assert bootstrap.json()["active_branch_id"] is None
    assert bootstrap.json()["allowed_branch_ids"] == []
    assert bootstrap.json()["requires_branch_selection"] is False


def test_refresh_rotation_copies_active_branch():
    user_id, email, branch_ids = _user_and_branches(memberships=("a", "b"))
    db = TestingSessionLocal()
    try:
        auth = AuthService(db, User, settings)
        raw = auth.create_refresh_token(user_id)
        before = auth.current_session(raw, expected_user_id=user_id)
        assert before is not None
        assert before[2] == branch_ids["a"]

        rotated = auth.rotate_refresh_token(raw)
        assert rotated is not None
        _user, successor = rotated
        after = auth.current_session(successor, expected_user_id=user_id)
        assert after is not None
        assert after[1] == before[1]
        assert after[2] == branch_ids["a"]
    finally:
        db.close()


def test_pin_switch_cannot_cross_terminal_branch(client: TestClient):
    terminal_id, terminal_email, branch_ids = _user_and_branches(memberships=("a",))
    db = TestingSessionLocal()
    try:
        target = User(
            email=f"cx02c-pin-{uuid.uuid4().hex}@test.local",
            password_hash=get_password_hash("Branch@Test123"),
            full_name="Other Branch Cashier",
            role="cashier",
            is_active=True,
        )
        db.add(target)
        db.flush()
        db.add(UserBranchMembership(
            user_id=target.id,
            branch_id=branch_ids["b"],
            is_default=True,
            is_active=True,
        ))
        from app.modules.core import services as core_services

        core_services.set_pin(db, target.id, "2468", created_by=target.id)
        db.commit()
        target_id = target.id
    finally:
        db.close()

    headers, _session_ref = _session_headers(terminal_id, terminal_email)
    denied = client.post(
        "/api/v1/pins/switch",
        json={"user_id": target_id, "pin": "2468"},
        headers=headers,
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["error_code"] == "PIN_BRANCH_MISMATCH"


def test_bootstrap_employee_id_reflects_hr_linkage(client: TestClient):
    """OPS-DATA-02 UX-API-01 §6.4 — /auth/bootstrap must expose whether this
    account has a linked HR Employee record, so the frontend can hide/skip
    /hr/me/* self-service (which always 404s otherwise) instead of finding
    out via a failed request. None for an unlinked account (e.g. the
    super_admin bootstrap account), the real id once one exists."""
    user_id, email, branch_ids = _user_and_branches(memberships=("a",))
    headers, _session_ref = _session_headers(user_id, email)

    unlinked = client.get("/api/v1/auth/bootstrap", headers=headers)
    assert unlinked.status_code == 200, unlinked.text
    assert unlinked.json()["employee_id"] is None

    db = TestingSessionLocal()
    try:
        employee = Employee(
            branch_id=branch_ids["a"],
            employee_code=f"EMP-{uuid.uuid4().hex[:8].upper()}",
            full_name="CX-02C Linked Employee",
            position="Manager",
            basic_salary=Decimal("10000.00"),
            hire_date=date(2024, 1, 1),
            user_id=user_id,
        )
        db.add(employee)
        db.commit()
        db.refresh(employee)
        employee_id = employee.id
    finally:
        db.close()

    linked = client.get("/api/v1/auth/bootstrap", headers=headers)
    assert linked.status_code == 200, linked.text
    assert linked.json()["employee_id"] == employee_id
