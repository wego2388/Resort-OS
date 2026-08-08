"""Pydantic contracts for personal credit accounts (Decision 0005)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class CreditAccountCreate(BaseModel):
    holder_type: str = Field(..., pattern=r"^(customer|employee)$")
    holder_id: int = Field(..., gt=0)
    credit_limit: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = Field(default=None, max_length=500)


class CreditAccountStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(active|suspended|closed)$")
    notes: str | None = Field(default=None, max_length=500)


class CreditAccountLimitUpdate(BaseModel):
    credit_limit: Decimal = Field(..., ge=0)
    notes: str | None = Field(default=None, max_length=500)


class CreditAccountRead(BaseModel):
    id: int
    branch_id: int
    holder_type: str
    customer_id: int | None
    employee_id: int | None
    holder_name: str
    credit_limit: Decimal
    current_balance: Decimal
    available_credit: Decimal | None
    status: str
    notes: str | None
    opened_by: int
    created_at: datetime
    updated_at: datetime
    computed_at: datetime

    model_config = {"from_attributes": True}


class CreditAccountPage(BaseModel):
    total: int
    page: int
    size: int
    items: list[CreditAccountRead]


class CreditChargeCreate(BaseModel):
    amount: Decimal = Field(..., gt=0)
    ref_order_id: int | None = Field(default=None, gt=0)
    ref_beach_tx_id: int | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=500)
    approver_user_id: int | None = Field(default=None, gt=0)
    approver_pin: str | None = Field(default=None, min_length=4, max_length=12)

    @model_validator(mode="after")
    def validate_source_and_approval(self) -> "CreditChargeCreate":
        if (self.ref_order_id is None) == (self.ref_beach_tx_id is None):
            raise ValueError("يجب تمرير مرجع طلب أو معاملة شاطئ واحد فقط")
        if (self.approver_user_id is None) != (self.approver_pin is None):
            raise ValueError("بيانات موافقة المدير يجب أن تُرسل كاملة")
        return self


class CreditPaymentCreate(BaseModel):
    amount: Decimal = Field(..., gt=0)
    payment_method: str = Field(default="cash", pattern=r"^(cash|bank)$")
    notes: str | None = Field(default=None, max_length=500)


class CreditReversalCreate(BaseModel):
    original_txn_id: int = Field(..., gt=0)
    notes: str = Field(..., min_length=5, max_length=500)


class CreditTransactionRead(BaseModel):
    id: int
    credit_account_id: int
    branch_id: int
    txn_type: str
    amount: Decimal
    balance_delta: Decimal
    payment_method: str | None
    ref_order_id: int | None
    ref_beach_tx_id: int | None
    reversed_txn_id: int | None
    notes: str | None
    recorded_by: int
    recorded_by_name: str
    journal_entry_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class CreditStatementResponse(BaseModel):
    account: CreditAccountRead
    transactions: list[CreditTransactionRead]
    period_from: str | None
    period_to: str | None
    total_charges: Decimal
    total_payments: Decimal
    total_refunds: Decimal
    net_movement: Decimal
    computed_at: datetime


class CreditReceivableItem(BaseModel):
    account_id: int
    holder_type: str
    holder_name: str
    current_balance: Decimal
    credit_limit: Decimal
    status: str
    last_charge_at: datetime | None
    days_since_last_charge: int | None
    is_overdue: bool


class CreditReceivablesResponse(BaseModel):
    branch_id: int
    accounts: list[CreditReceivableItem]
    total_outstanding: Decimal
    overdue_count: int
    computed_at: datetime
