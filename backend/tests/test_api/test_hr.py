"""
tests/test_api/test_hr.py
Integration tests for HR module.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

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

    def test_run_payroll_applies_registered_penalties_automatically(
        self, db, branch, employee, si_config, tax_brackets,
    ):
        """⚠️ باج حقيقي: run_payroll_for_branch كان بينادي
        calculate_employee_payroll من غير ما يبعت penalty_days خالص — يعني أي
        EmployeePenalty متسجّلة فعليًا (عن طريق POST /hr/penalties) كانت
        بتتجاهَل تمامًا وقت تشغيل كشف الرواتب الحقيقي، وتشتغل بس لو الأدمن
        كتب الرقم يدويًا في preview endpoint. دلوقتي لازم كشف الرواتب يجمع
        جزاءات الشهر المسجّلة فعليًا ويطبّقها تلقائيًا."""
        from app.modules.hr.schemas import EmployeePenaltyCreate

        baseline = services.run_payroll_for_branch(db, branch.id, 2026, 6)
        baseline_line = crud.list_lines_for_run(db, baseline.id)[0]
        assert baseline_line.penalty_deduction == Decimal("0")

        crud.create_penalty(db, EmployeePenaltyCreate(
            employee_id=employee.id, branch_id=branch.id,
            penalty_date=date(2026, 7, 10), penalty_days=2,
            reason="تأخر", applied_by=1,
        ))
        db.commit()

        run = services.run_payroll_for_branch(db, branch.id, 2026, 7)
        line = crud.list_lines_for_run(db, run.id)[0]
        assert line.penalty_deduction > Decimal("0")
        expected = (employee.basic_salary / Decimal("30") * Decimal("2")).quantize(Decimal("0.01"))
        assert line.penalty_deduction == expected
        assert line.net_salary < baseline_line.net_salary

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

    def test_new_tax_bracket_version_does_not_corrupt_current_period(
        self, db, employee, si_config, tax_brackets,
    ):
        """⚠️ باج حقيقي وخطير: get_active_tax_brackets كانت بترجع *كل* الصفوف
        is_active=True مع بعض بغض النظر عن effective_from — يعني إضافة نسخة
        شرائح جديدة (لما القانون يتغيّر، بالظبط الاستخدام اللي endpoint
        POST /hr/config/tax-brackets اتعمل عشانه) كانت بتكسر حساب الضريبة
        لكل الفترات فورًا (حتى الفترات الماضية والحاضرة)، مش بس المستقبلية،
        لأن شرائح النسختين كانت بتتجمّع في قايمة واحدة بمعدلات متضاربة."""
        from app.modules.hr.models import TaxBracketConfig

        before = services.calculate_employee_payroll(db, employee.id, 2026, 6)

        # نسخة "قانون جديد" مستقبلية — 0% لحد 20000 بدل الشرائح الحالية
        db.add(TaxBracketConfig(
            lower_bound=Decimal("0"), upper_bound=Decimal("20000"),
            rate=Decimal("0.0000"), effective_from=date(2027, 1, 1), is_active=True,
        ))
        db.add(TaxBracketConfig(
            lower_bound=Decimal("20000"), upper_bound=None,
            rate=Decimal("0.0500"), effective_from=date(2027, 1, 1), is_active=True,
        ))
        db.commit()

        after_current_period = services.calculate_employee_payroll(db, employee.id, 2026, 6)
        assert after_current_period.monthly_tax == before.monthly_tax, (
            "إضافة شرائح ضريبية مستقبلية لازم متأثرش حساب فترة حالية/ماضية"
        )

        future_period = services.calculate_employee_payroll(db, employee.id, 2027, 3)
        assert future_period.monthly_tax != before.monthly_tax, (
            "فترة مستقبلية (بعد effective_from) لازم تستخدم الشرائح الجديدة فعلاً"
        )

    def test_new_si_config_version_does_not_corrupt_current_period(
        self, db, employee, si_config, tax_brackets,
    ):
        """نفس فئة الباج فوق لكن لـ SocialInsuranceConfig — get_active_si_config
        كانت بترجع أحدث effective_from بس (من غير مقارنة بفترة الطلب)، يعني
        نسخة مستقبلية كانت بتُستخدم فورًا حتى لحساب فترة حالية/ماضية."""
        from app.modules.hr.models import SocialInsuranceConfig

        before = services.calculate_employee_payroll(db, employee.id, 2026, 6)

        db.add(SocialInsuranceConfig(
            max_insurable_salary=Decimal("30000.00"), employee_rate=Decimal("0.1100"),
            employer_rate=Decimal("0.1875"), personal_exemption_annual=Decimal("15000.00"),
            max_penalty_days_monthly=5, effective_from=date(2027, 1, 1), is_active=True,
        ))
        db.commit()

        after_current_period = services.calculate_employee_payroll(db, employee.id, 2026, 6)
        assert after_current_period.insurable_salary == before.insurable_salary

        future_period = services.calculate_employee_payroll(db, employee.id, 2027, 3)
        assert future_period.insurable_salary == employee.basic_salary  # الحد الأقصى الجديد أعلى من الراتب

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


def _cairo_to_utc_naive(d: date, hour: int, minute: int) -> datetime:
    """تحويل تاريخ+وقت بتوقيت القاهرة لـ UTC naive — نفس تمثيل check_in/
    check_out المخزّن فعليًا بالداتابيز. مطابق تمامًا لـ hr_engine.
    _local_wall_time_to_utc_naive الداخلية، مكرّر هنا عمدًا (تست مستقل)."""
    tz = ZoneInfo("Africa/Cairo")
    local_dt = datetime(d.year, d.month, d.day, hour, minute, tzinfo=tz)
    return local_dt.astimezone(timezone.utc).replace(tzinfo=None)


class TestAttendancePolicyAndAutoPayroll:
    """المسار الكامل: بصمات حضور خام (AttendanceRecord) + سياسة حضور
    (AttendancePolicy) → دقايق تأخير/أوفرتايم محسوبة تلقائيًا → مبلغ مالي
    حقيقي يدخل run_payroll_for_branch، بالتعايش الكامل مع الجزاءات اليدوية
    الموجودة أصلاً (EmployeePenalty)."""

    @pytest.fixture
    def policy(self, db: Session, branch):
        from app.modules.hr.models import AttendancePolicy
        p = AttendancePolicy(
            branch_id=branch.id,
            late_grace_minutes=10,
            early_leave_grace_minutes=10,
            standard_shift_start="09:00",
            standard_shift_end="17:00",
            overtime_rate_multiplier=Decimal("1.50"),
            late_penalty_rate_multiplier=Decimal("1.00"),
            is_active=True,
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        return p

    def test_run_payroll_computes_late_and_overtime_from_real_attendance(
        self, db, branch, employee, si_config, tax_brackets, policy,
    ):
        """موظف براتب أساسي 6000: يوم متأخر 20 دقيقة (فوق سماح 10) + يوم
        بأوفرتايم 90 دقيقة. معدل يومي = 200، معدل ساعة = 25 (وردية 8 ساعات).
        overtime = (90/60)×25×1.5 = 56.25. late_penalty = (20/60)×25×1.0 = 8.33.
        """
        employee.basic_salary = Decimal("6000.00")
        db.commit()

        crud.upsert_attendance(db, AttendanceRecordCreate(
            employee_id=employee.id, branch_id=branch.id, record_date=date(2026, 6, 5),
            check_in=_cairo_to_utc_naive(date(2026, 6, 5), 9, 20),
            check_out=_cairo_to_utc_naive(date(2026, 6, 5), 17, 0),
            status="late",
        ))
        crud.upsert_attendance(db, AttendanceRecordCreate(
            employee_id=employee.id, branch_id=branch.id, record_date=date(2026, 6, 6),
            check_in=_cairo_to_utc_naive(date(2026, 6, 6), 9, 0),
            check_out=_cairo_to_utc_naive(date(2026, 6, 6), 18, 30),
            status="present",
        ))
        db.commit()

        run = services.run_payroll_for_branch(db, branch.id, 2026, 6)
        lines = crud.list_lines_for_run(db, run.id)
        line = next(l for l in lines if l.employee_id == employee.id)

        assert line.gross_salary - line.basic_salary == Decimal("56.25")  # overtime داخل الإجمالي
        assert line.late_penalty_deduction == Decimal("8.33")

    def test_manual_penalty_coexists_with_automatic_late_deduction(
        self, db, branch, employee, si_config, tax_brackets, policy,
    ):
        """جزاء تأديبي يدوي (EmployeePenalty، يوم واحد) + تأخير تلقائي من
        الحضور (فوق السماح) — لازم الاتنين يتخصموا مع بعض، مش أحدهما بدل
        التاني. run_payroll_for_branch قبل الإصلاح كان بيتجاهل EmployeePenalty
        بالكامل (دايمًا penalty_days=0)."""
        employee.basic_salary = Decimal("6000.00")
        db.commit()

        crud.create_penalty(db, EmployeePenaltyCreate(
            employee_id=employee.id, branch_id=branch.id,
            penalty_date=date(2026, 7, 10), penalty_days=1,
            reason="تأخر متكرر", applied_by=1,
        ))
        crud.upsert_attendance(db, AttendanceRecordCreate(
            employee_id=employee.id, branch_id=branch.id, record_date=date(2026, 7, 5),
            check_in=_cairo_to_utc_naive(date(2026, 7, 5), 9, 20),  # 20 دقيقة تأخير
            check_out=_cairo_to_utc_naive(date(2026, 7, 5), 17, 0),
            status="late",
        ))
        db.commit()

        run = services.run_payroll_for_branch(db, branch.id, 2026, 7)
        lines = crud.list_lines_for_run(db, run.id)
        line = next(l for l in lines if l.employee_id == employee.id)

        assert line.penalty_deduction == Decimal("200.00")       # يدوي: يوم واحد × 6000/30
        assert line.late_penalty_deduction == Decimal("8.33")    # تلقائي: 20 دقيقة تأخير

    def test_no_policy_means_zero_automatic_adjustments(
        self, db, branch, employee, si_config, tax_brackets,
    ):
        """بدون AttendancePolicy للفرع (fixture مش مستخدَم هنا) — الحساب
        التلقائي يرجع صفر بالظبط، ومفيش أي انهيار أو تغيير سلوك عن قبل الميزة."""
        crud.upsert_attendance(db, AttendanceRecordCreate(
            employee_id=employee.id, branch_id=branch.id, record_date=date(2026, 8, 5),
            check_in=_cairo_to_utc_naive(date(2026, 8, 5), 9, 20),
            check_out=_cairo_to_utc_naive(date(2026, 8, 5), 18, 30),
            status="late",
        ))
        db.commit()

        run = services.run_payroll_for_branch(db, branch.id, 2026, 8)
        lines = crud.list_lines_for_run(db, run.id)
        line = next(l for l in lines if l.employee_id == employee.id)

        assert line.late_penalty_deduction == Decimal("0.00")
        assert line.gross_salary == line.basic_salary  # مفيش أوفرتايم اتضاف

    def test_rota_assignment_shift_overrides_policy_default_in_payroll(
        self, db, branch, employee, si_config, tax_brackets, policy,
    ):
        """موظف ليه RotaAssignment→Shift مضبوط بوردية مختلفة عن fallback
        السياسة (12:00-20:00 بدل 09:00-17:00) — لازم الحساب التلقائي
        يستخدم وردية الموظف الفعلية، مش fallback الفرع العام."""
        shift = crud.create_shift(db, ShiftCreate(
            branch_id=branch.id, name="Afternoon", start_time="12:00", end_time="20:00",
            duration_hours=Decimal("8"),
        ))
        crud.create_rota_assignment(db, RotaAssignmentCreate(
            branch_id=branch.id, employee_id=employee.id, shift_id=shift.id,
            assigned_date=date(2026, 9, 5),
        ))
        # دخول 12:05 (5 دقايق تأخير عن 12:00 — تحت سماح 10 دقايق) — لو النظام
        # غلط استخدم fallback 09:00 كان هيحسبها تأخير ساعات، مش صفر.
        crud.upsert_attendance(db, AttendanceRecordCreate(
            employee_id=employee.id, branch_id=branch.id, record_date=date(2026, 9, 5),
            check_in=_cairo_to_utc_naive(date(2026, 9, 5), 12, 5),
            check_out=_cairo_to_utc_naive(date(2026, 9, 5), 20, 0),
            status="present",
        ))
        db.commit()

        run = services.run_payroll_for_branch(db, branch.id, 2026, 9)
        lines = crud.list_lines_for_run(db, run.id)
        line = next(l for l in lines if l.employee_id == employee.id)

        assert line.late_penalty_deduction == Decimal("0.00")


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
        """record_date لازم يتحسب بتوقيت المنتجع (settings.TIMEZONE، راجع
        app.resort_os.timezone_utils.local_today) مش date.today() الخام —
        الاتنين بيتطابقوا بالصدفة بس لو نظام تشغيل السيرفر نفسه مضبوط على
        Africa/Cairo، وده مش مضمون في أي بيئة إنتاج/CI حقيقية (غالبًا UTC)."""
        from app.core.config import settings
        from app.resort_os.timezone_utils import local_today

        record = services.punch_in(db, linked_user_id)
        assert record.check_in is not None
        assert record.record_date == local_today(settings.TIMEZONE)

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

    def test_request_leave_end_before_start_raises(self, db, branch, employee, leave_type):
        """تاريخ نهاية قبل البداية — لازم يترفض برسالة واضحة."""
        with pytest.raises(ValueError, match="نهاية"):
            services.request_leave(
                db, employee_id=employee.id, branch_id=branch.id,
                leave_type_id=leave_type.id,
                start_date=date(2026, 8, 10), end_date=date(2026, 8, 5),
            )

    def test_request_leave_overlapping_pending_raises(self, db, branch, employee, leave_type):
        """طلب إجازة يتداخل مع طلب معلّق سابق لنفس الموظف لازم يترفض — بدون
        كده الموظف كان يقدر يبقى عنده أكتر من طلب معتمد لنفس اليوم."""
        services.request_leave(
            db, employee_id=employee.id, branch_id=branch.id,
            leave_type_id=leave_type.id,
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 5),
        )
        with pytest.raises(ValueError, match="يتداخل"):
            services.request_leave(
                db, employee_id=employee.id, branch_id=branch.id,
                leave_type_id=leave_type.id,
                start_date=date(2026, 8, 3), end_date=date(2026, 8, 7),
            )

    def test_request_leave_non_overlapping_succeeds(self, db, branch, employee, leave_type):
        """طلبين متتاليين من غير تداخل فعلي (يوم بعد ما ينتهي التاني) لازم
        يعدّوا عادي — الفحص لازم يكون تقاطع حقيقي مش أي طلبين لنفس الموظف."""
        services.request_leave(
            db, employee_id=employee.id, branch_id=branch.id,
            leave_type_id=leave_type.id,
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 5),
        )
        second = services.request_leave(
            db, employee_id=employee.id, branch_id=branch.id,
            leave_type_id=leave_type.id,
            start_date=date(2026, 8, 6), end_date=date(2026, 8, 8),
        )
        assert second.id is not None

    def test_cannot_self_approve_own_leave(self, db, branch, leave_type):
        """⚠️ باج حقيقي: approve_leave ما كانش بيتحقق خالص من إن approved_by
        هو نفسه صاحب الطلب — موظف مرتبط بحساب مدير كان يقدر يعتمد إجازته
        الخاصة. الموظف لازم يبقى مربوط بـ user_id عشان الفحص يتفعّل."""
        from app.core.kernel.models.user import User
        from app.core.kernel.security import get_password_hash
        from app.modules.hr.models import Employee

        requester_user = User(
            email=f"self-approve-{uuid.uuid4().hex[:6]}@test.local",
            password_hash=get_password_hash("Test@12345"),
            full_name="مدير نفسه (حساب)", role="manager", is_active=True,
        )
        other_manager_user = User(
            email=f"other-manager-{uuid.uuid4().hex[:6]}@test.local",
            password_hash=get_password_hash("Test@12345"),
            full_name="مدير تاني", role="manager", is_active=True,
        )
        db.add_all([requester_user, other_manager_user])
        db.flush()

        emp = Employee(
            branch_id=branch.id, employee_code=f"EMP-SELF-{uuid.uuid4().hex[:6].upper()}",
            full_name="مدير نفسه", position="مدير", basic_salary=Decimal("9000.00"),
            hire_date=date(2022, 1, 1), user_id=requester_user.id,
        )
        db.add(emp)
        db.commit()
        db.refresh(emp)

        req = services.request_leave(
            db, employee_id=emp.id, branch_id=branch.id,
            leave_type_id=leave_type.id,
            start_date=date(2026, 8, 20), end_date=date(2026, 8, 22),
        )
        with pytest.raises(ValueError, match="اعتماد طلب إجازته الخاص"):
            services.approve_leave(db, req.id, approved_by=requester_user.id)

        # مدير مختلف (user_id تاني) يقدر يعتمدها عادي
        approved = services.approve_leave(db, req.id, approved_by=other_manager_user.id)
        assert approved.status == "approved"


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
