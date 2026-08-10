from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.approved_room_pricing import (
    APPROVED_PAIRS,
    BUNDLE_MAX_OCCUPANCY,
    BUNDLE_PRICE,
    CHALET_BASE_RATE,
    CHALET_MAX_OCCUPANCY,
    MARKER_ACTION,
    STUDIO_BASE_RATE,
    STUDIO_MAX_OCCUPANCY,
    activate_room_pricing,
)
from app.core.database import Base
from app.core.kernel.models.user import User, UserRole
from app.core.kernel.security import get_password_hash
from app.modules.core.models import AuditLog, Branch
from app.modules.pms.models import Booking, BookingRoom, Room, RoomBundle, RoomType
from app.modules.pms.schemas import BookingCreate, BundleBookingCreate
from app.modules.pms.services import (
    BookingConflictError, create_booking, create_bundle_booking,
)
from app.real_room_inventory import replace_room_inventory


@pytest.fixture
def pricing_db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = session_factory()
    db.add(
        User(
            id=1,
            email="pricing-actor@example.invalid",
            password_hash=get_password_hash("isolated-test-credential"),
            full_name="Pricing Test Actor",
            role=UserRole.SUPER_ADMIN,
            is_active=True,
            two_factor_enabled=True,
        )
    )
    db.commit()
    try:
        yield db
    finally:
        db.rollback()
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _branch(db: Session) -> Branch:
    branch = Branch(
        name="El Kheima Beach Resort",
        name_ar="منتجع الخيمة بيتش",
        code="ELK-001",
        timezone="Africa/Cairo",
        is_active=True,
    )
    db.add(branch)
    db.flush()
    return branch


def _synthetic_inventory(db: Session, branch: Branch) -> None:
    """أدنى حد كافي عشان real_room_inventory.replace_room_inventory تشتغل."""
    room_type = RoomType(branch_id=branch.id, name="Demo Type", base_rate=Decimal("800"), max_occupancy=2)
    db.add(room_type)
    db.flush()
    db.add(Room(branch_id=branch.id, room_type_id=room_type.id, name="D001", floor=1))
    db.flush()


def _real_inventory(db: Session, branch: Branch) -> None:
    _synthetic_inventory(db, branch)
    replace_room_inventory(db, expected_branch_code="ELK-001", actor_id=1)
    db.commit()


def test_activates_pricing_and_creates_five_bundles(pricing_db: Session) -> None:
    db = pricing_db
    branch = _branch(db)
    _real_inventory(db, branch)

    result = activate_room_pricing(db, expected_branch_code="ELK-001", actor_id=1)
    db.commit()

    assert result.already_applied is False

    types = {row.name: row for row in db.query(RoomType).all()}
    assert types["Studio"].base_rate == STUDIO_BASE_RATE
    assert types["Studio"].max_occupancy == STUDIO_MAX_OCCUPANCY
    assert types["Chalet"].base_rate == CHALET_BASE_RATE
    assert types["Chalet"].max_occupancy == CHALET_MAX_OCCUPANCY

    bundles = db.query(RoomBundle).order_by(RoomBundle.name).all()
    assert len(bundles) == len(APPROVED_PAIRS) == 5
    pairs = {(b.chalet_room.name, b.studio_room.name) for b in bundles}
    assert pairs == {(a, s) for _, a, s in APPROVED_PAIRS}
    assert all(b.price == BUNDLE_PRICE for b in bundles)
    assert all(b.max_occupancy == BUNDLE_MAX_OCCUPANCY for b in bundles)
    assert all(b.is_active for b in bundles)
    assert db.query(AuditLog).filter(AuditLog.action == MARKER_ACTION).count() == 1


def test_activation_is_idempotent_when_unchanged(pricing_db: Session) -> None:
    db = pricing_db
    branch = _branch(db)
    _real_inventory(db, branch)
    activate_room_pricing(db, expected_branch_code="ELK-001", actor_id=1)
    db.commit()

    second = activate_room_pricing(db, expected_branch_code="ELK-001", actor_id=1)

    assert second.already_applied is True
    assert db.query(AuditLog).filter(AuditLog.action == MARKER_ACTION).count() == 1
    assert db.query(RoomBundle).count() == 5


def test_activation_requires_real_inventory_first(pricing_db: Session) -> None:
    db = pricing_db
    branch = _branch(db)
    _synthetic_inventory(db, branch)  # مفيش real_room_inventory هنا عمدًا
    db.commit()

    with pytest.raises(RuntimeError, match="missing units required for the approved pairs"):
        activate_room_pricing(db, expected_branch_code="ELK-001", actor_id=1)

    assert db.query(RoomBundle).count() == 0


class TestCreateBundleBooking:
    """راجع OPS-DATA-02 §7.1: حجز الباقة ذري بالكامل — الغرفتين بيتقفلوا/
    يتحجزوا سوا في نفس الـtransaction، وبدون ازدواج إيراد."""

    def _activated(self, db: Session) -> Branch:
        branch = _branch(db)
        _real_inventory(db, branch)
        activate_room_pricing(db, expected_branch_code="ELK-001", actor_id=1)
        db.commit()
        return branch

    def test_bundle_booking_splits_price_analytically_with_no_double_revenue(
        self, pricing_db: Session,
    ) -> None:
        db = pricing_db
        branch = self._activated(db)
        bundle = db.query(RoomBundle).filter(RoomBundle.chalet_room.has(name="102A")).one()

        booking = create_bundle_booking(db, BundleBookingCreate(
            branch_id=branch.id,
            bundle_id=bundle.id,
            guest_name="عائلة الاختبار",
            check_in=date.today() + timedelta(days=5),
            check_out=date.today() + timedelta(days=7),  # ليلتين
        ))

        assert booking.room_bundle_id == bundle.id
        rooms = {br.room_id: br for br in booking.rooms}
        assert len(rooms) == 2
        chalet_leg = rooms[bundle.chalet_room_id]
        studio_leg = rooms[bundle.studio_room_id]
        # 3500/(3500+2500) * 4500 = 2625.00 بالظبط، والباقي 1875.00
        assert chalet_leg.daily_rate == Decimal("2625.00")
        assert studio_leg.daily_rate == Decimal("1875.00")
        assert chalet_leg.daily_rate + studio_leg.daily_rate == BUNDLE_PRICE  # مفيش ازدواج إيراد
        assert booking.total_rate == BUNDLE_PRICE * 2  # ليلتين

        assert db.query(Room).filter(Room.id == bundle.chalet_room_id).one().status == "reserved"
        assert db.query(Room).filter(Room.id == bundle.studio_room_id).one().status == "reserved"

    def test_bundle_booking_is_all_or_nothing_when_one_unit_is_taken(
        self, pricing_db: Session,
    ) -> None:
        db = pricing_db
        branch = self._activated(db)
        bundle = db.query(RoomBundle).filter(RoomBundle.chalet_room.has(name="111A")).one()
        check_in = date.today() + timedelta(days=10)
        check_out = date.today() + timedelta(days=12)

        # يحجز الاستوديو (نص الزوج) لوحده الأول — الشاليه لسه فاضي
        create_booking(db, BookingCreate(
            branch_id=branch.id, guest_name="ضيف سابق",
            check_in=check_in, check_out=check_out,
            room_ids=[bundle.studio_room_id],
        ))
        db.commit()

        with pytest.raises(BookingConflictError):
            create_bundle_booking(db, BundleBookingCreate(
                branch_id=branch.id, bundle_id=bundle.id,
                guest_name="عائلة اتأخرت",
                check_in=check_in, check_out=check_out,
            ))

        # مفيش حجز نص باقة أبدًا — الشاليه (اللي كان متاح فعليًا) لازم يفضل
        # available، مش reserved بالغلط.
        assert db.query(Room).filter(Room.id == bundle.chalet_room_id).one().status == "available"
        assert db.query(Booking).count() == 1  # الحجز الأول بس

    def test_bundle_booking_rejects_inactive_bundle(self, pricing_db: Session) -> None:
        db = pricing_db
        branch = self._activated(db)
        bundle = db.query(RoomBundle).first()
        bundle.is_active = False
        db.commit()

        with pytest.raises(ValueError, match="غير مفعّلة"):
            create_bundle_booking(db, BundleBookingCreate(
                branch_id=branch.id, bundle_id=bundle.id,
                guest_name="ضيف",
                check_in=date.today() + timedelta(days=3),
                check_out=date.today() + timedelta(days=4),
            ))
        assert db.query(Booking).count() == 0

    def test_bundle_booking_rejects_unknown_bundle(self, pricing_db: Session) -> None:
        db = pricing_db
        branch = self._activated(db)

        with pytest.raises(ValueError, match="غير موجودة"):
            create_bundle_booking(db, BundleBookingCreate(
                branch_id=branch.id, bundle_id=999999,
                guest_name="ضيف",
                check_in=date.today() + timedelta(days=3),
                check_out=date.today() + timedelta(days=4),
            ))
