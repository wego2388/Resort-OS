"""
tests/test_api/test_leasing.py
Integration tests for leasing module.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.modules.leasing.schemas import LeaseContractCreate, PayLeaseRequest
from app.modules.leasing import services, crud


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
