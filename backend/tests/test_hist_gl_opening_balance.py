"""tests/test_hist_gl_opening_balance.py — HIST-01 GL opening balance
journal (OPS-DATA-02 §11.3)."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.hist_gl_opening_balance import generate as generate_gl_opening_balance


@pytest.fixture
def branch(db: Session):
    from app.modules.core.models import Branch
    b = Branch(name="Test GL Opening HIST", name_ar="اختبار قيد افتتاح تاريخي",
               code=f"HGL-{uuid.uuid4().hex[:6].upper()}")
    db.add(b)
    db.commit()
    return b


def _seed_accounts(db: Session, branch):
    from app.modules.finance.models import Account
    accounts = [
        ("1100", "Cash", "asset"), ("1110", "Bank", "asset"), ("1150", "Folio AR", "asset"),
        ("1170", "Timeshare Installment AR", "asset"), ("1200", "Inventory", "asset"),
        ("1210", "Prepaids", "asset"), ("1500", "Land", "asset"), ("1510", "Buildings", "asset"),
        ("1515", "Pool/Landscape", "asset"), ("1520", "Equipment", "asset"),
        ("1530", "Furniture", "asset"), ("1540", "IT", "asset"),
        ("1590", "Accumulated Depreciation", "asset"), ("2200", "Accounts Payable", "liability"),
        ("2160", "VAT Payable", "liability"), ("2170", "Guest Advances", "liability"),
        ("2150", "Tenant Deposits", "liability"), ("2310", "Timeshare Contract Liability", "liability"),
        ("2180", "Accrued Expenses", "liability"), ("3100", "Capital", "equity"),
        ("3200", "Retained Earnings", "equity"),
    ]
    for code, name, acc_type in accounts:
        db.add(Account(branch_id=branch.id, code=code, name=name, account_type=acc_type))
    db.commit()


class _Ctx:
    def __init__(self, branch_id: int):
        self.branch_id = branch_id
        self.period_year = 2026
        self.period_month = 7
        self.tz_name = "Africa/Cairo"


class TestHistGlOpeningBalanceGenerator:
    def test_posts_one_balanced_journal_entry_dated_june_30(self, db: Session, branch):
        from app.modules.finance.models import JournalEntry, JournalLine

        _seed_accounts(db, branch)
        generate_gl_opening_balance(db, _Ctx(branch.id))
        db.commit()

        entry = (
            db.query(JournalEntry)
            .filter(JournalEntry.branch_id == branch.id, JournalEntry.source == "opening_balance")
            .first()
        )
        assert entry is not None
        assert entry.entry_date == date(2026, 6, 30)

        lines = db.query(JournalLine).filter(JournalLine.entry_id == entry.id).all()
        assert len(lines) == 21
        total_debit = sum(l.debit for l in lines)
        total_credit = sum(l.credit for l in lines)
        assert total_debit == total_credit == Decimal("21670000.00")

    def test_fixed_assets_gross_split_matches_fixed_assets_generator_totals(self, db: Session, branch):
        from app.modules.finance.models import Account, JournalLine

        _seed_accounts(db, branch)
        generate_gl_opening_balance(db, _Ctx(branch.id))
        db.commit()

        codes = {"1500": "6000000.00", "1510": "9500000.00", "1515": "1200000.00",
                 "1520": "1910000.00", "1530": "880000.00", "1540": "180000.00"}
        for code, expected in codes.items():
            account = db.query(Account).filter_by(branch_id=branch.id, code=code).first()
            debit_sum = sum(
                l.debit for l in db.query(JournalLine).filter(JournalLine.account_id == account.id).all()
            )
            assert debit_sum == Decimal(expected), f"account {code}"

        # مجموع الفروع الستة = 19,670,000 — نفس إجمالي hist_fixed_assets.py
        total = sum(Decimal(v) for v in codes.values())
        assert total == Decimal("19670000.00")

    def test_accumulated_depreciation_matches_fixed_assets_generator_opening(self, db: Session, branch):
        from app.modules.finance.models import Account, JournalLine

        _seed_accounts(db, branch)
        generate_gl_opening_balance(db, _Ctx(branch.id))
        db.commit()

        account = db.query(Account).filter_by(branch_id=branch.id, code="1590").first()
        credit_sum = sum(
            l.credit for l in db.query(JournalLine).filter(JournalLine.account_id == account.id).all()
        )
        assert credit_sum == Decimal("2731178.57")

    def test_inventory_line_matches_inventory_generator_opening(self, db: Session, branch):
        from app.modules.finance.models import Account, JournalLine

        _seed_accounts(db, branch)
        generate_gl_opening_balance(db, _Ctx(branch.id))
        db.commit()

        account = db.query(Account).filter_by(branch_id=branch.id, code="1200").first()
        debit_sum = sum(
            l.debit for l in db.query(JournalLine).filter(JournalLine.account_id == account.id).all()
        )
        assert debit_sum == Decimal("420000.00")

    def test_rejects_when_required_accounts_missing(self, db: Session, branch):
        with pytest.raises(Exception):
            generate_gl_opening_balance(db, _Ctx(branch.id))
            db.commit()
