"""Controlled activation of Mohamed's approved Beach Scoops menu.

The command is dry-run by default, writes only one new Cafe category, uses a
transaction/advisory lock, and records one attributable audit marker. Prices
are the final customer-facing amounts and therefore set
``price_includes_vat_service=True``; order creation separates VAT/service from
inside those amounts instead of adding them again.

Run inside the backend container::

    python -m app.approved_ice_cream_menu --branch-code ELK-001 --outlet-name Cafe
    python -m app.approved_ice_cream_menu --branch-code ELK-001 --outlet-name Cafe \
      --apply --confirm "ACTIVATE EL KHEIMA ICE CREAM MENU"
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

DATASET_VERSION = "2026-08-12.1"
MARKER_ACTION = "approved_ice_cream_menu_activated"
MARKER_ENTITY = "dining_menu"
CONFIRMATION_PHRASE = "ACTIVATE EL KHEIMA ICE CREAM MENU"
_ADVISORY_LOCK_KEY = 4_502_026_081_812

FROZEN_FRUIT_PRICE = Decimal("50.00")
PACKAGED_ICE_CREAM_PRICE = Decimal("70.00")
SCOOP_PRICE = Decimal("50.00")
SAUCE_PRICE = Decimal("15.00")
TOPPING_PRICE = Decimal("30.00")

# sort, English, Arabic, Russian, Italian, final price, family EN/AR
PACKAGED_ITEMS: tuple[tuple[int, str, str, str, str, Decimal, str, str], ...] = (
    (
        1,
        "Nestle Squizz Up Mango",
        "نستله سكويز أب مانجو",
        "Nestle Squizz Up Mango",
        "Nestle Squizz Up Mango",
        FROZEN_FRUIT_PRICE,
        "Frozen Fruits",
        "فواكه مجمدة",
    ),
    (
        2,
        "Nestle Squizz Up Mixed Berries",
        "نستله سكويز أب توت مشكل",
        "Nestle Squizz Up Mixed Berries",
        "Nestle Squizz Up Mixed Berries",
        FROZEN_FRUIT_PRICE,
        "Frozen Fruits",
        "فواكه مجمدة",
    ),
    (
        3,
        "Nestle Squizz Mango",
        "نستله سكويز مانجو",
        "Nestle Squizz Mango",
        "Nestle Squizz Mango",
        FROZEN_FRUIT_PRICE,
        "Frozen Fruits",
        "فواكه مجمدة",
    ),
    (
        4,
        "Nestle Squizz Mixed Berries",
        "نستله سكويز توت مشكل",
        "Nestle Squizz Mixed Berries",
        "Nestle Squizz Mixed Berries",
        FROZEN_FRUIT_PRICE,
        "Frozen Fruits",
        "فواكه مجمدة",
    ),
    (
        5,
        "Cadbury Dairy Milk Cone",
        "كون كادبوري ديري ميلك",
        "Cadbury Dairy Milk Cone",
        "Cono Cadbury Dairy Milk",
        PACKAGED_ICE_CREAM_PRICE,
        "Cones",
        "كون آيس كريم",
    ),
    (
        6,
        "Cadbury Flake 99 Cone",
        "كون كادبوري فليك 99",
        "Cadbury Flake 99 Cone",
        "Cono Cadbury Flake 99",
        PACKAGED_ICE_CREAM_PRICE,
        "Cones",
        "كون آيس كريم",
    ),
    (
        7,
        "KitKat Cone",
        "كون كيت كات",
        "KitKat Cone",
        "Cono KitKat",
        PACKAGED_ICE_CREAM_PRICE,
        "Cones",
        "كون آيس كريم",
    ),
    (
        8,
        "Nestle Brownies Extreme Cone",
        "كون نستله براونيز إكستريم",
        "Nestle Brownies Extreme Cone",
        "Cono Nestle Brownies Extreme",
        PACKAGED_ICE_CREAM_PRICE,
        "Cones",
        "كون آيس كريم",
    ),
    (
        9,
        "KitKat Ice Cream Stick",
        "آيس كريم ستيك كيت كات",
        "KitKat Ice Cream Stick",
        "Stecco KitKat",
        PACKAGED_ICE_CREAM_PRICE,
        "Ice Cream Sticks",
        "آيس كريم ستيك",
    ),
    (
        10,
        "Cadbury Dairy Milk Ice Cream Stick",
        "آيس كريم ستيك كادبوري ديري ميلك",
        "Cadbury Dairy Milk Ice Cream Stick",
        "Stecco Cadbury Dairy Milk",
        PACKAGED_ICE_CREAM_PRICE,
        "Ice Cream Sticks",
        "آيس كريم ستيك",
    ),
    (
        11,
        "Mega Blackberry Yogurt Stick",
        "ميجا زبادي بالتوت الأسود ستيك",
        "Mega Blackberry Yogurt Stick",
        "Stecco Mega yogurt e mora",
        PACKAGED_ICE_CREAM_PRICE,
        "Ice Cream Sticks",
        "آيس كريم ستيك",
    ),
    (
        12,
        "Mega Chocolate Stick",
        "ميجا شوكولاتة ستيك",
        "Mega Chocolate Stick",
        "Stecco Mega cioccolato",
        PACKAGED_ICE_CREAM_PRICE,
        "Ice Cream Sticks",
        "آيس كريم ستيك",
    ),
    (
        13,
        "Mega White Chocolate Vanilla Stick",
        "ميجا شوكولاتة بيضاء وفانيليا ستيك",
        "Mega White Chocolate Vanilla Stick",
        "Stecco Mega cioccolato bianco e vaniglia",
        PACKAGED_ICE_CREAM_PRICE,
        "Ice Cream Sticks",
        "آيس كريم ستيك",
    ),
    (
        14,
        "Mega Mango Vanilla Crunch Stick",
        "ميجا مانجو وفانيليا كرانش ستيك",
        "Mega Mango Vanilla Crunch Stick",
        "Stecco Mega mango e vaniglia crunch",
        PACKAGED_ICE_CREAM_PRICE,
        "Ice Cream Sticks",
        "آيس كريم ستيك",
    ),
    (
        15,
        "Mega Vanilla Stick",
        "ميجا فانيليا ستيك",
        "Mega Vanilla Stick",
        "Stecco Mega vaniglia",
        PACKAGED_ICE_CREAM_PRICE,
        "Ice Cream Sticks",
        "آيس كريم ستيك",
    ),
    (
        16,
        "Oreo Ice Cream Sandwich",
        "ساندوتش آيس كريم أوريو",
        "Oreo Ice Cream Sandwich",
        "Sandwich gelato Oreo",
        PACKAGED_ICE_CREAM_PRICE,
        "Ice Cream Sandwiches",
        "ساندوتش آيس كريم",
    ),
    (
        17,
        "Dolce Cookie Cream Sandwich",
        "ساندوتش دولتشي كوكي كريم",
        "Dolce Cookie Cream Sandwich",
        "Sandwich Dolce Cookie Cream",
        PACKAGED_ICE_CREAM_PRICE,
        "Ice Cream Sandwiches",
        "ساندوتش آيس كريم",
    ),
)

SCOOP_VARIANTS: tuple[tuple[str, str], ...] = (
    ("Vanilla", "فانيليا"),
    ("Strawberry", "فراولة"),
    ("Mango", "مانجو"),
    ("Chocolate", "شوكولاتة"),
    ("Mixed Berries", "توت مشكل"),
    ("Bubble Gum", "لبان"),
    ("Berry Yogurt", "زبادي بالتوت"),
)
SAUCES: tuple[tuple[str, str], ...] = (
    ("Strawberry Sauce", "صوص فراولة"),
    ("Chocolate Sauce", "صوص شوكولاتة"),
    ("Caramel Sauce", "صوص كراميل"),
)
TOPPINGS: tuple[tuple[str, str], ...] = (
    ("Cookies", "كوكيز"),
    ("Sprinkles", "سبرنكلز"),
    ("Chocolate Chips", "شوكولاتة شيبس"),
)


@dataclass(frozen=True)
class IceCreamMenuResult:
    branch_code: str
    outlet_name: str
    version: str
    already_applied: bool
    before: dict[str, object]
    after: dict[str, object]


def _acquire_lock(db: Session) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": _ADVISORY_LOCK_KEY}
        )


def _resolve_scope(
    db: Session, branch_code: str, outlet_name: str, actor_id: int | None
):
    from app.core.kernel.models.user import User
    from app.modules.core.models import Branch
    from app.modules.dining.models import Outlet

    branch = (
        db.query(Branch)
        .filter(Branch.code == branch_code, Branch.is_active.is_(True))
        .one_or_none()
    )
    if branch is None:
        raise RuntimeError(f"Active branch {branch_code!r} was not found")
    outlets = (
        db.query(Outlet)
        .filter(
            Outlet.branch_id == branch.id,
            Outlet.outlet_type == "cafe",
            Outlet.name == outlet_name,
            Outlet.is_active.is_(True),
        )
        .all()
    )
    if len(outlets) != 1:
        raise RuntimeError(
            f"Expected exactly one active Cafe outlet named {outlet_name!r}; "
            f"found {len(outlets)}"
        )

    query = db.query(User).filter(User.is_active.is_(True))
    if actor_id is not None:
        query = query.filter(User.id == actor_id)
    actors = [
        u for u in query.all() if getattr(u.role, "value", u.role) == "super_admin"
    ]
    if len(actors) != 1:
        raise RuntimeError(
            "Resolve exactly one active super_admin actor, or pass --actor-id"
        )
    return branch, outlets[0], actors[0]


def _marker(db: Session, branch_id: int, outlet_id: int):
    from app.modules.core.models import AuditLog

    return (
        db.query(AuditLog)
        .filter(
            AuditLog.branch_id == branch_id,
            AuditLog.action == MARKER_ACTION,
            AuditLog.entity_type == MARKER_ENTITY,
            AuditLog.entity_id == outlet_id,
        )
        .order_by(AuditLog.id.desc())
        .first()
    )


def _snapshot(db: Session, outlet_id: int) -> dict[str, object]:
    from app.modules.dining.models import DiningCategory, DiningItem

    category = (
        db.query(DiningCategory)
        .filter(
            DiningCategory.outlet_id == outlet_id,
            DiningCategory.name == "Ice Cream",
        )
        .one_or_none()
    )
    item_count = 0
    if category is not None:
        item_count = int(
            db.query(func.count(DiningItem.id))
            .filter(DiningItem.category_id == category.id)
            .scalar()
            or 0
        )
    return {"category_id": category.id if category else None, "item_count": item_count}


def _matches(db: Session, outlet_id: int) -> bool:
    from app.modules.dining.models import DiningCategory, DiningItem

    category = (
        db.query(DiningCategory)
        .filter(
            DiningCategory.outlet_id == outlet_id,
            DiningCategory.name == "Ice Cream",
            DiningCategory.is_active.is_(True),
        )
        .one_or_none()
    )
    if category is None or (
        category.name_ar,
        category.name_ru,
        category.name_it,
    ) != ("آيس كريم", "Мороженое", "Gelato"):
        return False
    items = {
        i.name: i
        for i in db.query(DiningItem)
        .filter(DiningItem.category_id == category.id)
        .all()
    }
    expected = {row[1] for row in PACKAGED_ITEMS} | {"Ice Cream Scoop"}
    if set(items) != expected:
        return False
    for (
        sort_order,
        name,
        name_ar,
        name_ru,
        name_it,
        price,
        family,
        family_ar,
    ) in PACKAGED_ITEMS:
        item = items[name]
        if (
            item.price != price
            or item.name_ar != name_ar
            or item.name_ru != name_ru
            or item.name_it != name_it
            or item.description != family
            or item.description_ar != family_ar
            or not item.price_includes_vat_service
            or not item.is_available
            or item.station != "bar"
            or item.preparation_minutes != 0
            or item.sort_order != sort_order
        ):
            return False
    scoop = items["Ice Cream Scoop"]
    if (
        scoop.price != SCOOP_PRICE
        or scoop.name_ar != "سكوب آيس كريم"
        or scoop.name_ru != "Шарик мороженого"
        or scoop.name_it != "Pallina di gelato"
        or not scoop.price_includes_vat_service
        or not scoop.is_available
        or scoop.station != "bar"
        or scoop.preparation_minutes != 3
        or scoop.sort_order != 18
    ):
        return False
    if {
        (v.name, v.name_ar, v.price, v.sort_order, v.is_available)
        for v in scoop.variants
    } != {
        (name, name_ar, SCOOP_PRICE, sort_order, True)
        for sort_order, (name, name_ar) in enumerate(SCOOP_VARIANTS, start=1)
    }:
        return False
    groups = {group.name: group for group in scoop.extra_groups}
    if set(groups) != {"Sauces", "Toppings"}:
        return False
    group_specs = (
        (groups["Sauces"], "الصوصات", SAUCES, SAUCE_PRICE, 1),
        (groups["Toppings"], "الإضافات", TOPPINGS, TOPPING_PRICE, 2),
    )
    for group, name_ar, options, price, sort_order in group_specs:
        if (
            group.name_ar != name_ar
            or group.group_type != "pick_list"
            or group.min_select != 0
            or group.max_select != 3
            or group.sort_order != sort_order
        ):
            return False
        if {
            (
                option.name,
                option.name_ar,
                option.price_addition,
                option.sort_order,
                option.is_available,
            )
            for option in group.options
        } != {
            (name, option_name_ar, price, option_sort, True)
            for option_sort, (name, option_name_ar) in enumerate(options, start=1)
        }:
            return False
    return True


def activate_ice_cream_menu(
    db: Session,
    *,
    expected_branch_code: str,
    outlet_name: str,
    actor_id: int | None = None,
) -> IceCreamMenuResult:
    environment = (settings.ENVIRONMENT or "").strip().lower()
    if environment not in {"production", "test", "testing"}:
        raise RuntimeError(
            "The approved ice-cream tool is restricted to production/test"
        )

    _acquire_lock(db)
    branch, outlet, actor = _resolve_scope(
        db, expected_branch_code, outlet_name, actor_id
    )
    before = _snapshot(db, outlet.id)
    marker = _marker(db, branch.id, outlet.id)
    if marker:
        if not _matches(db, outlet.id):
            raise RuntimeError(
                "The ice-cream audit marker exists but the catalogue has drifted"
            )
        return IceCreamMenuResult(
            branch.code, outlet.name, DATASET_VERSION, True, before, before.copy()
        )
    if before["category_id"] is not None:
        raise RuntimeError(
            "An Ice Cream category exists without the approved audit marker; "
            "investigate first"
        )

    from app.modules.core.models import AuditLog
    from app.modules.dining.models import (
        DiningCategory,
        DiningItem,
        DiningItemExtra,
        DiningItemExtraGroup,
        DiningItemVariant,
    )

    max_sort = (
        db.query(func.max(DiningCategory.sort_order))
        .filter(DiningCategory.outlet_id == outlet.id)
        .scalar()
    )
    category = DiningCategory(
        branch_id=branch.id,
        outlet_id=outlet.id,
        name="Ice Cream",
        name_ar="آيس كريم",
        name_ru="Мороженое",
        name_it="Gelato",
        sort_order=int(max_sort or 0) + 1,
        is_active=True,
    )
    db.add(category)
    db.flush()

    for (
        sort_order,
        name,
        name_ar,
        name_ru,
        name_it,
        price,
        family,
        family_ar,
    ) in PACKAGED_ITEMS:
        db.add(
            DiningItem(
                branch_id=branch.id,
                outlet_id=outlet.id,
                category_id=category.id,
                name=name,
                name_ar=name_ar,
                name_ru=name_ru,
                name_it=name_it,
                description=family,
                description_ar=family_ar,
                price=price,
                price_includes_vat_service=True,
                station="bar",
                preparation_minutes=0,
                sort_order=sort_order,
                is_available=True,
            )
        )

    scoop = DiningItem(
        branch_id=branch.id,
        outlet_id=outlet.id,
        category_id=category.id,
        name="Ice Cream Scoop",
        name_ar="سكوب آيس كريم",
        name_ru="Шарик мороженого",
        name_it="Pallina di gelato",
        description="Choose one flavor; final price per scoop",
        description_ar="اختر نكهة واحدة؛ السعر النهائي للسكوب الواحد",
        price=SCOOP_PRICE,
        price_includes_vat_service=True,
        station="bar",
        preparation_minutes=3,
        sort_order=18,
        is_available=True,
    )
    db.add(scoop)
    db.flush()
    for sort_order, (name, name_ar) in enumerate(SCOOP_VARIANTS, start=1):
        db.add(
            DiningItemVariant(
                item_id=scoop.id,
                name=name,
                name_ar=name_ar,
                price=SCOOP_PRICE,
                sort_order=sort_order,
                is_available=True,
            )
        )

    for group_sort, (group_name, group_name_ar, options, price) in enumerate(
        (
            ("Sauces", "الصوصات", SAUCES, SAUCE_PRICE),
            ("Toppings", "الإضافات", TOPPINGS, TOPPING_PRICE),
        ),
        start=1,
    ):
        group = DiningItemExtraGroup(
            item_id=scoop.id,
            name=group_name,
            name_ar=group_name_ar,
            group_type="pick_list",
            min_select=0,
            max_select=3,
            sort_order=group_sort,
        )
        db.add(group)
        db.flush()
        for option_sort, (name, name_ar) in enumerate(options, start=1):
            db.add(
                DiningItemExtra(
                    group_id=group.id,
                    name=name,
                    name_ar=name_ar,
                    price_addition=price,
                    is_available=True,
                    sort_order=option_sort,
                )
            )
    db.flush()

    after = _snapshot(db, outlet.id)
    if after["item_count"] != len(PACKAGED_ITEMS) + 1 or not _matches(db, outlet.id):
        raise RuntimeError(f"Ice-cream catalogue verification failed: {after}")

    db.add(
        AuditLog(
            user_id=actor.id,
            branch_id=branch.id,
            action=MARKER_ACTION,
            entity_type=MARKER_ENTITY,
            entity_id=outlet.id,
            old_data=json.dumps(before, sort_keys=True, default=str),
            new_data=json.dumps(
                {
                    "version": DATASET_VERSION,
                    "category": "Ice Cream",
                    "sellable_items": len(PACKAGED_ITEMS) + 1,
                    "scoop_variants": len(SCOOP_VARIANTS),
                    "sauces": len(SAUCES),
                    "toppings": len(TOPPINGS),
                    "prices_are_final": True,
                    "source": "Mohamed-approved Beach Scoops board, 2026-08-12",
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            ip_address="127.0.0.1",
            user_agent="app.approved_ice_cream_menu",
            approved_by=actor.id,
        )
    )
    db.flush()
    return IceCreamMenuResult(
        branch.code, outlet.name, DATASET_VERSION, False, before, after
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run or activate the approved El Kheima ice-cream menu."
    )
    parser.add_argument("--branch-code", required=True)
    parser.add_argument("--outlet-name", required=True)
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
            result = activate_ice_cream_menu(
                db,
                expected_branch_code=args.branch_code,
                outlet_name=args.outlet_name,
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
                        "outlet_name": result.outlet_name,
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
