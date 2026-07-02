"""
app/modules/analytics/schemas.py — Pydantic v2

⚠️ First schemas.py this module has ever had. Every other endpoint in
api/router.py returns ad-hoc dicts (no response_model) — an intentional style
for a read-only aggregation module. These 2 schemas exist only because
UtilityReading is a genuine write path (Task B audit finding: the model +
migration existed, but there was no way anywhere in the system to ever create
a reading) and FastAPI request-body validation needs a real Pydantic model.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class UtilityReadingCreate(BaseModel):
    branch_id:     int
    reading_date:  date
    utility_type:  str = Field(..., pattern=r"^(electricity|water|gas|diesel)$")
    reading_value: Decimal = Field(..., gt=0)
    unit:          str = Field("kWh", max_length=10)
    unit_cost:     Decimal = Field(Decimal("0"), ge=0)
    notes:         Optional[str] = Field(None, max_length=300)


class UtilityReadingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:            int
    branch_id:     int
    reading_date:  date
    utility_type:  str
    reading_value: Decimal
    unit:          str
    unit_cost:     Decimal
    total_cost:    Decimal
    notes:         Optional[str]
    recorded_by:   Optional[int]
    created_at:    datetime
