"""app/modules/crm/services.py — Business logic"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.modules.crm import crud
from app.modules.crm.models import Activity, Customer, CustomerInteraction, Lead, Opportunity
from app.modules.crm.schemas import (
    ActivityCreate, ActivityUpdate,
    BlacklistRequest,
    CustomerCreate, CustomerUpdate,
    InteractionCreate,
    LeadCreate, LeadStageUpdate,
    OpportunityCreate, OpportunityUpdate,
)


# ── Customer ──────────────────────────────────────────────────────────

def get_customer_or_404(db: Session, customer_id: int) -> Customer:
    c = crud.get_customer(db, customer_id)
    if not c:
        raise ValueError(f"العميل {customer_id} غير موجود")
    return c


def create_customer(db: Session, data: CustomerCreate) -> Customer:
    obj = crud.create_customer(db, data)
    db.commit()
    db.refresh(obj)
    return obj


def update_customer(db: Session, customer_id: int, data: CustomerUpdate) -> Customer:
    customer = get_customer_or_404(db, customer_id)
    obj = crud.update_customer(db, customer, data)
    db.commit()
    db.refresh(obj)
    return obj


def blacklist_customer(db: Session, customer_id: int, req: BlacklistRequest) -> Customer:
    customer = get_customer_or_404(db, customer_id)
    if customer.blacklisted:
        raise ValueError("العميل مُدرج في القائمة السوداء مسبقاً")
    obj = crud.blacklist_customer(db, customer, req.reason)
    db.commit()
    db.refresh(obj)
    return obj


def unblacklist_customer(db: Session, customer_id: int) -> Customer:
    customer = get_customer_or_404(db, customer_id)
    if not customer.blacklisted:
        raise ValueError("العميل ليس في القائمة السوداء")
    obj = crud.unblacklist_customer(db, customer)
    db.commit()
    db.refresh(obj)
    return obj


# ── Interaction ───────────────────────────────────────────────────────

def log_interaction(db: Session, data: InteractionCreate, handled_by: int) -> CustomerInteraction:
    get_customer_or_404(db, data.customer_id)
    obj = crud.create_interaction(db, data, handled_by)
    db.commit()
    db.refresh(obj)
    return obj


# ── Opportunity ───────────────────────────────────────────────────────

def get_opportunity_or_404(db: Session, opp_id: int) -> Opportunity:
    opp = crud.get_opportunity(db, opp_id)
    if not opp:
        raise ValueError(f"الفرصة {opp_id} غير موجودة")
    return opp


def create_opportunity(db: Session, data: OpportunityCreate) -> Opportunity:
    get_customer_or_404(db, data.customer_id)
    obj = crud.create_opportunity(db, data)
    db.commit()
    db.refresh(obj)
    return obj


def update_opportunity(db: Session, opp_id: int, data: OpportunityUpdate) -> Opportunity:
    opp = get_opportunity_or_404(db, opp_id)
    if opp.stage in ("won", "lost"):
        raise ValueError("لا يمكن تعديل فرصة مغلقة")
    if data.stage == "lost" and not data.lost_reason:
        raise ValueError("يجب تحديد سبب الخسارة")
    obj = crud.update_opportunity(db, opp, data)
    db.commit()
    db.refresh(obj)
    return obj


# ── Activity ──────────────────────────────────────────────────────────

def get_activity_or_404(db: Session, activity_id: int) -> Activity:
    a = crud.get_activity(db, activity_id)
    if not a:
        raise ValueError(f"النشاط {activity_id} غير موجود")
    return a


def create_activity(db: Session, data: ActivityCreate) -> Activity:
    get_customer_or_404(db, data.customer_id)
    obj = crud.create_activity(db, data)
    db.commit()
    db.refresh(obj)
    return obj


def update_activity(db: Session, activity_id: int, data: ActivityUpdate) -> Activity:
    activity = get_activity_or_404(db, activity_id)
    if activity.status in ("done", "cancelled"):
        raise ValueError("لا يمكن تعديل نشاط منتهٍ أو ملغى")
    obj = crud.update_activity(db, activity, data)
    db.commit()
    db.refresh(obj)
    return obj


# ── Lead ──────────────────────────────────────────────────────────────

def get_lead_or_404(db: Session, lead_id: int) -> Lead:
    lead = crud.get_lead(db, lead_id)
    if not lead:
        raise ValueError(f"العميل المحتمل {lead_id} غير موجود")
    return lead


def create_lead(db: Session, data: LeadCreate) -> Lead:
    return crud.create_lead(db, data.model_dump())


def update_lead_stage(db: Session, lead_id: int, data: LeadStageUpdate) -> Lead:
    """يتقدّم بالـ lead في الـ pipeline: new → contacted → qualified → proposal
    → won/lost. won/lost نهائيان (زي Opportunity.closed_at)."""
    from datetime import datetime as _dt  # noqa: PLC0415

    lead = get_lead_or_404(db, lead_id)
    if lead.stage in ("won", "lost"):
        raise ValueError(f"الـ lead في حالة نهائية '{lead.stage}' ولا يمكن تعديله")

    update_data: dict = {"stage": data.stage}
    if data.stage == "won":
        update_data["won_at"] = _dt.utcnow()
    elif data.stage == "lost":
        update_data["lost_at"] = _dt.utcnow()
        if data.lost_reason:
            update_data["lost_reason"] = data.lost_reason

    return crud.update_lead(db, lead, update_data)


def get_overdue_activities(db: Session, branch_id: int) -> list[Activity]:
    """يُستخدم من Celery لإرسال تذكيرات."""
    today = date.today()
    items, _ = crud.list_activities(
        db, branch_id,
        status="pending",
        due_before=today,
        limit=500,
    )
    return items
