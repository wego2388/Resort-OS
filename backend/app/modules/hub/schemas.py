"""app/modules/hub/schemas.py — Pydantic v2"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ── HubPage ───────────────────────────────────────────────────────────

class HubPageCreate(BaseModel):
    branch_id:    int
    slug:         str = Field(..., max_length=100, pattern=r"^[a-z0-9-]+$")
    title:        str = Field(..., max_length=300)
    title_ar:     Optional[str] = Field(None, max_length=300)
    content:      Optional[str] = None
    content_ar:   Optional[str] = None
    page_type:    str = Field("info", pattern=r"^(info|offer|news|gallery|contact)$")
    meta_title:   Optional[str] = Field(None, max_length=200)
    meta_desc:    Optional[str] = Field(None, max_length=300)
    sort_order:   int = 100


class HubPageUpdate(BaseModel):
    title:        Optional[str] = None
    title_ar:     Optional[str] = None
    content:      Optional[str] = None
    content_ar:   Optional[str] = None
    meta_title:   Optional[str] = None
    meta_desc:    Optional[str] = None
    sort_order:   Optional[int] = None
    is_published: Optional[bool] = None


class HubPageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:           int
    branch_id:    int
    slug:         str
    title:        str
    title_ar:     Optional[str]
    page_type:    str
    is_published: bool
    published_at: Optional[datetime]
    meta_title:   Optional[str]
    meta_desc:    Optional[str]
    sort_order:   int
    created_at:   datetime
    updated_at:   datetime


# ── HubOffer ──────────────────────────────────────────────────────────

class HubOfferCreate(BaseModel):
    branch_id:      int
    title:          str = Field(..., max_length=300)
    title_ar:       Optional[str] = None
    description:    Optional[str] = None
    description_ar: Optional[str] = None
    offer_type:     str = Field(..., pattern=r"^(room|beach|restaurant|package|event)$")
    original_price: Decimal = Field(..., gt=0)
    offer_price:    Decimal = Field(..., gt=0)
    valid_from:     date
    valid_until:    date
    max_bookings:   int = -1
    image_url:      Optional[str] = Field(None, max_length=500)


class HubOfferUpdate(BaseModel):
    title:          Optional[str]     = None
    description:    Optional[str]     = None
    offer_price:    Optional[Decimal] = None
    valid_until:    Optional[date]    = None
    max_bookings:   Optional[int]     = None
    is_active:      Optional[bool]    = None
    image_url:      Optional[str]     = None


class HubOfferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:             int
    branch_id:      int
    title:          str
    title_ar:       Optional[str]
    offer_type:     str
    original_price: Decimal
    offer_price:    Decimal
    valid_from:     date
    valid_until:    date
    max_bookings:   int
    bookings_count: int
    is_active:      bool
    image_url:      Optional[str]
    created_at:     datetime
    updated_at:     datetime


# ── HubOnlineBooking ──────────────────────────────────────────────────

class OnlineBookingCreate(BaseModel):
    branch_id:      int
    offer_id:       Optional[int] = None
    guest_name:     str = Field(..., max_length=200)
    guest_phone:    str = Field(..., max_length=20)
    guest_email:    Optional[str] = Field(None, max_length=150)
    guests_count:   int = Field(1, ge=1)
    requested_date: date
    # بيانات الإقامة — اختيارية للـ lead العادي، إلزامية لو مطلوب PMS booking تلقائي
    check_in:       Optional[date] = None
    check_out:      Optional[date] = None
    room_type_id:   Optional[int]  = None
    bundle_id:      Optional[int]  = None
    adults:         int = Field(1, ge=1)
    children:       int = Field(0, ge=0)
    notes:          Optional[str] = None
    source:         str = Field("website", pattern=r"^(website|whatsapp|instagram|tiktok|other)$")


class OnlineBookingUpdate(BaseModel):
    status:       Optional[str] = Field(None, pattern=r"^(pending|confirmed|cancelled|no_show)$")
    notes:        Optional[str] = None
    total_amount: Optional[Decimal] = None


class OnlineBookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:             int
    branch_id:      int
    offer_id:       Optional[int]
    guest_name:     str
    guest_phone:    str
    guest_email:    Optional[str]
    guests_count:   int
    requested_date: date
    notes:          Optional[str]
    status:         str
    source:         str
    confirmed_by:   Optional[int]
    confirmed_at:   Optional[datetime]
    total_amount:    Decimal
    check_in:        Optional[date] = None
    check_out:       Optional[date] = None
    room_type_id:    Optional[int]  = None
    bundle_id:       Optional[int]  = None
    adults:          int = 1
    children:        int = 0
    pms_booking_id:  Optional[int]  = None
    public_reference: Optional[str] = None
    quoted_nightly_rate: Optional[Decimal] = None
    quoted_nights:        Optional[int] = None
    quoted_subtotal:      Optional[Decimal] = None
    quoted_vat_amount:    Optional[Decimal] = None
    quoted_service_amount: Optional[Decimal] = None
    quoted_total:          Optional[Decimal] = None
    quoted_currency:       Optional[str] = None
    quoted_at:              Optional[datetime] = None
    created_at:      datetime
    updated_at:      datetime


# ── Public contact ───────────────────────────────────────────────────────────

SERVICE_CONTACT_DISCLOSURE_VERSION = "service-contact-2026-07-26.v1"
MARKETING_CONSENT_VERSION = "marketing-contact-2026-07-26.v1"


def _normalise_public_phone(value):
    """مشتركة بين ContactFormCreate وPublicRoomBookingRequest — نفس منطق
    تطبيع رقم التليفون الدولي بالظبط."""
    if value is None:
        return None
    clean = re.sub(r"[\s().-]+", "", str(value))
    if not clean:
        return None
    if clean.startswith("00"):
        clean = f"+{clean[2:]}"
    elif clean.startswith("01") and len(clean) == 11:
        clean = f"+2{clean}"
    elif clean.startswith("201") and len(clean) == 12:
        clean = f"+{clean}"
    if not re.fullmatch(r"\+[1-9]\d{7,14}", clean):
        raise ValueError("phone must be a valid international number")
    return clean


def _normalise_public_email(value):
    """مشتركة بين ContactFormCreate وPublicRoomBookingRequest."""
    if value is None:
        return None
    clean = str(value).strip().lower()
    if not clean:
        return None
    if not re.fullmatch(
        r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
        r"@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
        r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+",
        clean,
    ):
        raise ValueError("email must be valid")
    return clean

ContactPurpose = Literal[
    "general_inquiry",
    "booking_request",
    "activity_request",
    "beach_service",
    "spa_request",
    "room_service",
    "housekeeping",
    "maintenance_request",
]


class ContactFormCreate(BaseModel):
    """Strict public contract; browser-controlled branch IDs are forbidden."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str = Field(..., min_length=2, max_length=120)
    phone: Optional[str] = Field(None, max_length=32)
    email: Optional[str] = Field(None, max_length=254)
    subject: str = Field(..., min_length=3, max_length=160)
    message: str = Field(..., min_length=3, max_length=2000)
    source_page: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^/[A-Za-z0-9/_-]*$",
    )
    purpose: ContactPurpose
    language: Literal["ar", "en", "ru", "it"] = "ar"
    service_contact_authorized: Literal[True]
    service_disclosure_version: Literal[
        SERVICE_CONTACT_DISCLOSURE_VERSION
    ]
    marketing_consent: bool = False
    marketing_consent_version: Optional[str] = Field(None, max_length=40)
    # Intentionally accepted but never persisted. A non-empty value is a bot
    # signal and receives a generic accepted response without creating a row.
    website: str = Field("", max_length=200)

    @field_validator("phone", mode="before")
    @classmethod
    def normalise_phone(cls, value):
        return _normalise_public_phone(value)

    @field_validator("email", mode="before")
    @classmethod
    def normalise_email(cls, value):
        return _normalise_public_email(value)

    @field_validator("full_name", "subject", "message")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        if any(ord(char) < 32 and char not in "\n\t" for char in value):
            raise ValueError("control characters are not allowed")
        return value

    @model_validator(mode="after")
    def validate_contact_and_consent(self):
        if not self.phone and not self.email:
            raise ValueError("phone or email is required")
        if self.marketing_consent:
            if self.marketing_consent_version != MARKETING_CONSENT_VERSION:
                raise ValueError(
                    "current marketing consent version is required"
                )
        elif self.marketing_consent_version is not None:
            raise ValueError(
                "marketing consent version requires marketing consent"
            )
        return self


class ContactFormResponse(BaseModel):
    message: str
    reference: str


class ContactFormListItem(BaseModel):
    """Staff-facing view of one public contact submission.

    A CRM Lead is only created when the guest opts into marketing_consent
    (see app.modules.hub.public_contact); every submission — consenting or
    not — is a real, explicit "please contact me" request and must stay
    visible to staff here regardless of that separate marketing choice.
    """

    model_config = ConfigDict(from_attributes=True)
    id:                  int
    public_reference:    str
    full_name:           Optional[str]
    phone:               Optional[str]
    email:               Optional[str]
    subject:             Optional[str]
    message:             Optional[str]
    source_page:         Optional[str]
    purpose:             str
    language:            str
    marketing_consent:   bool
    crm_sync_status:     str
    lead_id:             Optional[int]
    status:              str
    created_at:           datetime


# ── Public room catalog + online booking request (OPS-DATA-02 §7.2/§7.3) ──

ROOM_BOOKING_DISCLOSURE_VERSION = SERVICE_CONTACT_DISCLOSURE_VERSION


class RoomCatalogEntryRead(BaseModel):
    """راجع hub.public_catalog.CatalogEntry — نفس الحقول بالظبط."""
    entry_type:         Literal["room_type", "bundle"]
    id:                  int
    name:                str
    name_ar:             Optional[str] = None
    capacity:            int
    base_price:          Decimal
    vat_amount:          Decimal
    service_amount:      Decimal
    total:               Decimal
    currency:            str
    price_unit:          str
    effective_from:      date
    includes_breakfast:  bool


class RoomQuoteRead(BaseModel):
    """لقطة سعر — نفس الشكل المحفوظ في HubOnlineBooking.quoted_* عند التأكيد."""
    entry_type:      Literal["room_type", "bundle"]
    room_type_id:    Optional[int] = None
    bundle_id:        Optional[int] = None
    nightly_rate:      Decimal
    nights:            int
    subtotal:          Decimal
    vat_amount:        Decimal
    service_amount:    Decimal
    total:             Decimal
    currency:          str
    quoted_at:          datetime


class PublicRoomBookingRequest(BaseModel):
    """طلب حجز غرفة/باقة عام — بديل توجيه حجز الغرف لـ /hub/contact
    (راجع OPS-DATA-02 §7.3). لسه مش حجز مؤكد؛ الفريق بيتواصل ويأكّد."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    guest_name:  str = Field(..., min_length=2, max_length=120)
    guest_phone: str = Field(..., max_length=32)
    guest_email: Optional[str] = Field(None, max_length=254)
    check_in:    date
    check_out:   date
    adults:      int = Field(1, ge=1)
    children:    int = Field(0, ge=0)
    room_type_id: Optional[int] = None
    bundle_id:    Optional[int] = None
    notes:        Optional[str] = Field(None, max_length=1000)
    language:     Literal["ar", "en", "ru", "it"] = "ar"
    service_contact_authorized: Literal[True]
    service_disclosure_version: Literal[ROOM_BOOKING_DISCLOSURE_VERSION]
    # مقبول لكن مش بيتخزّن أبدًا — قيمة غير فاضية = إشارة بوت (راجع
    # ContactFormCreate.website لنفس النمط بالظبط).
    website: str = Field("", max_length=200)

    @field_validator("guest_phone", mode="before")
    @classmethod
    def normalise_phone(cls, value):
        result = _normalise_public_phone(value)
        if result is None:
            raise ValueError("guest_phone is required")
        return result

    @field_validator("guest_email", mode="before")
    @classmethod
    def normalise_email(cls, value):
        return _normalise_public_email(value)

    @model_validator(mode="after")
    def _exactly_one_target(self):
        if bool(self.room_type_id) == bool(self.bundle_id):
            raise ValueError("حدد إما room_type_id أو bundle_id، وليس الاثنين معًا ولا بلا أي منهما")
        return self


class PublicRoomBookingResponse(BaseModel):
    message:   str
    reference: str
    quote:      Optional[RoomQuoteRead] = None


# ── Simple fixed-shape response schemas ──────────────────────────────────────

class BlogPostItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:           int
    title:        str
    slug:         str
    excerpt:      Optional[str]
    cover_image:  Optional[str]
    published_at: Optional[datetime]
    views_count:  int

class BlogPostsResponse(BaseModel):
    posts: list[BlogPostItem]

class BlogPostDetail(BlogPostItem):
    """نفس بيانات القائمة + النص الكامل — مقصود منفصل عن BlogPostItem
    (مش body في كل عنصر قائمة، توفير bandwidth للمقالات الطويلة)."""
    body: str
