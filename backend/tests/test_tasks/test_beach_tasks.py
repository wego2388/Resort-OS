"""
tests/test_tasks/test_beach_tasks.py
اختبارات الـ beach_tasks.py — service logic مباشرة بـ db fixture
بدون تشغيل Celery runtime
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest


# ─── helpers ────────────────────────────────────────────────────────────────

def _make_branch(db, active=True):
    """⚠️ حسابات 1165/4300 بتتزرع هنا دايمًا (مش بس وقت الحاجة الصريحة
    ليها): post_b2b_monthly_fees/mark_b2b_contracts_overdue بيفحصوا كل
    عقود B2B *النشطة عبر كل الفروع* بتصميم (نفس نطاق مهمة Celery
    الحقيقية) — أي عقد بيتعمل في أي تست في الملف ده (حتى لو مش موضوع
    التست الحالي) هيدخل في نفس الاستعلام العام، فلازم فرعه يقدر يترحّل
    عليه رسم شهري من غير FinancialConfigurationError وإلا التستات
    المتأخرة في نفس الجلسة تتأثر ببيانات تستات سابقة."""
    from app.modules.core.models import Branch
    b = Branch(
        name=f"Beach-Branch-{uuid.uuid4().hex[:6]}",
        code=f"BH{uuid.uuid4().hex[:4].upper()}",
        is_active=active,
    )
    db.add(b)
    db.commit()
    _seed_finance_accounts(db, b)
    return b


def _make_b2b_contract(db, branch, contact_phone=None, payment_terms_days=30, is_active=True):
    from app.modules.beach.models import B2BContract
    today = date.today()
    c = B2BContract(
        branch_id=branch.id,
        hotel_name=f"Hotel-{uuid.uuid4().hex[:4]}",
        contact_phone=contact_phone,
        monthly_guest_cap=50,
        monthly_fee=Decimal("4500"),
        valid_from=today - timedelta(days=60),
        valid_until=today + timedelta(days=300),
        is_active=is_active,
        payment_terms_days=payment_terms_days,
        is_overdue=False,
        notified_overdue=False,
    )
    db.add(c)
    db.commit()
    return c


def _seed_finance_accounts(db, branch):
    """2026-08-20: post_b2b_monthly_fees بيرحّل قيد حقيقي (Dr 1165/Cr 4300)
    — لازم الحسابين يكونوا موجودين على الفرع، وإلا الترحيل نفسه بيفشل
    بـFinancialConfigurationError. Idempotent."""
    from app.modules.finance.models import Account
    existing = {a.code for a in db.query(Account).filter(Account.branch_id == branch.id).all()}
    wanted = [("1165", "ذمم فنادق شريكة (B2B)", "asset"), ("4300", "Beach Revenue", "revenue")]
    added = [Account(branch_id=branch.id, code=c, name=n, account_type=t) for c, n, t in wanted if c not in existing]
    if added:
        db.add_all(added)
        db.commit()


def _bill_month(db, on_date):
    """يرحّل الرسم الشهري الثابت لكل عقود B2B النشطة عن الشهر المحتوي
    ``on_date`` — نفس آلية services.post_b2b_monthly_fees الحقيقية بالظبط
    (بديل _make_b2b_day القديمة اللي كانت بتبني B2BContractDay.total_amount
    مباشرة — العمود ده اتحذف من الموديل، والرصيد المستحق/التأخر بقى مبني
    على B2BContractMonth المُرحَّل فعليًا، راجع crud.get_b2b_oldest_
    unsettled_month)."""
    from app.modules.beach.services import post_b2b_monthly_fees
    billed = post_b2b_monthly_fees(db, on_date)
    db.commit()
    return billed


def _make_beach_reservation(db, branch, res_date=None, status="confirmed"):
    from app.modules.beach.models import BeachReservation
    res = BeachReservation(
        branch_id=branch.id,
        guest_name=f"Beach Guest {uuid.uuid4().hex[:4]}",
        guest_phone="01000000000",
        reservation_date=res_date or date.today(),
        guests_count=2,
        total_amount=Decimal("300"),
        status=status,
    )
    db.add(res)
    db.commit()
    return res


# ─── process_reservation_no_shows logic ─────────────────────────────────────

class TestBeachNoShows:
    """اختبار منطق process_reservation_no_shows"""

    def test_confirmed_reservation_becomes_no_show(self, db):
        """حجز confirmed يتحول لـ no_show"""
        branch = _make_branch(db)
        today = date.today()
        res = _make_beach_reservation(db, branch, res_date=today, status="confirmed")

        from app.modules.beach.crud import update_reservation_status
        update_reservation_status(db, res, "no_show")
        db.commit()
        db.refresh(res)

        assert res.status == "no_show"

    def test_cancelled_reservation_not_in_confirmed_query(self, db):
        """حجز cancelled لا يظهر في استعلام confirmed"""
        branch = _make_branch(db)
        today = date.today()
        res = _make_beach_reservation(db, branch, res_date=today, status="cancelled")

        from app.modules.beach.crud import list_reservations
        items, _ = list_reservations(db, branch.id, res_date=today, status="confirmed", limit=500)
        assert res.id not in [r.id for r in items]

    def test_task_runs_without_error(self, db):
        """task يشتغل بدون exception"""
        from unittest.mock import patch, MagicMock
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=db)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch("app.core.database.SessionLocal", return_value=ctx):
            from app.tasks.beach_tasks import process_reservation_no_shows
            process_reservation_no_shows()


# ─── mark_b2b_contracts_overdue logic ────────────────────────────────────────

class TestBeachB2BOverdue:
    """اختبار mark_b2b_contracts_overdue مباشرة"""

    def test_overdue_contract_marked(self, db):
        """عقد رحّله شهر قديم غير مسوّى يُصبح overdue"""
        branch = _make_branch(db)
        _seed_finance_accounts(db, branch)
        contract = _make_b2b_contract(db, branch, payment_terms_days=7)
        old_day = date.today() - timedelta(days=45)
        _bill_month(db, old_day)

        from app.modules.beach.services import mark_b2b_contracts_overdue
        changed = mark_b2b_contracts_overdue(db, date.today())
        db.commit()
        db.refresh(contract)

        assert changed >= 1
        assert contract.is_overdue is True

    def test_contract_within_terms_not_overdue(self, db):
        """عقد الشهر المرحّل له لسه ضمن المهلة لا يُصبح overdue"""
        branch = _make_branch(db)
        _seed_finance_accounts(db, branch)
        contract = _make_b2b_contract(db, branch, payment_terms_days=30)
        recent_day = date.today() - timedelta(days=5)
        _bill_month(db, recent_day)

        from app.modules.beach.services import mark_b2b_contracts_overdue
        mark_b2b_contracts_overdue(db, date.today())
        db.commit()
        db.refresh(contract)

        assert contract.is_overdue is False

    def test_whatsapp_sent_first_time_overdue(self, db):
        """واتساب يُرسل أول مرة يصبح العقد overdue"""
        import app.core.kernel.whatsapp as wa_module
        sent = []
        original = wa_module.send_whatsapp_message
        wa_module.send_whatsapp_message = lambda phone, msg: sent.append(phone)
        try:
            branch = _make_branch(db)
            _seed_finance_accounts(db, branch)
            contract = _make_b2b_contract(
                db, branch, contact_phone="01099991111", payment_terms_days=7,
            )
            old_day = date.today() - timedelta(days=45)
            _bill_month(db, old_day)

            from app.modules.beach.services import mark_b2b_contracts_overdue
            mark_b2b_contracts_overdue(db, date.today())
            db.commit()
            assert "01099991111" in sent
        finally:
            wa_module.send_whatsapp_message = original

    def test_whatsapp_not_sent_twice(self, db):
        """واتساب لا يُرسل مرة تانية لو notified_overdue=True"""
        import app.core.kernel.whatsapp as wa_module
        sent = []
        original = wa_module.send_whatsapp_message
        wa_module.send_whatsapp_message = lambda phone, msg: sent.append(phone)
        try:
            branch = _make_branch(db)
            _seed_finance_accounts(db, branch)
            contract = _make_b2b_contract(
                db, branch, contact_phone="01099990000", payment_terms_days=7,
            )
            contract.is_overdue = True
            contract.notified_overdue = True
            db.commit()

            old_day = date.today() - timedelta(days=45)
            _bill_month(db, old_day)

            from app.modules.beach.services import mark_b2b_contracts_overdue
            mark_b2b_contracts_overdue(db, date.today())
            db.commit()
            assert "01099990000" not in sent
        finally:
            wa_module.send_whatsapp_message = original

    def test_no_billed_months_no_overdue(self, db):
        """عقد من غير أي رسم شهري مُرحَّل لا يُصبح overdue"""
        branch = _make_branch(db)
        contract = _make_b2b_contract(db, branch, payment_terms_days=7)

        from app.modules.beach.services import mark_b2b_contracts_overdue
        mark_b2b_contracts_overdue(db, date.today())
        db.commit()
        db.refresh(contract)

        assert contract.is_overdue is False

    def test_task_runs_without_error(self, db):
        """task mark_b2b_overdue يشتغل بدون exception"""
        import app.core.kernel.whatsapp as wa_module
        original = wa_module.send_whatsapp_message
        wa_module.send_whatsapp_message = lambda *a, **kw: None
        try:
            from unittest.mock import patch, MagicMock
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=db)
            ctx.__exit__ = MagicMock(return_value=False)
            with patch("app.core.database.SessionLocal", return_value=ctx):
                from app.tasks.beach_tasks import mark_b2b_overdue
                mark_b2b_overdue()
        finally:
            wa_module.send_whatsapp_message = original


# ─── post_b2b_monthly_fees task ──────────────────────────────────────────────

class TestBeachB2BMonthlyFeesTask:
    """اختبار task الـCelery post_b2b_monthly_fees (wrapper حول
    services.post_b2b_monthly_fees) — نفس نمط TestBeachB2BOverdue.
    test_task_runs_without_error بالظبط (2026-08-20، جديد مع تحويل عقود
    B2B لمبلغ شهري ثابت)."""

    def test_task_runs_without_error(self, db):
        """task post_b2b_monthly_fees يشتغل بدون exception حتى بدون عقود"""
        from unittest.mock import patch, MagicMock
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=db)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch("app.core.database.SessionLocal", return_value=ctx):
            from app.tasks.beach_tasks import post_b2b_monthly_fees
            post_b2b_monthly_fees()

    def test_task_bills_active_contract_via_real_session(self, db):
        """تشغيل الـtask الحقيقي (مش services.post_b2b_monthly_fees مباشرة)
        على عقد نشط لازم يرحّل رسمه الشهري فعليًا — يثبت إن الـwrapper
        نفسه (SessionLocal + commit) بيوصل منطق الترحيل صح، مش بس الدالة
        الداخلية القابلة للاختبار."""
        from unittest.mock import patch, MagicMock
        from app.modules.beach import crud as beach_crud

        branch = _make_branch(db)
        _seed_finance_accounts(db, branch)
        contract = _make_b2b_contract(db, branch)

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=db)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch("app.core.database.SessionLocal", return_value=ctx):
            from app.tasks.beach_tasks import post_b2b_monthly_fees
            post_b2b_monthly_fees()

        month_start = date.today().replace(day=1)
        billed_month = beach_crud.get_b2b_contract_month(db, contract.id, month_start)
        assert billed_month is not None
        assert billed_month.amount == contract.monthly_fee
