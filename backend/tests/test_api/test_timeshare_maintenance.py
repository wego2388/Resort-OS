"""
tests/test_api/test_timeshare_maintenance.py
اختبارات نظام رسوم الصيانة السنوية لعقود التايم شير (2026-07-26) — تفعيل
TimeshareContract.maintenance_fee/maintenance_increase الخاملَين + استحقاق/
تحصيل/قيد محاسبي/تجميد حجز حقيقي، مربوط بنموذج الحجز الداخلي الرسمي اللي
بيشترط سداد الصيانة لتأكيد أي حجز أسبوع سنوي.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.modules.timeshare.schemas import (
    TimeshareContractCreate, TimeshareVisitCreate,
    PayInstallmentRequest, PayMaintenanceDueRequest,
)
from app.modules.timeshare import services, crud
from app.tasks.timeshare_tasks import _generate_annual_maintenance_dues, _mark_overdue


@pytest.fixture
def branch(db: Session):
    import uuid
    from app.modules.core.models import Branch
    b = Branch(name="Test", name_ar="اختبار", code=f"TSM-{uuid.uuid4().hex[:6].upper()}")
    db.add(b); db.flush()
    return b


@pytest.fixture
def unit(db: Session, branch):
    from app.modules.timeshare.models import TimeshareUnit
    u = TimeshareUnit(branch_id=branch.id, unit_number="A-201", unit_type="2R")
    db.add(u); db.flush()
    return u


def make_finance_accounts(db, branch):
    """1100 (نقدية) + 4650 (إيرادات صيانة عقود التايم شير) — الحسابين اللي
    _post_maintenance_payment_journal بيدوّر عليهم."""
    from app.modules.finance.models import Account
    cash = Account(branch_id=branch.id, code="1100", name="Cash", account_type="asset")
    revenue = Account(branch_id=branch.id, code="4650", name="Maintenance Revenue", account_type="revenue")
    db.add_all([cash, revenue])
    db.commit()
    return cash, revenue


def make_contract_with_maintenance(db, branch, maintenance_fee=Decimal("2000"), contract_date=None, start_date=None):
    data = TimeshareContractCreate(
        branch_id=branch.id,
        customer_name="سارة عبد الرحمن",
        customer_phone="01000000002",
        room_type="2R",
        total_value=Decimal("120000"),
        down_payment=Decimal("20000"),
        installments=12, installment_period=1,
        first_installment_date=date(2026, 8, 1),
        partner_share_pct=Decimal("0"),
        start_date=start_date or date(2026, 1, 1),
        contract_date=contract_date,
        maintenance_fee=maintenance_fee,
    )
    return services.create_contract(db, data, signed_by=1)


class TestMaintenanceDueGenerationOnContractCreation:
    """مستحق الصيانة الأول بيتولّد فور إنشاء العقد — مش بس عن طريق التوليد
    الجماعي السنوي — عشان عقد اتوقّع نص السنة ميفضلش من غير مستحق للسنة دي."""

    def test_contract_with_maintenance_fee_gets_first_due(self, db, branch):
        contract = make_contract_with_maintenance(db, branch, contract_date=date(2026, 6, 15))
        dues = crud.list_maintenance_dues(db, contract.id)
        assert len(dues) == 1
        assert dues[0].fee_year == 2026
        assert dues[0].amount == Decimal("2000.00")

    def test_due_date_anchored_to_signing_date_not_jan1(self, db, branch):
        """تفصيل هندسي مهم: due_date للمستحق الأول = تاريخ التوقيع نفسه، مش
        1 يناير الثابت — وإلا عقد اتوقّع في يونيو كان هيبقى "متأخر" فورًا."""
        signing = date(2026, 6, 15)
        contract = make_contract_with_maintenance(db, branch, contract_date=signing)
        due = crud.list_maintenance_dues(db, contract.id)[0]
        assert due.due_date == signing

    def test_contract_without_maintenance_fee_gets_no_due(self, db, branch):
        contract = make_contract_with_maintenance(db, branch, maintenance_fee=Decimal("0"))
        assert crud.list_maintenance_dues(db, contract.id) == []

    def test_full_amount_no_proration_for_mid_year_contract(self, db, branch):
        """قرار Mohamed: عقد نص السنة يستحق كامل الصيانة، بلا أي تناسب زمني."""
        contract = make_contract_with_maintenance(
            db, branch, maintenance_fee=Decimal("2000"), contract_date=date(2026, 11, 20),
        )
        due = crud.list_maintenance_dues(db, contract.id)[0]
        assert due.amount == Decimal("2000.00")

    def test_falls_back_to_start_date_when_contract_date_missing(self, db, branch):
        contract = make_contract_with_maintenance(
            db, branch, contract_date=None, start_date=date(2026, 3, 1),
        )
        due = crud.list_maintenance_dues(db, contract.id)[0]
        assert due.due_date == date(2026, 3, 1)
        assert due.fee_year == 2026


class TestAnnualBatchGeneration:
    """التوليد الجماعي (1 يناير) — idempotent، بيتخطى العقود اللي مالهاش
    maintenance_fee أو مش active، ومبيكررش مستحق موجود بالفعل."""

    def test_generation_is_idempotent_for_the_signing_year(self, db, branch):
        contract = make_contract_with_maintenance(db, branch, contract_date=date(2026, 1, 10))
        # المستحق الأول اتولّد فعلاً وقت الإنشاء — إعادة التوليد الجماعي لنفس
        # السنة لازم تلاقي 0 جديد
        created = _generate_annual_maintenance_dues(db, branch.id, 2026)
        db.commit()
        assert created == 0
        assert len(crud.list_maintenance_dues(db, contract.id)) == 1

    def test_generation_creates_new_year_due(self, db, branch):
        contract = make_contract_with_maintenance(db, branch, contract_date=date(2026, 1, 10))
        created = _generate_annual_maintenance_dues(db, branch.id, 2027)
        db.commit()
        assert created == 1
        dues = {d.fee_year for d in crud.list_maintenance_dues(db, contract.id)}
        assert dues == {2026, 2027}

        # تشغيل تاني لنفس 2027 — صفر إضافة
        created_again = _generate_annual_maintenance_dues(db, branch.id, 2027)
        db.commit()
        assert created_again == 0

    def test_zero_maintenance_fee_contract_skipped(self, db, branch):
        make_contract_with_maintenance(db, branch, maintenance_fee=Decimal("0"), contract_date=date(2026, 1, 10))
        created = _generate_annual_maintenance_dues(db, branch.id, 2027)
        db.commit()
        assert created == 0

    def test_cancelled_contract_skipped(self, db, branch):
        contract = make_contract_with_maintenance(db, branch, contract_date=date(2026, 1, 10))
        services.cancel_contract(db, contract.id, Decimal("0"))
        created = _generate_annual_maintenance_dues(db, branch.id, 2027)
        db.commit()
        assert created == 0


class TestPayMaintenanceDue:

    def test_pay_full_due(self, db, branch):
        contract = make_contract_with_maintenance(db, branch, contract_date=date(2026, 1, 10))
        due = crud.list_maintenance_dues(db, contract.id)[0]
        req = PayMaintenanceDueRequest(paid_amount=due.amount, payment_method="cash", receipt_number="R-1")
        paid = services.pay_maintenance_due(db, due.id, req)
        assert paid.status == "paid"
        assert paid.paid_amount == due.amount

    def test_partial_payment(self, db, branch):
        contract = make_contract_with_maintenance(db, branch, contract_date=date(2026, 1, 10))
        due = crud.list_maintenance_dues(db, contract.id)[0]
        paid = services.pay_maintenance_due(
            db, due.id, PayMaintenanceDueRequest(paid_amount=due.amount / 2, payment_method="cash"),
        )
        assert paid.status == "partial"

    def test_overpayment_raises(self, db, branch):
        contract = make_contract_with_maintenance(db, branch, contract_date=date(2026, 1, 10))
        due = crud.list_maintenance_dues(db, contract.id)[0]
        with pytest.raises(ValueError, match="أكبر من المتبقي"):
            services.pay_maintenance_due(
                db, due.id,
                PayMaintenanceDueRequest(paid_amount=due.amount + Decimal("500"), payment_method="cash"),
            )

    def test_cannot_pay_on_cancelled_contract(self, db, branch):
        contract = make_contract_with_maintenance(db, branch, contract_date=date(2026, 1, 10))
        due = crud.list_maintenance_dues(db, contract.id)[0]
        services.cancel_contract(db, contract.id, Decimal("0"))
        with pytest.raises(ValueError, match="ملغي"):
            services.pay_maintenance_due(
                db, due.id, PayMaintenanceDueRequest(paid_amount=due.amount, payment_method="cash"),
            )

    def test_already_paid_due_rejected(self, db, branch):
        contract = make_contract_with_maintenance(db, branch, contract_date=date(2026, 1, 10))
        due = crud.list_maintenance_dues(db, contract.id)[0]
        services.pay_maintenance_due(db, due.id, PayMaintenanceDueRequest(paid_amount=due.amount, payment_method="cash"))
        with pytest.raises(ValueError, match="مدفوع"):
            services.pay_maintenance_due(db, due.id, PayMaintenanceDueRequest(paid_amount=due.amount, payment_method="cash"))

    def test_pay_maintenance_due_posts_journal_entry_to_4650(self, db, branch):
        """4650 منفصل عمدًا عن 4600 (إيراد سعر الشراء) — رسم خدمة سنوي
        مرتبط بسنة محدَّدة، مختلف في طبيعته المحاسبية."""
        from app.modules.finance import crud as finance_crud
        make_finance_accounts(db, branch)
        contract = make_contract_with_maintenance(db, branch, contract_date=date(2026, 1, 10))
        due = crud.list_maintenance_dues(db, contract.id)[0]

        services.pay_maintenance_due(
            db, due.id, PayMaintenanceDueRequest(paid_amount=due.amount, payment_method="cash"),
        )

        entries, _total = finance_crud.list_journal_entries(db, branch.id, source="timeshare")
        maint_entries = [e for e in entries if e.reference.startswith("TS-MAINT-")]
        assert len(maint_entries) == 1
        entry = maint_entries[0]
        assert sum(l.debit for l in entry.lines) == sum(l.credit for l in entry.lines) == due.amount
        for line in entry.lines:
            assert line.cost_center_id is not None


class TestFreezeUnfreezeInteraction:
    """السيناريو الجوهري: صيانة وأقساط متأخرات مستقلة — سداد نوع واحد
    ميفكّش التجميد لو النوع التاني لسه متأخر."""

    def _make_overdue_maintenance_contract(self, db, branch):
        contract = make_contract_with_maintenance(db, branch, contract_date=date(2020, 1, 10))
        due = crud.list_maintenance_dues(db, contract.id)[0]
        due.due_date = date(2020, 1, 10)  # ماضي بعيد فعليًا
        db.flush()
        return contract, due

    def test_maintenance_only_overdue_freezes_and_installments_dont_unfreeze(self, db, branch):
        contract, _due = self._make_overdue_maintenance_contract(db, branch)
        _mark_overdue(db, date.today())
        db.commit()
        db.refresh(contract)
        assert contract.booking_frozen is True

        # سداد كل الأقساط (اللي مش متأخرة أصلاً) ميفكّش التجميد
        for inst in contract.installments_list:
            services.pay_installment(db, inst.id, PayInstallmentRequest(paid_amount=inst.amount, payment_method="cash"))
        db.refresh(contract)
        assert contract.booking_frozen is True

    def test_paying_maintenance_unfreezes_when_no_other_overdue(self, db, branch):
        contract, due = self._make_overdue_maintenance_contract(db, branch)
        _mark_overdue(db, date.today())
        db.commit()
        db.refresh(due)

        services.pay_maintenance_due(db, due.id, PayMaintenanceDueRequest(paid_amount=due.amount, payment_method="cash"))
        db.refresh(contract)
        assert contract.booking_frozen is False

    def test_both_overdue_requires_both_paid_to_unfreeze(self, db, branch):
        contract, due = self._make_overdue_maintenance_contract(db, branch)
        for inst in contract.installments_list[:1]:
            inst.due_date = date(2020, 2, 1)
        db.flush()
        _mark_overdue(db, date.today())
        db.commit()
        db.refresh(contract)
        assert contract.booking_frozen is True

        overdue_inst = next(i for i in contract.installments_list if i.status == "overdue")
        services.pay_installment(db, overdue_inst.id, PayInstallmentRequest(paid_amount=overdue_inst.amount, payment_method="cash"))
        db.refresh(contract)
        assert contract.booking_frozen is True, "لسه الصيانة متأخرة — ميفكّش"

        db.refresh(due)
        services.pay_maintenance_due(db, due.id, PayMaintenanceDueRequest(paid_amount=due.amount, payment_method="cash"))
        db.refresh(contract)
        assert contract.booking_frozen is False


class TestPayInstallmentUnfreezeBugFix:
    """باج كامن حقيقي كان في pay_installment قبل توحيد فحص التجميد: الاستبعاد
    `i.id != inst_id` كان بيتجاهل بالظبط القسط اللي اتدفع جزئيًا لسه — فلو
    كان هو القسط الوحيد المتأخر، العقد كان بيتفك تجميده غلط."""

    def test_partial_payment_on_sole_overdue_installment_does_not_unfreeze(self, db, branch):
        contract = make_contract_with_maintenance(db, branch, maintenance_fee=Decimal("0"), contract_date=date(2026, 1, 10))
        inst = contract.installments_list[0]
        inst.due_date = date(2020, 1, 1)
        db.flush()
        _mark_overdue(db, date.today())
        db.commit()
        db.refresh(contract)
        assert contract.booking_frozen is True

        # دفعة جزئية بس — القسط يبقى "partial" (لسه متأخر فعليًا) مش "paid"
        services.pay_installment(
            db, inst.id, PayInstallmentRequest(paid_amount=inst.amount / 2, payment_method="cash"),
        )
        db.refresh(contract)
        assert contract.booking_frozen is True, (
            "دفعة جزئية على القسط المتأخر الوحيد مافيش لازم تفك التجميد — لسه فيه رصيد متأخر"
        )


class TestCreateVisitRejectsForMaintenanceOverdue:

    def test_rejected_with_maintenance_specific_message(self, db, branch):
        contract = make_contract_with_maintenance(db, branch, contract_date=date(2020, 1, 10))
        due = crud.list_maintenance_dues(db, contract.id)[0]
        due.due_date = date(2020, 1, 10)
        db.flush()
        _mark_overdue(db, date.today())
        db.commit()
        db.refresh(contract)
        assert contract.booking_frozen is True

        visit_data = TimeshareVisitCreate(
            branch_id=branch.id, contract_id=contract.id,
            check_in=date(2027, 8, 1), check_out=date(2027, 8, 8),
        )
        with pytest.raises(ValueError, match="رسوم صيانة متأخرة"):
            services.create_visit(db, visit_data)
