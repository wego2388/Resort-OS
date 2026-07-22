from __future__ import annotations

import uuid
from datetime import datetime, timedelta


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
    demo = db.query(User).filter(User.email == "admin@resortos.local").first()
    if demo is None:
        demo = User(
            email="admin@resortos.local",
            password_hash=get_password_hash("Admin@123456"),
            full_name="Legacy Demo Admin",
            role="super_admin",
            is_active=True,
        )
        db.add(demo)
    else:
        demo.is_active = True
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

    db.refresh(demo)
    assert disabled >= 1
    assert demo.is_active is False
    audit = db.query(AuditLog).filter(
        AuditLog.action == "legacy_demo_accounts_disabled",
    ).order_by(AuditLog.id.desc()).first()
    assert audit is not None
    assert "password" not in (audit.new_data or "").lower()
