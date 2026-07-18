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
import sys

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.kernel.auth.service import AuthService
from app.core.kernel.models.user import User


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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
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
