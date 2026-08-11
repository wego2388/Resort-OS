"""
tests/test_hub_confirm_concurrency.py
Postgres-only real-concurrency proof for the Hub confirmation atomicity
fix (2026-08-11). hub.services.confirm_booking now locks the
HubOnlineBooking row (SELECT ... FOR UPDATE NOWAIT) before creating the
linked PMS booking — SQLite ignores with_for_update entirely (CLAUDE.md
§13 bullet ⓫), so the regular SQLite-backed suite can only prove the
atomicity/rollback logic (see test_api/test_hub.py's
test_forced_failure_after_pms_insert_leaves_no_orphan_booking), not
genuine lock contention between two concurrent confirmation requests for
the same Hub booking. This file proves the real thing against a live
Postgres, mirroring tests/test_crm_loyalty_concurrency.py's pattern.

Usage — set an admin Postgres DSN before running:

    HUB_CONFIRM_CONCURRENCY_TEST_ADMIN_URL=postgresql+psycopg://postgres:resort_dev_pass@localhost:5436/postgres \\
        pytest tests/test_hub_confirm_concurrency.py -v

Skips automatically (does not fail, does not affect `pytest tests/`'s
100%-green requirement) when that env var is unset.
"""
from __future__ import annotations

import os
import threading
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

HUB_CONFIRM_CONCURRENCY_TEST_ADMIN_URL = os.environ.get("HUB_CONFIRM_CONCURRENCY_TEST_ADMIN_URL")

pytestmark = pytest.mark.skipif(
    not HUB_CONFIRM_CONCURRENCY_TEST_ADMIN_URL,
    reason=(
        "Postgres-only real-concurrency test — set HUB_CONFIRM_CONCURRENCY_TEST_ADMIN_URL "
        "(admin DSN, e.g. postgresql+psycopg://postgres:pass@localhost:5436/postgres) "
        "to run. Skipped by default; does not affect `pytest tests/`."
    ),
)


@pytest.fixture
def pg_engine():
    admin_engine = sa.create_engine(HUB_CONFIRM_CONCURRENCY_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT")
    db_name = f"resort_os_hub_confirm_conctest_{uuid.uuid4().hex[:10]}"
    admin_url_obj = sa.engine.make_url(HUB_CONFIRM_CONCURRENCY_TEST_ADMIN_URL)
    target_url = admin_url_obj.set(database=db_name).render_as_string(hide_password=False)

    with admin_engine.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
    admin_engine.dispose()

    from app.core.database import Base
    import app.core.kernel.models.user      # noqa: F401
    import app.modules.core.models          # noqa: F401
    import app.modules.pms.models           # noqa: F401
    import app.modules.hub.models           # noqa: F401
    import app.modules.crm.models           # noqa: F401

    engine = sa.create_engine(target_url, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)

    try:
        yield engine
    finally:
        engine.dispose()
        cleanup_engine = sa.create_engine(HUB_CONFIRM_CONCURRENCY_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT")
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
    b = Branch(name="Hub Confirm Concurrency Branch", name_ar="فرع اختبار تزامن التأكيد",
               code=f"HUBCONC-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_room_type(db, branch):
    from app.modules.pms.models import RoomType
    rt = RoomType(branch_id=branch.id, name="Standard", base_rate=Decimal("500.00"), max_occupancy=2)
    db.add(rt)
    db.commit()
    return rt


def make_room(db, branch, room_type, suffix):
    from app.modules.pms.models import Room
    r = Room(branch_id=branch.id, room_type_id=room_type.id, name=f"R-{suffix}",
             floor=1, status="available")
    db.add(r)
    db.commit()
    return r


def make_hub_booking(db, branch, room_type):
    from app.modules.hub.models import HubOnlineBooking
    b = HubOnlineBooking(
        branch_id=branch.id,
        guest_name="ضيف اختبار تزامن",
        guest_phone="01008000000",
        guests_count=2,
        requested_date=date.today() + timedelta(days=25),
        check_in=date.today() + timedelta(days=25),
        check_out=date.today() + timedelta(days=27),
        room_type_id=room_type.id,
        status="pending",
    )
    db.add(b)
    db.commit()
    return b


class TestHubConfirmationRace:
    def test_two_concurrent_confirms_create_exactly_one_pms_booking(self, Session):
        """نفس الحجز الإلكتروني، طلبي تأكيد متزامنين حقيقيين — مع توفر
        غرفتين من نفس النوع. لازم واحد بس ينجح (يقفل صف HubOnlineBooking
        أول، ينشئ حجز PMS، يحدّث الحالة)، والتاني يترفض فورًا
        (HubConfirmationConcurrencyError، NOWAIT مش انتظار) — مش الاتنين
        ينجحوا بحجزين PMS منفصلين لنفس طلب Hub واحد."""
        from app.modules.hub import services
        from app.modules.hub.services import HubConfirmationConcurrencyError

        setup_db = Session()
        branch = make_branch(setup_db)
        room_type = make_room_type(setup_db, branch)
        make_room(setup_db, branch, room_type, "A")
        make_room(setup_db, branch, room_type, "B")
        hub_booking = make_hub_booking(setup_db, branch, room_type)
        hub_booking_id = hub_booking.id
        branch_id = branch.id
        setup_db.close()

        results: list[tuple[str, object]] = []
        start_barrier = threading.Barrier(2)

        def _attempt():
            db = Session()
            try:
                start_barrier.wait(timeout=5)
                confirmed = services.confirm_booking(db, hub_booking_id, confirmed_by=1)
                results.append(("ok", confirmed.pms_booking_id))
            except HubConfirmationConcurrencyError as exc:
                db.rollback()
                results.append(("rejected", str(exc)))
            except Exception as exc:  # noqa: BLE001 — أي استثناء غير متوقع لازم يظهر صراحةً
                db.rollback()
                results.append(("error", exc))
            finally:
                db.close()

        threads = [threading.Thread(target=_attempt) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
            assert not t.is_alive(), "thread علق (hang حقيقي — NOWAIT مفروض يرفض فورًا مش ينتظر)"

        oks = [r for kind, r in results if kind == "ok"]
        rejected = [r for kind, r in results if kind == "rejected"]
        assert len(oks) == 1, f"لازم تأكيد واحد بس ينجح، الموجود: {results}"
        assert len(rejected) == 1, f"لازم الطلب التاني يترفض بـHubConfirmationConcurrencyError، الموجود: {results}"
        assert oks[0] is not None, "الحجز الناجح لازم يكون مربوط بحجز PMS حقيقي"

        verify_db = Session()
        try:
            from app.modules.pms.models import Booking as PMSBooking
            from app.modules.hub.models import HubOnlineBooking
            pms_bookings = (
                verify_db.query(PMSBooking).filter(PMSBooking.branch_id == branch_id).all()
            )
            assert len(pms_bookings) == 1, (
                f"لازم حجز PMS واحد بس اتنشأ، مش حجزين منفصلين لنفس طلب Hub: "
                f"{[b.id for b in pms_bookings]}"
            )
            refreshed = verify_db.get(HubOnlineBooking, hub_booking_id)
            assert refreshed.status == "confirmed"
            assert refreshed.pms_booking_id == pms_bookings[0].id
        finally:
            verify_db.close()
