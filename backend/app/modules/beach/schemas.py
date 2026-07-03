"""app/modules/beach/schemas.py — Pydantic v2"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class BeachInventoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:               int
    branch_id:        int
    inventory_date:   date
    capacity_max:     int
    capacity_used:    int
    towels_total:     int
    towels_available: int
    towels_used:      int
    surge_pct:        Decimal
    available_slots:  int = 0
    capacity_pct:     int = 0
    # الأسعار مش عمود في جدول beach_inventory — بتتحسب من settings الفرع
    # (نفس الدالة اللي البيع الفعلي بيستخدمها، app.modules.beach.services
    # .get_base_prices) ومُدمجة هنا وقت الـ router.get_inventory() عشان
    # شاشة الـ POS تقدر تعرض السعر قبل ما الكاشير يعمل البيع فعليًا.
    adult_price:      Decimal = Decimal("0")
    child_price:      Decimal = Decimal("0")
    resident_price:   Decimal = Decimal("0")
    towel_price:      Decimal = Decimal("0")
    surge_active:     bool = False
    # app.resort_os.beach_engine.calculate_tx_price يفسّر surge_pct=50.0 كـ
    # "+50%" (يعني الضرب في 1.5) — المضاعف ده نفسه، جاهز يتضرب في الأسعار
    # مباشرة في الفرونت إند بدل ما يعيد نفس الحسبة تاني.
    surge_multiplier: float = 1.0

    def model_post_init(self, __context: object) -> None:
        object.__setattr__(self, "available_slots",
                           max(0, self.capacity_max - self.capacity_used))
        cap_pct = (
            min(100, int(self.capacity_used / self.capacity_max * 100))
            if self.capacity_max > 0 else 100
        )
        object.__setattr__(self, "surge_multiplier", 1.0 + float(self.surge_pct) / 100.0)
        object.__setattr__(self, "capacity_pct", cap_pct)
        object.__setattr__(self, "surge_active", self.surge_pct > 0)


class BeachSellRequest(BaseModel):
    """طلب بيع تذكرة دخول أو فوطة."""
    tx_type:         str = Field(..., pattern=r"^(entry|entry_child|entry_resident|entry_towel|towel_rent|towel_return)$")
    quantity:        int = Field(1, ge=1)
    cashier_id:      Optional[int] = None
    folio_id:        Optional[int] = None
    room_id:         Optional[int] = None
    # لو موجود ومفيش folio_id مباشر: يدوّر على فوليو الضيف المقيم في الغرفة دي
    # (Charge to Room) — راجع pms.services.find_active_folio_for_room
    b2b_contract_id: Optional[int] = None
    customer_id:     Optional[int] = None
    notes:           Optional[str] = None


class BeachTransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:              int
    branch_id:       int
    tx_type:         str
    quantity:        int
    unit_price:      Decimal
    total_amount:    Decimal
    vat_amount:      Decimal
    surge_applied:   bool
    tx_date:         date
    cashier_id:      Optional[int]
    folio_id:        Optional[int]
    b2b_contract_id: Optional[int]
    customer_id:     Optional[int] = None
    notes:           Optional[str]
    voided_at:       Optional[datetime]
    voided_reason:   Optional[str] = None
    shift_id:        Optional[int] = None
    created_at:      datetime


class VoidTransactionRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=200)


class B2BContractCreate(BaseModel):
    branch_id:     int
    hotel_name:    str = Field(..., max_length=200)
    hotel_name_ar: Optional[str] = None
    contact_phone: Optional[str] = Field(None, max_length=20)
    daily_quota:   int = Field(50, ge=1)
    entry_price:   Decimal = Field(..., gt=0)
    towel_price:   Decimal = Field(Decimal("0"), ge=0)
    valid_from:    date
    valid_until:   date
    is_active:     bool = True
    notes:         Optional[str] = None


class B2BContractRead(B2BContractCreate):
    model_config = ConfigDict(from_attributes=True)
    id:         int
    created_at: datetime
    updated_at: datetime


class B2BCheckinRequest(BaseModel):
    contract_id:  int
    guests_count: int = Field(1, ge=1)
    with_towel:   bool = False
    cashier_id:   Optional[int] = None


class BeachReservationCreate(BaseModel):
    branch_id:        int
    guest_name:       str = Field(..., max_length=200)
    guest_phone:      Optional[str] = Field(None, max_length=20)
    reservation_date: date
    guests_count:     int = Field(1, ge=1)
    with_towel:       bool = False
    notes:            Optional[str] = None


class BeachReservationRead(BeachReservationCreate):
    model_config = ConfigDict(from_attributes=True)
    id:           int
    status:       str
    total_amount: Decimal
    tx_id:        Optional[int]
    created_at:   datetime


class BeachReservationPublic(BaseModel):
    """معلومات عامة عن الحجز — تُعرض في صفحة QR قبل تأكيد الدخول، بدون تسجيل دخول."""
    model_config = ConfigDict(from_attributes=True)
    id:               int
    guest_name:       str
    guests_count:     int
    with_towel:       bool
    reservation_date: date
    status:           str
    total_amount:     Decimal


class BeachSurgeSet(BaseModel):
    """طلب ضبط surge يدوياً من المدير."""
    surge_pct: Decimal = Field(..., ge=0, le=200)
    inv_date:  Optional[date] = None


class BeachDailySummary(BaseModel):
    """ملخص يومي للشاطئ."""
    date:             date
    total_entries:    int
    total_revenue:    Decimal
    b2b_entries:      int
    b2b_revenue:      Decimal
    capacity_pct:     int
    surge_active:     bool
    towels_rented:    int
