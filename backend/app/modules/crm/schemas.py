"""app/modules/crm/schemas.py — Pydantic v2"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Customer ──────────────────────────────────────────────────────────

class CustomerCreate(BaseModel):
    branch_id:   int
    full_name:   str = Field(..., max_length=200)
    phone:       Optional[str] = Field(None, max_length=20)
    email:       Optional[str] = Field(None, max_length=150)
    national_id: Optional[str] = Field(None, max_length=20)
    nationality: Optional[str] = Field(None, max_length=50)
    segment:     str = Field("regular", pattern=r"^(regular|vip|corporate|travel_agent)$")
    source:      str = Field("walk_in", pattern=r"^(walk_in|online|referral|corporate|social_media)$")
    birthday:    Optional[date] = None
    notes:       Optional[str] = None


class CustomerUpdate(BaseModel):
    full_name:   Optional[str] = Field(None, max_length=200)
    phone:       Optional[str] = None
    email:       Optional[str] = None
    nationality: Optional[str] = None
    segment:     Optional[str] = Field(None, pattern=r"^(regular|vip|corporate|travel_agent)$")
    birthday:    Optional[date] = None
    notes:       Optional[str] = None
    is_active:   Optional[bool] = None


class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:              int
    branch_id:       int
    full_name:       str
    phone:           Optional[str]
    email:           Optional[str]
    national_id:     Optional[str]
    nationality:     Optional[str]
    segment:         str
    source:          str
    total_spent:     Decimal
    visits_count:    int
    last_visit:      Optional[date]
    birthday:        Optional[date]
    notes:           Optional[str]
    is_active:       bool
    blacklisted:     bool
    blacklist_reason: Optional[str]
    created_at:      datetime
    updated_at:      datetime


class BlacklistRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=300)


# ── Interaction ───────────────────────────────────────────────────────

class InteractionCreate(BaseModel):
    customer_id:      int
    branch_id:        int
    interaction_type: str = Field(..., pattern=r"^(call|whatsapp|email|visit|complaint|compliment|inquiry)$")
    direction:        str = Field("inbound", pattern=r"^(inbound|outbound)$")
    summary:          str = Field(..., max_length=500)
    outcome:          Optional[str] = Field(None, max_length=100)
    occurred_at:      datetime


class InteractionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:               int
    customer_id:      int
    branch_id:        int
    interaction_type: str
    direction:        str
    summary:          str
    outcome:          Optional[str]
    handled_by:       Optional[int]
    occurred_at:      datetime
    created_at:       datetime


# ── Opportunity ───────────────────────────────────────────────────────

class OpportunityCreate(BaseModel):
    branch_id:      int
    customer_id:    int
    title:          str = Field(..., max_length=300)
    product_type:   str = Field(..., pattern=r"^(timeshare|leasing|membership|group_booking|other)$")
    expected_value: Decimal = Field(Decimal("0"), ge=0)
    probability:    int = Field(20, ge=0, le=100)
    assigned_to:    Optional[int] = None
    expected_close: Optional[date] = None
    notes:          Optional[str] = None


class OpportunityUpdate(BaseModel):
    title:          Optional[str]     = None
    stage:          Optional[str]     = Field(None, pattern=r"^(lead|qualified|proposal|negotiation|won|lost)$")
    expected_value: Optional[Decimal] = None
    probability:    Optional[int]     = Field(None, ge=0, le=100)
    assigned_to:    Optional[int]     = None
    expected_close: Optional[date]    = None
    lost_reason:    Optional[str]     = None
    notes:          Optional[str]     = None


class OpportunityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:             int
    branch_id:      int
    customer_id:    int
    title:          str
    product_type:   str
    stage:          str
    expected_value: Decimal
    probability:    int
    assigned_to:    Optional[int]
    expected_close: Optional[date]
    closed_at:      Optional[datetime]
    lost_reason:    Optional[str]
    notes:          Optional[str]
    created_at:     datetime
    updated_at:     datetime


# ── Lead ──────────────────────────────────────────────────────────────
# frontend/apps/admin/src/views/CRMView.vue بينادي GET /crm/leads و
# PATCH /crm/leads/{id} — الـ model (Lead) والـ crud functions
# (create_lead/list_leads/get_lead/update_lead) كانوا موجودين بالكامل من
# زمان، بس مفيش schemas ولا router endpoint خالص — نفس باج
# GET /restaurant/menu/categories المذكور في CLAUDE.md § 11.6.

class LeadCreate(BaseModel):
    branch_id:      int
    full_name:      str = Field(..., max_length=200)
    phone:          Optional[str] = Field(None, max_length=20)
    email:          Optional[str] = Field(None, max_length=150)
    nationality:    Optional[str] = Field(None, max_length=50)
    source_id:      Optional[int] = None
    interest:       str = Field("other", pattern=r"^(timeshare|leasing|booking|membership|other)$")
    expected_value: Decimal = Field(Decimal("0"), ge=0)
    assigned_to:    Optional[int] = None
    notes:          Optional[str] = None


class LeadStageUpdate(BaseModel):
    stage: str = Field(..., pattern=r"^(new|contacted|qualified|proposal|won|lost)$")
    lost_reason: Optional[str] = Field(None, max_length=300)


class LeadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:             int
    branch_id:      int
    full_name:      str
    phone:          Optional[str]
    email:          Optional[str]
    nationality:    Optional[str]
    source_id:      Optional[int]
    interest:       str
    stage:          str
    assigned_to:    Optional[int]
    expected_value: Decimal
    won_at:         Optional[datetime]
    lost_at:        Optional[datetime]
    lost_reason:    Optional[str]
    booking_id:     Optional[int]
    notes:          Optional[str]
    created_at:     datetime
    updated_at:     datetime


# ── Activity ──────────────────────────────────────────────────────────

class ActivityCreate(BaseModel):
    branch_id:     int
    customer_id:   int
    activity_type: str = Field(..., pattern=r"^(follow_up|meeting|demo|proposal_send|contract_sign)$")
    title:         str = Field(..., max_length=300)
    due_date:      date
    due_time:      Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    assigned_to:   Optional[int] = None
    notes:         Optional[str] = None


class ActivityUpdate(BaseModel):
    title:       Optional[str]  = None
    due_date:    Optional[date] = None
    due_time:    Optional[str]  = None
    assigned_to: Optional[int]  = None
    status:      Optional[str]  = Field(None, pattern=r"^(pending|done|cancelled)$")
    notes:       Optional[str]  = None


class ActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:            int
    branch_id:     int
    customer_id:   int
    activity_type: str
    title:         str
    due_date:      date
    due_time:      Optional[str]
    assigned_to:   Optional[int]
    status:        str
    done_at:       Optional[datetime]
    notes:         Optional[str]
    created_at:    datetime
    updated_at:    datetime
