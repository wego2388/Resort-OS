from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal


def test_reconciliation_is_dry_run_by_default_and_applies_explicit_links(db):
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    from app.modules.core.models import AuditLog, Branch, UserBranchMembership
    from app.modules.hr.models import Employee
    from scripts.reconcile_single_branch_accounts import (
        EXPECTED_BRANCH_NAME,
        reconcile,
    )

    db.query(Branch).update({Branch.is_active: False}, synchronize_session=False)
    branch = Branch(
        name=EXPECTED_BRANCH_NAME,
        name_ar="منتجع الخيمة بيتش",
        code=f"ELK-{uuid.uuid4().hex[:8].upper()}",
        is_active=True,
    )
    user = User(
        email=f"reconcile-{uuid.uuid4().hex}@test.local",
        password_hash=get_password_hash("Test@12345"),
        full_name="Reconciliation Cashier",
        role="cashier",
        is_active=True,
    )
    employee = Employee(
        branch_id=0,  # assigned after branch flush
        employee_code=f"REC-{uuid.uuid4().hex[:8].upper()}",
        full_name=user.full_name,
        position="Cashier",
        basic_salary=Decimal("5000"),
        hire_date=date.today(),
    )
    db.add(branch)
    db.flush()
    employee.branch_id = branch.id
    db.add_all([user, employee])
    db.commit()

    dry_run = reconcile(
        db,
        links={user.id: employee.id},
        apply=False,
        actor_user_id=None,
    )
    assert dry_run.applied is False
    assert user.id in dry_run.membership_create_user_ids
    assert db.query(UserBranchMembership).filter_by(
        user_id=user.id,
        branch_id=branch.id,
    ).first() is None
    db.expire(employee)
    assert employee.user_id is None

    applied = reconcile(
        db,
        links={user.id: employee.id},
        apply=True,
        actor_user_id=1,
    )
    assert applied.applied is True
    membership = db.query(UserBranchMembership).filter_by(
        user_id=user.id,
        branch_id=branch.id,
    ).one()
    assert membership.is_active is True
    assert membership.is_default is True
    db.expire(employee)
    assert employee.user_id == user.id
    assert db.query(AuditLog).filter_by(
        action="single_branch_accounts_reconciled",
        entity_id=branch.id,
    ).one().user_id == 1
