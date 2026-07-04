"""
tests/test_api/test_hr.py
Integration tests for HR module.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.modules.hr.schemas import (
    AttendanceRecordCreate,
    DepartmentCreate,
    EmployeeCreate,
    EmployeeUpdate,
    EmployeePenaltyCreate,
    LeaveRequestCreate,
    LeaveTypeCreate,
    RotaAssignmentCreate,
    ShiftCreate,
    ShiftSwapRequestCreate,
)
from app.modules.hr import services, crud


@pytest.fixture
def branch(db: Session):
    from app.modules.core.models import Branch
    b = Branch(name="Test HR", name_ar="موارد بشرية اختبارية",
               code=f"HR-{uuid.uuid4().hex[:6].upper()}")
    db.add(b)
    db.flush()
    return b


@pytest.fixture
def si_config(db: Session):
    """SocialInsuranceConfig مطلوب لـ payroll."""
    from app.modules.hr.models import SocialInsuranceConfig
    cfg = SocialInsuranceConfig(
        max_insurable_salary=Decimal("9400.00"),
        employee_rate=Decimal("0.1100"),
        employer_rate=Decimal("0.1800"),
        personal_exemption_annual=Decimal("15000.00"),
        max_penalty_days_monthly=5,
        effective_from=date(2024, 1, 1),
        is_active=True,
    )
    db.add(cfg)
    db.flush()
    return cfg


@pytest.fixture
def tax_brackets(db: Session):
    """شرائح ضريبية مطلوبة لـ payroll."""
    from app.modules.hr.models import TaxBracketConfig
    brackets = [
        TaxBracketConfig(lower_bound=Decimal("0"),      upper_bound=Decimal("15000"),  rate=Decimal("0.0000"), effective_from=date(2024, 1, 1), is_active=True),
        TaxBracketConfig(lower_bound=Decimal("15000"),  upper_bound=Decimal("30000"),  rate=Decimal("0.1000"), effective_from=date(2024, 1, 1), is_active=True),
        TaxBracketConfig(lower_bound=Decimal("30000"),  upper_bound=Decimal("45000"),  rate=Decimal("0.1500"), effective_from=date(2024, 1, 1), is_active=True),
        TaxBracketConfig(lower_bound=Decimal("45000"),  upper_bound=Decimal("60000"),  rate=Decimal("0.2000"), effective_from=date(2024, 1, 1), is_active=True),
        TaxBracketConfig(lower_bound=Decimal("60000"),  upper_bound=None,              rate=Decimal("0.2250"), effective_from=date(2024, 1, 1), is_active=True),
    ]
    db.add_all(brackets)
    db.flush()
    return brackets


@pytest.fixture
def employee(db: Session, branch):
    data = EmployeeCreate(
        branch_id=branch.id,
        employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
        full_name="محمد عبدالله",
        position="محاسب",
        department="المالية",
        basic_salary=Decimal("5000.00"),
        hire_date=date(2023, 1, 1),
        birth_date=date(1990, 6, 15),
    )
    return services.create_employee(db, data)


class TestEmployee:

    def test_create_employee(self, db, branch):
        data = EmployeeCreate(
            branch_id=branch.id,
            employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
            full_name="سارة حسن",
            position="موظفة استقبال",
            basic_salary=Decimal("3500.00"),
            hire_date=date(2024, 3, 1),
        )
        emp = services.create_employee(db, data)
        assert emp.id is not None
        assert emp.status == "active"

    def test_duplicate_code_raises(self, db, branch, employee):
        data = EmployeeCreate(
            branch_id=branch.id,
            employee_code=employee.employee_code,  # كود مكرر
            full_name="موظف آخر",
            position="نادل",
            basic_salary=Decimal("2500.00"),
            hire_date=date(2024, 1, 1),
        )
        with pytest.raises(ValueError, match="مستخدم مسبقاً"):
            services.create_employee(db, data)

    def test_update_employee(self, db, employee):
        updated = services.update_employee(
            db, employee.id,
            EmployeeUpdate(position="مدير مالي", basic_salary=Decimal("8000.00")),
        )
        assert updated.position == "مدير مالي"
        assert updated.basic_salary == Decimal("8000.00")

    def test_terminate_employee(self, db, employee):
        updated = services.update_employee(
            db, employee.id,
            EmployeeUpdate(status="terminated"),
        )
        assert updated.status == "terminated"

    def test_salary_change_writes_audit_log(self, db, employee):
        from app.modules.core.crud import list_audit_logs
        from app.core.kernel.models.user import User
        from app.core.kernel.security import get_password_hash
        user = User(email=f"hrmgr-{uuid.uuid4().hex[:6]}@test.local",
                    password_hash=get_password_hash("Test@12345"),
                    full_name="HR Manager", role="admin", is_active=True)
        db.add(user); db.flush()

        old_salary = employee.basic_salary
        services.update_employee(
            db, employee.id,
            EmployeeUpdate(basic_salary=Decimal("9500.00")),
            updated_by=user.id,
        )
        logs, _ = list_audit_logs(db, entity_type="employee", entity_id=employee.id)
        salary_logs = [l for l in logs if l.action == "update_salary"]
        assert len(salary_logs) == 1
        assert salary_logs[0].user_id == user.id
        assert str(old_salary) in salary_logs[0].old_data
        assert "9500.00" in salary_logs[0].new_data

    def test_non_salary_update_does_not_write_audit_log(self, db, employee):
        from app.modules.core.crud import list_audit_logs
        services.update_employee(db, employee.id, EmployeeUpdate(position="مشرف"))
        logs, _ = list_audit_logs(db, entity_type="employee", entity_id=employee.id)
        assert not any(l.action == "update_salary" for l in logs)

    def test_employee_not_found_raises(self, db):
        with pytest.raises(ValueError):
            services.get_employee_or_404(db, 9999)


class TestPayroll:

    def test_calculate_employee_payroll(self, db, employee, si_config, tax_brackets):
        result = services.calculate_employee_payroll(
            db,
            employee_id=employee.id,
            period_year=2026,
            period_month=6,
        )
        assert result.basic_salary == Decimal("5000.00")
        assert result.gross_salary >= result.basic_salary
        assert result.net_salary < result.gross_salary  # بعد الاستقطاعات
        assert result.employee_si > Decimal("0")

    def test_payroll_with_penalty(self, db, employee, si_config, tax_brackets):
        result = services.calculate_employee_payroll(
            db,
            employee_id=employee.id,
            period_year=2026,
            period_month=6,
            penalty_days=2,
        )
        assert result.penalty_deduction > Decimal("0")
        # الراتب الصافي بعد الخصم أقل من الطبيعي
        base_result = services.calculate_employee_payroll(
            db, employee.id, 2026, 6,
        )
        assert result.net_salary < base_result.net_salary

    def test_calculate_payroll_no_si_config_raises(self, db, employee):
        """بدون SocialInsuranceConfig يُلقي خطأ."""
        with pytest.raises(ValueError, match="تأمينات"):
            services.calculate_employee_payroll(db, employee.id, 2026, 6)

    def test_calculate_payroll_no_tax_brackets_raises(self, db, employee, si_config):
        """SI موجود لكن TaxBracketConfig مفقود — يُلقي خطأ منفصل."""
        with pytest.raises(ValueError, match="ضريبية"):
            services.calculate_employee_payroll(db, employee.id, 2026, 6)

    def test_run_payroll_for_branch(self, db, branch, employee, si_config, tax_brackets):
        run = services.run_payroll_for_branch(db, branch.id, 2026, 6)
        assert run.id is not None
        assert run.status == "draft"
        assert run.total_gross > Decimal("0")
        assert run.total_net > Decimal("0")

    def test_duplicate_payroll_run_raises(self, db, branch, employee, si_config, tax_brackets):
        services.run_payroll_for_branch(db, branch.id, 2026, 7)
        with pytest.raises(ValueError, match="موجود مسبقاً"):
            services.run_payroll_for_branch(db, branch.id, 2026, 7)

    def test_approve_payroll_run(self, db, branch, employee, si_config, tax_brackets):
        run = services.run_payroll_for_branch(db, branch.id, 2026, 8)
        approved = services.approve_payroll_run(db, run.id, approved_by=1)
        assert approved.status == "approved"
        assert approved.approved_by == 1
        assert approved.approved_at is not None

    def test_cannot_approve_non_draft_run(self, db, branch, employee, si_config, tax_brackets):
        run = services.run_payroll_for_branch(db, branch.id, 2026, 9)
        services.approve_payroll_run(db, run.id, approved_by=1)
        with pytest.raises(ValueError, match="approved"):
            services.approve_payroll_run(db, run.id, approved_by=2)

    def test_approve_payroll_run_not_found_raises(self, db):
        with pytest.raises(ValueError, match="غير موجود"):
            services.approve_payroll_run(db, 999999, approved_by=1)

    def test_approve_payroll_run_posts_balanced_journal_when_accounts_exist(
        self, db, branch, employee, si_config, tax_brackets,
    ):
        """approve_payroll_run بيرحّل قيد محاسبي حقيقي لما دليل الحسابات
        (accounts 5100/2100/2110/2120) يكون موجود — بدونه بيتجاهل القيد بصمت
        (finance module اختياري من منظور HR).

        Regression: قبل الإصلاح كان فيه حساب "5110" بيدبّت run.total_si (SI
        الموظف) تحت مسمى "مصروف صاحب العمل" بدون أي قيد دائن مقابل — القيد
        كان بيطلع دايماً غير متوازن (مدين ≠ دائن) لما الحساب ده يكون موجود.
        اتشال، والتست ده بيتأكد إن القيد اللي بيترحّل فعلاً متوازن 100%."""
        from app.modules.finance.models import Account, JournalEntry, JournalLine

        for code, acc_type in [
            ("5100", "expense"),
            ("2100", "liability"), ("2110", "liability"), ("2120", "liability"),
        ]:
            db.add(Account(branch_id=branch.id, code=code, name=code, account_type=acc_type))
        db.commit()

        # موظف براتب أعلى — يضمن ضريبة دخل شهرية > 0، عشان نتأكد إن حساب
        # "2100" (ضريبة دخل مستحقة) فعلاً بيتضاف كسطر دائن في القيد، مش بس
        # 2110/2120.
        services.create_employee(db, EmployeeCreate(
            branch_id=branch.id, employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
            full_name="موظف راتب مرتفع", position="مدير", basic_salary=Decimal("25000.00"),
            hire_date=date(2020, 1, 1),
        ))

        run = services.run_payroll_for_branch(db, branch.id, 2026, 10)
        assert run.total_gross > Decimal("0")
        assert run.total_tax > Decimal("0")

        approved = services.approve_payroll_run(db, run.id, approved_by=1)
        assert approved.status == "approved"

        entry = (
            db.query(JournalEntry)
            .filter(JournalEntry.source == "payroll", JournalEntry.source_id == run.id)
            .first()
        )
        assert entry is not None, "لازم يترحّل قيد رواتب حقيقي لما الحسابات موجودة"
        lines = db.query(JournalLine).filter(JournalLine.entry_id == entry.id).all()
        assert len(lines) == 4  # 5100 + 2100 + 2110 + 2120
        total_debit  = sum(l.debit for l in lines)
        total_credit = sum(l.credit for l in lines)
        assert total_debit == total_credit, "القيد لازم يكون متوازن (مدين = دائن)"

    def test_approve_payroll_run_skips_journal_when_no_lines_computed(
        self, db, branch, si_config, tax_brackets,
    ):
        """فرع بدون أي موظف نشط — run.total_gross/total_tax/total_si/total_net
        كلهم صفر رغم إن دليل الحسابات موجود، فمفيش أي سطر يتضاف للقيد
        (lines فاضية) — لازم القيد يتجاهَل بهدوء، مش يترحّل قيد فاضي أو ينهار."""
        from app.modules.finance.models import Account, JournalEntry

        for code, acc_type in [
            ("5100", "expense"),
            ("2100", "liability"), ("2110", "liability"), ("2120", "liability"),
        ]:
            db.add(Account(branch_id=branch.id, code=code, name=code, account_type=acc_type))
        db.commit()

        run = services.run_payroll_for_branch(db, branch.id, 2026, 11)
        assert run.total_gross == Decimal("0")

        services.approve_payroll_run(db, run.id, approved_by=1)
        entry = (
            db.query(JournalEntry)
            .filter(JournalEntry.source == "payroll", JournalEntry.source_id == run.id)
            .first()
        )
        assert entry is None


class TestAttendance:

    def test_record_attendance(self, db, branch, employee):
        data = AttendanceRecordCreate(
            employee_id=employee.id,
            branch_id=branch.id,
            record_date=date.today(),
            check_in=datetime.utcnow(),
            status="present",
        )
        record = crud.upsert_attendance(db, data)
        assert record.id is not None
        assert record.status == "present"

    def test_upsert_attendance_updates_existing(self, db, branch, employee):
        today = date.today()
        data = AttendanceRecordCreate(
            employee_id=employee.id,
            branch_id=branch.id,
            record_date=today,
            status="present",
        )
        rec1 = crud.upsert_attendance(db, data)

        # تحديث نفس اليوم
        data2 = AttendanceRecordCreate(
            employee_id=employee.id,
            branch_id=branch.id,
            record_date=today,
            status="late",
            notes="تأخر 30 دقيقة",
        )
        rec2 = crud.upsert_attendance(db, data2)

        assert rec1.id == rec2.id
        assert rec2.status == "late"

    def test_record_absence(self, db, branch, employee):
        yesterday = date.today() - timedelta(days=1)
        data = AttendanceRecordCreate(
            employee_id=employee.id,
            branch_id=branch.id,
            record_date=yesterday,
            status="absent",
        )
        record = crud.upsert_attendance(db, data)
        assert record.status == "absent"


class TestSelfServicePunch:
    """POST /hr/me/attendance/punch-in|out — الفرونت إند مبني ومستني الـ endpoints
    دي، بس مكنتش موجودة خالص في الباك إند (باج حقيقي اتصلح)."""

    @pytest.fixture
    def linked_user_id(self, db: Session, employee) -> int:
        from app.core.kernel.models.user import User
        from app.core.kernel.security import get_password_hash
        user = User(
            email=f"emp-{uuid.uuid4().hex[:6]}@test.local",
            password_hash=get_password_hash("Test@12345"),
            full_name="حساب موظف اختباري", role="employee", is_active=True,
        )
        db.add(user)
        db.flush()
        services.link_employee_to_user(db, employee, user.id)
        return user.id

    def test_punch_in_creates_today_record(self, db, linked_user_id):
        record = services.punch_in(db, linked_user_id)
        assert record.check_in is not None
        assert record.record_date == date.today()

    def test_cannot_punch_in_twice(self, db, linked_user_id):
        services.punch_in(db, linked_user_id)
        with pytest.raises(ValueError, match="بالفعل"):
            services.punch_in(db, linked_user_id)

    def test_punch_out_requires_punch_in_first(self, db, linked_user_id):
        with pytest.raises(ValueError, match="الأول"):
            services.punch_out(db, linked_user_id)

    def test_punch_out_computes_hours_worked(self, db, linked_user_id):
        from app.modules.hr.schemas import AttendanceRecordRead

        record = services.punch_in(db, linked_user_id)
        record.check_in = datetime.utcnow() - timedelta(hours=8)
        db.commit()

        out = services.punch_out(db, linked_user_id)
        assert out.check_out is not None

        read = AttendanceRecordRead.model_validate(out)
        assert read.hours_worked is not None
        assert 7.9 <= read.hours_worked <= 8.1

    def test_cannot_punch_out_twice(self, db, linked_user_id):
        services.punch_in(db, linked_user_id)
        services.punch_out(db, linked_user_id)
        with pytest.raises(ValueError, match="بالفعل"):
            services.punch_out(db, linked_user_id)


class TestLeaderboard:
    """لوحة أداء الموظفين — لازم تكون مبيعات حقيقية من الطلبات المدفوعة فعليًا،
    مش أرقام مصنوعة."""

    def _make_paid_restaurant_order(self, db, branch, waiter_user_id, amount):
        import uuid as _uuid
        from app.modules.restaurant.models import MenuItem
        from app.modules.restaurant.schemas import OrderCreate, OrderItemCreate
        from app.modules.restaurant import services as rest_services

        item = MenuItem(branch_id=branch.id, name=f"Item {_uuid.uuid4().hex[:4]}", price=amount)
        db.add(item); db.commit()
        data = OrderCreate(order_type="takeaway", guests_count=1,
                            items=[OrderItemCreate(menu_item_id=item.id, quantity=1)])
        order = rest_services.create_order(db, branch.id, data, waiter_id=waiter_user_id)
        rest_services.update_order_status(db, order.id, "paid")
        return order

    def test_leaderboard_ranks_by_real_sales(self, db, branch, employee):
        from decimal import Decimal as D
        from app.core.kernel.models.user import User
        from app.core.kernel.security import get_password_hash

        top_user = User(email=f"top-{uuid.uuid4().hex[:6]}@test.local",
                         password_hash=get_password_hash("Test@12345"),
                         full_name="Top Seller", role="waiter", is_active=True)
        low_user = User(email=f"low-{uuid.uuid4().hex[:6]}@test.local",
                         password_hash=get_password_hash("Test@12345"),
                         full_name="Low Seller", role="waiter", is_active=True)
        db.add_all([top_user, low_user]); db.flush()
        services.link_employee_to_user(db, employee, top_user.id)

        self._make_paid_restaurant_order(db, branch, top_user.id, D("500"))
        self._make_paid_restaurant_order(db, branch, top_user.id, D("300"))
        self._make_paid_restaurant_order(db, branch, low_user.id, D("50"))

        # نطاق يومين حوالين اليوم (مش يوم واحد بالظبط) — الـ timestamps بتتسجل
        # بتوقيت UTC من السيرفر بينما date.today() المحلي ممكن يكون قدّامه
        # بساعتين/تلاتة، فيوم واحد بالظبط عرضة لفلاكي قريب من منتصف الليل.
        today = date.today()
        board = services.get_sales_leaderboard(
            db, branch.id, today - timedelta(days=1), today + timedelta(days=1),
        )

        assert board[0].user_id == top_user.id
        assert board[0].employee_name == employee.full_name
        assert board[0].order_count == 2
        assert board[1].user_id == low_user.id
        assert board[1].employee_name is None  # مفيش Employee مربوط بيه
        assert board[0].total_sales > board[1].total_sales

    def test_leaderboard_ignores_unpaid_orders(self, db, branch):
        from app.modules.restaurant.models import MenuItem
        from app.modules.restaurant.schemas import OrderCreate, OrderItemCreate
        from app.modules.restaurant import services as rest_services

        item = MenuItem(branch_id=branch.id, name="Unpaid Item", price=Decimal("100"))
        db.add(item); db.commit()
        data = OrderCreate(order_type="takeaway", guests_count=1,
                            items=[OrderItemCreate(menu_item_id=item.id, quantity=1)])
        rest_services.create_order(db, branch.id, data, waiter_id=999)  # لسه "open"، مش paid

        today = date.today()
        board = services.get_sales_leaderboard(
            db, branch.id, today - timedelta(days=1), today + timedelta(days=1),
        )
        assert not any(e.user_id == 999 for e in board)

    def test_leaderboard_includes_cafe_and_beach_sales(self, db, branch):
        """لوحة الأداء لازم تجمع مبيعات الكافيه والشاطئ مش بس المطعم — الفروع
        التلاتة بتتجمّع في _accumulate واحدة."""
        from datetime import datetime as _dt
        from app.modules.cafe.models import CafeOrder
        from app.modules.beach.models import BeachTransaction

        cafe_order = CafeOrder(
            branch_id=branch.id, order_number=f"CAF-{uuid.uuid4().hex[:8]}",
            status="paid", total=Decimal("120.00"), waiter_id=777,
        )
        # طلب كافيه بدون waiter_id — لازم يتجاهله _accumulate بهدوء (guard clause)
        cafe_order_no_waiter = CafeOrder(
            branch_id=branch.id, order_number=f"CAF-{uuid.uuid4().hex[:8]}",
            status="paid", total=Decimal("999.00"), waiter_id=None,
        )
        db.add_all([cafe_order, cafe_order_no_waiter])

        beach_tx = BeachTransaction(
            branch_id=branch.id, tx_type="entry", quantity=1,
            unit_price=Decimal("200.00"), total_amount=Decimal("200.00"),
            vat_amount=Decimal("28.00"), tx_date=date.today(), cashier_id=888,
        )
        db.add(beach_tx)
        db.commit()

        today = date.today()
        board = services.get_sales_leaderboard(
            db, branch.id, today - timedelta(days=1), today + timedelta(days=1),
        )

        cafe_entry = next(e for e in board if e.user_id == 777)
        assert cafe_entry.total_sales == Decimal("120.00")
        assert cafe_entry.employee_name is None  # مفيش Employee مربوط

        beach_entry = next(e for e in board if e.user_id == 888)
        assert beach_entry.total_sales == Decimal("228.00")  # total_amount + vat_amount

        assert not any(e.user_id is None for e in board)  # الـ guard منع None


class TestLeaveBalance:

    def test_upsert_leave_balance(self, db, employee):
        balance = crud.upsert_leave_balance(db, employee.id, year=2026, annual_entitled=21)
        assert balance.id is not None
        assert balance.annual_entitled == 21
        assert balance.annual_taken == 0

    def test_upsert_updates_existing(self, db, employee):
        crud.upsert_leave_balance(db, employee.id, year=2026, annual_entitled=21)
        updated = crud.upsert_leave_balance(db, employee.id, year=2026, annual_entitled=25)
        # نفس السنة — يُحدَّث
        balance = crud.get_leave_balance(db, employee.id, year=2026)
        assert balance.annual_entitled == 25


# ── Fixtures for new modules ──────────────────────────────────────────

@pytest.fixture
def leave_type(db: Session, branch):
    data = LeaveTypeCreate(
        branch_id=branch.id,
        name="إجازة سنوية",
        name_ar="Annual Leave",
        is_paid=True,
        max_days_per_year=21,
        requires_approval=True,
    )
    lt = crud.create_leave_type(db, data)
    db.commit()
    db.refresh(lt)
    return lt


@pytest.fixture
def shift(db: Session, branch):
    data = ShiftCreate(
        branch_id=branch.id,
        name="Morning",
        name_ar="الصباح",
        start_time="08:00",
        end_time="16:00",
        duration_hours=Decimal("8"),
    )
    s = crud.create_shift(db, data)
    db.commit()
    db.refresh(s)
    return s


@pytest.fixture
def department(db: Session, branch):
    data = DepartmentCreate(
        branch_id=branch.id,
        name="Front Office",
        name_ar="الاستقبال",
        budget_limit=Decimal("50000"),
    )
    dept = crud.create_department(db, data)
    db.commit()
    db.refresh(dept)
    return dept


class TestLeaveManagement:

    def test_create_leave_type(self, db, branch):
        data = LeaveTypeCreate(
            branch_id=branch.id,
            name="إجازة مرضية",
            is_paid=True,
            max_days_per_year=15,
            requires_approval=False,
        )
        lt = crud.create_leave_type(db, data)
        db.commit()
        assert lt.id is not None
        assert lt.name == "إجازة مرضية"
        assert lt.is_paid is True

    def test_list_leave_types(self, db, branch, leave_type):
        types = crud.list_leave_types(db, branch.id)
        assert len(types) >= 1
        assert any(lt.name == "إجازة سنوية" for lt in types)

    def test_request_leave(self, db, branch, employee, leave_type):
        start = date(2026, 8, 1)
        end   = date(2026, 8, 5)
        req = services.request_leave(
            db,
            employee_id=employee.id,
            branch_id=branch.id,
            leave_type_id=leave_type.id,
            start_date=start,
            end_date=end,
            reason="رحلة عائلية",
        )
        assert req.id is not None
        assert req.status == "pending"
        assert req.days_requested == 5

    def test_request_leave_insufficient_balance(self, db, branch, employee, leave_type):
        """الطلب يُرفض إذا تجاوز الرصيد المتاح."""
        # أنشئ سلد إجازة مع 0 متبقٍ
        balance = crud.upsert_leave_balance(db, employee.id, year=2026, annual_entitled=5)
        balance.annual_taken = 5
        db.flush()
        db.commit()

        with pytest.raises(ValueError, match="سلد"):
            services.request_leave(
                db,
                employee_id=employee.id,
                branch_id=branch.id,
                leave_type_id=leave_type.id,
                start_date=date(2026, 9, 1),
                end_date=date(2026, 9, 10),
            )

    def test_approve_leave_updates_balance(self, db, branch, employee, leave_type):
        # أنشئ سلد فعلي
        crud.upsert_leave_balance(db, employee.id, year=2026, annual_entitled=21)
        db.commit()

        start = date(2026, 10, 1)
        end   = date(2026, 10, 3)
        req = services.request_leave(
            db,
            employee_id=employee.id,
            branch_id=branch.id,
            leave_type_id=leave_type.id,
            start_date=start,
            end_date=end,
        )

        approved = services.approve_leave(db, req.id, approved_by=1)
        assert approved.status == "approved"
        assert approved.approved_by == 1
        assert approved.approved_at is not None

        # السلد يُحدَّث
        balance = crud.get_leave_balance(db, employee.id, 2026)
        assert balance.annual_taken == 3

    def test_reject_leave(self, db, branch, employee, leave_type):
        req = services.request_leave(
            db,
            employee_id=employee.id,
            branch_id=branch.id,
            leave_type_id=leave_type.id,
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 2),
        )
        rejected = services.reject_leave(db, req.id, reason="فترة مكتظة")
        assert rejected.status == "rejected"
        assert rejected.rejection_reason == "فترة مكتظة"

    def test_cannot_approve_already_processed_request(self, db, branch, employee, leave_type):
        req = services.request_leave(
            db,
            employee_id=employee.id,
            branch_id=branch.id,
            leave_type_id=leave_type.id,
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 1),
        )
        services.approve_leave(db, req.id, approved_by=1)
        with pytest.raises(ValueError, match="approved"):
            services.approve_leave(db, req.id, approved_by=2)

    def test_approve_leave_not_found_raises(self, db):
        with pytest.raises(ValueError, match="غير موجود"):
            services.approve_leave(db, 999999, approved_by=1)

    def test_reject_leave_not_found_raises(self, db):
        with pytest.raises(ValueError, match="غير موجود"):
            services.reject_leave(db, 999999, reason="أي سبب")

    def test_reject_already_processed_request_raises(self, db, branch, employee, leave_type):
        req = services.request_leave(
            db,
            employee_id=employee.id,
            branch_id=branch.id,
            leave_type_id=leave_type.id,
            start_date=date(2026, 12, 15),
            end_date=date(2026, 12, 15),
        )
        services.reject_leave(db, req.id, reason="مرفوض أول مرة")
        with pytest.raises(ValueError, match="rejected"):
            services.reject_leave(db, req.id, reason="محاولة تانية")


class TestPenalties:

    def test_create_penalty(self, db, branch, employee):
        data = EmployeePenaltyCreate(
            employee_id=employee.id,
            branch_id=branch.id,
            penalty_date=date(2026, 6, 10),
            penalty_days=1,
            reason="تأخر متكرر",
            applied_by=1,
        )
        penalty = crud.create_penalty(db, data)
        db.commit()
        assert penalty.id is not None
        assert penalty.penalty_days == 1

    def test_list_penalties_by_month(self, db, branch, employee):
        # إنشاء عقوبتين في شهرين مختلفين
        for day, month in [(5, 6), (7, 7)]:
            crud.create_penalty(db, EmployeePenaltyCreate(
                employee_id=employee.id,
                branch_id=branch.id,
                penalty_date=date(2026, month, day),
                penalty_days=1,
                reason="تأخر",
                applied_by=1,
            ))
        db.commit()

        june_penalties = crud.list_penalties(db, branch.id, employee_id=employee.id, month="2026-06")
        july_penalties = crud.list_penalties(db, branch.id, employee_id=employee.id, month="2026-07")
        assert len(june_penalties) >= 1
        assert len(july_penalties) >= 1
        # تأكد أن فلتر الشهر يعمل
        assert all(p.penalty_date.month == 6 for p in june_penalties)
        assert all(p.penalty_date.month == 7 for p in july_penalties)


class TestRota:

    def test_create_department(self, db, branch):
        data = DepartmentCreate(
            branch_id=branch.id,
            name="Housekeeping",
            name_ar="التدبير المنزلي",
            budget_limit=Decimal("30000"),
        )
        dept = crud.create_department(db, data)
        db.commit()
        assert dept.id is not None
        assert dept.name == "Housekeeping"

    def test_list_departments(self, db, branch, department):
        depts = crud.list_departments(db, branch.id)
        assert len(depts) >= 1

    def test_create_shift(self, db, branch):
        data = ShiftCreate(
            branch_id=branch.id,
            name="Night",
            name_ar="الليل",
            start_time="23:00",
            end_time="07:00",
            duration_hours=Decimal("8"),
        )
        shift = crud.create_shift(db, data)
        db.commit()
        assert shift.id is not None
        assert shift.start_time == "23:00"

    def test_list_shifts(self, db, branch, shift):
        shifts = crud.list_shifts(db, branch.id)
        assert len(shifts) >= 1

    def test_create_rota_assignment(self, db, branch, employee, shift):
        data = RotaAssignmentCreate(
            branch_id=branch.id,
            employee_id=employee.id,
            shift_id=shift.id,
            assigned_date=date(2026, 7, 7),
            notes="وردية إضافية",
        )
        assignment = crud.create_rota_assignment(db, data)
        db.commit()
        assert assignment.id is not None
        assert assignment.status == "scheduled"

    def test_list_rota_assignments_by_week(self, db, branch, employee, shift):
        # إنشاء 3 مهام في أسابيع مختلفة
        dates = [date(2026, 7, 7), date(2026, 7, 8), date(2026, 7, 15)]
        for d in dates:
            crud.create_rota_assignment(db, RotaAssignmentCreate(
                branch_id=branch.id,
                employee_id=employee.id,
                shift_id=shift.id,
                assigned_date=d,
            ))
        db.commit()

        week1 = crud.list_rota_assignments(
            db, branch.id, week_start=date(2026, 7, 6), week_end=date(2026, 7, 12)
        )
        week2 = crud.list_rota_assignments(
            db, branch.id, week_start=date(2026, 7, 13), week_end=date(2026, 7, 19)
        )
        assert len(week1) >= 2
        assert len(week2) >= 1

    def test_shift_swap_request(self, db, branch, employee, shift):
        """اختبار إنشاء وموافقة طلب تبديل الوردية."""
        # إنشاء موظف ثانٍ
        emp2_data = EmployeeCreate(
            branch_id=branch.id,
            employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
            full_name="أحمد محمود",
            position="نادل",
            basic_salary=Decimal("3000.00"),
            hire_date=date(2023, 6, 1),
        )
        emp2 = services.create_employee(db, emp2_data)

        # إنشاء مهمتين
        a1 = crud.create_rota_assignment(db, RotaAssignmentCreate(
            branch_id=branch.id, employee_id=employee.id,
            shift_id=shift.id, assigned_date=date(2026, 8, 5),
        ))
        a2 = crud.create_rota_assignment(db, RotaAssignmentCreate(
            branch_id=branch.id, employee_id=emp2.id,
            shift_id=shift.id, assigned_date=date(2026, 8, 6),
        ))
        db.commit()

        # طلب تبديل
        swap_data = ShiftSwapRequestCreate(
            branch_id=branch.id,
            requester_id=employee.id,
            target_employee_id=emp2.id,
            from_assignment_id=a1.id,
            to_assignment_id=a2.id,
            reason="ظرف طارئ",
        )
        swap = crud.create_swap_request(db, swap_data)
        db.commit()
        assert swap.status == "pending"

        # الموافقة
        approved_swap = crud.approve_swap(db, swap, approver_id=1)
        db.commit()
        assert approved_swap.status == "approved"
        assert approved_swap.approver_id == 1

        # تحقق من تبديل الموظفين
        db.refresh(a1)
        db.refresh(a2)
        assert a1.employee_id == emp2.id
        assert a2.employee_id == employee.id


class TestPayslipPdfWithDeductions:
    """generate_payslip_pdf بيضيف سطرين إضافيين (جزاءات/إجازة بدون أجر) بس
    لما القيمة فعلاً أكبر من صفر — الفروع دي كانت غير مغطاة، ومهمة لأن قسيمة
    الراتب الحقيقية لازم تعرض سبب أي خصم غير قياسي للموظف."""

    def test_payslip_pdf_includes_penalty_and_unpaid_leave_lines(self, db, branch, employee):
        from app.modules.hr.models import PayrollRun, PayrollLine

        run = PayrollRun(
            branch_id=branch.id, period_year=2027, period_month=1, status="approved",
            total_gross=Decimal("5000.00"), total_net=Decimal("4000.00"),
            total_tax=Decimal("300.00"), total_si=Decimal("400.00"),
        )
        db.add(run)
        db.flush()
        line = PayrollLine(
            payroll_run_id=run.id, employee_id=employee.id,
            basic_salary=Decimal("5000.00"), gross_salary=Decimal("5000.00"),
            net_salary=Decimal("4000.00"), employee_si=Decimal("400.00"),
            employer_si=Decimal("600.00"), monthly_tax=Decimal("300.00"),
            penalty_deduction=Decimal("150.00"), unpaid_leave_deduction=Decimal("200.00"),
        )
        db.add(line)
        db.commit()

        pdf_bytes = services.generate_payslip_pdf(db, run.id, employee.id)
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 500
        assert pdf_bytes.startswith(b"%PDF")

    def test_payslip_pdf_404_when_run_missing(self, db):
        with pytest.raises(ValueError, match="غير موجود"):
            services.generate_payslip_pdf(db, 999999, 1)

    def test_payslip_pdf_404_when_employee_not_in_run(self, db, branch, employee):
        from app.modules.hr.models import PayrollRun

        run = PayrollRun(
            branch_id=branch.id, period_year=2027, period_month=2, status="approved",
            total_gross=Decimal("0"), total_net=Decimal("0"),
            total_tax=Decimal("0"), total_si=Decimal("0"),
        )
        db.add(run)
        db.commit()
        with pytest.raises(ValueError, match="غير موجود"):
            services.generate_payslip_pdf(db, run.id, employee.id)
