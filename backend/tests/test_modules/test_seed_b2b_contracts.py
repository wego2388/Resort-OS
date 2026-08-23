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

from app.modules.beach import services as beach_services
from app.modules.beach.models import B2BContract
from app.modules.core.models import Branch
from app.modules.finance.models import Account
from app.seed import _seed_b2b_contracts


def _make_branch(db: Session) -> Branch:
    b = Branch(name="Seed Test Branch", name_ar="فرع اختبار",
               code=f"SEED-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    # الديمو المتأخر (Palm Oasis) بيرحّل قيد محاسبي حقيقي (Dr 1165/Cr 4300)
    # وقت الزرع — لازم الحسابين يكونوا موجودين، وإلا _seed_b2b_contracts
    # نفسها هتفشل بـFinancialConfigurationError.
    db.add_all([
        Account(branch_id=b.id, code="1165", name="ذمم فنادق شريكة (B2B)", account_type="asset"),
        Account(branch_id=b.id, code="4300", name="Beach Revenue", account_type="revenue"),
    ])
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
        assert c.monthly_guest_cap > 0
        assert c.monthly_fee > 0

    # 2026-08-20: العقد بقى مبلغ شهري ثابت + حد أقصى استرشادي، مفيش حصة
    # يومية خالص — بدل "عقد قريب من استنفاد الحصة اليومية"، الديمو الحقيقي
    # هنا هو عقد واحد بس مسجّل is_overdue=True برصيد مستحق حقيقي مرحّل
    # فعليًا (Dr 1165/Cr 4300، راجع _seed_b2b_contracts) — عشان لوحة
    # is_overdue الحيّة يكون عندها حاجة تعرضها على بيئة زرع جديدة.
    status = beach_services.get_b2b_quota_status(db, branch.id)
    overdue_entries = [s for s in status if s["is_overdue"]]
    assert len(overdue_entries) == 1
    assert overdue_entries[0]["outstanding_balance"] > 0


def test_seed_b2b_contracts_is_idempotent(db: Session):
    branch = _make_branch(db)
    _seed_b2b_contracts(db, branch_id=branch.id)
    _seed_b2b_contracts(db, branch_id=branch.id)  # running twice must not duplicate rows
    db.commit()

    assert db.query(B2BContract).filter(B2BContract.branch_id == branch.id).count() == 3
