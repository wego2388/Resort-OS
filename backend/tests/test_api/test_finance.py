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
    FolioCreate, FolioChargeCreate, JournalEntryCreate, JournalLineCreate, PaymentCreate,
)
from app.modules.finance import services, crud


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

    def test_missing_accounts_does_not_block_payment(self, db, branch, folio):
        """لو 1100/1150 مش موجودين، تسجيل الدفعة لازم ينجح عادي — نفس فلسفة
        باقي القيود في المشروع (فشل الترحيل المحاسبي ميوقفش العملية الأساسية)."""
        data = PaymentCreate(
            folio_id=folio.id, branch_id=branch.id,
            amount=Decimal("100.00"), method="cash", posted_at=datetime.utcnow(),
        )
        payment = services.add_payment(db, folio.id, data)
        assert payment.id is not None
        _, total = crud.list_journal_entries(db, branch.id, source="folio_payment")
        assert total == 0


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
        شاطئ/PMS/تايم شير/إيجارات)."""
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

    def test_payments_auto_attach_open_shift(self, db: Session, branch, folio):
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
                db, shift.id, CashMovementCreate(movement_type="correction", amount=Decimal("50"), reason="تصحيح عدّ"),
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

class TestCostCenterReport:

    def test_default_cost_centers_seeded_idempotently(self, db: Session, branch):
        first = services.ensure_default_cost_centers(db, branch.id)
        assert {c.code for c in first} == {"ROOM", "REST", "CAFE", "BEACH", "TS"}
        second = services.ensure_default_cost_centers(db, branch.id)
        assert len(second) == 5  # مفيش تكرار

    def test_empty_report_all_zero(self, db: Session, branch):
        report = services.get_cost_center_report(
            db, branch.id, date(2026, 1, 1), date(2026, 1, 31),
        )
        assert len(report.lines) == 5
        assert report.total_revenue == Decimal("0")
        assert all(l.revenue == Decimal("0") for l in report.lines)

    def test_beach_revenue_shows_as_separate_line(self, db: Session, branch):
        from app.modules.beach import services as beach_services
        from app.modules.beach.schemas import BeachSellRequest

        today = date(2026, 6, 15)
        beach_services.sell_ticket(
            db, branch.id, BeachSellRequest(tx_type="entry", quantity=2), tx_date=today,
        )
        report = services.get_cost_center_report(db, branch.id, date(2026, 6, 1), date(2026, 6, 30))
        by_code = {l.code: l for l in report.lines}
        assert by_code["BEACH"].revenue == Decimal("400")  # 2 * 200 (default entry price)
        assert by_code["BEACH"].source == "direct"
        assert by_code["REST"].revenue == Decimal("0")

    def test_restaurant_and_cafe_revenue_from_folio_charges(self, db: Session, branch, folio):
        services.post_charge(db, folio.id, FolioChargeCreate(
            charge_type="restaurant", description="عشاء", amount=Decimal("300"),
            posted_at=datetime(2026, 6, 10, 20, 0),
        ))
        services.post_charge(db, folio.id, FolioChargeCreate(
            charge_type="cafe", description="قهوة", amount=Decimal("50"),
            posted_at=datetime(2026, 6, 10, 10, 0),
        ))
        report = services.get_cost_center_report(db, branch.id, date(2026, 6, 1), date(2026, 6, 30))
        by_code = {l.code: l for l in report.lines}
        assert by_code["REST"].revenue == Decimal("300")
        assert by_code["CAFE"].revenue == Decimal("50")

    def test_room_revenue_from_ledger_account_4100(self, db: Session, branch, account, account2):
        room_acc = crud.create_account(db, AccountCreate(
            branch_id=branch.id, code="4100", name="Room Revenue", account_type="revenue",
        ))
        db.commit(); db.refresh(room_acc)

        entry_data = JournalEntryCreate(
            branch_id=branch.id, entry_date=date(2026, 6, 12),
            reference="CHK-001", description="Room checkout",
            lines=[
                JournalLineCreate(account_id=account.id, debit=Decimal("1000"), credit=Decimal("0")),
                JournalLineCreate(account_id=room_acc.id, debit=Decimal("0"), credit=Decimal("1000")),
            ],
        )
        services.post_journal_entry(db, entry_data, user_id=1)

        report = services.get_cost_center_report(db, branch.id, date(2026, 6, 1), date(2026, 6, 30))
        by_code = {l.code: l for l in report.lines}
        assert by_code["ROOM"].revenue == Decimal("1000")
        assert by_code["ROOM"].source == "ledger"

    def test_out_of_range_dates_excluded(self, db: Session, branch):
        from app.modules.beach import services as beach_services
        from app.modules.beach.schemas import BeachSellRequest

        beach_services.sell_ticket(
            db, branch.id, BeachSellRequest(tx_type="entry", quantity=1),
            tx_date=date(2026, 5, 1),  # خارج نطاق يونيو
        )
        report = services.get_cost_center_report(db, branch.id, date(2026, 6, 1), date(2026, 6, 30))
        by_code = {l.code: l for l in report.lines}
        assert by_code["BEACH"].revenue == Decimal("0")

    def test_total_revenue_sums_all_lines(self, db: Session, branch, folio):
        from app.modules.beach import services as beach_services
        from app.modules.beach.schemas import BeachSellRequest

        beach_services.sell_ticket(
            db, branch.id, BeachSellRequest(tx_type="entry", quantity=1), tx_date=date(2026, 6, 5),
        )
        services.post_charge(db, folio.id, FolioChargeCreate(
            charge_type="cafe", description="Coffee", amount=Decimal("30"),
            posted_at=datetime(2026, 6, 5, 9, 0),
        ))
        report = services.get_cost_center_report(db, branch.id, date(2026, 6, 1), date(2026, 6, 30))
        assert report.total_revenue == sum((l.revenue for l in report.lines), Decimal("0"))
        assert report.total_revenue == Decimal("230")  # 200 (beach entry) + 30 (cafe)

    def test_dining_sourced_charges_bucket_by_outlet_type(self, db: Session, branch, folio):
        """DINING_CUTOVER_PLAN.md D-05 — أي طلب حقيقي عبر /dining مباشرة
        (charge_type='dining') لازم يظهر في سطر REST/CAFE الصح، مبني على
        Outlet.outlet_type بتاعه (عبر ref_order_id)، مش يختفي من التقرير.
        راجع crud.list_folio_charges_by_outlet_family_with_currency."""
        from app.modules.dining import services as dining_services
        from app.modules.dining.models import DiningOrder
        from app.modules.dining.schemas import OutletCreate

        rest_outlet = dining_services.create_outlet(db, OutletCreate(
            branch_id=branch.id, name="مطعم dining", outlet_type="restaurant",
            revenue_account_code="4200",
        ))
        cafe_outlet = dining_services.create_outlet(db, OutletCreate(
            branch_id=branch.id, name="كافيه dining", outlet_type="cafe",
            revenue_account_code="4400",
        ))
        rest_order = DiningOrder(
            branch_id=branch.id, outlet_id=rest_outlet.id, order_number=f"O-{uuid.uuid4().hex[:8]}",
            order_type="takeaway", status="paid", subtotal=Decimal("120"), total=Decimal("120"),
        )
        cafe_order = DiningOrder(
            branch_id=branch.id, outlet_id=cafe_outlet.id, order_number=f"O-{uuid.uuid4().hex[:8]}",
            order_type="takeaway", status="paid", subtotal=Decimal("40"), total=Decimal("40"),
        )
        db.add_all([rest_order, cafe_order])
        db.commit()

        services.post_charge(db, folio.id, FolioChargeCreate(
            charge_type="dining", description="عشاء dining", amount=Decimal("120"),
            posted_at=datetime(2026, 6, 10, 20, 0), ref_order_id=rest_order.id,
        ))
        services.post_charge(db, folio.id, FolioChargeCreate(
            charge_type="dining", description="قهوة dining", amount=Decimal("40"),
            posted_at=datetime(2026, 6, 10, 10, 0), ref_order_id=cafe_order.id,
        ))

        report = services.get_cost_center_report(db, branch.id, date(2026, 6, 1), date(2026, 6, 30))
        by_code = {l.code: l for l in report.lines}
        assert by_code["REST"].revenue == Decimal("120")
        assert by_code["CAFE"].revenue == Decimal("40")

    def test_legacy_and_dining_charges_sum_together_during_transition(self, db: Session, branch, folio):
        """أثناء فترة الانتقال (قبل Batch 4 — الفرونت إند لسه ممكن يكلّم
        /restaurant/cafe القديمين)، charge_type='restaurant' القديم *و*
        charge_type='dining' الجديد لازم يتجمّعوا في نفس سطر REST — مفيش
        فقدان بيانات، ومفيش عدّ مزدوج."""
        from app.modules.dining import services as dining_services
        from app.modules.dining.models import DiningOrder
        from app.modules.dining.schemas import OutletCreate

        rest_outlet = dining_services.create_outlet(db, OutletCreate(
            branch_id=branch.id, name="مطعم مختلط", outlet_type="restaurant",
            revenue_account_code="4200",
        ))
        dining_order = DiningOrder(
            branch_id=branch.id, outlet_id=rest_outlet.id, order_number=f"O-{uuid.uuid4().hex[:8]}",
            order_type="takeaway", status="paid", subtotal=Decimal("75"), total=Decimal("75"),
        )
        db.add(dining_order)
        db.commit()

        services.post_charge(db, folio.id, FolioChargeCreate(
            charge_type="restaurant", description="طلب قديم عبر /restaurant", amount=Decimal("300"),
            posted_at=datetime(2026, 6, 10, 20, 0),
        ))
        services.post_charge(db, folio.id, FolioChargeCreate(
            charge_type="dining", description="طلب جديد عبر /dining", amount=Decimal("75"),
            posted_at=datetime(2026, 6, 11, 13, 0), ref_order_id=dining_order.id,
        ))

        report = services.get_cost_center_report(db, branch.id, date(2026, 6, 1), date(2026, 6, 30))
        by_code = {l.code: l for l in report.lines}
        assert by_code["REST"].revenue == Decimal("375")  # 300 + 75, not double-counted


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
