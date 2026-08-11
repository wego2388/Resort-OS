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


# ─── accrue_due_rents task ────────────────────────────────────────────────

class TestLeasingAccrueDueRentsTask:
    """OPS-DATA-02 §10.5: الإيراد يتحقق (accrue) عند تاريخ الاستحقاق يوميًا
    عبر كل الفروع، قبل مهمة mark_overdue (راجع celery_app.py's beat_schedule
    — accrue الساعة 2:00، mark_overdue الساعة 2:30)."""

    def _seed_accounts(self, db, branch):
        from app.modules.finance.models import Account
        for code, name, acc_type in [
            ("1100", "Cash", "asset"), ("1260", "Tenant AR", "asset"),
            ("4500", "Lease Revenue", "revenue"),
        ]:
            db.add(Account(branch_id=branch.id, code=code, name=name, account_type=acc_type))
        db.commit()

    def test_task_accrues_due_payment_across_branches(self, db):
        from unittest.mock import patch, MagicMock
        branch = _make_branch(db)
        self._seed_accounts(db, branch)
        contract = _make_contract(db, branch)
        payment = _make_payment(db, contract, due_date=date.today() - timedelta(days=1))

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=db)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch("app.core.database.SessionLocal", return_value=ctx):
            from app.tasks.leasing_tasks import accrue_due_rents
            accrue_due_rents()

        db.refresh(payment)
        assert payment.accrued is True
        assert payment.accrual_journal_entry_id is not None

    def test_task_runs_without_error_when_nothing_due(self, db):
        from unittest.mock import patch, MagicMock
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=db)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch("app.core.database.SessionLocal", return_value=ctx):
            from app.tasks.leasing_tasks import accrue_due_rents
            accrue_due_rents()

    @staticmethod
    def _actor(db):
        from app.core.kernel.models.user import User
        user = User(
            email=f"backfill-{uuid.uuid4().hex[:8]}@test.local",
            password_hash="not-used", full_name="Backfill Operator",
            role="super_admin", is_active=True,
        )
        db.add(user)
        db.commit()
        return user

    def test_backfill_posts_strict_journal_once_with_real_actor(self, db):
        from app.modules.finance.models import JournalEntry
        from scripts.backfill_leasing_rent_accruals import apply_backfill, list_backfill_items

        branch = _make_branch(db)
        self._seed_accounts(db, branch)
        contract = _make_contract(db, branch)
        as_of = date(1900, 1, 2)
        payment = _make_payment(db, contract, due_date=date(1900, 1, 1))
        actor = self._actor(db)

        proposed = list_backfill_items(db, as_of=as_of)
        assert [item.payment_id for item in proposed] == [payment.id]
        assert payment.accrued is False

        assert apply_backfill(db, as_of=as_of, actor_id=actor.id) == [payment.id]
        db.refresh(payment)
        entry = db.query(JournalEntry).filter(JournalEntry.id == payment.accrual_journal_entry_id).one()
        assert payment.accrued is True
        assert entry.created_by == actor.id
        assert apply_backfill(db, as_of=as_of, actor_id=actor.id) == []

    def test_backfill_stops_on_accrued_row_without_linked_journal(self, db):
        from scripts.backfill_leasing_rent_accruals import apply_backfill

        branch = _make_branch(db)
        contract = _make_contract(db, branch)
        as_of = date(1899, 1, 2)
        payment = _make_payment(db, contract, due_date=date(1899, 1, 1))
        actor = self._actor(db)
        payment.accrued = True
        payment.accrual_journal_entry_id = None
        db.commit()

        with pytest.raises(RuntimeError, match="manual review required"):
            apply_backfill(db, as_of=as_of, actor_id=actor.id)


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

    def test_partial_payment_still_flagged_overdue_with_growing_penalty(self, db):
        """باج حقيقي اتصلح: الفلتر القديم كان ``status == "pending"`` بس —
        دفعة اتسدّدت جزئيًا (status="partial") كانت بتتخطى فحص التأخر
        للأبد، فمفيهاش غرامة اتحسبت خالص حتى لو باقي المبلغ فضل شهور من
        غير تحصيل. المهمة الحقيقية (مش استعلام مكرر يدوي) لازم تلقط
        وتحدّث الغرامة حتى لو الدفعة "partial"."""
        from unittest.mock import patch, MagicMock

        branch = _make_branch(db)
        contract = _make_contract(db, branch)
        overdue_date = date.today() - timedelta(days=10)  # داخل شريحة 5%
        payment = _make_payment(db, contract, due_date=overdue_date, status="partial")
        payment.paid_amount = Decimal("1000")
        db.commit()

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=db)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch("app.core.database.SessionLocal", return_value=ctx):
            from app.tasks.leasing_tasks import mark_overdue
            mark_overdue()

        db.refresh(payment)
        assert payment.status == "overdue"
        assert payment.penalty > Decimal("0")
        assert payment.paid_amount == Decimal("1000")  # المبلغ المدفوع فعلاً ميتلمسش

    def test_already_overdue_payment_penalty_escalates_with_time(self, db):
        """باج حقيقي اتصلح: دفعة اتوسمت "overdue" مرة كانت بتتخطى للأبد —
        يعني شريحة الغرامة كانت بتتجمّد على أول قيمة اتحسبت (5%) بدل ما
        تتصاعد لـ10% بعد ما التأخير يعدي 30 يوم."""
        from unittest.mock import patch, MagicMock
        from app.resort_os.timeshare_engine import calculate_lease_penalty

        branch = _make_branch(db)
        contract = _make_contract(db, branch)
        due = date.today() - timedelta(days=35)  # داخل شريحة 10%
        payment = _make_payment(db, contract, due_date=due, status="overdue")
        payment.penalty = calculate_lease_penalty(payment.amount, due, date.today() - timedelta(days=25))
        db.commit()
        stale_penalty = payment.penalty

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=db)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch("app.core.database.SessionLocal", return_value=ctx):
            from app.tasks.leasing_tasks import mark_overdue
            mark_overdue()

        db.refresh(payment)
        assert payment.penalty > stale_penalty


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
