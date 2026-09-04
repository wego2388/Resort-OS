from __future__ import annotations

import subprocess
import sys
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def test_cli_import_registers_audit_log_user_foreign_key():
    """The standalone CLI must load every table required by its AuditLog row."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from scripts.disable_beach_vat import AuditLog; "
                "from app.core.database import Base; "
                "assert 'users' in Base.metadata.tables; "
                "fk = next(fk for fk in AuditLog.__table__.foreign_keys "
                "if fk.parent.name == 'approved_by'); "
                "assert fk.column.table.name == 'users'"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture
def isolated_db():
    from app.core.database import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _fixture(db):
    from app.modules.beach.models import BeachTransaction
    from app.modules.core.models import Branch
    from app.modules.dining.models import DiningOrder, Outlet
    from app.modules.finance.models import (
        Account,
        CashierShift,
        JournalEntry,
        JournalLine,
        Payment,
    )
    from scripts.disable_beach_vat import EXPECTED_BRANCH_NAME

    db.query(Branch).update({Branch.is_active: False}, synchronize_session=False)
    branch = Branch(
        name=EXPECTED_BRANCH_NAME,
        name_ar="منتجع الخيمة بيتش",
        code=f"VAT-{uuid.uuid4().hex[:8].upper()}",
        is_active=True,
    )
    db.add(branch)
    db.flush()

    cash = Account(branch_id=branch.id, code="1100", name="Cash", account_type="asset")
    revenue = Account(branch_id=branch.id, code="4300", name="Beach", account_type="revenue")
    vat = Account(branch_id=branch.id, code="2160", name="VAT", account_type="liability")
    real_restaurant = Outlet(
        branch_id=branch.id, name="Restaurant", name_ar="المطعم",
        outlet_type="restaurant", revenue_account_code="4200", is_active=True,
    )
    real_cafe = Outlet(
        branch_id=branch.id, name="Cafe", name_ar="الكافيه",
        outlet_type="cafe", revenue_account_code="4400", is_active=True,
    )
    hist_restaurant = Outlet(
        branch_id=branch.id, name="Restaurant HIST", name_ar="مطعم HIST",
        outlet_type="restaurant", revenue_account_code="4200", is_active=True,
    )
    hist_cafe = Outlet(
        branch_id=branch.id, name="Cafe HIST", name_ar="كافيه HIST",
        outlet_type="cafe", revenue_account_code="4400", is_active=True,
    )
    shift = CashierShift(
        branch_id=branch.id,
        cashier_id=2,
        opened_at=datetime(2026, 8, 15, 8, 0, tzinfo=timezone.utc),
        opened_by=2,
        opening_float=Decimal("0.00"),
        status="closed",
        closed_at=datetime(2026, 8, 15, 9, 0, tzinfo=timezone.utc),
        closed_by=2,
        expected_cash=Decimal("228.00"),
        counted_cash=Decimal("200.00"),
        variance=Decimal("-28.00"),
    )
    db.add_all([
        cash, revenue, vat, real_restaurant, real_cafe,
        hist_restaurant, hist_cafe, shift,
    ])
    db.flush()

    tx = BeachTransaction(
        branch_id=branch.id,
        tx_type="entry",
        quantity=1,
        unit_price=Decimal("200.00"),
        total_amount=Decimal("200.00"),
        discount_amount=Decimal("0.00"),
        vat_amount=Decimal("28.00"),
        surge_applied=False,
        tx_date=date(2026, 8, 15),
        cashier_id=2,
        shift_id=shift.id,
        payment_method="cash",
    )
    db.add(tx)
    db.flush()
    dangling_hist_order = DiningOrder(
        branch_id=branch.id,
        outlet_id=hist_restaurant.id,
        order_number=f"ORD-HIST-{uuid.uuid4().hex[:8].upper()}",
        status="open",
        order_type="dine_in",
        subtotal=Decimal("0.00"),
        vat_amount=Decimal("0.00"),
        service_charge=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total=Decimal("0.00"),
    )
    db.add(dangling_hist_order)
    db.flush()
    payment = Payment(
        branch_id=branch.id,
        folio_id=None,
        amount=Decimal("228.00"),
        currency="EGP",
        fx_rate=Decimal("1.00"),
        method="cash",
        reference=f"BCH-{tx.id:06d}",
        posted_at=datetime(2026, 8, 15, 8, 30, tzinfo=timezone.utc),
        cashier_id=2,
        shift_id=shift.id,
        source=None,  # legacy Beach payments predate the explicit source field
    )
    journal = JournalEntry(
        branch_id=branch.id,
        entry_date=date(2026, 8, 15),
        reference=f"BCH-{tx.id:06d}",
        description="Legacy Beach sale with VAT",
        status="posted",
        created_by=0,
        source="beach",
        source_id=tx.id,
    )
    db.add_all([payment, journal])
    db.flush()
    db.add_all([
        JournalLine(entry_id=journal.id, account_id=cash.id, debit=Decimal("228.00"), credit=0),
        JournalLine(entry_id=journal.id, account_id=revenue.id, debit=0, credit=Decimal("200.00")),
        JournalLine(entry_id=journal.id, account_id=vat.id, debit=0, credit=Decimal("28.00")),
    ])
    db.commit()
    return (
        branch, tx, payment, shift, journal, real_restaurant, real_cafe,
        hist_restaurant, hist_cafe, vat, dangling_hist_order,
    )


def test_dry_run_then_apply_reconciles_beach_and_archives_hist_outlets(isolated_db):
    from app.modules.core.models import AuditLog
    from app.modules.finance.models import JournalLine
    from scripts.disable_beach_vat import apply_beach_no_vat_policy

    db = isolated_db
    (
        branch, tx, payment, shift, journal, real_restaurant, real_cafe,
        hist_restaurant, hist_cafe, vat, dangling_hist_order,
    ) = _fixture(db)

    with pytest.raises(ValueError, match="Transaction-count guard failed"):
        apply_beach_no_vat_policy(
            db,
            expected_transaction_count=2,
            expected_payment_count=1,
            expected_outlet_count=2,
            expected_hist_active_order_count=1,
            apply=False,
            reason=None,
        )
    db.rollback()

    dry_run = apply_beach_no_vat_policy(
        db,
        expected_transaction_count=1,
        expected_payment_count=1,
        expected_outlet_count=2,
        expected_hist_active_order_count=1,
        apply=False,
        reason=None,
    )
    assert dry_run.applied is False
    assert dry_run.total_vat_removed == "28.00"
    db.expire_all()
    assert db.get(type(tx), tx.id).vat_amount == Decimal("28.00")
    assert db.get(type(payment), payment.id).amount == Decimal("228.00")

    applied = apply_beach_no_vat_policy(
        db,
        expected_transaction_count=1,
        expected_payment_count=1,
        expected_outlet_count=2,
        expected_hist_active_order_count=1,
        apply=True,
        reason="Approved Beach final-price policy and HIST outlet cleanup",
    )
    assert applied.applied is True
    db.expire_all()

    assert db.get(type(tx), tx.id).vat_amount == Decimal("0.00")
    assert db.get(type(payment), payment.id).amount == Decimal("200.00")
    assert db.get(type(payment), payment.id).source == "beach"
    repaired_shift = db.get(type(shift), shift.id)
    assert repaired_shift.expected_cash == Decimal("200.00")
    assert repaired_shift.counted_cash == Decimal("200.00")
    assert repaired_shift.variance == Decimal("0.00")

    lines = db.query(JournalLine).filter(JournalLine.entry_id == journal.id).all()
    assert len(lines) == 2
    assert sum((row.debit for row in lines), Decimal(0)) == Decimal("200.00")
    assert sum((row.credit for row in lines), Decimal(0)) == Decimal("200.00")
    assert all(row.account_id != vat.id for row in lines)

    assert db.get(type(real_restaurant), real_restaurant.id).is_active is True
    assert db.get(type(real_cafe), real_cafe.id).is_active is True
    assert db.get(type(hist_restaurant), hist_restaurant.id).is_active is False
    assert db.get(type(hist_cafe), hist_cafe.id).is_active is False
    assert db.get(type(dangling_hist_order), dangling_hist_order.id).status == "cancelled"
    assert db.query(AuditLog).filter_by(
        action="beach_vat_disabled_hist_outlets_archived",
        branch_id=branch.id,
    ).count() == 1
