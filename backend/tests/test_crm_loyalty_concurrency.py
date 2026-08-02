"""
tests/test_crm_loyalty_concurrency.py
Postgres-only real-concurrency proof for the loyalty-points redeem lock
fix (2026-08-02). Row-level locking (SELECT ... FOR UPDATE NOWAIT on
LoyaltyAccount) only actually enforces under a real Postgres engine —
SQLite ignores with_for_update entirely (CLAUDE.md §13 bullet ⓫), so the
regular SQLite-backed test suite can only prove the balance-check *logic*,
not genuine lock contention against a double-redeem. This file proves the
real thing, with real overlapping transactions on separate threads/
connections against a live Postgres.

Mirrors tests/test_dining_paid_concurrency.py's pattern exactly: an admin
connection creates a disposable, per-test throwaway database (never the
shared dev `resort_os` database), tables are built directly via
Base.metadata.create_all() (no Alembic needed — we're not testing
migration correctness, just row locks), and the database is dropped at
the end regardless of outcome.

Usage — set an admin Postgres DSN before running:

    CRM_LOYALTY_CONCURRENCY_TEST_ADMIN_URL=postgresql+psycopg://postgres:resort_dev_pass@localhost:5436/postgres \\
        pytest tests/test_crm_loyalty_concurrency.py -v

Skips automatically (does not fail, does not affect `pytest tests/`'s
100%-green requirement) when that env var is unset.
"""
from __future__ import annotations

import os
import threading
import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

CRM_LOYALTY_CONCURRENCY_TEST_ADMIN_URL = os.environ.get("CRM_LOYALTY_CONCURRENCY_TEST_ADMIN_URL")

pytestmark = pytest.mark.skipif(
    not CRM_LOYALTY_CONCURRENCY_TEST_ADMIN_URL,
    reason=(
        "Postgres-only real-concurrency test — set CRM_LOYALTY_CONCURRENCY_TEST_ADMIN_URL "
        "(admin DSN, e.g. postgresql+psycopg://postgres:pass@localhost:5436/postgres) "
        "to run. Skipped by default; does not affect `pytest tests/`."
    ),
)


@pytest.fixture
def pg_engine():
    admin_engine = sa.create_engine(CRM_LOYALTY_CONCURRENCY_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT")
    db_name = f"resort_os_crm_loyalty_conctest_{uuid.uuid4().hex[:10]}"
    base_url = CRM_LOYALTY_CONCURRENCY_TEST_ADMIN_URL.rsplit("/", 1)[0]
    target_url = f"{base_url}/{db_name}"

    with admin_engine.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
    admin_engine.dispose()

    from app.core.database import Base
    import app.core.kernel.models.user      # noqa: F401
    import app.modules.core.models          # noqa: F401
    import app.modules.crm.models           # noqa: F401

    engine = sa.create_engine(target_url, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)

    try:
        yield engine
    finally:
        engine.dispose()
        cleanup_engine = sa.create_engine(CRM_LOYALTY_CONCURRENCY_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT")
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


def make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(name="Loyalty Concurrency Test Branch", name_ar="فرع اختبار تزامن النقاط",
               code=f"LOYCONC-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_customer(db, branch):
    from app.modules.crm.models import Customer
    c = Customer(branch_id=branch.id, full_name="عميل اختبار تزامن النقاط",
                  phone=f"010{uuid.uuid4().int % 100000000:08d}")
    db.add(c)
    db.commit()
    return c


def make_loyalty_program(db, branch):
    from app.modules.crm.models import LoyaltyProgram
    p = LoyaltyProgram(
        branch_id=branch.id, is_active=True,
        earn_rate=Decimal("10"), redeem_rate=Decimal("0.10"),
        min_redeem=10, max_redeem_pct=Decimal("100"),
    )
    db.add(p)
    db.commit()
    return p


def make_loyalty_account(db, program, customer, points=100):
    from app.modules.crm.models import LoyaltyAccount
    acc = LoyaltyAccount(
        program_id=program.id, branch_id=program.branch_id, customer_id=customer.id,
        points=points, total_earned=points, total_redeemed=0,
    )
    db.add(acc)
    db.commit()
    return acc


class TestLoyaltyRedeemRealLock:
    def test_second_concurrent_redeem_gets_409_while_first_holds_lock(self, Session):
        """باج حقيقي اتصلح (2026-08-02): قراءة غير مقفولة لرصيد النقاط كانت
        بتسمح بنفس الرصيد يترد مرتين من طلبين متزامنين — كل واحد بيقرا
        القيمة القديمة قبل ما التاني يعمل commit، فيتقبل الاتنين ويتخصم
        نصيب واحد بس فعليًا (lost update): خصم حقيقي مزدوج على فاتورتين،
        بينما دفتر النقاط بيوريه استرداد واحد بس. Thread A تمسك قفل صف
        الحساب فعليًا (SELECT FOR UPDATE NOWAIT) وتفضل ماسكاه، وThread B
        (المعاملة الحقيقية عبر services.redeem_loyalty_points) بتحاول
        تسترد من نفس الحساب في نفس اللحظة — لازم ترفض فورًا بـ
        LoyaltyConcurrencyError (409)، مش تنتظر ولا تنجح."""
        from app.modules.crm import crud, services
        from app.modules.crm.schemas import LoyaltyRedeemRequest

        setup_db = Session()
        branch = make_branch(setup_db)
        customer = make_customer(setup_db, branch)
        program = make_loyalty_program(setup_db, branch)
        make_loyalty_account(setup_db, program, customer, points=100)
        branch_id, customer_id = branch.id, customer.id
        setup_db.close()

        lock_acquired = threading.Event()
        release_lock = threading.Event()
        holder_db = Session()

        def _hold_lock():
            crud.get_loyalty_account_by_customer_for_update(holder_db, branch_id, customer_id)
            lock_acquired.set()
            release_lock.wait(timeout=10)
            holder_db.rollback()

        holder_thread = threading.Thread(target=_hold_lock)
        holder_thread.start()
        assert lock_acquired.wait(timeout=5), "Thread A ماسكتش القفل خلال المهلة"

        attacker_db = Session()
        try:
            with pytest.raises(services.LoyaltyConcurrencyError):
                services.redeem_loyalty_points(
                    attacker_db,
                    LoyaltyRedeemRequest(branch_id=branch_id, customer_id=customer_id, points=80),
                    created_by=1,
                )
        finally:
            attacker_db.rollback()
            attacker_db.close()

        release_lock.set()
        holder_thread.join(timeout=5)
        assert not holder_thread.is_alive(), (
            "Thread A لسه شغال بعد المهلة (hang حقيقي) — النتيجة اللي بعد "
            "كده (فتح جلسة جديدة، استرداد حقيقي) مش موثوقة لو القفل لسه "
            "ممسوك فعليًا في thread معلّق"
        )
        holder_db.close()

        # بعد ما القفل يتحرر، نفس الحساب لازم يتقدر يسترد منه صح، والرصيد
        # يفضل صحيح (مفيش أي أثر من المحاولة اللي اترفضت).
        final_db = Session()
        try:
            result = services.redeem_loyalty_points(
                final_db,
                LoyaltyRedeemRequest(branch_id=branch_id, customer_id=customer_id, points=80),
                created_by=1,
            )
            assert result.new_balance == 20
        finally:
            final_db.close()

    def test_two_real_concurrent_redeems_never_double_spend(self, Session):
        """نفس السيناريو، لكن بمعاملتين حقيقيتين متسابقتين فعليًا (مش
        thread واحد ماسك قفل يدوي) — الرصيد 100، كل طلب بيحاول يسترد 80.
        لازم واحد بس ينجح (النتيجة الصحيحة رياضيًا: 100-80=20 لا تسمح
        بخصم تاني)، والتاني يترفض (إما ValueError برصيد غير كافٍ لو
        اتنفّذ بعد الأول، أو LoyaltyConcurrencyError لو اتسابق حرفيًا) —
        أي نتيجة تالتة (الاتنين نجحوا، أو الرصيد بقى سالب أو 100 زي ما هو)
        تعني lost update حقيقي."""
        from app.modules.crm import services
        from app.modules.crm.schemas import LoyaltyRedeemRequest

        setup_db = Session()
        branch = make_branch(setup_db)
        customer = make_customer(setup_db, branch)
        program = make_loyalty_program(setup_db, branch)
        make_loyalty_account(setup_db, program, customer, points=100)
        branch_id, customer_id = branch.id, customer.id
        setup_db.close()

        results: list[tuple[str, object]] = []
        start_barrier = threading.Barrier(2)

        def _attempt():
            db = Session()
            try:
                start_barrier.wait(timeout=5)
                r = services.redeem_loyalty_points(
                    db,
                    LoyaltyRedeemRequest(branch_id=branch_id, customer_id=customer_id, points=80),
                    created_by=1,
                )
                results.append(("ok", r.new_balance))
            except Exception as exc:  # noqa: BLE001 — أي استثناء غير متوقع لازم يظهر كنتيجة صريحة، مش يختفي كـ thread crash صامت
                db.rollback()
                results.append(("rejected", exc))
            finally:
                db.close()

        threads = [threading.Thread(target=_attempt) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
            assert not t.is_alive(), "thread علق (hang حقيقي)"

        oks = [r for kind, r in results if kind == "ok"]
        assert len(oks) == 1, f"لازم استرداد واحد بس ينجح، الموجود: {results}"
        assert oks[0] == 20, f"الرصيد النهائي لازم يبقى 20 بالظبط، الموجود {oks[0]}"

        verify_db = Session()
        try:
            from app.modules.crm import crud
            account = crud.get_loyalty_account_by_customer(verify_db, branch_id, customer_id)
            assert account.points == 20, (
                f"الرصيد المخزّن فعليًا لازم يبقى 20 — lost update لو مختلف "
                f"(الموجود: {account.points})"
            )
        finally:
            verify_db.close()
