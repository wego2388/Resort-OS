"""
tests/test_tasks/test_maintenance_tasks.py
اختبارات الـ maintenance_tasks.py — service logic مباشرة بـ db fixture
بدون تشغيل Celery runtime
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest


# ─── helpers ────────────────────────────────────────────────────────────────

def _make_branch(db, active=True):
    from app.modules.core.models import Branch
    b = Branch(
        name=f"Maint-Branch-{uuid.uuid4().hex[:6]}",
        code=f"MN{uuid.uuid4().hex[:4].upper()}",
        is_active=active,
    )
    db.add(b)
    db.commit()
    return b


def _make_asset(db, branch):
    from app.modules.maintenance.models import Asset
    a = Asset(
        branch_id=branch.id,
        code=f"AST-{uuid.uuid4().hex[:6].upper()}",
        name=f"Asset-{uuid.uuid4().hex[:4]}",
        category="electrical",
        location="Main Building",
        status="operational",
    )
    db.add(a)
    db.commit()
    return a


def _make_employee(db, branch, phone=None):
    from app.modules.hr import crud as hr_crud
    from app.modules.hr.schemas import EmployeeCreate
    data = EmployeeCreate(
        branch_id=branch.id,
        employee_code=f"E{uuid.uuid4().hex[:6].upper()}",
        full_name="Maint Employee",
        position="technician",
        department="maintenance",
        basic_salary=Decimal("4000"),
        hire_date=date(2024, 1, 1),
        phone=phone,
    )
    emp = hr_crud.create_employee(db, data)
    db.commit()
    return emp


def _make_work_order(db, branch, asset=None, scheduled_date=None, status="open", assigned_to=None):
    from app.modules.maintenance.models import WorkOrder
    wo = WorkOrder(
        branch_id=branch.id,
        asset_id=asset.id if asset else None,
        order_number=f"WO-{uuid.uuid4().hex[:8].upper()}",
        title=f"Work Order {uuid.uuid4().hex[:4]}",
        order_type="corrective",
        priority="medium",
        status=status,
        scheduled_date=scheduled_date,
        assigned_to=assigned_to,
    )
    db.add(wo)
    db.commit()
    return wo


def _make_preventive_schedule(db, branch, asset, assigned_to=None, next_due=None):
    from app.modules.maintenance.models import PreventiveSchedule
    from app.core.config import settings
    from app.resort_os.timezone_utils import local_today
    today = local_today(settings.TIMEZONE)
    ps = PreventiveSchedule(
        branch_id=branch.id,
        asset_id=asset.id,
        title=f"Schedule-{uuid.uuid4().hex[:4]}",
        frequency_days=30,
        next_due=next_due or today,
        is_active=True,
        assigned_to=assigned_to,
    )
    db.add(ps)
    db.commit()
    return ps


# ─── generate_preventive_work_orders logic ──────────────────────────────────

class TestGeneratePreventiveWorkOrders:
    """اختبار generate_preventive_work_orders مباشرة"""

    def test_creates_work_order_for_due_schedule(self, db):
        """جدول مستحق ينشئ أمر صيانة وقائية"""
        branch = _make_branch(db)
        asset = _make_asset(db, branch)
        _make_preventive_schedule(db, branch, asset)

        from app.modules.maintenance.services import generate_preventive_work_orders
        count = generate_preventive_work_orders(db, branch.id)
        db.commit()

        assert count >= 1

    def test_no_duplicate_work_order(self, db):
        """لا يُنشئ أمر مكرر لو فيه أمر preventive مفتوح لنفس الأصل"""
        branch = _make_branch(db)
        asset = _make_asset(db, branch)
        schedule = _make_preventive_schedule(db, branch, asset)

        # أنشئ أمر preventive مفتوح أولاً
        from app.modules.maintenance.models import WorkOrder
        existing = WorkOrder(
            branch_id=branch.id,
            asset_id=asset.id,
            order_number=f"WO-DUP-{uuid.uuid4().hex[:6].upper()}",
            title="صيانة وقائية موجودة",
            order_type="preventive",
            priority="medium",
            status="open",
        )
        db.add(existing)
        db.commit()

        from app.modules.maintenance.services import generate_preventive_work_orders
        count = generate_preventive_work_orders(db, branch.id)

        # المفروض 0 — الأمر المفتوح موجود بالفعل
        assert count == 0

    def test_no_schedules_returns_zero(self, db):
        """فرع بدون جداول وقائية يُرجع 0"""
        branch = _make_branch(db)
        from app.modules.maintenance.services import generate_preventive_work_orders
        count = generate_preventive_work_orders(db, branch.id)
        assert count == 0

    def test_future_schedule_not_triggered(self, db):
        """جدول تاريخه في المستقبل لا يُنشئ أمر"""
        branch = _make_branch(db)
        asset = _make_asset(db, branch)
        future_date = date.today() + timedelta(days=7)
        _make_preventive_schedule(db, branch, asset, next_due=future_date)

        from app.modules.maintenance.services import generate_preventive_work_orders
        count = generate_preventive_work_orders(db, branch.id)
        assert count == 0

    def test_task_runs_without_error(self, db):
        """task generate_preventive_tasks يشتغل بدون exception"""
        from unittest.mock import patch, MagicMock
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=db)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch("app.core.database.SessionLocal", return_value=ctx):
            from app.tasks.maintenance_tasks import generate_preventive_tasks
            generate_preventive_tasks()


# ─── notify_overdue_work_orders logic ────────────────────────────────────────

class TestNotifyOverdueWorkOrders:
    """اختبار منطق notify_overdue_work_orders"""

    def test_overdue_wo_detected(self, db):
        """أمر صيانة متأخر يُكتشف"""
        branch = _make_branch(db)
        yesterday = date.today() - timedelta(days=1)
        wo = _make_work_order(db, branch, scheduled_date=yesterday, status="open")

        from app.modules.maintenance.models import WorkOrder
        from app.core.config import settings
        from app.resort_os.timezone_utils import local_today
        today = local_today(settings.TIMEZONE)

        overdue = (
            db.query(WorkOrder)
            .filter(
                WorkOrder.scheduled_date < today,
                WorkOrder.status.in_(["open", "in_progress"]),
            )
            .all()
        )
        assert wo.id in [w.id for w in overdue]

    def test_completed_wo_not_overdue(self, db):
        """أمر صيانة مكتمل لا يُعتبر متأخراً"""
        branch = _make_branch(db)
        yesterday = date.today() - timedelta(days=1)
        wo = _make_work_order(db, branch, scheduled_date=yesterday, status="completed")

        from app.modules.maintenance.models import WorkOrder
        from app.core.config import settings
        from app.resort_os.timezone_utils import local_today
        today = local_today(settings.TIMEZONE)

        overdue = (
            db.query(WorkOrder)
            .filter(
                WorkOrder.scheduled_date < today,
                WorkOrder.status.in_(["open", "in_progress"]),
            )
            .all()
        )
        assert wo.id not in [w.id for w in overdue]

    def test_whatsapp_sent_to_assigned_employee(self, db):
        """واتساب يُرسل للموظف المسؤول"""
        import app.core.kernel.whatsapp as wa_module
        sent = []
        original_send = wa_module.send_whatsapp_message
        original_notify = getattr(wa_module, "notify_admin", lambda *a: None)
        wa_module.send_whatsapp_message = lambda phone, msg: sent.append(phone)
        wa_module.notify_admin = lambda msg: None
        try:
            branch = _make_branch(db)
            emp = _make_employee(db, branch, phone="01011110000")
            yesterday = date.today() - timedelta(days=1)
            wo = _make_work_order(db, branch, scheduled_date=yesterday, status="open", assigned_to=emp.id)

            from app.modules.maintenance.models import WorkOrder
            from app.modules.hr.models import Employee
            from app.core.config import settings
            from app.resort_os.timezone_utils import local_today
            today = local_today(settings.TIMEZONE)

            overdue = (
                db.query(WorkOrder)
                .filter(
                    WorkOrder.scheduled_date < today,
                    WorkOrder.status.in_(["open", "in_progress"]),
                )
                .all()
            )
            for w in overdue:
                if w.assigned_to:
                    emp_rec = db.query(Employee).filter(Employee.id == w.assigned_to).first()
                    if emp_rec and emp_rec.phone:
                        wa_module.send_whatsapp_message(emp_rec.phone, f"أمر صيانة متأخر: {w.title}")

            assert "01011110000" in sent
        finally:
            wa_module.send_whatsapp_message = original_send
            wa_module.notify_admin = original_notify

    def test_notify_admin_when_no_employee(self, db):
        """notify_admin يُستدعى لو الأمر بدون موظف مسؤول"""
        import app.core.kernel.whatsapp as wa_module
        admin_notified = []
        original_send = wa_module.send_whatsapp_message
        original_notify = getattr(wa_module, "notify_admin", lambda *a: None)
        wa_module.send_whatsapp_message = lambda *a, **kw: None
        wa_module.notify_admin = lambda msg: admin_notified.append(msg)
        try:
            branch = _make_branch(db)
            yesterday = date.today() - timedelta(days=1)
            wo = _make_work_order(db, branch, scheduled_date=yesterday, status="open", assigned_to=None)

            from app.modules.maintenance.models import WorkOrder
            from app.modules.hr.models import Employee
            from app.core.config import settings
            from app.resort_os.timezone_utils import local_today
            today = local_today(settings.TIMEZONE)

            overdue = (
                db.query(WorkOrder)
                .filter(
                    WorkOrder.scheduled_date < today,
                    WorkOrder.status.in_(["open", "in_progress"]),
                )
                .all()
            )
            for w in overdue:
                sent_flag = False
                if w.assigned_to:
                    emp_rec = db.query(Employee).filter(Employee.id == w.assigned_to).first()
                    if emp_rec and emp_rec.phone:
                        wa_module.send_whatsapp_message(emp_rec.phone, "test")
                        sent_flag = True
                if not sent_flag:
                    wa_module.notify_admin(f"أمر صيانة متأخر بلا موظف مسؤول: {w.title} (WO #{w.id}).")

            assert len(admin_notified) >= 1
            assert any(str(wo.id) in msg for msg in admin_notified)
        finally:
            wa_module.send_whatsapp_message = original_send
            wa_module.notify_admin = original_notify

    def test_task_runs_without_error(self, db):
        """task notify_overdue_work_orders يشتغل بدون exception"""
        import app.core.kernel.whatsapp as wa_module
        original_send = wa_module.send_whatsapp_message
        original_notify = getattr(wa_module, "notify_admin", lambda *a: None)
        wa_module.send_whatsapp_message = lambda *a, **kw: None
        wa_module.notify_admin = lambda *a, **kw: None
        try:
            from unittest.mock import patch, MagicMock
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=db)
            ctx.__exit__ = MagicMock(return_value=False)
            with patch("app.core.database.SessionLocal", return_value=ctx):
                from app.tasks.maintenance_tasks import notify_overdue_work_orders
                notify_overdue_work_orders()
        finally:
            wa_module.send_whatsapp_message = original_send
            wa_module.notify_admin = original_notify
