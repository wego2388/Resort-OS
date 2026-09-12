"""Read-only owner mall summary backed by the existing Leasing truth.

The physical mall-unit registry is intentionally not inferred from lease
contracts: a contract proves an occupied lease, never the total/vacant unit
inventory or the map geometry. Until approved master data is imported, this
service returns real financial/contract information and explicit unknowns.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.modules.finance.models import Payment
from app.modules.leasing.models import LeaseContract, LeasePayment, TenantCashLog
from app.modules.owner._services._helpers import (
    _cairo_today,
    _is_period_provisional,
    _utc_date_bounds,
)
from app.modules.owner.schemas import (
    OwnerMallContractSummary,
    OwnerMallSummaryResponse,
    PeriodMeta,
)


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def get_mall_summary(db: Session, branch_id: int) -> OwnerMallSummaryResponse:
    """Return branch-scoped mall facts without tenant PII or fake occupancy."""

    today = _cairo_today()
    period_from = today.replace(day=1)
    period_to = today
    range_start, range_end = _utc_date_bounds(period_from, period_to)

    contracts = (
        db.query(LeaseContract)
        .filter(LeaseContract.branch_id == branch_id)
        .options(selectinload(LeaseContract.payments))
        .order_by(LeaseContract.end_date, LeaseContract.id)
        .all()
    )
    active_contract_count = sum(1 for contract in contracts if contract.status == "active")
    expiry_horizon = today + timedelta(days=30)
    expiring_within_30_days = sum(
        1
        for contract in contracts
        if contract.status == "active" and today <= contract.end_date <= expiry_horizon
    )

    scheduled_rent = _money(
        db.query(func.sum(LeasePayment.amount))
        .join(LeaseContract, LeaseContract.id == LeasePayment.contract_id)
        .filter(
            LeaseContract.branch_id == branch_id,
            LeaseContract.status == "active",
            LeasePayment.due_date >= period_from,
            LeasePayment.due_date <= period_to,
        )
        .scalar()
    )
    accrued_rent = _money(
        db.query(func.sum(LeasePayment.amount))
        .join(LeaseContract, LeaseContract.id == LeasePayment.contract_id)
        .filter(
            LeaseContract.branch_id == branch_id,
            LeasePayment.due_date >= period_from,
            LeasePayment.due_date <= period_to,
            LeasePayment.accrued.is_(True),
        )
        .scalar()
    )

    # Normal scheduled receipts and direct rent/revenue-share cash logs are
    # separate flows. Deposits, penalties, maintenance and refunds are excluded.
    scheduled_collected = _money(
        db.query(func.sum(Payment.amount))
        .join(LeasePayment, LeasePayment.id == Payment.ref_order_id)
        .join(LeaseContract, LeaseContract.id == LeasePayment.contract_id)
        .filter(
            Payment.source == "leasing_rent",
            Payment.branch_id == branch_id,
            Payment.voided_at.is_(None),
            Payment.posted_at >= range_start,
            Payment.posted_at < range_end,
            LeaseContract.branch_id == branch_id,
        )
        .scalar()
    )
    direct_collected = _money(
        db.query(func.sum(Payment.amount))
        .join(TenantCashLog, TenantCashLog.id == Payment.ref_order_id)
        .filter(
            Payment.source == "leasing_cash_log",
            Payment.branch_id == branch_id,
            Payment.voided_at.is_(None),
            Payment.posted_at >= range_start,
            Payment.posted_at < range_end,
            TenantCashLog.branch_id == branch_id,
            TenantCashLog.activity_type.in_(("rent_payment", "revenue_share")),
        )
        .scalar()
    )

    overdue_receivables = _money(
        db.query(
            func.sum(LeasePayment.amount + LeasePayment.penalty - LeasePayment.paid_amount)
        )
        .join(LeaseContract, LeaseContract.id == LeasePayment.contract_id)
        .filter(
            LeaseContract.branch_id == branch_id,
            LeasePayment.due_date < today,
            LeasePayment.status.in_(("pending", "partial", "overdue")),
        )
        .scalar()
    )

    contract_rows: list[OwnerMallContractSummary] = []
    for contract in contracts:
        scheduled_to_date = sum(
            (payment.amount for payment in contract.payments if payment.due_date <= today),
            start=Decimal(0),
        )
        paid_to_date = sum(
            (payment.paid_amount for payment in contract.payments),
            start=Decimal(0),
        )
        due_outstanding = sum(
            (
                payment.amount + payment.penalty - payment.paid_amount
                for payment in contract.payments
                if payment.due_date <= today
                and payment.status in ("pending", "partial", "overdue")
            ),
            start=Decimal(0),
        )
        contract_rows.append(OwnerMallContractSummary(
            contract_id=contract.id,
            contract_number=contract.contract_number,
            unit_description=contract.unit_description,
            status=contract.status,
            start_date=contract.start_date,
            end_date=contract.end_date,
            days_until_expiry=(contract.end_date - today).days,
            scheduled_to_date=_money(scheduled_to_date),
            paid_to_date=_money(paid_to_date),
            due_outstanding=_money(due_outstanding),
        ))

    computed_at = datetime.now(timezone.utc)
    return OwnerMallSummaryResponse(
        branch_id=branch_id,
        registry_ready=False,
        map_available=False,
        registered_unit_count=None,
        occupied_unit_count=None,
        vacant_unit_count=None,
        occupancy_pct=None,
        total_contract_count=len(contracts),
        active_contract_count=active_contract_count,
        expiring_within_30_days=expiring_within_30_days,
        scheduled_rent=scheduled_rent,
        accrued_rent=accrued_rent,
        collected_rent=_money(scheduled_collected + direct_collected),
        overdue_receivables=overdue_receivables,
        period=PeriodMeta(
            date_from=period_from,
            date_to=period_to,
            is_provisional=_is_period_provisional(db, branch_id, period_to),
            computed_at=computed_at,
        ),
        contracts=contract_rows,
    )
