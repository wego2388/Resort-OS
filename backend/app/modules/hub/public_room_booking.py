"""Public online room/bundle booking requests (OPS-DATA-02 §7.3).

Mirrors app.modules.hub.public_contact's security contract exactly
(idempotency, honeypot, rate limiting, branch resolved server-side from
Host — never trusted from the client) but persists a HubOnlineBooking with
a real, versioned quote snapshot instead of a free-text ContactForm.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.kernel import cache as cache_module
from app.core.kernel.cache import rate_limit
from app.modules.hub import public_catalog
from app.modules.hub.models import HubOnlineBooking
from app.modules.hub.public_contact import _digest, _is_safe_environment
from app.modules.hub.schemas import PublicRoomBookingRequest, PublicRoomBookingResponse, RoomQuoteRead

logger = logging.getLogger(__name__)

_SUCCESS_MESSAGES = {
    "ar": "شكراً! تم استلام طلب حجزك وسيتواصل معك الفريق لتأكيد التفاصيل والدفع.",
    "en": "Thank you. Your booking request was received; the team will contact you to confirm details and payment.",
    "ru": "Спасибо. Ваш запрос на бронирование получен; команда свяжется с вами для подтверждения деталей и оплаты.",
    "it": "Grazie. La tua richiesta di prenotazione è stata ricevuta; il team ti contatterà per confermare dettagli e pagamento.",
}


@dataclass(frozen=True)
class RoomBookingSubmissionFailure(Exception):
    status_code: int
    code: str
    message: str


def _new_reference() -> str:
    return f"roombkg_{secrets.token_urlsafe(16)}"


def _payload_digest(data: PublicRoomBookingRequest) -> str:
    payload = data.model_dump(exclude={"website"}, mode="json")
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return _digest(encoded)


def _require_abuse_backend() -> None:
    if not _is_safe_environment() and cache_module._redis is None:
        raise RoomBookingSubmissionFailure(
            503, "room_booking_protection_unavailable",
            "Room booking service is temporarily unavailable.",
        )


def _enforce_abuse_limits(requester_hash: str, identity_hash: str) -> None:
    _require_abuse_backend()
    if not rate_limit(f"public-room-booking-ip:{requester_hash}", max_requests=5, window_seconds=600):
        raise RoomBookingSubmissionFailure(
            429, "room_booking_rate_limited", "Too many booking requests. Please try again later.",
        )
    if not rate_limit(f"public-room-booking-identity:{identity_hash}", max_requests=3, window_seconds=3600):
        raise RoomBookingSubmissionFailure(
            429, "room_booking_identity_rate_limited", "Too many booking requests. Please try again later.",
        )


def _quote_read(booking: HubOnlineBooking) -> RoomQuoteRead:
    return RoomQuoteRead(
        entry_type="bundle" if booking.bundle_id else "room_type",
        room_type_id=booking.room_type_id,
        bundle_id=booking.bundle_id,
        nightly_rate=booking.quoted_nightly_rate,
        nights=booking.quoted_nights,
        subtotal=booking.quoted_subtotal,
        vat_amount=booking.quoted_vat_amount,
        service_amount=booking.quoted_service_amount,
        total=booking.quoted_total,
        currency=booking.quoted_currency,
        quoted_at=booking.quoted_at,
    )


def _response_for_existing(
    existing: HubOnlineBooking, payload_hash: str, language: str,
) -> PublicRoomBookingResponse:
    """طلب اتبعت قبل كده بنفس Idempotency-Key — لازم يرجّع بالظبط نفس
    النتيجة الأصلية من غير ما يعيد حساب quote أو ينشئ صف جديد. نفس مفتاح
    مع بيانات مختلفة = تعارض حقيقي (409)، نفس نمط submit_public_contact."""
    if not hmac.compare_digest(existing.payload_hash or "", payload_hash):
        raise RoomBookingSubmissionFailure(
            409, "idempotency_conflict", "Idempotency-Key was already used with different booking data.",
        )
    return PublicRoomBookingResponse(
        message=_SUCCESS_MESSAGES.get(language, _SUCCESS_MESSAGES["en"]),
        reference=existing.public_reference,
        quote=_quote_read(existing) if existing.quoted_total is not None else None,
    )


def submit_public_room_booking(
    db: Session,
    *,
    branch,
    data: PublicRoomBookingRequest,
    idempotency_key: str,
    client_ip: str,
) -> PublicRoomBookingResponse:
    """يحسب quote حقيقي (نفس محرك hub.public_catalog اللي بيغذّي الكتالوج
    العام) ويحفظه كلقطة على HubOnlineBooking — التأكيد لاحقًا (hub.services.
    confirm_booking) بيحصّل بالظبط السعر ده، مش سعر حي وقت التأكيد."""
    key_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    payload_hash = _payload_digest(data)
    existing = (
        db.query(HubOnlineBooking)
        .filter(
            HubOnlineBooking.branch_id == branch.id,
            HubOnlineBooking.idempotency_key_hash == key_hash,
        )
        .first()
    )
    if existing:
        return _response_for_existing(existing, payload_hash, data.language)

    requester_hash = _digest(client_ip)
    identity_hash = _digest(data.guest_phone)
    _enforce_abuse_limits(requester_hash, identity_hash)

    # Honeypot submissions receive the same outward success shape but create
    # no booking, quote, or PII-bearing row — same pattern as public_contact.
    if data.website:
        logger.info(
            "Public room-booking honeypot suppressed: branch=%s requester=%s",
            branch.id, requester_hash[:12],
        )
        return PublicRoomBookingResponse(
            message=_SUCCESS_MESSAGES.get(data.language, _SUCCESS_MESSAGES["en"]),
            reference=_new_reference(),
        )

    quote = public_catalog.compute_quote(
        db, branch.id,
        room_type_id=data.room_type_id, bundle_id=data.bundle_id,
        check_in=data.check_in, check_out=data.check_out,
        adults=data.adults, children=data.children,
    )

    now = datetime.utcnow()
    booking = HubOnlineBooking(
        branch_id=branch.id,
        guest_name=data.guest_name,
        guest_phone=data.guest_phone,
        guest_email=data.guest_email,
        guests_count=data.adults + data.children,
        requested_date=data.check_in,
        check_in=data.check_in,
        check_out=data.check_out,
        room_type_id=data.room_type_id,
        bundle_id=data.bundle_id,
        adults=data.adults,
        children=data.children,
        notes=data.notes,
        status="pending",
        source="website",
        quoted_nightly_rate=quote.nightly_rate,
        quoted_nights=quote.nights,
        quoted_subtotal=quote.subtotal,
        quoted_vat_amount=quote.vat_amount,
        quoted_service_amount=quote.service_amount,
        quoted_total=quote.total,
        quoted_currency=quote.currency,
        quoted_at=now,
        quote_version=public_catalog.QUOTE_VERSION,
        public_reference=_new_reference(),
        idempotency_key_hash=key_hash,
        payload_hash=payload_hash,
        requester_hash=requester_hash,
    )

    try:
        with db.begin_nested():
            db.add(booking)
            db.flush()
    except IntegrityError:
        existing = (
            db.query(HubOnlineBooking)
            .filter(
                HubOnlineBooking.branch_id == branch.id,
                HubOnlineBooking.idempotency_key_hash == key_hash,
            )
            .first()
        )
        if existing:
            return _response_for_existing(existing, payload_hash, data.language)
        raise

    db.commit()
    db.refresh(booking)
    return PublicRoomBookingResponse(
        message=_SUCCESS_MESSAGES.get(data.language, _SUCCESS_MESSAGES["en"]),
        reference=booking.public_reference,
        quote=_quote_read(booking),
    )
