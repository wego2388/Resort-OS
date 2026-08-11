"""tests/test_hist_hr.py — HIST-01 HR generator (OPS-DATA-02 §10.1).

⚠️ Employee.employee_code فريد عالميًا (مش مقيّد بالفرع — نفس منطق منتجع
واحد، راجع models.py) فمولّد HR بيستخدم أكواد ثابتة زي §10.1 بالظبط
("MGR-01"، ...). عشان كده الاختبارات هنا بتشغّل المولّد **مرة واحدة بس**
عبر فيكستشر class-scoped (زي إعداد الحقيقة على الإنتاج فعليًا: مرة واحدة
لكل فترة)، مش مرة لكل test method — تكرار التشغيل بأكواد ثابتة هيصطدم
بقيد uniqueness الحقيقي، مش باج."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.hist_hr import generate as generate_hr
from tests.conftest import TestingSessionLocal


def _seed_accounts(db: Session, branch_id: int) -> None:
    from app.modules.finance.models import Account
    for code, name, acc_type in [
        ("5100", "Payroll Expense", "expense"),
        ("2100", "Tax Payable", "liability"),
        ("2110", "SI Payable", "liability"),
        ("2120", "Net Salaries Payable", "liability"),
        ("1180", "Employee Advances Receivable", "asset"),
    ]:
        db.add(Account(branch_id=branch_id, code=code, name=name, account_type=acc_type))
    db.commit()


class _Ctx:
    def __init__(self, branch_id: int):
        self.branch_id = branch_id
        self.period_year = 2026
        self.period_month = 7
        self.tz_name = "Africa/Cairo"
        self.actor_id = 1
        self.period_end_day = None


@pytest.fixture(scope="class")
def branch_id(setup_db) -> int:
    from app.modules.core.models import Branch

    db = TestingSessionLocal()
    try:
        b = Branch(name="Test HR HIST", name_ar="اختبار موارد بشرية تاريخية",
                   code=f"HH-{uuid.uuid4().hex[:6].upper()}")
        db.add(b)
        db.commit()
        _seed_accounts(db, b.id)
        generate_hr(db, _Ctx(b.id))
        db.commit()
        return b.id
    finally:
        db.close()


class TestHistHrGenerator:
    def test_creates_fourteen_employees_matching_brief_total(self, db: Session, branch_id: int):
        from app.modules.hr.models import Employee

        employees = db.query(Employee).filter(Employee.branch_id == branch_id).all()
        assert len(employees) == 14
        assert sum(e.basic_salary for e in employees) == Decimal("181000.00")
        assert all(e.status == "active" for e in employees)

    def test_full_july_attendance_created_for_every_employee(self, db: Session, branch_id: int):
        from app.modules.hr.models import AttendanceRecord, Employee

        employees = db.query(Employee).filter(Employee.branch_id == branch_id).all()
        for emp in employees:
            count = (
                db.query(AttendanceRecord)
                .filter(AttendanceRecord.employee_id == emp.id)
                .count()
            )
            assert count == 31, f"{emp.employee_code} expected 31 attendance records, got {count}"

    def test_payroll_run_created_and_approved(self, db: Session, branch_id: int):
        from app.modules.hr.models import PayrollRun

        run = (
            db.query(PayrollRun)
            .filter(PayrollRun.branch_id == branch_id, PayrollRun.period_year == 2026,
                    PayrollRun.period_month == 7)
            .first()
        )
        assert run is not None
        assert run.status == "approved"
        assert run.total_gross > Decimal("0")
        assert run.total_net > Decimal("0")

    def test_unpaid_leave_actually_reduces_the_correct_employee_net(self, db: Session, branch_id: int):
        """راجع الباج الحقيقي اللي اتصلح في نفس دفعة العمل: unpaid_leave_days
        كانت من قبل بترجع صفر دايمًا حتى مع إجازة معتمدة حقيقية. هنا بنتأكد
        إن CSH-01 (الموظف اللي أخد إجازة غير مدفوعة معتمدة يومين) فعليًا
        عنده unpaid_leave_deduction > 0 بعد تشغيل المولّد، مش رقم مفترض."""
        from app.modules.hr import crud as hr_crud
        from app.modules.hr.models import Employee, PayrollRun

        cashier1 = db.query(Employee).filter_by(branch_id=branch_id, employee_code="CSH-01").first()
        run = db.query(PayrollRun).filter_by(branch_id=branch_id, period_year=2026, period_month=7).first()
        lines = hr_crud.list_lines_for_run(db, run.id)
        line = next(l for l in lines if l.employee_id == cashier1.id)

        assert line.unpaid_leave_deduction == Decimal("733.33")  # 2 يوم × 11000/30

    def test_payroll_journal_entry_is_balanced(self, db: Session, branch_id: int):
        from app.modules.finance.models import JournalEntry, JournalLine
        from app.modules.hr.models import PayrollRun

        run = db.query(PayrollRun).filter_by(branch_id=branch_id, period_year=2026, period_month=7).first()
        entry = (
            db.query(JournalEntry)
            .filter(JournalEntry.source == "payroll", JournalEntry.source_id == run.id)
            .first()
        )
        assert entry is not None
        lines = db.query(JournalLine).filter(JournalLine.entry_id == entry.id).all()
        assert sum(l.debit for l in lines) == sum(l.credit for l in lines)
        assert sum(l.debit for l in lines) > Decimal("0")


def test_rejects_when_required_accounts_missing(db: Session):
    from app.modules.core.models import Branch

    b = Branch(name="Test HR HIST No Accounts", name_ar="اختبار بدون حسابات",
               code=f"HH-{uuid.uuid4().hex[:6].upper()}")
    db.add(b)
    db.commit()

    with pytest.raises(Exception):
        generate_hr(db, _Ctx(b.id))
        db.commit()
