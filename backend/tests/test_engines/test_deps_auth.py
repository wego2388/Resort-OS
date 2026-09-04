"""
tests/test_engines/test_deps_auth.py
Pure-logic checks for the auth dependency chain — role→level mapping and
the mandatory-2FA role set. (Live JWT decode / token-blacklist / revocation
/ 2FA-gate / rate-limit behavior is verified against the running app — see
project memory; SQLite test DB has no row-locking, so concurrency-dependent
paths like SELECT FOR UPDATE NOWAIT are verified live too, not here.)
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.deps import (
    MANDATORY_2FA_ROLES,
    ROLE_LEVELS,
    get_booking_operator_user,
    get_cashier_user,
    get_finance_user,
    get_hr_reader_user,
    get_operations_admin_user,
    get_pms_user,
    get_waiter_user,
    get_websocket_user,
    user_level,
)


class TestUserLevel:
    def test_known_roles_map_to_expected_thresholds(self):
        assert user_level(SimpleNamespace(role="super_admin")) == 100
        assert user_level(SimpleNamespace(role="admin")) == 80
        assert user_level(SimpleNamespace(role="manager")) == 60
        assert user_level(SimpleNamespace(role="cashier")) == 40
        assert user_level(SimpleNamespace(role="waiter")) == 30
        assert user_level(SimpleNamespace(role="customer")) == 0

    def test_unknown_role_defaults_to_zero(self):
        assert user_level(SimpleNamespace(role="totally-made-up-role")) == 0

    def test_thresholds_are_strictly_ordered(self):
        """get_manager_user/get_admin_user/etc. rely on `<` comparisons against
        these — if two roles ever collapse to the same level, access checks
        between them silently stop discriminating."""
        ordered = sorted(set(ROLE_LEVELS.values()), reverse=True)
        assert ordered == sorted(ordered, reverse=True)
        assert max(ROLE_LEVELS.values()) == 100
        assert min(ROLE_LEVELS.values()) == 0


class TestMandatory2FARoles:
    def test_super_admin_and_accountant_require_2fa(self):
        assert "super_admin" in MANDATORY_2FA_ROLES
        assert "accountant" in MANDATORY_2FA_ROLES

    def test_operational_roles_do_not_require_2fa(self):
        assert "waiter" not in MANDATORY_2FA_ROLES
        assert "cashier" not in MANDATORY_2FA_ROLES
        assert "customer" not in MANDATORY_2FA_ROLES


class TestNamedWorkspaceBoundaries:
    """Specialist roles must not inherit unrelated workspaces by level."""

    @pytest.mark.parametrize(
        ("dependency", "allowed_role"),
        [
            (get_finance_user, "accountant"),
            (get_hr_reader_user, "hr_manager"),
            (get_booking_operator_user, "receptionist"),
            (get_pms_user, "employee"),
            (get_cashier_user, "cashier"),
            (get_waiter_user, "waiter"),
            (get_operations_admin_user, "supervisor"),
        ],
    )
    def test_named_workspace_accepts_its_role(self, dependency, allowed_role):
        user = SimpleNamespace(role=allowed_role)
        assert dependency(user) is user

    @pytest.mark.parametrize(
        "dependency",
        [
            get_finance_user,
            get_hr_reader_user,
            get_booking_operator_user,
            get_pms_user,
            get_cashier_user,
            get_waiter_user,
            get_operations_admin_user,
        ],
    )
    def test_timeshare_admin_is_isolated_from_general_workspaces(self, dependency):
        with pytest.raises(HTTPException) as exc_info:
            dependency(SimpleNamespace(role="timeshare_admin"))
        assert exc_info.value.status_code == 403

    @pytest.mark.parametrize(
        "dependency",
        [
            get_booking_operator_user,
            get_pms_user,
            get_cashier_user,
            get_waiter_user,
            get_operations_admin_user,
        ],
    )
    def test_accountant_does_not_inherit_operations_access(self, dependency):
        with pytest.raises(HTTPException) as exc_info:
            dependency(SimpleNamespace(role="accountant"))
        assert exc_info.value.status_code == 403


class _FakeWebSocket:
    query_params = {"token": "test-token"}
    url = SimpleNamespace(path="/api/v1/finance/ws/shifts/1")

    def __init__(self):
        self.closed_with: int | None = None

    async def close(self, code: int):
        self.closed_with = code


class TestNamedWebSocketBoundaries:
    @pytest.mark.asyncio
    async def test_specialist_role_is_rejected_from_unrelated_live_channel(self, monkeypatch):
        user = SimpleNamespace(
            role="timeshare_admin",
            is_active=True,
            must_change_password=False,
            two_factor_enabled=False,
        )
        monkeypatch.setattr(
            "app.core.deps._resolve_user_from_token",
            lambda _token, _db: user,
        )
        websocket = _FakeWebSocket()

        resolved = await get_websocket_user(
            websocket,
            object(),
            min_level=40,
            allowed_roles={"cashier", "manager", "admin", "super_admin"},
        )

        assert resolved is None
        assert websocket.closed_with == 4403

    @pytest.mark.asyncio
    async def test_named_live_channel_accepts_allowed_role(self, monkeypatch):
        user = SimpleNamespace(
            role="cashier",
            is_active=True,
            must_change_password=False,
            two_factor_enabled=False,
        )
        monkeypatch.setattr(
            "app.core.deps._resolve_user_from_token",
            lambda _token, _db: user,
        )
        websocket = _FakeWebSocket()

        resolved = await get_websocket_user(
            websocket,
            object(),
            min_level=40,
            allowed_roles={"cashier", "manager", "admin", "super_admin"},
        )

        assert resolved is user
        assert websocket.closed_with is None
