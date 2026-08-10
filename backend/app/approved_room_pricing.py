"""Controlled activation of El Kheima's approved commercial room pricing.

Sets ``RoomType.base_rate``/``max_occupancy`` for Studio/Chalet and creates
the 5 Mohamed-approved "Family Compound 6P" bundles (Chalet + Family Studio
sharing the same unit number — OPS-DATA-02 §3/§7.1, NOT a third RoomType).

The command is dry-run by default, uses one transaction and a PostgreSQL
advisory lock, requires the 14 real units from ``app.real_room_inventory``
to already be in place, and writes an attributable audit marker.

Run from the backend container after ``app.real_room_inventory`` has been
applied::

    python -m app.approved_room_pricing --branch-code ELK-001
    python -m app.approved_room_pricing --branch-code ELK-001 --apply \
      --confirm "ACTIVATE EL KHEIMA APPROVED ROOM PRICING"
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal

DATASET_VERSION = "2026-08-10.1"
MARKER_ACTION = "approved_room_pricing_activated"
MARKER_ENTITY = "pms_room_pricing"
CONFIRMATION_PHRASE = "ACTIVATE EL KHEIMA APPROVED ROOM PRICING"
_ADVISORY_LOCK_KEY = 4_502_026_081_000

# OPS-DATA-02 §3: أسعار لليلة، غير شاملة VAT 14%/خدمة 12%، بلا إفطار.
STUDIO_BASE_RATE = Decimal("2500.00")
STUDIO_MAX_OCCUPANCY = 2
CHALET_BASE_RATE = Decimal("3500.00")
CHALET_MAX_OCCUPANCY = 4
BUNDLE_PRICE = Decimal("4500.00")
BUNDLE_MAX_OCCUPANCY = 6

# الأزواج التجريبية المعتمدة (§3) — نفس أسماء الوحدات اللي real_room_inventory
# أنشأها بالفعل (chalet=...A, studio=...S بنفس الرقم).
APPROVED_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("102", "102A", "102S"),
    ("111", "111A", "111S"),
    ("122", "122A", "122S"),
    ("123", "123A", "123S"),
    ("124", "124A", "124S"),
)


@dataclass(frozen=True)
class RoomPricingResult:
    branch_code: str
    version: str
    already_applied: bool
    before: dict[str, object]
    after: dict[str, object]


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


def _snapshot(db: Session, branch_id: int) -> dict[str, object]:
    from app.modules.pms.models import RoomBundle, RoomType

    room_types = {
        row.name: {"base_rate": row.base_rate, "max_occupancy": row.max_occupancy}
        for row in db.query(RoomType).filter(RoomType.branch_id == branch_id).all()
    }
    bundle_count = int(
        db.query(func.count(RoomBundle.id)).filter(RoomBundle.branch_id == branch_id).scalar() or 0
    )
    return {"room_types": room_types, "room_bundles": bundle_count}


def _require_real_inventory(db: Session, branch_id: int) -> dict[str, "Room"]:  # noqa: F821
    """يتأكد إن الوحدات الـ14 المعتمدة (real_room_inventory) موجودة فعلًا،
    ويرجّع dict {room_name: Room} — بدون كده مفيش أي معنى لتفعيل تسعير على
    غرف مش موجودة."""
    from app.modules.pms.models import Room

    rooms = {
        room.name: room
        for room in db.query(Room).filter(Room.branch_id == branch_id).all()
    }
    expected_names = {name for _, a, s in APPROVED_PAIRS for name in (a, s)}
    missing = expected_names - set(rooms)
    if missing:
        raise RuntimeError(
            "Real room inventory is missing units required for the approved "
            f"pairs: {sorted(missing)} — run app.real_room_inventory first"
        )
    return rooms


def _matches_activated_pricing(db: Session, branch_id: int) -> bool:
    from app.modules.pms.models import RoomBundle, RoomType

    room_types = {
        row.name: row
        for row in db.query(RoomType).filter(RoomType.branch_id == branch_id).all()
    }
    if set(room_types) != {"Chalet", "Studio"}:
        return False
    if room_types["Studio"].base_rate != STUDIO_BASE_RATE:
        return False
    if room_types["Studio"].max_occupancy != STUDIO_MAX_OCCUPANCY:
        return False
    if room_types["Chalet"].base_rate != CHALET_BASE_RATE:
        return False
    if room_types["Chalet"].max_occupancy != CHALET_MAX_OCCUPANCY:
        return False

    bundles = {
        (b.chalet_room.name, b.studio_room.name): b
        for b in db.query(RoomBundle).filter(RoomBundle.branch_id == branch_id).all()
    }
    expected = {(a, s) for _, a, s in APPROVED_PAIRS}
    if set(bundles) != expected:
        return False
    return all(
        b.price == BUNDLE_PRICE and b.max_occupancy == BUNDLE_MAX_OCCUPANCY and b.is_active
        for b in bundles.values()
    )


def activate_room_pricing(
    db: Session,
    *,
    expected_branch_code: str,
    actor_id: int | None = None,
) -> RoomPricingResult:
    """Stage the reviewed approved-pricing activation in the caller's transaction."""
    environment = (settings.ENVIRONMENT or "").strip().lower()
    if environment not in {"production", "test", "testing"}:
        raise RuntimeError("The approved room pricing tool is restricted to production/test")

    _acquire_lock(db)
    branch, actor = _resolve_scope(db, expected_branch_code, actor_id)
    before = _snapshot(db, branch.id)
    marker = _existing_marker(db, branch.id)
    if marker:
        if not _matches_activated_pricing(db, branch.id):
            raise RuntimeError("The pricing audit marker exists but pricing has drifted")
        return RoomPricingResult(branch.code, DATASET_VERSION, True, before, before.copy())

    rooms = _require_real_inventory(db, branch.id)

    from app.modules.core.models import AuditLog
    from app.modules.pms.models import RoomBundle, RoomType

    room_types = {
        row.name: row
        for row in db.query(RoomType).filter(RoomType.branch_id == branch.id).all()
    }
    if set(room_types) != {"Chalet", "Studio"}:
        raise RuntimeError(f"Expected exactly Chalet+Studio room types; found {sorted(room_types)}")

    stray_bundle = db.query(RoomBundle).filter(RoomBundle.branch_id == branch.id).first()
    if stray_bundle:
        raise RuntimeError(
            "Unexpected pre-existing room_bundles row without an audit marker — "
            "investigate before activating pricing"
        )

    room_types["Studio"].base_rate = STUDIO_BASE_RATE
    room_types["Studio"].max_occupancy = STUDIO_MAX_OCCUPANCY
    room_types["Chalet"].base_rate = CHALET_BASE_RATE
    room_types["Chalet"].max_occupancy = CHALET_MAX_OCCUPANCY
    db.flush()

    for pair_number, chalet_name, studio_name in APPROVED_PAIRS:
        db.add(RoomBundle(
            branch_id=branch.id,
            name=f"Family Compound 6P ({pair_number})",
            name_ar=f"كومباوند عائلي 6 أفراد ({pair_number})",
            chalet_room_id=rooms[chalet_name].id,
            studio_room_id=rooms[studio_name].id,
            max_occupancy=BUNDLE_MAX_OCCUPANCY,
            price=BUNDLE_PRICE,
            is_active=True,
        ))
    db.flush()

    after = _snapshot(db, branch.id)
    if after["room_bundles"] != len(APPROVED_PAIRS):
        raise RuntimeError(f"Bundle count mismatch after activation: {after}")

    db.add(
        AuditLog(
            user_id=actor.id,
            branch_id=branch.id,
            action=MARKER_ACTION,
            entity_type=MARKER_ENTITY,
            entity_id=branch.id,
            old_data=json.dumps(before, sort_keys=True, default=str),
            new_data=json.dumps(
                {
                    "version": DATASET_VERSION,
                    "room_types": {
                        "Studio": {"base_rate": str(STUDIO_BASE_RATE), "max_occupancy": STUDIO_MAX_OCCUPANCY},
                        "Chalet": {"base_rate": str(CHALET_BASE_RATE), "max_occupancy": CHALET_MAX_OCCUPANCY},
                    },
                    "bundles": [
                        {"pair": pair, "chalet": a, "studio": s, "price": str(BUNDLE_PRICE)}
                        for pair, a, s in APPROVED_PAIRS
                    ],
                    "source": "Mohamed-approved pricing, OPS-DATA-02 §3, 2026-08-10",
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            ip_address="127.0.0.1",
            user_agent="app.approved_room_pricing",
            approved_by=actor.id,
        )
    )
    db.flush()
    return RoomPricingResult(branch.code, DATASET_VERSION, False, before, after)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run or apply the approved El Kheima room pricing + Family Compound bundles."
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
            result = activate_room_pricing(
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
                    default=str,
                )
            )
            return 0
        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    raise SystemExit(main())
