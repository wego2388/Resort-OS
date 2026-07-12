"""app/tasks/hr_tasks.py — Payroll reminders + Attendance + Leave accrual"""
from __future__ import annotations

import logging

from app.celery_app import celery_app
from app.core.config import settings
from app.core.kernel.worker import notify_task_failure
from app.resort_os.timezone_utils import local_today

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.hr_tasks.mark_attendance_absent", bind=True)
def mark_attendance_absent(self):
    """
    آخر اليوم 23:59 — يُسجّل غياب لكل موظف لم يُسجَّل له حضور.
    """
    try:
        from app.core.database import SessionLocal         # noqa: PLC0415
        from app.modules.core.models import Branch         # noqa: PLC0415
        from app.modules.hr.crud import (                  # noqa: PLC0415
            list_employees, upsert_attendance,
        )
        from app.modules.hr.schemas import AttendanceRecordCreate  # noqa: PLC0415
        from app.modules.hr.models import AttendanceRecord         # noqa: PLC0415

        today = local_today(settings.TIMEZONE)
        with SessionLocal() as db:
            branches = db.query(Branch).filter(Branch.is_active.is_(True)).all()
            for branch in branches:
                employees, _ = list_employees(db, branch.id, status="active", limit=1000)
                for emp in employees:
                    # تحقق إن كان له تسجيل اليوم
                    existing = (
                        db.query(AttendanceRecord)
                        .filter(
                            AttendanceRecord.employee_id == emp.id,
                            AttendanceRecord.record_date == today,
                        )
                        .first()
                    )
                    if not existing:
                        upsert_attendance(db, AttendanceRecordCreate(
                            employee_id=emp.id,
                            branch_id=branch.id,
                            record_date=today,
                            status="absent",
                        ))
            db.commit()
            logger.info("Attendance absent marked for date=%s", today)

    except Exception as exc:
        logger.error("mark_attendance_absent failed: %s", exc)
        notify_task_failure("app.tasks.hr_tasks.mark_attendance_absent", exc)


@celery_app.task(name="app.tasks.hr_tasks.payroll_reminder", bind=True)
def payroll_reminder(self):
    """
    تذكير إعداد كشف الرواتب — أيام 28-31 من كل شهر.
    """
    try:
        from app.core.database import SessionLocal          # noqa: PLC0415
        from app.modules.core.models import Branch          # noqa: PLC0415

        today = local_today(settings.TIMEZONE)
        with SessionLocal() as db:
            branches = db.query(Branch).filter(Branch.is_active.is_(True)).all()
            from app.core.kernel.whatsapp import notify_admin  # noqa: PLC0415
            for branch in branches:
                logger.info(
                    "Payroll reminder: branch=%s month=%s/%s",
                    branch.id, today.month, today.year,
                )
                notify_admin(f"تذكير: موعد إعداد كشف رواتب شهر {today.month}/{today.year} — فرع #{branch.id}.")
    except Exception as exc:
        logger.error("payroll_reminder failed: %s", exc)
        notify_task_failure("app.tasks.hr_tasks.payroll_reminder", exc)


@celery_app.task(name="app.tasks.hr_tasks.accrue_leave_balances", bind=True)
def accrue_leave_balances(self):
    """
    أول يناير — يُنشئ/يُحدّث أرصدة الإجازة للموظفين النشطين.
    """
    try:
        from app.core.database import SessionLocal          # noqa: PLC0415
        from app.modules.core.models import Branch          # noqa: PLC0415
        from app.modules.hr.crud import (                   # noqa: PLC0415
            list_employees, upsert_leave_balance,
        )
        from app.resort_os.hr_engine import annual_leave_entitlement  # noqa: PLC0415

        year = local_today(settings.TIMEZONE).year
        with SessionLocal() as db:
            branches = db.query(Branch).filter(Branch.is_active.is_(True)).all()
            total = 0
            for branch in branches:
                employees, _ = list_employees(db, branch.id, status="active", limit=1000)
                for emp in employees:
                    entitled = annual_leave_entitlement(
                        emp.hire_date,
                        emp.birth_date or emp.hire_date,
                    )
                    upsert_leave_balance(db, emp.id, year, entitled)
                    total += 1
            db.commit()
            logger.info("Leave balances accrued: year=%s employees=%s", year, total)

    except Exception as exc:
        logger.error("accrue_leave_balances failed: %s", exc)
        notify_task_failure("app.tasks.hr_tasks.accrue_leave_balances", exc)


@celery_app.task(name="app.tasks.hr_tasks.generate_weekly_rota", bind=True)
def generate_weekly_rota(self):
    """
    الجمعة كل أسبوع — placeholder للجدول الأسبوعي.
    """
    logger.info("Weekly rota generation triggered — not yet implemented")
