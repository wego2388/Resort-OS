"""Local, interactive privileged-account bootstrap and recovery command.

Usage (after migrations):

    python -m app.admin_bootstrap create
    python -m app.admin_bootstrap recover

Passwords and enrollment tokens are generated internally and printed once;
they are deliberately not accepted as command-line arguments or environment
variables, keeping them out of shell history and deployment manifests.
"""
from __future__ import annotations

import argparse
import json
import sys

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.kernel.auth.service import AuthService
from app.core.kernel.models.user import User


LEGACY_DEMO_EMAILS = frozenset({
    "admin@resortos.local",
    "branch_admin@resortos.local",
    "accountant@resortos.local",
    "hr@resortos.local",
    "manager@resortos.local",
    "supervisor@resortos.local",
    "reception@resortos.local",
    "cashier@resortos.local",
    "waiter@resortos.local",
    "chef@resortos.local",
    "kitchen@resortos.local",
    "employee@resortos.local",
})


def disable_legacy_demo_accounts(db) -> int:
    """Disable documented seed identities only after safe replacement."""
    from app.core.deps import revoke_user_tokens  # noqa: PLC0415
    from app.core.kernel.models.user import RefreshToken, StepUpGrant  # noqa: PLC0415
    from app.modules.core.models import AuditLog  # noqa: PLC0415

    named_super_admin_candidates = db.query(User).filter(
        User.role == "super_admin",
        User.is_active.is_(True),
        User.deleted_at.is_(None),
        User.two_factor_enabled.is_(True),
        User.must_change_password.is_(False),
        User.two_factor_bootstrap_required.is_(False),
        ~User.email.in_(LEGACY_DEMO_EMAILS),
    ).order_by(User.id).with_for_update().all()
    named_super_admins = []
    for candidate in named_super_admin_candidates:
        enabled_event = db.query(AuditLog).filter(
            AuditLog.user_id == candidate.id,
            AuditLog.action == "two_factor_enabled",
        ).order_by(AuditLog.created_at.desc()).first()
        if enabled_event is None:
            continue
        verified_login = db.query(AuditLog).filter(
            AuditLog.user_id == candidate.id,
            AuditLog.action == "login_succeeded",
            AuditLog.created_at >= enabled_event.created_at,
            AuditLog.new_data.like('%"assurance": "2fa"%'),
        ).first()
        if verified_login is not None:
            named_super_admins.append(candidate)
    if not named_super_admins:
        raise ValueError(
            "A fully onboarded non-demo super-admin with a verified 2FA login is required "
            "before disabling demo accounts"
        )

    demo_users = db.query(User).filter(
        User.email.in_(LEGACY_DEMO_EMAILS),
        User.deleted_at.is_(None),
    ).order_by(User.id).with_for_update().all()
    demo_ids = [user.id for user in demo_users]
    disabled_count = 0
    for user in demo_users:
        if user.is_active:
            user.is_active = False
            disabled_count += 1
    if demo_ids:
        db.query(RefreshToken).filter(RefreshToken.user_id.in_(demo_ids)).delete(
            synchronize_session=False,
        )
        db.query(StepUpGrant).filter(StepUpGrant.user_id.in_(demo_ids)).delete(
            synchronize_session=False,
        )

    db.add(AuditLog(
        user_id=None,
        branch_id=None,
        action="legacy_demo_accounts_disabled",
        entity_type="security_control_plane",
        entity_id=None,
        old_data=None,
        new_data=json.dumps({
            "matched_count": len(demo_users),
            "disabled_count": disabled_count,
            "replacement_super_admin_ids": [user.id for user in named_super_admins],
        }, sort_keys=True),
    ))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    for user_id in demo_ids:
        revoke_user_tokens(user_id)
    return disabled_count


def _required_input(label: str) -> str:
    value = input(label).strip()
    if not value:
        raise ValueError(f"{label.strip(': ')} is required")
    return value


def _confirm_identity(email: str) -> None:
    confirmation = input(f"Type the account email to confirm ({email}): ").strip().casefold()
    if confirmation != email.casefold():
        raise ValueError("Confirmation did not match; nothing was changed")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a named super-admin or securely recover an existing account.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create a separate named super-admin")
    create.add_argument("--email", help="Non-secret account email (prompted when omitted)")
    create.add_argument("--full-name", help="Named operator (prompted when omitted)")

    recover = subparsers.add_parser(
        "recover",
        help="Rotate an existing account without changing its role",
    )
    recover.add_argument("--email", help="Non-secret account email (prompted when omitted)")
    subparsers.add_parser(
        "disable-legacy-demo",
        help="Disable seed identities after a named super-admin completes 2FA",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "disable-legacy-demo":
            confirmation = input(
                "Type DISABLE LEGACY DEMO ACCOUNTS to confirm: "
            ).strip()
            if confirmation != "DISABLE LEGACY DEMO ACCOUNTS":
                raise ValueError("Confirmation did not match; nothing was changed")
            with SessionLocal() as db:
                disabled_count = disable_legacy_demo_accounts(db)
            print(f"Disabled {disabled_count} active legacy demo account(s).")
            return 0

        email = (args.email or _required_input("Account email: ")).strip().casefold()
        full_name = (
            (args.full_name or _required_input("Named operator full name: ")).strip()
            if args.command == "create"
            else None
        )
        _confirm_identity(email)

        with SessionLocal() as db:
            auth = AuthService(db, User, settings)
            result = auth.provision_account_bootstrap(
                email=email,
                full_name=full_name,
                create=args.command == "create",
            )
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled; nothing was changed.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Bootstrap failed: {exc}", file=sys.stderr)
        return 1

    print("\nSecure bootstrap issued. Store these values separately and share them out-of-band.")
    print("They are shown once; the database stores only hashes where applicable.\n")
    print(f"Account:          {result['email']} ({result['full_name']})")
    print(f"Temporary password: {result['temporary_password']}")
    print(f"Enrollment token:   {result['enrollment_token']}")
    print(f"Token expires:      {result['enrollment_expires_at'].isoformat()}")
    print("\nRequired flow: login -> replace temporary password -> login again -> enroll 2FA.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
