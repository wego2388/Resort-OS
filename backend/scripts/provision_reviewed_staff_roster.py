#!/usr/bin/env python3
"""Provision a reviewed single-branch staff roster with one-time credentials.

The roster is supplied as runtime JSON and is never committed with this tool.
Dry-run is the default. Apply is guarded by exact expected counts and writes
bootstrap credentials once to an exclusive mode-0600 file; secrets are never
printed or written to AuditLog.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.kernel.auth.service import STAFF_PROVISIONABLE_ROLES, AuthService
from app.core.kernel.models.user import (
    RefreshToken,
    StepUpGrant,
    TwoFactorRecoveryCode,
    User,
)
from app.core.kernel.security import get_password_hash, validate_email_format
from app.modules.core.models import (
    AuditLog,
    Branch,
    PinCredential,
    UserBranchMembership,
    UserPermission,
)
from app.modules.hr.models import Employee

EXPECTED_BRANCH_NAME = "El Kheima Beach Resort"
MANDATORY_2FA_ROLES = frozenset({"super_admin", "accountant", "owner"})


@dataclass(frozen=True)
class ProvisionReport:
    branch_id: int
    entry_count: int
    new_account_count: int
    restored_account_count: int
    new_employee_count: int
    reused_employee_count: int
    account_user_ids: list[int]
    applied: bool


@dataclass(frozen=True)
class PreparedEntry:
    full_name: str
    email: str
    role: str
    preferred_language: str
    phone: str | None
    restore_user_id: int | None
    employee_mode: str
    existing_employee_id: int | None
    employee_code: str | None
    position: str | None
    department: str | None
    hire_date: date | None
    basic_salary: Decimal | None
    insurance_base_salary: Decimal | None
    national_id: str | None


def _canonical_email(value: Any) -> str:
    email = str(value or "").strip().casefold()
    if not validate_email_format(email):
        raise ValueError("Every roster entry requires a valid email address")
    return email


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _positive_int(value: Any, label: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return parsed


def _money(value: Any, label: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a valid amount") from exc
    if amount < 0:
        raise ValueError(f"{label} cannot be negative")
    return amount.quantize(Decimal("0.01"))


def _prepare_entry(raw: dict[str, Any]) -> PreparedEntry:
    full_name = str(raw.get("full_name") or "").strip()
    if len(full_name) < 3:
        raise ValueError("Every roster entry requires a full name")
    email = _canonical_email(raw.get("email"))
    role = str(raw.get("role") or "").strip()
    if role not in STAFF_PROVISIONABLE_ROLES:
        raise ValueError(f"Unsupported roster role for {email}")
    language = str(raw.get("preferred_language") or "ar").strip()
    if language not in {"ar", "en"}:
        raise ValueError(f"Unsupported language for {email}")

    restore_user_id = raw.get("restore_user_id")
    if restore_user_id is not None:
        restore_user_id = _positive_int(restore_user_id, "restore_user_id")

    employee = raw.get("employee")
    if not isinstance(employee, dict):
        raise TypeError(f"Employee plan is required for {email}")
    mode = str(employee.get("mode") or "").strip()
    if mode not in {"create", "existing"}:
        raise ValueError(f"Employee mode must be create or existing for {email}")

    if mode == "existing":
        existing_id = _positive_int(employee.get("employee_id"), "employee_id")
        employee_code = None
        position = _optional_text(employee.get("position"))
        department = _optional_text(employee.get("department"))
        hire_date_raw = employee.get("hire_date")
        try:
            hire_date = (
                date.fromisoformat(str(hire_date_raw))
                if hire_date_raw not in (None, "") else None
            )
        except ValueError as exc:
            raise ValueError(f"hire_date must use YYYY-MM-DD for {email}") from exc
        salary_raw = employee.get("basic_salary")
        basic_salary = (
            _money(salary_raw, "basic_salary")
            if salary_raw not in (None, "") else None
        )
        insurance_raw = employee.get("insurance_base_salary")
        insurance_base_salary = (
            _money(insurance_raw, "insurance_base_salary")
            if insurance_raw not in (None, "") else None
        )
        national_id = _optional_text(employee.get("national_id"))
    else:
        existing_id = None
        employee_code = str(employee.get("employee_code") or "").strip()
        position = str(employee.get("position") or "").strip()
        department = _optional_text(employee.get("department"))
        if not employee_code or not position:
            raise ValueError(f"Employee code and position are required for {email}")
        try:
            hire_date = date.fromisoformat(str(employee.get("hire_date") or ""))
        except ValueError as exc:
            raise ValueError(f"hire_date must use YYYY-MM-DD for {email}") from exc
        basic_salary = _money(employee.get("basic_salary"), "basic_salary")
        insurance_raw = employee.get("insurance_base_salary")
        insurance_base_salary = (
            _money(insurance_raw, "insurance_base_salary")
            if insurance_raw not in (None, "") else None
        )
        national_id = _optional_text(employee.get("national_id"))

    return PreparedEntry(
        full_name=full_name,
        email=email,
        role=role,
        preferred_language=language,
        phone=_optional_text(raw.get("phone")),
        restore_user_id=restore_user_id,
        employee_mode=mode,
        existing_employee_id=existing_id,
        employee_code=employee_code,
        position=position,
        department=department,
        hire_date=hire_date,
        basic_salary=basic_salary,
        insurance_base_salary=insurance_base_salary,
        national_id=national_id,
    )


def load_roster(path: Path) -> list[PreparedEntry]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_entries = payload.get("entries") if isinstance(payload, dict) else None
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError("Roster JSON must contain a non-empty entries list")
    entries = [_prepare_entry(raw) for raw in raw_entries]
    emails = [entry.email for entry in entries]
    if len(emails) != len(set(emails)):
        raise ValueError("Roster emails must be unique")
    restore_ids = [entry.restore_user_id for entry in entries if entry.restore_user_id]
    if len(restore_ids) != len(set(restore_ids)):
        raise ValueError("restore_user_id values must be unique")
    employee_ids = [
        entry.existing_employee_id for entry in entries if entry.existing_employee_id
    ]
    if len(employee_ids) != len(set(employee_ids)):
        raise ValueError("Existing employee IDs must be unique")
    codes = [entry.employee_code for entry in entries if entry.employee_code]
    if len(codes) != len(set(codes)):
        raise ValueError("New employee codes must be unique")
    return entries


def _token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _write_credentials(path: Path, credentials: list[dict[str, Any]]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                {"generated_at": datetime.now(timezone.utc).isoformat(), "accounts": credentials},
                handle,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
    except Exception:
        path.unlink(missing_ok=True)
        raise


def provision_roster(
    db: Session,
    *,
    entries: list[PreparedEntry],
    actor_email: str,
    expected_entry_count: int,
    expected_new_account_count: int,
    expected_restored_account_count: int,
    apply: bool,
    reason: str | None,
    commit: bool = True,
) -> tuple[ProvisionReport, list[dict[str, Any]]]:
    if len(entries) != expected_entry_count:
        raise ValueError(
            f"Entry-count guard failed: expected {expected_entry_count}, found {len(entries)}"
        )
    restored_count = sum(entry.restore_user_id is not None for entry in entries)
    new_count = len(entries) - restored_count
    if new_count != expected_new_account_count:
        raise ValueError(
            f"New-account guard failed: expected {expected_new_account_count}, found {new_count}"
        )
    if restored_count != expected_restored_account_count:
        raise ValueError(
            "Restored-account guard failed: "
            f"expected {expected_restored_account_count}, found {restored_count}"
        )
    if apply and (reason is None or len(reason.strip()) < 10):
        raise ValueError("A meaningful reason of at least 10 characters is required")

    branches = (
        db.query(Branch)
        .filter(Branch.is_active.is_(True))
        .order_by(Branch.id)
        .with_for_update()
        .all()
    )
    if len(branches) != 1 or branches[0].name.strip() != EXPECTED_BRANCH_NAME:
        raise ValueError("Expected the one active El Kheima Beach Resort branch")
    branch = branches[0]

    actor = (
        db.query(User)
        .filter(
            func.lower(User.email) == _canonical_email(actor_email),
            User.role == "super_admin",
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
        .with_for_update()
        .first()
    )
    if actor is None:
        raise ValueError("The audit actor must be an active super-admin")
    actor_membership = db.query(UserBranchMembership).filter(
        UserBranchMembership.user_id == actor.id,
        UserBranchMembership.branch_id == branch.id,
        UserBranchMembership.is_active.is_(True),
    ).first()
    if actor_membership is None:
        raise ValueError("The audit actor must belong to the operating branch")

    existing_emails = {
        email
        for (email,) in db.query(func.lower(User.email)).filter(
            func.lower(User.email).in_([entry.email for entry in entries])
        ).all()
    }
    if existing_emails:
        raise ValueError(f"{len(existing_emails)} roster email(s) already have an account")

    restored_users: dict[int, User] = {}
    restore_ids = [entry.restore_user_id for entry in entries if entry.restore_user_id]
    if restore_ids:
        restored_users = {
            user.id: user
            for user in db.query(User)
            .filter(User.id.in_(restore_ids))
            .order_by(User.id)
            .with_for_update()
            .all()
        }
    if set(restored_users) != set(restore_ids):
        raise ValueError("A requested archived account ID was not found")
    for entry in entries:
        if entry.restore_user_id is None:
            continue
        user = restored_users[entry.restore_user_id]
        if user.deleted_at is None or user.is_active:
            raise ValueError("A requested restore account is not archived")
        if user.role != entry.role:
            raise ValueError("A requested restore account has a different preserved role")

    existing_employee_ids = [
        entry.existing_employee_id for entry in entries if entry.existing_employee_id
    ]
    existing_employees = {
        employee.id: employee
        for employee in (
            db.query(Employee)
            .filter(Employee.id.in_(existing_employee_ids))
            .order_by(Employee.id)
            .with_for_update()
            .all()
            if existing_employee_ids else []
        )
    }
    if set(existing_employees) != set(existing_employee_ids):
        raise ValueError("A requested existing employee ID was not found")
    for entry in entries:
        if entry.existing_employee_id is None:
            continue
        employee = existing_employees[entry.existing_employee_id]
        if employee.branch_id != branch.id or employee.status == "terminated":
            raise ValueError("An existing employee is not active in the operating branch")
        if employee.user_id is not None:
            raise ValueError("An existing employee is already linked to an account")
        if (employee.email or "").strip().casefold() != entry.email:
            raise ValueError("An existing employee email does not match the reviewed roster")

    new_codes = [entry.employee_code for entry in entries if entry.employee_code]
    conflicting_codes = db.query(Employee.id).filter(Employee.employee_code.in_(new_codes)).count()
    if conflicting_codes:
        raise ValueError(f"{conflicting_codes} new employee code(s) already exist")

    report = ProvisionReport(
        branch_id=branch.id,
        entry_count=len(entries),
        new_account_count=new_count,
        restored_account_count=restored_count,
        new_employee_count=sum(entry.employee_mode == "create" for entry in entries),
        reused_employee_count=sum(entry.employee_mode == "existing" for entry in entries),
        account_user_ids=[],
        applied=apply,
    )
    if not apply:
        db.rollback()
        return report, []

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.TWO_FACTOR_ENROLLMENT_TOKEN_TTL_MINUTES)
    credentials: list[dict[str, Any]] = []
    account_ids: list[int] = []
    for entry in entries:
        if entry.employee_mode == "existing":
            employee = existing_employees[entry.existing_employee_id]
            employee.full_name = entry.full_name
            employee.email = entry.email
            employee.phone = entry.phone or employee.phone
            employee.position = entry.position or employee.position
            employee.department = entry.department or employee.department
            employee.hire_date = entry.hire_date or employee.hire_date
            if entry.basic_salary is not None:
                employee.basic_salary = entry.basic_salary
            if entry.insurance_base_salary is not None:
                employee.insurance_base_salary = entry.insurance_base_salary
            if entry.national_id is not None:
                employee.national_id = entry.national_id
        else:
            employee = Employee(
                branch_id=branch.id,
                employee_code=entry.employee_code,
                full_name=entry.full_name,
                national_id=entry.national_id,
                position=entry.position,
                department=entry.department,
                basic_salary=entry.basic_salary,
                insurance_base_salary=entry.insurance_base_salary,
                hire_date=entry.hire_date,
                status="active",
                phone=entry.phone,
                email=entry.email,
            )
            db.add(employee)
            db.flush()

        temporary_password = AuthService._new_temporary_password()
        enrollment_token = secrets.token_urlsafe(32)
        requires_2fa = entry.role in MANDATORY_2FA_ROLES
        if entry.restore_user_id is not None:
            user = restored_users[entry.restore_user_id]
            user.email = entry.email
            user.full_name = entry.full_name
            user.phone = entry.phone
            user.is_active = True
            user.deleted_at = None
            user.preferred_language = entry.preferred_language
            user.password_hash = get_password_hash(temporary_password)
            user.must_change_password = True
            user.failed_login_attempts = 0
            user.account_locked_until = None
            user.two_factor_enabled = False
            user.two_factor_secret = None
            user.two_factor_last_used_step = None
            user.two_factor_bootstrap_required = requires_2fa
            user.two_factor_enrollment_token_hash = (
                _token_hash(enrollment_token) if requires_2fa else None
            )
            user.two_factor_enrollment_expires_at = expires_at if requires_2fa else None
            db.query(RefreshToken).filter(RefreshToken.user_id == user.id).delete(
                synchronize_session=False
            )
            db.query(TwoFactorRecoveryCode).filter(
                TwoFactorRecoveryCode.user_id == user.id
            ).delete(synchronize_session=False)
            db.query(StepUpGrant).filter(StepUpGrant.user_id == user.id).delete(
                synchronize_session=False
            )
            db.query(UserPermission).filter(UserPermission.user_id == user.id).delete(
                synchronize_session=False
            )
            db.query(PinCredential).filter(PinCredential.user_id == user.id).delete(
                synchronize_session=False
            )
            membership = db.query(UserBranchMembership).filter(
                UserBranchMembership.user_id == user.id,
                UserBranchMembership.branch_id == branch.id,
            ).with_for_update().one_or_none()
            if membership is None:
                membership = UserBranchMembership(
                    user_id=user.id,
                    branch_id=branch.id,
                    created_by=actor.id,
                )
                db.add(membership)
            membership.is_active = True
            membership.is_default = True
            membership.revoked_at = None
            membership.revoked_by = None
            action = "reviewed_staff_account_restored"
        else:
            user = User(
                email=entry.email,
                password_hash=get_password_hash(temporary_password),
                full_name=entry.full_name,
                phone=entry.phone,
                role=entry.role,
                is_active=True,
                preferred_language=entry.preferred_language,
                must_change_password=True,
                two_factor_enabled=False,
                two_factor_bootstrap_required=requires_2fa,
                two_factor_enrollment_token_hash=(
                    _token_hash(enrollment_token) if requires_2fa else None
                ),
                two_factor_enrollment_expires_at=expires_at if requires_2fa else None,
            )
            db.add(user)
            db.flush()
            db.add(UserBranchMembership(
                user_id=user.id,
                branch_id=branch.id,
                is_default=True,
                is_active=True,
                created_by=actor.id,
            ))
            action = "reviewed_staff_account_provisioned"

        employee.user_id = user.id
        account_ids.append(user.id)
        db.add(AuditLog(
            user_id=actor.id,
            branch_id=branch.id,
            action=action,
            entity_type="user",
            entity_id=user.id,
            old_data=None,
            new_data=json.dumps({
                "employee_id": employee.id,
                "employee_code": employee.employee_code,
                "role": entry.role,
                "reason": reason.strip(),
                "requires_password_change": True,
                "requires_2fa_bootstrap": requires_2fa,
            }, ensure_ascii=False, sort_keys=True),
        ))
        credentials.append({
            "full_name": entry.full_name,
            "email": entry.email,
            "role": entry.role,
            "temporary_password": temporary_password,
            "enrollment_token": enrollment_token if requires_2fa else None,
            "enrollment_expires_at": expires_at.isoformat() if requires_2fa else None,
        })

    if commit:
        db.commit()
    else:
        db.flush()
    report = ProvisionReport(**{**asdict(report), "account_user_ids": account_ids})
    return report, credentials


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roster", type=Path, required=True)
    parser.add_argument("--actor-email", required=True)
    parser.add_argument("--expected-entry-count", type=int, required=True)
    parser.add_argument("--expected-new-account-count", type=int, required=True)
    parser.add_argument("--expected-restored-account-count", type=int, required=True)
    parser.add_argument("--reason")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm")
    parser.add_argument("--credentials-output", type=Path)
    args = parser.parse_args()

    confirmation = f"PROVISION-{args.expected_entry_count}-REVIEWED-STAFF"
    if args.apply and args.confirm != confirmation:
        print(f"ERROR: --confirm must equal {confirmation}", file=sys.stderr)
        return 1
    if args.apply and args.credentials_output is None:
        print("ERROR: --credentials-output is required with --apply", file=sys.stderr)
        return 1

    try:
        entries = load_roster(args.roster)
        with SessionLocal() as db:
            report, credentials = provision_roster(
                db,
                entries=entries,
                actor_email=args.actor_email,
                expected_entry_count=args.expected_entry_count,
                expected_new_account_count=args.expected_new_account_count,
                expected_restored_account_count=args.expected_restored_account_count,
                apply=args.apply,
                reason=args.reason,
                commit=not args.apply,
            )
            if args.apply:
                try:
                    _write_credentials(args.credentials_output, credentials)
                    db.commit()
                except Exception:
                    db.rollback()
                    args.credentials_output.unlink(missing_ok=True)
                    raise
                from app.core.deps import revoke_user_tokens

                for entry in entries:
                    if entry.restore_user_id is not None:
                        revoke_user_tokens(entry.restore_user_id)
    except Exception as exc:  # noqa: BLE001 - production CLI must fail closed
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(asdict(report), indent=2, sort_keys=True))
    if args.apply:
        print("APPLIED: one-time credentials written to the protected output file")
    else:
        print("DRY RUN ONLY: no rows were changed and no credentials were generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
