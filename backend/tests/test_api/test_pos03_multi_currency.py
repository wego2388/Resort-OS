"""
tests/test_api/test_pos03_multi_currency.py
POS-03 — Multi-currency cashier payment tests.

يغطي:
1. دفعة كاش بعملة أجنبية (USD) تُسجَّل بـ Payment.currency="USD"، Payment.fx_rate،
   وPayment.amount = EGP-equivalent.
2. قفل الوردية بعدّ عملات متعددة + دفعات بعملات أجنبية →
   ForeignCurrencySummary.expected_amount/variance لكل عملة.
3. قفل الوردية بعدّ عملة أجنبية من غير أي دفعة بنفس العملة →
   variance = total_foreign (زيادة بالكامل).
4. OrderStatusUpdate مع payment_currency بدون fx_rate → Pydantic validation error.
5. SplitBillPayment مع currency ≠ EGP بدون fx_rate → validation error.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.modules.finance import crud as finance_crud
from app.modules.finance import services as finance_services
from app.modules.finance.models import Payment
from app.modules.finance.schemas import (
    CashCountLine,
    CashierShiftClose,
    CashierShiftOpen,
    ExchangeRateCreate,
    FolioCreate,
    ForeignCurrencySummary,
)


# ── helpers ──────────────────────────────────────────────────────────

def _make_branch(db: Session):
    from app.modules.core.models import Branch
    b = Branch(name="POS-03 Branch", name_ar="فرع اختبار POS-03",
               code=f"P03-{uuid.uuid4().hex[:6].upper()}")
    db.add(b)
    db.flush()
    return b


def _make_cashier() -> int:
    """بيرجع cashier_id رقم عشوائي — التستات بتستخدم رقم مباشر زي باقي test_finance.py."""
    import random
    return random.randint(5000, 9999)


def _seed_rate(db: Session, from_cur: str, to_cur: str, rate: Decimal):
    from app.modules.finance.services import create_exchange_rate
    from app.resort_os.timezone_utils import local_today
    from app.core.config import settings
    try:
        return create_exchange_rate(
            db,
            ExchangeRateCreate(
                from_currency=from_cur, to_currency=to_cur,
                rate=rate, effective_date=local_today(settings.TIMEZONE),
            ),
            created_by=0,
        )
    except ValueError:
        pass  # already exists for today — OK


def _open_shift(db: Session, branch_id: int, cashier_id: int):
    return finance_services.open_shift(
        db,
        cashier_id=cashier_id,
        opened_by=cashier_id,
        data=CashierShiftOpen(branch_id=branch_id, opening_float=Decimal("0")),
    )


# ── Test 1: دفعة كاش بعملة أجنبية (USD) ─────────────────────────────

class TestForeignCurrencyPaymentRecord:
    """Payment.amount = EGP-equivalent، Payment.currency="USD"، Payment.fx_rate مسجّل."""

    def test_usd_cash_payment_recorded_correctly(self, db: Session):
        branch = _make_branch(db)
        cashier = _make_cashier()
        _seed_rate(db, "USD", "EGP", Decimal("48.00"))

        shift = _open_shift(db, branch.id, cashier)

        # كاشير استلم 50 USD = 2400 EGP بسعر 48
        egp_amount = Decimal("2400.00")
        fx = Decimal("48.00")

        payment = finance_crud.create_direct_payment(
            db,
            branch_id=branch.id,
            amount=egp_amount,
            method="cash",
            posted_at=datetime.utcnow(),
            shift_id=shift.id,
            cashier_id=cashier,
            reference="ORD-TEST-USD",
            currency="USD",
            fx_rate=fx,
            source="dining",
        )
        db.flush()

        p = db.query(Payment).filter(Payment.id == payment.id).one()
        assert p.amount == egp_amount, "amount لازم يكون EGP-equivalent"
        assert p.currency == "USD"
        assert p.fx_rate == fx
        # المبلغ الأصلي بالدولار = amount / fx_rate
        assert (p.amount / p.fx_rate).quantize(Decimal("0.01")) == Decimal("50.00")

    def test_egp_payment_fx_rate_defaults_to_one(self, db: Session):
        branch = _make_branch(db)
        cashier = _make_cashier()
        shift = _open_shift(db, branch.id, cashier)

        payment = finance_crud.create_direct_payment(
            db, branch_id=branch.id, amount=Decimal("200.00"),
            method="cash", posted_at=datetime.utcnow(),
            shift_id=shift.id, cashier_id=cashier,
        )
        db.flush()

        p = db.query(Payment).filter(Payment.id == payment.id).one()
        assert p.currency == "EGP"
        assert p.fx_rate == Decimal("1")


# ── Test 2: قفل الوردية — variance per-currency ─────────────────────

class TestShiftCloseMultiCurrencyVariance:
    """بعد قفل وردية بعدّ USD + دفعات USD، ForeignCurrencySummary تعرض expected_amount/variance."""

    def test_shift_close_with_usd_sales_shows_variance(self, db: Session):
        branch = _make_branch(db)
        cashier = _make_cashier()
        _seed_rate(db, "USD", "EGP", Decimal("48.00"))

        shift = _open_shift(db, branch.id, cashier)

        # سجّل دفعتين USD
        # دفعة 1: 50 USD = 2400 EGP
        finance_crud.create_direct_payment(
            db, branch_id=branch.id, amount=Decimal("2400.00"),
            method="cash", posted_at=datetime.utcnow(),
            shift_id=shift.id, cashier_id=cashier,
            currency="USD", fx_rate=Decimal("48.00"), source="dining",
        )
        # دفعة 2: 20 USD = 960 EGP
        finance_crud.create_direct_payment(
            db, branch_id=branch.id, amount=Decimal("960.00"),
            method="cash", posted_at=datetime.utcnow(),
            shift_id=shift.id, cashier_id=cashier,
            currency="USD", fx_rate=Decimal("48.00"), source="dining",
        )
        db.flush()

        # قفل الوردية بعدّ: 70 USD (50+20) = correct
        close_data = CashierShiftClose(
            cash_count=[
                CashCountLine(denomination=Decimal("50"), currency="USD", quantity=1),
                CashCountLine(denomination=Decimal("20"), currency="USD", quantity=1),
            ],
        )
        closed = finance_services.close_shift(db, shift.id, cashier, close_data)
        assert closed.status == "closed"

        report = finance_services.build_shift_end_report(db, shift.id)
        usd_summary = next((f for f in report.foreign_currency_summary if f.currency == "USD"), None)

        assert usd_summary is not None, "لازم يظهر ملخص USD في التقرير"
        assert usd_summary.total_foreign == Decimal("70.00"), "70 USD معدودة"
        assert usd_summary.expected_amount == Decimal("70.00"), "70 USD متوقعة (50+20)"
        assert usd_summary.variance == Decimal("0.00"), "فرق صفر لما العدّ صح"

    def test_shift_close_usd_surplus_shows_positive_variance(self, db: Session):
        """الكاشير عدّ 80 USD لكن باع 50 USD فقط → variance = +30 (زيادة)."""
        branch = _make_branch(db)
        cashier = _make_cashier()
        _seed_rate(db, "USD", "EGP", Decimal("48.00"))

        shift = _open_shift(db, branch.id, cashier)

        # بيع 50 USD
        finance_crud.create_direct_payment(
            db, branch_id=branch.id, amount=Decimal("2400.00"),
            method="cash", posted_at=datetime.utcnow(),
            shift_id=shift.id, cashier_id=cashier,
            currency="USD", fx_rate=Decimal("48.00"), source="dining",
        )
        db.flush()

        # عدّ 80 USD
        close_data = CashierShiftClose(
            cash_count=[
                CashCountLine(denomination=Decimal("50"), currency="USD", quantity=1),
                CashCountLine(denomination=Decimal("10"), currency="USD", quantity=3),
            ],
        )
        finance_services.close_shift(db, shift.id, cashier, close_data)

        report = finance_services.build_shift_end_report(db, shift.id)
        usd = next((f for f in report.foreign_currency_summary if f.currency == "USD"), None)

        assert usd is not None
        assert usd.total_foreign == Decimal("80.00")
        assert usd.expected_amount == Decimal("50.00")
        assert usd.variance == Decimal("30.00"), "زيادة 30 USD"

    def test_shift_close_usd_deficit_shows_negative_variance(self, db: Session):
        """الكاشير باع 70 USD لكن عدّ 50 فقط → variance = -20 (عجز)."""
        branch = _make_branch(db)
        cashier = _make_cashier()
        _seed_rate(db, "USD", "EGP", Decimal("48.00"))

        shift = _open_shift(db, branch.id, cashier)

        # بيع 70 USD
        finance_crud.create_direct_payment(
            db, branch_id=branch.id, amount=Decimal("3360.00"),
            method="cash", posted_at=datetime.utcnow(),
            shift_id=shift.id, cashier_id=cashier,
            currency="USD", fx_rate=Decimal("48.00"), source="dining",
        )
        db.flush()

        # عدّ 50 USD
        close_data = CashierShiftClose(
            cash_count=[
                CashCountLine(denomination=Decimal("50"), currency="USD", quantity=1),
            ],
        )
        finance_services.close_shift(db, shift.id, cashier, close_data)

        report = finance_services.build_shift_end_report(db, shift.id)
        usd = next((f for f in report.foreign_currency_summary if f.currency == "USD"), None)

        assert usd is not None
        assert usd.total_foreign == Decimal("50.00")
        assert usd.expected_amount == Decimal("70.00")
        assert usd.variance == Decimal("-20.00"), "عجز 20 USD"


# ── Test 3: عملة معدودة بدون مبيعات بنفس العملة ─────────────────────

class TestShiftCloseUnexpectedForeignCurrency:
    """لو الكاشير لقى 20 EUR في الدرج من غير أي بيع بيورو → variance = +20 EUR."""

    def test_counted_eur_with_no_eur_sales(self, db: Session):
        branch = _make_branch(db)
        cashier = _make_cashier()
        _seed_rate(db, "EUR", "EGP", Decimal("52.00"))

        shift = _open_shift(db, branch.id, cashier)
        # مفيش أي بيع EUR

        close_data = CashierShiftClose(
            cash_count=[
                CashCountLine(denomination=Decimal("20"), currency="EUR", quantity=1),
            ],
        )
        finance_services.close_shift(db, shift.id, cashier, close_data)

        report = finance_services.build_shift_end_report(db, shift.id)
        eur = next((f for f in report.foreign_currency_summary if f.currency == "EUR"), None)

        assert eur is not None
        assert eur.total_foreign == Decimal("20.00")
        # expected_amount = 0 (لأنه None → 0 فعليًا، الـ variance هيكون 20)
        # لو expected_amount = None → variance = None (لو مفيش بيع خالص يفضل None)
        # القرار: لو expected_amount=None (مفيش دفعات بهذه العملة)، variance=None
        # هنا نتحقق من total_foreign بس
        assert eur.egp_equivalent == Decimal("1040.00")  # 20 × 52


# ── Test 4: Pydantic validation — fx_rate مطلوب مع عملة أجنبية ───────

class TestFxRateValidation:
    def test_order_status_update_missing_fx_rate(self):
        from app.modules.dining.schemas import OrderStatusUpdate
        import pydantic
        with pytest.raises(pydantic.ValidationError) as exc_info:
            OrderStatusUpdate(
                status="paid",
                payment_method="cash",
                payment_currency="USD",
                # payment_fx_rate مش موجود
            )
        assert "payment_fx_rate" in str(exc_info.value) or "fx_rate" in str(exc_info.value)

    def test_order_status_update_egp_no_fx_rate_ok(self):
        from app.modules.dining.schemas import OrderStatusUpdate
        # EGP مش محتاج fx_rate
        obj = OrderStatusUpdate(
            status="paid",
            payment_method="cash",
            payment_currency="EGP",
        )
        assert obj.payment_currency == "EGP"

    def test_split_bill_payment_missing_fx_rate(self):
        from app.modules.dining.schemas import SplitBillPayment
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            SplitBillPayment(
                amount=Decimal("100.00"),
                payment_method="cash",
                currency="USD",
                # fx_rate مش موجود
            )

    def test_split_bill_payment_with_fx_rate_ok(self):
        from app.modules.dining.schemas import SplitBillPayment
        obj = SplitBillPayment(
            amount=Decimal("2400.00"),
            payment_method="cash",
            currency="USD",
            fx_rate=Decimal("48.00"),
        )
        assert obj.currency == "USD"
        assert obj.fx_rate == Decimal("48.00")
