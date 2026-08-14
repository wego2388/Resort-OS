#!/usr/bin/env python3
"""Archive every visible user except an explicit, reviewed retain allowlist.

This is a production cleanup tool for replacing experimental login accounts.
It deliberately does not hard-delete ``users`` rows: business and audit rows
may reference their numeric IDs.  Instead it anonymizes and soft-deletes the
identity, revokes branch access, unlinks HR, and removes reusable auth state.

Dry-run is the default.  Applying requires an active retained super-admin,
an exact expected target count, a reason, and an exact confirmation phrase.
No email address or other account PII is emitted in the report or audit log.
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.kernel.models.user import (
    RefreshToken,
    StepUpGrant,
    TokenBlacklist,
    TwoFactorRecoveryCode,
    User,
)
from app.core.kernel.security import get_password_hash
from app.modules.core.models import (
    AuditLog,
    Branch,
    PinCredential,
    UserBranchMembership,
    UserPermission,
)
from app.modules.hr.models import Employee

EXPECTED_BRANCH_NAME = "El Kheima Beach Resort"


@dataclass(frozen=True)
class ArchiveReport:
    branch_id: int
    retained_user_ids: list[int]
    target_user_ids: list[int]
    target_role_counts: dict[str, int]
    revoked_membership_count: int
    unlinked_employee_count: int
    deleted_auth_row_counts: dict[str, int]
    applied: bool


def _canonical_email(value: str) -> str:
    canonical = value.strip().casefold()
    if not canonical or "@" not in canonical:
        raise ValueError("Every retained email must be a non-empty email address")
    return canonical


def _validated_retain_emails(values: list[str]) -> list[str]:
    canonical = [_canonical_email(value) for value in values]
    if not canonical:
        raise ValueError("At least one --retain-email is required")
    if len(canonical) != len(set(canonical)):
        raise ValueError("Duplicate --retain-email values are not allowed")
    return sorted(canonical)


def archive_experimental_accounts(
    db: Session,
    *,
    retain_emails: list[str],
    actor_email: str,
    expected_target_count: int,
    apply: bool,
    reason: str | None,
) -> ArchiveReport:
    """Build or atomically apply the reviewed experimental-account cleanup."""
    retained_email_set = set(_validated_retain_emails(retain_emails))
    actor_canonical = _canonical_email(actor_email)
    if actor_canonical not in retained_email_set:
        raise ValueError("The audit actor must be included in the retain allowlist")
    if expected_target_count < 0:
        raise ValueError("Expected target count cannot be negative")
    if apply and (reason is None or len(reason.strip()) < 10):
        raise ValueError("A meaningful --reason of at least 10 characters is required")

    branches = (
        db.query(Branch)
        .filter(Branch.is_active.is_(True))
        .order_by(Branch.id)
        .with_for_update()
        .all()
    )
    if len(branches) != 1:
        raise ValueError("Expected exactly one active operating branch")
    branch = branches[0]
    if branch.name.strip() != EXPECTED_BRANCH_NAME:
        raise ValueError(
            f"Active branch name must be exactly {EXPECTED_BRANCH_NAME!r}; "
            f"found branch ID {branch.id} with a different name"
        )

    visible_users = (
        db.query(User)
        .filter(User.deleted_at.is_(None))
        .order_by(User.id)
        .with_for_update()
        .all()
    )
    retained_users = [
        user for user in visible_users
        if user.email.strip().casefold() in retained_email_set
    ]
    found_retained = {user.email.strip().casefold() for user in retained_users}
    missing = sorted(retained_email_set - found_retained)
    if missing:
        # Do not echo the addresses: a production log must not leak account PII.
        raise ValueError(f"{len(missing)} retained account(s) were not found")
    if any(not user.is_active for user in retained_users):
        raise ValueError("Every retained account must be active")
    if not any(user.role == "super_admin" for user in retained_users):
        raise ValueError("The retain allowlist must include an active super-admin")
    if not any(user.role == "owner" for user in retained_users):
        raise ValueError("The retain allowlist must include an active owner")

    retained_ids = [user.id for user in retained_users]
    retained_branch_user_ids = {
        row.user_id
        for row in db.query(UserBranchMembership.user_id)
        .filter(
            UserBranchMembership.user_id.in_(retained_ids),
            UserBranchMembership.branch_id == branch.id,
            UserBranchMembership.is_active.is_(True),
        )
        .all()
    }
    if retained_branch_user_ids != set(retained_ids):
        raise ValueError(
            "Every retained account must have an active membership in the operating branch"
        )

    actor = next(
        (user for user in retained_users if user.email.strip().casefold() == actor_canonical),
        None,
    )
    if actor is None or actor.role != "super_admin" or not actor.is_active:
        raise ValueError("The audit actor must be an active retained super-admin")

    target_users = [
        user for user in visible_users
        if user.email.strip().casefold() not in retained_email_set
    ]
    target_ids = [user.id for user in target_users]
    if len(target_ids) != expected_target_count:
        raise ValueError(
            "Target-count guard failed: "
            f"expected {expected_target_count}, found {len(target_ids)}"
        )

    target_role_counts = dict(sorted(Counter(user.role for user in target_users).items()))
    memberships = []
    linked_employees = []
    if target_ids:
        memberships = (
            db.query(UserBranchMembership)
            .filter(UserBranchMembership.user_id.in_(target_ids))
            .order_by(UserBranchMembership.id)
            .with_for_update()
            .all()
        )
        linked_employees = (
            db.query(Employee)
            .filter(Employee.user_id.in_(target_ids))
            .order_by(Employee.id)
            .with_for_update()
            .all()
        )

    auth_models = {
        "refresh_tokens": RefreshToken,
        "recovery_codes": TwoFactorRecoveryCode,
        "step_up_grants": StepUpGrant,
        "token_blacklist": TokenBlacklist,
        "user_permissions": UserPermission,
        "pin_credentials": PinCredential,
    }
    auth_counts = {
        name: (
            db.query(model).filter(model.user_id.in_(target_ids)).count()
            if target_ids else 0
        )
        for name, model in auth_models.items()
    }

    report = ArchiveReport(
        branch_id=branch.id,
        retained_user_ids=sorted(user.id for user in retained_users),
        target_user_ids=target_ids,
        target_role_counts=target_role_counts,
        revoked_membership_count=len(memberships),
        unlinked_employee_count=len(linked_employees),
        deleted_auth_row_counts=auth_counts,
        applied=apply,
    )

    if not apply:
        db.rollback()
        return report

    now = datetime.now(timezone.utc)
    for employee in linked_employees:
        employee.user_id = None

    for membership in memberships:
        membership.is_active = False
        membership.is_default = False
        membership.revoked_at = now
        membership.revoked_by = actor.id

    for model in auth_models.values():
        if target_ids:
            db.query(model).filter(model.user_id.in_(target_ids)).delete(
                synchronize_session=False
            )

    for user in target_users:
        # Keep only the stable numeric ID required by financial/audit FKs.
        user.email = f"archived-user-{user.id}-{secrets.token_hex(8)}@invalid.local"
        user.full_name = f"Archived experimental account #{user.id}"
        user.password_hash = get_password_hash(secrets.token_urlsafe(48))
        user.is_active = False
        user.deleted_at = now
        user.failed_login_attempts = 0
        user.account_locked_until = None
        user.two_factor_enabled = False
        user.two_factor_secret = None
        user.two_factor_bootstrap_required = False
        user.two_factor_enrollment_token_hash = None
        user.two_factor_enrollment_expires_at = None
        user.two_factor_last_used_step = None
        user.must_change_password = False
        user.email_verified = False
        user.phone = None
        user.profile_photo_url = None
        user.job_title = None
        user.department = None
        user.national_id = None
        user.hire_date = None
        user.contract_type = None
        user.base_salary = None
        user.emergency_phone = None

    db.add(AuditLog(
        user_id=actor.id,
        branch_id=branch.id,
        action="experimental_accounts_archived",
        entity_type="branch",
        entity_id=branch.id,
        old_data=None,
        new_data=json.dumps({
            "reason": reason.strip(),
            "retained_user_ids": report.retained_user_ids,
            "target_user_ids": report.target_user_ids,
            "target_role_counts": report.target_role_counts,
            "revoked_membership_count": report.revoked_membership_count,
            "unlinked_employee_count": report.unlinked_employee_count,
            "deleted_auth_row_counts": report.deleted_auth_row_counts,
        }, sort_keys=True),
    ))
    db.commit()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retain-email", action="append", default=[])
    parser.add_argument("--actor-email", required=True)
    parser.add_argument("--expected-target-count", required=True, type=int)
    parser.add_argument("--reason")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--confirm",
        help="With --apply, must equal ARCHIVE-<count>-EXPERIMENTAL-ACCOUNTS",
    )
    args = parser.parse_args()

    expected_confirmation = (
        f"ARCHIVE-{args.expected_target_count}-EXPERIMENTAL-ACCOUNTS"
    )
    if args.apply and args.confirm != expected_confirmation:
        print(
            f"ERROR: --confirm must equal {expected_confirmation}",
            file=sys.stderr,
        )
        return 1

    try:
        with SessionLocal() as db:
            report = archive_experimental_accounts(
                db,
                retain_emails=args.retain_email,
                actor_email=args.actor_email,
                expected_target_count=args.expected_target_count,
                apply=args.apply,
                reason=args.reason,
            )
    except Exception as exc:  # noqa: BLE001 - CLI must fail closed on any DB error
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(asdict(report), indent=2, sort_keys=True))
    if args.apply:
        # Database state rejects every old access token even if cache is down;
        # the cache cutoff is extra defense for already-issued JWTs.
        revocation_failures: list[int] = []
        from app.core.deps import revoke_user_tokens

        for user_id in report.target_user_ids:
            try:
                revoke_user_tokens(user_id)
            except Exception:  # noqa: BLE001 - report every cache backend failure
                revocation_failures.append(user_id)
        if revocation_failures:
            print(
                "ERROR: database cleanup committed, but token-cache cutoff failed "
                f"for user IDs {revocation_failures}",
                file=sys.stderr,
            )
            return 2
        print("APPLIED: target identities archived and authentication state revoked")
    else:
        print("DRY RUN ONLY: no rows were changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
