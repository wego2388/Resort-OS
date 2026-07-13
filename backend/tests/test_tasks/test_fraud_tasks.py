"""
tests/test_tasks/test_fraud_tasks.py
Operations & Control Layer plan §3.5 — Fraud Detection boundary logic.
find_fraud_signals() is pure query + threshold comparison (no Celery/Redis/
WhatsApp involved), so every boundary case is tested directly against it,
mirroring beach_tasks.mark_b2b_contracts_overdue's testing style (explicit
`now` passed in, not datetime.utcnow() read inside the function).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest


def _make_user(db, role="cashier"):
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash

    user = User(
        email=f"fraud-{uuid.uuid4().hex[:8]}@test.local",
        password_hash=get_password_hash("Test@12345"),
        full_name=f"Test {role} {uuid.uuid4().hex[:4]}",
        role=role, is_active=True,
    )
    db.add(user); db.commit()
    return user


def _make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(name="Fraud Branch", name_ar="فرع اختبار احتيال",
               code=f"FRD-{uuid.uuid4().hex[:6].upper()}")
    db.add(b); db.commit()
    return b


def _add_audit_log(db, user_id, action, created_at, branch_id=None):
    from app.modules.core.models import AuditLog
    log = AuditLog(
        user_id=user_id, branch_id=branch_id, action=action,
        entity_type="test_entity", entity_id=1, created_at=created_at,
    )
    db.add(log)
    db.commit()
    return log


def _add_cash_movement(db, branch, shift, performed_by, movement_type, created_at):
    from app.modules.finance.models import CashMovement
    from decimal import Decimal
    m = CashMovement(
        branch_id=branch.id, shift_id=shift.id, movement_type=movement_type,
        amount=Decimal("0"), reason="اختبار", performed_by=performed_by, created_at=created_at,
    )
    db.add(m)
    db.commit()
    return m


class TestFindFraudSignalsRefund:
    def test_below_threshold_no_signal(self, db):
        from app.tasks.fraud_tasks import find_fraud_signals

        user = _make_user(db)
        now = datetime.utcnow()
        for _ in range(4):
            _add_audit_log(db, user.id, "refund_order_item", now - timedelta(minutes=5))

        signals = find_fraud_signals(
            db, now,
            refund_threshold=5, refund_window_minutes=60,
            void_threshold=999, void_window_minutes=60,
            discount_threshold=999, discount_window_minutes=60,
            drawer_open_threshold=999, drawer_open_window_minutes=1440,
        )
        assert signals == []

    def test_exactly_at_threshold_signals(self, db):
        from app.tasks.fraud_tasks import find_fraud_signals

        user = _make_user(db)
        now = datetime.utcnow()
        for _ in range(5):
            _add_audit_log(db, user.id, "refund_order_item", now - timedelta(minutes=5))

        signals = find_fraud_signals(
            db, now,
            refund_threshold=5, refund_window_minutes=60,
            void_threshold=999, void_window_minutes=60,
            discount_threshold=999, discount_window_minutes=60,
            drawer_open_threshold=999, drawer_open_window_minutes=1440,
        )
        assert len(signals) == 1
        assert signals[0].rule == "refund_count"
        assert signals[0].user_id == user.id
        assert signals[0].count == 5

    def test_outside_window_excluded(self, db):
        """مرتجعات قديمة (خارج نافذة الـ 60 دقيقة) متتحسبش خالص."""
        from app.tasks.fraud_tasks import find_fraud_signals

        user = _make_user(db)
        now = datetime.utcnow()
        for _ in range(10):
            _add_audit_log(db, user.id, "refund_order_item", now - timedelta(minutes=90))

        signals = find_fraud_signals(
            db, now,
            refund_threshold=5, refund_window_minutes=60,
            void_threshold=999, void_window_minutes=60,
            discount_threshold=999, discount_window_minutes=60,
            drawer_open_threshold=999, drawer_open_window_minutes=1440,
        )
        # الاستعلام عالمي (مش مقيّد بفرع) عمدًا — راجع docstring find_fraud_signals.
        # التستات التانية في نفس الجلسة بتـ commit بيانات حقيقية مش بترجع بـ
        # rollback (db.rollback() بيلغي بس الغير-محفوظ)، فالتحقق هنا مقصور
        # على *هذا* المستخدم تحديدًا بدل افتراض جدول فاضي عالميًا.
        assert user.id not in {s.user_id for s in signals}


class TestFindFraudSignalsOtherRules:
    def test_void_count_signal(self, db):
        from app.tasks.fraud_tasks import find_fraud_signals

        user = _make_user(db)
        now = datetime.utcnow()
        for _ in range(6):
            _add_audit_log(db, user.id, "void_order_item", now - timedelta(minutes=10))

        signals = find_fraud_signals(
            db, now,
            refund_threshold=999, refund_window_minutes=60,
            void_threshold=6, void_window_minutes=60,
            discount_threshold=999, discount_window_minutes=60,
            drawer_open_threshold=999, drawer_open_window_minutes=1440,
        )
        assert len(signals) == 1
        assert signals[0].rule == "void_count"

    def test_discount_count_signal(self, db):
        from app.tasks.fraud_tasks import find_fraud_signals

        user = _make_user(db)
        now = datetime.utcnow()
        for _ in range(3):
            _add_audit_log(db, user.id, "apply_discount", now - timedelta(minutes=10))

        signals = find_fraud_signals(
            db, now,
            refund_threshold=999, refund_window_minutes=60,
            void_threshold=999, void_window_minutes=60,
            discount_threshold=3, discount_window_minutes=60,
            drawer_open_threshold=999, drawer_open_window_minutes=1440,
        )
        assert len(signals) == 1
        assert signals[0].rule == "discount_count"

    def test_drawer_open_count_signal(self, db):
        """راجع Batch 2 — drawer_open مصدره CashMovement مش AuditLog."""
        from app.tasks.fraud_tasks import find_fraud_signals

        branch = _make_branch(db)
        user = _make_user(db)
        from app.modules.finance import services as finance_services
        from app.modules.finance.schemas import CashierShiftOpen
        from decimal import Decimal
        shift = finance_services.open_shift(
            db, cashier_id=user.id, opened_by=user.id,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("0")),
        )

        now = datetime.utcnow()
        for _ in range(4):
            _add_cash_movement(db, branch, shift, user.id, "drawer_open", now - timedelta(hours=2))

        signals = find_fraud_signals(
            db, now,
            refund_threshold=999, refund_window_minutes=60,
            void_threshold=999, void_window_minutes=60,
            discount_threshold=999, discount_window_minutes=60,
            drawer_open_threshold=4, drawer_open_window_minutes=1440,
        )
        assert len(signals) == 1
        assert signals[0].rule == "drawer_open_count"
        assert signals[0].count == 4

    def test_multiple_users_multiple_signals(self, db):
        from app.tasks.fraud_tasks import find_fraud_signals

        user1 = _make_user(db)
        user2 = _make_user(db)
        now = datetime.utcnow()
        for _ in range(5):
            _add_audit_log(db, user1.id, "refund_order_item", now - timedelta(minutes=5))
        for _ in range(5):
            _add_audit_log(db, user2.id, "void_order_item", now - timedelta(minutes=5))

        signals = find_fraud_signals(
            db, now,
            refund_threshold=5, refund_window_minutes=60,
            void_threshold=5, void_window_minutes=60,
            discount_threshold=999, discount_window_minutes=60,
            drawer_open_threshold=999, drawer_open_window_minutes=1440,
        )
        # نفس ملاحظة test_outside_window_excluded — نفلتر على المستخدمين
        # اللي أنشأهم التست ده تحديدًا، الاستعلام نفسه عالمي عمدًا.
        by_user = {s.user_id: s.rule for s in signals if s.user_id in (user1.id, user2.id)}
        assert by_user == {user1.id: "refund_count", user2.id: "void_count"}


class TestScanForFraudSignalsTask:
    def test_task_sends_whatsapp_and_dedups(self, db, monkeypatch):
        """اتصال الـ task الكامل: نداء notify_admin فعلي (mocked) لمرة واحدة
        بس — تاني نداء لنفس الكاشير/القاعدة خلال نافذة الـ dedup ما بيبعتش
        تنبيه تاني."""
        import app.tasks.fraud_tasks as fraud_tasks_module

        user = _make_user(db)
        now = datetime.utcnow()
        for _ in range(20):
            _add_audit_log(db, user.id, "refund_order_item", now - timedelta(minutes=5))

        sent_messages = []
        monkeypatch.setattr(
            "app.core.kernel.whatsapp.notify_admin",
            lambda msg: sent_messages.append(msg) or True,
        )
        monkeypatch.setattr("app.core.database.SessionLocal", lambda: db)
        # منع الـ context manager من قفل الـ session بتاع التست نفسه
        monkeypatch.setattr(type(db), "__enter__", lambda self: self, raising=False)
        monkeypatch.setattr(type(db), "__exit__", lambda self, *a: None, raising=False)

        # dedup cache في الذاكرة بدل Redis حقيقي
        _dedup_store: dict[str, bool] = {}
        monkeypatch.setattr(
            "app.core.kernel.cache.get_cache", lambda key: _dedup_store.get(key),
        )
        monkeypatch.setattr(
            "app.core.kernel.cache.set_cache",
            lambda key, value, ttl=300: _dedup_store.__setitem__(key, value),
        )
        monkeypatch.setattr(fraud_tasks_module.settings, "FRAUD_REFUND_COUNT_THRESHOLD", 5)

        def _messages_for_user() -> list[str]:
            # الاستعلام عالمي عمدًا (راجع find_fraud_signals docstring) —
            # التستات التانية في نفس الجلسة ممكن تكون سابت بيانات محفوظة
            # (db.rollback() بيلغي بس الغير-محفوظ)، فبنفلتر على اسم هذا
            # المستخدم تحديدًا بدل افتراض صندوق بريد فاضي عالميًا.
            return [m for m in sent_messages if user.full_name in m]

        fraud_tasks_module.scan_for_fraud_signals()
        assert len(_messages_for_user()) == 1

        # تاني نداء لنفس البيانات (نفس المرتجعات لسه موجودة) — مفيش تنبيه تاني
        fraud_tasks_module.scan_for_fraud_signals()
        assert len(_messages_for_user()) == 1
