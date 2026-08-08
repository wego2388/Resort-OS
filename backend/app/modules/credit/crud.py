"""Persistence helpers for personal credit accounts."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.credit.models import CreditAccount, CreditTransaction


def get_account(db: Session, account_id: int) -> CreditAccount | None:
    return db.query(CreditAccount).filter(CreditAccount.id == account_id).first()


def lock_account(db: Session, account_id: int, branch_id: int) -> CreditAccount | None:
    """Fresh NOWAIT row lock for every balance/status/limit mutation."""
    return (
        db.query(CreditAccount)
        .filter(CreditAccount.id == account_id, CreditAccount.branch_id == branch_id)
        .with_for_update(nowait=True)
        .execution_options(populate_existing=True)
        .first()
    )


def get_account_for_holder(
    db: Session,
    holder_type: str,
    holder_id: int,
    branch_id: int,
    *,
    for_update: bool = False,
) -> CreditAccount | None:
    q = db.query(CreditAccount).filter(CreditAccount.branch_id == branch_id)
    if holder_type == "customer":
        q = q.filter(CreditAccount.customer_id == holder_id)
    else:
        q = q.filter(CreditAccount.employee_id == holder_id)
    if for_update:
        q = q.with_for_update(nowait=True).execution_options(populate_existing=True)
    return q.first()


def get_account_for_customer(
    db: Session, customer_id: int, branch_id: int, *, for_update: bool = False,
) -> CreditAccount | None:
    return get_account_for_holder(
        db, "customer", customer_id, branch_id, for_update=for_update,
    )


def get_account_for_employee(
    db: Session, employee_id: int, branch_id: int, *, for_update: bool = False,
) -> CreditAccount | None:
    return get_account_for_holder(
        db, "employee", employee_id, branch_id, for_update=for_update,
    )


def list_accounts(
    db: Session,
    branch_id: int,
    status: str | None = None,
    holder_type: str | None = None,
    *,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[CreditAccount], int]:
    q = db.query(CreditAccount).filter(CreditAccount.branch_id == branch_id)
    if status:
        q = q.filter(CreditAccount.status == status)
    if holder_type:
        q = q.filter(CreditAccount.holder_type == holder_type)
    total = q.count()
    items = (
        q.order_by(CreditAccount.current_balance.desc(), CreditAccount.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return items, total


def create_account(db: Session, account: CreditAccount) -> CreditAccount:
    db.add(account)
    db.flush()
    return account


def create_transaction(db: Session, txn: CreditTransaction) -> CreditTransaction:
    db.add(txn)
    db.flush()
    return txn


def get_transaction(db: Session, txn_id: int) -> CreditTransaction | None:
    return db.query(CreditTransaction).filter(CreditTransaction.id == txn_id).first()


def lock_transaction(db: Session, txn_id: int, branch_id: int) -> CreditTransaction | None:
    return (
        db.query(CreditTransaction)
        .filter(CreditTransaction.id == txn_id, CreditTransaction.branch_id == branch_id)
        .with_for_update(nowait=True)
        .execution_options(populate_existing=True)
        .first()
    )


def get_transaction_by_idempotency(
    db: Session, branch_id: int, idempotency_key: str,
) -> CreditTransaction | None:
    return (
        db.query(CreditTransaction)
        .filter(
            CreditTransaction.branch_id == branch_id,
            CreditTransaction.idempotency_key == idempotency_key,
        )
        .first()
    )


def get_charge_for_source(
    db: Session,
    *,
    ref_order_id: int | None = None,
    ref_beach_tx_id: int | None = None,
) -> CreditTransaction | None:
    query = db.query(CreditTransaction).filter(CreditTransaction.txn_type == "charge")
    if ref_order_id is not None:
        query = query.filter(CreditTransaction.ref_order_id == ref_order_id)
    elif ref_beach_tx_id is not None:
        query = query.filter(CreditTransaction.ref_beach_tx_id == ref_beach_tx_id)
    else:
        return None
    return query.first()


def get_reversal_for_transaction(
    db: Session, original_txn_id: int,
) -> CreditTransaction | None:
    return (
        db.query(CreditTransaction)
        .filter(
            CreditTransaction.reversed_txn_id == original_txn_id,
            CreditTransaction.txn_type == "reversal",
        )
        .first()
    )


def list_adjustments_for_transaction(
    db: Session, original_txn_id: int,
) -> list[CreditTransaction]:
    return (
        db.query(CreditTransaction)
        .filter(CreditTransaction.reversed_txn_id == original_txn_id)
        .order_by(CreditTransaction.id.asc())
        .all()
    )


def list_transactions(
    db: Session,
    account_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[CreditTransaction]:
    q = db.query(CreditTransaction).filter(
        CreditTransaction.credit_account_id == account_id,
    )
    if date_from:
        q = q.filter(func.date(CreditTransaction.created_at) >= date_from)
    if date_to:
        q = q.filter(func.date(CreditTransaction.created_at) <= date_to)
    return q.order_by(CreditTransaction.created_at.asc(), CreditTransaction.id.asc()).all()


def compute_balance_from_transactions(db: Session, account_id: int) -> Decimal:
    value = (
        db.query(func.coalesce(func.sum(CreditTransaction.balance_delta), 0))
        .filter(CreditTransaction.credit_account_id == account_id)
        .scalar()
    )
    return Decimal(value or 0).quantize(Decimal("0.01"))


def get_accounts_with_balance(db: Session, branch_id: int) -> list[CreditAccount]:
    return (
        db.query(CreditAccount)
        .filter(CreditAccount.branch_id == branch_id, CreditAccount.current_balance > 0)
        .order_by(CreditAccount.current_balance.desc(), CreditAccount.id.asc())
        .all()
    )


def get_last_charge_times(db: Session, account_ids: list[int]) -> dict[int, object]:
    if not account_ids:
        return {}
    rows = (
        db.query(CreditTransaction.credit_account_id, func.max(CreditTransaction.created_at))
        .filter(
            CreditTransaction.credit_account_id.in_(account_ids),
            CreditTransaction.txn_type == "charge",
        )
        .group_by(CreditTransaction.credit_account_id)
        .all()
    )
    return {account_id: created_at for account_id, created_at in rows}
