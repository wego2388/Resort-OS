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

from app.modules.pms.schemas import BookingCreate, RatePlanCreate
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


def make_finance_accounts(db, branch):
    """يزرع 1100 (نقدية) و4100 (إيرادات الغرف) — الحسابين اللي
    pms.services._post_checkout_journal بيدوّر عليهم بالكود عند ترحيل قيد
    إيراد الغرف وقت الخروج."""
    from app.modules.finance.models import Account
    cash = Account(branch_id=branch.id, code="1100", name="Cash", account_type="asset")
    revenue = Account(branch_id=branch.id, code="4100", name="Room Revenue", account_type="revenue")
    db.add_all([cash, revenue])
    db.commit()
    return cash, revenue


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


class TestGetAvailableRooms:
    """باج حقيقي اتصلح 2026-07-03 (QA pass): الفلترة كانت بتشترط
    Room.status == "available" حرفيًا — أي غرفة في حالة يومية عابرة
    (occupied/reserved/checkout_pending لضيف تاني هيسيب الغرفة قبل تاريخ
    الوصول المطلوب) كانت بتتشال بالكامل من نتيجة "الغرف المتاحة" حتى لو
    مفيش أي تعارض حجز حقيقي في الفترة المطلوبة. اكتُشف لما شاشة "حجز جديد"
    طلعت فاضية بالكامل رغم وجود غرفة وحيدة مش محجوزة فعليًا للفترة المطلوبة،
    لمجرد إن حالتها الحالية "checkout_pending". status == "maintenance" بس
    هو اللي المفروض يمنع الحجز فعليًا (عطل حقيقي في الغرفة)."""

    def test_room_with_transient_status_is_still_available(self, db):
        branch = make_branch(db)
        rt = make_room_type(db, branch)
        room = make_room(db, branch, rt)
        for transient_status in ("occupied", "reserved", "checkout_pending"):
            crud.update_room_status(db, room, transient_status)
            db.flush()
            check_in = date.today() + timedelta(days=100)
            check_out = check_in + timedelta(days=2)
            available = crud.get_available_rooms(db, branch.id, check_in, check_out)
            assert room.id in [r.id for r in available], (
                f"room in status '{transient_status}' with no overlapping booking "
                "should still be bookable for a future date range"
            )

    def test_room_under_maintenance_is_excluded(self, db):
        branch = make_branch(db)
        rt = make_room_type(db, branch)
        room = make_room(db, branch, rt)
        crud.update_room_status(db, room, "maintenance")
        db.flush()
        check_in = date.today() + timedelta(days=100)
        check_out = check_in + timedelta(days=2)
        available = crud.get_available_rooms(db, branch.id, check_in, check_out)
        assert room.id not in [r.id for r in available]

    def test_room_with_overlapping_booking_is_excluded(self, db):
        branch = make_branch(db)
        rt = make_room_type(db, branch)
        room = make_room(db, branch, rt)
        check_in = date.today() + timedelta(days=100)
        check_out = check_in + timedelta(days=3)
        data = BookingCreate(
            branch_id=branch.id, guest_name="ضيف",
            check_in=check_in, check_out=check_out, room_ids=[room.id],
        )
        services.create_booking(db, data)
        available = crud.get_available_rooms(db, branch.id, check_in, check_out)
        assert room.id not in [r.id for r in available]


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

    def test_request_early_late_on_closed_folio_leaves_zero_trace(self, db):
        """مراجعة Codex الثانية (Gate 1B): كان فيه except Exception يبتلع
        فشل add_folio_charge بعد ما يسجّله بس — يعني تعديل الحجز (extra_
        charge/total_rate/early_checkin_at) كان بيتسجّل ويتقفل بـcommit
        حتى لو الفوليو مقفول، يعني رسوم إضافية على الحجز من غير أي شحنة
        فوليو مقابلة. دلوقتي لازم يفشل بالكامل من غير أي تعديل جزئي
        متسجّل على الحجز."""
        from datetime import datetime, timedelta as _td
        from app.modules.pms.schemas import EarlyLateRequest
        from tests.conftest import TestingSessionLocal

        branch = make_branch(db)
        rt = make_room_type(db, branch)
        room = make_room(db, branch, rt)
        booking = make_booking(db, branch, room)
        checked_in = services.checkin_booking(db, booking.id)
        assert checked_in.folio_id is not None

        from app.modules.finance import crud as finance_crud
        folio = finance_crud.get_folio(db, checked_in.folio_id)
        folio.status = "closed"
        db.commit()

        original_total_rate = checked_in.total_rate
        booking_id = booking.id

        with pytest.raises(ValueError):
            services.request_early_late(db, booking_id, EarlyLateRequest(
                early_checkin_at=datetime.utcnow() + _td(hours=2),
                charge=Decimal("150.00"),
            ))

        fresh = TestingSessionLocal()
        try:
            from app.modules.pms.models import Booking
            fresh_booking = fresh.query(Booking).filter(Booking.id == booking_id).first()
            assert fresh_booking.early_checkin_at is None, (
                "early_checkin_at اتسجّل رغم فشل شحنة الفوليو — تعديل جزئي ممنوع"
            )
            assert fresh_booking.total_rate == original_total_rate, (
                "total_rate اتغيّر رغم فشل شحنة الفوليو بالكامل — تعديل جزئي ممنوع"
            )
        finally:
            fresh.close()

    def test_checkout_updates_linked_customer_stats(self, db):
        from app.modules.crm import services as crm_services
        from app.modules.crm.schemas import CustomerCreate

        branch = make_branch(db)
        customer = crm_services.create_customer(db, CustomerCreate(
            branch_id=branch.id, full_name="نزيل دائم",
        ))
        rt = make_room_type(db, branch)
        room = make_room(db, branch, rt)
        data = BookingCreate(
            branch_id=branch.id, guest_name="نزيل دائم", guest_phone="01000000099",
            check_in=date.today() + timedelta(days=1),
            check_out=date.today() + timedelta(days=3),
            adults=2, children=0, room_ids=[room.id], customer_id=customer.id,
        )
        booking = services.create_booking(db, data)
        services.checkin_booking(db, booking.id)
        services.checkout_booking(db, booking.id)

        db.refresh(customer)
        assert customer.visits_count == 1
        assert customer.total_spent == booking.total_rate

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


class TestRatePlanBookingIntegration:
    """باج "الموديل موجود، الـ API صفر" (RatePlan) اتصلح جزئيًا بربط
    GET/POST /pms/rate-plans — بس create_booking عمرها ما كانت بتستخدم أي
    خطة فعليًا، السعر كان دايمًا room_type.base_rate الخام. التستات دي
    بتتأكد إن تمرير rate_plan_id فعلاً بيغيّر السعر النهائي، مش بس إنه
    مقبول شكليًا."""

    def test_rate_multiplier_applies_to_daily_rate(self, db):
        branch = make_branch(db)
        rt = make_room_type(db, branch)  # base_rate = 500.00
        room = make_room(db, branch, rt)
        plan = crud.create_rate_plan(db, RatePlanCreate(
            branch_id=branch.id, room_type_id=rt.id, name="موسم عالي",
            rate_multiplier=Decimal("1.5000"),
            valid_from=date.today(), valid_until=date.today() + timedelta(days=365),
        ))
        db.commit()
        ci = date.today() + timedelta(days=10)
        booking = services.create_booking(db, BookingCreate(
            branch_id=branch.id, guest_name="ضيف موسم عالي",
            check_in=ci, check_out=ci + timedelta(days=2),
            room_ids=[room.id], rate_plan_id=plan.id,
        ))
        assert booking.rooms[0].daily_rate == Decimal("750.00")  # 500 * 1.5
        assert booking.rooms[0].rate_plan_id == plan.id
        assert booking.total_rate == Decimal("1500.00")  # 750 * 2 nights

    def test_base_rate_override_wins_over_multiplier(self, db):
        branch = make_branch(db)
        rt = make_room_type(db, branch)  # base_rate = 500.00
        room = make_room(db, branch, rt)
        plan = crud.create_rate_plan(db, RatePlanCreate(
            branch_id=branch.id, room_type_id=rt.id, name="سعر ثابت",
            base_rate_override=Decimal("999.00"), rate_multiplier=Decimal("2.0000"),
            valid_from=date.today(), valid_until=date.today() + timedelta(days=365),
        ))
        db.commit()
        ci = date.today() + timedelta(days=11)
        booking = services.create_booking(db, BookingCreate(
            branch_id=branch.id, guest_name="ضيف",
            check_in=ci, check_out=ci + timedelta(days=1),
            room_ids=[room.id], rate_plan_id=plan.id,
        ))
        assert booking.rooms[0].daily_rate == Decimal("999.00")

    def test_rate_plan_scoped_to_other_room_type_does_not_apply(self, db):
        branch = make_branch(db)
        rt = make_room_type(db, branch)          # base_rate = 500.00
        other_rt = make_room_type(db, branch)
        other_rt.base_rate = Decimal("500.00")
        room = make_room(db, branch, rt)
        plan = crud.create_rate_plan(db, RatePlanCreate(
            branch_id=branch.id, room_type_id=other_rt.id, name="خطة لنوع تاني",
            rate_multiplier=Decimal("3.0000"),
            valid_from=date.today(), valid_until=date.today() + timedelta(days=365),
        ))
        db.commit()
        ci = date.today() + timedelta(days=12)
        booking = services.create_booking(db, BookingCreate(
            branch_id=branch.id, guest_name="ضيف",
            check_in=ci, check_out=ci + timedelta(days=1),
            room_ids=[room.id], rate_plan_id=plan.id,
        ))
        # الخطة مخصصة لنوع غرفة مختلف — السعر الأساسي الخام هو اللي لازم يتطبّق
        assert booking.rooms[0].daily_rate == Decimal("500.00")
        assert booking.rooms[0].rate_plan_id is None

    def test_rate_plan_outside_validity_window_rejected(self, db):
        branch = make_branch(db)
        rt = make_room_type(db, branch)
        room = make_room(db, branch, rt)
        plan = crud.create_rate_plan(db, RatePlanCreate(
            branch_id=branch.id, room_type_id=rt.id, name="عرض محدود",
            rate_multiplier=Decimal("0.8000"),
            valid_from=date.today() + timedelta(days=100),
            valid_until=date.today() + timedelta(days=110),
        ))
        db.commit()
        ci = date.today() + timedelta(days=13)  # خارج نطاق سريان الخطة
        with pytest.raises(ValueError, match="سارية"):
            services.create_booking(db, BookingCreate(
                branch_id=branch.id, guest_name="ضيف",
                check_in=ci, check_out=ci + timedelta(days=1),
                room_ids=[room.id], rate_plan_id=plan.id,
            ))

    def test_rate_plan_min_nights_enforced(self, db):
        branch = make_branch(db)
        rt = make_room_type(db, branch)
        room = make_room(db, branch, rt)
        plan = crud.create_rate_plan(db, RatePlanCreate(
            branch_id=branch.id, room_type_id=rt.id, name="حد أدنى 3 ليالٍ",
            rate_multiplier=Decimal("0.9000"), min_nights=3,
            valid_from=date.today(), valid_until=date.today() + timedelta(days=365),
        ))
        db.commit()
        ci = date.today() + timedelta(days=14)
        with pytest.raises(ValueError, match="3 ليالٍ"):
            services.create_booking(db, BookingCreate(
                branch_id=branch.id, guest_name="ضيف",
                check_in=ci, check_out=ci + timedelta(days=1),  # ليلة واحدة بس
                room_ids=[room.id], rate_plan_id=plan.id,
            ))

    def test_inactive_rate_plan_rejected(self, db):
        branch = make_branch(db)
        rt = make_room_type(db, branch)
        room = make_room(db, branch, rt)
        plan = crud.create_rate_plan(db, RatePlanCreate(
            branch_id=branch.id, room_type_id=rt.id, name="خطة موقوفة",
            rate_multiplier=Decimal("1.2000"), is_active=False,
            valid_from=date.today(), valid_until=date.today() + timedelta(days=365),
        ))
        db.commit()
        ci = date.today() + timedelta(days=15)
        with pytest.raises(ValueError, match="غير مفعّلة"):
            services.create_booking(db, BookingCreate(
                branch_id=branch.id, guest_name="ضيف",
                check_in=ci, check_out=ci + timedelta(days=1),
                room_ids=[room.id], rate_plan_id=plan.id,
            ))


class TestRatePlanManagement:
    """wagdy.md P-06 — services.update_rate_plan (PATCH كان غير موجود خالص،
    GET/POST بس)."""

    def test_update_rate_plan_partial_fields(self, db):
        from app.modules.pms.schemas import RatePlanUpdate
        branch = make_branch(db)
        rt = make_room_type(db, branch)
        plan = crud.create_rate_plan(db, RatePlanCreate(
            branch_id=branch.id, room_type_id=rt.id, name="خطة أصلية",
            rate_multiplier=Decimal("1.1000"),
            valid_from=date.today(), valid_until=date.today() + timedelta(days=90),
        ))
        db.commit()

        updated = services.update_rate_plan(db, plan.id, RatePlanUpdate(
            rate_multiplier=Decimal("1.3000"),
        ))
        assert updated.rate_multiplier == Decimal("1.3000")
        assert updated.name == "خطة أصلية"  # مش متضمّن في التحديث، لازم يفضل زي ما هو

    def test_deactivate_rate_plan(self, db):
        from app.modules.pms.schemas import RatePlanUpdate
        branch = make_branch(db)
        rt = make_room_type(db, branch)
        plan = crud.create_rate_plan(db, RatePlanCreate(
            branch_id=branch.id, room_type_id=rt.id, name="خطة هتتعطّل",
            valid_from=date.today(), valid_until=date.today() + timedelta(days=90),
        ))
        db.commit()
        assert plan.is_active is True

        updated = services.update_rate_plan(db, plan.id, RatePlanUpdate(is_active=False))
        assert updated.is_active is False

    def test_update_nonexistent_rate_plan_raises(self, db):
        from app.modules.pms.schemas import RatePlanUpdate
        with pytest.raises(ValueError, match="غير موجودة"):
            services.update_rate_plan(db, 999999, RatePlanUpdate(name="x"))

    def test_update_rate_plan_invalid_date_range_raises(self, db):
        from app.modules.pms.schemas import RatePlanUpdate
        branch = make_branch(db)
        rt = make_room_type(db, branch)
        plan = crud.create_rate_plan(db, RatePlanCreate(
            branch_id=branch.id, room_type_id=rt.id, name="خطة تواريخ",
            valid_from=date.today(), valid_until=date.today() + timedelta(days=30),
        ))
        db.commit()
        # valid_from جديد بعد valid_until الحالي (مش متضمّن في التحديث)
        with pytest.raises(ValueError, match="valid_until"):
            services.update_rate_plan(db, plan.id, RatePlanUpdate(
                valid_from=date.today() + timedelta(days=60),
            ))

    def test_create_rate_plan_via_service_validates_dates(self, db):
        branch = make_branch(db)
        with pytest.raises(ValueError, match="valid_until"):
            services.create_rate_plan(db, RatePlanCreate(
                branch_id=branch.id, name="خطة غلط",
                valid_from=date.today(), valid_until=date.today() - timedelta(days=1),
            ))


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


class TestTimezoneBugFixes:
    """باج توقيت حقيقي (نفس فئة KDS "urgent"/dashboard "إيراد اليوم"): أي
    منطق كان بيحسب "اليوم" بـ date.today()/datetime.utcnow() الخام (تاريخ
    السيرفر UTC) بدل تاريخ المنتجع الفعلي (Africa/Cairo) — اتصلح باستخدام
    app.resort_os.timezone_utils.local_today، والتستات دي بتتأكد إن الاستدعاء
    فعلاً بيمر من الدالة المشتركة دي مش من date.today() القديم."""

    def test_generate_booking_number_uses_resort_local_date(self, db, monkeypatch):
        import app.resort_os.timezone_utils as tzutils
        forced_date = date(2026, 12, 25)
        monkeypatch.setattr(tzutils, "local_today", lambda tz_name: forced_date)

        branch = make_branch(db)
        number = crud.generate_booking_number(db, branch.id)
        assert number.startswith("BKG-20261225-")

    def test_checkout_journal_uses_resort_local_date_not_server_utc(self, db, monkeypatch):
        """لو السيرفر (UTC) لسه فاتح على تاريخ الأمس بينما توقيت القاهرة
        بالفعل دخل يوم جديد، قيد إيراد الغرف عند الخروج لازم يتسجّل بتاريخ
        القاهرة (اليوم الجديد) مش بتاريخ الـ UTC القديم."""
        import app.resort_os.timezone_utils as tzutils
        from app.modules.finance.models import JournalEntry

        forced_date = date(2026, 12, 26)  # "اليوم" بتوقيت القاهرة
        monkeypatch.setattr(tzutils, "local_today", lambda tz_name: forced_date)

        branch = make_branch(db)
        make_finance_accounts(db, branch)
        rt = make_room_type(db, branch)
        room = make_room(db, branch, rt)
        booking = make_booking(db, branch, room)
        services.checkin_booking(db, booking.id)
        services.checkout_booking(db, booking.id)

        entry = (
            db.query(JournalEntry)
            .filter(JournalEntry.source == "pms", JournalEntry.source_id == booking.id)
            .first()
        )
        assert entry is not None
        assert entry.entry_date == forced_date

    def test_local_today_returns_cairo_date_when_server_utc_is_still_yesterday(self, monkeypatch):
        """اختبار مباشر للدالة المشتركة نفسها: 2026-07-05 23:30 UTC = فعليًا
        2026-07-06 02:30 بتوقيت القاهرة (UTC+3) — يوم جديد بالفعل بتوقيت
        المنتجع رغم إن تاريخ UTC الخام لسه اليوم اللي فات."""
        import app.resort_os.timezone_utils as tzutils
        from datetime import datetime as real_datetime, timezone as dt_timezone

        fixed_utc = real_datetime(2026, 7, 5, 23, 30, tzinfo=dt_timezone.utc)

        class FakeDateTime(real_datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_utc if tz is None else fixed_utc.astimezone(tz)

        monkeypatch.setattr(tzutils, "datetime", FakeDateTime)

        assert tzutils.local_today("Africa/Cairo") == date(2026, 7, 6)
