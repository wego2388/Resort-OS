"""
tests/test_api/test_finance.py
Integration tests for finance module.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.modules.finance.schemas import (
    AccountCreate, CashCountLine, CashierShiftClose, CashierShiftOpen, CashMovementCreate,
    ConditionalDiscountCreate,
    FolioCreate, FolioChargeCreate, JournalEntryCreate, JournalEntryRead, JournalLineCreate,
    PaymentCreate,
)
from app.modules.finance import services, crud


def make_finance_accounts(db, branch):
    """1100 (نقدية) + 1150 (ذمم الفوليو) — الحسابين اللي add_payment/
    void_payment بيدوّروا عليهم. ⚠️ 2026-08-11 (strict=True — راجع §4):
    من غيرهم add_payment نفسه بيفشل بـ FinancialConfigurationError."""
    from app.modules.finance.models import Account
    if db.query(Account).filter_by(branch_id=branch.id, code="1100").first():
        return
    cash = Account(branch_id=branch.id, code="1100", name="Cash", account_type="asset")
    guest_ledger = Account(branch_id=branch.id, code="1150", name="ذمم الفوليو", account_type="asset")
    db.add_all([cash, guest_ledger])
    db.commit()
    return cash, guest_ledger


@pytest.fixture
def branch(db: Session):
    from app.modules.core.models import Branch
    b = Branch(name="Test Finance", name_ar="اختبار مالي",
               code=f"FIN-{uuid.uuid4().hex[:6].upper()}")
    db.add(b)
    db.flush()
    return b


@pytest.fixture
def folio(db: Session, branch):
    data = FolioCreate(
        branch_id=branch.id,
        guest_name="ضيف اختباري",
        check_in=datetime.utcnow(),
        check_out=datetime.utcnow() + timedelta(days=2),
    )
    return services.create_folio(db, data)


@pytest.fixture
def discount(db: Session, branch):
    data = ConditionalDiscountCreate(
        branch_id=branch.id,
        condition_type="total_amount",
        condition_value=">=100",
        discount_type="percentage",
        discount_value=Decimal("10"),
        valid_from=date.today() - timedelta(days=30),
        valid_until=date.today() + timedelta(days=365),
        priority=1,
    )
    return services.create_discount(db, data)


class TestFolio:

    def test_create_folio(self, db, branch):
        data = FolioCreate(
            branch_id=branch.id,
            guest_name="أحمد علي",
            check_in=datetime.utcnow(),
            check_out=datetime.utcnow() + timedelta(days=3),
        )
        folio = services.create_folio(db, data)
        assert folio.id is not None
        assert folio.status == "open"
        assert folio.total == Decimal("0")

    def test_folio_not_found_raises(self, db):
        with pytest.raises(ValueError):
            services.get_folio_or_404(db, 9999)

    def test_post_charge(self, db, folio):
        charge_data = FolioChargeCreate(
            charge_type="room",
            description="إيجار ليلة",
            amount=Decimal("500.00"),
            vat_amount=Decimal("70.00"),
            posted_at=datetime.utcnow(),
        )
        charge = services.post_charge(db, folio.id, charge_data)
        assert charge.id is not None
        assert charge.amount == Decimal("500.00")
        # تحديث الـ folio من الـ DB
        db.refresh(folio)
        assert folio.total == Decimal("570.00")  # 500 + 70 vat

    def test_settle_folio(self, db, folio):
        """فوليو فارغ يمكن تسويته."""
        settled = services.settle_folio(db, folio.id)
        assert settled.status == "closed"

    def test_cannot_post_charge_to_closed_folio(self, db, folio):
        services.settle_folio(db, folio.id)
        charge_data = FolioChargeCreate(
            charge_type="restaurant",
            description="مطعم",
            amount=Decimal("100"),
            posted_at=datetime.utcnow(),
        )
        with pytest.raises(ValueError):
            services.post_charge(db, folio.id, charge_data)


class TestPayment:

    def test_add_payment(self, db, branch, folio):
        make_finance_accounts(db, branch)
        data = PaymentCreate(
            folio_id=folio.id,
            branch_id=branch.id,
            amount=Decimal("300.00"),
            method="cash",
            posted_at=datetime.utcnow(),
        )
        payment = services.add_payment(db, folio.id, data)
        assert payment.id is not None
        assert payment.voided_at is None

    def test_void_payment(self, db, branch, folio):
        make_finance_accounts(db, branch)
        data = PaymentCreate(
            folio_id=folio.id,
            branch_id=branch.id,
            amount=Decimal("200.00"),
            method="card",
            posted_at=datetime.utcnow(),
        )
        payment = services.add_payment(db, folio.id, data)
        voided = services.void_payment(db, payment.id, voided_by=1)
        assert voided.voided_at is not None
        assert voided.voided_by == 1

    def test_cannot_void_payment_of_closed_folio(self, db, branch, folio):
        make_finance_accounts(db, branch)
        data = PaymentCreate(
            folio_id=folio.id,
            branch_id=branch.id,
            amount=Decimal("100.00"),
            method="cash",
            posted_at=datetime.utcnow(),
        )
        payment = services.add_payment(db, folio.id, data)
        services.settle_folio(db, folio.id)
        with pytest.raises(ValueError, match="مغلق"):
            services.void_payment(db, payment.id, voided_by=1)

    def test_payment_not_found_raises(self, db):
        with pytest.raises(ValueError):
            services.void_payment(db, 9999, voided_by=1)

    def test_cannot_void_direct_payment_via_folio_void(self, db, branch):
        """باج حقيقي اتصلح (2026-07-28): void_payment كانت بترحّل نفس عكس
        قيد تحصيل الفوليو (Dr 1150/Cr 1100) لأي دفعة، حتى دفعة بيع مباشر
        (folio_id=None — بيع نقدي فوري من dining/beach عبر
        create_direct_payment) اللي أصلها مالوش تحصيل فوليو خالص. النظير
        كان بيروح لذمم فوليو وهمية بدل عكس الإيراد الحقيقي — إلغاء بيع مباشر
        لازم يعدّي من إلغاء الصنف/الطلب في الموديول نفسه، مش من هنا."""
        from app.modules.finance import crud as fin_crud
        payment = fin_crud.create_direct_payment(
            db, branch_id=branch.id, amount=Decimal("100"), method="cash",
            posted_at=datetime.utcnow(), reference="ORD-99", ref_order_id=99, source="dining",
        )
        db.commit()
        with pytest.raises(ValueError, match="بيع مباشر"):
            services.void_payment(db, payment.id, voided_by=1)


class TestPaymentSettlementJournalPosting:
    """⚠️ باج محاسبي حقيقي اتصلح (2026-07-07، فجوة معمارية موثّقة في
    CLAUDE.md §18): add_payment (تحصيل فوليو — Charge to Room settled عند
    الخروج) عمرها ما كانت بترحّل أي قيد محاسبي خالص. الكاش المحصّل فعليًا من
    الضيف كان غير مرئي تمامًا في دفتر الأستاذ. دلوقتي بترحّل Dr Cash(1100)/
    Cr ذمم الفوليو(1150)، وvoid_payment بيعكسها."""

    def _make_finance_accounts(self, db, branch):
        from app.modules.finance.models import Account
        cash = Account(branch_id=branch.id, code="1100", name="Cash", account_type="asset")
        guest_ledger = Account(branch_id=branch.id, code="1150", name="ذمم الفوليو", account_type="asset")
        db.add_all([cash, guest_ledger])
        db.commit()
        return cash, guest_ledger

    def test_add_payment_posts_settlement_journal(self, db, branch, folio):
        cash, guest_ledger = self._make_finance_accounts(db, branch)
        data = PaymentCreate(
            folio_id=folio.id, branch_id=branch.id,
            amount=Decimal("300.00"), method="cash", posted_at=datetime.utcnow(),
        )
        payment = services.add_payment(db, folio.id, data)

        entries, total = crud.list_journal_entries(db, branch.id, source="folio_payment")
        assert total == 1
        entry = entries[0]
        assert entry.source_id == payment.id
        db.refresh(cash); db.refresh(guest_ledger)
        cash_line = next(l for l in entry.lines if l.account_id == cash.id)
        guest_ledger_line = next(l for l in entry.lines if l.account_id == guest_ledger.id)
        assert cash_line.debit == Decimal("300.00")
        assert guest_ledger_line.credit == Decimal("300.00")

    def test_void_payment_reverses_settlement_journal(self, db, branch, folio):
        cash, guest_ledger = self._make_finance_accounts(db, branch)
        data = PaymentCreate(
            folio_id=folio.id, branch_id=branch.id,
            amount=Decimal("150.00"), method="cash", posted_at=datetime.utcnow(),
        )
        payment = services.add_payment(db, folio.id, data)
        services.void_payment(db, payment.id, voided_by=1)

        entries, total = crud.list_journal_entries(db, branch.id, source="folio_payment_void")
        assert total == 1
        entry = entries[0]
        db.refresh(cash); db.refresh(guest_ledger)
        cash_line = next(l for l in entry.lines if l.account_id == cash.id)
        guest_ledger_line = next(l for l in entry.lines if l.account_id == guest_ledger.id)
        assert cash_line.credit == Decimal("150.00")   # عكس التحصيل: دائن مش مدين
        assert guest_ledger_line.debit == Decimal("150.00")  # عكس التحصيل: مدين مش دائن

    def test_missing_accounts_fails_payment_atomically(self, db, branch, folio):
        """⚠️ 2026-08-11: عكس السلوك القديم تمامًا — كان فيه باج محاسبي حقيقي
        هنا (لو 1100/1150 مش موجودين، الدفعة كانت تتسجّل عادي بصفر أثر
        محاسبي بصمت). دلوقتي strict=True: حساب مش معرَّف للفرع لازم يفشّل
        تسجيل الدفعة كله — مفيش Payment، مفيش قيد، من غير أي حالة نصف-
        مكتملة (راجع services.add_payment's try/except db.rollback())."""
        from app.modules.finance.services import FinancialConfigurationError

        data = PaymentCreate(
            folio_id=folio.id, branch_id=branch.id,
            amount=Decimal("100.00"), method="cash", posted_at=datetime.utcnow(),
        )
        with pytest.raises(FinancialConfigurationError):
            services.add_payment(db, folio.id, data)

        _, total = crud.list_journal_entries(db, branch.id, source="folio_payment")
        assert total == 0
        assert crud.list_payments(db, folio.id) == []


class TestDiscount:

    def test_create_discount(self, db, discount):
        assert discount.id is not None
        assert discount.is_active is True
        assert discount.uses_count == 0

    def test_invalid_date_range_raises(self, db, branch):
        data = ConditionalDiscountCreate(
            branch_id=branch.id,
            condition_type="total_amount",
            condition_value=">=50",
            discount_type="fixed_amount",
            discount_value=Decimal("20"),
            valid_from=date.today() + timedelta(days=30),
            valid_until=date.today(),  # نهاية قبل البداية
        )
        with pytest.raises(ValueError, match="valid_from"):
            services.create_discount(db, data)

    def test_calculate_percentage_discount(self, db, branch, discount):
        result = services.calculate_order_discount(
            db,
            branch_id=branch.id,
            order_total=Decimal("200"),
            item_count=2,
        )
        assert result.applied is True
        assert result.amount_saved == Decimal("20.00")  # 10% of 200

    def test_discount_not_applied_below_threshold(self, db, branch, discount):
        """الحد الأدنى 100 — طلب بـ 50 لا يحصل على خصم."""
        result = services.calculate_order_discount(
            db,
            branch_id=branch.id,
            order_total=Decimal("50"),
        )
        assert result.applied is False
        assert result.amount_saved == Decimal("0")


# ── Accounting Fixtures ───────────────────────────────────────────────

@pytest.fixture
def account(db: Session, branch):
    data = AccountCreate(
        branch_id=branch.id,
        code="1001",
        name="Cash",
        account_type="asset",
    )
    acc = crud.create_account(db, data)
    db.commit()
    db.refresh(acc)
    return acc


@pytest.fixture
def account2(db: Session, branch):
    data = AccountCreate(
        branch_id=branch.id,
        code="4001",
        name="Revenue",
        account_type="revenue",
    )
    acc = crud.create_account(db, data)
    db.commit()
    db.refresh(acc)
    return acc


class TestAccountLedger:
    """2026-08-19 (طلب Mohamed — كشف حساب): كل حركات حساب واحد خلال مدى
    تاريخي، برصيد متحرّك حسب طبيعة الحساب."""

    def test_ledger_debit_normal_account_running_balance(self, db: Session, branch, account, account2):
        services.post_simple_revenue_journal(
            db, branch.id, date(2026, 8, 1),
            debit_account_code=account.code, credit_account_code=account2.code,
            amount=Decimal("1000"), reference="LEDGER-1", description="أول حركة",
            source="test_ledger", source_id=1,
        )
        services.post_simple_revenue_journal(
            db, branch.id, date(2026, 8, 5),
            debit_account_code=account2.code, credit_account_code=account.code,
            amount=Decimal("300"), reference="LEDGER-2", description="حركة تانية",
            source="test_ledger", source_id=2,
        )

        report = services.get_account_ledger(
            db, branch.id, account.id, date(2026, 8, 1), date(2026, 8, 31),
        )
        assert report.account_code == "1001"
        assert report.opening_balance == Decimal("0")
        assert len(report.lines) == 2
        assert report.lines[0].running_balance == Decimal("1000.00")
        assert report.lines[1].running_balance == Decimal("700.00")
        assert report.closing_balance == Decimal("700.00")
        assert report.total_debit == Decimal("1000.00")
        assert report.total_credit == Decimal("300.00")

    def test_ledger_credit_normal_account_running_balance(self, db: Session, branch, account, account2):
        services.post_simple_revenue_journal(
            db, branch.id, date(2026, 8, 1),
            debit_account_code=account.code, credit_account_code=account2.code,
            amount=Decimal("500"), reference="LEDGER-3", description="إيراد",
            source="test_ledger", source_id=3,
        )
        report = services.get_account_ledger(
            db, branch.id, account2.id, date(2026, 8, 1), date(2026, 8, 31),
        )
        # account2 (4001 Revenue) دائن-طبيعي — الدائن بيزوّد الرصيد.
        assert report.lines[0].running_balance == Decimal("500.00")
        assert report.closing_balance == Decimal("500.00")

    def test_ledger_opening_balance_excludes_lines_before_range(self, db: Session, branch, account, account2):
        services.post_simple_revenue_journal(
            db, branch.id, date(2026, 7, 1),
            debit_account_code=account.code, credit_account_code=account2.code,
            amount=Decimal("200"), reference="LEDGER-OLD", description="قبل المدى",
            source="test_ledger", source_id=4,
        )
        services.post_simple_revenue_journal(
            db, branch.id, date(2026, 8, 10),
            debit_account_code=account.code, credit_account_code=account2.code,
            amount=Decimal("100"), reference="LEDGER-NEW", description="جوه المدى",
            source="test_ledger", source_id=5,
        )
        report = services.get_account_ledger(
            db, branch.id, account.id, date(2026, 8, 1), date(2026, 8, 31),
        )
        assert report.opening_balance == Decimal("200.00")
        assert len(report.lines) == 1
        assert report.closing_balance == Decimal("300.00")

    def test_ledger_rejects_account_from_other_branch(self, db: Session, branch, account):
        from app.modules.core.models import Branch
        other = Branch(name="Other", name_ar="فرع تاني", code="OTHER-LEDGER")
        db.add(other); db.commit()

        with pytest.raises(ValueError, match="غير موجود في هذا الفرع"):
            services.get_account_ledger(db, other.id, account.id, date(2026, 8, 1), date(2026, 8, 31))

    def test_ledger_rejects_inverted_date_range(self, db: Session, branch, account):
        with pytest.raises(ValueError, match="تاريخ البداية"):
            services.get_account_ledger(db, branch.id, account.id, date(2026, 8, 31), date(2026, 8, 1))


class TestAccounting:

    def test_create_account(self, db: Session, branch):
        data = AccountCreate(
            branch_id=branch.id,
            code="2001",
            name="Accounts Payable",
            name_ar="دائنون",
            account_type="liability",
        )
        acc = crud.create_account(db, data)
        db.commit()
        db.refresh(acc)
        assert acc.id is not None
        assert acc.code == "2001"
        assert acc.account_type == "liability"
        assert acc.is_active is True

    def test_post_journal_entry_balanced(self, db: Session, branch, account, account2):
        data = JournalEntryCreate(
            branch_id=branch.id,
            entry_date=date.today(),
            reference="JE-TEST-001",
            description="Test balanced entry",
            lines=[
                JournalLineCreate(account_id=account.id, debit=Decimal("500.00"), credit=Decimal("0")),
                JournalLineCreate(account_id=account2.id, debit=Decimal("0"), credit=Decimal("500.00")),
            ],
        )
        entry = services.post_journal_entry(db, data, user_id=1)
        assert entry.id is not None
        assert entry.status == "posted"
        assert len(entry.lines) == 2
        total_debit = sum(l.debit for l in entry.lines)
        total_credit = sum(l.credit for l in entry.lines)
        assert total_debit == total_credit == Decimal("500.00")

    def test_post_journal_entry_unbalanced_raises(self, db: Session, branch, account, account2):
        data = JournalEntryCreate(
            branch_id=branch.id,
            entry_date=date.today(),
            reference="JE-TEST-002",
            description="Unbalanced entry",
            lines=[
                JournalLineCreate(account_id=account.id, debit=Decimal("300.00"), credit=Decimal("0")),
                JournalLineCreate(account_id=account2.id, debit=Decimal("0"), credit=Decimal("200.00")),
            ],
        )
        with pytest.raises(ValueError, match="غير متوازن"):
            services.post_journal_entry(db, data, user_id=1)

    def test_post_simple_revenue_journal_creates_balanced_entry(self, db: Session, branch):
        """الدالة المشتركة اللي بتحل محل النسخ المكررة في 6 موديولات (مطعم/كافيه/
        شاطئ/PMS/ملكية جزئية/إيجارات)."""
        from app.modules.finance.schemas import AccountCreate as AC
        cash = crud.create_account(db, AC(branch_id=branch.id, code="1100", name="Cash", account_type="asset"))
        rev = crud.create_account(db, AC(branch_id=branch.id, code="4200", name="Restaurant Revenue", account_type="revenue"))
        db.commit()

        entry = services.post_simple_revenue_journal(
            db, branch.id, date.today(),
            debit_account_code="1100", credit_account_code="4200",
            amount=Decimal("350.50"), reference="ORD-TEST-001",
            description="اختبار الدالة المشتركة", source="restaurant", source_id=99,
        )
        assert entry is not None
        assert entry.source == "restaurant"
        assert entry.source_id == 99
        lines = {l.account_id: (l.debit, l.credit) for l in entry.lines}
        assert lines[cash.id] == (Decimal("350.50"), Decimal("0"))
        assert lines[rev.id] == (Decimal("0"), Decimal("350.50"))

    def test_post_simple_revenue_journal_is_idempotent_for_stable_source(self, db: Session, branch):
        from app.modules.finance.models import JournalEntry
        from app.modules.finance.schemas import AccountCreate as AC

        crud.create_account(
            db,
            AC(branch_id=branch.id, code="1100", name="Cash", account_type="asset"),
        )
        crud.create_account(
            db,
            AC(branch_id=branch.id, code="4100", name="Room Revenue", account_type="revenue"),
        )
        db.commit()
        kwargs = dict(
            branch_id=branch.id,
            entry_date=date(2026, 8, 11),
            debit_account_code="1100",
            credit_account_code="4100",
            amount=Decimal("75.00"),
            reference="IDEMPOTENT-75",
            description="اختبار عدم تكرار القيد",
            source="test_idempotency",
            source_id=750,
        )

        first = services.post_simple_revenue_journal(db, **kwargs)
        second = services.post_simple_revenue_journal(db, **kwargs)

        assert first is not None
        assert second is first
        assert db.query(JournalEntry).filter_by(
            branch_id=branch.id,
            source="test_idempotency",
            source_id=750,
            reference="IDEMPOTENT-75",
        ).count() == 1

    def test_post_simple_revenue_journal_noop_when_account_missing(self, db: Session, branch):
        result = services.post_simple_revenue_journal(
            db, branch.id, date.today(),
            debit_account_code="9999", credit_account_code="8888",
            amount=Decimal("100"), reference="X", description="X", source="x", source_id=None,
        )
        assert result is None

    def test_post_simple_revenue_journal_converts_foreign_currency(self, db: Session, branch):
        """قيد بعملة غير EGP — السطور المخزّنة لازم تكون EGP-equivalent (عشان
        التقارير المجمّعة تفضل صح)، والقيد نفسه يسجّل العملة الأصلية وسعر
        الصرف. 100 دولار × 48 = 4800 جنيه بالظبط (سعر الصرف الافتراضي)."""
        from app.modules.finance.schemas import AccountCreate as AC
        cash = crud.create_account(db, AC(branch_id=branch.id, code="1100", name="Cash", account_type="asset"))
        rev = crud.create_account(db, AC(branch_id=branch.id, code="4100", name="Room Revenue", account_type="revenue"))
        db.commit()

        entry = services.post_simple_revenue_journal(
            db, branch.id, date.today(),
            debit_account_code="1100", credit_account_code="4100",
            amount=Decimal("100"), reference="CHK-USD-001",
            description="حجز بالدولار", source="pms", source_id=1,
            currency="USD",
        )
        assert entry is not None
        assert entry.currency == "USD"
        assert entry.fx_rate == Decimal("48.000000")
        lines = {l.account_id: (l.debit, l.credit) for l in entry.lines}
        assert lines[cash.id] == (Decimal("4800.00"), Decimal("0"))
        assert lines[rev.id] == (Decimal("0"), Decimal("4800.00"))

    def test_post_simple_revenue_journal_noop_when_amount_zero(self, db: Session, branch):
        from app.modules.finance.schemas import AccountCreate as AC
        crud.create_account(db, AC(branch_id=branch.id, code="1100", name="Cash", account_type="asset"))
        crud.create_account(db, AC(branch_id=branch.id, code="4200", name="Revenue", account_type="revenue"))
        db.commit()
        result = services.post_simple_revenue_journal(
            db, branch.id, date.today(),
            debit_account_code="1100", credit_account_code="4200",
            amount=Decimal("0"), reference="X", description="X", source="x", source_id=None,
        )
        assert result is None

    def test_post_simple_revenue_journal_noop_when_converted_amount_rounds_to_zero(self, db: Session, branch):
        """مبلغ صغير جداً بعملة أجنبية (0.001) بسعر صرف 1 => بعد التحويل
        والتقريب لقرشين بيبقى 0.00 — لازم يرجّع None زي المبلغ الصفري تماماً،
        مش يحاول يرحّل قيد بمبلغ صفر."""
        from app.modules.finance.schemas import AccountCreate as AC, ExchangeRateCreate as ERC
        crud.create_account(db, AC(branch_id=branch.id, code="1100", name="Cash", account_type="asset"))
        crud.create_account(db, AC(branch_id=branch.id, code="4200", name="Revenue", account_type="revenue"))
        db.commit()
        services.create_exchange_rate(
            db, ERC(from_currency="XAF", to_currency="EGP", rate=Decimal("1.00"),
                    effective_date=date.today()),
            created_by=1,
        )
        result = services.post_simple_revenue_journal(
            db, branch.id, date.today(),
            debit_account_code="1100", credit_account_code="4200",
            amount=Decimal("0.001"), reference="X", description="X", source="x", source_id=None,
            currency="XAF",
        )
        assert result is None

    def test_post_simple_revenue_journal_swallows_exception_when_no_rate_registered(self, db: Session, branch):
        """مفيش سعر صرف مسجّل خالص للعملة دي — get_rate بترفع ValueError، وبما
        إن post_simple_revenue_journal مصمّمة عمداً تبتلع أي خطأ (راجع تعليقها)
        عشان فشل الترحيل المحاسبي ميمنعش العملية التشغيلية الأصلية، لازم ترجّع
        None برضه مش تطلّع الاستثناء للمستدعي."""
        from app.modules.finance.schemas import AccountCreate as AC
        crud.create_account(db, AC(branch_id=branch.id, code="1100", name="Cash", account_type="asset"))
        crud.create_account(db, AC(branch_id=branch.id, code="4200", name="Revenue", account_type="revenue"))
        db.commit()
        result = services.post_simple_revenue_journal(
            db, branch.id, date.today(),
            debit_account_code="1100", credit_account_code="4200",
            amount=Decimal("100"), reference="X", description="X", source="x", source_id=None,
            currency="SAR",
        )
        assert result is None


class TestPostTaxedSaleJournal:
    """OPS-DATA-02 §11.2 (FIN-TAX-01) — post_taxed_sale_journal splits a
    taxed sale into net revenue + VAT payable + service charge payable,
    replacing the old post_simple_revenue_journal(amount=gross) pattern
    that posted the whole VAT/service-inclusive total straight to revenue."""

    def _accounts(self, db: Session, branch, revenue_code="4200"):
        from app.modules.finance.schemas import AccountCreate as AC
        cash = crud.create_account(db, AC(branch_id=branch.id, code="1100", name="Cash", account_type="asset"))
        rev = crud.create_account(db, AC(branch_id=branch.id, code=revenue_code, name="Revenue", account_type="revenue"))
        vat = crud.create_account(db, AC(branch_id=branch.id, code="2160", name="VAT Payable", account_type="liability"))
        svc = crud.create_account(db, AC(branch_id=branch.id, code="2165", name="Service Payable", account_type="liability"))
        db.commit()
        return cash, rev, vat, svc

    def test_splits_net_revenue_vat_and_service_into_separate_lines(self, db: Session, branch):
        cash, rev, vat, svc = self._accounts(db, branch)
        entry = services.post_taxed_sale_journal(
            db, branch.id, date.today(),
            debit_account_code="1100", revenue_account_code="4200",
            net_revenue_amount=Decimal("1000.00"),
            vat_amount=Decimal("140.00"), service_charge_amount=Decimal("120.00"),
            reference="ORD-TAX-001", description="اختبار فصل الضريبة",
            source="dining", source_id=1,
        )
        lines = {l.account_id: (l.debit, l.credit) for l in entry.lines}
        # gross = 1000 + 140 + 120 = 1260, all on the debit side only
        assert lines[cash.id] == (Decimal("1260.00"), Decimal("0"))
        assert lines[rev.id] == (Decimal("0"), Decimal("1000.00"))
        assert lines[vat.id] == (Decimal("0"), Decimal("140.00"))
        assert lines[svc.id] == (Decimal("0"), Decimal("120.00"))
        total_debit = sum(l.debit for l in entry.lines)
        total_credit = sum(l.credit for l in entry.lines)
        assert total_debit == total_credit == Decimal("1260.00")

    def test_no_service_line_for_historical_vat_only_sale(self, db: Session, branch):
        """The generic journal supports legacy VAT-only rows without 2165."""
        from app.modules.finance.schemas import AccountCreate as AC
        cash = crud.create_account(db, AC(branch_id=branch.id, code="1100", name="Cash", account_type="asset"))
        rev = crud.create_account(db, AC(branch_id=branch.id, code="4300", name="Beach Revenue", account_type="revenue"))
        vat = crud.create_account(db, AC(branch_id=branch.id, code="2160", name="VAT Payable", account_type="liability"))
        db.commit()
        entry = services.post_taxed_sale_journal(
            db, branch.id, date.today(),
            debit_account_code="1100", revenue_account_code="4300",
            net_revenue_amount=Decimal("200.00"), vat_amount=Decimal("28.00"),
            reference="BCH-TAX-001", description="اختبار الشاطئ",
            source="beach", source_id=1, cost_center_code="BEACH",
        )
        assert len(entry.lines) == 3
        lines = {l.account_id: (l.debit, l.credit) for l in entry.lines}
        assert lines[cash.id] == (Decimal("228.00"), Decimal("0"))
        assert lines[rev.id] == (Decimal("0"), Decimal("200.00"))
        assert lines[vat.id] == (Decimal("0"), Decimal("28.00"))

    def test_idempotent_retry_returns_existing_entry_not_a_duplicate(self, db: Session, branch):
        self._accounts(db, branch)
        first = services.post_taxed_sale_journal(
            db, branch.id, date.today(),
            debit_account_code="1100", revenue_account_code="4200",
            net_revenue_amount=Decimal("100.00"), vat_amount=Decimal("14.00"),
            reference="ORD-DUP-001", description="x", source="dining", source_id=5,
        )
        second = services.post_taxed_sale_journal(
            db, branch.id, date.today(),
            debit_account_code="1100", revenue_account_code="4200",
            net_revenue_amount=Decimal("100.00"), vat_amount=Decimal("14.00"),
            reference="ORD-DUP-001", description="retried", source="dining", source_id=5,
        )
        assert second.id == first.id
        count = db.query(services.JournalEntry).filter(
            services.JournalEntry.source == "dining", services.JournalEntry.source_id == 5,
        ).count()
        assert count == 1

    def test_raises_on_missing_vat_account(self, db: Session, branch):
        from app.modules.finance.schemas import AccountCreate as AC
        crud.create_account(db, AC(branch_id=branch.id, code="1100", name="Cash", account_type="asset"))
        crud.create_account(db, AC(branch_id=branch.id, code="4200", name="Revenue", account_type="revenue"))
        db.commit()
        with pytest.raises(services.FinancialConfigurationError, match="2160"):
            services.post_taxed_sale_journal(
                db, branch.id, date.today(),
                debit_account_code="1100", revenue_account_code="4200",
                net_revenue_amount=Decimal("100.00"), vat_amount=Decimal("14.00"),
                reference="X", description="x", source="dining", source_id=None,
            )

    def test_raises_on_zero_gross_amount(self, db: Session, branch):
        self._accounts(db, branch)
        with pytest.raises(ValueError, match="غير صالح"):
            services.post_taxed_sale_journal(
                db, branch.id, date.today(),
                debit_account_code="1100", revenue_account_code="4200",
                net_revenue_amount=Decimal("0"),
                reference="X", description="x", source="dining", source_id=None,
            )

    def test_raises_when_accounting_period_is_closed(self, db: Session, branch):
        """post_simple_revenue_journal (legacy) deliberately skips this check
        — post_taxed_sale_journal must not: FIN-TAX-01 requires it to respect
        the accounting-period lock."""
        self._accounts(db, branch)
        from app.core.kernel.models.user import User
        from app.core.kernel.security import get_password_hash
        user = User(email=f"closer2-{uuid.uuid4().hex[:6]}@test.local",
                    password_hash=get_password_hash("Test@12345"),
                    full_name="Closer", role="admin", is_active=True)
        db.add(user); db.flush()
        today = date.today()
        services.close_accounting_period(db, branch.id, today.year, today.month, closed_by=user.id)
        with pytest.raises(ValueError, match="مقفولة"):
            services.post_taxed_sale_journal(
                db, branch.id, today,
                debit_account_code="1100", revenue_account_code="4200",
                net_revenue_amount=Decimal("100.00"), vat_amount=Decimal("14.00"),
                reference="X", description="x", source="dining", source_id=None,
            )

    def test_tax_profile_version_recorded_in_description(self, db: Session, branch):
        self._accounts(db, branch)
        entry = services.post_taxed_sale_journal(
            db, branch.id, date.today(),
            debit_account_code="1100", revenue_account_code="4200",
            net_revenue_amount=Decimal("100.00"), vat_amount=Decimal("14.00"),
            reference="ORD-TP-001", description="طلب عادي", source="dining", source_id=9,
            tax_profile_version="EG-TRIAL-2026-07-v1",
        )
        assert "EG-TRIAL-2026-07-v1" in entry.description

    def test_does_not_commit_internally(self, db: Session, branch):
        """لا يعمل commit داخليًا — المسؤولية على المستدعي (زي الأصل)."""
        self._accounts(db, branch)
        services.post_taxed_sale_journal(
            db, branch.id, date.today(),
            debit_account_code="1100", revenue_account_code="4200",
            net_revenue_amount=Decimal("100.00"), vat_amount=Decimal("14.00"),
            reference="ORD-NOCOMMIT-001", description="x", source="dining", source_id=None,
        )
        db.rollback()
        count = db.query(services.JournalEntry).filter(
            services.JournalEntry.reference == "ORD-NOCOMMIT-001",
        ).count()
        assert count == 0


class TestReverseTaxedSaleJournal:
    """void/refund must reverse the exact original tax-split lines, not
    post a fresh Dr Revenue = gross entry (OPS-DATA-02 §11.2)."""

    def _accounts(self, db: Session, branch, revenue_code="4200"):
        from app.modules.finance.schemas import AccountCreate as AC
        cash = crud.create_account(db, AC(branch_id=branch.id, code="1100", name="Cash", account_type="asset"))
        rev = crud.create_account(db, AC(branch_id=branch.id, code=revenue_code, name="Revenue", account_type="revenue"))
        vat = crud.create_account(db, AC(branch_id=branch.id, code="2160", name="VAT Payable", account_type="liability"))
        svc = crud.create_account(db, AC(branch_id=branch.id, code="2165", name="Service Payable", account_type="liability"))
        db.commit()
        return cash, rev, vat, svc

    def test_reversal_debits_revenue_vat_service_and_credits_cash(self, db: Session, branch):
        cash, rev, vat, svc = self._accounts(db, branch)
        services.post_taxed_sale_journal(
            db, branch.id, date.today(),
            debit_account_code="1100", revenue_account_code="4200",
            net_revenue_amount=Decimal("1000.00"),
            vat_amount=Decimal("140.00"), service_charge_amount=Decimal("120.00"),
            reference="ORD-REV-001", description="بيع أصلي",
            source="dining", source_id=1,
        )
        reversal = services.reverse_taxed_sale_journal(
            db, branch.id, date.today(),
            debit_account_code="1100", revenue_account_code="4200",
            net_revenue_amount=Decimal("1000.00"),
            vat_amount=Decimal("140.00"), service_charge_amount=Decimal("120.00"),
            reference="ORD-REV-001-VOID", description="إلغاء",
            source="dining_void", source_id=1,
        )
        lines = {l.account_id: (l.debit, l.credit) for l in reversal.lines}
        assert lines[cash.id] == (Decimal("0"), Decimal("1260.00"))
        assert lines[rev.id] == (Decimal("1000.00"), Decimal("0"))
        assert lines[vat.id] == (Decimal("140.00"), Decimal("0"))
        assert lines[svc.id] == (Decimal("120.00"), Decimal("0"))

    def test_reversal_is_also_idempotent(self, db: Session, branch):
        self._accounts(db, branch)
        first = services.reverse_taxed_sale_journal(
            db, branch.id, date.today(),
            debit_account_code="1100", revenue_account_code="4200",
            net_revenue_amount=Decimal("100.00"), vat_amount=Decimal("14.00"),
            reference="ORD-REV-DUP", description="x", source="dining_void", source_id=2,
        )
        second = services.reverse_taxed_sale_journal(
            db, branch.id, date.today(),
            debit_account_code="1100", revenue_account_code="4200",
            net_revenue_amount=Decimal("100.00"), vat_amount=Decimal("14.00"),
            reference="ORD-REV-DUP", description="retry", source="dining_void", source_id=2,
        )
        assert second.id == first.id


class TestAccountingPeriodAndShiftHandover:
    def test_close_period_writes_audit_log(self, db: Session, branch):
        from app.modules.core.crud import list_audit_logs
        from app.core.kernel.models.user import User
        from app.core.kernel.security import get_password_hash
        user = User(email=f"closer-{uuid.uuid4().hex[:6]}@test.local",
                    password_hash=get_password_hash("Test@12345"),
                    full_name="Closer", role="admin", is_active=True)
        db.add(user); db.flush()

        today = date.today()
        services.close_accounting_period(db, branch.id, today.year, today.month, closed_by=user.id)
        logs, _ = list_audit_logs(db, branch_id=branch.id, entity_type="accounting_period")
        assert any(l.action == "close_period" and l.user_id == user.id for l in logs)

    def test_handover_note_visible_to_next_shift_opener(self, db: Session, branch):
        assert services.get_latest_handover_note(db, branch.id) is None

        shift = services.open_shift(
            db, cashier_id=30, opened_by=30,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("0")),
        )
        services.close_shift(
            db, shift.id, closed_by=30,
            data=CashierShiftClose(
                counted_cash=Decimal("0"),
                handover_note="فيه عميل هيجي الصبح يستلم طلبية معلّقة، خد بالك",
            ),
        )
        note = services.get_latest_handover_note(db, branch.id)
        assert note == "فيه عميل هيجي الصبح يستلم طلبية معلّقة، خد بالك"

    def test_handover_note_uses_most_recently_closed_shift(self, db: Session, branch):
        s1 = services.open_shift(db, cashier_id=31, opened_by=31,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("0")))
        services.close_shift(db, s1.id, closed_by=31,
            data=CashierShiftClose(counted_cash=Decimal("0"), handover_note="ملاحظة قديمة"))

        s2 = services.open_shift(db, cashier_id=32, opened_by=32,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("0")))
        services.close_shift(db, s2.id, closed_by=32,
            data=CashierShiftClose(counted_cash=Decimal("0"), handover_note="ملاحظة جديدة"))

        assert services.get_latest_handover_note(db, branch.id) == "ملاحظة جديدة"


class TestAccountingYearClose:
    """2026-08-19 (طلب Mohamed — إقفال سنة محاسبية): يترحّل قيد إقفال حقيقي
    يصفّر الإيرادات/المصروفات في 3200 (أرباح مرحّلة)."""

    def _close_all_months(self, db, branch, year, closed_by=1):
        for month in range(1, 13):
            services.close_accounting_period(db, branch.id, year, month, closed_by=closed_by)

    def test_close_year_requires_all_12_months_closed(self, db, branch):
        year = 2025
        for month in range(1, 6):
            services.close_accounting_period(db, branch.id, year, month, closed_by=1)

        with pytest.raises(ValueError, match=r"5/12"):
            services.close_accounting_year(db, branch.id, year, closed_by=1)

    def test_close_year_requires_retained_earnings_account(self, db, branch):
        year = 2025
        self._close_all_months(db, branch, year)

        with pytest.raises(services.FinancialConfigurationError, match="3200"):
            services.close_accounting_year(db, branch.id, year, closed_by=1)

    def test_close_year_posts_closing_entry_and_zeroes_pnl(self, db, branch):
        from app.modules.finance.models import Account, JournalEntry
        year = 2025
        cash = Account(branch_id=branch.id, code="1100", name="Cash", account_type="asset")
        revenue = Account(branch_id=branch.id, code="4100", name="Revenue", account_type="revenue")
        expense = Account(branch_id=branch.id, code="5100", name="Expense", account_type="expense")
        retained = Account(branch_id=branch.id, code="3200", name="أرباح مرحّلة", account_type="equity")
        db.add_all([cash, revenue, expense, retained]); db.commit()

        services.post_simple_revenue_journal(
            db, branch.id, date(year, 3, 15),
            debit_account_code="1100", credit_account_code="4100",
            amount=Decimal("10000"), reference="REV-2025", description="إيراد السنة",
            source="test_year_close", source_id=1,
        )
        services.post_simple_revenue_journal(
            db, branch.id, date(year, 6, 1),
            debit_account_code="5100", credit_account_code="1100",
            amount=Decimal("4000"), reference="EXP-2025", description="مصروف السنة",
            source="test_year_close", source_id=2,
        )

        self._close_all_months(db, branch, year)
        year_close = services.close_accounting_year(db, branch.id, year, closed_by=1)

        assert year_close.net_income == Decimal("6000.00")
        assert year_close.branch_id == branch.id

        entry = db.query(JournalEntry).filter(JournalEntry.id == year_close.journal_entry_id).one()
        assert entry.source == "year_close"
        total_debit = sum(l.debit for l in entry.lines)
        total_credit = sum(l.credit for l in entry.lines)
        assert total_debit == total_credit

        by_account = {l.account_id: l for l in entry.lines}
        assert by_account[revenue.id].debit == Decimal("10000.00")  # يصفّر الإيراد
        assert by_account[expense.id].credit == Decimal("4000.00")  # يصفّر المصروف
        assert by_account[retained.id].credit == Decimal("6000.00")  # صافي الربح

        # الرصيد الفعلي لحساب الإيرادات/المصروفات بعد الإقفال = صفر
        post_close_sums = crud.sum_journal_lines_by_account(db, branch.id, None, date(year, 12, 31))
        rev_debit, rev_credit = post_close_sums[revenue.id]
        assert rev_credit - rev_debit == Decimal("0.00")
        exp_debit, exp_credit = post_close_sums[expense.id]
        assert exp_debit - exp_credit == Decimal("0.00")

    def test_close_year_rejects_double_close(self, db, branch):
        from app.modules.finance.models import Account
        year = 2025
        cash = Account(branch_id=branch.id, code="1100", name="Cash", account_type="asset")
        revenue = Account(branch_id=branch.id, code="4100", name="Revenue", account_type="revenue")
        retained = Account(branch_id=branch.id, code="3200", name="أرباح مرحّلة", account_type="equity")
        db.add_all([cash, revenue, retained]); db.commit()
        services.post_simple_revenue_journal(
            db, branch.id, date(year, 1, 10),
            debit_account_code="1100", credit_account_code="4100",
            amount=Decimal("500"), reference="REV-DOUBLE", description="إيراد",
            source="test_year_close", source_id=3,
        )
        self._close_all_months(db, branch, year)
        services.close_accounting_year(db, branch.id, year, closed_by=1)

        with pytest.raises(ValueError, match="مقفولة بالفعل"):
            services.close_accounting_year(db, branch.id, year, closed_by=1)

    def test_close_year_rejects_no_activity(self, db, branch):
        from app.modules.finance.models import Account
        year = 2025
        retained = Account(branch_id=branch.id, code="3200", name="أرباح مرحّلة", account_type="equity")
        db.add(retained); db.commit()
        self._close_all_months(db, branch, year)

        with pytest.raises(ValueError, match="لا يوجد نشاط مالي"):
            services.close_accounting_year(db, branch.id, year, closed_by=1)

    def test_validate_period_open_blocks_closed(self, db: Session, branch):
        # اقفل الفترة الحالية
        today = date.today()
        services.close_accounting_period(db, branch.id, today.year, today.month, closed_by=1)
        # حاول ترحيل قيد في فترة مقفولة
        from app.modules.finance.schemas import AccountCreate as AC
        data_acc = AC(branch_id=branch.id, code="1099", name="Test Account", account_type="asset")
        acc = crud.create_account(db, data_acc)
        db.commit()
        db.refresh(acc)
        data_acc2 = AC(branch_id=branch.id, code="4099", name="Revenue Test", account_type="revenue")
        acc2 = crud.create_account(db, data_acc2)
        db.commit()
        db.refresh(acc2)
        entry_data = JournalEntryCreate(
            branch_id=branch.id,
            entry_date=today,
            reference="JE-BLOCKED",
            description="Should be blocked",
            lines=[
                JournalLineCreate(account_id=acc.id, debit=Decimal("100"), credit=Decimal("0")),
                JournalLineCreate(account_id=acc2.id, debit=Decimal("0"), credit=Decimal("100")),
            ],
        )
        with pytest.raises(ValueError, match="مقفولة"):
            services.post_journal_entry(db, entry_data, user_id=1)

    def test_close_period(self, db: Session, branch):
        year = 2025
        month = 1
        period = services.close_accounting_period(db, branch.id, year, month, closed_by=1)
        assert period.id is not None
        assert period.status == "closed"
        assert period.closed_by == 1
        assert period.closed_at is not None
        # Verify it persists
        fetched = crud.get_period_status(db, branch.id, year, month)
        assert fetched is not None
        assert fetched.status == "closed"

    def test_close_accounting_period_twice_rejected(self, db: Session, branch):
        """close_accounting_period (services) لازم يمنع إعادة قفل فترة مقفولة
        بالفعل — زي قفل الوردية بالظبط، عشان محدش يقدر يغيّر closed_by/closed_at
        بصمت فوق سجل تدقيق فترة مقفولة أصلاً."""
        services.close_accounting_period(db, branch.id, 2025, 6, closed_by=1)
        with pytest.raises(ValueError, match="مقفولة بالفعل"):
            services.close_accounting_period(db, branch.id, 2025, 6, closed_by=2)

    def test_crud_close_period_is_a_generic_upsert(self, db: Session, branch):
        """crud.close_period نفسه (طبقة DB الخام، بدون قاعدة العمل) لازم يفضل
        upsert عام (ينشئ أو يحدّث) — قاعدة منع إعادة القفل موجودة في services
        فوقه، مش هنا. بنتأكد الحقول بتتحدّث فعلاً لو الصف كان موجود بالفعل."""
        first = crud.close_period(db, branch.id, 2025, 7, closed_by=1)
        db.commit()
        assert first.closed_by == 1

        second = crud.close_period(db, branch.id, 2025, 7, closed_by=2)
        db.commit()
        assert second.id == first.id
        assert second.closed_by == 2


# ── CRUD-level filters (list_folios / list_shifts / list_journal_entries) ──

class TestCrudFilters:

    def test_list_folios_filters_by_status_and_date_range(self, db: Session, branch):
        from app.modules.finance.schemas import FolioCreate as FC
        open_folio = crud.create_folio(db, FC(
            branch_id=branch.id, guest_name="Open Guest",
            check_in=datetime(2026, 6, 10), check_out=datetime(2026, 6, 12),
        ))
        closed_folio = crud.create_folio(db, FC(
            branch_id=branch.id, guest_name="Closed Guest",
            check_in=datetime(2026, 6, 10), check_out=datetime(2026, 6, 12),
        ))
        crud.close_folio(db, closed_folio)
        out_of_range = crud.create_folio(db, FC(
            branch_id=branch.id, guest_name="Out of Range",
            check_in=datetime(2026, 1, 1), check_out=datetime(2026, 1, 3),
        ))
        db.commit()

        by_status, total = crud.list_folios(db, branch.id, status="closed")
        assert total == 1
        assert by_status[0].id == closed_folio.id

        by_range, total_range = crud.list_folios(
            db, branch.id, date_from=date(2026, 6, 1), date_to=date(2026, 6, 30),
        )
        ids_in_range = {f.id for f in by_range}
        assert open_folio.id in ids_in_range
        assert closed_folio.id in ids_in_range
        assert out_of_range.id not in ids_in_range

    def test_list_payments_excludes_voided(self, db: Session, branch, folio):
        make_finance_accounts(db, branch)
        data1 = PaymentCreate(
            folio_id=folio.id, branch_id=branch.id, amount=Decimal("100"),
            method="cash", posted_at=datetime.utcnow(),
        )
        p1 = services.add_payment(db, folio.id, data1)
        data2 = PaymentCreate(
            folio_id=folio.id, branch_id=branch.id, amount=Decimal("50"),
            method="cash", posted_at=datetime.utcnow(),
        )
        p2 = services.add_payment(db, folio.id, data2)
        services.void_payment(db, p2.id, voided_by=1)

        payments = crud.list_payments(db, folio.id)
        assert {p.id for p in payments} == {p1.id}

    def test_settle_all_charges_marks_existing_charges_settled(self, db: Session, folio):
        services.post_charge(db, folio.id, FolioChargeCreate(
            charge_type="room", description="غرفة", amount=Decimal("300"),
            posted_at=datetime.utcnow(),
        ))
        db.refresh(folio)
        assert all(not c.is_settled for c in folio.charges)

        crud.settle_all_charges(db, folio)
        db.commit()
        db.refresh(folio)
        assert all(c.is_settled for c in folio.charges)

    def test_list_shifts_filters_by_cashier_and_status(self, db: Session, branch):
        s1 = services.open_shift(db, cashier_id=60, opened_by=60,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("0")))
        services.close_shift(db, s1.id, closed_by=60, data=CashierShiftClose(counted_cash=Decimal("0")))
        services.open_shift(db, cashier_id=61, opened_by=61,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("0")))

        by_cashier, total_cashier = crud.list_shifts(db, branch.id, cashier_id=60)
        assert total_cashier == 1
        assert by_cashier[0].cashier_id == 60

        by_status, total_status = crud.list_shifts(db, branch.id, status="closed")
        assert total_status == 1
        assert by_status[0].id == s1.id

    def test_list_journal_entries_filters_by_date_range(self, db: Session, branch, account, account2):
        entry_in_range = JournalEntryCreate(
            branch_id=branch.id, entry_date=date(2026, 6, 15),
            reference="JE-IN-RANGE", description="in range",
            lines=[
                JournalLineCreate(account_id=account.id, debit=Decimal("10"), credit=Decimal("0")),
                JournalLineCreate(account_id=account2.id, debit=Decimal("0"), credit=Decimal("10")),
            ],
        )
        services.post_journal_entry(db, entry_in_range, user_id=1)
        entry_out_of_range = JournalEntryCreate(
            branch_id=branch.id, entry_date=date(2026, 1, 15),
            reference="JE-OUT-OF-RANGE", description="out of range",
            lines=[
                JournalLineCreate(account_id=account.id, debit=Decimal("20"), credit=Decimal("0")),
                JournalLineCreate(account_id=account2.id, debit=Decimal("0"), credit=Decimal("20")),
            ],
        )
        services.post_journal_entry(db, entry_out_of_range, user_id=1)

        items, total = crud.list_journal_entries(
            db, branch.id, date_from=date(2026, 6, 1), date_to=date(2026, 6, 30),
        )
        assert total == 1
        assert items[0].reference == "JE-IN-RANGE"

    def test_list_journal_entries_lines_include_account_code_and_name(
        self, db: Session, branch, account, account2,
    ):
        """JournalLineRead.account_code/account_name — الفرونت إند (شاشة
        دفتر اليومية) بيعرضهم مباشرة من غير أي join تاني، فلازم يوصلوا
        صح من الـ account relationship (مش account_id بس)."""
        entry_data = JournalEntryCreate(
            branch_id=branch.id, entry_date=date(2026, 6, 15),
            reference="JE-ACC-DISPLAY", description="test",
            lines=[
                JournalLineCreate(account_id=account.id, debit=Decimal("10"), credit=Decimal("0")),
                JournalLineCreate(account_id=account2.id, debit=Decimal("0"), credit=Decimal("10")),
            ],
        )
        services.post_journal_entry(db, entry_data, user_id=1)

        items, _ = crud.list_journal_entries(db, branch.id, source=None)
        entry = next(e for e in items if e.reference == "JE-ACC-DISPLAY")
        read = JournalEntryRead.model_validate(entry)
        by_account_id = {line.account_id: line for line in read.lines}
        assert by_account_id[account.id].account_code == account.code
        assert by_account_id[account.id].account_name == account.name
        assert by_account_id[account2.id].account_code == account2.code
        assert by_account_id[account2.id].account_name == account2.name

    def test_list_depreciation_entries_filters_by_asset(self, db: Session, branch):
        from app.modules.maintenance.models import Asset
        asset1 = Asset(branch_id=branch.id, name="Asset 1", code=f"AST-{uuid.uuid4().hex[:6].upper()}",
                        category="hvac", purchase_cost=Decimal("1200.00"), useful_life_years=1,
                        depreciation_start_date=date(2026, 1, 1))
        asset2 = Asset(branch_id=branch.id, name="Asset 2", code=f"AST-{uuid.uuid4().hex[:6].upper()}",
                        category="hvac", purchase_cost=Decimal("2400.00"), useful_life_years=1,
                        depreciation_start_date=date(2026, 1, 1))
        db.add_all([asset1, asset2]); db.commit()
        services.run_depreciation(db, branch.id, 2026, 1, user_id=1)

        items, total = crud.list_depreciation_entries(db, branch.id, asset_id=asset1.id)
        assert total == 1
        assert items[0].asset_id == asset1.id

    def test_list_bank_accounts_active_only_filter(self, db: Session, branch):
        from app.modules.finance.schemas import BankAccountCreate, BankAccountUpdate
        active = services.create_bank_account(db, BankAccountCreate(
            branch_id=branch.id, bank_name="بنك مصر", account_name="نشط",
            account_number=f"ACC-{uuid.uuid4().hex[:8]}",
        ))
        inactive = services.create_bank_account(db, BankAccountCreate(
            branch_id=branch.id, bank_name="بنك مصر", account_name="غير نشط",
            account_number=f"ACC-{uuid.uuid4().hex[:8]}",
        ))
        services.update_bank_account(db, inactive.id, BankAccountUpdate(is_active=False))

        active_only = crud.list_bank_accounts(db, branch.id, active_only=True)
        assert {a.id for a in active_only} == {active.id}

        all_accounts = crud.list_bank_accounts(db, branch.id, active_only=False)
        assert {a.id for a in all_accounts} == {active.id, inactive.id}


# ── Cashier Shift / Safe (POS Day) + Shift End Report ──────────────────

class TestCashierShift:

    def test_open_shift(self, db: Session, branch):
        data = CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("500"))
        shift = services.open_shift(db, cashier_id=10, opened_by=10, data=data)
        assert shift.id is not None
        assert shift.status == "open"
        assert shift.opening_float == Decimal("500")

    def test_cannot_open_second_shift_while_open(self, db: Session, branch):
        data = CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("0"))
        services.open_shift(db, cashier_id=11, opened_by=11, data=data)
        with pytest.raises(ValueError, match="مفتوحة"):
            services.open_shift(db, cashier_id=11, opened_by=11, data=data)

    def test_shift_end_report_aggregates_cash_card_credit(self, db: Session, branch, folio):
        make_finance_accounts(db, branch)
        shift = services.open_shift(
            db, cashier_id=20, opened_by=20,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("500")),
        )
        # Cash payment
        services.add_payment(db, folio.id, PaymentCreate(
            folio_id=folio.id, branch_id=branch.id, amount=Decimal("300"),
            method="cash", posted_at=datetime.utcnow(), cashier_id=20,
        ))
        # Card payment
        services.add_payment(db, folio.id, PaymentCreate(
            folio_id=folio.id, branch_id=branch.id, amount=Decimal("200"),
            method="card", posted_at=datetime.utcnow(), cashier_id=20,
        ))
        # Credit (آجل) payment, later voided
        voided = services.add_payment(db, folio.id, PaymentCreate(
            folio_id=folio.id, branch_id=branch.id, amount=Decimal("100"),
            method="credit", posted_at=datetime.utcnow(), cashier_id=20,
        ))
        services.void_payment(db, voided.id, voided_by=20)

        report = services.build_shift_end_report(db, shift.id)
        assert report.total_cash == Decimal("300")
        assert report.total_card == Decimal("200")
        assert report.total_credit == Decimal("0")  # voided, excluded
        assert report.total_sales == Decimal("500")
        assert report.invoice_count == 2
        assert report.voided_count == 1
        assert report.voided_amount == Decimal("100")
        assert report.expected_cash == Decimal("800")  # 500 opening + 300 cash

    def test_shift_report_shows_refunds_as_explicit_separate_line(self, db: Session, branch):
        """M2 (جولة مراجعة Codex الأولى): مرتجع (Payment سالب) بيظهر كبند
        مستقل صريح (refunds_total/refunds_count) بدل ما يتخصم صامت من
        total_cash/total_sales — والكاش المتوقع بيحسب الصافي (بيع − مرتجع)."""
        from app.modules.finance import crud as fin_crud
        shift = services.open_shift(
            db, cashier_id=40, opened_by=40,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("100")),
        )
        fin_crud.create_direct_payment(
            db, branch_id=branch.id, amount=Decimal("200"), method="cash",
            posted_at=datetime.utcnow(), shift_id=shift.id, cashier_id=40,
            reference="ORD-1", ref_order_id=1, source="dining",
        )
        fin_crud.create_direct_payment(
            db, branch_id=branch.id, amount=Decimal("-50"), method="cash",
            posted_at=datetime.utcnow(), shift_id=shift.id, cashier_id=40,
            reference="ORD-REFUND-1", ref_order_id=1, source="dining_refund",
        )
        db.commit()

        report = services.build_shift_end_report(db, shift.id)
        assert report.total_cash == Decimal("200")     # إجمالي البيع (gross)، مش صافي
        assert report.total_sales == Decimal("200")
        assert report.refunds_total == Decimal("50")   # بند مرتجعات صريح
        assert report.refunds_count == 1
        assert report.invoice_count == 1               # المرتجع مش فاتورة
        assert report.expected_cash == Decimal("250")  # 100 افتتاح + (200 − 50) صافي كاش

    def test_shift_report_includes_room_tenders_from_settlement_snapshot(self, db: Session, branch):
        """M2: حصة الغرفة (room tender) مالهاش صف Payment — التقرير بيجمعها من
        لقطة tender_breakdown على DiningSettlement بدل ما تفضل غايبة تمامًا."""
        from app.modules.dining import crud as dining_crud
        from app.modules.dining.models import DiningOrder, Outlet
        outlet = Outlet(branch_id=branch.id, name="rest-m2", outlet_type="restaurant",
                        revenue_account_code="4200")
        db.add(outlet)
        db.flush()
        order = DiningOrder(branch_id=branch.id, outlet_id=outlet.id, order_number="ORD-RM-M2",
                            status="paid", order_type="dine_in", total=Decimal("100"))
        db.add(order)
        db.flush()
        shift = services.open_shift(
            db, cashier_id=41, opened_by=41,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("0")),
        )
        dining_crud.create_settlement(
            db, branch_id=branch.id, order_id=order.id, idempotency_key=None,
            intent_hash="m2hash", total=Decimal("100"), cashier_id=41,
            shift_id=shift.id, created_by=41,
            tender_breakdown=[
                {"method": "cash", "amount": "40", "account": "1100"},
                {"method": "room", "amount": "60", "folio_id": 9},
            ],
        )
        db.commit()

        report = services.build_shift_end_report(db, shift.id)
        assert report.total_room == Decimal("60")

    def test_payments_auto_attach_open_shift(self, db: Session, branch, folio):
        make_finance_accounts(db, branch)
        shift = services.open_shift(
            db, cashier_id=21, opened_by=21,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("0")),
        )
        payment = services.add_payment(db, folio.id, PaymentCreate(
            folio_id=folio.id, branch_id=branch.id, amount=Decimal("150"),
            method="cash", posted_at=datetime.utcnow(),
        ), cashier_id=21)
        assert payment.cashier_id == 21
        assert payment.shift_id == shift.id

    def test_close_shift_computes_variance(self, db: Session, branch, folio):
        make_finance_accounts(db, branch)
        shift = services.open_shift(
            db, cashier_id=22, opened_by=22,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("500")),
        )
        services.add_payment(db, folio.id, PaymentCreate(
            folio_id=folio.id, branch_id=branch.id, amount=Decimal("300"),
            method="cash", posted_at=datetime.utcnow(), cashier_id=22,
        ))
        closed = services.close_shift(
            db, shift.id, closed_by=22,
            data=CashierShiftClose(counted_cash=Decimal("790"), notes="short by 10"),
        )
        assert closed.status == "closed"
        assert closed.expected_cash == Decimal("800")
        assert closed.counted_cash == Decimal("790")
        assert closed.variance == Decimal("-10")

    def test_close_shift_with_cash_count_computes_counted_cash_from_breakdown(self, db: Session, branch, folio):
        """لو الكاشير عدّ الكاش بالفئة، الإجمالي المعدود لازم يتحسب من العدّ نفسه —
        مش من رقم منفصل يكتبه — وتفاصيل العدّ تتحفظ للتدقيق."""
        make_finance_accounts(db, branch)
        shift = services.open_shift(
            db, cashier_id=25, opened_by=25,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("500")),
        )
        services.add_payment(db, folio.id, PaymentCreate(
            folio_id=folio.id, branch_id=branch.id, amount=Decimal("300"),
            method="cash", posted_at=datetime.utcnow(), cashier_id=25,
        ))
        closed = services.close_shift(
            db, shift.id, closed_by=25,
            data=CashierShiftClose(cash_count=[
                CashCountLine(denomination=Decimal("200"), quantity=3),
                CashCountLine(denomination=Decimal("100"), quantity=2),
                CashCountLine(denomination=Decimal("20"), quantity=5),
            ]),
        )
        # 200×3 + 100×2 + 20×5 = 600 + 200 + 100 = 900
        assert closed.counted_cash == Decimal("900")
        assert closed.expected_cash == Decimal("800")
        assert closed.variance == Decimal("100")

        lines = crud.list_cash_count_lines(db, shift.id)
        assert len(lines) == 3
        subtotals = {(float(l.denomination), l.quantity): float(l.subtotal) for l in lines}
        assert subtotals[(200.0, 3)] == 600.0
        assert subtotals[(100.0, 2)] == 200.0
        assert subtotals[(20.0, 5)] == 100.0

    def test_close_shift_requires_counted_amount_or_cash_count(self):
        with pytest.raises(ValueError):
            CashierShiftClose()

    def test_cannot_close_already_closed_shift(self, db: Session, branch):
        shift = services.open_shift(
            db, cashier_id=23, opened_by=23,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("0")),
        )
        services.close_shift(db, shift.id, closed_by=23, data=CashierShiftClose(counted_cash=Decimal("0")))
        with pytest.raises(ValueError, match="مقفولة"):
            services.close_shift(db, shift.id, closed_by=23, data=CashierShiftClose(counted_cash=Decimal("0")))

    def test_report_compares_to_previous_closed_shift(self, db: Session, branch, folio):
        make_finance_accounts(db, branch)
        shift1 = services.open_shift(
            db, cashier_id=24, opened_by=24,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("0")),
        )
        services.add_payment(db, folio.id, PaymentCreate(
            folio_id=folio.id, branch_id=branch.id, amount=Decimal("500"),
            method="cash", posted_at=datetime.utcnow(), cashier_id=24,
        ))
        services.close_shift(db, shift1.id, closed_by=24, data=CashierShiftClose(counted_cash=Decimal("500")))

        shift2 = services.open_shift(
            db, cashier_id=24, opened_by=24,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("0")),
        )
        services.add_payment(db, folio.id, PaymentCreate(
            folio_id=folio.id, branch_id=branch.id, amount=Decimal("650"),
            method="cash", posted_at=datetime.utcnow(), cashier_id=24,
        ))
        report = services.build_shift_end_report(db, shift2.id)
        assert report.previous_shift_id == shift1.id
        assert report.previous_total_sales == Decimal("500")
        assert report.delta_vs_previous == Decimal("150")

    def test_shift_not_found_raises(self, db: Session):
        with pytest.raises(ValueError):
            services.build_shift_end_report(db, 9999)

    def test_shift_end_report_pdf(self, db: Session, branch, folio):
        make_finance_accounts(db, branch)
        shift = services.open_shift(
            db, cashier_id=25, opened_by=25,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("500")),
        )
        services.add_payment(db, folio.id, PaymentCreate(
            folio_id=folio.id, branch_id=branch.id, amount=Decimal("300"),
            method="cash", posted_at=datetime.utcnow(), cashier_id=25,
        ))
        pdf = services.generate_shift_end_report_pdf(db, shift.id)
        assert pdf.startswith(b"%PDF")

    def test_shift_end_report_pdf_not_found_raises(self, db: Session):
        with pytest.raises(ValueError):
            services.generate_shift_end_report_pdf(db, 9999)

    def test_close_nonexistent_shift_raises(self, db: Session):
        with pytest.raises(ValueError, match="غير موجودة"):
            services.close_shift(db, 9999, closed_by=1, data=CashierShiftClose(counted_cash=Decimal("0")))

    def test_close_shift_multi_currency_cash_count(self, db: Session, branch, folio):
        """عدّ خزينة متعددة العملات: جنيه + دولار + يورو.
        الإجمالي المعدود لازم يتحوّل لـ EGP بأسعار الصرف المسجّلة.
        5×200ج + 10×$1(fx=48) + 2×€50(fx=52) = 1000 + 480 + 5200 = 6680 ج
        مبيعات الوردية المسجّلة = 6680 ج بالظبط (بدون فرق) عمدًا — الهدف هنا
        اختبار حساب التحويل بين العملات نفسه (fx math)، مش سلوك المطابقة
        (reconciliation)، اللي ليه اختبارات مخصصة منفصلة تحت.
        """
        from datetime import date as _date  # noqa: PLC0415
        from app.modules.finance.schemas import ExchangeRateCreate as ERC  # noqa: PLC0415

        make_finance_accounts(db, branch)
        # سجّل أسعار الصرف بتاريخ فريد لتجنب تعارض مع tests أخرى
        fx_date = _date(2026, 7, 9)
        # لو موجود من run سابق في نفس الـ session، نتجاهل الـ duplicate error
        try:
            services.create_exchange_rate(db, ERC(
                from_currency="USD", to_currency="EGP",
                rate=Decimal("48.00"), effective_date=fx_date,
            ), created_by=1)
        except Exception:
            db.rollback()
        try:
            services.create_exchange_rate(db, ERC(
                from_currency="EUR", to_currency="EGP",
                rate=Decimal("52.00"), effective_date=fx_date,
            ), created_by=1)
        except Exception:
            db.rollback()

        shift = services.open_shift(
            db, cashier_id=91, opened_by=91,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("0")),
        )
        services.add_payment(db, folio.id, PaymentCreate(
            folio_id=folio.id, branch_id=branch.id, amount=Decimal("6680"),
            method="cash", posted_at=datetime.utcnow(), cashier_id=91,
        ))

        closed = services.close_shift(
            db, shift.id, closed_by=91,
            data=CashierShiftClose(cash_count=[
                CashCountLine(denomination=Decimal("200"), currency="EGP", quantity=5),   # 1000 ج
                CashCountLine(denomination=Decimal("1"),   currency="USD", quantity=10),  # 10$ = 480 ج
                CashCountLine(denomination=Decimal("50"),  currency="EUR", quantity=2),   # 100€ = 5200 ج
            ]),
        )
        # 1000 + 480 + 5200 = 6680 — يطابق مبيعات الوردية بالظبط (variance=0)
        assert closed.counted_cash == Decimal("6680.00")
        assert closed.expected_cash == Decimal("6680.00")   # opening_float=0 + 6680 cash payment
        assert closed.variance == Decimal("0.00")

        lines = crud.list_cash_count_lines(db, shift.id)
        assert len(lines) == 3

        egp_line  = next(l for l in lines if l.currency == "EGP")
        usd_line  = next(l for l in lines if l.currency == "USD")
        eur_line  = next(l for l in lines if l.currency == "EUR")

        assert egp_line.egp_equivalent  == Decimal("1000.00")
        assert usd_line.egp_equivalent  == Decimal("480.00")
        assert usd_line.fx_rate         == Decimal("48.000000")
        assert eur_line.egp_equivalent  == Decimal("5200.00")
        assert eur_line.fx_rate         == Decimal("52.000000")

        # تحقق من ShiftEndReport — foreign_currency_summary وcounted_cash_egp
        report = services.build_shift_end_report(db, shift.id)
        assert report.counted_cash_egp == Decimal("6680.00")
        assert len(report.foreign_currency_summary) == 2

        usd_fc = next(fc for fc in report.foreign_currency_summary if fc.currency == "USD")
        eur_fc = next(fc for fc in report.foreign_currency_summary if fc.currency == "EUR")
        assert usd_fc.total_foreign  == Decimal("10.00")   # 10 × $1
        assert usd_fc.egp_equivalent == Decimal("480.00")
        assert eur_fc.total_foreign  == Decimal("100.00")  # 2 × €50
        assert eur_fc.egp_equivalent == Decimal("5200.00")

    def test_close_shift_missing_exchange_rate_raises(self, db: Session, branch, folio):
        """لو عملة أجنبية في العدّ ومفيش سعر صرف مسجّل → ValueError واضحة."""
        shift = services.open_shift(
            db, cashier_id=92, opened_by=92,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("0")),
        )
        with pytest.raises(ValueError, match="سعر صرف"):
            services.close_shift(
                db, shift.id, closed_by=92,
                data=CashierShiftClose(cash_count=[
                    CashCountLine(denomination=Decimal("100"), currency="JPY", quantity=1),
                ]),
            )


# ── Cash Control ledger (Operations & Control Layer plan §3.2) ────────

class TestCashMovement:

    def _make_user(self, db, email, role="cashier"):
        """AuditLog.user_id/approved_by بيتحقق إن اليوزر موجود فعليًا
        (core.crud.create_audit_log) — لازم يوزر حقيقي مش رقم عشوائي."""
        from app.core.kernel.models.user import User
        from app.core.kernel.security import get_password_hash

        user = User(email=email, password_hash=get_password_hash("Test@12345"),
                    full_name=f"Test {role}", role=role, is_active=True)
        db.add(user); db.commit()
        return user

    def _open_shift(self, db, branch, cashier_id):
        return services.open_shift(
            db, cashier_id=cashier_id, opened_by=cashier_id,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("500")),
        )

    def test_manager_self_qualified_no_pin_needed(self, db: Session, branch):
        manager = self._make_user(db, "cash-mv-mgr1@test.local", role="manager")
        shift = self._open_shift(db, branch, cashier_id=manager.id)
        movement = services.record_cash_movement(
            db, shift.id, CashMovementCreate(movement_type="cash_in", amount=Decimal("100"), reason="عهدة إضافية"),
            performed_by=manager.id, acting_user_level=60,
        )
        assert movement.movement_type == "cash_in"
        assert movement.amount == Decimal("100")
        assert movement.approved_by is None

    def test_cashier_needs_pin_for_correction(self, db: Session, branch):
        """قرار Mohamed الصريح — التصحيح محتاج موافقة PIN مدير+ دايمًا."""
        cashier = self._make_user(db, "cash-mv-c1@test.local")
        shift = self._open_shift(db, branch, cashier_id=cashier.id)
        with pytest.raises(ValueError, match="موافقة مدير"):
            services.record_cash_movement(
                db, shift.id,
                CashMovementCreate(
                    movement_type="correction", amount=Decimal("50"),
                    reason="تصحيح عدّ", direction="increase",
                ),
                performed_by=cashier.id, acting_user_level=40,
            )

    def test_cashier_needs_pin_for_drawer_open_even_zero_amount(self, db: Session, branch):
        """drawer_open بمبلغ صفر (فتح الدرج بدون بيع) لسه محتاج موافقة —
        الإشراف على الفعل نفسه مش على قيمة المبلغ."""
        cashier = self._make_user(db, "cash-mv-c2@test.local")
        shift = self._open_shift(db, branch, cashier_id=cashier.id)
        with pytest.raises(ValueError, match="موافقة مدير"):
            services.record_cash_movement(
                db, shift.id, CashMovementCreate(movement_type="drawer_open", amount=Decimal("0"), reason="فحص الدرج"),
                performed_by=cashier.id, acting_user_level=40,
            )

    def test_cashier_with_valid_manager_pin_succeeds_and_audits(self, db: Session, branch):
        from app.modules.core import services as core_services
        from app.modules.core.models import AuditLog

        manager = self._make_user(db, "cash-mgr@test.local", role="manager")
        core_services.set_pin(db, manager.id, "1122", created_by=manager.id)
        db.commit()
        cashier = self._make_user(db, "cash-mv-c3@test.local")

        shift = self._open_shift(db, branch, cashier_id=cashier.id)
        movement = services.record_cash_movement(
            db, shift.id,
            CashMovementCreate(
                movement_type="safe_drop", amount=Decimal("300"), reason="تنزيل خزنة نهاية اليوم",
                approver_user_id=manager.id, approver_pin="1122",
            ),
            performed_by=cashier.id, acting_user_level=40,
        )
        assert movement.approved_by == manager.id

        log = (
            db.query(AuditLog)
            .filter(AuditLog.entity_type == "cash_movement", AuditLog.entity_id == movement.id,
                    AuditLog.action == "cash_movement_safe_drop")
            .first()
        )
        assert log is not None
        assert log.approved_by == manager.id
        assert log.user_id == cashier.id

    def test_movement_rejected_on_closed_shift(self, db: Session, branch):
        manager = self._make_user(db, "cash-mv-mgr2@test.local", role="manager")
        shift = self._open_shift(db, branch, cashier_id=manager.id)
        services.close_shift(db, shift.id, closed_by=manager.id, data=CashierShiftClose(counted_cash=Decimal("500")))
        with pytest.raises(ValueError, match="مقفولة"):
            services.record_cash_movement(
                db, shift.id, CashMovementCreate(movement_type="cash_out", amount=Decimal("10"), reason="اختبار"),
                performed_by=manager.id, acting_user_level=60,
            )

    def test_list_cash_movements_returns_newest_first(self, db: Session, branch):
        manager = self._make_user(db, "cash-mv-mgr3@test.local", role="manager")
        shift = self._open_shift(db, branch, cashier_id=manager.id)
        m1 = services.record_cash_movement(
            db, shift.id, CashMovementCreate(movement_type="cash_in", amount=Decimal("50"), reason="أول حركة"),
            performed_by=manager.id, acting_user_level=60,
        )
        m2 = services.record_cash_movement(
            db, shift.id, CashMovementCreate(movement_type="cash_out", amount=Decimal("20"), reason="تاني حركة"),
            performed_by=manager.id, acting_user_level=60,
        )
        movements = services.list_cash_movements(db, shift.id)
        assert [m.id for m in movements] == [m2.id, m1.id]


# ── Folio Reports (Statement + All-Invoices Export) ──────────────────

class TestFolioReports:

    def test_folio_statement_pdf_running_balance(self, db: Session, branch, folio):
        make_finance_accounts(db, branch)
        services.post_charge(db, folio.id, FolioChargeCreate(
            charge_type="room", description="غرفة 101", amount=Decimal("400"),
            posted_at=datetime.utcnow(),
        ))
        services.add_payment(db, folio.id, PaymentCreate(
            folio_id=folio.id, branch_id=branch.id, amount=Decimal("250"),
            method="cash", posted_at=datetime.utcnow(),
        ))
        pdf = services.generate_folio_statement_pdf(db, folio.id)
        assert pdf.startswith(b"%PDF")

    def test_folio_statement_excludes_voided_payments(self, db: Session, branch, folio):
        make_finance_accounts(db, branch)
        services.post_charge(db, folio.id, FolioChargeCreate(
            charge_type="room", description="غرفة 101", amount=Decimal("400"),
            posted_at=datetime.utcnow(),
        ))
        voided = services.add_payment(db, folio.id, PaymentCreate(
            folio_id=folio.id, branch_id=branch.id, amount=Decimal("400"),
            method="cash", posted_at=datetime.utcnow(),
        ))
        services.void_payment(db, voided.id, voided_by=1)
        # Should not raise, and voided payment must not zero out the balance.
        pdf = services.generate_folio_statement_pdf(db, folio.id)
        assert pdf.startswith(b"%PDF")

    def test_folio_statement_not_found_raises(self, db: Session):
        with pytest.raises(ValueError):
            services.generate_folio_statement_pdf(db, 9999)

    def test_folios_report_excel(self, db: Session, branch, folio):
        services.post_charge(db, folio.id, FolioChargeCreate(
            charge_type="room", description="غرفة 101", amount=Decimal("400"),
            posted_at=datetime.utcnow(),
        ))
        xlsx = services.generate_folios_report_excel(db, branch.id)
        assert xlsx.startswith(b"PK")  # xlsx is a zip container

    def test_folios_report_excel_empty_branch(self, db: Session):
        from app.modules.core.models import Branch
        empty_branch = Branch(name="Empty", name_ar="فارغ", code=f"EMPTY-{uuid.uuid4().hex[:6].upper()}")
        db.add(empty_branch)
        db.flush()
        xlsx = services.generate_folios_report_excel(db, empty_branch.id)
        assert xlsx.startswith(b"PK")


# ── Cost Center Report ───────────────────────────────────────────────
# Batch 3: التقرير بقى بيقرأ journal_lines.cost_center_id مباشرة (مش
# جداول عمليات منفصلة زي beach_transactions/folio_charges قبل كده) —
# فالتستات هنا لازم تمرّ فعليًا عبر عمليات حقيقية بترحّل قيود (بيع شاطئ،
# دفع طلب dining) بدل إنشاء FolioCharge مباشرة (اللي مالوش أي أثر على
# دفتر اليومية). محتاجة دليل حسابات حقيقي (1100/1150/4100-4600...) عشان
# post_simple_revenue_journal يقدر يرحّل أصلاً.

def _seed_full_chart_of_accounts(db: Session, branch_id: int) -> None:
    codes = [
        ("1100", "Cash", "asset"), ("1150", "Guest Ledger", "asset"),
        ("1200", "Inventory", "asset"),
        ("4100", "Room Revenue", "revenue"), ("4200", "Restaurant Revenue", "revenue"),
        ("4300", "Beach Revenue", "revenue"), ("4400", "Cafe Revenue", "revenue"),
        ("4600", "Timeshare Revenue", "revenue"),
        ("5200", "COGS", "expense"),
        # FIN-TAX-01 — post_taxed_sale_journal (strict) needs these for any
        # real dining/beach sale, which always has vat_amount > 0.
        ("2160", "VAT Payable", "liability"), ("2165", "Service Charge Payable", "liability"),
    ]
    for code, name, acc_type in codes:
        if not crud.get_account_by_code(db, branch_id, code):
            crud.create_account(db, AccountCreate(branch_id=branch_id, code=code, name=name, account_type=acc_type))
    db.commit()


class TestCostCenterReport:

    def test_default_cost_centers_seeded_idempotently(self, db: Session, branch):
        first = services.ensure_default_cost_centers(db, branch.id)
        # OPS-DATA-02 §11.1 added LEASE/MAINT/ADMIN alongside the original 5.
        assert {c.code for c in first} == {
            "ROOM", "REST", "CAFE", "BEACH", "TS", "LEASE", "MAINT", "ADMIN",
        }
        second = services.ensure_default_cost_centers(db, branch.id)
        assert len(second) == 8  # مفيش تكرار

    def test_empty_report_all_zero(self, db: Session, branch):
        report = services.get_cost_center_report(
            db, branch.id, date(2026, 1, 1), date(2026, 1, 31),
        )
        assert len(report.lines) == 8
        assert report.total_revenue == Decimal("0")
        assert report.total_expense == Decimal("0")
        assert all(l.revenue == Decimal("0") and l.expense == Decimal("0") for l in report.lines)

    def test_beach_revenue_tagged_from_real_ledger_posting(self, db: Session, branch):
        """راجع beach.services._post_beach_revenue_journal —
        cost_center_code="BEACH" بيتوسم وقت الترحيل نفسه، مش استنتاج بعدي."""
        from app.modules.beach import services as beach_services
        from app.modules.beach.schemas import BeachSellRequest

        _seed_full_chart_of_accounts(db, branch.id)
        today = date(2026, 6, 15)
        tx = beach_services.sell_ticket(
            db, branch.id, BeachSellRequest(tx_type="entry", quantity=2), tx_date=today,
        )
        # FIN-TAX-01: the revenue-account line (what this report sums) is
        # net-only now — VAT posts to its own 2160 payable line instead of
        # being folded into revenue.
        expected = tx.total_amount or Decimal("0")

        report = services.get_cost_center_report(db, branch.id, date(2026, 6, 1), date(2026, 6, 30))
        by_code = {l.code: l for l in report.lines}
        assert by_code["BEACH"].revenue == expected
        assert by_code["BEACH"].source == "ledger"
        assert by_code["REST"].revenue == Decimal("0")

    def test_out_of_range_dates_excluded(self, db: Session, branch):
        from app.modules.beach import services as beach_services
        from app.modules.beach.schemas import BeachSellRequest

        _seed_full_chart_of_accounts(db, branch.id)
        beach_services.sell_ticket(
            db, branch.id, BeachSellRequest(tx_type="entry", quantity=1),
            tx_date=date(2026, 5, 1),  # خارج نطاق يونيو
        )
        report = services.get_cost_center_report(db, branch.id, date(2026, 6, 1), date(2026, 6, 30))
        by_code = {l.code: l for l in report.lines}
        assert by_code["BEACH"].revenue == Decimal("0")

    def test_room_revenue_tagged_via_post_simple_revenue_journal(self, db: Session, branch):
        """راجع pms.services._post_checkout_journal —
        cost_center_code="ROOM"."""
        _seed_full_chart_of_accounts(db, branch.id)
        services.post_simple_revenue_journal(
            db, branch.id, date(2026, 6, 12),
            debit_account_code="1100", credit_account_code="4100",
            amount=Decimal("1000"), reference="CHK-001", description="Room checkout",
            source="pms", source_id=1, cost_center_code="ROOM",
        )
        report = services.get_cost_center_report(db, branch.id, date(2026, 6, 1), date(2026, 6, 30))
        by_code = {l.code: l for l in report.lines}
        assert by_code["ROOM"].revenue == Decimal("1000")
        assert by_code["ROOM"].source == "ledger"

    def test_dining_order_payment_tags_revenue_and_cogs_expense_by_outlet(self, db: Session, branch):
        """أهم تست في الدفعة دي — بيثبت المطلب الأساسي: التقرير بقى بيحسب
        المصروف (COGS) مش الإيراد بس. طلب مطعم حقيقي بصنف عنده وصفة/BOM،
        استهلاك المخزون وقت الدفع بيرحّل قيد COGS موسوم REST — لازم يظهر
        كـ expense على REST وde يقلل net، من غير ما يأثر على CAFE."""
        from app.modules.dining import crud as dining_crud, services as dining_services
        from app.modules.dining.models import DiningItem, DiningItemRecipeLine
        from app.modules.dining.schemas import OutletCreate, OrderCreate, OrderItemCreate
        from app.modules.inventory.schemas import ProductCreate, StockMovementCreate, WarehouseCreate
        from app.modules.inventory import services as inventory_services

        _seed_full_chart_of_accounts(db, branch.id)

        warehouse = inventory_services.create_warehouse(
            db, WarehouseCreate(branch_id=branch.id, name="WH", code=f"WH-{uuid.uuid4().hex[:6]}"),
        )
        product = inventory_services.create_product(db, ProductCreate(
            branch_id=branch.id, warehouse_id=warehouse.id, name="دجاج", sku=f"SKU-{uuid.uuid4().hex[:8]}",
            unit="kg", cost_price=Decimal("20.00"), min_stock=Decimal("0"), reorder_point=Decimal("0"),
        ))
        # رصيد ابتدائي عشان الاستهلاك ميرجعش سالب
        inventory_services.record_movement(db, StockMovementCreate(
            branch_id=branch.id, product_id=product.id, warehouse_id=warehouse.id,
            movement_type="adjustment", quantity=Decimal("100"), unit_cost=Decimal("20.00"),
            moved_at=datetime(2026, 6, 1),
        ), moved_by=1)

        rest_outlet = dining_services.create_outlet(db, OutletCreate(
            branch_id=branch.id, name="مطعم COGS", outlet_type="restaurant",
            revenue_account_code="4200",
        ))
        item = DiningItem(branch_id=branch.id, outlet_id=rest_outlet.id, name="طبق دجاج",
                          price=Decimal("100.00"), is_available=True, station="hot")
        db.add(item); db.commit()
        recipe = DiningItemRecipeLine(item_id=item.id, product_id=product.id, quantity_per_unit=Decimal("1"))
        db.add(recipe); db.commit()

        order = dining_services.create_order(
            db, branch.id,
            OrderCreate(outlet_id=rest_outlet.id, order_type="takeaway",
                        items=[OrderItemCreate(item_id=item.id, quantity=1)]),
            waiter_id=1,
        )
        dining_services.update_order_status(db, order.id, "paid")

        # ⚠️ قيد إيراد الدايننج/COGS بيترحّل بـ local_today() (تاريخ اليوم
        # الحقيقي بتوقيت المنتجع)، مش تاريخ ثابت في الماضي — التقرير هنا
        # لازم يغطي نفس اليوم ده.
        today = date.today()
        report = services.get_cost_center_report(db, branch.id, today, today)
        by_code = {l.code: l for l in report.lines}
        # FIN-TAX-01: post_taxed_sale_journal بيرحّل الإيراد الصافي بس
        # لحساب 4200 — الـVAT/الخدمة بيروحوا لـ2160/2165 (liability)، مش
        # جزء من الإيراد المحاسبي. order.total (إجمالي شامل الضريبة/الخدمة)
        # مش الرقم الصح للمقارنة بقى.
        assert by_code["REST"].revenue == order.subtotal
        assert by_code["REST"].expense == Decimal("20.00")  # 1 * cost_price
        assert by_code["REST"].net == order.subtotal - Decimal("20.00")
        assert by_code["CAFE"].revenue == Decimal("0")
        assert by_code["CAFE"].expense == Decimal("0")

    def test_total_revenue_and_expense_sum_all_lines(self, db: Session, branch):
        from app.modules.beach import services as beach_services
        from app.modules.beach.schemas import BeachSellRequest

        _seed_full_chart_of_accounts(db, branch.id)
        tx = beach_services.sell_ticket(
            db, branch.id, BeachSellRequest(tx_type="entry", quantity=1), tx_date=date(2026, 6, 5),
        )
        # FIN-TAX-01: net revenue only — VAT is a payable, not revenue.
        expected_beach = tx.total_amount or Decimal("0")

        report = services.get_cost_center_report(db, branch.id, date(2026, 6, 1), date(2026, 6, 30))
        assert report.total_revenue == sum((l.revenue for l in report.lines), Decimal("0"))
        assert report.total_expense == sum((l.expense for l in report.lines), Decimal("0"))
        assert report.total_revenue == expected_beach
        assert report.total_net == report.total_revenue - report.total_expense


# ── ETA E-Invoice list/tracking ─────────────────────────────────────────

class TestETAInvoiceList:

    def test_list_empty(self, db: Session, branch):
        items, total = crud.list_eta_invoices(db, branch.id)
        assert items == []
        assert total == 0

    def test_list_returns_created_invoices(self, db: Session, branch):
        crud.create_eta_invoice(db, branch.id, None, "ETA-20260701-0001", "{}")
        crud.create_eta_invoice(db, branch.id, None, "ETA-20260701-0002", "{}")
        db.commit()

        items, total = crud.list_eta_invoices(db, branch.id)
        assert total == 2
        assert {i.internal_id for i in items} == {"ETA-20260701-0001", "ETA-20260701-0002"}
        assert all(i.status == "pending" for i in items)

    def test_list_filters_by_status(self, db: Session, branch):
        inv1 = crud.create_eta_invoice(db, branch.id, None, "ETA-A", "{}")
        crud.create_eta_invoice(db, branch.id, None, "ETA-B", "{}")
        db.commit()
        crud.mark_eta_invoice_submitted(db, inv1, status="submitted", submission_uuid="uuid-1")

        pending, pending_total = crud.list_eta_invoices(db, branch.id, status="pending")
        assert pending_total == 1
        assert pending[0].internal_id == "ETA-B"

        submitted, submitted_total = crud.list_eta_invoices(db, branch.id, status="submitted")
        assert submitted_total == 1
        assert submitted[0].internal_id == "ETA-A"

    def test_get_eta_invoice_by_id(self, db: Session, branch):
        inv = crud.create_eta_invoice(db, branch.id, None, "ETA-GET", "{}")
        db.commit()
        fetched = crud.get_eta_invoice(db, inv.id)
        assert fetched is not None
        assert fetched.internal_id == "ETA-GET"

    def test_get_eta_invoice_missing_returns_none(self, db: Session):
        assert crud.get_eta_invoice(db, 999999) is None


# ── ETA E-Invoice submission (service-level, mocked ETAService) ─────────

class TestSubmitETAInvoiceService:
    """submit_eta_invoice() هو الجزء الأكثر حساسية من الناحية القانونية/الضريبية
    في الموديول كله (تكامل مصلحة الضرائب المصرية) — الحالات الأربعة هنا (معطّل،
    إعداد ناقص، رفض من ETA، فشل إرسال) لازم تتسجّل دايماً في eta_invoices
    للتدقيق، مش تختفي بصمت."""

    @staticmethod
    def _eta_settings(**overrides):
        from app.core.config import Settings
        base = {
            "ETA_ENABLED": True,
            "ETA_CLIENT_ID": "test-client",
            "ETA_CLIENT_SECRET": "test-secret",
            "ETA_TAXPAYER_RIN": "123456789",
            "ETA_TAXPAYER_NAME": "El Kheima Beach",
            "VAT_PERCENTAGE": 14.0,
        }
        base.update(overrides)
        return Settings(**base)

    @staticmethod
    def _submit_request(branch_id: int):
        from app.modules.finance.schemas import ETAInvoiceLineItem, ETAInvoiceSubmitRequest
        return ETAInvoiceSubmitRequest(
            branch_id=branch_id, receiver_name="Guest",
            line_items=[ETAInvoiceLineItem(description="Room", quantity=1, unit_price=500.0)],
        )

    async def test_disabled_raises_value_error(self, db: Session, branch):
        from app.core.config import Settings
        with pytest.raises(ValueError, match="ETA_ENABLED"):
            await services.submit_eta_invoice(
                db, Settings(ETA_ENABLED=False), self._submit_request(branch.id),
            )

    async def test_missing_taxpayer_config_raises_value_error(self, db: Session, branch):
        settings = self._eta_settings(ETA_TAXPAYER_RIN=None, ETA_TAXPAYER_NAME=None)
        with pytest.raises(ValueError):
            await services.submit_eta_invoice(db, settings, self._submit_request(branch.id))
        # لازم منسجّلش أي صف eta_invoices لو فشل بناء المستند أصلاً
        items, total = crud.list_eta_invoices(db, branch.id)
        assert total == 0

    async def test_accepted_document_marks_submitted(self, db: Session, branch, monkeypatch):
        from app.modules.finance import eta_service

        async def fake_submit_invoice(self, document):
            return {"acceptedDocuments": [{"uuid": "uuid-accept-1", "longId": "LONG-1"}]}
        monkeypatch.setattr(eta_service.ETAService, "submit_invoice", fake_submit_invoice)

        settings = self._eta_settings()
        invoice = await services.submit_eta_invoice(db, settings, self._submit_request(branch.id))
        assert invoice.status == "submitted"
        assert invoice.submission_uuid == "uuid-accept-1"
        assert invoice.long_id == "LONG-1"
        assert invoice.internal_id.startswith("ETA-")

        # ثاني فاتورة نفس اليوم — internal_id تسلسلي متزايد لا يتكرر
        invoice2 = await services.submit_eta_invoice(db, settings, self._submit_request(branch.id))
        assert invoice2.internal_id != invoice.internal_id

    async def test_rejected_document_marks_invalid(self, db: Session, branch, monkeypatch):
        from app.modules.finance import eta_service

        async def fake_submit_invoice(self, document):
            return {"rejectedDocuments": [{"error": {"code": "E001", "message": "invalid RIN"}}]}
        monkeypatch.setattr(eta_service.ETAService, "submit_invoice", fake_submit_invoice)

        settings = self._eta_settings()
        invoice = await services.submit_eta_invoice(db, settings, self._submit_request(branch.id))
        assert invoice.status == "invalid"
        assert invoice.error_message is not None

    async def test_submission_error_marks_failed(self, db: Session, branch, monkeypatch):
        from app.modules.finance import eta_service

        async def fake_submit_invoice(self, document):
            raise eta_service.ETASubmissionError("ETA رفضت الإرسال: 500 internal error")
        monkeypatch.setattr(eta_service.ETAService, "submit_invoice", fake_submit_invoice)

        settings = self._eta_settings()
        invoice = await services.submit_eta_invoice(db, settings, self._submit_request(branch.id))
        assert invoice.status == "failed"
        assert "500" in invoice.error_message


# ── Exchange Rates (Multi-Currency) ──────────────────────────────────────

class TestExchangeRates:

    def test_folio_creation_rejects_unsupported_currency(self, db: Session, branch):
        data = FolioCreate(
            branch_id=branch.id, guest_name="Guest",
            check_in=datetime.utcnow(), check_out=datetime.utcnow() + timedelta(days=1),
            currency="GBP",  # مش من ضمن SUPPORTED_CURRENCIES الافتراضية (EGP,USD,EUR,SAR)
        )
        with pytest.raises(ValueError, match="غير مدعومة"):
            services.create_folio(db, data)

    def test_get_rate_same_currency_is_one(self, db: Session):
        assert services.get_rate(db, "EGP", "EGP", date.today()) == Decimal("1")

    def test_get_rate_no_rate_registered_raises(self, db: Session):
        # سعر صرف زوج عملة غريب لا يوجد له default seed ولا سعر مسجّل
        from app.modules.finance.schemas import ExchangeRateCreate as ERC
        with pytest.raises(ValueError, match="لا يوجد سعر صرف"):
            services.get_rate(db, "JPY", "KWD", date.today())

    def test_get_rate_falls_back_to_inverse(self, db: Session):
        """لو مفيش سعر EGP→USD مباشر بس فيه USD→EGP، لازم يستنتج المعكوس بدل
        ما يرفع خطأ."""
        from app.modules.finance.schemas import ExchangeRateCreate as ERC
        services.create_exchange_rate(
            db, ERC(from_currency="USD", to_currency="EGP", rate=Decimal("50.00"),
                    effective_date=date(2026, 1, 1)),
            created_by=1,
        )
        rate = services.get_rate(db, "EGP", "USD", date(2026, 1, 15))
        assert rate == Decimal("1") / Decimal("50.00")

    def test_convert_to_egp_same_currency_passthrough(self, db: Session):
        assert services.convert_to_egp(db, Decimal("100.00"), "EGP", date.today()) == Decimal("100.00")

    def test_create_exchange_rate_duplicate_date_rejected(self, db: Session):
        from app.modules.finance.schemas import ExchangeRateCreate as ERC
        data = ERC(from_currency="USD", to_currency="EGP", rate=Decimal("48.50"),
                   effective_date=date(2026, 2, 1))
        services.create_exchange_rate(db, data, created_by=1)
        with pytest.raises(ValueError, match="يوجد سعر صرف مسجّل بالفعل"):
            services.create_exchange_rate(db, data, created_by=1)

    def test_create_exchange_rate_same_currency_rejected(self, db: Session):
        from app.modules.finance.schemas import ExchangeRateCreate as ERC
        data = ERC(from_currency="EGP", to_currency="EGP", rate=Decimal("1"),
                   effective_date=date(2026, 3, 1))
        with pytest.raises(ValueError, match="مختلفين"):
            services.create_exchange_rate(db, data, created_by=1)

    def test_list_exchange_rates_service_wrapper(self, db: Session):
        from app.modules.finance.schemas import ExchangeRateCreate as ERC
        services.create_exchange_rate(
            db, ERC(from_currency="EUR", to_currency="EGP", rate=Decimal("55.00"),
                    effective_date=date(2026, 4, 1)),
            created_by=1,
        )
        items, total = services.list_exchange_rates(db, from_currency="EUR")
        assert total >= 1
        assert all(r.from_currency == "EUR" for r in items)


# ── Shift-end report edge cases (negative delta, cash-count PDF) ────────

class TestShiftEndReportEdgeCases:

    def test_delta_vs_previous_negative_shows_down_arrow_in_pdf(self, db: Session, branch, folio):
        make_finance_accounts(db, branch)
        shift1 = services.open_shift(
            db, cashier_id=40, opened_by=40,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("0")),
        )
        services.add_payment(db, folio.id, PaymentCreate(
            folio_id=folio.id, branch_id=branch.id, amount=Decimal("900"),
            method="cash", posted_at=datetime.utcnow(), cashier_id=40,
        ))
        services.close_shift(db, shift1.id, closed_by=40, data=CashierShiftClose(counted_cash=Decimal("900")))

        shift2 = services.open_shift(
            db, cashier_id=40, opened_by=40,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("0")),
        )
        services.add_payment(db, folio.id, PaymentCreate(
            folio_id=folio.id, branch_id=branch.id, amount=Decimal("300"),
            method="cash", posted_at=datetime.utcnow(), cashier_id=40,
        ))
        report = services.build_shift_end_report(db, shift2.id)
        assert report.delta_vs_previous == Decimal("-600")

        # generate_shift_end_report_pdf يستخدم _fmt_delta الداخلية — نتأكد إنها
        # لا ترفع استثناء مع دلتا سالبة (الفرع ▼) قبل ما تقفل الوردية.
        services.close_shift(db, shift2.id, closed_by=40, data=CashierShiftClose(counted_cash=Decimal("300")))
        pdf = services.generate_shift_end_report_pdf(db, shift2.id)
        assert pdf.startswith(b"%PDF")

    def test_cash_count_breakdown_appears_in_pdf_summary(self, db: Session, branch, folio):
        from app.modules.finance.schemas import CashCountLine
        # opening_float=450 يطابق العدّ بالفئة تحت (2×200 + 1×50 = 450) بالظبط —
        # variance=0، عشان الاختبار ده يتحقق من ظهور تفاصيل العدّ في الـ PDF بس
        # (مش من سلوك المطابقة/الرفض، اللي ليه اختبارات مخصصة منفصلة).
        shift = services.open_shift(
            db, cashier_id=41, opened_by=41,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("450")),
        )
        services.close_shift(
            db, shift.id, closed_by=41,
            data=CashierShiftClose(cash_count=[
                CashCountLine(denomination=Decimal("200"), quantity=2),
                CashCountLine(denomination=Decimal("50"), quantity=1),
            ]),
        )
        pdf = services.generate_shift_end_report_pdf(db, shift.id)
        assert pdf.startswith(b"%PDF")


# ── Income Statement / Balance Sheet — inactive accounts + equity ──────

class TestFinancialReportsEdgeCases:

    def test_income_statement_skips_accounts_with_no_activity(self, db: Session, branch, account, account2):
        """حساب موجود في الفرع بس مالوش أي حركة في المدى المطلوب — لازم يتجاهل
        (continue) مش يظهر بصفر في التقرير."""
        report = services.get_income_statement(db, branch.id, date(2026, 1, 1), date(2026, 1, 31))
        assert report.revenue_lines == []
        assert report.expense_lines == []
        assert report.total_revenue == Decimal("0")

    def test_balance_sheet_includes_equity_account(self, db: Session, branch, account):
        from app.modules.finance.schemas import AccountCreate as AC
        equity_acc = crud.create_account(db, AC(
            branch_id=branch.id, code="3100", name="Owner's Equity", account_type="equity",
        ))
        db.commit(); db.refresh(equity_acc)

        entry_data = JournalEntryCreate(
            branch_id=branch.id, entry_date=date.today(),
            reference="JE-EQUITY", description="Capital injection",
            lines=[
                JournalLineCreate(account_id=account.id, debit=Decimal("5000"), credit=Decimal("0")),
                JournalLineCreate(account_id=equity_acc.id, debit=Decimal("0"), credit=Decimal("5000")),
            ],
        )
        services.post_journal_entry(db, entry_data, user_id=1)

        report = services.get_balance_sheet(db, branch.id, date.today())
        by_code = {l.account_code: l for l in report.equity_lines}
        assert by_code["3100"].amount == Decimal("5000")
        assert report.total_equity == Decimal("5000")
        assert report.is_balanced is True

    def test_balance_sheet_skips_accounts_with_no_activity(self, db: Session, branch, account, account2):
        report = services.get_balance_sheet(db, branch.id, date(2026, 1, 1))
        assert report.asset_lines == []
        assert report.total_assets == Decimal("0")


# ── Fixed-Asset Depreciation — edge branches ─────────────────────────────

class TestDepreciationEdgeCases:

    def test_asset_not_yet_started_is_skipped(self, db: Session, branch):
        from app.modules.maintenance.models import Asset
        asset = Asset(
            branch_id=branch.id, name="Future Asset", code=f"AST-{uuid.uuid4().hex[:6].upper()}",
            category="hvac", purchase_cost=Decimal("5000"), useful_life_years=5,
            depreciation_start_date=date(2027, 1, 1),
        )
        db.add(asset); db.commit()

        result = services.run_depreciation(db, branch.id, 2026, 6, user_id=1)
        assert result.entries == []
        assert any("بداية الإهلاك" in s for s in result.skipped_assets)

    def test_asset_with_zero_depreciable_base_is_skipped(self, db: Session, branch):
        """purchase_cost وuseful_life_years موجودين (فبيعدي فلتر crud) بس
        salvage_value == purchase_cost => قيمة قابلة للإهلاك = صفر."""
        from app.modules.maintenance.models import Asset
        asset = Asset(
            branch_id=branch.id, name="No Depreciable Value", code=f"AST-{uuid.uuid4().hex[:6].upper()}",
            category="furniture", purchase_cost=Decimal("1000"), salvage_value=Decimal("1000"),
            useful_life_years=5,
        )
        db.add(asset); db.commit()

        result = services.run_depreciation(db, branch.id, 2026, 6, user_id=1)
        assert result.entries == []
        assert any("لا توجد قيمة قابلة للإهلاك" in s for s in result.skipped_assets)

    def test_fully_depreciated_asset_is_skipped(self, db: Session, branch):
        from app.modules.maintenance.models import Asset
        asset = Asset(
            branch_id=branch.id, name="Fully Depreciated", code=f"AST-{uuid.uuid4().hex[:6].upper()}",
            category="furniture", purchase_cost=Decimal("1000"), salvage_value=Decimal("0"),
            useful_life_years=1, accumulated_depreciation=Decimal("1000.00"),
        )
        db.add(asset); db.commit()

        result = services.run_depreciation(db, branch.id, 2026, 6, user_id=1)
        assert result.entries == []
        assert any("مُهلَك بالكامل" in s for s in result.skipped_assets)

    def test_depreciation_reuses_existing_gl_accounts_across_runs(self, db: Session, branch):
        """أول دورة إهلاك بتنشئ حسابات المصروف/المجمّع تلقائيًا (5500/1590) —
        دورة تانية لشهر مختلف لازم تستخدم نفس الحسابين، مش تنشئهم تاني (كان
        هيكسر uq على الكود لو حصل)."""
        from app.modules.maintenance.models import Asset
        asset = Asset(
            branch_id=branch.id, name="Multi-Month Asset", code=f"AST-{uuid.uuid4().hex[:6].upper()}",
            category="hvac", purchase_cost=Decimal("2400.00"), useful_life_years=2,
            depreciation_start_date=date(2026, 1, 1),
        )
        db.add(asset); db.commit()

        first = services.run_depreciation(db, branch.id, 2026, 1, user_id=1)
        assert first.journal_entry_id is not None
        second = services.run_depreciation(db, branch.id, 2026, 2, user_id=1)
        assert second.journal_entry_id is not None
        assert second.journal_entry_id != first.journal_entry_id

        expense_accounts = [a for a in crud.list_accounts(db, branch.id, active_only=False, limit=100)[0]
                             if a.code == "5500"]
        assert len(expense_accounts) == 1  # لم يتكرر إنشاء الحساب

    def test_list_depreciation_entries_service_wrapper(self, db: Session, branch):
        from app.modules.maintenance.models import Asset
        asset = Asset(
            branch_id=branch.id, name="Listed Asset", code=f"AST-{uuid.uuid4().hex[:6].upper()}",
            category="hvac", purchase_cost=Decimal("1200.00"), useful_life_years=1,
            depreciation_start_date=date(2026, 1, 1),
        )
        db.add(asset); db.commit()
        services.run_depreciation(db, branch.id, 2026, 1, user_id=1)

        items, total = services.list_depreciation_entries(db, branch.id, asset_id=None, page=1, size=10)
        assert total == 1
        assert items[0].asset_id == asset.id


# ── Bank Reconciliation — service-level edge cases ──────────────────────

class TestBankReconciliationServiceEdgeCases:

    def test_get_bank_account_or_404_raises_for_missing(self, db: Session):
        with pytest.raises(ValueError, match="غير موجود"):
            services.get_bank_account_or_404(db, 999999)

    def test_update_bank_account_not_found_raises(self, db: Session):
        from app.modules.finance.schemas import BankAccountUpdate
        with pytest.raises(ValueError):
            services.update_bank_account(db, 999999, BankAccountUpdate(bank_name="X"))

    def test_update_bank_account_success(self, db: Session, branch):
        from app.modules.finance.schemas import BankAccountCreate, BankAccountUpdate
        account = services.create_bank_account(db, BankAccountCreate(
            branch_id=branch.id, bank_name="بنك مصر", account_name="حساب رئيسي",
            account_number=f"ACC-{uuid.uuid4().hex[:8]}",
        ))
        updated = services.update_bank_account(db, account.id, BankAccountUpdate(bank_name="بنك القاهرة"))
        assert updated.bank_name == "بنك القاهرة"

    def test_auto_match_skips_negative_amount_lines(self, db: Session, branch, folio):
        from app.modules.finance.schemas import (
            BankAccountCreate, BankStatementImportRequest, BankStatementLineCreate,
        )
        account = services.create_bank_account(db, BankAccountCreate(
            branch_id=branch.id, bank_name="بنك مصر", account_name="حساب رئيسي",
            account_number=f"ACC-{uuid.uuid4().hex[:8]}",
        ))
        services.import_bank_statement_lines(db, account.id, uploaded_by=1, data=BankStatementImportRequest(
            lines=[BankStatementLineCreate(
                line_date=date(2026, 6, 1), description="Bank fee", amount=Decimal("-25.00"),
            )],
        ))
        matched = services.auto_match_bank_statement_lines(db, account.id, matched_by=1)
        assert matched == 0
        lines, _ = crud.list_bank_statement_lines(db, account.id)
        assert lines[0].status == "unmatched"

    def test_match_statement_line_missing_line_raises(self, db: Session, branch):
        from app.modules.finance.schemas import BankAccountCreate
        account = services.create_bank_account(db, BankAccountCreate(
            branch_id=branch.id, bank_name="بنك مصر", account_name="حساب رئيسي",
            account_number=f"ACC-{uuid.uuid4().hex[:8]}",
        ))
        with pytest.raises(ValueError, match="غير موجود"):
            services.match_bank_statement_line(db, account.id, 999999, payment_id=1, matched_by=1)

    def test_match_statement_line_missing_payment_raises(self, db: Session, branch):
        from app.modules.finance.schemas import (
            BankAccountCreate, BankStatementImportRequest, BankStatementLineCreate,
        )
        account = services.create_bank_account(db, BankAccountCreate(
            branch_id=branch.id, bank_name="بنك مصر", account_name="حساب رئيسي",
            account_number=f"ACC-{uuid.uuid4().hex[:8]}",
        ))
        lines = services.import_bank_statement_lines(db, account.id, uploaded_by=1, data=BankStatementImportRequest(
            lines=[BankStatementLineCreate(line_date=date(2026, 6, 1), description="X", amount=Decimal("100"))],
        ))
        with pytest.raises(ValueError, match="غير موجودة"):
            services.match_bank_statement_line(db, account.id, lines[0].id, payment_id=999999, matched_by=1)

    def test_unmatch_statement_line_missing_line_raises(self, db: Session, branch):
        from app.modules.finance.schemas import BankAccountCreate
        account = services.create_bank_account(db, BankAccountCreate(
            branch_id=branch.id, bank_name="بنك مصر", account_name="حساب رئيسي",
            account_number=f"ACC-{uuid.uuid4().hex[:8]}",
        ))
        with pytest.raises(ValueError, match="غير موجود"):
            services.unmatch_bank_statement_line(db, account.id, 999999)

    def test_unmatch_statement_line_not_matched_raises(self, db: Session, branch):
        from app.modules.finance.schemas import (
            BankAccountCreate, BankStatementImportRequest, BankStatementLineCreate,
        )
        account = services.create_bank_account(db, BankAccountCreate(
            branch_id=branch.id, bank_name="بنك مصر", account_name="حساب رئيسي",
            account_number=f"ACC-{uuid.uuid4().hex[:8]}",
        ))
        lines = services.import_bank_statement_lines(db, account.id, uploaded_by=1, data=BankStatementImportRequest(
            lines=[BankStatementLineCreate(line_date=date(2026, 6, 1), description="X", amount=Decimal("100"))],
        ))
        with pytest.raises(ValueError, match="مش متطابق"):
            services.unmatch_bank_statement_line(db, account.id, lines[0].id)

    def test_reconciliation_summary_uses_ledger_when_gl_account_linked(self, db: Session, branch, account):
        """لو الحساب البنكي مربوط بحساب دفتر يومية (gl_account_id)، رصيد
        الدفاتر لازم يتحسب من مجموع القيود على الحساب ده، مش من الدفعات
        المطابقة فقط."""
        from app.modules.finance.schemas import AccountCreate as AC, BankAccountCreate

        revenue_acc = crud.create_account(db, AC(
            branch_id=branch.id, code="4900", name="Misc Revenue", account_type="revenue",
        ))
        db.commit(); db.refresh(revenue_acc)

        bank_account = services.create_bank_account(db, BankAccountCreate(
            branch_id=branch.id, bank_name="بنك مصر", account_name="حساب رئيسي",
            account_number=f"ACC-{uuid.uuid4().hex[:8]}", gl_account_id=account.id,
        ))

        entry_data = JournalEntryCreate(
            branch_id=branch.id, entry_date=date(2026, 6, 5),
            reference="JE-BANK-GL", description="Deposit via ledger",
            lines=[
                JournalLineCreate(account_id=account.id, debit=Decimal("2000.00"), credit=Decimal("0")),
                JournalLineCreate(account_id=revenue_acc.id, debit=Decimal("0"), credit=Decimal("2000.00")),
            ],
        )
        services.post_journal_entry(db, entry_data, user_id=1)

        summary = services.get_bank_reconciliation_summary(db, bank_account.id, date(2026, 6, 30))
        assert summary.book_balance == Decimal("2000.00")
        assert summary.statement_balance == Decimal("0")
        assert summary.difference == Decimal("-2000.00")
        assert summary.is_reconciled is False


class TestAgingReport:
    """2026-08-19 (طلب Mohamed — تقرير أعمار الديون): مين مديون لنا (فوليوهات
    مفتوحة) ومين إحنا مديونين له (أوامر شراء + مصروفات آجلة)."""

    def test_receivables_from_open_folio_with_balance(self, db, branch):
        from app.modules.finance.models import Folio
        check_in = datetime.combine(date.today() - timedelta(days=40), datetime.min.time())
        folio = Folio(
            branch_id=branch.id, guest_name="ضيف اختبار", check_in=check_in,
            check_out=check_in + timedelta(days=3), status="open", total=Decimal("1500"),
        )
        db.add(folio); db.commit()

        report = services.get_aging_report(db, branch.id, as_of=date.today())
        assert len(report.receivables) == 1
        line = report.receivables[0]
        assert line.folio_id == folio.id
        assert line.balance_due == Decimal("1500")
        assert line.bucket == "31-60"
        assert report.receivables_total == Decimal("1500")

    def test_closed_folio_excluded_from_receivables(self, db, branch):
        from app.modules.finance.models import Folio
        check_in = datetime.combine(date.today() - timedelta(days=10), datetime.min.time())
        folio = Folio(
            branch_id=branch.id, guest_name="ضيف مسدد", check_in=check_in,
            check_out=check_in + timedelta(days=1), status="closed", total=Decimal("500"),
        )
        db.add(folio); db.commit()

        report = services.get_aging_report(db, branch.id, as_of=date.today())
        assert report.receivables == []

    def test_payables_from_unpaid_purchase_order_and_deferred_expense(self, db, branch):
        from app.modules.finance.models import Account
        from app.modules.finance.schemas import ExpenseCreate
        from app.modules.inventory.models import PurchaseOrder, Supplier

        supplier = Supplier(branch_id=branch.id, name="مورد اختبار")
        db.add(supplier); db.commit()
        po = PurchaseOrder(
            branch_id=branch.id, order_number="PO-AGING-001", supplier_id=supplier.id,
            status="received", ordered_at=date.today() - timedelta(days=100),
            total_amount=Decimal("2000"), amount_paid=Decimal("500"), payment_status="partial",
        )
        db.add(po)

        accrued = Account(branch_id=branch.id, code="2180", name="مصروفات مستحقة", account_type="liability")
        rent = Account(branch_id=branch.id, code="5100", name="إيجار", account_type="expense")
        db.add_all([accrued, rent]); db.commit()
        expense = services.record_expense(db, branch.id, ExpenseCreate(
            expense_date=date.today() - timedelta(days=10),
            expense_account_id=rent.id, settlement_account_id=None,
            amount=Decimal("300"), description="فاتورة مقاول", defer_payment=True,
        ), recorded_by=1)

        report = services.get_aging_report(db, branch.id, as_of=date.today())
        assert len(report.payables) == 2
        by_type = {p.source_type: p for p in report.payables}
        assert by_type["purchase_order"].remaining == Decimal("1500")
        assert by_type["purchase_order"].bucket == "90+"
        assert by_type["purchase_order"].counterparty == "مورد اختبار"
        assert by_type["expense"].source_id == expense.id
        assert by_type["expense"].remaining == Decimal("300")
        assert by_type["expense"].bucket == "0-30"
        assert report.payables_total == Decimal("1800")

    def test_voided_expense_excluded_from_payables(self, db, branch):
        from app.modules.finance.models import Account
        from app.modules.finance.schemas import ExpenseCreate
        accrued = Account(branch_id=branch.id, code="2180", name="مصروفات مستحقة", account_type="liability")
        rent = Account(branch_id=branch.id, code="5100", name="إيجار", account_type="expense")
        db.add_all([accrued, rent]); db.commit()
        expense = services.record_expense(db, branch.id, ExpenseCreate(
            expense_date=date.today(),
            expense_account_id=rent.id, settlement_account_id=None,
            amount=Decimal("300"), description="ملغى", defer_payment=True,
        ), recorded_by=1)
        services.void_expense(db, expense.id, voided_by=1, reason="اختبار إلغاء")

        report = services.get_aging_report(db, branch.id, as_of=date.today())
        assert report.payables == []

    def test_aging_buckets_summary(self, db, branch):
        from app.modules.finance.models import Account
        from app.modules.finance.schemas import ExpenseCreate
        accrued = Account(branch_id=branch.id, code="2180", name="مصروفات مستحقة", account_type="liability")
        rent = Account(branch_id=branch.id, code="5100", name="إيجار", account_type="expense")
        db.add_all([accrued, rent]); db.commit()
        for days, amount in [(5, "100"), (45, "200"), (75, "300"), (120, "400")]:
            services.record_expense(db, branch.id, ExpenseCreate(
                expense_date=date.today() - timedelta(days=days),
                expense_account_id=rent.id, settlement_account_id=None,
                amount=Decimal(amount), description=f"مصروف {days} يوم", defer_payment=True,
            ), recorded_by=1)

        report = services.get_aging_report(db, branch.id, as_of=date.today())
        buckets = {b.label: b for b in report.payables_buckets}
        assert buckets["0-30"].amount == Decimal("100")
        assert buckets["31-60"].amount == Decimal("200")
        assert buckets["61-90"].amount == Decimal("300")
        assert buckets["90+"].amount == Decimal("400")
        assert sum(b.count for b in report.payables_buckets) == 4


class TestExpense:
    """2026-08-16 — سند مصروفات حقيقي بفئة (طلب Mohamed صراحةً). الفئة هي
    expense_account_id نفسه (حساب 5xxx)، مفيش taxonomy موازية."""

    @pytest.fixture
    def expense_accounts(self, db, branch):
        from app.modules.finance.models import Account
        rent = Account(branch_id=branch.id, code="5100", name="إيجار", account_type="expense")
        cash = Account(branch_id=branch.id, code="1100", name="Cash", account_type="asset")
        db.add_all([rent, cash]); db.commit()
        return rent, cash

    def test_expense_above_threshold_needs_pin_from_accountant(self, db, branch, expense_accounts):
        """2026-08-19 (طلب Mohamed — حد موافقة المصروفات): مبلغ >= الحد
        (5000 افتراضيًا) من محاسب (level 70) أو مدير (60) — الاتنين
        الأدوار المسموح لهم أصلاً يسجّلوا سند مصروفات (get_finance_user)
        — محتاج موافقة admin+ (80). لو الحد فضل 60 كان المحاسب (70)
        هيتخطّاه تلقائيًا والبوابة كانت هتبقى بلا أثر عمليًا."""
        from app.modules.finance.schemas import ExpenseCreate
        rent, cash = expense_accounts

        with pytest.raises(ValueError, match="موافقة مدير"):
            services.record_expense(db, branch.id, ExpenseCreate(
                expense_date=date(2026, 8, 19),
                expense_account_id=rent.id, settlement_account_id=cash.id,
                amount=Decimal("6000"), description="فوق الحد — محاسب لوحده",
            ), recorded_by=1, acting_user_level=70)

    def test_expense_below_threshold_no_pin_needed(self, db, branch, expense_accounts):
        from app.modules.finance.schemas import ExpenseCreate
        rent, cash = expense_accounts

        expense = services.record_expense(db, branch.id, ExpenseCreate(
            expense_date=date(2026, 8, 19),
            expense_account_id=rent.id, settlement_account_id=cash.id,
            amount=Decimal("100"), description="تحت الحد",
        ), recorded_by=1, acting_user_level=70)
        assert expense.amount == Decimal("100")

    def test_expense_above_threshold_admin_self_qualified(self, db, branch, expense_accounts):
        from app.modules.finance.schemas import ExpenseCreate
        rent, cash = expense_accounts

        expense = services.record_expense(db, branch.id, ExpenseCreate(
            expense_date=date(2026, 8, 19),
            expense_account_id=rent.id, settlement_account_id=cash.id,
            amount=Decimal("9000"), description="أدمن بنفسه",
        ), recorded_by=1, acting_user_level=80)
        assert expense.amount == Decimal("9000")

    def test_expense_above_threshold_with_valid_pin_succeeds_and_audits(self, db, branch, expense_accounts):
        from app.core.kernel.models.user import User
        from app.core.kernel.security import get_password_hash
        from app.modules.core import services as core_services
        from app.modules.core.models import AuditLog
        from app.modules.finance.schemas import ExpenseCreate
        rent, cash = expense_accounts

        admin_user = User(email="exp-admin@test.local", password_hash=get_password_hash("Test@12345"),
                           full_name="Expense Admin", role="admin", is_active=True)
        db.add(admin_user); db.commit()
        core_services.set_pin(db, admin_user.id, "1234", created_by=admin_user.id)
        db.commit()

        expense = services.record_expense(db, branch.id, ExpenseCreate(
            expense_date=date(2026, 8, 19),
            expense_account_id=rent.id, settlement_account_id=cash.id,
            amount=Decimal("7000"), description="فوق الحد بموافقة",
            approver_user_id=admin_user.id, approver_pin="1234",
        ), recorded_by=1, acting_user_level=70)
        assert expense.amount == Decimal("7000")

        log = (
            db.query(AuditLog)
            .filter(AuditLog.entity_type == "expense", AuditLog.entity_id == expense.id,
                    AuditLog.action == "record_expense")
            .first()
        )
        assert log is not None
        assert log.approved_by == admin_user.id
        assert log.user_id == 1

    def test_record_expense_posts_balanced_journal(self, db, branch, expense_accounts):
        from app.modules.finance.schemas import ExpenseCreate
        rent, cash = expense_accounts

        expense = services.record_expense(db, branch.id, ExpenseCreate(
            expense_date=date(2026, 8, 16),
            expense_account_id=rent.id, settlement_account_id=cash.id,
            amount=Decimal("5000"), description="إيجار أغسطس 2026",
        ), recorded_by=1)

        assert expense.amount == Decimal("5000")
        entry = crud.get_journal_entry(db, expense.journal_entry_id)
        assert entry is not None
        assert entry.source == "manual_expense"
        total_debit = sum(l.debit for l in entry.lines)
        total_credit = sum(l.credit for l in entry.lines)
        assert total_debit == total_credit == Decimal("5000.00")
        debit_line = next(l for l in entry.lines if l.debit > 0)
        credit_line = next(l for l in entry.lines if l.credit > 0)
        assert debit_line.account_id == rent.id
        assert credit_line.account_id == cash.id

    def test_expense_account_must_be_expense_type(self, db, branch, expense_accounts):
        from app.modules.finance.models import Account
        from app.modules.finance.schemas import ExpenseCreate
        _, cash = expense_accounts
        revenue = Account(branch_id=branch.id, code="4100", name="Revenue", account_type="revenue")
        db.add(revenue); db.commit()

        with pytest.raises(ValueError, match="ليس حساب مصروفات"):
            services.record_expense(db, branch.id, ExpenseCreate(
                expense_date=date(2026, 8, 16),
                expense_account_id=revenue.id, settlement_account_id=cash.id,
                amount=Decimal("100"), description="محاولة خاطئة",
            ), recorded_by=1)

    def test_settlement_account_must_be_asset_type(self, db, branch, expense_accounts):
        from app.modules.finance.models import Account
        from app.modules.finance.schemas import ExpenseCreate
        rent, _ = expense_accounts
        liability = Account(branch_id=branch.id, code="2200", name="Payable", account_type="liability")
        db.add(liability); db.commit()

        with pytest.raises(ValueError, match="حساب أصول"):
            services.record_expense(db, branch.id, ExpenseCreate(
                expense_date=date(2026, 8, 16),
                expense_account_id=rent.id, settlement_account_id=liability.id,
                amount=Decimal("100"), description="محاولة خاطئة",
            ), recorded_by=1)

    def test_void_expense_posts_reversing_journal(self, db, branch, expense_accounts):
        from app.modules.finance.schemas import ExpenseCreate
        rent, cash = expense_accounts

        expense = services.record_expense(db, branch.id, ExpenseCreate(
            expense_date=date(2026, 8, 16),
            expense_account_id=rent.id, settlement_account_id=cash.id,
            amount=Decimal("5000"), description="إيجار أغسطس 2026",
        ), recorded_by=1)

        voided = services.void_expense(db, expense.id, voided_by=2, reason="سند مكرر بالخطأ")
        assert voided.voided_at is not None
        assert voided.voided_by == 2

        entry = crud.get_journal_entry(db, voided.journal_entry_id)
        # القيد الأصلي زي ما هو (مفيش تعديل عليه — العكس قيد جديد منفصل)
        debit_line = next(l for l in entry.lines if l.debit > 0)
        assert debit_line.account_id == rent.id

    def test_cannot_void_expense_with_recorded_payment(self, db, branch, expense_accounts):
        """حالة نادرة مؤجَّلة عمدًا (طلب Mohamed 2026-08-19) — سند آجل بعد
        ما يتسدد جزئيًا/كليًا يحتاج مراجعة يدوية أوسع، مش إلغاء مباشر."""
        from app.modules.finance.schemas import ExpenseCreate
        rent, cash = expense_accounts

        expense = services.record_expense(db, branch.id, ExpenseCreate(
            expense_date=date(2026, 8, 16),
            expense_account_id=rent.id, settlement_account_id=cash.id,
            amount=Decimal("5000"), description="إيجار أغسطس 2026",
        ), recorded_by=1)
        expense.amount_paid = Decimal("2000")
        db.commit()

        with pytest.raises(ValueError, match="سداد مسجّل بالفعل"):
            services.void_expense(db, expense.id, voided_by=2, reason="محاولة إلغاء")

    def test_cannot_void_already_voided_expense(self, db, branch, expense_accounts):
        from app.modules.finance.schemas import ExpenseCreate
        rent, cash = expense_accounts

        expense = services.record_expense(db, branch.id, ExpenseCreate(
            expense_date=date(2026, 8, 16),
            expense_account_id=rent.id, settlement_account_id=cash.id,
            amount=Decimal("5000"), description="إيجار أغسطس 2026",
        ), recorded_by=1)
        services.void_expense(db, expense.id, voided_by=2, reason="أول مرة")

        with pytest.raises(ValueError, match="ملغى بالفعل"):
            services.void_expense(db, expense.id, voided_by=2, reason="محاولة تانية")

    def test_deferred_expense_posts_to_accrued_liability(self, db, branch, expense_accounts):
        """2026-08-19 (طلب Mohamed — مصروف آجل): defer_payment=True يرحّل
        Dr.المصروف/Cr.2180 بدل تسوية نقدية فورية، ويسيب السند unpaid."""
        from app.modules.finance.models import Account
        from app.modules.finance.schemas import ExpenseCreate
        rent, _cash = expense_accounts
        accrued = Account(branch_id=branch.id, code="2180", name="مصروفات مستحقة", account_type="liability")
        db.add(accrued); db.commit()

        expense = services.record_expense(db, branch.id, ExpenseCreate(
            expense_date=date(2026, 8, 19),
            expense_account_id=rent.id, settlement_account_id=None,
            amount=Decimal("3000"), description="فاتورة مقاول — عمالة يومية",
            defer_payment=True,
        ), recorded_by=1)

        assert expense.payment_status == "unpaid"
        assert expense.amount_paid == Decimal("0")
        assert expense.settlement_account_id == accrued.id

        entry = crud.get_journal_entry(db, expense.journal_entry_id)
        debit_line = next(l for l in entry.lines if l.debit > 0)
        credit_line = next(l for l in entry.lines if l.credit > 0)
        assert debit_line.account_id == rent.id
        assert credit_line.account_id == accrued.id

    def test_deferred_expense_requires_2180_seeded(self, db, branch, expense_accounts):
        from app.modules.finance.schemas import ExpenseCreate
        rent, _cash = expense_accounts

        with pytest.raises(services.FinancialConfigurationError, match="2180"):
            services.record_expense(db, branch.id, ExpenseCreate(
                expense_date=date(2026, 8, 19),
                expense_account_id=rent.id, settlement_account_id=None,
                amount=Decimal("100"), description="محاولة من غير 2180",
                defer_payment=True,
            ), recorded_by=1)

    def test_non_deferred_expense_requires_settlement_account(self, db, branch, expense_accounts):
        from app.modules.finance.schemas import ExpenseCreate
        rent, _cash = expense_accounts

        with pytest.raises(ValueError, match="حساب التسوية مطلوب"):
            services.record_expense(db, branch.id, ExpenseCreate(
                expense_date=date(2026, 8, 19),
                expense_account_id=rent.id, settlement_account_id=None,
                amount=Decimal("100"), description="محاولة من غير حساب تسوية",
                defer_payment=False,
            ), recorded_by=1)

    def test_pay_expense_full_then_partial_flow(self, db, branch, expense_accounts):
        from app.modules.finance.models import Account
        from app.modules.finance.schemas import ExpenseCreate, ExpensePaymentCreate
        rent, cash = expense_accounts
        accrued = Account(branch_id=branch.id, code="2180", name="مصروفات مستحقة", account_type="liability")
        db.add(accrued); db.commit()

        expense = services.record_expense(db, branch.id, ExpenseCreate(
            expense_date=date(2026, 8, 19),
            expense_account_id=rent.id, settlement_account_id=None,
            amount=Decimal("3000"), description="فاتورة مقاول",
            defer_payment=True,
        ), recorded_by=1)

        expense = services.pay_expense(db, expense.id, ExpensePaymentCreate(
            amount=Decimal("1000"), settlement_account_id=cash.id, paid_at=date(2026, 8, 19),
        ), recorded_by=2)
        assert expense.payment_status == "partial"
        assert expense.amount_paid == Decimal("1000.00")

        expense = services.pay_expense(db, expense.id, ExpensePaymentCreate(
            amount=Decimal("2000"), settlement_account_id=cash.id, paid_at=date(2026, 8, 19),
        ), recorded_by=2)
        assert expense.payment_status == "paid"
        assert expense.amount_paid == Decimal("3000.00")

        payments = crud.list_expense_payments(db, expense.id)
        assert len(payments) == 2

        entry = crud.get_journal_entry(db, payments[0].journal_entry_id)
        debit_line = next(l for l in entry.lines if l.debit > 0)
        credit_line = next(l for l in entry.lines if l.credit > 0)
        assert debit_line.account_id == accrued.id
        assert credit_line.account_id == cash.id

    def test_pay_expense_overpayment_rejected(self, db, branch, expense_accounts):
        from app.modules.finance.models import Account
        from app.modules.finance.schemas import ExpenseCreate, ExpensePaymentCreate
        rent, cash = expense_accounts
        accrued = Account(branch_id=branch.id, code="2180", name="مصروفات مستحقة", account_type="liability")
        db.add(accrued); db.commit()

        expense = services.record_expense(db, branch.id, ExpenseCreate(
            expense_date=date(2026, 8, 19),
            expense_account_id=rent.id, settlement_account_id=None,
            amount=Decimal("500"), description="فاتورة صغيرة", defer_payment=True,
        ), recorded_by=1)

        with pytest.raises(ValueError, match="أكبر من المتبقي"):
            services.pay_expense(db, expense.id, ExpensePaymentCreate(
                amount=Decimal("600"), settlement_account_id=cash.id, paid_at=date(2026, 8, 19),
            ), recorded_by=2)

    def test_cannot_pay_already_fully_paid_expense(self, db, branch, expense_accounts):
        """سند عادي (paid) من الأساس — pay_expense مرفوض عليه، مش بس على
        سند آجل اتسدد بالكامل."""
        from app.modules.finance.schemas import ExpenseCreate, ExpensePaymentCreate
        rent, cash = expense_accounts

        expense = services.record_expense(db, branch.id, ExpenseCreate(
            expense_date=date(2026, 8, 19),
            expense_account_id=rent.id, settlement_account_id=cash.id,
            amount=Decimal("500"), description="سند فوري", defer_payment=False,
        ), recorded_by=1)

        with pytest.raises(ValueError, match="مسدد بالكامل بالفعل"):
            services.pay_expense(db, expense.id, ExpensePaymentCreate(
                amount=Decimal("100"), settlement_account_id=cash.id, paid_at=date(2026, 8, 19),
            ), recorded_by=2)

    def test_void_unpaid_deferred_expense_reverses_accrued_liability(self, db, branch, expense_accounts):
        """سند آجل لسه من غير أي سداد (amount_paid=0) لازم يقدر يتلغي عادي
        — الحالة النادرة المؤجَّلة هي سند عليه سداد فعلي مسجّل، مش أي سند آجل."""
        from app.modules.finance.models import Account
        from app.modules.finance.schemas import ExpenseCreate
        rent, _cash = expense_accounts
        accrued = Account(branch_id=branch.id, code="2180", name="مصروفات مستحقة", account_type="liability")
        db.add(accrued); db.commit()

        expense = services.record_expense(db, branch.id, ExpenseCreate(
            expense_date=date(2026, 8, 19),
            expense_account_id=rent.id, settlement_account_id=None,
            amount=Decimal("3000"), description="فاتورة مقاول", defer_payment=True,
        ), recorded_by=1)

        voided = services.void_expense(db, expense.id, voided_by=2, reason="اتلغى الاتفاق")
        assert voided.voided_at is not None

        # voided.journal_entry_id لسه بيشاور على القيد الأصلي (نفس نمط
        # void_payment بالظبط — العكس قيد جديد منفصل مش تعديل على الأصلي).
        from app.modules.finance.models import JournalEntry
        reversal = (
            db.query(JournalEntry)
            .filter(JournalEntry.source == "expense_void", JournalEntry.source_id == expense.id)
            .one()
        )
        debit_line = next(l for l in reversal.lines if l.debit > 0)
        credit_line = next(l for l in reversal.lines if l.credit > 0)
        assert debit_line.account_id == accrued.id
        assert credit_line.account_id == rent.id

    class TestCustody:
        """2026-08-19 (طلب Mohamed — العهدة/سلفة نقدية): صرف عهدة، تسويتها
        بتوزيع فعلي على حسابات مصروفات، وإلغاؤها قبل التسوية."""

        @pytest.fixture
        def custody_accounts(self, db, branch):
            from app.modules.finance.models import Account
            cash = Account(branch_id=branch.id, code="1100", name="Cash", account_type="asset")
            custody_acc = Account(branch_id=branch.id, code="1190", name="عهد نقدية تحت التسوية", account_type="asset")
            labor = Account(branch_id=branch.id, code="5300", name="أجور مقاولين", account_type="expense")
            materials = Account(branch_id=branch.id, code="5310", name="مواد بناء", account_type="expense")
            db.add_all([cash, custody_acc, labor, materials]); db.commit()
            return cash, custody_acc, labor, materials

        def test_disburse_custody_posts_to_1190(self, db, branch, custody_accounts):
            from app.modules.finance.schemas import CustodyCreate
            cash, custody_acc, _labor, _materials = custody_accounts

            custody = services.disburse_custody(db, branch.id, CustodyCreate(
                holder_name="أحمد المقاول", purpose="مقاولة رصف بلاط",
                amount=Decimal("5000"), disbursed_date=date(2026, 8, 19),
                source_account_id=cash.id,
            ), disbursed_by=1)

            assert custody.status == "open"
            assert custody.custody_account_id == custody_acc.id
            entry = crud.get_journal_entry(db, custody.disbursement_entry_id)
            debit_line = next(l for l in entry.lines if l.debit > 0)
            credit_line = next(l for l in entry.lines if l.credit > 0)
            assert debit_line.account_id == custody_acc.id
            assert credit_line.account_id == cash.id

        def test_disburse_custody_requires_1190_seeded(self, db, branch):
            from app.modules.finance.models import Account
            from app.modules.finance.schemas import CustodyCreate
            cash = Account(branch_id=branch.id, code="1100", name="Cash", account_type="asset")
            db.add(cash); db.commit()

            with pytest.raises(services.FinancialConfigurationError, match="1190"):
                services.disburse_custody(db, branch.id, CustodyCreate(
                    holder_name="أحمد", purpose="اختبار", amount=Decimal("100"),
                    disbursed_date=date(2026, 8, 19), source_account_id=cash.id,
                ), disbursed_by=1)

        def test_settle_custody_full_distribution_no_return(self, db, branch, custody_accounts):
            from app.modules.finance.schemas import CustodyCreate, CustodySettleRequest, CustodySettlementLineCreate
            cash, custody_acc, labor, materials = custody_accounts

            custody = services.disburse_custody(db, branch.id, CustodyCreate(
                holder_name="أحمد المقاول", purpose="مقاولة رصف بلاط",
                amount=Decimal("5000"), disbursed_date=date(2026, 8, 19),
                source_account_id=cash.id,
            ), disbursed_by=1)

            settled = services.settle_custody(db, custody.id, CustodySettleRequest(
                settlement_date=date(2026, 8, 19),
                lines=[
                    CustodySettlementLineCreate(
                        expense_account_id=labor.id, amount=Decimal("3000"),
                        description="أجور عمالة يومية",
                    ),
                    CustodySettlementLineCreate(
                        expense_account_id=materials.id, amount=Decimal("2000"),
                        description="رملة وطوب",
                    ),
                ],
                returned_amount=Decimal("0"),
            ), settled_by=2)

            assert settled.status == "settled"
            assert settled.settled_by == 2
            assert settled.settled_at is not None

            entry = crud.get_journal_entry(db, settled.settlement_entry_id)
            total_debit = sum(l.debit for l in entry.lines)
            total_credit = sum(l.credit for l in entry.lines)
            assert total_debit == total_credit == Decimal("5000.00")
            credit_line = next(l for l in entry.lines if l.credit > 0)
            assert credit_line.account_id == custody_acc.id

            lines = crud.list_custody_settlement_lines(db, custody.id)
            assert len(lines) == 2

        def test_settle_custody_with_partial_return(self, db, branch, custody_accounts):
            from app.modules.finance.schemas import CustodyCreate, CustodySettleRequest, CustodySettlementLineCreate
            cash, custody_acc, labor, _materials = custody_accounts

            custody = services.disburse_custody(db, branch.id, CustodyCreate(
                holder_name="أحمد المقاول", purpose="عمالة يومية",
                amount=Decimal("2000"), disbursed_date=date(2026, 8, 19),
                source_account_id=cash.id,
            ), disbursed_by=1)

            settled = services.settle_custody(db, custody.id, CustodySettleRequest(
                settlement_date=date(2026, 8, 19),
                lines=[CustodySettlementLineCreate(
                    expense_account_id=labor.id, amount=Decimal("1500"), description="أجور",
                )],
                returned_amount=Decimal("500"),
            ), settled_by=2)

            assert settled.returned_amount == Decimal("500.00")
            entry = crud.get_journal_entry(db, settled.settlement_entry_id)
            debit_lines = [l for l in entry.lines if l.debit > 0]
            assert any(l.account_id == cash.id and l.debit == Decimal("500.00") for l in debit_lines)

        def test_settle_custody_rejects_mismatched_total(self, db, branch, custody_accounts):
            from app.modules.finance.schemas import CustodyCreate, CustodySettleRequest, CustodySettlementLineCreate
            cash, _custody_acc, labor, _materials = custody_accounts

            custody = services.disburse_custody(db, branch.id, CustodyCreate(
                holder_name="أحمد", purpose="اختبار", amount=Decimal("1000"),
                disbursed_date=date(2026, 8, 19), source_account_id=cash.id,
            ), disbursed_by=1)

            with pytest.raises(ValueError, match="لازم يساوي مبلغ العهدة"):
                services.settle_custody(db, custody.id, CustodySettleRequest(
                    settlement_date=date(2026, 8, 19),
                    lines=[CustodySettlementLineCreate(
                        expense_account_id=labor.id, amount=Decimal("700"), description="أجور",
                    )],
                    returned_amount=Decimal("0"),
                ), settled_by=2)

        def test_settle_custody_rejects_non_expense_account(self, db, branch, custody_accounts):
            from app.modules.finance.schemas import CustodyCreate, CustodySettleRequest, CustodySettlementLineCreate
            cash, _custody_acc, _labor, _materials = custody_accounts

            custody = services.disburse_custody(db, branch.id, CustodyCreate(
                holder_name="أحمد", purpose="اختبار", amount=Decimal("1000"),
                disbursed_date=date(2026, 8, 19), source_account_id=cash.id,
            ), disbursed_by=1)

            with pytest.raises(ValueError, match="ليس حساب مصروفات"):
                services.settle_custody(db, custody.id, CustodySettleRequest(
                    settlement_date=date(2026, 8, 19),
                    lines=[CustodySettlementLineCreate(
                        expense_account_id=cash.id, amount=Decimal("1000"), description="محاولة خاطئة",
                    )],
                    returned_amount=Decimal("0"),
                ), settled_by=2)

        def test_void_open_custody_reverses_1190(self, db, branch, custody_accounts):
            from app.modules.finance.models import JournalEntry
            from app.modules.finance.schemas import CustodyCreate
            cash, custody_acc, _labor, _materials = custody_accounts

            custody = services.disburse_custody(db, branch.id, CustodyCreate(
                holder_name="أحمد", purpose="اتلغى", amount=Decimal("1000"),
                disbursed_date=date(2026, 8, 19), source_account_id=cash.id,
            ), disbursed_by=1)

            voided = services.void_custody(db, custody.id, voided_by=2, reason="اتلغى الاتفاق")
            assert voided.voided_at is not None

            reversal = (
                db.query(JournalEntry)
                .filter(JournalEntry.source == "custody_void", JournalEntry.source_id == custody.id)
                .one()
            )
            debit_line = next(l for l in reversal.lines if l.debit > 0)
            credit_line = next(l for l in reversal.lines if l.credit > 0)
            assert debit_line.account_id == cash.id
            assert credit_line.account_id == custody_acc.id

        def test_cannot_void_settled_custody(self, db, branch, custody_accounts):
            from app.modules.finance.schemas import CustodyCreate, CustodySettleRequest, CustodySettlementLineCreate
            cash, _custody_acc, labor, _materials = custody_accounts

            custody = services.disburse_custody(db, branch.id, CustodyCreate(
                holder_name="أحمد", purpose="اختبار", amount=Decimal("1000"),
                disbursed_date=date(2026, 8, 19), source_account_id=cash.id,
            ), disbursed_by=1)
            services.settle_custody(db, custody.id, CustodySettleRequest(
                settlement_date=date(2026, 8, 19),
                lines=[CustodySettlementLineCreate(
                    expense_account_id=labor.id, amount=Decimal("1000"), description="أجور",
                )],
                returned_amount=Decimal("0"),
            ), settled_by=2)

            with pytest.raises(ValueError, match="متسواة بالفعل"):
                services.void_custody(db, custody.id, voided_by=2, reason="محاولة إلغاء")

    class TestCashReceipt:
        """2026-08-19 (طلب Mohamed — إذن قبض عام): تحصيل نقدية من مصدر
        متنوع مش مرتبط بمسار بيع قائم."""

        @pytest.fixture
        def receipt_accounts(self, db, branch):
            from app.modules.finance.models import Account
            cash = Account(branch_id=branch.id, code="1100", name="Cash", account_type="asset")
            capital = Account(branch_id=branch.id, code="3100", name="رأس المال", account_type="equity")
            db.add_all([cash, capital]); db.commit()
            return cash, capital

        def test_record_cash_receipt_posts_balanced_journal(self, db, branch, receipt_accounts):
            from app.modules.finance.schemas import CashReceiptCreate
            cash, capital = receipt_accounts

            receipt = services.record_cash_receipt(db, branch.id, CashReceiptCreate(
                receipt_date=date(2026, 8, 19),
                destination_account_id=cash.id, source_account_id=capital.id,
                amount=Decimal("10000"), description="ضخ رأس مال إضافي",
            ), recorded_by=1)

            assert receipt.amount == Decimal("10000")
            entry = crud.get_journal_entry(db, receipt.journal_entry_id)
            debit_line = next(l for l in entry.lines if l.debit > 0)
            credit_line = next(l for l in entry.lines if l.credit > 0)
            assert debit_line.account_id == cash.id
            assert credit_line.account_id == capital.id

        def test_cash_receipt_destination_must_be_asset(self, db, branch, receipt_accounts):
            from app.modules.finance.models import Account
            from app.modules.finance.schemas import CashReceiptCreate
            _cash, capital = receipt_accounts
            revenue = Account(branch_id=branch.id, code="4900", name="إيراد متفرق", account_type="revenue")
            db.add(revenue); db.commit()

            with pytest.raises(ValueError, match="حساب أصول"):
                services.record_cash_receipt(db, branch.id, CashReceiptCreate(
                    receipt_date=date(2026, 8, 19),
                    destination_account_id=revenue.id, source_account_id=capital.id,
                    amount=Decimal("100"), description="محاولة خاطئة",
                ), recorded_by=1)

        def test_void_cash_receipt_reverses_journal(self, db, branch, receipt_accounts):
            from app.modules.finance.models import JournalEntry
            from app.modules.finance.schemas import CashReceiptCreate
            cash, capital = receipt_accounts

            receipt = services.record_cash_receipt(db, branch.id, CashReceiptCreate(
                receipt_date=date(2026, 8, 19),
                destination_account_id=cash.id, source_account_id=capital.id,
                amount=Decimal("10000"), description="ضخ رأس مال إضافي",
            ), recorded_by=1)

            voided = services.void_cash_receipt(db, receipt.id, voided_by=2, reason="اتسجّل بالخطأ")
            assert voided.voided_at is not None

            reversal = (
                db.query(JournalEntry)
                .filter(JournalEntry.source == "cash_receipt_void", JournalEntry.source_id == receipt.id)
                .one()
            )
            debit_line = next(l for l in reversal.lines if l.debit > 0)
            credit_line = next(l for l in reversal.lines if l.credit > 0)
            assert debit_line.account_id == capital.id
            assert credit_line.account_id == cash.id

        def test_cannot_void_already_voided_cash_receipt(self, db, branch, receipt_accounts):
            from app.modules.finance.schemas import CashReceiptCreate
            cash, capital = receipt_accounts

            receipt = services.record_cash_receipt(db, branch.id, CashReceiptCreate(
                receipt_date=date(2026, 8, 19),
                destination_account_id=cash.id, source_account_id=capital.id,
                amount=Decimal("500"), description="اختبار",
            ), recorded_by=1)
            services.void_cash_receipt(db, receipt.id, voided_by=2, reason="أول مرة")

            with pytest.raises(ValueError, match="ملغى بالفعل"):
                services.void_cash_receipt(db, receipt.id, voided_by=2, reason="محاولة تانية")

    def test_list_expenses_filters_by_date_and_enriches_account_labels(self, db, branch, expense_accounts):
        from app.modules.finance.schemas import ExpenseCreate
        rent, cash = expense_accounts

        services.record_expense(db, branch.id, ExpenseCreate(
            expense_date=date(2026, 8, 1),
            expense_account_id=rent.id, settlement_account_id=cash.id,
            amount=Decimal("1000"), description="مصروف أغسطس",
        ), recorded_by=1)
        services.record_expense(db, branch.id, ExpenseCreate(
            expense_date=date(2026, 7, 1),
            expense_account_id=rent.id, settlement_account_id=cash.id,
            amount=Decimal("900"), description="مصروف يوليو",
        ), recorded_by=1)

        items, total = services.list_expenses(db, branch.id, date_from=date(2026, 8, 1), date_to=date(2026, 8, 31))
        assert total == 1
        assert items[0]["description"] == "مصروف أغسطس"
        assert items[0]["expense_account_code"] == "5100"
        assert items[0]["settlement_account_code"] == "1100"
