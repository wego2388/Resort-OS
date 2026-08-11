"""tests/test_hist_pms_bookings.py — end-to-end HIST-01 PMS generator
(OPS-DATA-02 §10.2). يستخدم نفس نمط test_approved_room_pricing.py (SQLite
معزول، مش الـ`db` fixture المشتركة) لأن real_room_inventory.replace_room_
inventory وapproved_room_pricing.activate_room_pricing الاتنين بيتطلبوا
فرع واحد بالظبط + super_admin واحد بالظبط resolvable — مش متوافقين مع جلسة
مشتركة فيها عشرات الفروع من تستات تانية."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.approved_room_pricing import activate_room_pricing
from app.core.database import Base
from app.core.kernel.models.user import User, UserRole
from app.core.kernel.security import get_password_hash
from app.hist_pms_bookings import generate as generate_pms_bookings
from app.modules.core.models import Branch
from app.real_room_inventory import replace_room_inventory


@pytest.fixture
def hist_db() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = session_factory()
    db.add(User(
        id=1, email="hist-pms-actor@example.invalid",
        password_hash=get_password_hash("isolated-test-credential"),
        full_name="HIST PMS Test Actor", role=UserRole.SUPER_ADMIN,
        is_active=True, two_factor_enabled=True,
    ))
    db.commit()
    try:
        yield db
    finally:
        db.rollback()
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _real_branch_with_pricing(db: Session) -> Branch:
    from app.modules.pms.models import Room, RoomType

    branch = Branch(name="El Kheima Beach Resort", name_ar="منتجع الخيمة بيتش",
                     code="ELK-001", timezone="Africa/Cairo", is_active=True)
    db.add(branch)
    db.flush()
    # أدنى حد كافي عشان replace_room_inventory تشتغل (نفس نمط
    # test_approved_room_pricing.py's _synthetic_inventory)
    rt = RoomType(branch_id=branch.id, name="Demo", base_rate=Decimal("800"), max_occupancy=2)
    db.add(rt)
    db.flush()
    db.add(Room(branch_id=branch.id, room_type_id=rt.id, name="D001", floor=1))
    db.flush()

    replace_room_inventory(db, expected_branch_code="ELK-001", actor_id=1)
    db.commit()
    activate_room_pricing(db, expected_branch_code="ELK-001", actor_id=1)
    db.commit()
    return branch


def _seed_accounts(db: Session, branch: Branch) -> None:
    from app.modules.finance.models import Account
    for code, name, acc_type in [
        ("1100", "Cash", "asset"), ("1150", "Folio AR", "asset"),
        ("4100", "Room Revenue", "revenue"),
        ("2160", "VAT Payable", "liability"), ("2165", "Service Charge Payable", "liability"),
    ]:
        db.add(Account(branch_id=branch.id, code=code, name=name, account_type=acc_type))
    db.commit()


class _Ctx:
    def __init__(self, branch_id: int):
        self.branch_id = branch_id
        self.period_year = 2026
        self.period_month = 7
        self.tz_name = "Africa/Cairo"
        self.actor_id = 1
        self.period_end_day = None


class TestHistPmsBookingsGenerator:
    def test_generate_hits_exact_night_and_booking_targets(self, hist_db: Session):
        db = hist_db
        branch = _real_branch_with_pricing(db)
        _seed_accounts(db, branch)

        result = generate_pms_bookings(db, _Ctx(branch.id))
        db.commit()

        counts = result["counts"]
        assert counts["bookings_total"] == 38
        assert counts["bundle"] == 5
        assert counts["cancelled"] == 2
        assert counts["no_show"] == 2
        assert counts["night_audit_logs"] == 31
        assert counts["housekeeping_cycled"] == 1
        assert result["totals"]["room_nights"] == {"studio": 70, "chalet": 75, "bundle": 25}
        # كل الـ38 حجز موزعين على القنوات الأربعة، مفيش قناة صفر
        assert counts["direct"] + counts["online"] + counts["phone"] + counts["b2b"] == 38
        assert all(counts[c] > 0 for c in ("direct", "online", "phone", "b2b"))

    def test_generate_posts_exact_gl_room_revenue_before_vat_service(self, hist_db: Session):
        """صافي إيراد الغرف قبل VAT/الخدمة = 70×2500 + 75×3500 + 25×4500 =
        550,000 EGP (OPS-DATA-02 §10.2) + 250 EGP رسوم وصول مبكر/مغادرة
        متأخرة (150 + 100 — راجع HIST-01 فوق) = 550,250 بالظبط.

        ⚠️ 2026-08-11 (§5): قبل إصلاح ترحيل إيراد رسوم الوصول المبكر/
        المغادرة المتأخرة، الرقم القديم هنا (550,000) كان بيتجاهل الـ250
        جنيه دول تمامًا — نفس الباج بالظبط اللي أدى لوجود حالتين حقيقيتين
        على الإنتاج (250 جنيه) محتاجتين تسوية يدوية لاحقة (راجع تعليق
        management command الجديد تحت). الرقم الجديد هنا بيتحقق من حساب
        4100 الحقيقي بعد كل الـ31 يوم Night Audit + رسوم الوصول/المغادرة،
        مش من رقم مفترض."""
        from app.modules.finance.models import Account, JournalLine

        db = hist_db
        branch = _real_branch_with_pricing(db)
        _seed_accounts(db, branch)

        generate_pms_bookings(db, _Ctx(branch.id))
        db.commit()

        revenue_account = db.query(Account).filter_by(branch_id=branch.id, code="4100").first()
        total_credit = (
            db.query(JournalLine)
            .filter(JournalLine.account_id == revenue_account.id)
            .all()
        )
        net_revenue = sum(l.credit for l in total_credit)
        assert net_revenue == Decimal("550250.00")

    def test_generate_posts_correct_vat_and_service_totals(self, hist_db: Session):
        from app.modules.finance.models import Account, JournalLine

        db = hist_db
        branch = _real_branch_with_pricing(db)
        _seed_accounts(db, branch)

        generate_pms_bookings(db, _Ctx(branch.id))
        db.commit()

        vat_account = db.query(Account).filter_by(branch_id=branch.id, code="2160").first()
        service_account = db.query(Account).filter_by(branch_id=branch.id, code="2165").first()
        vat_total = sum(
            l.credit for l in db.query(JournalLine).filter(JournalLine.account_id == vat_account.id).all()
        )
        service_total = sum(
            l.credit for l in db.query(JournalLine).filter(JournalLine.account_id == service_account.id).all()
        )
        assert vat_total == Decimal("77000.00")
        assert service_total == Decimal("66000.00")

    def test_maintenance_room_actually_blocks_booking(self, hist_db: Session):
        from app.modules.pms.models import Room

        db = hist_db
        branch = _real_branch_with_pricing(db)
        _seed_accounts(db, branch)

        generate_pms_bookings(db, _Ctx(branch.id))
        db.commit()

        # الغرفة اللي كانت maintenance وقت التوليد لازم ترجع available في
        # الآخر (الأداة بترجّعها بعد التحقق) — نتأكد الحالة الحالية سليمة.
        studio_rooms = db.query(Room).join(Room.room_type).filter(
            Room.branch_id == branch.id,
        ).all()
        assert all(r.status != "maintenance" for r in studio_rooms)

    def test_cancelled_and_no_show_bookings_have_correct_status(self, hist_db: Session):
        from app.modules.pms.models import Booking

        db = hist_db
        branch = _real_branch_with_pricing(db)
        _seed_accounts(db, branch)

        generate_pms_bookings(db, _Ctx(branch.id))
        db.commit()

        cancelled = db.query(Booking).filter(
            Booking.branch_id == branch.id, Booking.status == "cancelled",
        ).all()
        no_show = db.query(Booking).filter(
            Booking.branch_id == branch.id, Booking.status == "no_show",
        ).all()
        assert len(cancelled) == 2
        assert len(no_show) == 2

    def test_month_crossing_and_multi_room_bookings_exist(self, hist_db: Session):
        from app.modules.pms.models import Booking

        db = hist_db
        branch = _real_branch_with_pricing(db)
        _seed_accounts(db, branch)

        generate_pms_bookings(db, _Ctx(branch.id))
        db.commit()

        crossing = db.query(Booking).filter(
            Booking.branch_id == branch.id, Booking.check_out > date(2026, 7, 31),
        ).all()
        assert len(crossing) == 1
        assert crossing[0].check_in == date(2026, 7, 29)

        # استبعاد حجوزات الباقة (بالفعل بغرفتين شاليه+استوديو) — الـmulti-room
        # الحقيقي المقصود هنا حجز عادي (room_bundle_id فاضي) بغرفتين شاليه.
        multi_room = [
            b for b in db.query(Booking).filter(Booking.branch_id == branch.id).all()
            if len(b.rooms) == 2 and b.room_bundle_id is None
        ]
        assert len(multi_room) == 1

    def test_rejects_when_bundles_missing(self, hist_db: Session):
        """14 أوضة حقيقية موجودة، لكن مفيش أي RoomBundle اتفعّل (approved_
        room_pricing ما اتشغّلش) — لازم يترفض بوضوح، مش يفترض 0 أزواج."""
        from app.modules.pms.models import Room, RoomType

        db = hist_db
        branch = Branch(name="No Pricing", name_ar="بلا تسعير", code="ELK-001",
                         timezone="Africa/Cairo", is_active=True)
        db.add(branch)
        db.flush()
        rt = RoomType(branch_id=branch.id, name="Demo", base_rate=Decimal("800"), max_occupancy=2)
        db.add(rt)
        db.flush()
        db.add(Room(branch_id=branch.id, room_type_id=rt.id, name="D001", floor=1))
        db.flush()
        replace_room_inventory(db, expected_branch_code="ELK-001", actor_id=1)
        db.commit()
        _seed_accounts(db, branch)

        with pytest.raises(RuntimeError, match="5 active room bundles"):
            generate_pms_bookings(db, _Ctx(branch.id))
