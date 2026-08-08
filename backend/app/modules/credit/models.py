"""ORM models for personal customer/employee credit accounts (Decision 0005)."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.kernel.models.mixins import TimestampMixin


class CreditAccount(Base, TimestampMixin):
    """One branch-scoped account, owned by exactly one CRM customer or employee."""

    __tablename__ = "credit_accounts"
    __table_args__ = (
        CheckConstraint(
            "(customer_id IS NOT NULL AND employee_id IS NULL) OR "
            "(customer_id IS NULL AND employee_id IS NOT NULL)",
            name="ck_credit_account_holder_xor",
        ),
        CheckConstraint(
            "(holder_type = 'customer' AND customer_id IS NOT NULL) OR "
            "(holder_type = 'employee' AND employee_id IS NOT NULL)",
            name="ck_credit_account_holder_type_match",
        ),
        CheckConstraint("credit_limit >= 0", name="ck_credit_account_limit_nonnegative"),
        CheckConstraint("current_balance >= 0", name="ck_credit_account_balance_nonnegative"),
        CheckConstraint(
            "status IN ('active', 'suspended', 'closed')",
            name="ck_credit_account_status_valid",
        ),
        UniqueConstraint("branch_id", "customer_id", name="uq_credit_account_branch_customer"),
        UniqueConstraint("branch_id", "employee_id", name="uq_credit_account_branch_employee"),
        Index("ix_credit_accounts_branch_status", "branch_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="RESTRICT"), index=True,
    )
    holder_type: Mapped[str] = mapped_column(String(10))
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("crm_customers.id", ondelete="RESTRICT"), nullable=True, index=True,
    )
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT"), nullable=True, index=True,
    )
    # 0 means unlimited.  The value is always evaluated after discounts.
    credit_limit: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), server_default="0",
    )
    # Denormalized projection; CreditTransaction.balance_delta remains the ledger truth.
    current_balance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), server_default="0",
    )
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    opened_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    transactions: Mapped[list["CreditTransaction"]] = relationship(
        "CreditTransaction", back_populates="account", lazy="select",
    )


class CreditTransaction(Base, TimestampMixin):
    """Immutable account-ledger movement; corrections are appended, never edited."""

    __tablename__ = "credit_transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_credit_txn_amount_positive"),
        CheckConstraint("balance_delta <> 0", name="ck_credit_txn_delta_nonzero"),
        CheckConstraint(
            "txn_type IN ('charge', 'payment', 'refund', 'reversal')",
            name="ck_credit_txn_type_valid",
        ),
        CheckConstraint(
            "(txn_type = 'charge' AND balance_delta = amount) OR "
            "(txn_type = 'payment' AND balance_delta = -amount) OR "
            "(txn_type = 'refund' AND balance_delta = -amount) OR "
            "txn_type = 'reversal'",
            name="ck_credit_txn_delta_direction",
        ),
        CheckConstraint(
            "(txn_type = 'charge' AND "
            " ((ref_order_id IS NOT NULL AND ref_beach_tx_id IS NULL) OR "
            "  (ref_order_id IS NULL AND ref_beach_tx_id IS NOT NULL)) AND "
            " reversed_txn_id IS NULL AND payment_method IS NULL) OR "
            "(txn_type = 'payment' AND ref_order_id IS NULL AND ref_beach_tx_id IS NULL "
            " AND reversed_txn_id IS NULL AND payment_method IN ('cash', 'bank')) OR "
            "(txn_type = 'refund' AND ref_order_id IS NULL AND ref_beach_tx_id IS NULL "
            " AND reversed_txn_id IS NOT NULL AND payment_method IS NULL) OR "
            "(txn_type = 'reversal' AND ref_order_id IS NULL AND ref_beach_tx_id IS NULL "
            " AND reversed_txn_id IS NOT NULL AND payment_method IS NULL)",
            name="ck_credit_txn_shape",
        ),
        UniqueConstraint("ref_order_id", name="uq_credit_txn_order_charge"),
        UniqueConstraint("ref_beach_tx_id", name="uq_credit_txn_beach_charge"),
        UniqueConstraint("branch_id", "idempotency_key", name="uq_credit_txn_branch_idempotency"),
        Index(
            "uq_credit_txn_reversal_once",
            "reversed_txn_id",
            unique=True,
            postgresql_where=text("txn_type = 'reversal'"),
            sqlite_where=text("txn_type = 'reversal'"),
        ),
        Index("ix_credit_transactions_account_type", "credit_account_id", "txn_type"),
        Index("ix_credit_transactions_branch_created", "branch_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    credit_account_id: Mapped[int] = mapped_column(
        ForeignKey("credit_accounts.id", ondelete="RESTRICT"), index=True,
    )
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"))
    txn_type: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    balance_delta: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    payment_method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ref_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("dining_orders.id", ondelete="RESTRICT"), nullable=True,
    )
    ref_beach_tx_id: Mapped[int | None] = mapped_column(
        ForeignKey("beach_transactions.id", ondelete="RESTRICT"), nullable=True,
    )
    reversed_txn_id: Mapped[int | None] = mapped_column(
        # Parent movement for an exact reversal or a partial source refund.
        # Posted movements are immutable and cannot be deleted underneath it.
        ForeignKey("credit_transactions.id", ondelete="RESTRICT"), nullable=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    journal_entry_id: Mapped[int] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="RESTRICT"), nullable=False,
    )

    account: Mapped["CreditAccount"] = relationship("CreditAccount", back_populates="transactions")
