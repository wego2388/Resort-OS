"""app/modules/crm/crud.py — CRUD خالص، لا business logic"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.resort_os.timezone_utils import local_today
from app.modules.crm.models import Activity, CallNote, Campaign, Customer, CustomerInteraction, Opportunity, Lead, LeadSource, GuestProfile
from app.modules.crm.schemas import (
    ActivityCreate, ActivityUpdate,
    CallNoteCreate,
    CampaignCreate, CampaignUpdate,
    CustomerCreate, CustomerUpdate,
    InteractionCreate,
    OpportunityCreate, OpportunityUpdate,
)


# ── Customer ──────────────────────────────────────────────────────────

def get_customer(db: Session, customer_id: int) -> Optional[Customer]:
    return db.query(Customer).filter(Customer.id == customer_id).first()


def get_customer_by_phone(db: Session, branch_id: int, phone: str) -> Optional[Customer]:
    return db.query(Customer).filter(
        Customer.branch_id == branch_id, Customer.phone == phone,
    ).first()


def get_customer_by_email(db: Session, branch_id: int, email: str) -> Optional[Customer]:
    return db.query(Customer).filter(
        Customer.branch_id == branch_id, Customer.email == email,
    ).first()


def list_customers(
    db: Session,
    branch_id: int,
    segment: Optional[str] = None,
    search: Optional[str] = None,
    blacklisted: Optional[bool] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Customer], int]:
    q = db.query(Customer).filter(Customer.branch_id == branch_id)
    if segment:
        q = q.filter(Customer.segment == segment)
    if search:
        like = f"%{search}%"
        q = q.filter(
            Customer.full_name.ilike(like) |
            Customer.phone.ilike(like) |
            Customer.email.ilike(like)
        )
    if blacklisted is not None:
        q = q.filter(Customer.blacklisted.is_(blacklisted))
    total = q.count()
    items = q.order_by(Customer.full_name).offset(skip).limit(limit).all()
    return items, total


def create_customer(db: Session, data: CustomerCreate) -> Customer:
    obj = Customer(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


def update_customer(db: Session, customer: Customer, data: CustomerUpdate) -> Customer:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    db.flush()
    return customer


def blacklist_customer(db: Session, customer: Customer, reason: str) -> Customer:
    customer.blacklisted = True
    customer.blacklist_reason = reason
    db.flush()
    return customer


def unblacklist_customer(db: Session, customer: Customer) -> Customer:
    customer.blacklisted = False
    customer.blacklist_reason = None
    db.flush()
    return customer


def update_customer_stats(
    db: Session,
    customer: Customer,
    amount: Decimal,
    visit_date: date,
) -> Customer:
    customer.total_spent += amount
    customer.visits_count += 1
    customer.last_visit = visit_date
    db.flush()
    return customer


# ── Interaction ───────────────────────────────────────────────────────

def list_interactions(
    db: Session,
    customer_id: int,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[CustomerInteraction], int]:
    q = db.query(CustomerInteraction).filter(CustomerInteraction.customer_id == customer_id)
    total = q.count()
    items = q.order_by(CustomerInteraction.occurred_at.desc()).offset(skip).limit(limit).all()
    return items, total


def create_interaction(
    db: Session,
    data: InteractionCreate,
    handled_by: int,
) -> CustomerInteraction:
    obj = CustomerInteraction(**data.model_dump(), handled_by=handled_by)
    db.add(obj)
    db.flush()
    return obj


# ── Opportunity ───────────────────────────────────────────────────────

def get_opportunity(db: Session, opp_id: int) -> Optional[Opportunity]:
    return db.query(Opportunity).filter(Opportunity.id == opp_id).first()


def list_opportunities(
    db: Session,
    branch_id: int,
    stage: Optional[str] = None,
    assigned_to: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Opportunity], int]:
    q = db.query(Opportunity).filter(Opportunity.branch_id == branch_id)
    if stage:
        q = q.filter(Opportunity.stage == stage)
    if assigned_to:
        q = q.filter(Opportunity.assigned_to == assigned_to)
    total = q.count()
    items = q.order_by(Opportunity.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def create_opportunity(db: Session, data: OpportunityCreate) -> Opportunity:
    obj = Opportunity(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


def update_opportunity(db: Session, opp: Opportunity, data: OpportunityUpdate) -> Opportunity:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(opp, field, value)
    if data.stage in ("won", "lost") and not opp.closed_at:
        opp.closed_at = datetime.utcnow()
    db.flush()
    return opp


# ── Activity ──────────────────────────────────────────────────────────

def get_activity(db: Session, activity_id: int) -> Optional[Activity]:
    return db.query(Activity).filter(Activity.id == activity_id).first()


def list_activities(
    db: Session,
    branch_id: int,
    customer_id: Optional[int] = None,
    assigned_to: Optional[int] = None,
    status: Optional[str] = None,
    due_before: Optional[date] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Activity], int]:
    q = db.query(Activity).filter(Activity.branch_id == branch_id)
    if customer_id:
        q = q.filter(Activity.customer_id == customer_id)
    if assigned_to:
        q = q.filter(Activity.assigned_to == assigned_to)
    if status:
        q = q.filter(Activity.status == status)
    if due_before:
        q = q.filter(Activity.due_date <= due_before)
    total = q.count()
    items = q.order_by(Activity.due_date).offset(skip).limit(limit).all()
    return items, total


def create_activity(db: Session, data: ActivityCreate) -> Activity:
    obj = Activity(**data.model_dump())
    db.add(obj)
    db.flush()
    return obj


def update_activity(db: Session, activity: Activity, data: ActivityUpdate) -> Activity:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(activity, field, value)
    if data.status == "done" and not activity.done_at:
        activity.done_at = datetime.utcnow()
    db.flush()
    return activity


# ── Campaign ──────────────────────────────────────────────────────────

def get_campaign(db: Session, campaign_id: int) -> Optional[Campaign]:
    return db.query(Campaign).filter(Campaign.id == campaign_id).first()


def list_campaigns(
    db: Session,
    branch_id: int,
    status: Optional[str] = None,
    campaign_type: Optional[str] = None,
    start_from: Optional[date] = None,
    start_to: Optional[date] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Campaign], int]:
    q = db.query(Campaign).filter(Campaign.branch_id == branch_id)
    if status:
        q = q.filter(Campaign.status == status)
    if campaign_type:
        q = q.filter(Campaign.campaign_type == campaign_type)
    if start_from:
        q = q.filter(Campaign.start_date >= start_from)
    if start_to:
        q = q.filter(Campaign.start_date <= start_to)
    total = q.count()
    items = q.order_by(Campaign.start_date.desc()).offset(skip).limit(limit).all()
    return items, total


def create_campaign(db: Session, data: CampaignCreate, created_by: int) -> Campaign:
    obj = Campaign(**data.model_dump(), created_by=created_by)
    db.add(obj)
    db.flush()
    return obj


def update_campaign(db: Session, campaign: Campaign, data: CampaignUpdate) -> Campaign:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(campaign, field, value)
    db.flush()
    return campaign


# ── LeadSource ──────────────────────────────────────────────────────────

def create_lead_source(db: Session, data: dict) -> LeadSource:
    obj = LeadSource(**data)
    db.add(obj); db.commit(); db.refresh(obj); return obj


def list_lead_sources(db: Session, branch_id: int, active_only: bool = True) -> list[LeadSource]:
    q = db.query(LeadSource).filter(LeadSource.branch_id == branch_id)
    if active_only:
        q = q.filter(LeadSource.is_active.is_(True))
    return q.order_by(LeadSource.name).all()


# ── Lead ──────────────────────────────────────────────────────────────

def create_lead(db: Session, data: dict) -> Lead:
    obj = Lead(**data)
    db.add(obj); db.commit(); db.refresh(obj); return obj

def list_leads(db: Session, branch_id: int, stage: str | None = None) -> list[Lead]:
    q = db.query(Lead).filter(Lead.branch_id == branch_id)
    if stage:
        q = q.filter(Lead.stage == stage)
    return q.order_by(Lead.created_at.desc()).all()

def get_lead(db: Session, lead_id: int) -> Lead | None:
    return db.query(Lead).filter(Lead.id == lead_id).first()

def update_lead(db: Session, lead: Lead, data: dict) -> Lead:
    for k, v in data.items():
        setattr(lead, k, v)
    db.commit(); db.refresh(lead); return lead


# ── Call Notes ──────────────────────────────────────────────────────────

def create_call_note(db: Session, data: CallNoteCreate, called_by: int) -> CallNote:
    obj = CallNote(
        branch_id=data.branch_id, lead_id=data.lead_id, direction=data.direction,
        duration_min=data.duration_min, summary=data.summary, outcome=data.outcome,
        callback_at=data.callback_at, called_by=called_by,
        called_at=data.called_at or datetime.utcnow(),
    )
    db.add(obj); db.commit(); db.refresh(obj); return obj


def list_call_notes_for_lead(db: Session, lead_id: int) -> list[CallNote]:
    return (
        db.query(CallNote)
        .filter(CallNote.lead_id == lead_id)
        .order_by(CallNote.called_at.desc())
        .all()
    )


# ── GuestProfile ──────────────────────────────────────────────────────

def get_or_create_guest_profile(db: Session, branch_id: int, phone: str, defaults: dict) -> GuestProfile:
    profile = db.query(GuestProfile).filter(
        GuestProfile.branch_id == branch_id,
        GuestProfile.phone == phone,
    ).first()
    if not profile:
        profile = GuestProfile(branch_id=branch_id, phone=phone, **defaults)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile

def update_guest_profile_on_checkout(db: Session, branch_id: int, phone: str, spend: Decimal) -> None:
    """يُحدَّث عند كل checkout."""
    profile = db.query(GuestProfile).filter(
        GuestProfile.branch_id == branch_id,
        GuestProfile.phone == phone,
    ).first()
    if not profile:
        return
    profile.total_visits += 1
    # #tz-fix: local_today بدل _date.today() — checkout بيحصل في نهار المنتجع
    # لكن الـ Celery/server ممكن يكون UTC، فاليوم المحلي مختلف في 3 ساعات
    profile.last_stay = local_today(settings.TIMEZONE)
    total = profile.avg_spend * (profile.total_visits - 1) + spend
    if profile.total_visits > 0:
        profile.avg_spend = (total / profile.total_visits).quantize(Decimal("0.01"))
    db.commit()


def get_guest_profile_by_phone(db: Session, branch_id: int, phone: str) -> Optional[GuestProfile]:
    return db.query(GuestProfile).filter(
        GuestProfile.branch_id == branch_id,
        GuestProfile.phone == phone,
    ).first()


def list_guest_profiles(
    db: Session, branch_id: int, vip_only: bool = False, limit: int = 100,
) -> list[GuestProfile]:
    q = db.query(GuestProfile).filter(GuestProfile.branch_id == branch_id)
    if vip_only:
        q = q.filter(GuestProfile.vip_flag.is_(True))
    return q.order_by(GuestProfile.last_stay.desc().nullslast()).limit(limit).all()
