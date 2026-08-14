from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def isolated_db():
    """Give the destructive-script test a database no other test can see."""
    from app.core.database import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    local_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = local_session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _create_fixture(db):
    from app.core.kernel.models.user import (
        RefreshToken,
        StepUpGrant,
        TwoFactorRecoveryCode,
        User,
    )
    from app.core.kernel.security import get_password_hash
    from app.modules.core.models import (
        Branch,
        PinCredential,
        UserBranchMembership,
        UserPermission,
    )
    from app.modules.hr.models import Employee
    from scripts.archive_experimental_accounts import EXPECTED_BRANCH_NAME

    db.query(Branch).update({Branch.is_active: False}, synchronize_session=False)
    branch = Branch(
        name=EXPECTED_BRANCH_NAME,
        name_ar="منتجع الخيمة بيتش",
        code=f"ARC-{uuid.uuid4().hex[:8].upper()}",
        is_active=True,
    )
    actor = User(
        id=1,
        email=f"retained-admin-{uuid.uuid4().hex}@test.local",
        password_hash=get_password_hash("Admin@12345"),
        full_name="Retained Admin",
        role="super_admin",
        is_active=True,
    )
    owner = User(
        email=f"retained-owner-{uuid.uuid4().hex}@test.local",
        password_hash=get_password_hash("Owner@12345"),
        full_name="Retained Owner",
        role="owner",
        is_active=True,
    )
    timeshare = User(
        email=f"retained-timeshare-{uuid.uuid4().hex}@test.local",
        password_hash=get_password_hash("Timeshare@12345"),
        full_name="Retained Timeshare",
        role="timeshare_admin",
        is_active=True,
    )
    cashier = User(
        email=f"target-cashier-{uuid.uuid4().hex}@test.local",
        password_hash=get_password_hash("Cashier@12345"),
        full_name="Experimental Cashier",
        phone="01000000000",
        role="cashier",
        is_active=True,
        two_factor_enabled=True,
        two_factor_secret="fixture-secret",
    )
    accountant = User(
        email=f"target-accountant-{uuid.uuid4().hex}@test.local",
        password_hash=get_password_hash("Accountant@12345"),
        full_name="Experimental Accountant",
        role="accountant",
        is_active=False,
    )
    db.add_all([branch, actor, owner, timeshare, cashier, accountant])
    db.flush()

    for user in (actor, owner, timeshare, cashier, accountant):
        db.add(UserBranchMembership(
            user_id=user.id,
            branch_id=branch.id,
            is_default=True,
            is_active=True,
            created_by=actor.id,
        ))

    employee = Employee(
        branch_id=branch.id,
        employee_code=f"ARC-{uuid.uuid4().hex[:8].upper()}",
        full_name=cashier.full_name,
        position="Cashier",
        basic_salary=Decimal(5000),
        hire_date=datetime.now(timezone.utc).date(),
        user_id=cashier.id,
    )
    expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    db.add_all([
        employee,
        RefreshToken(
            user_id=cashier.id,
            token_hash=uuid.uuid4().hex,
            expires_at=expiry.replace(tzinfo=None),
            family_id=uuid.uuid4().hex,
            family_public_id=uuid.uuid4().hex[:16],
        ),
        TwoFactorRecoveryCode(
            user_id=cashier.id,
            code_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        ),
        StepUpGrant(
            public_reference=uuid.uuid4().hex[:16],
            user_id=cashier.id,
            purpose="fixture",
            scope_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            access_token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            assurance_method="password",
            expires_at=expiry,
        ),
        UserPermission(
            user_id=cashier.id,
            resource="timeshare.installments",
            action="collect",
            allowed=True,
            branch_id=branch.id,
            granted_by=actor.id,
        ),
        PinCredential(
            user_id=cashier.id,
            pin_hash="fixture-pin-hash",
            created_by=actor.id,
        ),
    ])
    db.commit()
    return branch, actor, owner, timeshare, cashier, accountant, employee


def test_archive_is_dry_run_by_default_then_anonymizes_and_revokes(isolated_db):
    from app.core.kernel.models.user import RefreshToken, User
    from app.modules.core.models import (
        AuditLog,
        PinCredential,
        UserBranchMembership,
        UserPermission,
    )
    from scripts.archive_experimental_accounts import archive_experimental_accounts

    db = isolated_db
    branch, actor, owner, timeshare, cashier, accountant, employee = _create_fixture(db)
    retain = [actor.email.upper(), owner.email, timeshare.email]

    try:
        archive_experimental_accounts(
            db,
            retain_emails=retain,
            actor_email=actor.email,
            expected_target_count=3,
            apply=True,
            reason="Reviewed experimental account cleanup",
        )
    except ValueError as exc:
        assert "Target-count guard failed" in str(exc)
    else:
        raise AssertionError("Expected the target-count guard to fail")
    db.rollback()
    db.expire_all()
    assert db.query(User).filter(User.id == cashier.id).one().deleted_at is None

    dry_run = archive_experimental_accounts(
        db,
        retain_emails=retain,
        actor_email=actor.email,
        expected_target_count=2,
        apply=False,
        reason=None,
    )
    assert dry_run.applied is False
    assert dry_run.target_user_ids == [cashier.id, accountant.id]
    db.expire_all()
    assert db.query(User).filter(User.id == cashier.id).one().deleted_at is None
    assert db.query(RefreshToken).filter_by(user_id=cashier.id).count() == 1

    applied = archive_experimental_accounts(
        db,
        retain_emails=retain,
        actor_email=actor.email,
        expected_target_count=2,
        apply=True,
        reason="Remove reviewed experimental login identities",
    )
    assert applied.applied is True
    db.expire_all()

    for target_id in (cashier.id, accountant.id):
        target = db.query(User).filter(User.id == target_id).one()
        assert target.is_active is False
        assert target.deleted_at is not None
        assert target.email.startswith(f"archived-user-{target_id}-")
        assert target.email.endswith("@invalid.local")
        assert target.full_name == f"Archived experimental account #{target_id}"
        assert target.two_factor_enabled is False
        membership = db.query(UserBranchMembership).filter_by(
            user_id=target_id,
            branch_id=branch.id,
        ).one()
        assert membership.is_active is False
        assert membership.is_default is False
        assert membership.revoked_by == actor.id

    db.expire(employee)
    assert employee.user_id is None
    assert db.query(RefreshToken).filter_by(user_id=cashier.id).count() == 0
    assert db.query(UserPermission).filter_by(user_id=cashier.id).count() == 0
    assert db.query(PinCredential).filter_by(user_id=cashier.id).count() == 0
    audit = db.query(AuditLog).filter_by(
        action="experimental_accounts_archived",
        entity_id=branch.id,
    ).one()
    assert audit.user_id == actor.id
    assert "target-cashier" not in (audit.new_data or "")

    for retained_id in (actor.id, owner.id, timeshare.id):
        retained = db.query(User).filter(User.id == retained_id).one()
        assert retained.is_active is True
        assert retained.deleted_at is None
