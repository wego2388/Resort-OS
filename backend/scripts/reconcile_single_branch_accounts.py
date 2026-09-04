#!/usr/bin/env python3
"""Audit and reconcile operational identities for the single resort branch.

Dry-run is the default.  The command never guesses HR links from names or
emails and never deletes users.  Any HR repair must be supplied explicitly as
``--link USER_ID:EMPLOYEE_ID`` after the printed IDs have been reviewed.

Examples:
    python scripts/reconcile_single_branch_accounts.py
    python scripts/reconcile_single_branch_accounts.py --link 12:44
    python scripts/reconcile_single_branch_accounts.py --apply \
        --actor-user-id 1 --link 12:44 --link 13:45
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.kernel.models.user import User
from app.modules.core.models import AuditLog, Branch, UserBranchMembership
from app.modules.hr.models import Employee


EXPECTED_BRANCH_NAME = "El Kheima Beach Resort"
OPERATIONAL_ROLES = frozenset({
    "super_admin", "owner", "admin", "accountant", "hr_manager", "manager",
    "supervisor", "receptionist", "cashier", "waiter", "chef", "kitchen",
    "timeshare_admin", "timeshare_agent", "employee",
})
HR_LINK_REQUIRED_ROLES = OPERATIONAL_ROLES - {"super_admin", "owner"}


@dataclass(frozen=True)
class ReconciliationReport:
    branch_id: int
    active_operational_user_ids: list[int]
    membership_create_user_ids: list[int]
    membership_reactivate_user_ids: list[int]
    membership_default_user_ids: list[int]
    requested_hr_links: dict[int, int]
    unlinked_staff_user_ids_after_plan: list[int]
    applied: bool


def parse_link(value: str) -> tuple[int, int]:
    try:
        user_text, employee_text = value.split(":", 1)
        user_id, employee_id = int(user_text), int(employee_text)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("--link must use USER_ID:EMPLOYEE_ID") from exc
    if user_id <= 0 or employee_id <= 0:
        raise argparse.ArgumentTypeError("--link IDs must be positive integers")
    return user_id, employee_id


def _validated_link_map(values: list[tuple[int, int]]) -> dict[int, int]:
    links: dict[int, int] = {}
    employee_ids: set[int] = set()
    for user_id, employee_id in values:
        if user_id in links:
            raise ValueError(f"Duplicate user ID in --link: {user_id}")
        if employee_id in employee_ids:
            raise ValueError(f"Duplicate employee ID in --link: {employee_id}")
        links[user_id] = employee_id
        employee_ids.add(employee_id)
    return links


def reconcile(
    db: Session,
    *,
    links: dict[int, int],
    apply: bool,
    actor_user_id: int | None,
) -> ReconciliationReport:
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
    branch_id = branch.id

    actor: User | None = None
    if apply:
        if actor_user_id is None:
            raise ValueError("--actor-user-id is required with --apply")
        actor = (
            db.query(User)
            .filter(
                User.id == actor_user_id,
                User.role == "super_admin",
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
            .with_for_update()
            .first()
        )
        if actor is None:
            raise ValueError("The audit actor must be an active super-admin")

    users = (
        db.query(User)
        .filter(
            User.is_active.is_(True),
            User.deleted_at.is_(None),
            User.role.in_(OPERATIONAL_ROLES),
        )
        .order_by(User.id)
        .with_for_update()
        .all()
    )
    users_by_id = {user.id: user for user in users}
    memberships = {
        membership.user_id: membership
        for membership in db.query(UserBranchMembership)
        .filter(
            UserBranchMembership.user_id.in_(list(users_by_id)),
            UserBranchMembership.branch_id == branch_id,
        )
        .with_for_update()
        .all()
    }

    create_ids: list[int] = []
    reactivate_ids: list[int] = []
    default_ids: list[int] = []
    for user in users:
        membership = memberships.get(user.id)
        if membership is None:
            create_ids.append(user.id)
        else:
            if not membership.is_active:
                reactivate_ids.append(user.id)
            if not membership.is_default:
                default_ids.append(user.id)

    requested_employees: dict[int, Employee] = {}
    for user_id, employee_id in sorted(links.items()):
        user = users_by_id.get(user_id)
        if user is None or user.role not in HR_LINK_REQUIRED_ROLES:
            raise ValueError(f"User ID {user_id} is not an active operational staff account")
        employee = (
            db.query(Employee)
            .filter(Employee.id == employee_id)
            .with_for_update()
            .first()
        )
        if employee is None:
            raise ValueError(f"Employee ID {employee_id} does not exist")
        if employee.branch_id != branch.id:
            raise ValueError(f"Employee ID {employee_id} is outside the operating branch")
        if employee.status == "terminated":
            raise ValueError(f"Employee ID {employee_id} is terminated")
        if employee.user_id not in {None, user_id}:
            raise ValueError(f"Employee ID {employee_id} is already linked to another user")
        existing_employee = (
            db.query(Employee.id)
            .filter(Employee.user_id == user_id, Employee.id != employee_id)
            .first()
        )
        if existing_employee is not None:
            raise ValueError(f"User ID {user_id} is already linked to another employee")
        requested_employees[user_id] = employee

    currently_linked = {
        row.user_id
        for row in db.query(Employee.user_id)
        .filter(Employee.user_id.in_(users_by_id))
        .all()
        if row.user_id is not None
    }
    unlinked_after = sorted(
        user.id
        for user in users
        if user.role in HR_LINK_REQUIRED_ROLES
        and user.id not in currently_linked
        and user.id not in links
    )

    if apply:
        assert actor is not None
        for user in users:
            other_defaults = (
                db.query(UserBranchMembership)
                .filter(
                    UserBranchMembership.user_id == user.id,
                    UserBranchMembership.branch_id != branch.id,
                    UserBranchMembership.is_default.is_(True),
                )
                .with_for_update()
                .all()
            )
            for other in other_defaults:
                other.is_default = False

            membership = memberships.get(user.id)
            if membership is None:
                membership = UserBranchMembership(
                    user_id=user.id,
                    branch_id=branch.id,
                    is_default=True,
                    is_active=True,
                    created_by=actor.id,
                )
                db.add(membership)
            else:
                membership.is_active = True
                membership.is_default = True
                membership.revoked_at = None
                membership.revoked_by = None

        for user_id, employee in requested_employees.items():
            employee.user_id = user_id

        if create_ids or reactivate_ids or default_ids or links:
            db.add(AuditLog(
                user_id=actor.id,
                branch_id=branch.id,
                action="single_branch_accounts_reconciled",
                entity_type="branch",
                entity_id=branch.id,
                old_data=None,
                new_data=json.dumps({
                    "membership_created_user_ids": create_ids,
                    "membership_reactivated_user_ids": reactivate_ids,
                    "membership_defaulted_user_ids": default_ids,
                    "hr_links": links,
                    "unlinked_staff_user_ids_after_apply": unlinked_after,
                }, sort_keys=True),
            ))
        db.commit()
    else:
        db.rollback()

    return ReconciliationReport(
        branch_id=branch_id,
        active_operational_user_ids=sorted(users_by_id),
        membership_create_user_ids=create_ids,
        membership_reactivate_user_ids=reactivate_ids,
        membership_default_user_ids=default_ids,
        requested_hr_links=links,
        unlinked_staff_user_ids_after_plan=unlinked_after,
        applied=apply,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--link", action="append", type=parse_link, default=[])
    parser.add_argument("--apply", action="store_true", help="Commit the reviewed plan")
    parser.add_argument("--actor-user-id", type=int, default=None)
    args = parser.parse_args()

    try:
        links = _validated_link_map(args.link)
        with SessionLocal() as db:
            report = reconcile(
                db,
                links=links,
                apply=args.apply,
                actor_user_id=args.actor_user_id,
            )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(asdict(report), indent=2, sort_keys=True))
    if not args.apply:
        print("DRY RUN ONLY: no rows were changed")
    elif report.unlinked_staff_user_ids_after_plan:
        print("APPLIED, but explicit HR links are still required for the listed user IDs")
    else:
        print("APPLIED: single-branch membership and reviewed HR links are consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
