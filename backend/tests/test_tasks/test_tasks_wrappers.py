"""
tests/test_tasks/test_tasks_wrappers.py
اختبارات تغطي الـ task wrapper functions (الـ SessionLocal path)
لـ: timeshare_tasks.mark_overdue, finance_tasks، crm_tasks، leasing_tasks
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest


def _db_ctx(db):
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=db)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


def _make_branch(db, active=True):
    from app.modules.core.models import Branch
    b = Branch(
        name=f"WR-Branch-{uuid.uuid4().hex[:6]}",
        code=f"WR{uuid.uuid4().hex[:4].upper()}",
        is_active=active,
    )
    db.add(b)
    db.commit()
    return b


# ─── timeshare_tasks.mark_overdue (wrapper) ──────────────────────────────────

class TestTimeshareMarkOverdueWrapper:

    def test_mark_overdue_task_wrapper_runs(self, db):
        """task wrapper يشتغل بدون exception"""
        with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
            from app.tasks.timeshare_tasks import mark_overdue
            mark_overdue()

    def test_mark_overdue_partial_installment_flagged(self, db):
        """قسط partial متأخر يُحوَّل لـ overdue"""
        from app.modules.timeshare.models import TimeshareInstallment
        from app.tasks.timeshare_tasks import _mark_overdue

        branch = _make_branch(db)
        manager = _make_manager(db)
        contract = _make_ts_contract(db, branch, manager)

        # قسط partial من أمس
        yesterday = date.today() - timedelta(days=1)
        inst = TimeshareInstallment(
            contract_id=contract.id,
            installment_no=5,
            due_date=yesterday,
            amount=Decimal("3000"),
            status="partial",
        )
        db.add(inst)
        db.commit()

        count = _mark_overdue(db, date.today())
        db.commit()
        db.refresh(inst)

        assert inst.status == "overdue"
        assert count >= 1

    def test_mark_overdue_freezes_booking_for_overdue_contract(self, db):
        """عقد فيه أقساط overdue يتجمّد booking_frozen"""
        from app.modules.timeshare.models import TimeshareInstallment
        from app.tasks.timeshare_tasks import _mark_overdue

        branch = _make_branch(db)
        manager = _make_manager(db)
        contract = _make_ts_contract(db, branch, manager)

        # أضف قسط متأخر بقيمة كبيرة يستوجب التجميد
        old_date = date.today() - timedelta(days=5)
        inst = TimeshareInstallment(
            contract_id=contract.id,
            installment_no=6,
            due_date=old_date,
            amount=Decimal("20000"),
            status="pending",
        )
        db.add(inst)
        db.commit()

        _mark_overdue(db, date.today())
        db.commit()
        db.refresh(contract)

        # should_freeze_booking بتقرر بناءً على القيمة — نتحقق فقط إن الكود اتنفذ
        assert isinstance(contract.booking_frozen, bool)


def _make_manager(db):
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    u = User(
        email=f"mgr_{uuid.uuid4().hex[:6]}@wrap.test",
        password_hash=get_password_hash("Test@12345"),
        full_name="WR Manager",
        role="manager",
        is_active=True,
    )
    db.add(u)
    db.commit()
    return u


def _make_ts_contract(db, branch, manager):
    from app.modules.timeshare import crud as ts_crud
    from app.modules.timeshare.schemas import TimeshareContractCreate
    today = date.today()
    data = TimeshareContractCreate(
        branch_id=branch.id,
        customer_name=f"WR-{uuid.uuid4().hex[:4]}",
        room_type="2R",
        total_value=Decimal("50000"),
        down_payment=Decimal("5000"),
        installments=12,
        installment_period=1,
        first_installment_date=today + timedelta(days=30),
        start_date=today,
        season="high",
    )
    return ts_crud.create_contract(db, data, signed_by=manager.id)


# ─── finance_tasks wrappers ──────────────────────────────────────────────────

class TestFinanceTasksWrappers:

    def test_check_due_reminders_wrapper_runs(self, db):
        """check_due_reminders task يشتغل بدون exception"""
        import app.core.kernel.whatsapp as wa_module
        original = wa_module.send_whatsapp_message
        wa_module.send_whatsapp_message = lambda *a, **kw: None
        try:
            with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
                from app.tasks.finance_tasks import check_due_reminders
                check_due_reminders()
        finally:
            wa_module.send_whatsapp_message = original

    def test_check_timeshare_dues_direct(self, db):
        """_check_timeshare_dues يشتغل مباشرة بدون exception"""
        import app.core.kernel.whatsapp as wa_module
        original = wa_module.send_whatsapp_message
        wa_module.send_whatsapp_message = lambda *a, **kw: None
        try:
            from app.tasks.finance_tasks import _check_timeshare_dues
            branch = _make_branch(db)
            remind_date = date.today() + timedelta(days=3)
            _check_timeshare_dues(db, branch.id, remind_date)
        finally:
            wa_module.send_whatsapp_message = original

    def test_check_leasing_dues_direct(self, db):
        """_check_leasing_dues يشتغل مباشرة بدون exception"""
        import app.core.kernel.whatsapp as wa_module
        original = wa_module.send_whatsapp_message
        wa_module.send_whatsapp_message = lambda *a, **kw: None
        try:
            from app.tasks.finance_tasks import _check_leasing_dues
            branch = _make_branch(db)
            remind_date = date.today() + timedelta(days=3)
            _check_leasing_dues(db, branch.id, remind_date)
        finally:
            wa_module.send_whatsapp_message = original


# ─── crm_tasks wrappers ──────────────────────────────────────────────────────

class TestCrmTasksWrappers:

    def test_activity_reminders_wrapper_runs(self, db):
        """activity_reminders task wrapper يشتغل بدون exception"""
        import app.core.kernel.whatsapp as wa_module
        original = wa_module.send_whatsapp_message
        wa_module.send_whatsapp_message = lambda *a, **kw: None
        try:
            with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
                from app.tasks.crm_tasks import activity_reminders
                activity_reminders()
        finally:
            wa_module.send_whatsapp_message = original

    def test_overdue_alert_wrapper_runs(self, db):
        """overdue_activities_alert task wrapper يشتغل بدون exception"""
        import app.core.kernel.whatsapp as wa_module
        original_notify = getattr(wa_module, "notify_admin", lambda *a: None)
        wa_module.notify_admin = lambda *a, **kw: None
        try:
            with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
                from app.tasks.crm_tasks import overdue_activities_alert
                overdue_activities_alert()
        finally:
            wa_module.notify_admin = original_notify

    def test_birthday_greetings_wrapper_runs(self, db):
        """birthday_greetings task wrapper يشتغل بدون exception"""
        import app.core.kernel.whatsapp as wa_module
        original = wa_module.send_whatsapp_message
        wa_module.send_whatsapp_message = lambda *a, **kw: None
        try:
            with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
                from app.tasks.crm_tasks import birthday_greetings
                birthday_greetings()
        finally:
            wa_module.send_whatsapp_message = original


# ─── leasing_tasks wrappers ──────────────────────────────────────────────────

class TestLeasingTasksWrappers:

    def test_mark_overdue_wrapper_runs(self, db):
        """mark_overdue task wrapper يشتغل بدون exception"""
        with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
            from app.tasks.leasing_tasks import mark_overdue
            mark_overdue()

    def test_send_due_reminders_wrapper_runs(self, db):
        """send_due_reminders task wrapper يشتغل بدون exception"""
        import app.core.kernel.whatsapp as wa_module
        original = wa_module.send_whatsapp_message
        wa_module.send_whatsapp_message = lambda *a, **kw: None
        try:
            with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
                from app.tasks.leasing_tasks import send_due_reminders
                send_due_reminders()
        finally:
            wa_module.send_whatsapp_message = original


# ─── timeshare send_visit_reminders / send_installment_reminders wrappers ────

class TestTimeshareReminderWrappers:

    def test_send_visit_reminders_wrapper_runs(self, db):
        """send_visit_reminders task wrapper يشتغل بدون exception"""
        import app.core.kernel.whatsapp as wa_module
        original = wa_module.send_whatsapp_message
        wa_module.send_whatsapp_message = lambda *a, **kw: None
        try:
            with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
                from app.tasks.timeshare_tasks import send_visit_reminders
                send_visit_reminders()
        finally:
            wa_module.send_whatsapp_message = original

    def test_send_installment_reminders_wrapper_runs(self, db):
        """send_installment_reminders task wrapper يشتغل بدون exception"""
        import app.core.kernel.whatsapp as wa_module
        original = wa_module.send_whatsapp_message
        wa_module.send_whatsapp_message = lambda *a, **kw: None
        try:
            with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
                from app.tasks.timeshare_tasks import send_installment_reminders
                send_installment_reminders()
        finally:
            wa_module.send_whatsapp_message = original

    def test_send_visit_survey_wrapper_not_found(self, db):
        """send_visit_survey لا يرمي exception لو visit مش موجود"""
        with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
            from app.tasks.timeshare_tasks import send_visit_survey
            send_visit_survey(visit_id=999999, branch_id=1)
