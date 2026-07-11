"""
tests/test_api/test_leasing.py
Integration tests for leasing module.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.leasing.schemas import LeaseContractCreate, PayLeaseRequest
from app.modules.leasing import services, crud
from app.resort_os.timezone_utils import local_today


@pytest.fixture
def branch(db: Session):
    import uuid
    from app.modules.core.models import Branch
    b = Branch(name="Test", name_ar="اختبار", code=f"LS-{uuid.uuid4().hex[:6].upper()}")
    db.add(b); db.flush()
    return b


@pytest.fixture
def contract(db: Session, branch):
    data = LeaseContractCreate(
        branch_id=branch.id,
        tenant_name="شركة الفجر للتجارة",
        tenant_phone="01001000000",
        unit_description="محل تجاري رقم 5 — الطابق الأرضي",
        start_date=date(2026, 1, 1),
        end_date=date(2027, 12, 31),
        base_rent=Decimal("5000"),
        increase_rate=Decimal("10"),
        billing_day=1,
        grace_months=0,
        payment_period="monthly",
        security_deposit=Decimal("10000"),
    )
    return services.create_contract(db, data, signed_by=1)


class TestLeaseContract:

    def test_create_generates_payments(self, db, branch, contract):
        assert contract.contract_number.startswith("LC-")
        assert len(contract.payments) > 0

    def test_monthly_payments_count(self, db, contract):
        # 24 شهر بدون grace
        assert len(contract.payments) == 24

    def test_year2_payments_higher(self, db, contract):
        year1 = [p for p in contract.payments if p.year_n == 0]
        year2 = [p for p in contract.payments if p.year_n == 1]
        if year2:
            assert year2[0].amount > year1[0].amount

    def test_invalid_dates_raises(self, db, branch):
        data = LeaseContractCreate(
            branch_id=branch.id, tenant_name="مستأجر",
            unit_description="وحدة",
            start_date=date(2026, 12, 1),
            end_date=date(2026, 1, 1),  # نهاية قبل البداية
            base_rent=Decimal("5000"),
        )
        with pytest.raises(ValueError, match="تاريخ الانتهاء"):
            services.create_contract(db, data, signed_by=1)


class TestLeasePayment:

    def test_pay_full(self, db, contract):
        payment = contract.payments[0]
        req = PayLeaseRequest(paid_amount=payment.amount, payment_method="bank_transfer")
        paid = services.pay_payment(db, payment.id, req)
        assert paid.status == "paid"

    def test_partial_payment(self, db, contract):
        payment = contract.payments[0]
        req = PayLeaseRequest(
            paid_amount=payment.amount / Decimal("2"),
            payment_method="cash",
        )
        paid = services.pay_payment(db, payment.id, req)
        assert paid.status == "partial"

    def test_cannot_pay_already_paid(self, db, contract):
        payment = contract.payments[0]
        req = PayLeaseRequest(paid_amount=payment.amount, payment_method="cash")
        services.pay_payment(db, payment.id, req)
        with pytest.raises(ValueError, match="مسددة"):
            services.pay_payment(db, payment.id, req)

    def test_penalty_included_in_full_pay(self, db, contract):
        payment = contract.payments[0]
        payment.penalty = Decimal("250")
        db.flush(); db.commit()

        # دفع المبلغ بدون الغرامة → partial
        req = PayLeaseRequest(paid_amount=payment.amount, payment_method="cash")
        paid = services.pay_payment(db, payment.id, req)
        assert paid.status == "partial"

    def test_receipt_pdf_uses_freshly_computed_penalty_not_stale_column(self, db, contract):
        """payment.penalty ممكن يكون قديم لحد ما apply_penalties() تتنادى — الإيصال
        المفروض يعرض الغرامة المحسوبة لحظيًا مش القيمة المخزّنة الممكن تكون صفر."""
        from app.modules.leasing.services import calculate_penalty

        payment = contract.payments[0]  # متأخر فعليًا (تاريخ استحقاقه فات من شهور)
        assert payment.penalty in (None, Decimal("0"))  # العمود المخزّن لسه صفر/فاضي
        fresh_penalty = calculate_penalty(payment)
        assert fresh_penalty > 0  # فعلاً متأخر ولازم غرامة حقيقية

        pdf = services.generate_rent_receipt_pdf(db, payment.id)
        assert pdf.startswith(b"%PDF")

        import subprocess, tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(pdf); f.flush()
            text = subprocess.run(
                ["pdftotext", f.name, "-"], capture_output=True, text=True
            ).stdout
        assert f"{fresh_penalty:,.2f}" in text


def _make_contract(db: Session, branch, *, end_date: date, status: str = "active"):
    """عقد إيجار مساعد بتاريخ نهاية محدد — لاختبار تنبيه "قرب الانتهاء"
    (wagdy.md بند #28). start_date دايمًا في الماضي البعيد عشان نضمن جدول
    دفعات صالح بغض النظر عن end_date المطلوب في التست."""
    data = LeaseContractCreate(
        branch_id=branch.id,
        tenant_name="مستأجر اختبار الانتهاء",
        unit_description="وحدة اختبار",
        start_date=end_date - timedelta(days=730),
        end_date=end_date,
        base_rent=Decimal("3000"),
    )
    contract = services.create_contract(db, data, signed_by=1)
    if status != "active":
        contract.status = status
        db.flush(); db.commit()
    return contract


class TestLeasingExpiringSoon:
    """wagdy.md بند #28: عقود الإيجار اللي قربت تنتهي (خلال 30 يوم) كانت من
    غير أي تنبيه — مدير الإيجارات كان بيكتشف الانتهاء بالصدفة بس."""

    def test_days_until_expiry_positive_for_future_end_date(self, db, branch):
        today = local_today(settings.TIMEZONE)
        contract = _make_contract(db, branch, end_date=today + timedelta(days=10))
        assert services.days_until_expiry(contract, today) == 10

    def test_days_until_expiry_negative_for_past_end_date(self, db, branch):
        today = local_today(settings.TIMEZONE)
        contract = _make_contract(db, branch, end_date=today - timedelta(days=5))
        assert services.days_until_expiry(contract, today) == -5

    def test_list_expiring_soon_includes_contract_at_exact_30_day_boundary(self, db, branch):
        today = local_today(settings.TIMEZONE)
        contract = _make_contract(db, branch, end_date=today + timedelta(days=30))
        results = services.list_expiring_soon(db, branch.id, within_days=30)
        assert contract.id in [c.id for c in results]

    def test_list_expiring_soon_excludes_contract_at_31_days(self, db, branch):
        today = local_today(settings.TIMEZONE)
        contract = _make_contract(db, branch, end_date=today + timedelta(days=31))
        results = services.list_expiring_soon(db, branch.id, within_days=30)
        assert contract.id not in [c.id for c in results]

    def test_list_expiring_soon_includes_contract_expiring_today(self, db, branch):
        today = local_today(settings.TIMEZONE)
        contract = _make_contract(db, branch, end_date=today)
        results = services.list_expiring_soon(db, branch.id, within_days=30)
        assert contract.id in [c.id for c in results]

    def test_list_expiring_soon_excludes_already_expired_contract(self, db, branch):
        today = local_today(settings.TIMEZONE)
        contract = _make_contract(db, branch, end_date=today - timedelta(days=1))
        results = services.list_expiring_soon(db, branch.id, within_days=30)
        assert contract.id not in [c.id for c in results]

    def test_list_expiring_soon_excludes_terminated_contract(self, db, branch):
        today = local_today(settings.TIMEZONE)
        contract = _make_contract(db, branch, end_date=today + timedelta(days=5), status="terminated")
        results = services.list_expiring_soon(db, branch.id, within_days=30)
        assert contract.id not in [c.id for c in results]

    def test_list_expiring_soon_sorted_by_end_date_ascending(self, db, branch):
        today = local_today(settings.TIMEZONE)
        later = _make_contract(db, branch, end_date=today + timedelta(days=20))
        sooner = _make_contract(db, branch, end_date=today + timedelta(days=3))
        results = services.list_expiring_soon(db, branch.id, within_days=30)
        ids_in_order = [c.id for c in results if c.id in (later.id, sooner.id)]
        assert ids_in_order == [sooner.id, later.id]

    def test_list_expiring_soon_scoped_to_branch(self, db, branch):
        import uuid
        from app.modules.core.models import Branch
        other_branch = Branch(name="Other", name_ar="فرع آخر", code=f"LS2-{uuid.uuid4().hex[:6].upper()}")
        db.add(other_branch); db.flush()

        today = local_today(settings.TIMEZONE)
        _make_contract(db, other_branch, end_date=today + timedelta(days=5))
        results = services.list_expiring_soon(db, branch.id, within_days=30)
        assert results == []
