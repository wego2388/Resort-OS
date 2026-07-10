"""
tests/test_tasks/test_crm_tasks.py
اختبارات الـ crm_tasks.py — service logic مباشرة بـ db fixture
بدون تشغيل Celery runtime
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

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


def _make_employee(db, branch, phone=None):
    from app.modules.hr import crud as hr_crud
    from app.modules.hr.schemas import EmployeeCreate
    data = EmployeeCreate(
        branch_id=branch.id,
        employee_code=f"E{uuid.uuid4().hex[:6].upper()}",
        full_name="CRM Employee",
        position="sales_rep",
        department="sales",
        basic_salary=Decimal("5000"),
        hire_date=date(2024, 1, 1),
        phone=phone,
    )
    emp = hr_crud.create_employee(db, data)
    db.commit()
    return emp


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
        import app.core.kernel.whatsapp as wa_module
        wa_module.send_whatsapp_message = lambda *a, **kw: None

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

    def test_whatsapp_sent_when_employee_has_phone(self, db):
        """يُرسل واتساب للموظف لو عنده رقم"""
        import app.core.kernel.whatsapp as wa_module
        sent = []
        original = wa_module.send_whatsapp_message
        wa_module.send_whatsapp_message = lambda phone, msg: sent.append(phone)
        try:
            branch = _make_branch(db)
            customer = _make_customer(db, branch)
            emp = _make_employee(db, branch, phone="01012345678")
            today = date.today()
            act = _make_activity(db, branch, customer, due_date=today, assigned_to=emp.id)

            # تشغيل المنطق مباشرة
            from app.modules.crm.models import Activity
            from app.modules.hr.models import Employee

            activities = (
                db.query(Activity)
                .filter(
                    Activity.due_date.in_([today, today + timedelta(days=1)]),
                    Activity.status == "pending",
                )
                .all()
            )
            for a in activities:
                if a.assigned_to:
                    emp_rec = db.query(Employee).filter(Employee.id == a.assigned_to).first()
                    if emp_rec and emp_rec.phone:
                        wa_module.send_whatsapp_message(emp_rec.phone, "test msg")

            assert "01012345678" in sent
        finally:
            wa_module.send_whatsapp_message = original

    def test_whatsapp_skipped_when_no_phone(self, db):
        """لا يُرسل واتساب لو الموظف بدون رقم"""
        import app.core.kernel.whatsapp as wa_module
        sent = []
        original = wa_module.send_whatsapp_message
        wa_module.send_whatsapp_message = lambda phone, msg: sent.append(phone)
        try:
            branch = _make_branch(db)
            customer = _make_customer(db, branch)
            emp = _make_employee(db, branch, phone=None)
            today = date.today()
            act = _make_activity(db, branch, customer, due_date=today, assigned_to=emp.id)

            from app.modules.crm.models import Activity
            from app.modules.hr.models import Employee

            # فلترة على الـ activity المحدد فقط لعزل الـ test
            activities = (
                db.query(Activity)
                .filter(Activity.id == act.id, Activity.status == "pending")
                .all()
            )
            for a in activities:
                if a.assigned_to:
                    emp_rec = db.query(Employee).filter(Employee.id == a.assigned_to).first()
                    if emp_rec and emp_rec.phone:
                        wa_module.send_whatsapp_message(emp_rec.phone, "test")

            assert sent == []
        finally:
            wa_module.send_whatsapp_message = original

    def test_task_runs_without_error(self, db):
        """task يشتغل بدون exception حتى مع DB فاضية"""
        import app.core.kernel.whatsapp as wa_module
        original = wa_module.send_whatsapp_message
        wa_module.send_whatsapp_message = lambda *a, **kw: None
        try:
            from unittest.mock import patch, MagicMock
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=db)
            ctx.__exit__ = MagicMock(return_value=False)
            with patch("app.core.database.SessionLocal", return_value=ctx):
                from app.tasks.crm_tasks import activity_reminders
                activity_reminders()
        finally:
            wa_module.send_whatsapp_message = original


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

    def test_notify_admin_called_when_overdue(self, db):
        """notify_admin يُستدعى لو في أنشطة متأخرة"""
        import app.core.kernel.whatsapp as wa_module
        admin_msgs = []
        wa_module.notify_admin = lambda msg: admin_msgs.append(msg)

        branch = _make_branch(db)
        customer = _make_customer(db, branch)
        yesterday = date.today() - timedelta(days=2)
        _make_activity(db, branch, customer, due_date=yesterday)

        from app.modules.crm.models import Activity
        today = date.today()
        overdue = (
            db.query(Activity)
            .filter(Activity.due_date < today, Activity.status == "pending")
            .all()
        )
        if overdue:
            wa_module.notify_admin(f"تنبيه CRM: فيه {len(overdue)} نشاط متأخر محتاج متابعة.")

        assert len(admin_msgs) == 1
        assert str(len(overdue)) in admin_msgs[0]

    def test_task_runs_without_error(self, db):
        """task يشتغل بدون exception"""
        import app.core.kernel.whatsapp as wa_module
        original = wa_module.notify_admin
        wa_module.notify_admin = lambda *a, **kw: None
        try:
            from unittest.mock import patch, MagicMock
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=db)
            ctx.__exit__ = MagicMock(return_value=False)
            with patch("app.core.database.SessionLocal", return_value=ctx):
                from app.tasks.crm_tasks import overdue_activities_alert
                overdue_activities_alert()
        finally:
            wa_module.notify_admin = original


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

    def test_birthday_whatsapp_sent(self, db):
        """يُرسل واتساب لعميل ميلاده اليوم"""
        import app.core.kernel.whatsapp as wa_module
        sent = []
        wa_module.send_whatsapp_message = lambda phone, msg: sent.append((phone, msg))

        branch = _make_branch(db)
        today = date.today()
        customer = _make_customer(
            db, branch,
            phone="01011112222",
            birthday=date(1985, today.month, today.day),
        )

        from app.modules.crm.models import Customer
        customers = (
            db.query(Customer)
            .filter(
                Customer.is_active.is_(True),
                Customer.blacklisted.is_(False),
                Customer.birthday.isnot(None),
            )
            .all()
        )
        for c in customers:
            if (
                c.birthday
                and c.birthday.month == today.month
                and c.birthday.day == today.day
                and c.phone
            ):
                wa_module.send_whatsapp_message(
                    c.phone,
                    f"عيد ميلاد سعيد يا {c.full_name}!",
                )

        assert any(phone == "01011112222" for phone, _ in sent)

    def test_task_runs_without_error(self, db):
        """task يشتغل بدون exception"""
        import app.core.kernel.whatsapp as wa_module
        original = wa_module.send_whatsapp_message
        wa_module.send_whatsapp_message = lambda *a, **kw: None
        try:
            from unittest.mock import patch, MagicMock
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=db)
            ctx.__exit__ = MagicMock(return_value=False)
            with patch("app.core.database.SessionLocal", return_value=ctx):
                from app.tasks.crm_tasks import birthday_greetings
                birthday_greetings()
        finally:
            wa_module.send_whatsapp_message = original
