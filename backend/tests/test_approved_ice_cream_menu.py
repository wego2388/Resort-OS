from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.approved_ice_cream_menu import (
    MARKER_ACTION,
    PACKAGED_ITEMS,
    SAUCES,
    SCOOP_VARIANTS,
    TOPPINGS,
    activate_ice_cream_menu,
)
from app.core.database import Base
from app.core.kernel.models.user import User, UserRole
from app.core.kernel.security import get_password_hash
from app.modules.core.models import AuditLog, Branch
from app.modules.dining.models import DiningCategory, DiningItem, Outlet
from app.modules.dining.schemas import OrderCreate, OrderItemCreate
from app.modules.dining.services import create_order


@pytest.fixture
def ice_cream_db() -> Session:
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
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = factory()
    db.add(
        User(
            id=1,
            email="ice-cream-actor@example.invalid",
            password_hash=get_password_hash("isolated-test-credential"),
            full_name="Ice Cream Test Actor",
            role=UserRole.SUPER_ADMIN,
            is_active=True,
            two_factor_enabled=True,
        )
    )
    branch = Branch(
        name="El Kheima Beach Resort",
        name_ar="منتجع الخيمة بيتش",
        code="ELK-001",
        timezone="Africa/Cairo",
        is_active=True,
    )
    db.add(branch)
    db.flush()
    db.add(
        Outlet(
            branch_id=branch.id,
            name="Cafe",
            name_ar="الكافيه",
            outlet_type="cafe",
            revenue_account_code="4300",
            is_active=True,
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


def test_activation_creates_exact_catalogue_and_audit(ice_cream_db: Session) -> None:
    result = activate_ice_cream_menu(
        ice_cream_db,
        expected_branch_code="ELK-001",
        outlet_name="Cafe",
        actor_id=1,
    )
    ice_cream_db.commit()

    assert result.already_applied is False
    category = ice_cream_db.query(DiningCategory).filter_by(name="Ice Cream").one()
    items = ice_cream_db.query(DiningItem).filter_by(category_id=category.id).all()
    assert len(items) == len(PACKAGED_ITEMS) + 1 == 18
    assert all(item.price_includes_vat_service for item in items)
    scoop = next(item for item in items if item.name == "Ice Cream Scoop")
    assert len(scoop.variants) == len(SCOOP_VARIANTS) == 7
    assert (
        sum(len(group.options) for group in scoop.extra_groups)
        == len(SAUCES) + len(TOPPINGS)
        == 6
    )
    assert ice_cream_db.query(AuditLog).filter_by(action=MARKER_ACTION).count() == 1


def test_activation_is_idempotent(ice_cream_db: Session) -> None:
    activate_ice_cream_menu(
        ice_cream_db,
        expected_branch_code="ELK-001",
        outlet_name="Cafe",
        actor_id=1,
    )
    ice_cream_db.commit()
    second = activate_ice_cream_menu(
        ice_cream_db,
        expected_branch_code="ELK-001",
        outlet_name="Cafe",
        actor_id=1,
    )

    assert second.already_applied is True
    assert ice_cream_db.query(AuditLog).filter_by(action=MARKER_ACTION).count() == 1


def test_scoop_variant_sauce_and_topping_collect_exact_final_price(
    ice_cream_db: Session,
) -> None:
    db = ice_cream_db
    activate_ice_cream_menu(
        db,
        expected_branch_code="ELK-001",
        outlet_name="Cafe",
        actor_id=1,
    )
    db.commit()
    branch = db.query(Branch).filter_by(code="ELK-001").one()
    outlet = db.query(Outlet).filter_by(name="Cafe").one()
    scoop = db.query(DiningItem).filter_by(name="Ice Cream Scoop").one()
    vanilla = next(variant for variant in scoop.variants if variant.name == "Vanilla")
    chocolate = next(
        option
        for group in scoop.extra_groups
        for option in group.options
        if option.name == "Chocolate Sauce"
    )
    cookies = next(
        option
        for group in scoop.extra_groups
        for option in group.options
        if option.name == "Cookies"
    )
    payload = OrderCreate(
        outlet_id=outlet.id,
        order_type="takeaway",
        items=[
            OrderItemCreate(
                item_id=scoop.id,
                variant_id=vanilla.id,
                quantity=1,
                extra_ids=[chocolate.id, cookies.id],
            )
        ],
    )

    with (
        patch(
            "app.modules.core.services.get_effective_vat_percentage",
            return_value=Decimal("14"),
        ),
        patch(
            "app.modules.dining.services._service_charge_pct",
            return_value=Decimal("0.12"),
        ),
    ):
        order = create_order(db, branch.id, payload, waiter_id=1)

    assert order.total == Decimal("95.00")
    assert order.subtotal + order.vat_amount + order.service_charge == Decimal("95.00")
    assert order.items[0].listed_unit_price == Decimal("50.00")
    assert {extra.listed_price_addition for extra in order.items[0].extras} == {
        Decimal("15.00"),
        Decimal("30.00"),
    }
