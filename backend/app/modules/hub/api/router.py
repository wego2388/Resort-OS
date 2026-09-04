"""app/modules/hub/api/router.py"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import (
    APIRouter, Depends, Header, HTTPException, Query, Request, Response, status,
)

from app.core.deps import (
    DbDep, get_admin_user, get_employee_user,
    get_manager_user,
)
from app.modules.hub import crud, services
from app.modules.hub.schemas import (
    HubOfferCreate, HubOfferRead, HubOfferUpdate,
    HubPageCreate, HubPageRead, HubPageUpdate,
    OnlineBookingCreate, OnlineBookingRead,
    ContactFormCreate, ContactFormResponse, ContactFormListItem,
    BlogPostsResponse, BlogPostItem, BlogPostDetail,
    RoomCatalogEntryRead, PublicRoomBookingRequest, PublicRoomBookingResponse,
)
from app.modules.core import services as core_services
from app.modules.core.schemas import PaginatedResponse

router = APIRouter(tags=["hub"])


def _assert_hub_branch(db, user, branch_id: int, action_desc: str) -> None:
    """Gate 4B-style branch isolation — كانت غايبة من endpoints الإدارة في
    hub (pages/offers/online-bookings — اتكشف 2026-07-28، نفس فئة الباج في
    CRM/timeshare/leasing/beach). لا علاقة لها بالـendpoints العامة الحقيقية
    (hub/contact، hub/blog/posts) اللي مفيهاش auth أصلاً بتصميم مقصود."""
    try:
        core_services.assert_branch_access(db, user, branch_id, action_desc)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))


# ── Pages ─────────────────────────────────────────────────────────────

@router.get("/hub/pages", response_model=PaginatedResponse)
def list_pages(
    db: DbDep,
    user=Depends(get_employee_user),
    branch_id: int = Query(...),
    published_only: bool = Query(False),
    page_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    _assert_hub_branch(db, user, branch_id, "عرض صفحات الموقع")
    items, total = crud.list_pages(db, branch_id, published_only, page_type,
                                   skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[HubPageRead.model_validate(p) for p in items])


@router.post("/hub/pages", response_model=HubPageRead,
             status_code=status.HTTP_201_CREATED)
def create_page(data: HubPageCreate, db: DbDep, user=Depends(get_manager_user)):
    _assert_hub_branch(db, user, data.branch_id, "إنشاء صفحة موقع")
    try:
        return services.create_page(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


def _get_page_or_404(db, page_id: int):
    p = crud.get_page(db, page_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الصفحة غير موجودة")
    return p


@router.get("/hub/pages/{page_id}", response_model=HubPageRead)
def get_page(page_id: int, db: DbDep, user=Depends(get_employee_user)):
    p = _get_page_or_404(db, page_id)
    _assert_hub_branch(db, user, p.branch_id, "عرض صفحة موقع")
    return HubPageRead.model_validate(p)


@router.get("/hub/pages/slug/{slug}", response_model=HubPageRead)
def get_page_by_slug(slug: str, db: DbDep, user=Depends(get_employee_user)):
    p = crud.get_page_by_slug(db, slug)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الصفحة غير موجودة")
    _assert_hub_branch(db, user, p.branch_id, "عرض صفحة موقع")
    return HubPageRead.model_validate(p)


@router.patch("/hub/pages/{page_id}", response_model=HubPageRead)
def update_page(page_id: int, data: HubPageUpdate, db: DbDep, user=Depends(get_manager_user)):
    p = _get_page_or_404(db, page_id)
    _assert_hub_branch(db, user, p.branch_id, "تعديل صفحة موقع")
    try:
        return services.update_page(db, page_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.delete("/hub/pages/{page_id}",
               response_model=None, status_code=status.HTTP_204_NO_CONTENT)
def delete_page(page_id: int, db: DbDep, user=Depends(get_admin_user)):
    p = _get_page_or_404(db, page_id)
    _assert_hub_branch(db, user, p.branch_id, "حذف صفحة موقع")
    try:
        services.delete_page(db, page_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ── Offers ────────────────────────────────────────────────────────────

@router.get("/hub/offers", response_model=PaginatedResponse)
def list_offers(
    db: DbDep,
    user=Depends(get_employee_user),
    branch_id: int = Query(...),
    active_only: bool = Query(True),
    offer_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    _assert_hub_branch(db, user, branch_id, "عرض العروض")
    items, total = crud.list_offers(db, branch_id, active_only, offer_type,
                                    skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[HubOfferRead.model_validate(o) for o in items])


@router.post("/hub/offers", response_model=HubOfferRead,
             status_code=status.HTTP_201_CREATED)
def create_offer(data: HubOfferCreate, db: DbDep, user=Depends(get_manager_user)):
    _assert_hub_branch(db, user, data.branch_id, "إنشاء عرض")
    try:
        return services.create_offer(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


def _get_offer_or_404(db, offer_id: int):
    o = crud.get_offer(db, offer_id)
    if not o:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "العرض غير موجود")
    return o


@router.get("/hub/offers/{offer_id}", response_model=HubOfferRead)
def get_offer(offer_id: int, db: DbDep, user=Depends(get_employee_user)):
    o = _get_offer_or_404(db, offer_id)
    _assert_hub_branch(db, user, o.branch_id, "عرض تفاصيل عرض")
    return HubOfferRead.model_validate(o)


@router.patch("/hub/offers/{offer_id}", response_model=HubOfferRead)
def update_offer(offer_id: int, data: HubOfferUpdate, db: DbDep, user=Depends(get_manager_user)):
    o = _get_offer_or_404(db, offer_id)
    _assert_hub_branch(db, user, o.branch_id, "تعديل عرض")
    try:
        return services.update_offer(db, offer_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ── Online Bookings ───────────────────────────────────────────────────

@router.get("/hub/online-bookings", response_model=PaginatedResponse)
def list_online_bookings(
    db: DbDep,
    user=Depends(get_employee_user),
    branch_id: int = Query(...),
    status: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    _assert_hub_branch(db, user, branch_id, "عرض الحجوزات الإلكترونية")
    items, total = crud.list_online_bookings(db, branch_id, status, date_from, date_to,
                                             skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[OnlineBookingRead.model_validate(b) for b in items])


@router.post("/hub/online-bookings", response_model=OnlineBookingRead,
             status_code=status.HTTP_201_CREATED)
def create_online_booking(data: OnlineBookingCreate, db: DbDep,
                          user=Depends(get_employee_user)):
    _assert_hub_branch(db, user, data.branch_id, "إنشاء حجز إلكتروني")
    try:
        return services.create_online_booking(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


def _get_online_booking_or_404(db, booking_id: int):
    b = crud.get_online_booking(db, booking_id)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الحجز غير موجود")
    return b


@router.get("/hub/online-bookings/{booking_id}", response_model=OnlineBookingRead)
def get_online_booking(booking_id: int, db: DbDep, user=Depends(get_employee_user)):
    b = _get_online_booking_or_404(db, booking_id)
    _assert_hub_branch(db, user, b.branch_id, "عرض حجز إلكتروني")
    return OnlineBookingRead.model_validate(b)


@router.post("/hub/online-bookings/{booking_id}/confirm",
             response_model=OnlineBookingRead)
def confirm_booking(booking_id: int, db: DbDep, user=Depends(get_manager_user)):
    from app.modules.pms.services import BookingConflictError  # noqa: PLC0415
    from app.modules.hub.services import HubConfirmationConcurrencyError  # noqa: PLC0415

    b = _get_online_booking_or_404(db, booking_id)
    _assert_hub_branch(db, user, b.branch_id, "تأكيد حجز إلكتروني")
    try:
        return services.confirm_booking(db, booking_id, confirmed_by=user.id)
    except HubConfirmationConcurrencyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except BookingConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/hub/online-bookings/{booking_id}/cancel",
             response_model=OnlineBookingRead)
def cancel_booking(booking_id: int, db: DbDep, user=Depends(get_manager_user)):
    b = _get_online_booking_or_404(db, booking_id)
    _assert_hub_branch(db, user, b.branch_id, "إلغاء حجز إلكتروني")
    try:
        return services.cancel_booking(db, booking_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Public room catalog + online booking request ──────────────────────
# OPS-DATA-02 §7.2/§7.3 — نفس نمط أمان /hub/contact بالظبط: الفرع مححدد
# من Host (لا يوجد branch_id من العميل)، rate limited، idempotent.

@router.get(
    "/hub/public/room-catalog",
    response_model=list[RoomCatalogEntryRead],
)
def get_public_room_catalog(db: DbDep, request: Request):
    from app.modules.hub.public_catalog import get_public_catalog  # noqa: PLC0415
    from app.modules.hub.public_contact import resolve_public_site_branch  # noqa: PLC0415

    branch = resolve_public_site_branch(db, request.url.hostname)
    if branch is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            {"code": "public_site_not_configured", "message": "Public site is not configured."},
        )
    entries = get_public_catalog(db, branch.id)
    return [RoomCatalogEntryRead(**vars(e)) for e in entries]


@router.post(
    "/hub/public/room-bookings",
    response_model=PublicRoomBookingResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_public_room_booking(
    db: DbDep,
    data: PublicRoomBookingRequest,
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
    """طلب حجز غرفة/باقة عام — بديل توجيه حجز الغرف لـ /hub/contact
    (راجع OPS-DATA-02 §7.3). لسه مش حجز مؤكد؛ الفريق بيتواصل ويأكّد
    (POST /hub/online-bookings/{id}/confirm)."""
    from app.core.rate_limit import _client_ip  # noqa: PLC0415
    from app.modules.hub.public_contact import resolve_public_site_branch  # noqa: PLC0415
    from app.modules.hub.public_room_booking import (  # noqa: PLC0415
        RoomBookingSubmissionFailure, submit_public_room_booking as submit,
    )

    branch = resolve_public_site_branch(db, request.url.hostname)
    if branch is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            {"code": "public_site_not_configured", "message": "Public booking site is not configured."},
        )

    try:
        result = submit(
            db, branch=branch, data=data,
            idempotency_key=idempotency_key, client_ip=_client_ip(request),
        )
    except RoomBookingSubmissionFailure as exc:
        raise HTTPException(exc.status_code, {"code": exc.code, "message": exc.message}) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    response.headers["Cache-Control"] = "no-store"
    return result


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
    user=Depends(get_manager_user),
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
    _assert_hub_branch(db, user, branch_id, "عرض نماذج التواصل")
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
    posts = crud.list_published_blog_posts(db, branch_id)
    return {"posts": [BlogPostItem.model_validate(p) for p in posts]}


@router.get("/hub/blog/posts/{slug}", response_model=BlogPostDetail)
async def get_blog_post(
    db: DbDep,
    slug: str,
    branch_id: int = Query(...),
):
    """مقال واحد كامل (بما فيه body) للعرض العام — بيزوّد views_count."""
    post = crud.get_published_blog_post_by_slug(db, branch_id, slug)
    if not post:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المقال غير موجود")
    crud.increment_blog_post_views(db, post)
    db.commit()
    db.refresh(post)
    return BlogPostDetail.model_validate(post)
