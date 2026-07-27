"""Secure public contact intake, CRM consent provenance, and PII retention."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.kernel import cache as cache_module
from app.core.kernel.cache import rate_limit
from app.modules.core import crud as core_crud
from app.modules.core.schemas import AuditLogCreate
from app.modules.crm.models import Lead
from app.modules.hub.models import ContactForm
from app.modules.hub.schemas import ContactFormCreate, ContactFormResponse

logger = logging.getLogger(__name__)

CONTACT_RETENTION_DAYS = 180
PUBLIC_MARKETING_LEAD_RETENTION_DAYS = 730
_SAFE_ENVIRONMENTS = {"development", "test", "testing"}
_SUCCESS_MESSAGES = {
    "ar": "شكراً! تم استلام طلبك وسيتواصل معك الفريق بخصوصه.",
    "en": "Thank you. Your request was received and the team will contact you about it.",
    "ru": "Спасибо. Ваш запрос получен, и команда свяжется с вами по нему.",
    "it": "Grazie. La richiesta è stata ricevuta e il team ti contatterà in merito.",
}


@dataclass(frozen=True)
class ContactSubmissionFailure(Exception):
    status_code: int
    code: str
    message: str


def _normalise_host(host: str | None) -> str:
    return (host or "").strip().lower().rstrip(".")


def resolve_public_site_branch(db: Session, host: str | None):
    """Resolve Host only through the existing explicit public-site allowlist.

    The map currently lives under ``CHAT_PUBLIC_HOST_BRANCH_MAP`` because it
    was the first public Host-bound contract.  Contact intake shares the map,
    not chat state; no browser branch value or branch-1 fallback is accepted.
    """

    normalised = _normalise_host(host)
    mapping = {
        _normalise_host(key): value
        for key, value in settings.CHAT_PUBLIC_HOST_BRANCH_MAP.items()
    }
    branch_id = mapping.get(normalised)
    if branch_id is None:
        return None
    branch = core_crud.get_branch(db, branch_id)
    if not branch or not branch.is_active:
        return None
    return branch


def _digest(value: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _payload_digest(data: ContactFormCreate) -> str:
    payload = data.model_dump(exclude={"website"}, mode="json")
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return _digest(encoded)


def _is_safe_environment() -> bool:
    return (settings.ENVIRONMENT or "").strip().lower() in _SAFE_ENVIRONMENTS


def _require_abuse_backend() -> None:
    if not _is_safe_environment() and cache_module._redis is None:
        raise ContactSubmissionFailure(
            503,
            "contact_protection_unavailable",
            "Contact service is temporarily unavailable.",
        )


def _enforce_abuse_limits(data: ContactFormCreate, requester_hash: str) -> None:
    _require_abuse_backend()
    identity = data.phone or data.email
    if not rate_limit(
        f"public-contact-ip:{requester_hash}",
        max_requests=5,
        window_seconds=600,
    ):
        raise ContactSubmissionFailure(
            429,
            "contact_rate_limited",
            "Too many contact requests. Please try again later.",
        )
    if identity and not rate_limit(
        f"public-contact-identity:{_digest(identity)}",
        max_requests=3,
        window_seconds=3600,
    ):
        raise ContactSubmissionFailure(
            429,
            "contact_identity_rate_limited",
            "Too many contact requests. Please try again later.",
        )


def _audit(
    db: Session,
    form: ContactForm,
    action: str,
    *,
    extra: dict | None = None,
) -> None:
    safe_metadata = {
        "public_reference": form.public_reference,
        "purpose": form.purpose,
        "source": form.source,
        "source_page": form.source_page,
        "language": form.language,
        "service_disclosure_version": form.service_disclosure_version,
        "marketing_consent": form.marketing_consent,
        "marketing_consent_version": form.marketing_consent_version,
        "crm_sync_status": form.crm_sync_status,
    }
    if extra:
        safe_metadata.update(extra)
    core_crud.create_audit_log(
        db,
        AuditLogCreate(
            user_id=None,
            branch_id=form.branch_id,
            action=action,
            entity_type="contact_form",
            entity_id=form.id,
            new_data=json.dumps(
                safe_metadata,
                ensure_ascii=False,
                sort_keys=True,
            ),
            ip_address=None,
            user_agent=None,
        ),
    )


def _lead_interest(purpose: str) -> str:
    if purpose in {"booking_request", "activity_request", "beach_service", "spa_request"}:
        return "booking"
    return "other"


def _create_marketing_lead(
    db: Session,
    form: ContactForm,
    now: datetime,
) -> Lead:
    """Create a marketing lead only for an explicit, versioned opt-in."""

    lead = Lead(
        branch_id=form.branch_id,
        full_name=form.full_name,
        phone=form.phone,
        email=form.email,
        interest=_lead_interest(form.purpose),
        stage="new",
        notes=f"{form.subject}\n\n{form.message}",
        public_contact_form_id=form.id,
        purpose=form.purpose,
        marketing_consent=True,
        marketing_consent_version=form.marketing_consent_version,
        marketing_consent_at=form.marketing_consent_at,
        retention_until=now + timedelta(days=PUBLIC_MARKETING_LEAD_RETENTION_DAYS),
    )
    db.add(lead)
    db.flush()
    return lead


def _existing_response(
    existing: ContactForm,
    payload_hash: str,
    language: str,
) -> ContactFormResponse:
    if not hmac.compare_digest(existing.payload_hash or "", payload_hash):
        raise ContactSubmissionFailure(
            409,
            "idempotency_conflict",
            "Idempotency-Key was already used with different contact data.",
        )
    return ContactFormResponse(
        message=_SUCCESS_MESSAGES.get(language, _SUCCESS_MESSAGES["en"]),
        reference=existing.public_reference,
    )


def submit_public_contact(
    db: Session,
    *,
    branch,
    data: ContactFormCreate,
    idempotency_key: str,
    client_ip: str,
) -> ContactFormResponse:
    """Accept one public request exactly once without logging raw PII."""

    key_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    payload_hash = _payload_digest(data)
    existing = (
        db.query(ContactForm)
        .filter(
            ContactForm.branch_id == branch.id,
            ContactForm.idempotency_key_hash == key_hash,
        )
        .first()
    )
    if existing:
        return _existing_response(existing, payload_hash, data.language)

    requester_hash = _digest(client_ip)
    _enforce_abuse_limits(data, requester_hash)

    # Honeypot submissions receive the same outward success shape but create
    # no contact, lead, or PII-bearing audit row.
    if data.website:
        logger.info(
            "Public contact honeypot suppressed: branch=%s requester=%s",
            branch.id,
            requester_hash[:12],
        )
        return ContactFormResponse(
            message=_SUCCESS_MESSAGES.get(data.language, _SUCCESS_MESSAGES["en"]),
            reference=f"contact_{secrets.token_urlsafe(12)}",
        )

    now = datetime.utcnow()
    form = ContactForm(
        branch_id=branch.id,
        public_reference=f"contact_{secrets.token_urlsafe(16)}",
        full_name=data.full_name,
        phone=data.phone,
        email=data.email,
        subject=data.subject,
        message=data.message,
        source_page=data.source_page,
        source="public_website",
        purpose=data.purpose,
        language=data.language,
        service_contact_authorized=True,
        service_disclosure_version=data.service_disclosure_version,
        service_contact_authorized_at=now,
        marketing_consent=data.marketing_consent,
        marketing_consent_version=data.marketing_consent_version,
        marketing_consent_at=now if data.marketing_consent else None,
        idempotency_key_hash=key_hash,
        payload_hash=payload_hash,
        requester_hash=requester_hash,
        retention_until=now + timedelta(days=CONTACT_RETENTION_DAYS),
        status="accepted",
        crm_sync_status=(
            "pending" if data.marketing_consent else "not_requested"
        ),
    )

    try:
        with db.begin_nested():
            db.add(form)
            db.flush()
    except IntegrityError:
        existing = (
            db.query(ContactForm)
            .filter(
                ContactForm.branch_id == branch.id,
                ContactForm.idempotency_key_hash == key_hash,
            )
            .first()
        )
        if existing:
            return _existing_response(existing, payload_hash, data.language)
        raise

    if data.marketing_consent:
        try:
            with db.begin_nested():
                lead = _create_marketing_lead(db, form, now)
                form.lead_id = lead.id
                form.crm_sync_status = "created"
        except Exception as exc:
            form.crm_sync_status = "failed"
            logger.exception(
                "CRM lead sync failed for public contact reference=%s",
                form.public_reference,
            )
            _audit(
                db,
                form,
                "public_contact_crm_sync_failed",
                extra={"error_type": type(exc).__name__},
            )

    _audit(db, form, "public_contact_submitted")
    db.commit()

    return ContactFormResponse(
        message=_SUCCESS_MESSAGES.get(data.language, _SUCCESS_MESSAGES["en"]),
        reference=form.public_reference,
    )


def purge_expired_public_contact_pii(
    db: Session,
    *,
    now: datetime | None = None,
    batch_size: int = 500,
) -> dict[str, int]:
    """Null expired PII while retaining non-PII consent/audit provenance."""

    cutoff = now or datetime.utcnow()
    contacts = (
        db.query(ContactForm)
        .filter(
            ContactForm.retention_until <= cutoff,
            ContactForm.purged_at.is_(None),
        )
        .order_by(ContactForm.id)
        .limit(batch_size)
        .all()
    )
    for form in contacts:
        form.full_name = None
        form.phone = None
        form.email = None
        form.subject = None
        form.message = None
        form.purged_at = cutoff
        form.status = "purged"
        _audit(db, form, "public_contact_pii_purged")

    remaining = max(0, batch_size - len(contacts))
    leads = []
    if remaining:
        leads = (
            db.query(Lead)
            .filter(
                Lead.public_contact_form_id.is_not(None),
                Lead.retention_until <= cutoff,
                Lead.purged_at.is_(None),
            )
            .order_by(Lead.id)
            .limit(remaining)
            .all()
        )
        for lead in leads:
            lead.full_name = None
            lead.phone = None
            lead.email = None
            lead.nationality = None
            lead.notes = None
            lead.purged_at = cutoff

    db.flush()
    return {"contacts": len(contacts), "leads": len(leads)}
