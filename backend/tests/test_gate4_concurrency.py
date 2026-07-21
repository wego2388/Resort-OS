"""
tests/test_gate4_concurrency.py
Postgres-only real-concurrency proofs for Gate 4's new atomicity-sensitive
logic: the open-shift DB invariant, exactly-once idempotent settlement, the
one-active-order-per-table partial unique index, and concurrent refunds of
the same item. Row-level locking + partial unique indexes only actually
enforce on a real Postgres engine (SQLite ignores with_for_update and treats
the partial unique indexes loosely — CLAUDE.md §13 ⓫), so these prove the
real thing with overlapping transactions on separate threads/connections.

Mirrors tests/test_dining_paid_concurrency.py's pattern exactly: a disposable
per-test throwaway database (never the shared dev DB), tables built via
Base.metadata.create_all(), dropped at the end regardless of outcome. Reuses
that file's data helpers.

Usage — set an admin Postgres DSN before running:

    DINING_CONCURRENCY_TEST_ADMIN_URL=postgresql+psycopg://postgres:resort_dev_pass@localhost:5436/postgres \\
        pytest tests/test_gate4_concurrency.py -v

Skips automatically (does not fail) when that env var is unset.
"""
from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from tests.test_dining_paid_concurrency import (
    make_branch, make_finance_accounts, make_item, make_outlet,
    make_paid_ready_order,
)

DINING_CONCURRENCY_TEST_ADMIN_URL = os.environ.get("DINING_CONCURRENCY_TEST_ADMIN_URL")

pytestmark = pytest.mark.skipif(
    not DINING_CONCURRENCY_TEST_ADMIN_URL,
    reason=(
        "Postgres-only real-concurrency test — set DINING_CONCURRENCY_TEST_ADMIN_URL "
        "(admin DSN) to run. Skipped by default; does not affect `pytest tests/`."
    ),
)


@pytest.fixture
def pg_engine():
    admin_engine = sa.create_engine(DINING_CONCURRENCY_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT")
    db_name = f"resort_os_gate4_conctest_{uuid.uuid4().hex[:10]}"
    base_url = DINING_CONCURRENCY_TEST_ADMIN_URL.rsplit("/", 1)[0]
    target_url = f"{base_url}/{db_name}"

    with admin_engine.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
    admin_engine.dispose()

    from app.core.database import Base
    import app.core.kernel.models.user      # noqa: F401
    import app.modules.core.models          # noqa: F401
    import app.modules.finance.models       # noqa: F401
    import app.modules.hr.models            # noqa: F401
    import app.modules.pms.models           # noqa: F401
    import app.modules.beach.models         # noqa: F401
    import app.modules.inventory.models     # noqa: F401
    import app.modules.dining.models        # noqa: F401
    import app.modules.crm.models           # noqa: F401

    engine = sa.create_engine(target_url, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)

    try:
        yield engine
    finally:
        engine.dispose()
        cleanup_engine = sa.create_engine(DINING_CONCURRENCY_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT")
        with cleanup_engine.connect() as conn:
            conn.execute(sa.text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{db_name}' AND pid <> pg_backend_pid()"
            ))
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        cleanup_engine.dispose()


@pytest.fixture
def Session(pg_engine):
    return sessionmaker(bind=pg_engine, autoflush=False, autocommit=False)


def _open_shift(db, branch_id, cashier_id):
    from app.modules.finance.models import CashierShift
    shift = CashierShift(
        branch_id=branch_id, cashier_id=cashier_id, opened_at=datetime.utcnow(),
        opened_by=cashier_id, opening_float=Decimal("0"), status="open",
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift


def _make_table(db, branch, outlet):
    from app.modules.dining.models import VenueTable
    t = VenueTable(branch_id=branch.id,
                   table_number=f"T-{uuid.uuid4().hex[:4]}", capacity=4, status="available")
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _open_order(db, branch, outlet, item, *, table_id=None, qty=1):
    """طلب مفتوح (open) عبر ORM مباشرة — نفس منطق make_paid_ready_order بس
    بحالة open وطاولة اختيارية (لاختبارات نقل/دمج/إضافة أصناف)."""
    from app.modules.dining.models import DiningOrder, DiningOrderItem
    from app.core.config import settings
    subtotal = item.price * qty
    vat = (subtotal * Decimal(str(settings.VAT_PERCENTAGE)) / 100).quantize(Decimal("0.01"))
    svc = (subtotal * Decimal(str(settings.SERVICE_CHARGE_PERCENTAGE)) / 100).quantize(Decimal("0.01"))
    order = DiningOrder(
        branch_id=branch.id, outlet_id=outlet.id,
        order_number=f"ORD-{uuid.uuid4().hex[:10].upper()}",
        order_type="dine_in" if table_id else "takeaway", status="open", guests_count=1,
        table_id=table_id, subtotal=subtotal, vat_amount=vat, service_charge=svc,
        discount_amount=Decimal("0"), total=subtotal + vat + svc,
    )
    db.add(order)
    db.flush()
    db.add(DiningOrderItem(order_id=order.id, item_id=item.id, name=item.name,
                           quantity=qty, unit_price=item.price, status="pending"))
    db.commit()
    db.refresh(order)
    return order


# ─────────────────────── Open-shift double-open race ────────────────────

class TestOpenShiftDoubleOpenRace:
    def test_two_concurrent_open_shift_only_one_wins(self, Session):
        """كاشير واحد، فرع واحد، طلبان متزامنان لفتح وردية (threading.Barrier).
        الـ partial unique index (uq_open_shift_per_branch_cashier) لازم يخلي
        واحد بس ينجح والتاني يترفض OpenShiftConflictError — مفيش ورديتين
        مفتوحتين لنفس الكاشير."""
        from app.modules.finance import services as finance_services
        from app.modules.finance.schemas import CashierShiftOpen
        from app.modules.finance.models import CashierShift

        setup_db = Session()
        branch = make_branch(setup_db)
        branch_id = branch.id
        setup_db.close()

        cashier_id = 501
        barrier = threading.Barrier(2)
        results, errors = {}, {}

        def _open(key):
            db = Session()
            try:
                barrier.wait(timeout=5)
                results[key] = finance_services.open_shift(
                    db, cashier_id, cashier_id,
                    CashierShiftOpen(branch_id=branch_id, opening_float=Decimal("0")),
                )
            except Exception as exc:  # noqa: BLE001
                errors[key] = exc
            finally:
                db.close()

        t1 = threading.Thread(target=_open, args=("a",))
        t2 = threading.Thread(target=_open, args=("b",))
        t1.start(); t2.start()
        t1.join(timeout=15); t2.join(timeout=15)
        assert not t1.is_alive() and not t2.is_alive()

        assert len(results) == 1, f"لازم فتح واحد ينجح بس — results={list(results)}, errors={errors}"
        assert len(errors) == 1
        assert isinstance(list(errors.values())[0], finance_services.OpenShiftConflictError)

        verify_db = Session()
        try:
            open_count = (
                verify_db.query(CashierShift)
                .filter(CashierShift.branch_id == branch_id,
                        CashierShift.cashier_id == cashier_id,
                        CashierShift.status == "open")
                .count()
            )
            assert open_count == 1
        finally:
            verify_db.close()


# ─────────────────────── Idempotent exactly-once settlement ─────────────

class TestIdempotentSettlementDoubleSubmit:
    def test_same_key_double_submit_settles_exactly_once(self, Session):
        """نفس Idempotency-Key + نفس الطلب + نفس النية مبعوتين متزامنين —
        النتيجة: تسوية واحدة بالظبط، صف Payment موجب واحد بالظبط، والطلب
        paid. اللي مايكسبش قفل الطلب بياخد 409 concurrency أو replay ناجح —
        الاتنين مقبولين طول ما الأثر مرة واحدة بس."""
        from app.modules.dining import services as dining_services
        from app.modules.dining.models import DiningSettlement
        from app.modules.finance.models import Payment

        setup_db = Session()
        branch = make_branch(setup_db)
        outlet = make_outlet(setup_db, branch)
        make_finance_accounts(setup_db, branch)
        item = make_item(setup_db, branch, outlet)
        order = make_paid_ready_order(setup_db, branch, outlet, item)
        order_id = order.id
        cashier_id = 601
        _open_shift(setup_db, branch.id, cashier_id)
        setup_db.close()

        key = f"idem-{uuid.uuid4().hex}"
        barrier = threading.Barrier(2)
        outcome = {}

        def _settle(tag):
            db = Session()
            try:
                barrier.wait(timeout=5)
                res = dining_services.settle_order(
                    db, order_id,
                    tenders=[{"method": "cash", "amount": None, "charge_to_room_id": None}],
                    settled_by=cashier_id, idempotency_key=key,
                )
                outcome[tag] = ("ok", res.status)
            except Exception as exc:  # noqa: BLE001
                outcome[tag] = ("error", exc)
            finally:
                db.close()

        t1 = threading.Thread(target=_settle, args=("a",))
        t2 = threading.Thread(target=_settle, args=("b",))
        t1.start(); t2.start()
        t1.join(timeout=15); t2.join(timeout=15)
        assert not t1.is_alive() and not t2.is_alive()

        oks = [v for v in outcome.values() if v[0] == "ok"]
        assert oks, f"مفيش أي تسوية نجحت — {outcome}"

        verify_db = Session()
        try:
            settlements = verify_db.query(DiningSettlement).filter_by(order_id=order_id).count()
            assert settlements == 1, f"لازم تسوية واحدة بالظبط — لقينا {settlements}"
            positive_payments = (
                verify_db.query(Payment)
                .filter(Payment.ref_order_id == order_id, Payment.amount > 0)
                .count()
            )
            assert positive_payments == 1, f"لازم Payment موجب واحد بالظبط — لقينا {positive_payments}"
            from app.modules.dining.models import DiningOrder
            fresh = verify_db.query(DiningOrder).filter_by(id=order_id).first()
            assert fresh is not None and fresh.status == "paid"
        finally:
            verify_db.close()


# ─────────────────────── One active order per table ─────────────────────

class TestOneActiveOrderPerTableRace:
    def test_two_concurrent_orders_same_table_only_one_active(self, Session):
        """طلبان متزامنان بيتفتحوا على نفس الطاولة — قفل الطاولة + partial
        unique index (uq_active_order_per_table) لازم يخلوا طلب نشط واحد بس
        ينجح، والتاني يترفض بوضوح (الطاولة مشغولة). مفيش طلبين نشطين على نفس
        الطاولة أبدًا."""
        from app.modules.dining import services as dining_services
        from app.modules.dining.models import DiningOrder
        from app.modules.dining.schemas import OrderCreate, OrderItemCreate

        setup_db = Session()
        branch = make_branch(setup_db)
        outlet = make_outlet(setup_db, branch)
        make_finance_accounts(setup_db, branch)
        item = make_item(setup_db, branch, outlet)
        table = _make_table(setup_db, branch, outlet)
        branch_id, outlet_id, item_id, table_id = branch.id, outlet.id, item.id, table.id
        setup_db.close()

        barrier = threading.Barrier(2)
        outcome = {}

        def _create(tag):
            db = Session()
            try:
                data = OrderCreate(
                    outlet_id=outlet_id, table_id=table_id, order_type="dine_in",
                    items=[OrderItemCreate(item_id=item_id, quantity=1)],
                )
                barrier.wait(timeout=5)
                res = dining_services.create_order(db, branch_id, data, waiter_id=1)
                outcome[tag] = ("ok", res.id)
            except Exception as exc:  # noqa: BLE001
                outcome[tag] = ("error", exc)
            finally:
                db.close()

        t1 = threading.Thread(target=_create, args=("a",))
        t2 = threading.Thread(target=_create, args=("b",))
        t1.start(); t2.start()
        t1.join(timeout=15); t2.join(timeout=15)
        assert not t1.is_alive() and not t2.is_alive()

        oks = [v for v in outcome.values() if v[0] == "ok"]
        errs = [v for v in outcome.values() if v[0] == "error"]
        assert len(oks) == 1, f"لازم طلب واحد ينجح بس — {outcome}"
        assert len(errs) == 1

        verify_db = Session()
        try:
            active = (
                verify_db.query(DiningOrder)
                .filter(DiningOrder.table_id == table_id,
                        DiningOrder.status.in_(("held", "open", "in_kitchen", "served")))
                .count()
            )
            assert active == 1, f"لازم طلب نشط واحد بالظبط على الطاولة — لقينا {active}"
        finally:
            verify_db.close()


# ─────────────────────── Concurrent refund of same item ─────────────────

class TestConcurrentRefundSameItem:
    def test_two_concurrent_refunds_same_item_only_one_wins(self, Session):
        """طلب مدفوع، صنف واحد، مرتجعان متزامنان لنفس الصنف — قفل صف الطلب
        (get_order_for_update) لازم يخلي واحد بس ينجح والتاني يترفض (409
        مشغول أو 'مرتجع بالفعل'). النتيجة: refunded_amount = مرة واحدة بس،
        وصف عكس Payment واحد بس (مفيش عكس مالي مكرر)."""
        from app.modules.dining import services as dining_services
        from app.modules.dining.models import DiningOrder
        from app.modules.finance.models import Payment

        setup_db = Session()
        branch = make_branch(setup_db)
        outlet = make_outlet(setup_db, branch)
        make_finance_accounts(setup_db, branch)
        item = make_item(setup_db, branch, outlet)
        order = make_paid_ready_order(setup_db, branch, outlet, item)
        order_id = order.id
        cashier_id = 701
        _open_shift(setup_db, branch.id, cashier_id)
        # نحصّل الطلب أولاً (كاش) عشان يبقى paid وله Payment أصلي.
        dining_services.settle_order(
            setup_db, order_id,
            tenders=[{"method": "cash", "amount": None, "charge_to_room_id": None}],
            settled_by=cashier_id,
        )
        fresh = setup_db.query(DiningOrder).filter_by(id=order_id).first()
        assert fresh is not None
        item_id = fresh.items[0].id
        setup_db.close()

        barrier = threading.Barrier(2)
        outcome = {}

        def _refund(tag):
            db = Session()
            try:
                barrier.wait(timeout=5)
                res = dining_services.refund_order_item(db, order_id, item_id, "الأكل بايظ", refunded_by=cashier_id)
                outcome[tag] = ("ok", res.refunded_amount)
            except Exception as exc:  # noqa: BLE001
                outcome[tag] = ("error", exc)
            finally:
                db.close()

        t1 = threading.Thread(target=_refund, args=("a",))
        t2 = threading.Thread(target=_refund, args=("b",))
        t1.start(); t2.start()
        t1.join(timeout=15); t2.join(timeout=15)
        assert not t1.is_alive() and not t2.is_alive()

        oks = [v for v in outcome.values() if v[0] == "ok"]
        assert len(oks) == 1, f"لازم مرتجع واحد ينجح بس — {outcome}"

        verify_db = Session()
        try:
            reversal_count = (
                verify_db.query(Payment)
                .filter(Payment.ref_order_id == order_id,
                        Payment.source == "dining_refund", Payment.amount < 0)
                .count()
            )
            assert reversal_count == 1, f"لازم عكس Payment واحد بالظبط — لقينا {reversal_count}"
            fresh = verify_db.query(DiningOrder).filter_by(id=order_id).first()
            # الطلب صنف واحد بس → مرتجعه بيخلي الطلب كله refunded.
            assert fresh is not None and fresh.status == "refunded"
        finally:
            verify_db.close()


# ─────────────── High 1: payment / cash-movement vs close-shift ──────────

class TestPaymentVsCloseShift:
    def test_direct_payment_rejected_while_shift_being_closed_then_succeeds(self, Session):
        """High 1(a) (جولة مراجعة Codex الأولى): بينما وردية بتتقفل (صف
        الوردية مقفول FOR UPDATE من مسار الإغلاق)، محاولة دفع مباشر لنفس
        الوردية لازم تترفض فورًا (ShiftCloseInProgressError = 409 retry) —
        مش تنجح منسوبة لوردية بتتقفل وexpected_cash محسوب من غيرها. بعد ما
        القفل يتحرر، نفس الدفع لازم ينجح (الوردية لسه مفتوحة)."""
        from app.modules.dining import services as dining_services
        from app.modules.finance import services as finance_services
        from app.modules.finance import crud as finance_crud
        from app.modules.finance.models import Payment

        setup_db = Session()
        branch = make_branch(setup_db)
        outlet = make_outlet(setup_db, branch)
        make_finance_accounts(setup_db, branch)
        item = make_item(setup_db, branch, outlet)
        order = make_paid_ready_order(setup_db, branch, outlet, item)
        order_id = order.id
        cashier_id = 801
        shift = _open_shift(setup_db, branch.id, cashier_id)
        shift_id = shift.id
        setup_db.close()

        lock_acquired = threading.Event()
        release = threading.Event()
        holder_db = Session()

        def _hold_shift_lock():
            # يحاكي close_shift: قفل صف الوردية (blocking FOR UPDATE) وإمساكه.
            finance_crud.lock_shift_for_update(holder_db, shift_id)
            lock_acquired.set()
            release.wait(timeout=10)
            holder_db.rollback()

        holder = threading.Thread(target=_hold_shift_lock)
        holder.start()
        assert lock_acquired.wait(timeout=5), "الوردية ماتقفلتش خلال المهلة"

        payer_db = Session()
        try:
            with pytest.raises(finance_services.ShiftCloseInProgressError):
                dining_services.settle_order(
                    payer_db, order_id,
                    tenders=[{"method": "cash", "amount": None, "charge_to_room_id": None}],
                    settled_by=cashier_id,
                )
        finally:
            payer_db.rollback()
            payer_db.close()

        release.set()
        holder.join(timeout=5)
        assert not holder.is_alive()
        holder_db.close()

        final_db = Session()
        try:
            res = dining_services.settle_order(
                final_db, order_id,
                tenders=[{"method": "cash", "amount": None, "charge_to_room_id": None}],
                settled_by=cashier_id,
            )
            assert res.status == "paid"
            pay = final_db.query(Payment).filter(Payment.ref_order_id == order_id, Payment.amount > 0).one()
            assert pay.shift_id == shift_id  # اترصد على الوردية المفتوحة
        finally:
            final_db.close()


class TestCashMovementVsCloseShift:
    def test_cash_movement_rejected_when_shift_closed_under_lock(self, Session):
        """High 1(b): حركة كاش يدوية بتتسلسل ضد إغلاق الوردية (نفس صف
        الوردية، blocking FOR UPDATE) — مستحيل تتسجّل على وردية بتتقفل في
        نفس اللحظة. لما الإغلاق يكمّل (status=closed تحت القفل)، الحركة بتترفض
        ('الوردية مقفولة') ومفيش أي صف حركة بيتكتب."""
        from app.modules.finance import services as finance_services
        from app.modules.finance import crud as finance_crud
        from app.modules.finance.models import CashMovement
        from app.modules.finance.schemas import CashMovementCreate

        setup_db = Session()
        branch = make_branch(setup_db)
        cashier_id = 811
        shift = _open_shift(setup_db, branch.id, cashier_id)
        shift_id = shift.id
        setup_db.close()

        locked = threading.Event()
        release = threading.Event()
        holder_db = Session()

        def _close_holder():
            s = finance_crud.lock_shift_for_update(holder_db, shift_id)
            s.status = "closed"
            holder_db.flush()
            locked.set()
            release.wait(timeout=10)
            holder_db.commit()

        ht = threading.Thread(target=_close_holder)
        ht.start()
        assert locked.wait(timeout=5)

        outcome = {}
        mover_db = Session()

        def _move():
            try:
                finance_services.record_cash_movement(
                    mover_db, shift_id,
                    CashMovementCreate(movement_type="cash_in", amount=Decimal("50"), reason="عهدة اختبار تزامن"),
                    performed_by=cashier_id, acting_user_level=100,
                )
                outcome["r"] = ("ok", None)
            except Exception as exc:  # noqa: BLE001
                outcome["r"] = ("err", exc)
            finally:
                mover_db.rollback()
                mover_db.close()

        mt = threading.Thread(target=_move)
        mt.start()
        # الـ mover بيبلوك على قفل الوردية — نحرر holder عشان يكمّل الإغلاق.
        release.set()
        ht.join(timeout=5)
        mt.join(timeout=5)
        assert not ht.is_alive() and not mt.is_alive()
        holder_db.close()

        assert outcome["r"][0] == "err", f"الحركة نجحت على وردية بتتقفل — {outcome}"
        assert "مقفول" in str(outcome["r"][1])

        verify = Session()
        try:
            cnt = verify.query(CashMovement).filter(CashMovement.shift_id == shift_id).count()
            assert cnt == 0, "اتكتبت حركة كاش على وردية مقفولة"
        finally:
            verify.close()


# ─────────────── High 2: every order mutation locks the order ────────────

class TestPaidOrderMutationLockContention:
    """High 2: أي mutation على الطلب (إلغاء/إضافة أصناف/إلغاء صنف/خصم/نقل/دمج)
    بقى بيقفل صف الطلب (get_order_for_update NOWAIT) زي settle/refund بالظبط —
    فبينما الطلب مقفول بعملية دفع، أي mutation متزامنة بتترفض فورًا 409
    (OrderPaymentConcurrencyError) بدل ما تدهس الحالة بصمت. بيثبت 'الطرف
    الخاسر بياخد 409 نظيف، مش overwrite صامت'."""

    def _hold_order_lock(self, Session, order_id):
        from app.modules.dining import crud as dining_crud
        lock_acquired = threading.Event()
        release = threading.Event()
        holder_db = Session()

        def _hold():
            dining_crud.get_order_for_update(holder_db, order_id)
            lock_acquired.set()
            release.wait(timeout=10)
            holder_db.rollback()

        thread = threading.Thread(target=_hold)
        thread.start()
        assert lock_acquired.wait(timeout=5), "الطلب ماتقفلش خلال المهلة"
        return thread, release, holder_db

    def _setup(self, Session):
        db = Session()
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        item = make_item(db, branch, outlet)
        ctx = {"branch": branch, "outlet": outlet, "item": item, "db": db}
        return ctx

    def test_cancel_gets_409_while_order_locked(self, Session):
        from app.modules.dining import services as dining_services
        ctx = self._setup(Session)
        order = _open_order(ctx["db"], ctx["branch"], ctx["outlet"], ctx["item"])
        oid = order.id
        ctx["db"].close()
        thread, release, holder_db = self._hold_order_lock(Session, oid)
        db = Session()
        try:
            with pytest.raises(dining_services.OrderPaymentConcurrencyError):
                dining_services.update_order_status(db, oid, "cancelled")
        finally:
            db.rollback(); db.close()
            release.set(); thread.join(timeout=5); holder_db.close()

    def test_add_items_gets_409_while_order_locked(self, Session):
        from app.modules.dining import services as dining_services
        from app.modules.dining.schemas import OrderItemCreate
        ctx = self._setup(Session)
        order = _open_order(ctx["db"], ctx["branch"], ctx["outlet"], ctx["item"])
        oid, item_id = order.id, ctx["item"].id
        ctx["db"].close()
        thread, release, holder_db = self._hold_order_lock(Session, oid)
        db = Session()
        try:
            with pytest.raises(dining_services.OrderPaymentConcurrencyError):
                dining_services.add_items_to_order(db, oid, [OrderItemCreate(item_id=item_id, quantity=1)])
        finally:
            db.rollback(); db.close()
            release.set(); thread.join(timeout=5); holder_db.close()

    def test_void_item_gets_409_while_order_locked(self, Session):
        from app.modules.dining import services as dining_services
        ctx = self._setup(Session)
        order = _open_order(ctx["db"], ctx["branch"], ctx["outlet"], ctx["item"])
        oid = order.id
        item_row_id = order.items[0].id
        ctx["db"].close()
        thread, release, holder_db = self._hold_order_lock(Session, oid)
        db = Session()
        try:
            with pytest.raises(dining_services.OrderPaymentConcurrencyError):
                dining_services.void_order_item(db, oid, item_row_id, "سبب", voided_by=1, acting_user_level=100)
        finally:
            db.rollback(); db.close()
            release.set(); thread.join(timeout=5); holder_db.close()

    def test_apply_discount_gets_409_while_order_locked(self, Session):
        from app.modules.dining import services as dining_services
        ctx = self._setup(Session)
        order = _open_order(ctx["db"], ctx["branch"], ctx["outlet"], ctx["item"])
        oid = order.id
        ctx["db"].close()
        thread, release, holder_db = self._hold_order_lock(Session, oid)
        db = Session()
        try:
            with pytest.raises(dining_services.OrderPaymentConcurrencyError):
                dining_services.apply_order_discount(db, oid, applied_by=1, acting_user_level=100)
        finally:
            db.rollback(); db.close()
            release.set(); thread.join(timeout=5); holder_db.close()

    def test_transfer_table_gets_409_while_order_locked(self, Session):
        from app.modules.dining import services as dining_services
        ctx = self._setup(Session)
        table_a = _make_table(ctx["db"], ctx["branch"], ctx["outlet"])
        table_b = _make_table(ctx["db"], ctx["branch"], ctx["outlet"])
        order = _open_order(ctx["db"], ctx["branch"], ctx["outlet"], ctx["item"], table_id=table_a.id)
        oid, table_b_id = order.id, table_b.id
        ctx["db"].close()
        thread, release, holder_db = self._hold_order_lock(Session, oid)
        db = Session()
        try:
            with pytest.raises(dining_services.OrderPaymentConcurrencyError):
                dining_services.transfer_order_table(db, oid, table_b_id)
        finally:
            db.rollback(); db.close()
            release.set(); thread.join(timeout=5); holder_db.close()

    def test_merge_gets_409_while_order_locked(self, Session):
        from app.modules.dining import services as dining_services
        ctx = self._setup(Session)
        source = _open_order(ctx["db"], ctx["branch"], ctx["outlet"], ctx["item"])
        target = _open_order(ctx["db"], ctx["branch"], ctx["outlet"], ctx["item"])
        source_id, target_id = source.id, target.id
        ctx["db"].close()
        # نقفل الهدف (أعلى id غالبًا) — merge بيقفل الاتنين بترتيب تصاعدي فبيصطدم.
        lock_id = min(source_id, target_id)
        thread, release, holder_db = self._hold_order_lock(Session, lock_id)
        db = Session()
        try:
            with pytest.raises(dining_services.OrderPaymentConcurrencyError):
                dining_services.merge_orders(db, source_id, target_id, merged_by=1)
        finally:
            db.rollback(); db.close()
            release.set(); thread.join(timeout=5); holder_db.close()


class TestPaidVsCancelRace:
    def test_concurrent_pay_and_cancel_never_leaves_paid_order_cancelled(self, Session):
        """High 2 (الباج المُثبَت حيًا): دفع + إلغاء متزامنين لنفس الطلب —
        مستحيل الطلب يخلص 'cancelled' وهو عنده settlement/Payment موجب.
        النتيجة الوحيدة المقبولة: يا إما اتدفع (paid، والإلغاء اترفض) أو
        اتلغى (cancelled، والدفع اترفض) — مفيش حالة رمادية."""
        from app.modules.dining import services as dining_services
        from app.modules.dining.models import DiningOrder, DiningSettlement
        from app.modules.finance.models import Payment

        setup_db = Session()
        branch = make_branch(setup_db)
        outlet = make_outlet(setup_db, branch)
        make_finance_accounts(setup_db, branch)
        item = make_item(setup_db, branch, outlet)
        order = make_paid_ready_order(setup_db, branch, outlet, item)
        order_id = order.id
        cashier_id = 821
        _open_shift(setup_db, branch.id, cashier_id)
        setup_db.close()

        barrier = threading.Barrier(2)
        outcome = {}

        def _pay():
            db = Session()
            try:
                barrier.wait(timeout=5)
                dining_services.settle_order(
                    db, order_id,
                    tenders=[{"method": "cash", "amount": None, "charge_to_room_id": None}],
                    settled_by=cashier_id,
                )
                outcome["pay"] = ("ok", None)
            except Exception as exc:  # noqa: BLE001
                outcome["pay"] = ("err", exc)
            finally:
                db.close()

        def _cancel():
            db = Session()
            try:
                barrier.wait(timeout=5)
                dining_services.update_order_status(db, order_id, "cancelled")
                outcome["cancel"] = ("ok", None)
            except Exception as exc:  # noqa: BLE001
                outcome["cancel"] = ("err", exc)
            finally:
                db.close()

        t1 = threading.Thread(target=_pay)
        t2 = threading.Thread(target=_cancel)
        t1.start(); t2.start()
        t1.join(timeout=15); t2.join(timeout=15)
        assert not t1.is_alive() and not t2.is_alive()

        verify = Session()
        try:
            fresh = verify.query(DiningOrder).filter_by(id=order_id).one()
            settlements = verify.query(DiningSettlement).filter_by(order_id=order_id).count()
            positive_payments = (
                verify.query(Payment)
                .filter(Payment.ref_order_id == order_id, Payment.amount > 0)
                .count()
            )
            # الحالة الممنوعة تمامًا: طلب cancelled ومعاه أثر دفع حقيقي.
            assert not (fresh.status == "cancelled" and (settlements or positive_payments)), (
                f"طلب اتلغى ومعاه دفع! status={fresh.status}, "
                f"settlements={settlements}, positive_payments={positive_payments}"
            )
            if fresh.status == "paid":
                assert settlements == 1 and positive_payments == 1
            else:
                assert fresh.status == "cancelled" and settlements == 0 and positive_payments == 0
        finally:
            verify.close()
