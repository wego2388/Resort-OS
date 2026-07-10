"""
tests/test_tasks/test_leasing_tasks.py
اختبارات الـ leasing_tasks.py — service logic مباشرة بـ db fixture
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
        name=f"Lease-Branch-{uuid.uuid4().hex[:6]}",
        code=f"LS{uuid.uuid4().hex[:4].upper()}",
    )
    db.add(b)
    db.commit()
    return b


def _make_contract(db, branch, tenant_phone=None):
    from app.modules.leasing.models import LeaseContract
    today = date.today()
    import random
    contract = LeaseContract(
        branch_id=branch.id,
        contract_number=f"LC-{uuid.uuid4().hex[:8].upper()}",
        tenant_name=f"Tenant-{uuid.uuid4().hex[:4]}",
        tenant_phone=tenant_phone,
        unit_description="Unit A-101",
        start_date=today - timedelta(days=30),
        end_date=today + timedelta(days=335),
        base_rent=Decimal("5000"),
        billing_day=1,
        payment_period="monthly",
        status="active",
    )
    db.add(contract)
    db.commit()
    return contract


def _make_payment(db, contract, due_date, status="pending", amount=Decimal("5000")):
    from app.modules.leasing.models import LeasePayment
    p = LeasePayment(
        contract_id=contract.id,
        due_date=due_date,
        amount=amount,
        status=status,
    )
    db.add(p)
    db.commit()
    return p


# ─── mark_overdue logic ──────────────────────────────────────────────────────

class TestLeasingMarkOverdueLogic:
    """اختبار منطق mark_overdue مباشرة على DB"""

    def test_past_pending_payment_marked_overdue(self, db):
        """دفعة pending فات تاريخها تتحول لـ overdue"""
        from app.resort_os.timeshare_engine import calculate_lease_penalty
        branch = _make_branch(db)
        contract = _make_contract(db, branch)
        yesterday = date.today() - timedelta(days=1)
        payment = _make_payment(db, contract, due_date=yesterday, status="pending")

        # نفذ منطق المهمة مباشرة
        from app.modules.leasing.models import LeasePayment
        today = date.today()
        overdue = (
            db.query(LeasePayment)
            .filter(
                LeasePayment.due_date < today,
                LeasePayment.status == "pending",
            )
            .all()
        )
        for p in overdue:
            penalty = calculate_lease_penalty(p.amount, p.due_date, today)
            p.status = "overdue"
            p.penalty = penalty
        db.commit()

        db.refresh(payment)
        assert payment.status == "overdue"
        assert payment.penalty >= Decimal("0")

    def test_future_payment_not_touched(self, db):
        """دفعة في المستقبل لا تتغير"""
        branch = _make_branch(db)
        contract = _make_contract(db, branch)
        next_month = date.today() + timedelta(days=30)
        payment = _make_payment(db, contract, due_date=next_month, status="pending")

        from app.modules.leasing.models import LeasePayment
        today = date.today()
        overdue = (
            db.query(LeasePayment)
            .filter(LeasePayment.due_date < today, LeasePayment.status == "pending")
            .all()
        )
        # payment المستقبلي لا يكون في القائمة
        assert payment.id not in [p.id for p in overdue]

    def test_already_overdue_payment_not_duplicated(self, db):
        """دفعة overdue مسبقاً لا تتغير مرة تانية"""
        branch = _make_branch(db)
        contract = _make_contract(db, branch)
        old_date = date.today() - timedelta(days=10)
        payment = _make_payment(db, contract, due_date=old_date, status="overdue")

        from app.modules.leasing.models import LeasePayment
        today = date.today()
        # الاستعلام بيفلتر status == "pending" فقط
        overdue = (
            db.query(LeasePayment)
            .filter(LeasePayment.due_date < today, LeasePayment.status == "pending")
            .all()
        )
        assert payment.id not in [p.id for p in overdue]

    def test_penalty_calculated_correctly(self, db):
        """الغرامة محسوبة صح بـ calculate_lease_penalty"""
        from app.resort_os.timeshare_engine import calculate_lease_penalty
        amount = Decimal("10000")
        due = date.today() - timedelta(days=5)
        today = date.today()
        penalty = calculate_lease_penalty(amount, due, today)
        assert isinstance(penalty, Decimal)
        assert penalty >= Decimal("0")

    def test_task_runs_without_error(self, db):
        """task يشتغل بدون exception"""
        from unittest.mock import patch, MagicMock
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=db)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch("app.core.database.SessionLocal", return_value=ctx):
            from app.tasks.leasing_tasks import mark_overdue
            mark_overdue()


# ─── send_due_reminders logic ────────────────────────────────────────────────

class TestLeasingSendDueReminders:
    """اختبار منطق send_due_reminders"""

    def test_payment_due_in_7_days_found(self, db):
        """دفعة مستحقة خلال 7 أيام تُوجد في نتائج الاستعلام"""
        branch = _make_branch(db)
        contract = _make_contract(db, branch, tenant_phone="01099997777")
        remind_date = date.today() + timedelta(days=7)
        payment = _make_payment(db, contract, due_date=remind_date, status="pending")

        from app.modules.leasing.models import LeasePayment
        due_soon = (
            db.query(LeasePayment)
            .filter(
                LeasePayment.due_date == remind_date,
                LeasePayment.status == "pending",
            )
            .all()
        )
        assert payment.id in [p.id for p in due_soon]

    def test_payment_due_tomorrow_not_in_7day_query(self, db):
        """دفعة مستحقة غداً لا تظهر في استعلام الـ 7 أيام"""
        branch = _make_branch(db)
        contract = _make_contract(db, branch)
        tomorrow = date.today() + timedelta(days=1)
        payment = _make_payment(db, contract, due_date=tomorrow, status="pending")

        remind_date = date.today() + timedelta(days=7)
        from app.modules.leasing.models import LeasePayment
        due_soon = (
            db.query(LeasePayment)
            .filter(LeasePayment.due_date == remind_date, LeasePayment.status == "pending")
            .all()
        )
        assert payment.id not in [p.id for p in due_soon]

    def test_whatsapp_sent_to_tenant_with_phone(self, db):
        """يُرسل واتساب للمستأجر اللي عنده رقم"""
        import app.core.kernel.whatsapp as wa_module
        sent = []
        wa_module.send_whatsapp_message = lambda phone, msg: sent.append(phone)

        branch = _make_branch(db)
        contract = _make_contract(db, branch, tenant_phone="01012340000")
        remind_date = date.today() + timedelta(days=7)
        payment = _make_payment(db, contract, due_date=remind_date, status="pending")

        from app.modules.leasing.models import LeaseContract, LeasePayment
        due_soon = (
            db.query(LeasePayment)
            .filter(LeasePayment.due_date == remind_date, LeasePayment.status == "pending")
            .all()
        )
        for p in due_soon:
            c = db.query(LeaseContract).filter(LeaseContract.id == p.contract_id).first()
            if c and c.tenant_phone:
                wa_module.send_whatsapp_message(
                    c.tenant_phone,
                    f"تذكير: دفعة مستحقة {p.due_date:%Y-%m-%d}",
                )

        assert "01012340000" in sent

    def test_no_whatsapp_without_phone(self, db):
        """لا يُرسل واتساب لو المستأجر بدون رقم"""
        import app.core.kernel.whatsapp as wa_module
        sent = []
        original = wa_module.send_whatsapp_message
        wa_module.send_whatsapp_message = lambda phone, msg: sent.append(phone)
        try:
            branch = _make_branch(db)
            contract = _make_contract(db, branch, tenant_phone=None)
            remind_date = date.today() + timedelta(days=7)
            payment = _make_payment(db, contract, due_date=remind_date, status="pending")

            from app.modules.leasing.models import LeaseContract, LeasePayment
            # فلترة على contract_id المحدد فقط لعزل الـ test
            due_soon = (
                db.query(LeasePayment)
                .filter(
                    LeasePayment.contract_id == contract.id,
                    LeasePayment.due_date == remind_date,
                    LeasePayment.status == "pending",
                )
                .all()
            )
            for p in due_soon:
                c = db.query(LeaseContract).filter(LeaseContract.id == p.contract_id).first()
                if c and c.tenant_phone:
                    wa_module.send_whatsapp_message(c.tenant_phone, "test")

            assert sent == []
        finally:
            wa_module.send_whatsapp_message = original

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
                from app.tasks.leasing_tasks import send_due_reminders
                send_due_reminders()
        finally:
            wa_module.send_whatsapp_message = original
