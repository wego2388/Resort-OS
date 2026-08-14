from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def isolated_db():
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


def test_reviewed_roster_dry_run_then_atomic_provision_and_restore(
    isolated_db, tmp_path,
):
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash, verify_password
    from app.modules.core.models import AuditLog, Branch, UserBranchMembership
    from app.modules.hr.models import Employee
    from scripts.provision_reviewed_staff_roster import (
        EXPECTED_BRANCH_NAME,
        _prepare_entry,
        _write_credentials,
        provision_roster,
    )

    db = isolated_db
    branch = Branch(
        name=EXPECTED_BRANCH_NAME,
        name_ar="منتجع الخيمة بيتش",
        code=f"PROV-{uuid.uuid4().hex[:8].upper()}",
        is_active=True,
    )
    actor = User(
        email=f"actor-{uuid.uuid4().hex}@test.local",
        password_hash=get_password_hash("Actor@12345"),
        full_name="Named Super Admin",
        role="super_admin",
        is_active=True,
    )
    archived = User(
        email=f"archived-{uuid.uuid4().hex}@invalid.local",
        password_hash=get_password_hash("Archived@12345"),
        full_name="Archived account",
        role="hr_manager",
        is_active=False,
        deleted_at=datetime.now(timezone.utc),
    )
    existing_employee = Employee(
        branch_id=0,
        employee_code=f"ACC-{uuid.uuid4().hex[:6].upper()}",
        full_name="Existing Accountant",
        email=f"existing-{uuid.uuid4().hex}@test.local",
        position="Accountant",
        department="Finance",
        basic_salary=Decimal(8000),
        hire_date=date(2026, 8, 14),
        status="active",
    )
    db.add_all([branch, actor, archived])
    db.flush()
    existing_employee.branch_id = branch.id
    db.add(existing_employee)
    db.add_all([
        UserBranchMembership(
            user_id=actor.id,
            branch_id=branch.id,
            is_default=True,
            is_active=True,
            created_by=actor.id,
        ),
        UserBranchMembership(
            user_id=archived.id,
            branch_id=branch.id,
            is_default=False,
            is_active=False,
            created_by=actor.id,
            revoked_at=datetime.now(timezone.utc),
            revoked_by=actor.id,
        ),
    ])
    db.commit()

    new_email = f"new-{uuid.uuid4().hex}@test.local"
    entries = [
        _prepare_entry({
            "full_name": "New Cashier",
            "email": new_email,
            "role": "cashier",
            "employee": {
                "mode": "create",
                "employee_code": f"NEW-{uuid.uuid4().hex[:6].upper()}",
                "position": "Cashier",
                "department": "Finance",
                "hire_date": "2026-08-14",
                "basic_salary": "6000",
            },
        }),
        _prepare_entry({
            "full_name": "Restored HR Manager",
            "email": f"restored-{uuid.uuid4().hex}@test.local",
            "role": "hr_manager",
            "restore_user_id": archived.id,
            "employee": {
                "mode": "create",
                "employee_code": f"HR-{uuid.uuid4().hex[:6].upper()}",
                "position": "HR Manager",
                "department": "HR",
                "hire_date": "2026-08-14",
                "basic_salary": "9000",
            },
        }),
        _prepare_entry({
            "full_name": existing_employee.full_name,
            "email": existing_employee.email,
            "role": "accountant",
            "employee": {
                "mode": "existing",
                "employee_id": existing_employee.id,
                "position": "Chief Accountant",
                "department": "Accounting",
                "hire_date": "2026-08-14",
                "basic_salary": "8500",
            },
        }),
    ]

    dry_report, dry_credentials = provision_roster(
        db,
        entries=entries,
        actor_email=actor.email,
        expected_entry_count=3,
        expected_new_account_count=2,
        expected_restored_account_count=1,
        apply=False,
        reason=None,
    )
    assert dry_report.applied is False
    assert dry_credentials == []
    db.expire_all()
    assert db.query(User).filter(User.email == new_email).first() is None
    assert db.query(User).filter(User.id == archived.id).one().deleted_at is not None

    report, credentials = provision_roster(
        db,
        entries=entries,
        actor_email=actor.email,
        expected_entry_count=3,
        expected_new_account_count=2,
        expected_restored_account_count=1,
        apply=True,
        reason="Provision owner-reviewed production staff roster",
    )
    assert report.applied is True
    assert report.new_employee_count == 2
    assert report.reused_employee_count == 1
    assert len(credentials) == 3
    db.expire_all()

    restored = db.query(User).filter(User.id == archived.id).one()
    assert restored.email == entries[1].email
    assert restored.full_name == entries[1].full_name
    assert restored.is_active is True
    assert restored.deleted_at is None
    assert restored.must_change_password is True
    assert db.query(Employee).filter(Employee.user_id == restored.id).one()

    accountant = db.query(User).filter(User.email == existing_employee.email).one()
    accountant_credential = next(
        credential for credential in credentials if credential["role"] == "accountant"
    )
    assert verify_password(
        accountant_credential["temporary_password"], accountant.password_hash
    )
    assert accountant.two_factor_bootstrap_required is True
    assert accountant_credential["enrollment_token"] is not None
    assert existing_employee.user_id == accountant.id
    assert existing_employee.position == "Chief Accountant"
    assert existing_employee.department == "Accounting"
    assert existing_employee.basic_salary == Decimal(8500)

    cashier = db.query(User).filter(User.email == new_email).one()
    assert cashier.two_factor_bootstrap_required is False
    cashier_credential = next(
        credential for credential in credentials if credential["email"] == new_email
    )
    assert cashier_credential["enrollment_token"] is None
    assert db.query(UserBranchMembership).filter_by(
        user_id=cashier.id,
        branch_id=branch.id,
        is_active=True,
        is_default=True,
    ).one()

    audits = db.query(AuditLog).filter(
        AuditLog.action.in_({
            "reviewed_staff_account_provisioned",
            "reviewed_staff_account_restored",
        })
    ).all()
    assert len(audits) == 3
    audit_payload = "".join(audit.new_data or "" for audit in audits)
    assert all(
        credential["temporary_password"] not in audit_payload
        for credential in credentials
    )

    output = tmp_path / "credentials.json"
    _write_credentials(output, credentials)
    assert output.stat().st_mode & 0o777 == 0o600
    assert len(json.loads(output.read_text())["accounts"]) == 3
    with pytest.raises(FileExistsError):
        _write_credentials(output, credentials)
