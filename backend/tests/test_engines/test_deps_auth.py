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

from app.core.deps import MANDATORY_2FA_ROLES, ROLE_LEVELS, user_level


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
