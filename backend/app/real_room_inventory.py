"""Controlled replacement of synthetic PMS rooms with El Kheima's real units.

The command is dry-run by default, uses one transaction and a PostgreSQL
advisory lock, refuses to touch inventory referenced by bookings/housekeeping,
and writes an attributable audit marker.  It deliberately stores no room price
or capacity until Mohamed approves those commercial facts.

Run from the backend container after migration ``d0e1f2a3b4c5``::

    python -m app.real_room_inventory --branch-code ELK-001
    python -m app.real_room_inventory --branch-code ELK-001 --apply \
      --confirm "REPLACE EL KHEIMA ROOMS WITH 14 REAL UNITS"
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal

DATASET_VERSION = "2026-08-08.1"
MARKER_ACTION = "real_room_inventory_replaced"
MARKER_ENTITY = "pms_room_inventory"
CONFIRMATION_PHRASE = "REPLACE EL KHEIMA ROOMS WITH 14 REAL UNITS"
_ADVISORY_LOCK_KEY = 4_502_026_080_814

ROOM_SPECS: tuple[tuple[str, str, str], ...] = (
    ("101A", "chalet", "none"),
    ("102A", "chalet", "none"),
    ("102S", "studio", "none"),
    ("103A", "chalet", "none"),
    ("124S", "studio", "none"),
    ("111A", "chalet", "none"),
    ("111S", "studio", "none"),
    ("114A", "chalet", "side_sea"),
    ("124A", "chalet", "side_sea"),
    ("112S", "studio", "sea"),
    ("122A", "chalet", "sea"),
    ("122S", "studio", "sea"),
    ("123A", "chalet", "sea"),
    ("123S", "studio", "sea"),
)

@dataclass(frozen=True)
class RoomInventoryResult:
    branch_code: str
    version: str
    already_applied: bool
    before: dict[str, int]
    after: dict[str, int]


def _counts(db: Session, branch_id: int) -> dict[str, int]:
    from app.modules.pms.models import RatePlan, Room, RoomType

    return {
        "rooms": int(
            db.query(func.count(Room.id)).filter(Room.branch_id == branch_id).scalar() or 0
        ),
        "room_types": int(
            db.query(func.count(RoomType.id))
            .filter(RoomType.branch_id == branch_id)
            .scalar()
            or 0
        ),
        "rate_plans": int(
            db.query(func.count(RatePlan.id))
            .filter(RatePlan.branch_id == branch_id)
            .scalar()
            or 0
        ),
    }


def _acquire_lock(db: Session) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _ADVISORY_LOCK_KEY},
        )


def _resolve_scope(db: Session, expected_branch_code: str, actor_id: int | None):
    from app.core.kernel.models.user import User
    from app.modules.core.models import Branch

    branches = db.query(Branch).order_by(Branch.id).all()
    if len(branches) != 1:
        raise RuntimeError(f"Expected exactly one branch; found {len(branches)}")
    branch = branches[0]
    if not branch.is_active or branch.code != expected_branch_code:
        raise RuntimeError(
            f"Branch mismatch: expected active {expected_branch_code!r}, "
            f"found {branch.code!r} (active={branch.is_active})"
        )

    query = db.query(User).filter(User.is_active.is_(True))
    if actor_id is not None:
        query = query.filter(User.id == actor_id)
    actors = [
        user
        for user in query.all()
        if getattr(user.role, "value", user.role) == "super_admin"
    ]
    if len(actors) != 1:
        raise RuntimeError("Resolve exactly one active super_admin actor, or pass --actor-id")
    return branch, actors[0]


def _existing_marker(db: Session, branch_id: int):
    from app.modules.core.models import AuditLog

    return (
        db.query(AuditLog)
        .filter(
            AuditLog.branch_id == branch_id,
            AuditLog.action == MARKER_ACTION,
            AuditLog.entity_type == MARKER_ENTITY,
        )
        .order_by(AuditLog.id.desc())
        .first()
    )


def _assert_unreferenced(db: Session, branch_id: int) -> None:
    from app.modules.pms.models import Booking, BookingRoom, HousekeepingTask, Room

    booking_count = db.query(func.count(Booking.id)).filter(
        Booking.branch_id == branch_id
    ).scalar() or 0
    booking_room_count = (
        db.query(func.count(BookingRoom.id))
        .join(Room, Room.id == BookingRoom.room_id)
        .filter(Room.branch_id == branch_id)
        .scalar()
        or 0
    )
    housekeeping_count = (
        db.query(func.count(HousekeepingTask.id))
        .join(Room, Room.id == HousekeepingTask.room_id)
        .filter(Room.branch_id == branch_id)
        .scalar()
        or 0
    )
    if booking_count or booking_room_count or housekeeping_count:
        raise RuntimeError(
            "Room replacement blocked because PMS history exists: "
            f"bookings={booking_count}, booking_rooms={booking_room_count}, "
            f"housekeeping_tasks={housekeeping_count}"
        )


def _matches_real_inventory(db: Session, branch_id: int) -> bool:
    from app.modules.pms.models import RatePlan, Room, RoomType

    room_types = {
        row.name: row
        for row in db.query(RoomType).filter(RoomType.branch_id == branch_id).all()
    }
    if set(room_types) != {"Chalet", "Studio"}:
        return False
    if any(
        row.base_rate is not None or row.max_occupancy is not None
        for row in room_types.values()
    ):
        return False
    actual = {
        (room.name, room.room_type.name.casefold(), room.view_type, room.floor)
        for room in db.query(Room).filter(Room.branch_id == branch_id).all()
    }
    expected = {(name, kind, view, 0) for name, kind, view in ROOM_SPECS}
    rate_plan_count = db.query(func.count(RatePlan.id)).filter(
        RatePlan.branch_id == branch_id
    ).scalar() or 0
    return actual == expected and rate_plan_count == 0


def replace_room_inventory(
    db: Session,
    *,
    expected_branch_code: str,
    actor_id: int | None = None,
) -> RoomInventoryResult:
    """Stage the reviewed real-room replacement in the caller's transaction."""
    environment = (settings.ENVIRONMENT or "").strip().lower()
    if environment not in {"production", "test", "testing"}:
        raise RuntimeError("The real room importer is restricted to production/test")

    _acquire_lock(db)
    branch, actor = _resolve_scope(db, expected_branch_code, actor_id)
    before = _counts(db, branch.id)
    marker = _existing_marker(db, branch.id)
    if marker:
        if not _matches_real_inventory(db, branch.id):
            raise RuntimeError("The real-room audit marker exists but inventory has drifted")
        return RoomInventoryResult(
            branch.code,
            DATASET_VERSION,
            True,
            before,
            before.copy(),
        )

    _assert_unreferenced(db, branch.id)

    from app.modules.core.models import AuditLog
    from app.modules.pms.models import RatePlan, Room, RoomType

    # These rows were confirmed synthetic and have no PMS history.  Remove
    # pricing plans too: their multipliers are demo commercial facts and would
    # otherwise apply silently to the real units.
    db.query(RatePlan).filter(RatePlan.branch_id == branch.id).delete(
        synchronize_session=False
    )
    db.query(Room).filter(Room.branch_id == branch.id).delete(
        synchronize_session=False
    )
    db.query(RoomType).filter(RoomType.branch_id == branch.id).delete(
        synchronize_session=False
    )
    db.flush()

    types = {
        "chalet": RoomType(
            branch_id=branch.id,
            name="Chalet",
            name_ar="شاليه",
            base_rate=None,
            max_occupancy=None,
            amenities=None,
            is_active=True,
        ),
        "studio": RoomType(
            branch_id=branch.id,
            name="Studio",
            name_ar="أستديو",
            base_rate=None,
            max_occupancy=None,
            amenities=None,
            is_active=True,
        ),
    }
    db.add_all(types.values())
    db.flush()

    db.add_all(
        Room(
            branch_id=branch.id,
            room_type_id=types[kind].id,
            name=name,
            floor=0,
            view_type=view,
            status="available",
        )
        for name, kind, view in ROOM_SPECS
    )
    db.flush()

    after = _counts(db, branch.id)
    if after != {"rooms": 14, "room_types": 2, "rate_plans": 0}:
        raise RuntimeError(f"Real-room safety counts failed: {after}")

    db.add(
        AuditLog(
            user_id=actor.id,
            branch_id=branch.id,
            action=MARKER_ACTION,
            entity_type=MARKER_ENTITY,
            entity_id=branch.id,
            old_data=json.dumps(before, sort_keys=True),
            new_data=json.dumps(
                {
                    "version": DATASET_VERSION,
                    "rooms": [
                        {"name": name, "type": kind, "view": view, "floor": 0}
                        for name, kind, view in ROOM_SPECS
                    ],
                    "room_types": {
                        "Chalet": {"base_rate": None, "max_occupancy": None},
                        "Studio": {"base_rate": None, "max_occupancy": None},
                    },
                    "removed_demo_rate_plans": before["rate_plans"],
                    "source": "Mohamed-approved real inventory, 2026-08-08",
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            ip_address="127.0.0.1",
            user_agent="app.real_room_inventory",
            approved_by=actor.id,
        )
    )
    db.flush()
    return RoomInventoryResult(branch.code, DATASET_VERSION, False, before, after)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run or apply the approved El Kheima real room inventory."
    )
    parser.add_argument("--branch-code", required=True)
    parser.add_argument("--actor-id", type=int)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.apply and args.confirm != CONFIRMATION_PHRASE:
        raise SystemExit(f"--apply requires --confirm {CONFIRMATION_PHRASE!r}")

    with SessionLocal() as db:
        try:
            result = replace_room_inventory(
                db,
                expected_branch_code=args.branch_code,
                actor_id=args.actor_id,
            )
            if args.apply:
                db.commit()
            else:
                db.rollback()
            print(
                json.dumps(
                    {
                        "mode": "apply" if args.apply else "dry-run",
                        "branch_code": result.branch_code,
                        "version": result.version,
                        "already_applied": result.already_applied,
                        "before": result.before,
                        "after": result.after,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0
        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    raise SystemExit(main())
