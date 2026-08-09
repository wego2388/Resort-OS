"""
tests/test_timeshare_leasing_concurrency.py
Postgres-only real-concurrency proof for the 2026-07-28 lost-update fix in
timeshare.services.pay_installment/pay_maintenance_due and
leasing.services.pay_payment: these previously read paid_amount, computed
paid_amount + req.paid_amount in Python, and wrote it back with NO row lock
at all (not even a missing-.populate_existing() case — no with_for_update()
whatsoever). Two concurrent payments on the same installment/payment could
silently lose one payment's money with no error (verified live during the
audit that found this bug). Row-level locking only actually enforces on a
real Postgres engine (SQLite ignores with_for_update — CLAUDE.md §13 ⓫), so
this proves the real thing with overlapping transactions on separate
threads/connections.

Mirrors tests/test_gate4_concurrency.py's pattern exactly: a disposable
per-test throwaway database, tables built via Base.metadata.create_all(),
dropped at the end regardless of outcome.

Usage — set an admin Postgres DSN before running:

    DINING_CONCURRENCY_TEST_ADMIN_URL=postgresql+psycopg://postgres:resort_dev_pass@localhost:5436/postgres \\
        pytest tests/test_timeshare_leasing_concurrency.py -v

Skips automatically (does not fail) when that env var is unset.
"""
from __future__ import annotations

import os
import threading
import uuid
from datetime import date
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

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
    db_name = f"resort_os_ts_lease_conctest_{uuid.uuid4().hex[:10]}"
    base_url = DINING_CONCURRENCY_TEST_ADMIN_URL.rsplit("/", 1)[0]
    target_url = f"{base_url}/{db_name}"

    with admin_engine.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
    admin_engine.dispose()

    from app.core.database import Base
    import app.core.kernel.models.user      # noqa: F401
    import app.modules.core.models          # noqa: F401
    import app.modules.finance.models       # noqa: F401
    import app.modules.timeshare.models     # noqa: F401
    import app.modules.leasing.models       # noqa: F401

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


def make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(name="Concurrency Test Branch", name_ar="فرع اختبار التزامن",
               code=f"CONC-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_timeshare_contract_with_installment(db, branch, *, installment_amount=Decimal("10000")):
    from app.modules.timeshare.models import TimeshareContract, TimeshareInstallment
    contract = TimeshareContract(
        branch_id=branch.id, contract_number=f"TS-{uuid.uuid4().hex[:10].upper()}",
        customer_name="عميل اختبار التزامن", room_type="Studio",
        nights_per_year=7, season="high",
        total_value=Decimal("120000"), down_payment=Decimal("12000"),
        installments=12, installment_period=1,
        first_installment_date=date(2026, 1, 1),
        status="active", start_date=date(2026, 1, 1),
    )
    db.add(contract)
    db.flush()
    inst = TimeshareInstallment(
        contract_id=contract.id, installment_no=1, due_date=date(2026, 1, 1),
        amount=installment_amount, paid_amount=Decimal("0"), status="pending",
    )
    db.add(inst)
    db.commit()
    db.refresh(contract)
    db.refresh(inst)
    return contract, inst


def make_lease_contract_with_payment(db, branch, *, payment_amount=Decimal("5000")):
    from app.modules.leasing.models import LeaseContract, LeasePayment
    contract = LeaseContract(
        branch_id=branch.id, contract_number=f"LC-{uuid.uuid4().hex[:10].upper()}",
        tenant_name="مستأجر اختبار التزامن", unit_description="محل رقم اختبار",
        start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        base_rent=payment_amount, status="active",
    )
    db.add(contract)
    db.flush()
    payment = LeasePayment(
        contract_id=contract.id, due_date=date(2026, 1, 1),
        amount=payment_amount, paid_amount=Decimal("0"), status="pending",
    )
    db.add(payment)
    db.commit()
    db.refresh(contract)
    db.refresh(payment)
    return contract, payment


class TestInstallmentPaymentRace:
    def test_two_concurrent_installment_payments_no_money_lost(self, Session):
        """قسط قيمته 10,000، تحصيلان متزامنان 6,000 لكل واحد (الاتنين أقل من
        المتبقي وقت القراءة، فمفيش أي واحد هيترفض بسبب تجاوز الحد). قبل
        الإصلاح: التحصيل التاني كان بيمسح أثر الأول بصمت (paid_amount نهائي
        = 6,000 بدل 12,000، أو حتى نتيجة غير متسقة). بعد الإصلاح: القفل
        NOWAIT يخلي واحد بس ينجح فورًا والتاني يترفض بـ409 واضح — فلوس محصّلة
        فعليًا ميختفيش، وaudit trail واضح إن التاني محتاج إعادة محاولة."""
        from app.modules.timeshare import services as ts_services
        from app.modules.timeshare.schemas import PayInstallmentRequest
        from app.modules.timeshare.models import TimeshareInstallment

        setup_db = Session()
        branch = make_branch(setup_db)
        _, inst = make_timeshare_contract_with_installment(setup_db, branch, installment_amount=Decimal("10000"))
        inst_id = inst.id
        setup_db.close()

        barrier = threading.Barrier(2)
        outcome = {}

        def _pay(tag):
            db = Session()
            try:
                barrier.wait(timeout=5)
                res = ts_services.pay_installment(
                    db, inst_id, PayInstallmentRequest(paid_amount=Decimal("6000"), payment_method="cash"),
                )
                outcome[tag] = ("ok", res.paid_amount)
            except Exception as exc:  # noqa: BLE001
                outcome[tag] = ("error", exc)
            finally:
                db.close()

        t1 = threading.Thread(target=_pay, args=("a",))
        t2 = threading.Thread(target=_pay, args=("b",))
        t1.start(); t2.start()
        t1.join(timeout=15); t2.join(timeout=15)
        assert not t1.is_alive() and not t2.is_alive()

        oks = [v for v in outcome.values() if v[0] == "ok"]
        errors = [v for v in outcome.values() if v[0] == "error"]
        assert len(oks) == 1, f"لازم تحصيل واحد بس ينجح — {outcome}"
        assert len(errors) == 1, f"التاني لازم يترفض بوضوح مش يتجاهل صامت — {outcome}"
        # النوع المتوقع الأكثر شيوعًا PaymentConflictError (قفل NOWAIT مشغول
        # فعليًا وقت المحاولة)، لكن لو التوقيت خلّى التحصيل التاني يبدأ بعد
        # ما الأول عمل commit وحرّر القفل، الثاني هيلاقي paid_amount المحدّث
        # فعليًا (بفضل .populate_existing()) ويترفض بـValueError "أكبر من
        # المتبقي" — النتيجتين سليمتين ماليًا (مفيش فلوس ضاعت)، الفرق بس
        # توقيت الـthreads، مش سلوك الكود.
        assert type(errors[0][1]).__name__ in ("PaymentConflictError", "ValueError"), (
            f"لازم رفض واضح (قفل مشغول أو مبلغ أكبر من المتبقي)، مش استثناء عشوائي — {outcome}"
        )

        verify_db = Session()
        try:
            fresh = verify_db.query(TimeshareInstallment).filter_by(id=inst_id).first()
            # الأهم: التحصيل اللي نجح فعلاً ظاهر بالكامل في paid_amount —
            # مفيش فلوس اتحصّلت واختفت بصمت (الباج الأصلي).
            assert fresh.paid_amount == Decimal("6000.00"), (
                f"فلوس محصّلة فعليًا لازم متختفيش من غير أي خطأ — paid_amount={fresh.paid_amount}"
            )
        finally:
            verify_db.close()


class TestLeasePaymentRace:
    def test_two_concurrent_lease_payments_no_money_lost(self, Session):
        """مرآة TestInstallmentPaymentRace بس على leasing.services.pay_payment."""
        from app.modules.leasing import services as lease_services
        from app.modules.leasing.schemas import PayLeaseRequest
        from app.modules.leasing.models import LeasePayment

        setup_db = Session()
        branch = make_branch(setup_db)
        _, payment = make_lease_contract_with_payment(setup_db, branch, payment_amount=Decimal("5000"))
        payment_id = payment.id
        setup_db.close()

        barrier = threading.Barrier(2)
        outcome = {}

        def _pay(tag):
            db = Session()
            try:
                barrier.wait(timeout=5)
                res = lease_services.pay_payment(
                    db, payment_id, PayLeaseRequest(paid_amount=Decimal("3000"), payment_method="cash"),
                )
                outcome[tag] = ("ok", res.paid_amount)
            except Exception as exc:  # noqa: BLE001
                outcome[tag] = ("error", exc)
            finally:
                db.close()

        t1 = threading.Thread(target=_pay, args=("a",))
        t2 = threading.Thread(target=_pay, args=("b",))
        t1.start(); t2.start()
        t1.join(timeout=15); t2.join(timeout=15)
        assert not t1.is_alive() and not t2.is_alive()

        oks = [v for v in outcome.values() if v[0] == "ok"]
        errors = [v for v in outcome.values() if v[0] == "error"]
        assert len(oks) == 1, f"لازم تحصيل واحد بس ينجح — {outcome}"
        assert len(errors) == 1, f"التاني لازم يترفض بوضوح مش يتجاهل صامت — {outcome}"
        # النوع المتوقع الأكثر شيوعًا PaymentConflictError (قفل NOWAIT مشغول
        # فعليًا وقت المحاولة)، لكن لو التوقيت خلّى التحصيل التاني يبدأ بعد
        # ما الأول عمل commit وحرّر القفل، الثاني هيلاقي paid_amount المحدّث
        # فعليًا (بفضل .populate_existing()) ويترفض بـValueError "أكبر من
        # المتبقي" — النتيجتين سليمتين ماليًا (مفيش فلوس ضاعت)، الفرق بس
        # توقيت الـthreads، مش سلوك الكود.
        assert type(errors[0][1]).__name__ in ("PaymentConflictError", "ValueError"), (
            f"لازم رفض واضح (قفل مشغول أو مبلغ أكبر من المتبقي)، مش استثناء عشوائي — {outcome}"
        )

        verify_db = Session()
        try:
            fresh = verify_db.query(LeasePayment).filter_by(id=payment_id).first()
            assert fresh.paid_amount == Decimal("3000.00"), (
                f"فلوس محصّلة فعليًا لازم متختفيش من غير أي خطأ — paid_amount={fresh.paid_amount}"
            )
        finally:
            verify_db.close()
