from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_disable_legacy_demo_accounts_after_named_super_admin_is_ready(db):
    from app.admin_bootstrap import disable_legacy_demo_accounts
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    from app.modules.core.models import AuditLog

    named = User(
        email=f"named-{uuid.uuid4().hex}@example.com",
        password_hash=get_password_hash("Named@12345"),
        full_name="Named Production Admin",
        role="super_admin",
        is_active=True,
        two_factor_enabled=True,
        must_change_password=False,
        two_factor_bootstrap_required=False,
    )
    demos = []
    for email, full_name, role in (
        ("admin@resortos.local", "Legacy Demo Admin", "super_admin"),
        ("housekeeper@resortos.local", "Synthetic HR Employee", "employee"),
    ):
        demo = db.query(User).filter(User.email == email).first()
        if demo is None:
            demo = User(
                email=email,
                password_hash=get_password_hash("Admin@123456"),
                full_name=full_name,
                role=role,
                is_active=True,
            )
            db.add(demo)
        else:
            demo.is_active = True
        demos.append(demo)
    db.add(named)
    db.flush()
    enabled_at = datetime.utcnow() - timedelta(seconds=2)
    db.add_all([
        AuditLog(
            user_id=named.id,
            action="two_factor_enabled",
            entity_type="user_authentication",
            entity_id=named.id,
            new_data='{"recovery_code_count": 8}',
            created_at=enabled_at,
        ),
        AuditLog(
            user_id=named.id,
            action="login_succeeded",
            entity_type="user_authentication",
            entity_id=named.id,
            new_data='{"assurance": "2fa"}',
            created_at=enabled_at + timedelta(seconds=1),
        ),
    ])
    db.commit()

    disabled = disable_legacy_demo_accounts(db)

    for demo in demos:
        db.refresh(demo)
        assert demo.is_active is False
    assert disabled >= 1
    audit = db.query(AuditLog).filter(
        AuditLog.action == "legacy_demo_accounts_disabled",
    ).order_by(AuditLog.id.desc()).first()
    assert audit is not None
    assert "password" not in (audit.new_data or "").lower()


def test_first_branch_bootstrap_is_audited_and_idempotent():
    from app.admin_bootstrap import bootstrap_first_branch
    from app.core.kernel.models.user import RefreshToken, User
    from app.core.kernel.security import get_password_hash
    from app.modules.core.models import (
        AuditLog,
        Branch,
        UserBranchMembership,
    )

    engine = create_engine("sqlite://")
    for table in (
        User.__table__,
        Branch.__table__,
        RefreshToken.__table__,
        UserBranchMembership.__table__,
        AuditLog.__table__,
    ):
        table.create(engine)

    with Session(engine) as db:
        user = User(
            email="named.owner@example.com",
            password_hash=get_password_hash("Named@12345"),
            full_name="Named Owner",
            role="super_admin",
            is_active=True,
        )
        db.add(user)
        db.flush()
        session = RefreshToken(
            user_id=user.id,
            token_hash="a" * 64,
            expires_at=datetime.utcnow() + timedelta(days=1),
            family_id="b" * 32,
            family_public_id="c" * 32,
        )
        db.add(session)
        db.commit()

        first = bootstrap_first_branch(
            db,
            super_admin_email=user.email,
            code="WSR-001",
            name="El Kheima Beach",
            name_ar="الخيمة بيتش",
            timezone_name="Africa/Cairo",
        )
        second = bootstrap_first_branch(
            db,
            super_admin_email=user.email,
            code="WSR-001",
            name="El Kheima Beach",
            name_ar="الخيمة بيتش",
            timezone_name="Africa/Cairo",
        )

        assert first["created"] is True
        assert second["created"] is False
        assert db.query(Branch).count() == 1
        membership = db.query(UserBranchMembership).one()
        assert membership.user_id == user.id
        assert membership.branch_id == first["branch_id"]
        assert membership.is_active is True
        assert membership.is_default is True
        db.refresh(session)
        assert session.active_branch_id == first["branch_id"]
        assert db.query(AuditLog).filter(
            AuditLog.action == "first_branch_bootstrapped",
        ).count() == 1

        with pytest.raises(ValueError, match="conflicts"):
            bootstrap_first_branch(
                db,
                super_admin_email=user.email,
                code="WSR-001",
                name="Different name",
                name_ar="الخيمة بيتش",
                timezone_name="Africa/Cairo",
            )
