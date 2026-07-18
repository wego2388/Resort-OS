"""
tests/test_dining_paid_concurrency.py
Postgres-only real-concurrency proof for Gate 1B's dining "paid" strict
unit of work. Row-level locking (SELECT ... FOR UPDATE NOWAIT for
Order/Product, blocking FOR UPDATE for Folio) only actually enforces under
a real Postgres engine — SQLite ignores with_for_update entirely (CLAUDE.md
§13 bullet ⓫), so tests/test_api/test_dining_paid_atomicity.py can only
prove the exception-handling *contract* via monkeypatch, not genuine lock
contention. This file proves the real thing, with real overlapping
transactions on separate threads/connections against a live Postgres.

Mirrors tests/test_dining_migration.py's pattern exactly: an admin
connection creates a disposable, per-test throwaway database (never the
shared dev `resort_os` database), tables are built directly via
Base.metadata.create_all() (no Alembic needed here — we're not testing
migration correctness, just row locks), and the database is dropped at the
end regardless of outcome.

Usage — set an admin Postgres DSN before running:

    DINING_CONCURRENCY_TEST_ADMIN_URL=postgresql+psycopg://postgres:resort_dev_pass@localhost:5436/postgres \\
        pytest tests/test_dining_paid_concurrency.py -v

Skips automatically (does not fail, does not affect `pytest tests/`'s
100%-green requirement) when that env var is unset.

Synchronization note: a real race with no coordination would be flaky and
prove nothing reliably. Each test uses threading.Event/Barrier to force a
*deterministic* overlap — e.g. thread A provably still holds a row lock
(signaled via an Event) at the exact moment thread B's conflicting attempt
runs — which is the standard, non-flaky way to prove real lock behavior.
"""
from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

DINING_CONCURRENCY_TEST_ADMIN_URL = os.environ.get("DINING_CONCURRENCY_TEST_ADMIN_URL")

pytestmark = pytest.mark.skipif(
    not DINING_CONCURRENCY_TEST_ADMIN_URL,
    reason=(
        "Postgres-only real-concurrency test — set DINING_CONCURRENCY_TEST_ADMIN_URL "
        "(admin DSN, e.g. postgresql+psycopg://postgres:pass@localhost:5436/postgres) "
        "to run. Skipped by default; does not affect `pytest tests/`."
    ),
)


@pytest.fixture
def pg_engine():
    """نفس نمط tests/test_dining_migration.py's migrated_db_url بالظبط —
    قاعدة بيانات مؤقتة معزولة لكل تست، متبنية جداولها مباشرة (بدون
    Alembic — مش بنختبر صحة الـ migration هنا، بس القفل الحقيقي)، وبتتمسح
    في النهاية دايمًا."""
    admin_engine = sa.create_engine(DINING_CONCURRENCY_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT")
    db_name = f"resort_os_dining_conctest_{uuid.uuid4().hex[:10]}"
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


# ─────────────────────── Fixture data helpers ──────────────────────────

def make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(name="Concurrency Test Branch", name_ar="فرع اختبار التزامن",
               code=f"CONC-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_finance_accounts(db, branch, revenue_code="4200"):
    from app.modules.finance.models import Account
    for code, acc_type in [
        ("1100", "asset"), ("1150", "asset"), ("1200", "asset"),
        ("5200", "expense"), (revenue_code, "revenue"),
    ]:
        db.add(Account(branch_id=branch.id, code=code, name=code, account_type=acc_type))
    db.commit()


def make_outlet(db, branch, revenue_account_code="4200"):
    from app.modules.dining.models import Outlet
    outlet = Outlet(branch_id=branch.id, name=f"outlet-{uuid.uuid4().hex[:6]}",
                     outlet_type="restaurant", revenue_account_code=revenue_account_code)
    db.add(outlet)
    db.commit()
    return outlet


def make_item(db, branch, outlet, price=Decimal("50.00")):
    from app.modules.dining.models import DiningItem
    item = DiningItem(branch_id=branch.id, outlet_id=outlet.id, name="صنف اختبار تزامن",
                       price=price, is_available=True)
    db.add(item)
    db.commit()
    return item


def make_paid_ready_order(db, branch, outlet, item, quantity=1, folio_id=None):
    """طلب مفتوح جاهز يتحول لـ 'paid' — بنبني الطلب مباشرة عبر ORM بدل
    dining.services.create_order عشان نتحكم في كل حقل بدقة من غير الاعتماد
    على أي إعداد Session خارجي (settings.VAT_PERCENTAGE إلخ) غير موجود هنا."""
    from app.modules.dining.models import DiningOrder, DiningOrderItem
    from app.core.config import settings

    subtotal = item.price * quantity
    vat = (subtotal * Decimal(str(settings.VAT_PERCENTAGE)) / 100).quantize(Decimal("0.01"))
    service_charge = (subtotal * Decimal(str(settings.SERVICE_CHARGE_PERCENTAGE)) / 100).quantize(Decimal("0.01"))
    total = subtotal + vat + service_charge

    order = DiningOrder(
        branch_id=branch.id, outlet_id=outlet.id,
        order_number=f"ORD-CONC-{uuid.uuid4().hex[:10].upper()}",
        order_type="takeaway", status="open", guests_count=1,
        subtotal=subtotal, vat_amount=vat, service_charge=service_charge,
        discount_amount=Decimal("0"), total=total, folio_id=folio_id,
    )
    db.add(order)
    db.flush()
    order_item = DiningOrderItem(
        order_id=order.id, item_id=item.id, name=item.name,
        quantity=quantity, unit_price=item.price, status="pending",
    )
    db.add(order_item)
    db.commit()
    db.refresh(order)
    return order


def make_folio(db, branch):
    from app.modules.finance.models import Folio
    folio = Folio(
        branch_id=branch.id, guest_name="ضيف اختبار تزامن",
        check_in=datetime.utcnow(), check_out=datetime.utcnow() + timedelta(days=1),
        status="open",
    )
    db.add(folio)
    db.commit()
    return folio


def make_product(db, branch, current_stock=Decimal("1000")):
    from app.modules.inventory.models import Product, Warehouse
    warehouse = Warehouse(branch_id=branch.id, name="مخزن اختبار",
                           code=f"WH-{uuid.uuid4().hex[:6].upper()}")
    db.add(warehouse)
    db.flush()
    product = Product(
        branch_id=branch.id, warehouse_id=warehouse.id, name="منتج اختبار تزامن",
        sku=f"SKU-{uuid.uuid4().hex[:8].upper()}", unit="piece",
        cost_price=Decimal("10.00"), current_stock=current_stock,
    )
    db.add(product)
    db.commit()
    return product


class TestSameOrderDoublePaymentRealLock:
    def test_second_concurrent_paid_attempt_gets_409_while_first_holds_lock(self, Session):
        """Thread A تمسك قفل صف الطلب (SELECT FOR UPDATE NOWAIT) فعليًا
        وتفضل ماسكاه (معاملة مفتوحة، من غير commit)، وفي نفس اللحظة —
        مُثبَتة بـ threading.Event، مش تخمين توقيت — Thread B (المعاملة
        الرئيسية الحقيقية عبر services.update_order_status) بتحاول تدفع
        نفس الطلب. لازم ترفض فورًا بـ OrderPaymentConcurrencyError (409)،
        مش تنتظر. بعد ما A تسيب القفل، نفس الطلب لازم يتقدر يتدفع صح."""
        from app.modules.dining import crud, services

        setup_db = Session()
        branch = make_branch(setup_db)
        outlet = make_outlet(setup_db, branch)
        make_finance_accounts(setup_db, branch)
        item = make_item(setup_db, branch, outlet)
        order = make_paid_ready_order(setup_db, branch, outlet, item)
        order_id = order.id
        setup_db.close()

        lock_acquired = threading.Event()
        release_lock = threading.Event()
        holder_db = Session()

        def _hold_lock():
            crud.get_order_for_update(holder_db, order_id)
            lock_acquired.set()
            release_lock.wait(timeout=10)
            holder_db.rollback()

        holder_thread = threading.Thread(target=_hold_lock)
        holder_thread.start()
        assert lock_acquired.wait(timeout=5), "Thread A ماسكتش القفل خلال المهلة"

        attacker_db = Session()
        try:
            with pytest.raises(services.OrderPaymentConcurrencyError):
                services.update_order_status(attacker_db, order_id, "paid")
        finally:
            attacker_db.rollback()
            attacker_db.close()

        release_lock.set()
        holder_thread.join(timeout=5)
        assert not holder_thread.is_alive(), (
            "Thread A لسه شغال بعد المهلة (hang حقيقي) — النتيجة اللي "
            "بعد كده (فتح جلسة جديدة، دفع الطلب) مش موثوقة لو القفل لسه "
            "ممسوك فعليًا في thread معلّق"
        )
        holder_db.close()

        final_db = Session()
        try:
            result = services.update_order_status(final_db, order_id, "paid")
            assert result.status == "paid"
        finally:
            final_db.close()


class TestSameFolioConcurrentDiningCharges:
    def test_two_concurrent_room_charge_orders_both_succeed_with_correct_total(self, Session):
        """فوليو واحد، طلبين مختلفين بيتدفعوا "في نفس اللحظة" (threading.Barrier
        عشان الاتنين يبدأوا معًا فعليًا) محمّلين على نفس الفوليو — قفل
        الفوليو (blocking، مش NOWAIT) لازم يسلسلهم بدل ما يخلي واحد يفقد
        تحديث التاني (lost update). النتيجة المتوقعة: الاتنين ينجحوا،
        وfolio.total يبقى مجموع الشحنتين بالظبط."""
        from app.modules.dining import services

        setup_db = Session()
        branch = make_branch(setup_db)
        outlet = make_outlet(setup_db, branch)
        make_finance_accounts(setup_db, branch)
        item1 = make_item(setup_db, branch, outlet, price=Decimal("50.00"))
        item2 = make_item(setup_db, branch, outlet, price=Decimal("75.00"))
        folio = make_folio(setup_db, branch)
        order1 = make_paid_ready_order(setup_db, branch, outlet, item1)
        order2 = make_paid_ready_order(setup_db, branch, outlet, item2)
        folio_id, order1_id, order2_id = folio.id, order1.id, order2.id
        expected_total = order1.total + order2.total
        setup_db.close()

        barrier = threading.Barrier(2)
        results = {}
        errors = {}

        def _pay(order_id, key):
            db = Session()
            try:
                barrier.wait(timeout=5)
                results[key] = services.update_order_status(
                    db, order_id, "paid", charge_to_room_id=None,
                )
            except Exception as exc:  # noqa: BLE001 — نلتقط أي استثناء للفحص بعدين
                errors[key] = exc
            finally:
                db.close()

        # نحدّد folio_id مباشرة على الطلبين بدل charge_to_room_id (مفيش
        # حجز/غرفة حقيقية هنا — بنختبر قفل الفوليو نفسه بس).
        prep_db = Session()
        from app.modules.dining.models import DiningOrder
        prep_db.query(DiningOrder).filter(DiningOrder.id == order1_id).update({"folio_id": folio_id})
        prep_db.query(DiningOrder).filter(DiningOrder.id == order2_id).update({"folio_id": folio_id})
        prep_db.commit()
        prep_db.close()

        t1 = threading.Thread(target=_pay, args=(order1_id, "o1"))
        t2 = threading.Thread(target=_pay, args=(order2_id, "o2"))
        t1.start(); t2.start()
        t1.join(timeout=15); t2.join(timeout=15)
        assert not t1.is_alive() and not t2.is_alive(), (
            "thread واحد على الأقل لسه شغال بعد المهلة (hang حقيقي) — "
            f"o1 done={not t1.is_alive()}, o2 done={not t2.is_alive()}"
        )

        assert not errors, f"معاملة دفع فشلت غير متوقّع تحت التزامن: {errors}"
        assert "o1" in results and "o2" in results, (
            f"نتيجة مفقودة من thread — results={list(results.keys())}, errors={errors}"
        )
        assert results["o1"].status == "paid"
        assert results["o2"].status == "paid"

        verify_db = Session()
        try:
            from app.modules.finance import crud as finance_crud
            from app.modules.finance.models import FolioCharge
            folio_after = finance_crud.get_folio(verify_db, folio_id)
            assert folio_after is not None
            assert folio_after.total == expected_total, (
                f"folio.total = {folio_after.total}, متوقع {expected_total} — "
                "احتمال lost update لأن قفل الفوليو ماسلسلش الشحنتين صح"
            )
            charges = verify_db.query(FolioCharge).filter_by(folio_id=folio_id).count()
            assert charges == 2
        finally:
            verify_db.close()


class TestAddChargeVsSettleRace:
    def test_concurrent_charge_and_settle_never_produce_closed_folio_with_missed_charge(self, Session):
        """سباق حقيقي بين إضافة شحنة (دفع طلب دايننج جديد) وتسوية نفس
        الفوليو — النتيجة المضمونة الوحيدة المقبولة: إما (أ) الشحنة نجحت
        على فوليو لسه مفتوح، أو (ب) الشحنة اترفضت (FolioClosedError) على
        فوليو اتقفل قبلها. **الممنوع تمامًا**: فوليو مقفول من غير الشحنة
        الجديدة فيه، أو الشحنة نجحت على فوليو اترفض بعد كده بصمت."""
        from app.modules.dining import services as dining_services
        from app.modules.finance import services as finance_services

        setup_db = Session()
        branch = make_branch(setup_db)
        outlet = make_outlet(setup_db, branch)
        make_finance_accounts(setup_db, branch)
        item = make_item(setup_db, branch, outlet, price=Decimal("40.00"))
        folio = make_folio(setup_db, branch)
        order = make_paid_ready_order(setup_db, branch, outlet, item, folio_id=folio.id)
        folio_id, order_id = folio.id, order.id
        setup_db.close()

        barrier = threading.Barrier(2)
        outcome = {}

        def _pay_order():
            db = Session()
            try:
                barrier.wait(timeout=5)
                outcome["charge"] = ("ok", dining_services.update_order_status(db, order_id, "paid"))
            except Exception as exc:  # noqa: BLE001
                outcome["charge"] = ("error", exc)
            finally:
                db.close()

        def _settle():
            db = Session()
            try:
                barrier.wait(timeout=5)
                outcome["settle"] = ("ok", finance_services.settle_folio(db, folio_id))
            except Exception as exc:  # noqa: BLE001
                outcome["settle"] = ("error", exc)
            finally:
                db.close()

        t1 = threading.Thread(target=_pay_order)
        t2 = threading.Thread(target=_settle)
        t1.start(); t2.start()
        t1.join(timeout=15); t2.join(timeout=15)
        assert not t1.is_alive() and not t2.is_alive(), (
            "thread واحد على الأقل لسه شغال بعد المهلة (hang حقيقي) — "
            f"charge done={not t1.is_alive()}, settle done={not t2.is_alive()}"
        )
        assert "charge" in outcome and "settle" in outcome, (
            f"نتيجة مفقودة من thread — outcome keys={list(outcome.keys())}"
        )

        verify_db = Session()
        try:
            from app.modules.finance import crud as finance_crud
            folio_after = finance_crud.get_folio(verify_db, folio_id)
            assert folio_after is not None
            charge_kind, charge_result = outcome["charge"]

            if charge_kind == "ok":
                # الشحنة نجحت — لازم تكون اتحسبت في التسوية (لو التسوية
                # نجحت هي كمان) أو الفوليو لسه مفتوح (لو التسوية فشلت لأن
                # الشحنة سبقتها والفوليو كان لسه من غير charges مستوّاة).
                settle_kind, _settle_result = outcome["settle"]
                if settle_kind == "ok":
                    assert folio_after.status == "closed"
                    # كل الشحنات (بما فيها الجديدة) لازم تبقى settled — مفيش
                    # شحنة "ضاعت" من التسوية.
                    unsettled = [c for c in folio_after.charges if not c.is_settled]
                    assert not unsettled, (
                        f"فوليو اتقفل وفيه {len(unsettled)} شحنة لسه مش "
                        "متسوّاة — بالظبط الباج اللي قفل الفوليو المفروض يمنعه"
                    )
                else:
                    # التسوية فشلت (رفضت لأي سبب) — الفوليو لازم يفضل مفتوح
                    assert folio_after.status == "open"
            else:
                # الشحنة اترفضت — لازم يكون السبب فوليو مقفول فعليًا (مش
                # خطأ تاني غير متوقع)، والفوليو المقفول ده معندوش أي أثر
                # للشحنة اللي اترفضت (مفيش تسجيل جزئي).
                assert isinstance(charge_result, finance_services.FolioClosedError), (
                    f"الشحنة اترفضت بسبب غير متوقع: {charge_result!r}"
                )
                assert folio_after.status == "closed"
        finally:
            verify_db.close()


class TestProductLockContentionRealLock:
    def test_concurrent_inventory_movement_gets_busy_while_lock_held(self, Session):
        from app.modules.inventory import crud as inventory_crud
        from app.modules.inventory import services as inventory_services
        from app.modules.inventory.schemas import StockMovementCreate

        setup_db = Session()
        branch = make_branch(setup_db)
        product = make_product(setup_db, branch)
        branch_id, product_id, warehouse_id = branch.id, product.id, product.warehouse_id
        setup_db.close()

        lock_acquired = threading.Event()
        release_lock = threading.Event()
        holder_db = Session()

        def _hold_lock():
            inventory_crud.lock_product_for_update(holder_db, product_id)
            lock_acquired.set()
            release_lock.wait(timeout=10)
            holder_db.rollback()

        holder_thread = threading.Thread(target=_hold_lock)
        holder_thread.start()
        assert lock_acquired.wait(timeout=5), "Thread A ماسكتش قفل المنتج خلال المهلة"

        attacker_db = Session()
        try:
            with pytest.raises(inventory_services.InventoryConcurrencyError):
                inventory_services.record_movement(
                    attacker_db,
                    StockMovementCreate(
                        branch_id=branch_id, product_id=product_id, warehouse_id=warehouse_id,
                        movement_type="consumption", quantity=Decimal("-1"), unit_cost=Decimal("10"),
                        moved_at=datetime.utcnow(),
                    ),
                    moved_by=1,
                )
        finally:
            release_lock.set()
            holder_thread.join(timeout=5)
            assert not holder_thread.is_alive(), (
                "Thread A لسه شغال بعد المهلة (hang حقيقي) — القفل ممكن يكون "
                "لسه ممسوك فعليًا"
            )
            holder_db.close()
            attacker_db.rollback()
            attacker_db.close()

    def test_consume_stock_itself_gets_busy_and_session_stays_usable(self, Session):
        """مراجعة Codex الثالثة (Gate 1B): consume_stock's أول قفل (على
        cost_price الطازة) كان بيرفع InventoryConcurrencyError من غير
        db.rollback() — على PostgreSQL حقيقي ده بيسيب الـtransaction
        "aborted"، وأي استخدام تاني لنفس الـsession بيفشل بـ
        InFailedSqlTransaction لحد rollback حقيقي. هنا بنختبر consume_stock
        نفسها (مش record_movement بس) تحت قفل حقيقي، ونثبت إن الـsession
        تفضل قابلة للاستخدام فعليًا بعد كده — من غير أي rollback يدوي من
        التست نفسه، غير اللي جوه consume_stock ذاتها."""
        from app.modules.inventory import crud as inventory_crud
        from app.modules.inventory import services as inventory_services

        setup_db = Session()
        branch = make_branch(setup_db)
        product = make_product(setup_db, branch)
        branch_id, product_id, warehouse_id = branch.id, product.id, product.warehouse_id
        setup_db.close()

        lock_acquired = threading.Event()
        release_lock = threading.Event()
        holder_db = Session()

        def _hold_lock():
            inventory_crud.lock_product_for_update(holder_db, product_id)
            lock_acquired.set()
            release_lock.wait(timeout=10)
            holder_db.rollback()

        holder_thread = threading.Thread(target=_hold_lock)
        holder_thread.start()
        assert lock_acquired.wait(timeout=5), "Thread A ماسكتش قفل المنتج خلال المهلة"

        attacker_db = Session()
        try:
            with pytest.raises(inventory_services.InventoryConcurrencyError):
                inventory_services.consume_stock(
                    attacker_db, branch_id=branch_id, product_id=product_id,
                    warehouse_id=warehouse_id, quantity=Decimal("1"), allow_negative=True,
                )

            # الـsession لازم تفضل قابلة للاستخدام فعليًا فورًا — بدون أي
            # rollback/close يدوي من التست هنا — لإثبات إن consume_stock
            # نفسها عملت rollback الداخلي الصح، مش إننا بنعالج الأثر من برّه.
            fresh_read = inventory_crud.get_product(attacker_db, product_id)
            assert fresh_read is not None
            assert fresh_read.id == product_id
        finally:
            release_lock.set()
            holder_thread.join(timeout=5)
            assert not holder_thread.is_alive(), "Thread A لسه شغال بعد المهلة (hang حقيقي)"
            holder_db.close()
            attacker_db.rollback()
            attacker_db.close()
