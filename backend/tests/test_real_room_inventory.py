from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.kernel.models.user import User, UserRole
from app.core.kernel.security import get_password_hash
from app.modules.core.models import AuditLog, Branch
from app.modules.pms.models import Booking, BookingRoom, RatePlan, Room, RoomType
from app.modules.pms.schemas import BookingCreate
from app.modules.pms.services import create_booking
from app.real_room_inventory import (
    MARKER_ACTION,
    ROOM_SPECS,
    replace_room_inventory,
)


@pytest.fixture
def room_inventory_db() -> Session:
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
            email="real-room-actor@example.invalid",
            password_hash=get_password_hash("isolated-test-credential"),
            full_name="Real Room Test Actor",
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
    room_types = []
    for index in range(5):
        room_type = RoomType(
            branch_id=branch.id,
            name=f"Demo Type {index + 1}",
            base_rate=Decimal(800 + index * 400),
            max_occupancy=index + 1,
        )
        db.add(room_type)
        room_types.append(room_type)
    db.flush()
    for index in range(52):
        db.add(
            Room(
                branch_id=branch.id,
                room_type_id=room_types[index % len(room_types)].id,
                name=f"D{index + 1:03d}",
                floor=(index // 10) + 1,
            )
        )
    for index, multiplier in enumerate(("1.0", "1.2", "1.4", "0.85"), start=1):
        db.add(
            RatePlan(
                branch_id=branch.id,
                name=f"Demo Plan {index}",
                rate_multiplier=Decimal(multiplier),
                valid_from=date(2026, 1, 1),
                valid_until=date(2026, 12, 31),
            )
        )
    db.flush()


def test_replaces_synthetic_rooms_with_exact_unpriced_real_inventory(
    room_inventory_db: Session,
) -> None:
    db = room_inventory_db
    branch = _branch(db)
    _synthetic_inventory(db, branch)

    result = replace_room_inventory(
        db,
        expected_branch_code="ELK-001",
        actor_id=1,
    )
    db.commit()

    assert result.before == {"rooms": 52, "room_types": 5, "rate_plans": 4}
    assert result.after == {"rooms": 14, "room_types": 2, "rate_plans": 0}
    assert result.already_applied is False

    types = db.query(RoomType).order_by(RoomType.name).all()
    assert [(row.name, row.name_ar) for row in types] == [
        ("Chalet", "شاليه"),
        ("Studio", "أستديو"),
    ]
    assert all(row.base_rate is None for row in types)
    assert all(row.max_occupancy is None for row in types)
    assert all(row.amenities is None for row in types)

    rooms = db.query(Room).order_by(Room.name).all()
    actual = {
        (room.name, room.room_type.name.casefold(), room.view_type, room.floor)
        for room in rooms
    }
    assert actual == {(name, kind, view, 0) for name, kind, view in ROOM_SPECS}
    assert all(room.status == "available" for room in rooms)
    assert db.query(RatePlan).count() == 0
    assert db.query(AuditLog).filter(AuditLog.action == MARKER_ACTION).count() == 1


def test_real_inventory_import_is_idempotent_when_unchanged(
    room_inventory_db: Session,
) -> None:
    db = room_inventory_db
    branch = _branch(db)
    _synthetic_inventory(db, branch)
    replace_room_inventory(db, expected_branch_code="ELK-001", actor_id=1)
    db.commit()

    second = replace_room_inventory(db, expected_branch_code="ELK-001", actor_id=1)

    assert second.already_applied is True
    assert second.before == second.after == {
        "rooms": 14,
        "room_types": 2,
        "rate_plans": 0,
    }
    assert db.query(AuditLog).filter(AuditLog.action == MARKER_ACTION).count() == 1


def test_replacement_refuses_any_existing_booking_history(
    room_inventory_db: Session,
) -> None:
    db = room_inventory_db
    branch = _branch(db)
    _synthetic_inventory(db, branch)
    room = db.query(Room).first()
    booking = Booking(
        branch_id=branch.id,
        booking_number="BKG-SAFETY-1",
        guest_name="Safety Guest",
        check_in=date(2026, 8, 10),
        check_out=date(2026, 8, 11),
        adults=1,
        children=0,
        status="confirmed",
        source="direct",
        total_rate=Decimal("800"),
    )
    db.add(booking)
    db.flush()
    db.add(
        BookingRoom(
            booking_id=booking.id,
            room_id=room.id,
            daily_rate=Decimal("800"),
            nights=1,
            total=Decimal("800"),
        )
    )
    db.commit()

    with pytest.raises(RuntimeError, match="PMS history exists"):
        replace_room_inventory(db, expected_branch_code="ELK-001", actor_id=1)

    assert db.query(Room).count() == 52
    assert db.query(RoomType).count() == 5


def test_booking_unpriced_real_room_fails_closed(
    room_inventory_db: Session,
) -> None:
    db = room_inventory_db
    branch = _branch(db)
    _synthetic_inventory(db, branch)
    replace_room_inventory(db, expected_branch_code="ELK-001", actor_id=1)
    db.commit()
    room = db.query(Room).filter(Room.name == "101A").one()

    with pytest.raises(ValueError, match="لم يتم تحديد سعر للغرفة 101A"):
        create_booking(
            db,
            BookingCreate(
                branch_id=branch.id,
                guest_name="Unpriced Guest",
                check_in=date.today() + timedelta(days=2),
                check_out=date.today() + timedelta(days=3),
                room_ids=[room.id],
            ),
        )

    assert db.query(Booking).count() == 0
