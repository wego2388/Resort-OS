"""
tests/test_api/test_timeshare.py
Integration tests for timeshare module.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.modules.timeshare.schemas import (
    TimeshareContractCreate, TimeshareContractUpdate, PayInstallmentRequest,
)
from app.modules.timeshare import services, crud


@pytest.fixture
def branch(db: Session):
    import uuid
    from app.modules.core.models import Branch
    b = Branch(name="Test", name_ar="اختبار", code=f"TS-{uuid.uuid4().hex[:6].upper()}")
    db.add(b); db.flush()
    return b


@pytest.fixture
def unit(db: Session, branch):
    """وحدة تايم شير حقيقية (2R) متاحة — لازمة عشان create_visit يقدر يخصّص
    وحدة فعلية (allocation logic حقيقي، مش مجرد سطر تاريخ من غير حجز حقيقي)."""
    from app.modules.timeshare.models import TimeshareUnit
    u = TimeshareUnit(branch_id=branch.id, unit_number="A-101", unit_type="2R")
    db.add(u); db.flush()
    return u


@pytest.fixture
def contract(db: Session, branch):
    data = TimeshareContractCreate(
        branch_id=branch.id,
        customer_name="أحمد محمد",
        customer_phone="01000000001",
        room_type="2R",
        week_number=28,
        nights_per_year=7,
        total_value=Decimal("120000"),
        down_payment=Decimal("20000"),
        installments=12,
        installment_period=1,
        first_installment_date=date(2026, 8, 1),
        partner_share_pct=Decimal("0"),
        start_date=date(2026, 7, 1),
    )
    return services.create_contract(db, data, signed_by=1)


class TestTimeshareContract:

    def test_create_generates_installments(self, db, branch, contract):
        assert contract.contract_number.startswith("TS-")
        assert len(contract.installments_list) == 12

    def test_installment_amounts_sum_to_remaining(self, db, contract):
        total = sum(i.amount for i in contract.installments_list)
        assert total == Decimal("100000")  # 120000 - 20000

    def test_first_installment_date_correct(self, db, contract):
        first = min(contract.installments_list, key=lambda i: i.installment_no)
        assert first.due_date == date(2026, 8, 1)

    def test_down_payment_exceeds_total_raises(self, db, branch):
        data = TimeshareContractCreate(
            branch_id=branch.id,
            customer_name="عميل",
            room_type="2R",
            total_value=Decimal("50000"),
            down_payment=Decimal("60000"),  # أكبر من الإجمالي
            installments=12, installment_period=1,
            first_installment_date=date(2026, 8, 1),
            partner_share_pct=Decimal("0"),
            start_date=date(2026, 7, 1),
        )
        with pytest.raises(ValueError, match="الدفعة الأولى"):
            services.create_contract(db, data, signed_by=1)

    def test_end_date_before_start_date_raises(self, db, branch):
        """قاعدة عمل حقيقية من elkheima-beach-resort: end_date يجب أن يكون
        بعد start_date — كانت ناقصة في resort-os (فقط عند التحقق من الـ schema
        لم تكن هناك مقارنة بين الحقلين)."""
        data = TimeshareContractCreate(
            branch_id=branch.id,
            customer_name="عميل",
            room_type="2R",
            total_value=Decimal("50000"),
            down_payment=Decimal("5000"),
            installments=12, installment_period=1,
            first_installment_date=date(2026, 8, 1),
            partner_share_pct=Decimal("0"),
            start_date=date(2026, 7, 1),
            end_date=date(2026, 6, 1),  # قبل start_date
        )
        with pytest.raises(ValueError, match="تاريخ الانتهاء"):
            services.create_contract(db, data, signed_by=1)

    def test_end_date_equal_start_date_raises(self, db, branch):
        data = TimeshareContractCreate(
            branch_id=branch.id,
            customer_name="عميل",
            room_type="2R",
            total_value=Decimal("50000"),
            down_payment=Decimal("5000"),
            installments=12, installment_period=1,
            first_installment_date=date(2026, 8, 1),
            partner_share_pct=Decimal("0"),
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
        )
        with pytest.raises(ValueError, match="تاريخ الانتهاء"):
            services.create_contract(db, data, signed_by=1)

    def test_end_date_after_start_date_succeeds(self, db, branch):
        data = TimeshareContractCreate(
            branch_id=branch.id,
            customer_name="عميل",
            room_type="2R",
            total_value=Decimal("50000"),
            down_payment=Decimal("5000"),
            installments=12, installment_period=1,
            first_installment_date=date(2026, 8, 1),
            partner_share_pct=Decimal("0"),
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 2),
        )
        c = services.create_contract(db, data, signed_by=1)
        assert c.end_date == date(2026, 7, 2)


class TestPayInstallment:

    def test_pay_full_installment(self, db, contract):
        inst = contract.installments_list[0]
        req = PayInstallmentRequest(
            paid_amount=inst.amount,
            payment_method="cash",
            receipt_number="REC-001",
        )
        paid = services.pay_installment(db, inst.id, req)
        assert paid.status == "paid"
        assert paid.paid_amount == inst.amount

    def test_partial_payment(self, db, contract):
        inst = contract.installments_list[0]
        req = PayInstallmentRequest(
            paid_amount=inst.amount / 2,
            payment_method="card",
        )
        paid = services.pay_installment(db, inst.id, req)
        assert paid.status == "partial"

    def test_cannot_pay_already_paid(self, db, contract):
        inst = contract.installments_list[0]
        req = PayInstallmentRequest(paid_amount=inst.amount, payment_method="cash")
        services.pay_installment(db, inst.id, req)
        with pytest.raises(ValueError, match="مدفوع"):
            services.pay_installment(db, inst.id, req)

    def test_payment_unfreezes_booking(self, db, contract):
        # تجميد الحجز يدوياً
        contract.booking_frozen = True
        db.flush(); db.commit()

        inst = contract.installments_list[0]
        req = PayInstallmentRequest(paid_amount=inst.amount, payment_method="cash")
        services.pay_installment(db, inst.id, req)
        db.refresh(contract)
        assert not contract.booking_frozen


class TestWaitlist:

    def test_add_to_waitlist(self, db, branch, contract):
        from app.modules.timeshare.schemas import WaitlistCreate
        data = WaitlistCreate(
            branch_id=branch.id,
            contract_id=contract.id,
            requested_start=date(2026, 8, 1),
            requested_end=date(2026, 8, 7),
        )
        entry = services.add_to_waitlist(db, data)
        assert entry.position == 1
        assert entry.status == "waiting"

    def test_invalid_dates_raises(self, db, branch, contract):
        from app.modules.timeshare.schemas import WaitlistCreate
        data = WaitlistCreate(
            branch_id=branch.id, contract_id=contract.id,
            requested_start=date(2026, 8, 7),
            requested_end=date(2026, 8, 1),  # نهاية قبل البداية
        )
        with pytest.raises(ValueError, match="تاريخ النهاية"):
            services.add_to_waitlist(db, data)


class TestSalesDashboard:
    """لوحة مبيعات فريق المبيعات — pipeline + متأخرات بأرقام تليفون."""

    def test_pipeline_counts_by_status(self, db: Session, branch, contract):
        # عقد تاني في حالة draft
        data = TimeshareContractCreate(
            branch_id=branch.id, customer_name="Draft Guy", customer_phone="01111111111",
            room_type="2R", nights_per_year=7, total_value=Decimal("100000"),
            down_payment=Decimal("10000"), installments=12, installment_period=1,
            first_installment_date=date(2026, 8, 1), start_date=date(2026, 7, 1),
        )
        draft = services.create_contract(db, data, signed_by=1)
        services.update_contract(db, draft.id, TimeshareContractUpdate(status="draft"))

        dash = services.get_sales_dashboard(db, branch.id)
        assert dash["pipeline"]["active"] == 1
        assert dash["pipeline"]["draft"] == 1
        assert dash["active_contracts"] == 1  # draft عقود مش جوه cs-summary الأساسي

    def test_overdue_client_has_phone_for_sales_followup(self, db: Session, branch, contract):
        from app.modules.timeshare.models import TimeshareInstallment
        inst = (
            db.query(TimeshareInstallment)
            .filter(TimeshareInstallment.contract_id == contract.id, TimeshareInstallment.status == "pending")
            .first()
        )
        inst.status = "overdue"
        db.flush()

        dash = services.get_sales_dashboard(db, branch.id)
        assert dash["overdue_contracts_count"] == 1
        assert len(dash["overdue_clients"]) == 1
        overdue = dash["overdue_clients"][0]
        assert overdue["customer_phone"] == "01000000001"
        assert overdue["overdue_amount"] > 0

    def test_no_overdue_when_all_current(self, db: Session, branch, contract):
        dash = services.get_sales_dashboard(db, branch.id)
        assert dash["overdue_contracts_count"] == 0
        assert dash["overdue_clients"] == []

    def test_expired_contracts_counted_separately_from_active(self, db: Session, branch, contract):
        services.update_contract(db, contract.id, TimeshareContractUpdate(status="expired"))
        dash = services.get_sales_dashboard(db, branch.id)
        assert dash["pipeline"]["expired"] == 1
        assert dash["expired_contracts_count"] == 1
        assert dash["active_contracts"] == 0  # ماعادش نشط


def make_finance_accounts(db, branch):
    """يزرع 1100 (نقدية) و2300 (إيرادات مؤجّلة تايم شير) — الحسابين اللي
    timeshare.services._post_deferred_revenue_journal بيدوّر عليهم بالكود."""
    from app.modules.finance.models import Account
    cash = Account(branch_id=branch.id, code="1100", name="Cash", account_type="asset")
    deferred = Account(branch_id=branch.id, code="2300", name="Deferred Revenue", account_type="liability")
    db.add_all([cash, deferred])
    db.commit()
    return cash, deferred


class TestContractNotFound:

    def test_get_contract_or_404_raises(self, db):
        with pytest.raises(ValueError, match="غير موجود"):
            services.get_contract_or_404(db, 999999)

    def test_update_nonexistent_contract_raises(self, db):
        with pytest.raises(ValueError):
            services.update_contract(db, 999999, TimeshareContractUpdate(status="active"))


class TestDeferredRevenueJournalPosting:
    """Gap حقيقي مماثل تماماً لـ restaurant/cafe/beach: القيد المحاسبي لدفعة
    أول عقد تايم شير (Dr Cash / Cr Deferred Revenue 2300) موجود في الكود من
    زمان بس من غير أي تغطية اختبارية خالص — 0% على _post_deferred_revenue_journal."""

    def test_create_contract_posts_balanced_journal_entry(self, db: Session, branch):
        from app.modules.finance import crud as finance_crud
        cash, deferred = make_finance_accounts(db, branch)

        data = TimeshareContractCreate(
            branch_id=branch.id, customer_name="سامي عادل", room_type="2R",
            total_value=Decimal("80000"), down_payment=Decimal("15000"),
            installments=10, installment_period=1,
            first_installment_date=date(2026, 8, 1),
            partner_share_pct=Decimal("0"), start_date=date(2026, 7, 1),
        )
        contract = services.create_contract(db, data, signed_by=1)

        entries, total = finance_crud.list_journal_entries(db, branch.id, source="timeshare")
        assert total == 1
        entry = entries[0]
        assert entry.source_id == contract.id
        total_debit = sum(l.debit for l in entry.lines)
        total_credit = sum(l.credit for l in entry.lines)
        assert total_debit == total_credit == Decimal("15000.00")

        db.refresh(cash); db.refresh(deferred)
        cash_line = next(l for l in entry.lines if l.account_id == cash.id)
        deferred_line = next(l for l in entry.lines if l.account_id == deferred.id)
        assert cash_line.debit == Decimal("15000.00")
        assert deferred_line.credit == Decimal("15000.00")

    def test_zero_down_payment_does_not_post_journal(self, db: Session, branch):
        """دفعة أولى صفرية (down_payment=0) مفيهاش مبلغ حقيقي يترحّل."""
        from app.modules.finance import crud as finance_crud
        make_finance_accounts(db, branch)

        data = TimeshareContractCreate(
            branch_id=branch.id, customer_name="بدون دفعة", room_type="2R",
            total_value=Decimal("50000"), down_payment=Decimal("0"),
            installments=10, installment_period=1,
            first_installment_date=date(2026, 8, 1),
            partner_share_pct=Decimal("0"), start_date=date(2026, 7, 1),
        )
        services.create_contract(db, data, signed_by=1)

        _, total = finance_crud.list_journal_entries(db, branch.id, source="timeshare")
        assert total == 0

    def test_missing_accounts_does_not_block_contract_creation(self, db: Session, branch):
        """لو 1100/2300 مش موجودين، إنشاء العقد لازم ينجح عادي — نفس فلسفة
        pms._post_checkout_journal (الفشل المحاسبي ميوقفش العملية الأساسية)."""
        from app.modules.finance import crud as finance_crud

        data = TimeshareContractCreate(
            branch_id=branch.id, customer_name="بدون حسابات", room_type="2R",
            total_value=Decimal("60000"), down_payment=Decimal("10000"),
            installments=12, installment_period=1,
            first_installment_date=date(2026, 8, 1),
            partner_share_pct=Decimal("0"), start_date=date(2026, 7, 1),
        )
        contract = services.create_contract(db, data, signed_by=1)
        assert contract.id is not None

        _, total = finance_crud.list_journal_entries(db, branch.id, source="timeshare")
        assert total == 0


class TestCancelContract:

    def test_cancel_sets_status_and_refund_amount(self, db: Session, contract):
        cancelled = services.cancel_contract(db, contract.id, Decimal("5000"))
        assert cancelled.status == "cancelled"
        assert cancelled.cancel_amount == Decimal("5000")
        assert cancelled.cancelled_at is not None

    def test_cancel_already_cancelled_raises(self, db: Session, contract):
        services.cancel_contract(db, contract.id, Decimal("1000"))
        with pytest.raises(ValueError, match="ملغي"):
            services.cancel_contract(db, contract.id, Decimal("500"))

    def test_cancel_nonexistent_contract_raises(self, db: Session):
        with pytest.raises(ValueError):
            services.cancel_contract(db, 999999, Decimal("0"))


class TestTimeshareVisit:

    def test_create_visit_computes_nights(self, db: Session, branch, contract, unit):
        from app.modules.timeshare.schemas import TimeshareVisitCreate
        data = TimeshareVisitCreate(
            branch_id=branch.id, contract_id=contract.id,
            check_in=date(2026, 8, 1), check_out=date(2026, 8, 8),
        )
        visit = services.create_visit(db, data)
        assert visit.nights == 7
        assert visit.status == "scheduled"

    def test_checkout_before_checkin_raises(self, db: Session, branch, contract):
        from app.modules.timeshare.schemas import TimeshareVisitCreate
        data = TimeshareVisitCreate(
            branch_id=branch.id, contract_id=contract.id,
            check_in=date(2026, 8, 8), check_out=date(2026, 8, 1),
        )
        with pytest.raises(ValueError, match="check_out"):
            services.create_visit(db, data)

    def test_frozen_booking_blocks_visit_creation(self, db: Session, branch, contract):
        """قاعدة أعمال حقيقية: عقد بأقساط متأخرة (booking_frozen=True) ميقدرش
        يحجز زيارة جديدة لحد ما يسدّد المتأخرات."""
        from app.modules.timeshare.schemas import TimeshareVisitCreate
        contract.booking_frozen = True
        db.commit()

        data = TimeshareVisitCreate(
            branch_id=branch.id, contract_id=contract.id,
            check_in=date(2026, 8, 1), check_out=date(2026, 8, 5),
        )
        with pytest.raises(ValueError, match="مجمَّد"):
            services.create_visit(db, data)

    def test_update_visit_status(self, db: Session, branch, contract, unit):
        from app.modules.timeshare.schemas import TimeshareVisitCreate, TimeshareVisitUpdate
        data = TimeshareVisitCreate(
            branch_id=branch.id, contract_id=contract.id,
            check_in=date(2026, 8, 1), check_out=date(2026, 8, 3),
        )
        visit = services.create_visit(db, data)
        updated = services.update_visit(db, visit.id, TimeshareVisitUpdate(status="completed"))
        assert updated.status == "completed"

    def test_update_nonexistent_visit_raises(self, db: Session):
        from app.modules.timeshare.schemas import TimeshareVisitUpdate
        with pytest.raises(ValueError):
            services.update_visit(db, 999999, TimeshareVisitUpdate(status="completed"))

    # ── Real unit allocation / double-booking prevention ──────────────

    def test_floating_contract_allocates_unit(self, db: Session, branch, contract, unit):
        """عقد عائم (بدون unit_id ثابت) — لازم يتخصّص له وحدة فعلية حقيقية
        من نفس room_type لحظة إنشاء الزيارة."""
        from app.modules.timeshare.schemas import TimeshareVisitCreate
        assert contract.unit_id is None
        data = TimeshareVisitCreate(
            branch_id=branch.id, contract_id=contract.id,
            check_in=date(2026, 8, 1), check_out=date(2026, 8, 8),
        )
        visit = services.create_visit(db, data)
        assert visit.unit_id == unit.id

    def test_no_available_unit_raises(self, db: Session, branch, contract):
        """مفيش أي وحدة من نوع 2R في الفرع — لازم يرفض بوضوح (مش ينجح
        بدون تخصيص حقيقي)."""
        from app.modules.timeshare.schemas import TimeshareVisitCreate
        data = TimeshareVisitCreate(
            branch_id=branch.id, contract_id=contract.id,
            check_in=date(2026, 8, 1), check_out=date(2026, 8, 8),
        )
        with pytest.raises(ValueError, match="لا توجد وحدة متاحة"):
            services.create_visit(db, data)

    def test_floating_contract_picks_next_unit_when_first_taken(self, db: Session, branch, contract, unit):
        """عقد عائم تاني — طالما أول وحدة اتحجزت في فترة متقاطعة، لازم
        ياخد وحدة تانية متاحة، مش يفشل ومش يستخدم نفس الوحدة المحجوزة."""
        from app.modules.timeshare.models import TimeshareUnit
        from app.modules.timeshare.schemas import TimeshareContractCreate, TimeshareVisitCreate

        unit2 = TimeshareUnit(branch_id=branch.id, unit_number="A-102", unit_type="2R")
        db.add(unit2); db.flush()

        first_visit = services.create_visit(db, TimeshareVisitCreate(
            branch_id=branch.id, contract_id=contract.id,
            check_in=date(2026, 8, 1), check_out=date(2026, 8, 8),
        ))
        assert first_visit.unit_id == unit.id

        contract2 = services.create_contract(db, TimeshareContractCreate(
            branch_id=branch.id, customer_name="عميل ثاني", room_type="2R",
            total_value=Decimal("120000"), down_payment=Decimal("20000"),
            installments=12, installment_period=1,
            first_installment_date=date(2026, 8, 1),
            partner_share_pct=Decimal("0"), start_date=date(2026, 7, 1),
        ), signed_by=1)

        second_visit = services.create_visit(db, TimeshareVisitCreate(
            branch_id=branch.id, contract_id=contract2.id,
            check_in=date(2026, 8, 3), check_out=date(2026, 8, 6),  # يتقاطع مع الأول
        ))
        assert second_visit.unit_id == unit2.id

    def test_permanently_assigned_unit_rejects_overlap(self, db: Session, branch, contract, unit):
        """عقد بوحدة مخصَّصة دائمًا (contract.unit_id) — زيارة تانية متقاطعة
        على نفس الوحدة لازم تُرفض بوضوح (منع تعارض حجز حقيقي)."""
        from app.modules.timeshare.schemas import TimeshareVisitCreate

        contract.unit_id = unit.id
        db.commit()

        services.create_visit(db, TimeshareVisitCreate(
            branch_id=branch.id, contract_id=contract.id,
            check_in=date(2026, 8, 1), check_out=date(2026, 8, 8),
        ))

        with pytest.raises(ValueError, match="محجوزة بالفعل"):
            services.create_visit(db, TimeshareVisitCreate(
                branch_id=branch.id, contract_id=contract.id,
                check_in=date(2026, 8, 5), check_out=date(2026, 8, 10),  # يتقاطع
            ))

    def test_permanently_assigned_unit_non_overlapping_succeeds(self, db: Session, branch, contract, unit):
        """نفس الوحدة المخصَّصة دائمًا — لكن فترة تانية غير متقاطعة لازم تنجح
        عادي (مفيش تعارض حقيقي)."""
        from app.modules.timeshare.schemas import TimeshareVisitCreate

        contract.unit_id = unit.id
        db.commit()

        services.create_visit(db, TimeshareVisitCreate(
            branch_id=branch.id, contract_id=contract.id,
            check_in=date(2026, 8, 1), check_out=date(2026, 8, 8),
        ))
        second = services.create_visit(db, TimeshareVisitCreate(
            branch_id=branch.id, contract_id=contract.id,
            check_in=date(2026, 8, 10), check_out=date(2026, 8, 15),  # مش متقاطعة
        ))
        assert second.unit_id == unit.id


class TestExcelImport:

    def _build_workbook(self, headers: list[str], rows: list[list]) -> bytes:
        import io
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(headers)
        for row in rows:
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def test_import_valid_row_creates_contract(self, db: Session, branch):
        headers = [
            "customer_name", "room_type", "total_value", "down_payment",
            "installments", "start_date", "first_installment_date",
        ]
        rows = [["ياسمين علي", "2R", 90000, 10000, 10, "2026-07-01", "2026-08-01"]]
        content = self._build_workbook(headers, rows)

        result = services.import_contracts_excel(db, branch.id, content, signed_by=1)
        assert result["imported"] == 1
        assert result["skipped"] == 0
        assert result["errors"] == []

    def test_import_missing_required_columns_raises(self, db: Session, branch):
        headers = ["customer_name", "room_type"]  # ناقص أعمدة إلزامية
        rows = [["عميل", "2R"]]
        content = self._build_workbook(headers, rows)

        with pytest.raises(ValueError, match="أعمدة إلزامية ناقصة"):
            services.import_contracts_excel(db, branch.id, content, signed_by=1)

    def test_import_empty_file_raises(self, db: Session, branch):
        import io
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.delete_rows(1, ws.max_row)  # لا صفوف خالص، حتى الـ header
        buf = io.BytesIO()
        wb.save(buf)

        with pytest.raises(ValueError, match="فاضي"):
            services.import_contracts_excel(db, branch.id, buf.getvalue(), signed_by=1)

    def test_import_skips_duplicate_form_number(self, db: Session, branch):
        headers = [
            "customer_name", "room_type", "total_value", "down_payment",
            "installments", "start_date", "first_installment_date", "form_number",
        ]
        rows = [
            ["عميل واحد", "2R", 50000, 5000, 6, "2026-07-01", "2026-08-01", "FORM-100"],
            ["عميل نفس الفورم", "2R", 60000, 6000, 6, "2026-07-01", "2026-08-01", "FORM-100"],
        ]
        content = self._build_workbook(headers, rows)

        result = services.import_contracts_excel(db, branch.id, content, signed_by=1)
        assert result["imported"] == 1
        assert result["skipped"] == 1

    def test_import_row_error_does_not_abort_whole_batch(self, db: Session, branch):
        """صف بقيمة فاسدة (down_payment أكبر من total_value) يتسجّل كـ error
        من غير ما يوقف استيراد باقي الصفوف الصحيحة."""
        headers = [
            "customer_name", "room_type", "total_value", "down_payment",
            "installments", "start_date", "first_installment_date",
        ]
        rows = [
            ["عميل فاسد", "2R", 10000, 90000, 6, "2026-07-01", "2026-08-01"],  # down_payment > total
            ["عميل صحيح", "2R", 50000, 5000, 6, "2026-07-01", "2026-08-01"],
        ]
        content = self._build_workbook(headers, rows)

        result = services.import_contracts_excel(db, branch.id, content, signed_by=1)
        assert result["imported"] == 1
        assert len(result["errors"]) == 1


class TestTimeshareReports:
    """تقارير التايم شير (calendar/upcoming-visits/stats/list-installments) —
    0% تغطية قبل كده رغم إنها بتستخدم فعلياً في CS/Sales dashboards."""

    def test_get_calendar_includes_booked_week(self, db: Session, branch, contract):
        # contract fixture: week_number=28
        calendar = services.get_calendar(db, branch.id, year=2026)
        assert calendar["total_booked_weeks"] == 1
        week_28_entries = [
            wk for month in calendar["calendar"] for wk in month["weeks"] if wk["week"] == 28
        ]
        assert len(week_28_entries) == 1
        assert len(week_28_entries[0]["contracts"]) == 1
        assert week_28_entries[0]["contracts"][0]["contract_number"] == contract.contract_number

    def test_get_calendar_empty_when_no_week_number(self, db: Session, branch):
        data = TimeshareContractCreate(
            branch_id=branch.id, customer_name="بدون أسبوع", room_type="2R",
            total_value=Decimal("40000"), down_payment=Decimal("4000"),
            installments=6, installment_period=1,
            first_installment_date=date(2026, 8, 1), start_date=date(2026, 7, 1),
        )
        services.create_contract(db, data, signed_by=1)
        calendar = services.get_calendar(db, branch.id, year=2026)
        assert calendar["total_booked_weeks"] == 0

    def test_get_upcoming_visits_finds_active_contract_within_window(self, db: Session, branch, contract):
        from datetime import date as _date
        # week_number=28 و nights_per_year=7 — احسب نافذة الزيارة القادمة يدوياً
        # مش مهم القيمة الدقيقة، المهم إن العقد النشط يظهر أو مايظهرش حسب days_until
        visits = services.get_upcoming_visits(db, branch.id, days=365)
        # نافذة أسبوع 28 خلال آخر سنة لازم تظهر ضمن نطاق الـ 365 يوم
        assert any(v["contract_number"] == contract.contract_number for v in visits)

    def test_get_upcoming_visits_excludes_non_active_contracts(self, db: Session, branch, contract):
        services.update_contract(db, contract.id, TimeshareContractUpdate(status="suspended"))
        visits = services.get_upcoming_visits(db, branch.id, days=365)
        assert not any(v["contract_number"] == contract.contract_number for v in visits)

    def test_get_stats_reflects_collected_installment(self, db: Session, branch, contract):
        inst = contract.installments_list[0]
        req = PayInstallmentRequest(paid_amount=inst.amount, payment_method="cash")
        services.pay_installment(db, inst.id, req)

        stats = services.get_stats(db, branch.id)
        assert stats["collection"]["collected"] >= float(inst.amount)
        assert stats["collection"]["rate"] > 0
        assert any(r["room_type"] == "2R" for r in stats["by_room_type"])

    def test_get_stats_by_partner_includes_resort_net_share(self, db: Session, branch):
        """صافي حصة المنتجع بعد نصيب الشريك (resort_share) — خاصية حقيقية من
        elkheima-beach-resort (khayma_share) كانت محسوبة في الـ engine
        (calculate_partner_share) لكن غير مُستخدَمة في أي مكان."""
        data = TimeshareContractCreate(
            branch_id=branch.id, customer_name="عميل شريك", room_type="4R",
            total_value=Decimal("200000"), down_payment=Decimal("40000"),
            installments=10, installment_period=1,
            first_installment_date=date(2026, 8, 1), start_date=date(2026, 7, 1),
            partner_share_pct=Decimal("30"), partner_company="شركة الشريك",
        )
        services.create_contract(db, data, signed_by=1)

        stats = services.get_stats(db, branch.id)
        row = next(r for r in stats["by_partner"] if r["partner_company"] == "شركة الشريك")
        assert row["total_down"] == 40000.0
        # 40000 * (1 - 30/100) = 28000
        assert row["resort_share"] == 28000.0

    def test_list_installments_returns_summary(self, db: Session, branch, contract):
        result = services.list_installments(db, branch.id)
        assert result["total"] == 12
        assert "summary" in result

    def test_list_installments_filters_by_status(self, db: Session, branch, contract):
        inst = contract.installments_list[0]
        services.pay_installment(
            db, inst.id, PayInstallmentRequest(paid_amount=inst.amount, payment_method="cash"),
        )
        result = services.list_installments(db, branch.id, status="paid")
        assert result["total"] == 1
