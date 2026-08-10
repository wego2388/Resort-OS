"""tests/test_hist_timeshare.py — HIST-01 timeshare generator (OPS-DATA-02 §10.8)."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.hist_timeshare import generate as generate_timeshare


@pytest.fixture
def branch(db: Session):
    from app.modules.core.models import Branch
    b = Branch(name="Test Timeshare HIST", name_ar="اختبار تايم شير تاريخي",
               code=f"HT-{uuid.uuid4().hex[:6].upper()}")
    db.add(b)
    db.commit()
    return b


def _seed_accounts(db: Session, branch):
    from app.modules.finance.models import Account
    for code, name, acc_type in [
        ("1100", "Cash", "asset"), ("1110", "Bank", "asset"), ("1120", "Card Clearing", "asset"),
        ("4600", "Timeshare Contract Revenue", "revenue"),
        ("4650", "Timeshare Maintenance Revenue", "revenue"),
    ]:
        db.add(Account(branch_id=branch.id, code=code, name=name, account_type=acc_type))
    db.commit()


class _Ctx:
    def __init__(self, branch_id: int):
        self.branch_id = branch_id
        self.period_year = 2026
        self.period_month = 7
        self.tz_name = "Africa/Cairo"


class TestHistTimeshareGenerator:
    def test_creates_twelve_contracts_with_correct_values(self, db: Session, branch):
        from app.modules.timeshare.models import TimeshareContract

        _seed_accounts(db, branch)
        generate_timeshare(db, _Ctx(branch.id))
        db.commit()

        contracts = db.query(TimeshareContract).filter(TimeshareContract.branch_id == branch.id).all()
        assert len(contracts) == 12
        assert sum(c.total_value for c in contracts) == Decimal("1078500.00")
        capacities = sorted(c.unit_capacity for c in contracts)
        assert capacities == [2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6]

    def test_two_contracts_cancelled_with_refund(self, db: Session, branch):
        from app.modules.timeshare.models import TimeshareContract

        _seed_accounts(db, branch)
        generate_timeshare(db, _Ctx(branch.id))
        db.commit()

        cancelled = db.query(TimeshareContract).filter(
            TimeshareContract.branch_id == branch.id, TimeshareContract.status == "cancelled",
        ).all()
        assert len(cancelled) == 2
        assert all(c.cancel_amount == Decimal("500.00") for c in cancelled)

    def test_partial_and_overdue_installments_have_correct_status(self, db: Session, branch):
        from app.modules.timeshare.models import TimeshareContract

        _seed_accounts(db, branch)
        generate_timeshare(db, _Ctx(branch.id))
        db.commit()

        contracts = db.query(TimeshareContract).filter(
            TimeshareContract.branch_id == branch.id, TimeshareContract.status != "cancelled",
        ).all()
        partial = [c for c in contracts if c.installments_list[1].status == "partial"]
        overdue = [c for c in contracts if c.installments_list[1].status == "pending"]
        assert len(partial) == 1
        assert len(overdue) == 1
        assert partial[0].installments_list[1].paid_amount == (partial[0].installments_list[1].amount / 2).quantize(Decimal("0.01"))
        assert overdue[0].installments_list[1].paid_amount == Decimal("0.00")

    def test_full_payment_installments_are_paid(self, db: Session, branch):
        from app.modules.timeshare.models import TimeshareContract

        _seed_accounts(db, branch)
        generate_timeshare(db, _Ctx(branch.id))
        db.commit()

        contracts = db.query(TimeshareContract).filter(
            TimeshareContract.branch_id == branch.id, TimeshareContract.status != "cancelled",
        ).all()
        full = [
            c for c in contracts
            if c.installments_list[1].status == "paid"
        ]
        assert len(full) == 8
        for c in full:
            inst = c.installments_list[1]
            assert inst.paid_amount == inst.amount

    def test_maintenance_dues_paid_match_configured_fee_contracts(self, db: Session, branch):
        from app.modules.timeshare.models import TimeshareContract, TimeshareMaintenanceDue

        _seed_accounts(db, branch)
        result = generate_timeshare(db, _Ctx(branch.id))
        db.commit()

        assert result["counts"]["maintenance_dues_paid"] == 4
        paid_dues = (
            db.query(TimeshareMaintenanceDue)
            .join(TimeshareContract, TimeshareMaintenanceDue.contract_id == TimeshareContract.id)
            .filter(TimeshareContract.branch_id == branch.id, TimeshareMaintenanceDue.status == "paid")
            .all()
        )
        assert len(paid_dues) == 4
        assert sum(d.amount for d in paid_dues) == Decimal("10000.00")

    def test_gl_revenue_matches_real_collected_totals(self, db: Session, branch):
        from app.modules.finance.models import Account, JournalLine

        _seed_accounts(db, branch)
        result = generate_timeshare(db, _Ctx(branch.id))
        db.commit()

        maintenance_revenue_account = db.query(Account).filter_by(branch_id=branch.id, code="4650").first()

        # 4600 بيشمل الدفعة الأولى + قسط يونيو + قسط يوليو لكل العقود غير
        # الملغاة، ناقص عكس الإلغاء (راجع _post_contract_cancellation_refund_journal)
        # — هنا بنتحقق بس إن حساب الصيانة مطابق بالظبط للمحصَّل الفعلي في يوليو.
        maintenance_credit = sum(
            l.credit for l in db.query(JournalLine).filter(
                JournalLine.account_id == maintenance_revenue_account.id,
            ).all()
        )
        assert maintenance_credit == Decimal(result["totals"]["july_maintenance_collected"])
        assert maintenance_credit == Decimal("10000.00")

    def test_generate_is_deterministic_across_two_branches(self, db: Session, branch):
        from app.modules.core.models import Branch
        from app.modules.timeshare.models import TimeshareContract

        _seed_accounts(db, branch)
        result1 = generate_timeshare(db, _Ctx(branch.id))
        db.commit()

        branch2 = Branch(name="Second HIST Timeshare", name_ar="فرع ثاني",
                          code=f"HT2-{uuid.uuid4().hex[:6].upper()}")
        db.add(branch2)
        db.commit()
        _seed_accounts(db, branch2)
        result2 = generate_timeshare(db, _Ctx(branch2.id))
        db.commit()

        assert result1["totals"] == result2["totals"]
        c1 = db.query(TimeshareContract).filter(TimeshareContract.branch_id == branch.id).count()
        c2 = db.query(TimeshareContract).filter(TimeshareContract.branch_id == branch2.id).count()
        assert c1 == c2 == 12
