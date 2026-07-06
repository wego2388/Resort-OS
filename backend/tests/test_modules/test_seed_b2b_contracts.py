"""tests/test_modules/test_seed_b2b_contracts.py

Regression test for a real bug found during live acceptance testing of the
beach module (2026-07-06): `b2b_contracts` was never seeded at all (0 rows),
so the "B2B contracts" admin screen and the live dashboard's B2B panel always
showed an empty state, and there was no way to exercise a B2B hotel guest
check-in on a freshly-seeded environment without first creating a contract by
hand — the exact same class of gap as the previously-empty `employees`
(HR) and `rooms` (PMS) tables.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.modules.beach.models import B2BContract, B2BContractDay
from app.modules.core.models import Branch
from app.seed import _seed_b2b_contracts


def _make_branch(db: Session) -> Branch:
    b = Branch(name="Seed Test Branch", name_ar="فرع اختبار",
               code=f"SEED-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def test_seed_b2b_contracts_creates_active_contracts(db: Session):
    branch = _make_branch(db)
    _seed_b2b_contracts(db, branch_id=branch.id)
    db.commit()

    contracts = db.query(B2BContract).filter(B2BContract.branch_id == branch.id).all()
    assert len(contracts) == 3
    # every seeded contract must actually be usable for a check-in today —
    # active and within its validity window (the exact class of bug fixed
    # separately in validate_b2b_checkin: an expired/inactive seeded
    # contract would defeat the point of seeding it at all).
    today = date.today()
    for c in contracts:
        assert c.is_active is True
        assert c.valid_from <= today <= c.valid_until
        assert c.daily_quota > 0
        assert c.entry_price > 0

    # one contract seeded near its daily quota so the live dashboard's
    # quota_warning alert has something to show on a fresh environment.
    near_exhausted = db.query(B2BContractDay).filter(
        B2BContractDay.contract_id.in_([c.id for c in contracts]),
        B2BContractDay.day == today,
    ).all()
    assert any(
        (next(c for c in contracts if c.id == d.contract_id).daily_quota - d.checked_in_count) <= 5
        for d in near_exhausted
    )


def test_seed_b2b_contracts_is_idempotent(db: Session):
    branch = _make_branch(db)
    _seed_b2b_contracts(db, branch_id=branch.id)
    _seed_b2b_contracts(db, branch_id=branch.id)  # running twice must not duplicate rows
    db.commit()

    assert db.query(B2BContract).filter(B2BContract.branch_id == branch.id).count() == 3
