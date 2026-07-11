"""app/modules/timeshare/schemas.py — Pydantic v2"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TimeshareContractCreate(BaseModel):
    branch_id:              int
    customer_name:          str = Field(..., max_length=200)
    customer_phone:         Optional[str] = None
    customer_email:         Optional[str] = None
    customer_national_id:   Optional[str] = None
    room_type:              str = Field(..., pattern=r"^(2R|4R|6R)$")
    unit_id:                Optional[int] = None  # وحدة مخصَّصة دائمًا — None=عائم
    week_number:            Optional[int] = Field(None, ge=1, le=52)
    nights_per_year:        int = Field(7, ge=1)
    season:                 str = Field("high", pattern=r"^(high|low|both)$")
    total_value:            Decimal = Field(..., gt=0)
    down_payment:           Decimal = Field(..., ge=0)
    installments:           int = Field(12, ge=1)
    installment_period:     int = Field(1, pattern=None)
    first_installment_date: date
    partner_share_pct:      Decimal = Field(Decimal("0"), ge=0, le=100)
    partner_company:        Optional[str] = None
    start_date:             date
    end_date:               Optional[date] = None
    notes:                  Optional[str] = None
    # بيانات العميل الموسّعة
    nationality:            Optional[str] = None
    occupation:             Optional[str] = None
    passport_number:        Optional[str] = None
    address:                Optional[str] = None
    # بيانات العقد الموسّعة
    contract_date:          Optional[date] = None
    purchase_price:         Optional[Decimal] = None
    contract_deposit:       Optional[Decimal] = None
    maintenance_fee:        Decimal = Decimal("0")
    maintenance_increase:   Decimal = Decimal("10")
    batch_number:           Optional[int] = None
    form_number:            Optional[str] = None
    receipt_number:         Optional[str] = None
    rci_included:           bool = False
    contract_value:         Optional[Decimal] = None
    net_contract_value:     Optional[Decimal] = None
    over_under_price:       Decimal = Decimal("0")
    years_count:            int = 99
    payment_type:           str = Field("installment", pattern=r"^(installment|cash)$")


class TimeshareContractUpdate(BaseModel):
    customer_phone:    Optional[str]  = None
    customer_email:    Optional[str]  = None
    unit_id:           Optional[int]  = None
    week_number:       Optional[int]  = Field(None, ge=1, le=52)
    status:            Optional[str]  = Field(None, pattern=r"^(draft|active|suspended|cancelled|expired)$")
    booking_frozen:    Optional[bool] = None
    notes:             Optional[str]  = None
    nationality:       Optional[str]  = None
    address:           Optional[str]  = None


class InstallmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; contract_id: int; installment_no: int; due_date: date
    amount: Decimal; paid_amount: Decimal; status: str
    paid_at: Optional[datetime]; payment_method: Optional[str]
    receipt_number: Optional[str]; notes: Optional[str]
    created_at: datetime
    # بيانات العميل للعرض في جدول الأقساط (لوحة متابعة المتأخرات) — تُملأ فقط في
    # list_installments حيث الـ join على العقد متاح، وإلا None (مثلاً عند
    # pay_installment اللي بيرجّع القسط لوحده بدون العقد).
    customer_name:  Optional[str] = None
    customer_phone: Optional[str] = None
    room_type:      Optional[str] = None


class TimeshareContractRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; contract_number: str
    customer_name: str; customer_phone: Optional[str]; customer_email: Optional[str]
    customer_national_id: Optional[str]
    room_type: str; unit_id: Optional[int]; week_number: Optional[int]; nights_per_year: int; season: str
    total_value: Decimal; down_payment: Decimal; installments: int
    installment_period: int; first_installment_date: date
    partner_share_pct: Decimal; partner_company: Optional[str]
    status: str; booking_frozen: bool
    start_date: date; end_date: Optional[date]; notes: Optional[str]
    nationality: Optional[str]; occupation: Optional[str]
    passport_number: Optional[str]; address: Optional[str]
    contract_date: Optional[date]; purchase_price: Optional[Decimal]
    contract_deposit: Optional[Decimal]; maintenance_fee: Decimal
    maintenance_increase: Decimal; batch_number: Optional[int]
    form_number: Optional[str]; receipt_number: Optional[str]
    rci_included: bool; contract_value: Optional[Decimal]
    net_contract_value: Optional[Decimal]; over_under_price: Decimal
    years_count: int; payment_type: str
    cancelled_at: Optional[date]; cancel_amount: Decimal
    installments_list: list[InstallmentRead] = []
    created_at: datetime; updated_at: datetime


class TimeshareCancelRequest(BaseModel):
    cancel_amount: Decimal = Field(Decimal("0"), ge=0)


class TimeshareUnitTransferRequest(BaseModel):
    """wagdy.md #10: نقل عقد من وحدة ثابتة لوحدة تانية (نفس room_type —
    تغيير نوع الوحدة/"ترقية" بقيمة مختلفة قرار تسعير منفصل، مش في نطاق
    العملية دي، راجع services.transfer_unit). التعديل المباشر عبر
    TimeshareContractUpdate.unit_id كان موجود من غير أي تحقق خالص — مش مجرد
    UI ناقص، عملية غير آمنة فعليًا لو استُخدمت مباشرة."""
    new_unit_id: int
    reason: str = Field(..., min_length=3, max_length=300)


class PayInstallmentRequest(BaseModel):
    paid_amount:    Decimal = Field(..., gt=0)
    payment_method: str = Field(..., pattern=r"^(cash|card|bank_transfer|other)$")
    receipt_number: Optional[str] = None
    notes:          Optional[str] = None


class WaitlistCreate(BaseModel):
    branch_id:       int
    contract_id:     int
    requested_start: date
    requested_end:   date


class WaitlistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; contract_id: int
    requested_start: date; requested_end: date; position: int
    status: str; notified_at: Optional[datetime]; expires_at: Optional[datetime]
    created_at: datetime


class TimeshareVisitCreate(BaseModel):
    branch_id:   int
    contract_id: int
    check_in:    date
    check_out:   date
    booking_id:  Optional[int] = None
    notes:       Optional[str] = None


class TimeshareVisitUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern=r"^(scheduled|active|completed|cancelled)$")
    notes:  Optional[str] = None


class TimeshareVisitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; contract_id: int; booking_id: Optional[int]
    unit_id: Optional[int]
    check_in: date; check_out: date; nights: int; status: str
    notes: Optional[str]
    created_at: datetime


class TimeshareUnitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; unit_number: str; unit_type: str
    status: str; notes: Optional[str]
    created_at: datetime
