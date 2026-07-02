"""
tests/test_tasks/test_timeshare_tasks.py
اختبارات _mark_overdue — الجزء القابل للاختبار من مهمة Celery اليومية
app.tasks.timeshare_tasks.mark_overdue.

⚠️ قبل هذا الإصلاح: الكود كان يستخدم `contract.installments` (عمود عدد
الأقساط int) بدلاً من `contract.installments_list` (العلاقة الفعلية) —
ده كان بيرمي TypeError: 'int' object is not iterable في كل تشغيل، يعني
تجميد الحجز (booking_frozen) عند التأخر في السداد كان معطّل تماماً رغم
وجود منطق `should_freeze_booking` جاهز ومُختبَر في الـ engine.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.modules.timeshare import services
from app.modules.timeshare.schemas import TimeshareContractCreate
from app.tasks.timeshare_tasks import _mark_overdue


def make_branch(db: Session):
    import uuid

    from app.modules.core.models import Branch
    b = Branch(name="TS Task Branch", name_ar="فرع مهام", code=f"TST-{uuid.uuid4().hex[:6].upper()}")
    db.add(b)
    db.flush()
    return b


class TestMarkOverdue:
    def test_marks_past_due_pending_installment_as_overdue(self, db: Session):
        branch = make_branch(db)
        past_due = date.today() - timedelta(days=5)
        data = TimeshareContractCreate(
            branch_id=branch.id, customer_name="عميل متأخر", room_type="2R",
            total_value=Decimal("60000"), down_payment=Decimal("6000"),
            installments=6, installment_period=1,
            first_installment_date=past_due, start_date=date(2026, 1, 1),
        )
        contract = services.create_contract(db, data, signed_by=1)

        overdue_count = _mark_overdue(db, date.today())
        db.commit()
        db.refresh(contract)

        first_inst = min(contract.installments_list, key=lambda i: i.installment_no)
        assert first_inst.status == "overdue"
        assert overdue_count >= 1

    def test_freezes_booking_when_contract_has_overdue_installment(self, db: Session):
        branch = make_branch(db)
        past_due = date.today() - timedelta(days=10)
        data = TimeshareContractCreate(
            branch_id=branch.id, customer_name="عميل مجمّد", room_type="2R",
            total_value=Decimal("60000"), down_payment=Decimal("6000"),
            installments=6, installment_period=1,
            first_installment_date=past_due, start_date=date(2026, 1, 1),
        )
        contract = services.create_contract(db, data, signed_by=1)
        assert contract.booking_frozen is False

        _mark_overdue(db, date.today())
        db.commit()
        db.refresh(contract)

        assert contract.booking_frozen is True

    def test_freezes_booking_when_overdue_installment_is_partially_paid(self, db: Session):
        """قسط مدفوع جزئياً (status="partial") وفات معاده لازم يتحسب متأخر برضه —
        لو فضل status="partial" مش بيتحوّل overdue، عقد فيه سداد جزئي متأخر
        كان هيفلت من التجميد رغم إنه فعلياً متأخر (باج حقيقي اتصلح)."""
        branch = make_branch(db)
        past_due = date.today() - timedelta(days=10)
        data = TimeshareContractCreate(
            branch_id=branch.id, customer_name="عميل سدد جزء", room_type="2R",
            total_value=Decimal("60000"), down_payment=Decimal("6000"),
            installments=6, installment_period=1,
            first_installment_date=past_due, start_date=date(2026, 1, 1),
        )
        contract = services.create_contract(db, data, signed_by=1)
        first_inst = min(contract.installments_list, key=lambda i: i.installment_no)

        from app.modules.timeshare import crud
        from app.modules.timeshare.schemas import PayInstallmentRequest
        crud.pay_installment(db, first_inst, PayInstallmentRequest(
            paid_amount=first_inst.amount / Decimal("2"), payment_method="cash",
        ))
        db.commit()
        db.refresh(first_inst)
        assert first_inst.status == "partial"

        _mark_overdue(db, date.today())
        db.commit()
        db.refresh(contract)
        db.refresh(first_inst)

        assert first_inst.status == "overdue"
        assert contract.booking_frozen is True

    def test_does_not_freeze_when_installments_all_current(self, db: Session):
        branch = make_branch(db)
        future_due = date.today() + timedelta(days=30)
        data = TimeshareContractCreate(
            branch_id=branch.id, customer_name="عميل ملتزم", room_type="2R",
            total_value=Decimal("60000"), down_payment=Decimal("6000"),
            installments=6, installment_period=1,
            first_installment_date=future_due, start_date=date(2026, 1, 1),
        )
        contract = services.create_contract(db, data, signed_by=1)

        _mark_overdue(db, date.today())
        db.commit()
        db.refresh(contract)

        assert contract.booking_frozen is False
        assert all(i.status == "pending" for i in contract.installments_list)
