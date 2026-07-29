from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.kernel.models.user import User, UserRole
from app.core.kernel.security import get_password_hash
from app.modules.beach.models import B2BContract
from app.modules.core.models import AuditLog, Branch
from app.modules.crm.models import Activity
from app.modules.finance.models import JournalEntry
from app.modules.hr.models import Employee, PayrollRun
from app.modules.hub.models import HubOffer, HubPage
from app.modules.inventory.models import (
    PurchaseOrder,
    PurchaseOrderItem,
    StockMovement,
    Supplier,
)
from app.modules.leasing.models import LeasePayment
from app.modules.pms.models import Booking
from app.modules.timeshare.models import TimeshareInstallment
from app.production_demo_seed import (
    MARKER_ACTION,
    seed_production_demo_dataset,
)


@pytest.fixture
def demo_db() -> Session:
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
            email="demo-seed-actor@example.invalid",
            password_hash=get_password_hash("isolated-test-credential"),
            full_name="Demo Seed Test Actor",
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


def test_production_demo_seed_populates_catalogs_without_live_transactions(
    demo_db: Session,
) -> None:
    db = demo_db
    branch = _branch(db)
    user_count = db.query(User).count()

    result = seed_production_demo_dataset(
        db,
        expected_branch_code=branch.code,
        actor_id=1,
    )

    assert result.already_applied is False
    assert result.added["warehouses"] == 3
    assert result.added["suppliers"] == 6
    assert result.added["purchase_orders"] == 5
    assert result.added["purchase_requests"] == 3
    assert result.added["products"] >= 100
    assert result.added["stock_movements"] >= 100
    assert result.added["outlets"] == 2
    assert result.added["room_types"] == 5
    assert result.added["rooms"] == 52
    assert result.added["assets"] == 6

    assert db.query(User).count() == user_count
    assert db.query(Employee).count() == 0
    assert db.query(Booking).count() == 0
    assert db.query(JournalEntry).count() == 0
    assert db.query(PayrollRun).count() == 0
    assert db.query(LeasePayment).count() == 0
    assert db.query(TimeshareInstallment).count() == 0

    assert db.query(Activity).filter(Activity.status == "pending").count() == 0
    assert db.query(B2BContract).filter(B2BContract.is_active.is_(True)).count() == 0
    assert db.query(HubPage).filter(HubPage.is_published.is_(True)).count() == 0
    assert db.query(HubOffer).filter(HubOffer.is_active.is_(True)).count() == 0
    assert (
        db.query(PurchaseOrderItem).filter(PurchaseOrderItem.received_qty != 0).count()
        == 0
    )
    assert (
        db.query(PurchaseOrder)
        .filter(PurchaseOrder.status.in_(("partial", "received")))
        .count()
        == 0
    )
    assert (
        db.query(StockMovement)
        .filter(StockMovement.reference_type != "demo_seed")
        .count()
        == 0
    )
    assert all(
        supplier.phone is None and supplier.email is None
        for supplier in db.query(Supplier).all()
    )
    assert db.query(AuditLog).filter(AuditLog.action == MARKER_ACTION).count() == 1


def test_production_demo_seed_is_idempotent_after_audit_marker(
    demo_db: Session,
) -> None:
    db = demo_db
    branch = _branch(db)
    first = seed_production_demo_dataset(
        db,
        expected_branch_code=branch.code,
        actor_id=1,
    )
    db.flush()

    second = seed_production_demo_dataset(
        db,
        expected_branch_code=branch.code,
        actor_id=1,
    )

    assert first.already_applied is False
    assert second.already_applied is True
    assert second.added == {}
    assert db.query(AuditLog).filter(AuditLog.action == MARKER_ACTION).count() == 1


def test_production_demo_seed_refuses_branch_mismatch(demo_db: Session) -> None:
    db = demo_db
    _branch(db)

    try:
        seed_production_demo_dataset(
            db,
            expected_branch_code="WRONG",
            actor_id=1,
        )
    except RuntimeError as exc:
        assert "Branch mismatch" in str(exc)
    else:
        raise AssertionError("branch mismatch must fail closed")
