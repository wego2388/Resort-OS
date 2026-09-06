"""
tests/test_tasks/test_maintenance_tasks.py
اختبارات الـ maintenance_tasks.py — service logic مباشرة بـ db fixture
بدون تشغيل Celery runtime
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

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

    def test_task_runs_without_error(self, db):
        """task notify_overdue_work_orders يشتغل بدون exception"""
        from unittest.mock import patch, MagicMock
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=db)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch("app.core.database.SessionLocal", return_value=ctx):
            from app.tasks.maintenance_tasks import notify_overdue_work_orders
            notify_overdue_work_orders()
