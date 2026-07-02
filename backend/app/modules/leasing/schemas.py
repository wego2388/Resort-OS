"""app/modules/leasing/schemas.py — Pydantic v2"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LeaseContractCreate(BaseModel):
    branch_id:          int
    tenant_name:        str = Field(..., max_length=200)
    tenant_phone:       Optional[str] = None
    tenant_national_id: Optional[str] = None
    unit_description:   str = Field(..., max_length=300)
    start_date:         date
    end_date:           date
    base_rent:          Decimal = Field(..., gt=0)
    increase_rate:      Decimal = Field(Decimal("0"), ge=0, le=100)
    billing_day:        int = Field(1, ge=1, le=28)
    grace_months:       int = Field(0, ge=0)
    payment_period:     str = Field("monthly", pattern=r"^(monthly|quarterly|biannual|annual)$")
    security_deposit:   Decimal = Field(Decimal("0"), ge=0)
    notes:              Optional[str] = None


class LeaseContractUpdate(BaseModel):
    tenant_phone:   Optional[str]  = None
    status:         Optional[str]  = Field(None, pattern=r"^(draft|active|expired|terminated)$")
    notes:          Optional[str]  = None


class LeasePaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; contract_id: int; due_date: date; amount: Decimal
    penalty: Decimal; paid_amount: Decimal; status: str
    paid_at: Optional[datetime]; payment_method: Optional[str]
    receipt_number: Optional[str]; year_n: int; notes: Optional[str]
    created_at: datetime


class LeaseContractRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; contract_number: str
    tenant_name: str; tenant_phone: Optional[str]; tenant_national_id: Optional[str]
    unit_description: str; start_date: date; end_date: date
    base_rent: Decimal; increase_rate: Decimal; billing_day: int
    grace_months: int; payment_period: str; security_deposit: Decimal
    status: str; notes: Optional[str]
    payments: list[LeasePaymentRead] = []
    created_at: datetime; updated_at: datetime


class PayLeaseRequest(BaseModel):
    paid_amount:    Decimal = Field(..., gt=0)
    payment_method: str = Field(..., pattern=r"^(cash|card|bank_transfer|other)$")
    receipt_number: Optional[str] = None
    notes:          Optional[str] = None


# ── TenantCashLog ─────────────────────────────────────────────────────
# resort-os-docs/06-MODULES.md § LEASING: "TenantCashLog: للمستأجرين الذين
# يسوّون كاش يومي مع المنتجع (مركز غوص/واتر سبورت)". الـ model كان موجود
# بالكامل في models.py من زمان بس من غير schemas/crud/services/router —
# نفس فئة الباج الموثّقة في CLAUDE.md § 11.6، اتصلحت في مراجعة Task B.

class TenantCashLogCreate(BaseModel):
    branch_id:      int
    contract_id:    int
    amount:         Decimal = Field(..., gt=0)
    activity_type:  str = Field("rent_payment", pattern=r"^(rent_payment|penalty|deposit|refund|maintenance|revenue_share|other)$")
    payment_method: Optional[str] = Field(None, max_length=30)
    reference:      Optional[str] = Field(None, max_length=50)
    notes:          Optional[str] = None


class TenantCashLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:             int
    branch_id:      int
    contract_id:    int
    amount:         Decimal
    activity_type:  str
    payment_method: Optional[str]
    reference:      Optional[str]
    notes:          Optional[str]
    recorded_by:    Optional[int]
    created_at:     datetime
