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
    AccountCreate, CashCountLine, CashierShiftClose, CashierShiftOpen, ConditionalDiscountCreate,
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
