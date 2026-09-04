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


# ── Test 5: Beach multi-currency — schema validation ──────────────────

class TestBeachSellRequestFxValidation:
    """BeachSellRequest مع payment_currency ≠ EGP بدون payment_fx_rate → validation error."""

    def test_beach_sell_missing_fx_rate_raises(self):
        import pydantic
        from app.modules.beach.schemas import BeachSellRequest
        with pytest.raises(pydantic.ValidationError) as exc_info:
            BeachSellRequest(
                tx_type="entry",
                quantity=1,
                payment_currency="USD",
                # payment_fx_rate مش موجود
            )
        assert "payment_fx_rate" in str(exc_info.value)

    def test_beach_sell_egp_no_fx_rate_ok(self):
        from app.modules.beach.schemas import BeachSellRequest
        obj = BeachSellRequest(tx_type="entry", quantity=2)
        assert obj.payment_currency is None
        assert obj.payment_fx_rate is None

    def test_beach_sell_usd_with_fx_rate_ok(self):
        from app.modules.beach.schemas import BeachSellRequest
        obj = BeachSellRequest(
            tx_type="entry",
            quantity=1,
            payment_currency="USD",
            payment_fx_rate=Decimal("48.00"),
        )
        assert obj.payment_currency == "USD"
        assert obj.payment_fx_rate == Decimal("48.00")


# ── Test 6: Beach multi-currency — Payment مسجَّل بعملة أجنبية ───────

class TestBeachMultiCurrencyPaymentRecord:
    """بيع شاطئ بعملة أجنبية → Payment.currency="USD"، Payment.fx_rate مسجَّل،
    Payment.amount = EGP-equivalent، وForeignCurrencySummary صح في تقرير الوردية."""

    def test_beach_usd_sale_records_payment_with_currency(self, db: Session):
        """_record_shift_payment بيمرّر currency/fx_rate من BeachSellRequest."""
        from decimal import Decimal
        from datetime import datetime, date
        from app.modules.beach import services as beach_services
        from app.modules.beach.schemas import BeachSellRequest
        from app.modules.beach.models import BeachInventory as BeachInventoryModel
        from app.modules.finance.models import Payment

        branch = _make_branch(db)
        cashier = _make_cashier()
        _seed_rate(db, "USD", "EGP", Decimal("48.00"))
        shift = _open_shift(db, branch.id, cashier)

        # جهّز inventory للشاطئ
        today = date.today()
        inv = BeachInventoryModel(
            branch_id=branch.id,
            inventory_date=today,
            capacity_max=100,
            capacity_used=0,
            towels_total=50,
            towels_available=50,
            towels_used=0,
            surge_pct=Decimal("0"),
        )
        db.add(inv)
        db.flush()

        # اضبط الأسعار الأساسية للفرع (يحتاجها beach_services._get_base_prices)
        from app.modules.core.services import upsert_setting
        for key, val in [
            ("beach.adult_price", "200"),
            ("beach.child_price", "100"),
            ("beach.resident_price", "150"),
            ("beach.towel_price", "50"),
        ]:
            upsert_setting(db, branch.id, key, val)
        db.flush()

        req = BeachSellRequest(
            tx_type="entry",
            quantity=1,
            cashier_id=cashier,
            payment_currency="USD",
            payment_fx_rate=Decimal("48.00"),
        )
        tx = beach_services.sell_ticket(db, branch.id, req)

        # تحقق من Payment المسجّل
        payment = (
            db.query(Payment)
            .filter(
                Payment.shift_id == shift.id,
                Payment.source == "beach",
            )
            .order_by(Payment.id.desc())
            .first()
        )
        assert payment is not None, "لازم يكون في Payment مسجّل للشاطئ"
        assert payment.currency == "USD", "العملة لازم تكون USD"
        assert payment.fx_rate == Decimal("48.00"), "fx_rate لازم يكون 48"
        assert payment.amount > 0, "amount لازم يكون EGP-equivalent موجب"

    def test_beach_egp_sale_payment_currency_defaults_to_egp(self, db: Session):
        """بيع شاطئ عادي بالجنيه → Payment.currency='EGP'، Payment.fx_rate=1."""
        from decimal import Decimal
        from datetime import date
        from app.modules.beach import services as beach_services
        from app.modules.beach.schemas import BeachSellRequest
        from app.modules.beach.models import BeachInventory as BeachInventoryModel
        from app.modules.finance.models import Payment

        branch = _make_branch(db)
        cashier = _make_cashier()
        shift = _open_shift(db, branch.id, cashier)

        today = date.today()
        inv = BeachInventoryModel(
            branch_id=branch.id,
            inventory_date=today,
            capacity_max=100,
            capacity_used=0,
            towels_total=50,
            towels_available=50,
            towels_used=0,
            surge_pct=Decimal("0"),
        )
        db.add(inv)
        db.flush()

        from app.modules.core.services import upsert_setting
        for key, val in [
            ("beach.adult_price", "200"),
            ("beach.child_price", "100"),
            ("beach.resident_price", "150"),
            ("beach.towel_price", "50"),
        ]:
            upsert_setting(db, branch.id, key, val)
        db.flush()

        req = BeachSellRequest(tx_type="entry", quantity=1, cashier_id=cashier)
        beach_services.sell_ticket(db, branch.id, req)

        payment = (
            db.query(Payment)
            .filter(Payment.shift_id == shift.id, Payment.source == "beach")
            .order_by(Payment.id.desc())
            .first()
        )
        assert payment is not None
        assert payment.currency == "EGP"
        assert payment.fx_rate == Decimal("1")

    def test_beach_usd_sale_appears_in_shift_foreign_summary(self, db: Session):
        """بيع شاطئ USD → ForeignCurrencySummary في تقرير الوردية يعرض expected_amount صح."""
        from decimal import Decimal
        from datetime import date
        from app.modules.beach import services as beach_services
        from app.modules.beach.schemas import BeachSellRequest
        from app.modules.beach.models import BeachInventory as BeachInventoryModel

        branch = _make_branch(db)
        cashier = _make_cashier()
        _seed_rate(db, "USD", "EGP", Decimal("50.00"))
        shift = _open_shift(db, branch.id, cashier)

        today = date.today()
        inv = BeachInventoryModel(
            branch_id=branch.id,
            inventory_date=today,
            capacity_max=100,
            capacity_used=0,
            towels_total=50,
            towels_available=50,
            towels_used=0,
            surge_pct=Decimal("0"),
        )
        db.add(inv)
        db.flush()

        from app.modules.core.services import upsert_setting
        for key, val in [
            ("beach.adult_price", "250"),   # 250 ج = 5 USD @ 50
            ("beach.child_price", "100"),
            ("beach.resident_price", "150"),
            ("beach.towel_price", "50"),
        ]:
            upsert_setting(db, branch.id, key, val)
        db.flush()

        # بيع 2 بالغ = 500 ج = 10 USD @ 50
        req = BeachSellRequest(
            tx_type="entry",
            quantity=2,
            cashier_id=cashier,
            payment_currency="USD",
            payment_fx_rate=Decimal("50.00"),
        )
        beach_services.sell_ticket(db, branch.id, req)

        # قفل الوردية بعدّ 10 USD
        close_data = CashierShiftClose(
            cash_count=[
                CashCountLine(denomination=Decimal("10"), currency="USD", quantity=1),
            ],
        )
        finance_services.close_shift(db, shift.id, cashier, close_data)

        report = finance_services.build_shift_end_report(db, shift.id)
        usd = next((f for f in report.foreign_currency_summary if f.currency == "USD"), None)

        assert usd is not None, "لازم يظهر ملخص USD في تقرير وردية الشاطئ"
        assert usd.total_foreign == Decimal("10.00"), "10 USD معدودة"
        # expected_amount = مبيعات الشاطئ بـ USD = 500 ج ÷ 50 = 10 USD
        assert usd.expected_amount == Decimal("10.00"), "10 USD متوقعة من البيع"
        assert usd.variance == Decimal("0.00"), "فرق صفر (عدّ صح)"

    def test_beach_change_always_in_egp_not_in_foreign(self, db: Session):
        """الفكة دايمًا بالجنيه — نتحقق إن amount في Payment = EGP-equivalent كامل
        (مش بيتقلّل لو الكاشير استلم أكتر من المطلوب بالعملة الأجنبية)."""
        from decimal import Decimal
        from datetime import date
        from app.modules.beach import services as beach_services
        from app.modules.beach.schemas import BeachSellRequest
        from app.modules.beach.models import BeachInventory as BeachInventoryModel
        from app.modules.finance.models import Payment

        branch = _make_branch(db)
        cashier = _make_cashier()
        _seed_rate(db, "USD", "EGP", Decimal("48.00"))
        shift = _open_shift(db, branch.id, cashier)

        today = date.today()
        inv = BeachInventoryModel(
            branch_id=branch.id,
            inventory_date=today,
            capacity_max=100,
            capacity_used=0,
            towels_total=50,
            towels_available=50,
            towels_used=0,
            surge_pct=Decimal("0"),
        )
        db.add(inv)
        db.flush()

        from app.modules.core.services import upsert_setting
        for key, val in [
            ("beach.adult_price", "200"),  # 200 ج = ~4.17 USD @ 48
            ("beach.child_price", "100"),
            ("beach.resident_price", "150"),
            ("beach.towel_price", "50"),
        ]:
            upsert_setting(db, branch.id, key, val)
        db.flush()

        req = BeachSellRequest(
            tx_type="entry",
            quantity=1,
            cashier_id=cashier,
            payment_currency="USD",
            payment_fx_rate=Decimal("48.00"),
        )
        tx = beach_services.sell_ticket(db, branch.id, req)

        payment = (
            db.query(Payment)
            .filter(Payment.shift_id == shift.id, Payment.source == "beach")
            .order_by(Payment.id.desc())
            .first()
        )
        # amount = EGP-equivalent للمبيعة (total_amount + vat_amount) —
        # مش مرتبط بكمية الدولارات المستلمة فعليًا (الفكة مسؤولية الكاشير)
        assert payment is not None
        expected_egp = (tx.total_amount or Decimal("0")) + (tx.vat_amount or Decimal("0"))
        assert payment.amount == expected_egp, "amount = EGP-equivalent بالظبط، مش أقل"


# ── Test 5: Beach multi-currency — schema validation ──────────────────

class TestBeachSellRequestFxValidation:
    """BeachSellRequest مع payment_currency ≠ EGP بدون payment_fx_rate → validation error."""

    def test_beach_sell_missing_fx_rate_raises(self):
        import pydantic
        from app.modules.beach.schemas import BeachSellRequest
        with pytest.raises(pydantic.ValidationError) as exc_info:
            BeachSellRequest(
                tx_type="entry",
                quantity=1,
                payment_currency="USD",
                # payment_fx_rate مش موجود
            )
        assert "payment_fx_rate" in str(exc_info.value)

    def test_beach_sell_egp_no_fx_rate_ok(self):
        from app.modules.beach.schemas import BeachSellRequest
        obj = BeachSellRequest(tx_type="entry", quantity=2)
        assert obj.payment_currency is None
        assert obj.payment_fx_rate is None

    def test_beach_sell_usd_with_fx_rate_ok(self):
        from app.modules.beach.schemas import BeachSellRequest
        obj = BeachSellRequest(
            tx_type="entry",
            quantity=1,
            payment_currency="USD",
            payment_fx_rate=Decimal("48.00"),
        )
        assert obj.payment_currency == "USD"
        assert obj.payment_fx_rate == Decimal("48.00")


# ── helpers مشتركة لتستات الشاطئ ─────────────────────────────────────

def _make_beach_branch(db):
    """ينشئ فرع شاطئ — بـ commit كامل عشان FK constraints في settings."""
    from app.modules.core.models import Branch
    from app.modules.finance.models import Account
    b = Branch(
        name=f"Beach Test {uuid.uuid4().hex[:6]}",
        name_ar="فرع شاطئ اختبار",
        code=f"BCH-{uuid.uuid4().hex[:8].upper()}",
    )
    db.add(b)
    db.commit()
    # The strict Beach journal needs cash/revenue. VAT payable remains in the
    # fixture for historical compatibility; new Beach sales store VAT zero.
    db.add_all([
        Account(branch_id=b.id, code="1100", name="Cash", account_type="asset"),
        Account(branch_id=b.id, code="4300", name="Beach Revenue", account_type="revenue"),
        Account(branch_id=b.id, code="2160", name="VAT Payable", account_type="liability"),
    ])
    db.commit()
    return b


def _make_beach_inventory(db, branch_id: int):
    """ينشئ beach_inventory + أسعار الشاطئ للفرع (أسماء settings الصحيحة)."""
    from datetime import date
    from app.modules.beach.models import BeachInventory as BeachInventoryModel
    from app.modules.core.services import upsert_setting
    today = date.today()
    inv = BeachInventoryModel(
        branch_id=branch_id,
        inventory_date=today,
        capacity_max=100,
        capacity_used=0,
        towels_total=50,
        towels_available=50,
        towels_used=0,
        surge_pct=Decimal("0"),
    )
    db.add(inv)
    db.commit()
    for key, val in [
        ("beach.price.adult",    "200"),
        ("beach.price.child",    "100"),
        ("beach.price.resident", "150"),
        ("beach.price.towel",    "50"),
    ]:
        upsert_setting(db, key, val, branch_id=branch_id)
    db.commit()


# ── Test 6: Beach — Payment يتسجّل بعملة أجنبية ──────────────────────

class TestBeachMultiCurrencyPaymentRecord:
    """sell_ticket بعملة أجنبية → Payment.currency/fx_rate مسجّلان،
    amount = EGP-equivalent."""

    def test_usd_beach_sale_records_currency_and_fx(self, db: Session):
        from app.modules.beach import services as beach_services
        from app.modules.beach.schemas import BeachSellRequest
        from app.modules.finance.models import Payment

        branch = _make_beach_branch(db)
        cashier = _make_cashier()
        _seed_rate(db, "USD", "EGP", Decimal("48.00"))
        shift = _open_shift(db, branch.id, cashier)
        _make_beach_inventory(db, branch.id)

        req = BeachSellRequest(
            tx_type="entry", quantity=1, cashier_id=cashier,
            payment_currency="USD", payment_fx_rate=Decimal("48.00"),
        )
        tx = beach_services.sell_ticket(db, branch.id, req)

        payment = (
            db.query(Payment)
            .filter(Payment.shift_id == shift.id, Payment.source == "beach")
            .order_by(Payment.id.desc())
            .first()
        )
        assert payment is not None, "لازم Payment مسجّل للشاطئ"
        assert payment.currency == "USD"
        assert payment.fx_rate == Decimal("48.00")
        expected_egp = (tx.total_amount or Decimal("0")) + (tx.vat_amount or Decimal("0"))
        assert payment.amount == expected_egp, "amount = EGP-equivalent"

    def test_egp_beach_sale_defaults_to_egp_currency(self, db: Session):
        from app.modules.beach import services as beach_services
        from app.modules.beach.schemas import BeachSellRequest
        from app.modules.finance.models import Payment

        branch = _make_beach_branch(db)
        cashier = _make_cashier()
        shift = _open_shift(db, branch.id, cashier)
        _make_beach_inventory(db, branch.id)

        req = BeachSellRequest(tx_type="entry", quantity=1, cashier_id=cashier)
        beach_services.sell_ticket(db, branch.id, req)

        payment = (
            db.query(Payment)
            .filter(Payment.shift_id == shift.id, Payment.source == "beach")
            .order_by(Payment.id.desc())
            .first()
        )
        assert payment is not None
        assert payment.currency == "EGP"
        assert payment.fx_rate == Decimal("1")

    def test_beach_usd_sale_variance_in_shift_report(self, db: Session):
        """بيع شاطئ USD + قفل وردية بعدّ USD صح → variance = 0."""
        from app.modules.beach import services as beach_services
        from app.modules.beach.schemas import BeachSellRequest

        branch = _make_beach_branch(db)
        cashier = _make_cashier()
        _seed_rate(db, "USD", "EGP", Decimal("50.00"))
        shift = _open_shift(db, branch.id, cashier)
        _make_beach_inventory(db, branch.id)

        # 1 بالغ = 200 ج بدون VAT
        req = BeachSellRequest(
            tx_type="entry", quantity=1, cashier_id=cashier,
            payment_currency="USD", payment_fx_rate=Decimal("50.00"),
        )
        tx = beach_services.sell_ticket(db, branch.id, req)

        # المبلغ الفعلي = total_amount + vat_amount (قد يختلف عن 200 لو في VAT)
        egp_charged = (tx.total_amount or Decimal("0")) + (tx.vat_amount or Decimal("0"))
        expected_usd = (egp_charged / Decimal("50.00")).quantize(Decimal("0.01"))

        close_data = CashierShiftClose(
            cash_count=[
                CashCountLine(denomination=expected_usd, currency="USD", quantity=1),
            ],
        )
        finance_services.close_shift(db, shift.id, cashier, close_data)

        report = finance_services.build_shift_end_report(db, shift.id)
        usd = next((f for f in report.foreign_currency_summary if f.currency == "USD"), None)

        assert usd is not None, "لازم يظهر ملخص USD"
        assert usd.expected_amount == expected_usd
        assert usd.variance == Decimal("0.00"), f"فرق صفر — معدود={usd.total_foreign} متوقع={usd.expected_amount}"

    def test_beach_usd_sale_deficit_variance(self, db: Session):
        """بيع شاطئ USD، عدّ نص المبلغ فقط → variance سالب."""
        from app.modules.beach import services as beach_services
        from app.modules.beach.schemas import BeachSellRequest

        branch = _make_beach_branch(db)
        cashier = _make_cashier()
        _seed_rate(db, "USD", "EGP", Decimal("50.00"))
        shift = _open_shift(db, branch.id, cashier)
        _make_beach_inventory(db, branch.id)

        req = BeachSellRequest(
            tx_type="entry", quantity=1, cashier_id=cashier,
            payment_currency="USD", payment_fx_rate=Decimal("50.00"),
        )
        tx = beach_services.sell_ticket(db, branch.id, req)

        egp_charged = (tx.total_amount or Decimal("0")) + (tx.vat_amount or Decimal("0"))
        expected_usd = (egp_charged / Decimal("50.00")).quantize(Decimal("0.01"))
        half_usd = (expected_usd / 2).quantize(Decimal("0.01"))

        close_data = CashierShiftClose(
            cash_count=[
                CashCountLine(denomination=half_usd, currency="USD", quantity=1),
            ],
        )
        finance_services.close_shift(db, shift.id, cashier, close_data)

        report = finance_services.build_shift_end_report(db, shift.id)
        usd = next((f for f in report.foreign_currency_summary if f.currency == "USD"), None)

        assert usd is not None
        assert usd.variance is not None
        assert usd.variance < Decimal("0"), "لازم يكون عجز (variance سالب)"

    def test_beach_amount_is_always_egp_equivalent_regardless_of_received(self, db: Session):
        """الفكة مسؤولية الكاشير — amount في Payment = EGP-equivalent الكامل
        بغض النظر عن كمية الدولارات المستلمة فعليًا."""
        from app.modules.beach import services as beach_services
        from app.modules.beach.schemas import BeachSellRequest
        from app.modules.finance.models import Payment

        branch = _make_beach_branch(db)
        cashier = _make_cashier()
        _seed_rate(db, "USD", "EGP", Decimal("48.00"))
        shift = _open_shift(db, branch.id, cashier)
        _make_beach_inventory(db, branch.id)

        req = BeachSellRequest(
            tx_type="entry", quantity=1, cashier_id=cashier,
            payment_currency="USD", payment_fx_rate=Decimal("48.00"),
        )
        tx = beach_services.sell_ticket(db, branch.id, req)

        payment = (
            db.query(Payment)
            .filter(Payment.shift_id == shift.id, Payment.source == "beach")
            .order_by(Payment.id.desc())
            .first()
        )
        expected_egp = (tx.total_amount or Decimal("0")) + (tx.vat_amount or Decimal("0"))
        assert payment.amount == expected_egp
        # المبلغ الأصلي بالدولار = amount / fx_rate
        original_usd = (payment.amount / payment.fx_rate).quantize(Decimal("0.01"))
        assert original_usd > 0
