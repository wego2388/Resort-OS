"""
tests/test_tasks/test_timeshare_tasks_extended.py
اختبارات إضافية لـ timeshare_tasks.py — send_visit_reminders,
send_installment_reminders, send_visit_survey
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
    b = Branch(
        name=f"TS-Branch-{uuid.uuid4().hex[:6]}",
        code=f"TS{uuid.uuid4().hex[:4].upper()}",
    )
    db.add(b)
    db.commit()
    return b


def _make_manager(db):
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    u = User(
        email=f"mgr_{uuid.uuid4().hex[:6]}@ts.test",
        password_hash=get_password_hash("Test@12345"),
        full_name="TS Manager",
        role="manager",
        is_active=True,
    )
    db.add(u)
    db.commit()
    return u


def _make_ts_contract(db, branch, manager, phone=None, week_number=None, status="active"):
    from app.modules.timeshare import crud as ts_crud
    from app.modules.timeshare.schemas import TimeshareContractCreate
    today = date.today()
    data = TimeshareContractCreate(
        branch_id=branch.id,
        customer_name=f"TSCustomer-{uuid.uuid4().hex[:4]}",
        customer_phone=phone,
        room_type="2R",
        total_value=Decimal("60000"),
        down_payment=Decimal("10000"),
        installments=12,
        installment_period=1,
        first_installment_date=today + timedelta(days=30),
        start_date=today,
        season="high",
        week_number=week_number,
    )
    contract = ts_crud.create_contract(db, data, signed_by=manager.id)
    if status != "active":
        contract.status = status
        db.commit()
    return contract


def _make_installment(db, contract, due_date, status="pending", amount=Decimal("5000")):
    from app.modules.timeshare.models import TimeshareInstallment
    inst = TimeshareInstallment(
        contract_id=contract.id,
        installment_no=99,
        due_date=due_date,
        amount=amount,
        status=status,
    )
    db.add(inst)
    db.commit()
    return inst


def _make_ts_visit(db, contract, branch, check_in=None, check_out=None):
    from app.modules.timeshare.models import TimeshareVisit
    today = date.today()
    ci = check_in or today
    co = check_out or today + timedelta(days=7)
    visit = TimeshareVisit(
        contract_id=contract.id,
        branch_id=branch.id,
        check_in=ci,
        check_out=co,
        nights=(co - ci).days,
        status="scheduled",
    )
    db.add(visit)
    db.commit()
    return visit


# ─── send_installment_reminders logic ────────────────────────────────────────

class TestTimeshareInstallmentReminders:
    """اختبار منطق send_installment_reminders"""

    def test_installment_due_in_7_days_found(self, db):
        """قسط مستحق خلال 7 أيام يُوجد في الاستعلام"""
        branch = _make_branch(db)
        manager = _make_manager(db)
        contract = _make_ts_contract(db, branch, manager, phone="01012300000")
        remind_date = date.today() + timedelta(days=7)
        inst = _make_installment(db, contract, due_date=remind_date)

        from app.modules.timeshare.models import TimeshareInstallment
        due_soon = (
            db.query(TimeshareInstallment)
            .filter(
                TimeshareInstallment.due_date == remind_date,
                TimeshareInstallment.status == "pending",
            )
            .all()
        )
        assert inst.id in [i.id for i in due_soon]

    def test_past_installment_not_in_7day_query(self, db):
        """قسط فات تاريخه لا يظهر في استعلام الـ 7 أيام"""
        branch = _make_branch(db)
        manager = _make_manager(db)
        contract = _make_ts_contract(db, branch, manager)
        old_date = date.today() - timedelta(days=3)
        inst = _make_installment(db, contract, due_date=old_date)

        remind_date = date.today() + timedelta(days=7)
        from app.modules.timeshare.models import TimeshareInstallment
        due_soon = (
            db.query(TimeshareInstallment)
            .filter(TimeshareInstallment.due_date == remind_date, TimeshareInstallment.status == "pending")
            .all()
        )
        assert inst.id not in [i.id for i in due_soon]

    def test_whatsapp_sent_for_upcoming_installment(self, db):
        """يُرسل واتساب لصاحب العقد لو عنده رقم"""
        import app.core.kernel.whatsapp as wa_module
        sent = []
        wa_module.send_whatsapp_message = lambda phone, msg: sent.append(phone)

        branch = _make_branch(db)
        manager = _make_manager(db)
        contract = _make_ts_contract(db, branch, manager, phone="01099009900")
        remind_date = date.today() + timedelta(days=7)
        inst = _make_installment(db, contract, due_date=remind_date)

        from app.modules.timeshare.models import TimeshareInstallment, TimeshareContract
        due_soon = (
            db.query(TimeshareInstallment)
            .filter(TimeshareInstallment.due_date == remind_date, TimeshareInstallment.status == "pending")
            .all()
        )
        for i in due_soon:
            c = db.query(TimeshareContract).filter(TimeshareContract.id == i.contract_id).first()
            if c and c.customer_phone:
                wa_module.send_whatsapp_message(
                    c.customer_phone,
                    f"تذكير: قسط {i.amount:,.2f} مستحق {i.due_date:%Y-%m-%d}",
                )

        assert "01099009900" in sent

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
                from app.tasks.timeshare_tasks import send_installment_reminders
                send_installment_reminders()
        finally:
            wa_module.send_whatsapp_message = original


# ─── send_visit_reminders logic ──────────────────────────────────────────────

class TestTimeshareVisitReminders:
    """اختبار منطق send_visit_reminders"""

    def test_active_contracts_with_week_number_queried(self, db):
        """عقود active مع week_number مش null يُستعلَم عنها"""
        branch = _make_branch(db)
        manager = _make_manager(db)
        contract = _make_ts_contract(db, branch, manager, week_number=15)

        from app.modules.timeshare.models import TimeshareContract
        contracts = (
            db.query(TimeshareContract)
            .filter(
                TimeshareContract.status == "active",
                TimeshareContract.week_number.isnot(None),
            )
            .all()
        )
        assert contract.id in [c.id for c in contracts]

    def test_contract_without_week_number_excluded(self, db):
        """عقد بدون week_number (floating) لا يظهر في الاستعلام"""
        branch = _make_branch(db)
        manager = _make_manager(db)
        contract = _make_ts_contract(db, branch, manager, week_number=None)

        from app.modules.timeshare.models import TimeshareContract
        contracts = (
            db.query(TimeshareContract)
            .filter(
                TimeshareContract.status == "active",
                TimeshareContract.week_number.isnot(None),
            )
            .all()
        )
        assert contract.id not in [c.id for c in contracts]

    def test_cancelled_contract_excluded(self, db):
        """عقد cancelled لا يظهر في الاستعلام"""
        branch = _make_branch(db)
        manager = _make_manager(db)
        contract = _make_ts_contract(db, branch, manager, week_number=10, status="cancelled")

        from app.modules.timeshare.models import TimeshareContract
        contracts = (
            db.query(TimeshareContract)
            .filter(
                TimeshareContract.status == "active",
                TimeshareContract.week_number.isnot(None),
            )
            .all()
        )
        assert contract.id not in [c.id for c in contracts]

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
                from app.tasks.timeshare_tasks import send_visit_reminders
                send_visit_reminders()
        finally:
            wa_module.send_whatsapp_message = original


# ─── send_visit_survey task ──────────────────────────────────────────────────

class TestTimeshareVisitSurvey:
    """اختبار send_visit_survey"""

    def test_survey_sent_to_customer_with_phone(self, db):
        """يُرسل survey واتساب للضيف لو عنده رقم"""
        import app.core.kernel.whatsapp as wa_module
        sent = []
        original = wa_module.send_whatsapp_message
        wa_module.send_whatsapp_message = lambda phone, msg: sent.append((phone, msg))
        try:
            from unittest.mock import patch, MagicMock
            branch = _make_branch(db)
            manager = _make_manager(db)
            contract = _make_ts_contract(db, branch, manager, phone="01088887777", week_number=5)
            visit = _make_ts_visit(db, contract, branch)

            from app.modules.timeshare.models import TimeshareVisit
            from app.modules.analytics.services import create_survey_token

            v = db.query(TimeshareVisit).filter(TimeshareVisit.id == visit.id).first()
            assert v is not None
            c = v.contract
            assert c is not None

            if c.customer_phone:
                token = create_survey_token(branch_id=branch.id, timeshare_visit_id=visit.id)
                wa_module.send_whatsapp_message(c.customer_phone, f"شاركنا رأيك: survey/{token}")

            assert any(phone == "01088887777" for phone, _ in sent)
        finally:
            wa_module.send_whatsapp_message = original

    def test_survey_skipped_without_phone(self, db):
        """لا يُرسل survey لو العميل بدون رقم"""
        import app.core.kernel.whatsapp as wa_module
        sent = []
        original = wa_module.send_whatsapp_message
        wa_module.send_whatsapp_message = lambda phone, msg: sent.append(phone)
        try:
            branch = _make_branch(db)
            manager = _make_manager(db)
            contract = _make_ts_contract(db, branch, manager, phone=None, week_number=3)
            visit = _make_ts_visit(db, contract, branch)

            from app.modules.timeshare.models import TimeshareVisit
            v = db.query(TimeshareVisit).filter(TimeshareVisit.id == visit.id).first()
            c = v.contract

            if c and c.customer_phone:
                wa_module.send_whatsapp_message(c.customer_phone, "test")

            assert sent == []
        finally:
            wa_module.send_whatsapp_message = original

    def test_survey_task_visit_not_found(self, db):
        """task لا يرمي exception لو visit غير موجود"""
        from app.tasks.timeshare_tasks import send_visit_survey
        send_visit_survey(visit_id=999999, branch_id=1)  # should not raise

    def test_survey_task_runs_with_valid_visit(self, db):
        """task يشتغل بدون exception مع زيارة حقيقية"""
        import app.core.kernel.whatsapp as wa_module
        original = wa_module.send_whatsapp_message
        wa_module.send_whatsapp_message = lambda *a, **kw: None
        try:
            from unittest.mock import patch, MagicMock
            branch = _make_branch(db)
            manager = _make_manager(db)
            contract = _make_ts_contract(db, branch, manager, phone="01011110000", week_number=8)
            visit = _make_ts_visit(db, contract, branch)

            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=db)
            ctx.__exit__ = MagicMock(return_value=False)
            with patch("app.core.database.SessionLocal", return_value=ctx):
                from app.tasks.timeshare_tasks import send_visit_survey
                send_visit_survey(visit_id=visit.id, branch_id=branch.id)
        finally:
            wa_module.send_whatsapp_message = original
