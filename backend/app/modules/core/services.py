"""
app/modules/core/services.py

This file is the stable façade for every core service function — every
existing caller (`from app.modules.core import services`,
`services.<name>(...)`, `patch("app.modules.core.services.X", ...)`)
keeps working completely unchanged. The actual implementations were
extracted by capability into app/modules/core/_services/ (2026-09-07
oversized-file split — see PROJECT_STATUS.md) to keep each file a
manageable, single-purpose size.

Security-critical module — PIN approval, permissions, branch context,
and super_admin invariants live here. Callers across the codebase do a
fresh `from app.modules.core.services import get_effective_vat_percentage`
(etc.) on every call rather than a one-time module-load import, so the
`patch("app.modules.core.services.X")` pattern used by test_dining.py
works correctly against this façade without any special handling.
"""
from __future__ import annotations

from app.modules.core import crud

from app.modules.core._services._exceptions import (
    UserNotFoundError,
    SuperAdminPermissionOverrideForbiddenError,
    SuperAdminSelfLockoutForbiddenError,
    LastActiveSuperAdminRequiredError,
    ActorSuperAdminPrivilegesChangedError,
    ActorAuthorizationChangedError,
    MandatoryTwoFactorEnrollmentRequiredError,
)
from app.modules.core._services._audit_helpers import (
    _step_up_audit_context,
    _commit_rejected_control_plane_audit,
)
from app.modules.core._services.pins import (
    assert_can_manage_target_pin,
    set_pin,
    get_pin_status,
    list_eligible_approvers,
    list_terminal_operators,
    verify_pin,
    resolve_pin_approval,
    PinBranchMismatchError,
    pin_switch_login,
    PIN_MAX_ATTEMPTS,
    PIN_LOCKOUT_SECONDS,
    PIN_SWITCH_MAX_ROLE_LEVEL,
    TERMINAL_OPERATOR_ROLES,
)
from app.modules.core._services.branches import (
    get_branch_or_404,
    create_branch,
    update_branch,
    delete_branch,
)
from app.modules.core._services.accounts import (
    update_user_preferences,
    create_staff_account,
    update_user_role,
    unlock_user_account,
    force_reset_2fa,
    reset_staff_credentials,
)
from app.modules.core._services.settings import (
    get_setting_value,
    upsert_setting,
    _effective_percentage_setting,
    get_effective_vat_percentage,
    get_effective_service_charge_percentage,
)
from app.modules.core._services.authorization import (
    _resolve_permission,
    has_permission,
    list_user_permissions,
    get_effective_permissions,
    BranchAccessDeniedError,
    BranchContextRequiredError,
    SessionChangedError,
    _active_memberships,
    get_allowed_branches,
    get_default_branch_id,
    get_user_branch_id,
    _can_enter_branch,
    assert_branch_access,
    build_auth_bootstrap,
    switch_active_branch,
    grant_permission,
    revoke_permission,
)
from app.modules.core._services.guest_access import (
    list_guest_alerts,
    guest_alert_read,
    assert_guest_alerts_enabled,
    assert_location_belongs_to_branch,
    create_guest_alert,
    get_guest_alert_public_status,
    update_alert_status,
    resolve_bill_requests_for_paid_order,
    _location_label,
    _lock_service_location,
    _guest_service_outlets,
    _guest_capabilities,
    _service_location_read,
    _assert_active_location,
    create_guest_session,
    resolve_guest_session,
    create_or_rotate_service_location_token,
    list_service_location_tokens,
    resolve_service_location_token,
)

__all__ = [
    "crud",
    "UserNotFoundError",
    "SuperAdminPermissionOverrideForbiddenError",
    "SuperAdminSelfLockoutForbiddenError",
    "LastActiveSuperAdminRequiredError",
    "ActorSuperAdminPrivilegesChangedError",
    "ActorAuthorizationChangedError",
    "MandatoryTwoFactorEnrollmentRequiredError",
    "_step_up_audit_context",
    "_commit_rejected_control_plane_audit",
    "assert_can_manage_target_pin",
    "set_pin",
    "get_pin_status",
    "list_eligible_approvers",
    "list_terminal_operators",
    "verify_pin",
    "resolve_pin_approval",
    "PinBranchMismatchError",
    "pin_switch_login",
    "PIN_MAX_ATTEMPTS",
    "PIN_LOCKOUT_SECONDS",
    "PIN_SWITCH_MAX_ROLE_LEVEL",
    "TERMINAL_OPERATOR_ROLES",
    "get_branch_or_404",
    "create_branch",
    "update_branch",
    "delete_branch",
    "update_user_preferences",
    "create_staff_account",
    "update_user_role",
    "unlock_user_account",
    "force_reset_2fa",
    "reset_staff_credentials",
    "get_setting_value",
    "upsert_setting",
    "_effective_percentage_setting",
    "get_effective_vat_percentage",
    "get_effective_service_charge_percentage",
    "_resolve_permission",
    "has_permission",
    "list_user_permissions",
    "get_effective_permissions",
    "BranchAccessDeniedError",
    "BranchContextRequiredError",
    "SessionChangedError",
    "_active_memberships",
    "get_allowed_branches",
    "get_default_branch_id",
    "get_user_branch_id",
    "_can_enter_branch",
    "assert_branch_access",
    "build_auth_bootstrap",
    "switch_active_branch",
    "grant_permission",
    "revoke_permission",
    "list_guest_alerts",
    "guest_alert_read",
    "assert_guest_alerts_enabled",
    "assert_location_belongs_to_branch",
    "create_guest_alert",
    "get_guest_alert_public_status",
    "update_alert_status",
    "resolve_bill_requests_for_paid_order",
    "_location_label",
    "_lock_service_location",
    "_guest_service_outlets",
    "_guest_capabilities",
    "_service_location_read",
    "_assert_active_location",
    "create_guest_session",
    "resolve_guest_session",
    "create_or_rotate_service_location_token",
    "list_service_location_tokens",
    "resolve_service_location_token",
]
