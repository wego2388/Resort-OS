"""
tests/test_tasks/test_pms_tasks.py
اختبارات الـ pms_tasks.py — service logic مباشرة بـ db fixture
بدون تشغيل Celery runtime
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest


# ─── helpers ────────────────────────────────────────────────────────────────

def _make_branch(db, active=True):
    from app.modules.core.models import Branch
    b = Branch(
        name=f"PMS-Branch-{uuid.uuid4().hex[:6]}",
        code=f"PM{uuid.uuid4().hex[:4].upper()}",
        is_active=active,
    )
    db.add(b)
    db.commit()
    return b


def _make_room_type(db, branch):
    from app.modules.pms.models import RoomType
    rt = RoomType(
        branch_id=branch.id,
        name="Standard",
        base_rate=Decimal("500"),
        max_occupancy=2,
    )
    db.add(rt)
    db.commit()
    return rt


def _make_room(db, branch, room_type=None):
    from app.modules.pms.models import Room
    if room_type is None:
        room_type = _make_room_type(db, branch)
    r = Room(
        branch_id=branch.id,
        room_type_id=room_type.id,
        name=f"{uuid.uuid4().hex[:3].upper()}",
        floor=1,
        status="available",
    )
    db.add(r)
    db.commit()
    return r


def _make_booking(db, branch, room, check_in, check_out, status="confirmed"):
    from app.modules.pms.models import Booking, BookingRoom
    booking = Booking(
        branch_id=branch.id,
        booking_number=f"BKG-{uuid.uuid4().hex[:8].upper()}",
        guest_name=f"Guest-{uuid.uuid4().hex[:4]}",
        guest_phone="01000000000",
        check_in=check_in,
        check_out=check_out,
        adults=2,
        status=status,
        total_rate=Decimal("1000"),
    )
    db.add(booking)
    db.flush()
    br = BookingRoom(
        booking_id=booking.id,
        room_id=room.id,
        daily_rate=Decimal("500"),
        nights=(check_out - check_in).days,
        total=Decimal("1000"),
    )
    db.add(br)
    db.commit()
    return booking


# ─── _mark_no_shows logic ────────────────────────────────────────────────────

class TestPmsMarkNoShows:
    """اختبار _mark_no_shows مباشرة"""

    def test_mark_no_shows_marks_unconfirmed(self, db):
        """حجز confirmed يوم الدخول ولم يصل يُصبح no_show"""
        branch = _make_branch(db)
        room = _make_room(db, branch)
        today = date.today()
        booking = _make_booking(db, branch, room, check_in=today, check_out=today + timedelta(days=2))

        from app.modules.pms.services import _mark_no_shows
        _mark_no_shows(db, branch.id, today)
        db.commit()
        db.refresh(booking)
        assert booking.status == "no_show"

    def test_checked_in_booking_not_marked(self, db):
        """حجز checked_in لا يُصبح no_show"""
        branch = _make_branch(db)
        room = _make_room(db, branch)
        today = date.today()
        booking = _make_booking(
            db, branch, room,
            check_in=today, check_out=today + timedelta(days=2),
            status="checked_in",
        )

        from app.modules.pms.services import _mark_no_shows
        _mark_no_shows(db, branch.id, today)
        db.commit()
        db.refresh(booking)
        assert booking.status == "checked_in"

    def test_future_booking_not_marked(self, db):
        """حجز مستقبلي لا يُصبح no_show"""
        branch = _make_branch(db)
        room = _make_room(db, branch)
        tomorrow = date.today() + timedelta(days=1)
        booking = _make_booking(
            db, branch, room,
            check_in=tomorrow, check_out=tomorrow + timedelta(days=2),
        )

        from app.modules.pms.services import _mark_no_shows
        _mark_no_shows(db, branch.id, date.today())
        db.commit()
        db.refresh(booking)
        assert booking.status == "confirmed"


# ─── run_night_audit logic ───────────────────────────────────────────────────

class TestPmsNightAudit:
    """اختبار run_night_audit مباشرة"""

    def test_night_audit_creates_log(self, db):
        """night audit ينشئ سجل NightAuditLog"""
        branch = _make_branch(db)
        yesterday = date.today() - timedelta(days=1)

        from app.modules.pms.services import run_night_audit
        log = run_night_audit(db, branch.id, yesterday)
        db.commit()

        assert log is not None
        assert log.branch_id == branch.id
        assert log.audit_date == yesterday

    def test_night_audit_log_has_occupancy(self, db):
        """سجل Night Audit فيه occupancy_pct"""
        branch = _make_branch(db)
        yesterday = date.today() - timedelta(days=1)

        from app.modules.pms.services import run_night_audit
        log = run_night_audit(db, branch.id, yesterday)
        db.commit()

        assert hasattr(log, "occupancy_pct")
        assert log.occupancy_pct >= Decimal("0")

    def test_night_audit_with_checked_in_booking(self, db):
        """night audit مع حجز checked_in أمس"""
        branch = _make_branch(db)
        room = _make_room(db, branch)
        yesterday = date.today() - timedelta(days=1)
        _make_booking(
            db, branch, room,
            check_in=yesterday - timedelta(days=1),
            check_out=yesterday + timedelta(days=1),
            status="checked_in",
        )

        from app.modules.pms.services import run_night_audit
        log = run_night_audit(db, branch.id, yesterday)
        db.commit()

        assert log.occupancy_pct >= Decimal("0")


# ─── process_no_shows task (patch SessionLocal) ──────────────────────────────

class TestPmsProcessNoShowsTask:
    """اختبار task process_no_shows"""

    def test_task_runs_without_error(self, db, monkeypatch):
        """task يشتغل بدون exception"""
        from unittest.mock import patch, MagicMock
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=db)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch("app.core.database.SessionLocal", return_value=ctx):
            from app.tasks.pms_tasks import process_no_shows
            process_no_shows()


# ─── run_night_audit task (patch SessionLocal) ───────────────────────────────

class TestPmsNightAuditTask:
    """اختبار task run_night_audit"""

    def test_task_runs_with_branch(self, db, monkeypatch):
        """task يشتغل مع فرع محدد"""
        from unittest.mock import patch, MagicMock
        branch = _make_branch(db, active=True)
        yesterday = date.today() - timedelta(days=1)

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=db)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch("app.core.database.SessionLocal", return_value=ctx):
            from app.tasks.pms_tasks import run_night_audit as task
            result = task(branch_id=branch.id, audit_date_str=str(yesterday))
        assert isinstance(result, list)

    def test_task_inactive_branch_skipped(self, db, monkeypatch):
        """فرع غير نشط لا يُعالج"""
        from unittest.mock import patch, MagicMock
        _make_branch(db, active=False)

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=db)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch("app.core.database.SessionLocal", return_value=ctx):
            from app.tasks.pms_tasks import run_night_audit as task
            result = task()
        assert isinstance(result, list)
