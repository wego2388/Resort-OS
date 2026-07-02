"""
tests/test_api/test_pms.py
Integration tests for PMS (Property Management System) module.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.modules.pms.schemas import BookingCreate
from app.modules.pms import services, crud


def make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(name="PMS Branch", name_ar="فرع PMS",
               code=f"PMS-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.flush()
    return b


def make_room_type(db, branch):
    from app.modules.pms.models import RoomType
    rt = RoomType(
        branch_id=branch.id,
        name="Standard",
        base_rate=Decimal("500.00"),
        max_occupancy=2,
    )
    db.add(rt)
    db.flush()
    return rt


def make_room(db, branch, room_type):
    from app.modules.pms.models import Room
    r = Room(
        branch_id=branch.id,
        room_type_id=room_type.id,
        name=f"R-{uuid.uuid4().hex[:6].upper()}",
        floor=1,
        status="available",
    )
    db.add(r)
    db.flush()
    return r


def make_booking(db, branch, room):
    # كل booking يستخدم check_in مختلف لضمان عدم تعارض الغرفة
    unique_offset = hash(uuid.uuid4().int) % 30 + 1
    ci = date.today() + timedelta(days=unique_offset)
    data = BookingCreate(
        branch_id=branch.id,
        guest_name="أحمد محمد",
        guest_phone="01000000001",
        check_in=ci,
        check_out=ci + timedelta(days=2),
        adults=2,
        children=0,
        room_ids=[room.id],
    )
    return services.create_booking(db, data)


class TestRoomTypes:

    def test_create_room_type(self, db):
        branch = make_branch(db)
        from app.modules.pms.models import RoomType
        rt = RoomType(
            branch_id=branch.id,
            name="Suite",
            name_ar="جناح",
            base_rate=Decimal("1500.00"),
            max_occupancy=4,
        )
        db.add(rt)
        db.flush()
        assert rt.id is not None
        assert rt.is_active is True

    def test_room_type_has_rooms(self, db):
        branch = make_branch(db)
        rt = make_room_type(db, branch)
        make_room(db, branch, rt)
        db.refresh(rt)
        assert len(rt.rooms) == 1


class TestRoom:

    def test_room_initial_status_available(self, db):
        branch = make_branch(db)
        rt = make_room_type(db, branch)
        room = make_room(db, branch, rt)
        assert room.status == "available"

    def test_update_room_status(self, db):
        branch = make_branch(db)
        rt = make_room_type(db, branch)
        room = make_room(db, branch, rt)
        crud.update_room_status(db, room, "maintenance")
        db.flush()
        assert room.status == "maintenance"

    def test_get_room_not_found(self, db):
        assert crud.get_room(db, 9999) is None


class TestBooking:

    def test_create_booking_generates_number(self, db):
        branch = make_branch(db)
        rt = make_room_type(db, branch)
        room = make_room(db, branch, rt)
        booking = make_booking(db, branch, room)
        assert booking.booking_number.startswith("BKG-")
        assert booking.status == "confirmed"

    def test_booking_sets_room_reserved(self, db):
        branch = make_branch(db)
        rt = make_room_type(db, branch)
        room = make_room(db, branch, rt)
        make_booking(db, branch, room)
        db.refresh(room)
        assert room.status == "reserved"

    def test_create_booking_invalid_dates(self, db):
        branch = make_branch(db)
        rt = make_room_type(db, branch)
        room = make_room(db, branch, rt)
        data = BookingCreate(
            branch_id=branch.id,
            guest_name="عميل",
            check_in=date.today() + timedelta(days=5),
            check_out=date.today(),
            adults=1,
            room_ids=[room.id],
        )
        with pytest.raises(ValueError, match="check_out"):
            services.create_booking(db, data)

    def test_create_booking_room_not_available(self, db):
        branch = make_branch(db)
        rt = make_room_type(db, branch)
        room = make_room(db, branch, rt)
        # نحجز الغرفة في الفترة 100-102 مستقبلاً
        ci = date.today() + timedelta(days=100)
        data1 = BookingCreate(
            branch_id=branch.id, guest_name="عميل أول",
            check_in=ci, check_out=ci + timedelta(days=2),
            adults=1, room_ids=[room.id],
        )
        services.create_booking(db, data1)
        # نحاول حجز نفس الغرفة في نفس الفترة
        data2 = BookingCreate(
            branch_id=branch.id, guest_name="عميل آخر",
            check_in=ci, check_out=ci + timedelta(days=1),
            adults=1, room_ids=[room.id],
        )
        with pytest.raises(services.BookingConflictError):
            services.create_booking(db, data2)

    def test_get_booking_not_found(self, db):
        with pytest.raises(ValueError):
            services.get_booking_or_404(db, 9999)


class TestCheckinCheckout:

    def test_checkin_booking(self, db):
        branch = make_branch(db)
        rt = make_room_type(db, branch)
        room = make_room(db, branch, rt)
        booking = make_booking(db, branch, room)
        checked = services.checkin_booking(db, booking.id)
        assert checked.status == "checked_in"
        db.refresh(room)
        assert room.status == "occupied"

    def test_cannot_checkin_already_checked_in(self, db):
        branch = make_branch(db)
        rt = make_room_type(db, branch)
        room = make_room(db, branch, rt)
        booking = make_booking(db, branch, room)
        services.checkin_booking(db, booking.id)
        with pytest.raises(ValueError):
            services.checkin_booking(db, booking.id)

    def test_checkout_booking(self, db):
        branch = make_branch(db)
        rt = make_room_type(db, branch)
        room = make_room(db, branch, rt)
        booking = make_booking(db, branch, room)
        services.checkin_booking(db, booking.id)
        checked_out = services.checkout_booking(db, booking.id)
        assert checked_out.status == "checked_out"
        db.refresh(room)
        # room moves to checkout_pending, awaiting housekeeping
        assert room.status == "checkout_pending"

    def test_cannot_checkout_without_checkin(self, db):
        branch = make_branch(db)
        rt = make_room_type(db, branch)
        room = make_room(db, branch, rt)
        booking = make_booking(db, branch, room)
        with pytest.raises(ValueError, match="checked_in"):
            services.checkout_booking(db, booking.id)

    def test_cancel_booking(self, db):
        branch = make_branch(db)
        rt = make_room_type(db, branch)
        room = make_room(db, branch, rt)
        booking = make_booking(db, branch, room)
        cancelled = services.cancel_booking(db, booking.id, cancelled_by=1)
        assert cancelled.status == "cancelled"
        db.refresh(room)
        assert room.status == "available"

    def test_cannot_cancel_checked_out_booking(self, db):
        branch = make_branch(db)
        rt = make_room_type(db, branch)
        room = make_room(db, branch, rt)
        booking = make_booking(db, branch, room)
        services.checkin_booking(db, booking.id)
        services.checkout_booking(db, booking.id)
        with pytest.raises(ValueError):
            services.cancel_booking(db, booking.id, cancelled_by=1)


class TestNightAudit:

    def test_run_night_audit(self, db):
        branch = make_branch(db)
        rt = make_room_type(db, branch)
        room = make_room(db, branch, rt)
        booking = make_booking(db, branch, room)
        services.checkin_booking(db, booking.id)
        log = services.run_night_audit(db, branch.id, date.today())
        assert log.status == "completed"
        assert log.branch_id == branch.id

    def test_cannot_run_night_audit_twice(self, db):
        branch = make_branch(db)
        audit_date = date.today() - timedelta(days=15)
        services.run_night_audit(db, branch.id, audit_date)
        with pytest.raises(ValueError, match="مكتمل مسبقاً"):
            services.run_night_audit(db, branch.id, audit_date)
