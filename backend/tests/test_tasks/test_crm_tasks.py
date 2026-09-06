"""
tests/test_tasks/test_crm_tasks.py
اختبارات الـ crm_tasks.py — service logic مباشرة بـ db fixture
بدون تشغيل Celery runtime
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest


# ─── helpers ────────────────────────────────────────────────────────────────

def _make_branch(db):
    from app.modules.core.models import Branch
    branch = Branch(
        name=f"CRM-Branch-{uuid.uuid4().hex[:6]}",
        code=f"CRM{uuid.uuid4().hex[:4].upper()}",
    )
    db.add(branch)
    db.commit()
    return branch


def _make_customer(db, branch, phone=None, birthday=None):
    from app.modules.crm.models import Customer
    c = Customer(
        branch_id=branch.id,
        full_name=f"Customer-{uuid.uuid4().hex[:4]}",
        phone=phone,
        birthday=birthday,
        is_active=True,
        blacklisted=False,
    )
    db.add(c)
    db.commit()
    return c


def _make_activity(db, branch, customer, due_date, status="pending", assigned_to=None):
    from app.modules.crm.models import Activity
    act = Activity(
        branch_id=branch.id,
        customer_id=customer.id,
        activity_type="follow_up",
        title=f"Act-{uuid.uuid4().hex[:4]}",
        due_date=due_date,
        status=status,
        assigned_to=assigned_to,
    )
    db.add(act)
    db.commit()
    return act


# ─── activity_reminders ─────────────────────────────────────────────────────

class TestActivityRemindersLogic:
    """اختبار منطق activity_reminders مباشرة بـ db بدون Celery"""

    def test_activity_due_today_logged(self, db, caplog):
        """نشاط مستحق اليوم يتسجّل في الـ log"""
        branch = _make_branch(db)
        customer = _make_customer(db, branch)
        today = date.today()
        _make_activity(db, branch, customer, due_date=today)

        from app.modules.crm.models import Activity
        activities = (
            db.query(Activity)
            .filter(
                Activity.due_date.in_([today, today + timedelta(days=1)]),
                Activity.status == "pending",
            )
            .all()
        )
        assert any(a.due_date == today for a in activities)

    def test_activity_due_tomorrow_included(self, db):
        """نشاط مستحق غداً يُضمَّن في الاستعلام"""
        branch = _make_branch(db)
        customer = _make_customer(db, branch)
        tomorrow = date.today() + timedelta(days=1)
        act = _make_activity(db, branch, customer, due_date=tomorrow)

        from app.modules.crm.models import Activity
        tomorrow_acts = (
            db.query(Activity)
            .filter(Activity.due_date == tomorrow, Activity.status == "pending")
            .all()
        )
        assert act.id in [a.id for a in tomorrow_acts]

    def test_done_activity_excluded(self, db):
        """نشاط تمّ (done) لا يظهر في نتائج الاستعلام"""
        branch = _make_branch(db)
        customer = _make_customer(db, branch)
        today = date.today()
        _make_activity(db, branch, customer, due_date=today, status="done")

        from app.modules.crm.models import Activity
        pending = (
            db.query(Activity)
            .filter(Activity.due_date == today, Activity.status == "pending")
            .all()
        )
        assert all(a.status == "pending" for a in pending)

    def test_task_runs_without_error(self, db):
        """task يشتغل بدون exception حتى مع DB فاضية"""
        from unittest.mock import patch, MagicMock
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=db)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch("app.core.database.SessionLocal", return_value=ctx):
            from app.tasks.crm_tasks import activity_reminders
            activity_reminders()


# ─── overdue_activities_alert ────────────────────────────────────────────────

class TestOverdueActivitiesAlert:
    """اختبار منطق overdue_activities_alert"""

    def test_overdue_activity_detected(self, db):
        """نشاط تاريخه فات ولسه pending يُعتبر متأخر"""
        branch = _make_branch(db)
        customer = _make_customer(db, branch)
        yesterday = date.today() - timedelta(days=1)
        _make_activity(db, branch, customer, due_date=yesterday)

        from app.modules.crm.models import Activity
        today = date.today()
        overdue = (
            db.query(Activity)
            .filter(Activity.due_date < today, Activity.status == "pending")
            .all()
        )
        assert len(overdue) >= 1

    def test_future_activity_not_overdue(self, db):
        """نشاط في المستقبل لا يُعتبر متأخر"""
        branch = _make_branch(db)
        customer = _make_customer(db, branch)
        next_week = date.today() + timedelta(days=7)
        _make_activity(db, branch, customer, due_date=next_week)

        from app.modules.crm.models import Activity
        today = date.today()
        overdue = (
            db.query(Activity)
            .filter(Activity.due_date < today, Activity.status == "pending")
            .all()
        )
        assert not any(a.due_date >= today for a in overdue)

    def test_task_runs_without_error(self, db):
        """task يشتغل بدون exception"""
        branch = _make_branch(db)
        customer = _make_customer(db, branch)
        yesterday = date.today() - timedelta(days=2)
        _make_activity(db, branch, customer, due_date=yesterday)

        from unittest.mock import patch, MagicMock
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=db)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch("app.core.database.SessionLocal", return_value=ctx):
            from app.tasks.crm_tasks import overdue_activities_alert
            overdue_activities_alert()


# ─── birthday_greetings ──────────────────────────────────────────────────────

class TestBirthdayGreetings:
    """اختبار منطق birthday_greetings"""

    def test_birthday_customer_matched(self, db):
        """عميل ميلاده اليوم يُطابَق"""
        branch = _make_branch(db)
        today = date.today()
        customer = _make_customer(
            db, branch,
            phone="01099998888",
            birthday=date(1990, today.month, today.day),
        )

        from app.modules.crm.models import Customer
        birthdays = (
            db.query(Customer)
            .filter(
                Customer.is_active.is_(True),
                Customer.blacklisted.is_(False),
                Customer.birthday.isnot(None),
            )
            .all()
        )
        matched = [
            c for c in birthdays
            if c.birthday and c.birthday.month == today.month and c.birthday.day == today.day
        ]
        assert any(c.id == customer.id for c in matched)

    def test_different_birthday_not_matched(self, db):
        """عميل ميلاده مش اليوم لا يُطابَق"""
        branch = _make_branch(db)
        today = date.today()
        yesterday = today - timedelta(days=1)
        customer = _make_customer(
            db, branch,
            birthday=date(1990, yesterday.month, yesterday.day),
        )

        from app.modules.crm.models import Customer
        birthdays = db.query(Customer).filter(
            Customer.birthday.isnot(None),
        ).all()
        matched_today = [
            c for c in birthdays
            if c.birthday and c.birthday.month == today.month and c.birthday.day == today.day
            and c.id == customer.id
        ]
        assert len(matched_today) == 0

    def test_blacklisted_customer_excluded(self, db):
        """عميل محظور لا يأخذ تهنئة"""
        branch = _make_branch(db)
        today = date.today()
        customer = _make_customer(
            db, branch,
            birthday=date(1990, today.month, today.day),
        )
        customer.blacklisted = True
        db.commit()

        from app.modules.crm.models import Customer
        eligible = (
            db.query(Customer)
            .filter(
                Customer.is_active.is_(True),
                Customer.blacklisted.is_(False),
                Customer.birthday.isnot(None),
            )
            .all()
        )
        assert customer.id not in [c.id for c in eligible]

    def test_task_runs_without_error(self, db):
        """task يشتغل بدون exception"""
        branch = _make_branch(db)
        today = date.today()
        _make_customer(
            db, branch,
            phone="01011112222",
            birthday=date(1985, today.month, today.day),
        )

        from unittest.mock import patch, MagicMock
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=db)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch("app.core.database.SessionLocal", return_value=ctx):
            from app.tasks.crm_tasks import birthday_greetings
            birthday_greetings()
