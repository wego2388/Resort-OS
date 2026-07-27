"""app/modules/hub/api/router.py"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import (
    APIRouter, Depends, Header, HTTPException, Query, Request, Response, status,
)

from app.core.deps import (
    DbDep, get_admin_user, get_current_active_user,
    get_manager_user,
)
from app.modules.hub import crud, services
from app.modules.hub.schemas import (
    HubOfferCreate, HubOfferRead, HubOfferUpdate,
    HubPageCreate, HubPageRead, HubPageUpdate,
    OnlineBookingCreate, OnlineBookingRead,
    ContactFormCreate, ContactFormResponse, ContactFormListItem, BlogPostsResponse,
)
from app.modules.core.schemas import PaginatedResponse

router = APIRouter(tags=["hub"])


# ── Pages ─────────────────────────────────────────────────────────────

@router.get("/hub/pages", response_model=PaginatedResponse)
def list_pages(
    db: DbDep,
    _=Depends(get_current_active_user),
    branch_id: int = Query(...),
    published_only: bool = Query(False),
    page_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    items, total = crud.list_pages(db, branch_id, published_only, page_type,
                                   skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[HubPageRead.model_validate(p) for p in items])


@router.post("/hub/pages", response_model=HubPageRead,
             status_code=status.HTTP_201_CREATED)
def create_page(data: HubPageCreate, db: DbDep, _=Depends(get_manager_user)):
    try:
        return services.create_page(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/hub/pages/{page_id}", response_model=HubPageRead)
def get_page(page_id: int, db: DbDep, _=Depends(get_current_active_user)):
    p = crud.get_page(db, page_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الصفحة غير موجودة")
    return HubPageRead.model_validate(p)


@router.get("/hub/pages/slug/{slug}", response_model=HubPageRead)
def get_page_by_slug(slug: str, db: DbDep, _=Depends(get_current_active_user)):
    p = crud.get_page_by_slug(db, slug)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الصفحة غير موجودة")
    return HubPageRead.model_validate(p)


@router.patch("/hub/pages/{page_id}", response_model=HubPageRead)
def update_page(page_id: int, data: HubPageUpdate, db: DbDep, _=Depends(get_manager_user)):
    try:
        return services.update_page(db, page_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.delete("/hub/pages/{page_id}",
               response_model=None, status_code=status.HTTP_204_NO_CONTENT)
def delete_page(page_id: int, db: DbDep, _=Depends(get_admin_user)):
    try:
        services.delete_page(db, page_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ── Offers ────────────────────────────────────────────────────────────

@router.get("/hub/offers", response_model=PaginatedResponse)
def list_offers(
    db: DbDep,
    _=Depends(get_current_active_user),
    branch_id: int = Query(...),
    active_only: bool = Query(True),
    offer_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    items, total = crud.list_offers(db, branch_id, active_only, offer_type,
                                    skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[HubOfferRead.model_validate(o) for o in items])


@router.post("/hub/offers", response_model=HubOfferRead,
             status_code=status.HTTP_201_CREATED)
def create_offer(data: HubOfferCreate, db: DbDep, _=Depends(get_manager_user)):
    try:
        return services.create_offer(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/hub/offers/{offer_id}", response_model=HubOfferRead)
def get_offer(offer_id: int, db: DbDep, _=Depends(get_current_active_user)):
    o = crud.get_offer(db, offer_id)
    if not o:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "العرض غير موجود")
    return HubOfferRead.model_validate(o)


@router.patch("/hub/offers/{offer_id}", response_model=HubOfferRead)
def update_offer(offer_id: int, data: HubOfferUpdate, db: DbDep, _=Depends(get_manager_user)):
    try:
        return services.update_offer(db, offer_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ── Online Bookings ───────────────────────────────────────────────────

@router.get("/hub/online-bookings", response_model=PaginatedResponse)
def list_online_bookings(
    db: DbDep,
    _=Depends(get_current_active_user),
    branch_id: int = Query(...),
    status: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    items, total = crud.list_online_bookings(db, branch_id, status, date_from, date_to,
                                             skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[OnlineBookingRead.model_validate(b) for b in items])


@router.post("/hub/online-bookings", response_model=OnlineBookingRead,
             status_code=status.HTTP_201_CREATED)
def create_online_booking(data: OnlineBookingCreate, db: DbDep,
                          _=Depends(get_current_active_user)):
    try:
        return services.create_online_booking(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/hub/online-bookings/{booking_id}", response_model=OnlineBookingRead)
def get_online_booking(booking_id: int, db: DbDep, _=Depends(get_current_active_user)):
    b = crud.get_online_booking(db, booking_id)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الحجز غير موجود")
    return OnlineBookingRead.model_validate(b)


@router.post("/hub/online-bookings/{booking_id}/confirm",
             response_model=OnlineBookingRead)
def confirm_booking(booking_id: int, db: DbDep, user=Depends(get_manager_user)):
    try:
        return services.confirm_booking(db, booking_id, confirmed_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/hub/online-bookings/{booking_id}/cancel",
             response_model=OnlineBookingRead)
def cancel_booking(booking_id: int, db: DbDep, _=Depends(get_manager_user)):
    try:
        return services.cancel_booking(db, booking_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Contact Form → CRM Lead ───────────────────────────────────────────

@router.post(
    "/hub/contact",
    response_model=ContactFormResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_contact_form(
    db: DbDep,
    data: ContactFormCreate,
    request: Request,
    response: Response,
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
):
    """Public service contact; CRM conversion requires separate marketing opt-in."""
    from app.core.rate_limit import _client_ip  # noqa: PLC0415
    from app.modules.hub.public_contact import (  # noqa: PLC0415
        ContactSubmissionFailure,
        resolve_public_site_branch,
        submit_public_contact,
    )

    branch = resolve_public_site_branch(db, request.url.hostname)
    if branch is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            {
                "code": "public_site_not_configured",
                "message": "Public contact site is not configured.",
            },
        )

    try:
        result = submit_public_contact(
            db,
            branch=branch,
            data=data,
            idempotency_key=idempotency_key,
            client_ip=_client_ip(request),
        )
    except ContactSubmissionFailure as exc:
        raise HTTPException(
            exc.status_code,
            {"code": exc.code, "message": exc.message},
        ) from exc

    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/hub/contact-forms", response_model=PaginatedResponse)
def list_contact_forms(
    db: DbDep,
    _=Depends(get_manager_user),
    branch_id: int = Query(...),
    crm_sync_status: Optional[str] = Query(
        None, description="not_requested|created|failed",
    ),
    status_filter: Optional[str] = Query(
        None, alias="status", description="accepted|purged|spam",
    ),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """Every public contact submission, consenting or not — see ContactFormListItem."""
    items, total = crud.list_contact_forms(
        db, branch_id, crm_sync_status, status_filter,
        skip=(page - 1) * size, limit=size,
    )
    return PaginatedResponse(
        total=total, page=page, size=size,
        items=[ContactFormListItem.model_validate(f) for f in items],
    )


# ── Blog Posts ────────────────────────────────────────────────────────

@router.get("/hub/blog/posts", response_model=BlogPostsResponse)
async def list_blog_posts(
    db: DbDep,
    branch_id: int = Query(...),
):
    """قائمة المقالات المنشورة للعرض العام."""
    from app.modules.hub.models import BlogPost  # noqa: PLC0415
    posts = db.query(BlogPost).filter(
        BlogPost.branch_id == branch_id,
        BlogPost.status == "published",
    ).order_by(BlogPost.published_at.desc()).all()
    return {"posts": [
        {"id": p.id, "title": p.title, "slug": p.slug,
         "excerpt": p.excerpt, "published_at": str(p.published_at),
         "views_count": p.views_count}
        for p in posts
    ]}
