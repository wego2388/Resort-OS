"""tests/test_hist_leasing.py — HIST-01 leasing generator (OPS-DATA-02 §10.5)."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.hist_leasing import generate as generate_leasing


@pytest.fixture
def branch(db: Session):
    from app.modules.core.models import Branch
    b = Branch(name="Test Leasing HIST", name_ar="اختبار إيجارات تاريخية",
               code=f"HL-{uuid.uuid4().hex[:6].upper()}")
    db.add(b)
    db.commit()
    return b


def _seed_accounts(db: Session, branch):
    from app.modules.finance.models import Account
    for code, name, acc_type in [
        ("1100", "Cash", "asset"), ("1110", "Bank", "asset"),
        ("1260", "Tenant AR", "asset"), ("2150", "Tenant Deposits", "liability"),
        ("4500", "Lease Revenue", "revenue"),
    ]:
        db.add(Account(branch_id=branch.id, code=code, name=name, account_type=acc_type))
    db.commit()


class _Ctx:
    def __init__(self, branch_id: int):
        self.branch_id = branch_id
        self.period_year = 2026
        self.period_month = 7
        self.tz_name = "Africa/Cairo"


class TestHistLeasingGenerator:
    def test_creates_five_contracts_with_correct_terms(self, db: Session, branch):
        from app.modules.leasing.models import LeaseContract

        _seed_accounts(db, branch)
        generate_leasing(db, _Ctx(branch.id))
        db.commit()

        contracts = db.query(LeaseContract).filter(LeaseContract.branch_id == branch.id).all()
        assert len(contracts) == 5
        by_notes = {c.notes: c for c in contracts}
        assert by_notes["HIST-LSE-DIVE-01"].base_rent == Decimal("45000.00")
        assert by_notes["HIST-LSE-DIVE-01"].security_deposit == Decimal("90000.00")
        assert by_notes["HIST-LSE-SHOP-02"].base_rent == Decimal("15000.00")
        assert sum(c.base_rent for c in contracts) == Decimal("138000.00")
        assert sum(c.security_deposit for c in contracts) == Decimal("276000.00")

    def test_all_deposits_confirmed_received(self, db: Session, branch):
        from app.modules.leasing.models import LeaseContract

        _seed_accounts(db, branch)
        generate_leasing(db, _Ctx(branch.id))
        db.commit()

        contracts = db.query(LeaseContract).filter(LeaseContract.branch_id == branch.id).all()
        assert all(c.deposit_received for c in contracts)

    def test_deposit_journal_entries_post_correct_total(self, db: Session, branch):
        from app.modules.finance.models import Account, JournalLine

        _seed_accounts(db, branch)
        generate_leasing(db, _Ctx(branch.id))
        db.commit()

        deposit_account = db.query(Account).filter_by(branch_id=branch.id, code="2150").first()
        total_deposits = sum(
            l.credit for l in db.query(JournalLine).filter(JournalLine.account_id == deposit_account.id).all()
        )
        assert total_deposits == Decimal("276000.00")

    def test_shop2_stays_uncollected_and_becomes_tenant_ar(self, db: Session, branch):
        from app.modules.leasing.models import LeaseContract, LeasePayment

        _seed_accounts(db, branch)
        generate_leasing(db, _Ctx(branch.id))
        db.commit()

        shop2 = db.query(LeaseContract).filter(
            LeaseContract.branch_id == branch.id, LeaseContract.notes == "HIST-LSE-SHOP-02",
        ).one()
        july_payment = (
            db.query(LeasePayment)
            .filter(LeasePayment.contract_id == shop2.id)
            .order_by(LeasePayment.due_date)
            .all()
        )[1]
        assert july_payment.status == "overdue"
        assert july_payment.paid_amount == Decimal("0.00")
        assert july_payment.accrued is True  # اتحقق محاسبيًا رغم عدم التحصيل

    def test_shop1_penalty_computed_from_real_engine_not_hardcoded(self, db: Session, branch):
        """§10.5 بيفترض غرامة 2% ثابتة (360) — لكن المحرك الحقيقي المُقفَل
        (calculate_lease_penalty) بيطبّق شرائح 5%/10%. دفعة SHOP1 بتتأخر 14
        يوم (استحقاق يوم 1، تسديد يوم 15) = شريحة 5% = 900.00 بالظبط،
        محسوبة هنا من نفس المصدر الوحيد اللي الكود بيستخدمه، مش رقم مكرَّر."""
        from app.resort_os.timeshare_engine import calculate_lease_penalty
        from datetime import date
        from app.modules.leasing.models import LeaseContract, LeasePayment

        _seed_accounts(db, branch)
        generate_leasing(db, _Ctx(branch.id))
        db.commit()

        shop1 = db.query(LeaseContract).filter(
            LeaseContract.branch_id == branch.id, LeaseContract.notes == "HIST-LSE-SHOP-01",
        ).one()
        july_payment = (
            db.query(LeasePayment)
            .filter(LeasePayment.contract_id == shop1.id)
            .order_by(LeasePayment.due_date)
            .all()
        )[1]
        expected_penalty = calculate_lease_penalty(Decimal("18000"), date(2026, 7, 1), date(2026, 7, 15))
        assert expected_penalty == Decimal("900.00")
        assert july_payment.penalty == expected_penalty
        assert july_payment.status == "paid"
        assert july_payment.paid_amount == july_payment.amount + july_payment.penalty

    def test_dive_water_spa_july_payments_fully_collected(self, db: Session, branch):
        from app.modules.leasing.models import LeaseContract, LeasePayment

        _seed_accounts(db, branch)
        generate_leasing(db, _Ctx(branch.id))
        db.commit()

        for code, expected_amount in [
            ("HIST-LSE-DIVE-01", Decimal("45000.00")),
            ("HIST-LSE-WATER-01", Decimal("35000.00")),
            ("HIST-LSE-SPA-01", Decimal("25000.00")),
        ]:
            contract = db.query(LeaseContract).filter(
                LeaseContract.branch_id == branch.id, LeaseContract.notes == code,
            ).one()
            july_payment = (
                db.query(LeasePayment)
                .filter(LeasePayment.contract_id == contract.id)
                .order_by(LeasePayment.due_date)
                .all()
            )[1]
            assert july_payment.status == "paid", code
            assert july_payment.paid_amount == expected_amount, code

    def test_spa_split_payment_uses_both_bank_and_cash(self, db: Session, branch):
        from app.modules.finance.models import Account, JournalEntry
        from app.modules.leasing.models import LeaseContract

        _seed_accounts(db, branch)
        generate_leasing(db, _Ctx(branch.id))
        db.commit()

        spa = db.query(LeaseContract).filter(
            LeaseContract.branch_id == branch.id, LeaseContract.notes == "HIST-LSE-SPA-01",
        ).one()
        bank_account = db.query(Account).filter_by(branch_id=branch.id, code="1110").first()
        cash_account = db.query(Account).filter_by(branch_id=branch.id, code="1100").first()

        entries = db.query(JournalEntry).filter(
            JournalEntry.source == "leasing", JournalEntry.reference.like("LSE-RCV-%"),
        ).all()
        spa_lines = [l for e in entries for l in e.lines if e.description and spa.tenant_name in e.description]
        bank_debited = any(l.account_id == bank_account.id and l.debit == Decimal("15000.00") for l in spa_lines)
        cash_debited = any(l.account_id == cash_account.id and l.debit == Decimal("10000.00") for l in spa_lines)
        assert bank_debited
        assert cash_debited

    def test_generate_is_deterministic_across_two_branches(self, db: Session, branch):
        """نفس المدخلات (فرع تاني) لازم تنتج بالظبط نفس الأرقام — الخوارزمية
        حتمية 100%، مفيش أي عشوائية."""
        from app.modules.core.models import Branch
        from app.modules.leasing.models import LeaseContract

        _seed_accounts(db, branch)
        result1 = generate_leasing(db, _Ctx(branch.id))
        db.commit()

        branch2 = Branch(name="Second HIST Leasing", name_ar="فرع ثاني",
                          code=f"HL2-{uuid.uuid4().hex[:6].upper()}")
        db.add(branch2)
        db.commit()
        _seed_accounts(db, branch2)
        result2 = generate_leasing(db, _Ctx(branch2.id))
        db.commit()

        assert result1["totals"] == result2["totals"]
        contracts1 = db.query(LeaseContract).filter(LeaseContract.branch_id == branch.id).count()
        contracts2 = db.query(LeaseContract).filter(LeaseContract.branch_id == branch2.id).count()
        assert contracts1 == contracts2 == 5
