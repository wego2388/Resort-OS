"""app/modules/crm/api/router.py"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import (
    DbDep, get_admin_user, get_current_active_user,
    get_manager_user, require_module,
)
from app.modules.crm import crud, services
from app.modules.crm.schemas import (
    ActivityCreate, ActivityRead, ActivityUpdate,
    BlacklistRequest,
    CustomerCreate, CustomerRead, CustomerUpdate,
    InteractionCreate, InteractionRead,
    LeadCreate, LeadRead, LeadStageUpdate,
    OpportunityCreate, OpportunityRead, OpportunityUpdate,
)
from app.modules.core.schemas import PaginatedResponse

router = APIRouter(tags=["crm"])
_guard = Depends(require_module("crm"))


# ── Customers ─────────────────────────────────────────────────────────

@router.get("/crm/customers", response_model=PaginatedResponse, dependencies=[_guard])
def list_customers(
    db: DbDep,
    _=Depends(get_current_active_user),
    branch_id: int = Query(...),
    segment: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    blacklisted: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    items, total = crud.list_customers(db, branch_id, segment, search, blacklisted,
                                       skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[CustomerRead.model_validate(c) for c in items])


@router.post("/crm/customers", response_model=CustomerRead,
             status_code=status.HTTP_201_CREATED, dependencies=[_guard])
def create_customer(data: CustomerCreate, db: DbDep, _=Depends(get_current_active_user)):
    return services.create_customer(db, data)


@router.get("/crm/customers/{customer_id}", response_model=CustomerRead, dependencies=[_guard])
def get_customer(customer_id: int, db: DbDep, _=Depends(get_current_active_user)):
    c = crud.get_customer(db, customer_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "العميل غير موجود")
    return CustomerRead.model_validate(c)


@router.patch("/crm/customers/{customer_id}", response_model=CustomerRead, dependencies=[_guard])
def update_customer(customer_id: int, data: CustomerUpdate, db: DbDep,
                    _=Depends(get_current_active_user)):
    try:
        return services.update_customer(db, customer_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.post("/crm/customers/{customer_id}/blacklist",
             response_model=CustomerRead, dependencies=[_guard])
def blacklist_customer(customer_id: int, req: BlacklistRequest, db: DbDep,
                       _=Depends(get_manager_user)):
    try:
        return services.blacklist_customer(db, customer_id, req)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.delete("/crm/customers/{customer_id}/blacklist",
               response_model=CustomerRead, dependencies=[_guard])
def unblacklist_customer(customer_id: int, db: DbDep, _=Depends(get_manager_user)):
    try:
        return services.unblacklist_customer(db, customer_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Leads ─────────────────────────────────────────────────────────────
# frontend/apps/admin/src/views/CRMView.vue بينادي GET /crm/leads و
# PATCH /crm/leads/{id} — الـ model (Lead) وكل crud functions بتاعته كانوا
# موجودين بالكامل من زمان، بس مفيش router endpoint خالص، فكان 404 حقيقي
# في الإنتاج. نفس فئة الباج الموثّقة في CLAUDE.md § 11.6.

@router.get("/crm/leads", response_model=list[LeadRead], dependencies=[_guard])
def list_leads(
    db: DbDep, _=Depends(get_current_active_user),
    branch_id: int = Query(...),
    stage: Optional[str] = Query(None),
):
    return [LeadRead.model_validate(l) for l in crud.list_leads(db, branch_id, stage)]


@router.post("/crm/leads", response_model=LeadRead,
             status_code=status.HTTP_201_CREATED, dependencies=[_guard])
def create_lead(data: LeadCreate, db: DbDep, _=Depends(get_current_active_user)):
    return LeadRead.model_validate(services.create_lead(db, data))


@router.get("/crm/leads/{lead_id}", response_model=LeadRead, dependencies=[_guard])
def get_lead(lead_id: int, db: DbDep, _=Depends(get_current_active_user)):
    lead = crud.get_lead(db, lead_id)
    if not lead:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"العميل المحتمل {lead_id} غير موجود")
    return LeadRead.model_validate(lead)


@router.patch("/crm/leads/{lead_id}", response_model=LeadRead, dependencies=[_guard])
def update_lead_stage(lead_id: int, data: LeadStageUpdate, db: DbDep,
                      _=Depends(get_current_active_user)):
    try:
        return LeadRead.model_validate(services.update_lead_stage(db, lead_id, data))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Interactions ──────────────────────────────────────────────────────

@router.get("/crm/customers/{customer_id}/interactions",
            response_model=PaginatedResponse, dependencies=[_guard])
def list_interactions(
    customer_id: int, db: DbDep,
    _=Depends(get_current_active_user),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    items, total = crud.list_interactions(db, customer_id,
                                          skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[InteractionRead.model_validate(i) for i in items])


@router.post("/crm/interactions", response_model=InteractionRead,
             status_code=status.HTTP_201_CREATED, dependencies=[_guard])
def log_interaction(data: InteractionCreate, db: DbDep, user=Depends(get_current_active_user)):
    try:
        return services.log_interaction(db, data, handled_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Opportunities ─────────────────────────────────────────────────────

@router.get("/crm/opportunities", response_model=PaginatedResponse, dependencies=[_guard])
def list_opportunities(
    db: DbDep,
    _=Depends(get_current_active_user),
    branch_id: int = Query(...),
    stage: Optional[str] = Query(None),
    assigned_to: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    items, total = crud.list_opportunities(db, branch_id, stage, assigned_to,
                                           skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[OpportunityRead.model_validate(o) for o in items])


@router.post("/crm/opportunities", response_model=OpportunityRead,
             status_code=status.HTTP_201_CREATED, dependencies=[_guard])
def create_opportunity(data: OpportunityCreate, db: DbDep, _=Depends(get_current_active_user)):
    try:
        return services.create_opportunity(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.patch("/crm/opportunities/{opp_id}", response_model=OpportunityRead, dependencies=[_guard])
def update_opportunity(opp_id: int, data: OpportunityUpdate, db: DbDep,
                       _=Depends(get_current_active_user)):
    try:
        return services.update_opportunity(db, opp_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Activities ────────────────────────────────────────────────────────

@router.get("/crm/activities", response_model=PaginatedResponse, dependencies=[_guard])
def list_activities(
    db: DbDep,
    _=Depends(get_current_active_user),
    branch_id: int = Query(...),
    customer_id: Optional[int] = Query(None),
    assigned_to: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    due_before: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    items, total = crud.list_activities(
        db, branch_id, customer_id, assigned_to, status, due_before,
        skip=(page - 1) * size, limit=size,
    )
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[ActivityRead.model_validate(a) for a in items])


@router.post("/crm/activities", response_model=ActivityRead,
             status_code=status.HTTP_201_CREATED, dependencies=[_guard])
def create_activity(data: ActivityCreate, db: DbDep, _=Depends(get_current_active_user)):
    try:
        return services.create_activity(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.patch("/crm/activities/{activity_id}", response_model=ActivityRead, dependencies=[_guard])
def update_activity(activity_id: int, data: ActivityUpdate, db: DbDep,
                    _=Depends(get_current_active_user)):
    try:
        return services.update_activity(db, activity_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
