"""tests/test_operational_history_seed.py — HIST-01 CLI mechanics (OPS-DATA-02 §9).

مفيش أي مولّد بيانات فعلي هنا لأن SCENARIO_MODULES لسه فاضية (راجع
operational_history_seed.py) — الاختبارات دي بتغطي هيكل الأداة نفسها بس:
dry-run/apply عبر commit/rollback، منع rerun، تصادم مع batch "running"،
وconfirmation phrase.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.operational_history_seed import (
    DATASET_VERSION, confirmation_phrase, run_seed, validate_only,
)


@pytest.fixture
def branch(db: Session):
    from app.modules.core.models import Branch
    b = Branch(name="Test HIST", name_ar="اختبار تاريخي",
               code=f"HIST-{uuid.uuid4().hex[:6].upper()}", is_active=True)
    db.add(b)
    db.commit()
    return b


@pytest.fixture
def actor(db: Session):
    from app.core.kernel.models.user import User, UserRole
    from app.core.kernel.security import get_password_hash
    user = User(
        email=f"hist-actor-{uuid.uuid4().hex[:6]}@test.invalid",
        password_hash=get_password_hash("isolated-test-credential"),
        full_name="HIST Test Actor",
        role=UserRole.SUPER_ADMIN,
        is_active=True,
        two_factor_enabled=True,
    )
    db.add(user)
    db.commit()
    return user


def _seed_required_accounts(db: Session, branch):
    from app.modules.finance.models import Account
    for code, acc_type in [
        ("1100", "asset"), ("2160", "liability"), ("2165", "liability"), ("4100", "revenue"),
    ]:
        db.add(Account(branch_id=branch.id, code=code, name=code, account_type=acc_type))
    db.commit()


class TestPreconditions:
    def test_missing_branch_raises(self, db: Session, actor):
        with pytest.raises(RuntimeError, match="not found"):
            run_seed(db, branch_code="NOPE-999", period="2026-07", actor_id=actor.id)

    def test_missing_accounts_raises(self, db: Session, branch, actor):
        with pytest.raises(RuntimeError, match="Preconditions failed"):
            run_seed(db, branch_code=branch.code, period="2026-07", actor_id=actor.id)

    def test_inactive_branch_raises(self, db: Session, branch, actor):
        branch.is_active = False
        db.commit()
        with pytest.raises(RuntimeError, match="not active"):
            run_seed(db, branch_code=branch.code, period="2026-07", actor_id=actor.id)

    def test_no_actor_resolvable_raises(self, db: Session, branch):
        _seed_required_accounts(db, branch)
        with pytest.raises(RuntimeError, match="super_admin"):
            run_seed(db, branch_code=branch.code, period="2026-07")

    def test_invalid_period_format_raises(self, db: Session, branch, actor):
        _seed_required_accounts(db, branch)
        with pytest.raises(RuntimeError, match="YYYY-MM"):
            run_seed(db, branch_code=branch.code, period="July-2026", actor_id=actor.id)


class TestRunSeedManifest:
    def test_dry_run_creates_no_persisted_batch_after_rollback(self, db: Session, branch, actor):
        from app.modules.core.models import ImportBatch
        _seed_required_accounts(db, branch)

        run_seed(db, branch_code=branch.code, period="2026-07", actor_id=actor.id)
        db.rollback()

        assert db.query(ImportBatch).filter(ImportBatch.branch_id == branch.id).count() == 0

    def test_apply_persists_completed_batch(self, db: Session, branch, actor):
        from app.modules.core.models import ImportBatch
        _seed_required_accounts(db, branch)

        result = run_seed(db, branch_code=branch.code, period="2026-07", actor_id=actor.id)
        db.commit()

        assert result.already_applied is False
        assert result.version == DATASET_VERSION
        batch = db.query(ImportBatch).filter(ImportBatch.branch_id == branch.id).one()
        assert batch.status == "completed"
        assert batch.completed_at is not None
        assert batch.checksum

    def test_rerun_after_completed_batch_is_idempotent(self, db: Session, branch, actor):
        from app.modules.core.models import ImportBatch
        _seed_required_accounts(db, branch)

        run_seed(db, branch_code=branch.code, period="2026-07", actor_id=actor.id)
        db.commit()

        second = run_seed(db, branch_code=branch.code, period="2026-07", actor_id=actor.id)
        db.commit()

        assert second.already_applied is True
        assert db.query(ImportBatch).filter(ImportBatch.branch_id == branch.id).count() == 1

    def test_running_batch_blocks_rerun_no_auto_resume(self, db: Session, branch, actor):
        """batch لسه status='running' (مثال: crash نص الطريق) لازم يرفض أي
        محاولة تانية بدل استئناف تلقائي غير آمن — راجع §9.1/§9.3."""
        from app.modules.core.models import ImportBatch
        from datetime import datetime, timezone
        _seed_required_accounts(db, branch)

        db.add(ImportBatch(
            branch_id=branch.id, dataset_version=DATASET_VERSION, period="2026-07",
            checksum="deadbeef", status="running", actor="crashed-run@test.invalid",
            started_at=datetime.now(timezone.utc),
        ))
        db.commit()

        with pytest.raises(RuntimeError, match="still 'running'"):
            run_seed(db, branch_code=branch.code, period="2026-07", actor_id=actor.id)

    def test_different_branches_are_independent(self, db: Session, branch, actor):
        from app.modules.core.models import Branch, ImportBatch
        _seed_required_accounts(db, branch)
        branch2 = Branch(name="Second", name_ar="ثاني", code=f"HIST2-{uuid.uuid4().hex[:6].upper()}", is_active=True)
        db.add(branch2)
        db.commit()
        _seed_required_accounts(db, branch2)

        run_seed(db, branch_code=branch.code, period="2026-07", actor_id=actor.id)
        db.commit()
        run_seed(db, branch_code=branch2.code, period="2026-07", actor_id=actor.id)
        db.commit()

        assert db.query(ImportBatch).filter(ImportBatch.branch_id.in_([branch.id, branch2.id])).count() == 2


class TestValidateOnly:
    def test_reports_not_applied_when_no_batch(self, db: Session, branch):
        report = validate_only(db, branch_code=branch.code, period="2026-07")
        assert report["applied"] is False

    def test_reports_applied_after_successful_run(self, db: Session, branch, actor):
        _seed_required_accounts(db, branch)
        run_seed(db, branch_code=branch.code, period="2026-07", actor_id=actor.id)
        db.commit()

        report = validate_only(db, branch_code=branch.code, period="2026-07")
        assert report["applied"] is True
        assert report["status"] == "completed"
        assert report["version"] == DATASET_VERSION


class TestConfirmationPhrase:
    def test_includes_branch_period_and_version(self):
        phrase = confirmation_phrase("ELK-001", "2026-07")
        assert "ELK-001" in phrase
        assert "2026-07" in phrase
        assert DATASET_VERSION in phrase

    def test_different_periods_produce_different_phrases(self):
        assert confirmation_phrase("ELK-001", "2026-07") != confirmation_phrase("ELK-001", "2026-08")
