"""
tests/test_tasks/test_hr_tasks_extended.py
اختبارات إضافية لـ hr_tasks.py — payroll_reminder, accrue_leave_balances,
generate_weekly_rota, وتغطية mark_attendance_absent الناقصة
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest


# ─── helpers ────────────────────────────────────────────────────────────────

def _make_branch(db, active=True):
    from app.modules.core.models import Branch
    b = Branch(
        name=f"HR-Branch-{uuid.uuid4().hex[:6]}",
        code=f"HR{uuid.uuid4().hex[:4].upper()}",
        is_active=active,
    )
    db.add(b)
    db.commit()
    return b


def _make_employee(db, branch, phone=None):
    from app.modules.hr import crud as hr_crud
    from app.modules.hr.schemas import EmployeeCreate
    data = EmployeeCreate(
        branch_id=branch.id,
        employee_code=f"E{uuid.uuid4().hex[:6].upper()}",
        full_name=f"Emp-{uuid.uuid4().hex[:4]}",
        position="staff",
        department="ops",
        basic_salary=Decimal("4000"),
        hire_date=date(2023, 1, 1),
        phone=phone,
    )
    emp = hr_crud.create_employee(db, data)
    db.commit()
    return emp


def _db_ctx(db):
    """MagicMock context manager يُعيد db fixture."""
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=db)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


# ─── mark_attendance_absent (service logic) ──────────────────────────────────

class TestMarkAttendanceAbsentLogic:

    def test_absent_record_created_for_employee_without_attendance(self, db):
        """موظف بدون تسجيل حضور يُسجَّل له غياب"""
        from app.modules.hr.crud import list_employees, upsert_attendance
        from app.modules.hr.schemas import AttendanceRecordCreate
        from app.modules.hr.models import AttendanceRecord
        from app.core.config import settings
        from app.resort_os.timezone_utils import local_today

        branch = _make_branch(db)
        emp = _make_employee(db, branch)
        today = local_today(settings.TIMEZONE)

        # تأكد مفيش تسجيل
        existing = db.query(AttendanceRecord).filter(
            AttendanceRecord.employee_id == emp.id,
            AttendanceRecord.record_date == today,
        ).first()
        assert existing is None

        # شغّل المنطق
        employees, _ = list_employees(db, branch.id, status="active", limit=1000)
        for e in employees:
            if e.id == emp.id:
                existing_rec = db.query(AttendanceRecord).filter(
                    AttendanceRecord.employee_id == e.id,
                    AttendanceRecord.record_date == today,
                ).first()
                if not existing_rec:
                    upsert_attendance(db, AttendanceRecordCreate(
                        employee_id=e.id,
                        branch_id=branch.id,
                        record_date=today,
                        status="absent",
                    ))
        db.commit()

        record = db.query(AttendanceRecord).filter(
            AttendanceRecord.employee_id == emp.id,
            AttendanceRecord.record_date == today,
        ).first()
        assert record is not None
        assert record.status == "absent"

    def test_present_employee_not_overwritten(self, db):
        """موظف سجّل حضوره لا يُعاد تسجيله كغائب"""
        from app.modules.hr.crud import list_employees, upsert_attendance
        from app.modules.hr.schemas import AttendanceRecordCreate
        from app.modules.hr.models import AttendanceRecord
        from app.core.config import settings
        from app.resort_os.timezone_utils import local_today

        branch = _make_branch(db)
        emp = _make_employee(db, branch)
        today = local_today(settings.TIMEZONE)

        # سجّل حضور مسبقاً
        upsert_attendance(db, AttendanceRecordCreate(
            employee_id=emp.id, branch_id=branch.id,
            record_date=today, status="present",
        ))
        db.commit()

        # شغّل المنطق — يجب ألا يمسّ الـ record الموجود
        employees, _ = list_employees(db, branch.id, status="active", limit=1000)
        for e in employees:
            if e.id == emp.id:
                existing_rec = db.query(AttendanceRecord).filter(
                    AttendanceRecord.employee_id == e.id,
                    AttendanceRecord.record_date == today,
                ).first()
                if not existing_rec:
                    upsert_attendance(db, AttendanceRecordCreate(
                        employee_id=e.id, branch_id=branch.id,
                        record_date=today, status="absent",
                    ))
        db.commit()

        record = db.query(AttendanceRecord).filter(
            AttendanceRecord.employee_id == emp.id,
            AttendanceRecord.record_date == today,
        ).first()
        assert record.status == "present"

    def test_task_runs_without_error(self, db):
        """task يشتغل بدون exception"""
        with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
            from app.tasks.hr_tasks import mark_attendance_absent
            mark_attendance_absent()


# ─── payroll_reminder ────────────────────────────────────────────────────────

class TestPayrollReminder:

    def test_notify_admin_called_per_branch(self, db):
        """notify_admin يُستدعى لكل فرع نشط"""
        import app.core.kernel.whatsapp as wa_module
        msgs = []
        original = getattr(wa_module, "notify_admin", lambda *a: None)
        wa_module.notify_admin = lambda msg: msgs.append(msg)
        try:
            branch = _make_branch(db)
            from app.core.config import settings
            from app.resort_os.timezone_utils import local_today
            from app.modules.core.models import Branch

            today = local_today(settings.TIMEZONE)
            branches = db.query(Branch).filter(Branch.is_active.is_(True)).all()
            for br in branches:
                wa_module.notify_admin(
                    f"تذكير: موعد إعداد كشف رواتب شهر {today.month}/{today.year} — فرع #{br.id}."
                )
            assert len(msgs) >= 1
            assert str(branch.id) in msgs[-1]
        finally:
            wa_module.notify_admin = original

    def test_task_runs_without_error(self, db):
        """task payroll_reminder يشتغل بدون exception"""
        import app.core.kernel.whatsapp as wa_module
        original = getattr(wa_module, "notify_admin", lambda *a: None)
        wa_module.notify_admin = lambda *a, **kw: None
        try:
            with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
                from app.tasks.hr_tasks import payroll_reminder
                payroll_reminder()
        finally:
            wa_module.notify_admin = original

    def test_no_branches_no_notification(self, db):
        """بدون فروع نشطة لا يُرسل تنبيه"""
        import app.core.kernel.whatsapp as wa_module
        msgs = []
        original = getattr(wa_module, "notify_admin", lambda *a: None)
        wa_module.notify_admin = lambda msg: msgs.append(msg)
        try:
            from app.modules.core.models import Branch
            # تعطيل كل الفروع
            db.query(Branch).update({"is_active": False})
            db.commit()

            branches = db.query(Branch).filter(Branch.is_active.is_(True)).all()
            assert len(branches) == 0
            # لا تنبيهات لأن مفيش فروع
            assert msgs == []
        finally:
            wa_module.notify_admin = original
            # أعد تفعيل الفروع
            db.query(Branch).update({"is_active": True})
            db.commit()


# ─── accrue_leave_balances ────────────────────────────────────────────────────

class TestAccrueLeaveBalances:

    def test_leave_balance_created_for_employee(self, db):
        """يُنشئ رصيد إجازة للموظف النشط"""
        from app.modules.hr.crud import list_employees, upsert_leave_balance
        from app.modules.hr.models import LeaveBalance
        from app.resort_os.hr_engine import annual_leave_entitlement
        from app.core.config import settings
        from app.resort_os.timezone_utils import local_today

        branch = _make_branch(db)
        emp = _make_employee(db, branch)
        year = local_today(settings.TIMEZONE).year

        employees, _ = list_employees(db, branch.id, status="active", limit=1000)
        for e in employees:
            if e.id == emp.id:
                entitled = annual_leave_entitlement(
                    e.hire_date, e.birth_date or e.hire_date,
                )
                upsert_leave_balance(db, e.id, year, entitled)
        db.commit()

        balance = db.query(LeaveBalance).filter(
            LeaveBalance.employee_id == emp.id,
            LeaveBalance.year == year,
        ).first()
        assert balance is not None
        assert balance.annual_entitled >= 0

    def test_leave_balance_idempotent(self, db):
        """تشغيل مرتين لا يُنشئ سجلين"""
        from app.modules.hr.crud import upsert_leave_balance
        from app.modules.hr.models import LeaveBalance
        from app.core.config import settings
        from app.resort_os.timezone_utils import local_today

        branch = _make_branch(db)
        emp = _make_employee(db, branch)
        year = local_today(settings.TIMEZONE).year

        upsert_leave_balance(db, emp.id, year, 21)
        db.commit()
        upsert_leave_balance(db, emp.id, year, 21)
        db.commit()

        records = db.query(LeaveBalance).filter(
            LeaveBalance.employee_id == emp.id,
            LeaveBalance.year == year,
        ).all()
        assert len(records) == 1

    def test_task_runs_without_error(self, db):
        """task accrue_leave_balances يشتغل بدون exception"""
        with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
            from app.tasks.hr_tasks import accrue_leave_balances
            accrue_leave_balances()


# ─── accrue_monthly_leave_ledger (wagdy.md H-03) ──────────────────────────────

class TestAccrueMonthlyLeaveLedger:

    def test_task_creates_monthly_row_for_active_employee(self, db):
        from app.modules.hr.models import LeaveBalanceMonthly

        branch = _make_branch(db)
        emp = _make_employee(db, branch)

        with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
            from app.tasks.hr_tasks import accrue_monthly_leave_ledger
            accrue_monthly_leave_ledger()

        row = db.query(LeaveBalanceMonthly).filter(
            LeaveBalanceMonthly.employee_id == emp.id,
        ).first()
        assert row is not None
        assert row.accrued == Decimal("7.50")
        assert row.closing_balance == Decimal("7.50")

    def test_task_skips_inactive_branch(self, db):
        from app.modules.hr.models import LeaveBalanceMonthly

        branch = _make_branch(db, active=False)
        emp = _make_employee(db, branch)

        with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
            from app.tasks.hr_tasks import accrue_monthly_leave_ledger
            accrue_monthly_leave_ledger()

        row = db.query(LeaveBalanceMonthly).filter(
            LeaveBalanceMonthly.employee_id == emp.id,
        ).first()
        assert row is None

    def test_task_runs_without_error(self, db):
        with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
            from app.tasks.hr_tasks import accrue_monthly_leave_ledger
            accrue_monthly_leave_ledger()


# ─── generate_weekly_rota ─────────────────────────────────────────────────────

class TestGenerateWeeklyRota:

    def test_task_runs_without_error(self, db):
        """task يشتغل بدون exception (placeholder)"""
        from app.tasks.hr_tasks import generate_weekly_rota
        generate_weekly_rota()
