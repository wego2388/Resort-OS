"""CL-02B public contact, consent, CRM, privacy, and abuse contract."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa

from app.core.config import settings
from app.modules.hub import public_contact
from app.modules.hub.models import ContactForm
from app.modules.hub.schemas import (
    MARKETING_CONSENT_VERSION,
    SERVICE_CONTACT_DISCLOSURE_VERSION,
)
from tests.test_api.test_pms import make_branch


@pytest.fixture(autouse=True)
def _reset_public_contact_limits(monkeypatch):
    from app.core.kernel.cache import invalidate_pattern

    invalidate_pattern("public-contact")
    invalidate_pattern("rl:public")
    monkeypatch.setattr(settings, "CHAT_PUBLIC_HOST_BRANCH_MAP", {})


def _site(monkeypatch, db, host: str = "public-contact.test"):
    branch = make_branch(db)
    db.commit()
    monkeypatch.setattr(
        settings,
        "CHAT_PUBLIC_HOST_BRANCH_MAP",
        {host: branch.id},
    )
    return branch, host


def _headers(host: str, key: str = "contact-request-00000001") -> dict[str, str]:
    return {"host": host, "Idempotency-Key": key}


def _payload(**overrides) -> dict:
    payload = {
        "full_name": "زائر اختبار",
        "phone": "0100 123 4567",
        "email": "Visitor@Example.COM",
        "subject": "استفسار عن الإقامة",
        "message": "أرغب في معرفة التفاصيل المتاحة.",
        "source_page": "/contact",
        "purpose": "general_inquiry",
        "language": "ar",
        "service_contact_authorized": True,
        "service_disclosure_version": SERVICE_CONTACT_DISCLOSURE_VERSION,
        "marketing_consent": False,
        "marketing_consent_version": None,
        "website": "",
    }
    payload.update(overrides)
    return payload


def test_service_contact_is_accepted_without_silent_marketing_lead(
    client, db, monkeypatch,
):
    from app.modules.core.models import AuditLog
    from app.modules.crm.models import Lead

    branch, host = _site(monkeypatch, db)
    response = client.post(
        "/api/v1/hub/contact",
        headers=_headers(host),
        json=_payload(),
    )

    assert response.status_code == 202
    assert response.headers["cache-control"] == "no-store"
    form = db.query(ContactForm).filter_by(
        public_reference=response.json()["reference"]
    ).one()
    assert form.branch_id == branch.id
    assert form.phone == "+201001234567"
    assert form.email == "visitor@example.com"
    assert form.service_contact_authorized is True
    assert form.service_disclosure_version == SERVICE_CONTACT_DISCLOSURE_VERSION
    assert form.marketing_consent is False
    assert form.lead_id is None
    assert form.crm_sync_status == "not_requested"
    assert db.query(Lead).filter_by(branch_id=branch.id).count() == 0

    audit = db.query(AuditLog).filter_by(
        entity_type="contact_form",
        entity_id=form.id,
        action="public_contact_submitted",
    ).one()
    assert "زائر اختبار" not in (audit.new_data or "")
    assert "0100" not in (audit.new_data or "")
    assert "أرغب" not in (audit.new_data or "")
    assert audit.ip_address is None
    assert audit.user_agent is None


def test_marketing_opt_in_creates_provenanced_encrypted_lead(
    client, db, monkeypatch,
):
    from app.modules.crm.models import Lead

    _, host = _site(monkeypatch, db)
    response = client.post(
        "/api/v1/hub/contact",
        headers=_headers(host, "marketing-request-000001"),
        json=_payload(
            purpose="booking_request",
            marketing_consent=True,
            marketing_consent_version=MARKETING_CONSENT_VERSION,
        ),
    )

    assert response.status_code == 202
    form = db.query(ContactForm).filter_by(
        public_reference=response.json()["reference"]
    ).one()
    lead = db.query(Lead).filter_by(public_contact_form_id=form.id).one()
    assert form.lead_id == lead.id
    assert form.crm_sync_status == "created"
    assert lead.marketing_consent is True
    assert lead.marketing_consent_version == MARKETING_CONSENT_VERSION
    assert lead.marketing_consent_at is not None
    assert lead.purpose == "booking_request"
    assert lead.full_name == "زائر اختبار"

    raw_form = db.execute(sa.text(
        """
        SELECT full_name, phone, email, subject, message
          FROM contact_forms
         WHERE id = :form_id
        """
    ), {"form_id": form.id}).mappings().one()
    raw_lead = db.execute(sa.text(
        """
        SELECT full_name, phone, email, notes
          FROM leads
         WHERE id = :lead_id
        """
    ), {"lead_id": lead.id}).mappings().one()
    assert raw_form["full_name"] != "زائر اختبار"
    assert raw_form["phone"] != "+201001234567"
    assert raw_form["email"] != "visitor@example.com"
    assert "الإقامة" not in raw_form["subject"]
    assert "التفاصيل" not in raw_form["message"]
    assert raw_lead["full_name"] != "زائر اختبار"
    assert raw_lead["phone"] != "+201001234567"
    assert raw_lead["email"] != "visitor@example.com"
    assert "التفاصيل" not in raw_lead["notes"]


def test_idempotency_replays_once_and_conflicting_payload_is_rejected(
    client, db, monkeypatch,
):
    branch, host = _site(monkeypatch, db)
    headers = _headers(host, "same-contact-request-0001")
    first = client.post("/api/v1/hub/contact", headers=headers, json=_payload())
    replay = client.post("/api/v1/hub/contact", headers=headers, json=_payload())
    conflict = client.post(
        "/api/v1/hub/contact",
        headers=headers,
        json=_payload(message="رسالة مختلفة تماماً."),
    )

    assert first.status_code == 202
    assert replay.status_code == 202
    assert replay.json() == first.json()
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_conflict"
    assert db.query(ContactForm).filter_by(branch_id=branch.id).count() == 1
    row = db.query(ContactForm).filter_by(branch_id=branch.id).one()
    assert "same-contact-request-0001" not in row.idempotency_key_hash


@pytest.mark.parametrize(
    ("change", "expected_status"),
    [
        ({"branch_id": 999}, 422),
        ({"unexpected": "field"}, 422),
        ({"message": "x" * 2001}, 422),
        ({"phone": "123", "email": None}, 422),
        ({"phone": None, "email": "not-an-email"}, 422),
        ({"phone": None, "email": None}, 422),
        ({"source_page": "https://evil.example/contact"}, 422),
        ({"service_contact_authorized": False}, 422),
        ({"service_disclosure_version": "old-version"}, 422),
        (
            {
                "marketing_consent": True,
                "marketing_consent_version": None,
            },
            422,
        ),
        (
            {
                "marketing_consent": False,
                "marketing_consent_version": MARKETING_CONSENT_VERSION,
            },
            422,
        ),
    ],
)
def test_strict_schema_rejects_untrusted_or_malformed_fields(
    client, db, monkeypatch, change, expected_status,
):
    branch, host = _site(monkeypatch, db)
    response = client.post(
        "/api/v1/hub/contact",
        headers=_headers(host, f"invalid-contact-{abs(hash(str(change)))}"),
        json=_payload(**change),
    )
    assert response.status_code == expected_status
    assert db.query(ContactForm).filter_by(branch_id=branch.id).count() == 0


def test_host_mapping_is_required_and_has_no_branch_one_fallback(
    client, db, monkeypatch,
):
    branch_a = make_branch(db)
    branch_b = make_branch(db)
    db.commit()
    monkeypatch.setattr(
        settings,
        "CHAT_PUBLIC_HOST_BRANCH_MAP",
        {"site-a.test": branch_a.id},
    )

    unknown = client.post(
        "/api/v1/hub/contact",
        headers=_headers("unknown.test", "unknown-host-contact-01"),
        json=_payload(),
    )
    spoof = client.post(
        "/api/v1/hub/contact",
        headers=_headers("site-a.test", "spoof-branch-contact-01"),
        json=_payload(branch_id=branch_b.id),
    )
    accepted = client.post(
        "/api/v1/hub/contact",
        headers=_headers("site-a.test", "mapped-branch-contact-01"),
        json=_payload(),
    )

    assert unknown.status_code == 404
    assert spoof.status_code == 422
    assert accepted.status_code == 202
    assert db.query(ContactForm).filter_by(branch_id=branch_a.id).one().branch_id == branch_a.id


def test_idempotency_header_is_required(client, db, monkeypatch):
    branch, host = _site(monkeypatch, db)
    response = client.post(
        "/api/v1/hub/contact",
        headers={"host": host},
        json=_payload(),
    )
    assert response.status_code == 422


def test_honeypot_returns_generic_success_without_persisting_pii(
    client, db, monkeypatch,
):
    branch, host = _site(monkeypatch, db)
    response = client.post(
        "/api/v1/hub/contact",
        headers=_headers(host, "honeypot-contact-000001"),
        json=_payload(website="https://spam.example"),
    )
    assert response.status_code == 202
    assert response.json()["reference"].startswith("contact_")
    assert db.query(ContactForm).filter_by(branch_id=branch.id).count() == 0


def test_application_abuse_limit_returns_429(client, db, monkeypatch):
    branch, host = _site(monkeypatch, db)
    monkeypatch.setattr(public_contact, "rate_limit", lambda *args, **kwargs: False)
    response = client.post(
        "/api/v1/hub/contact",
        headers=_headers(host, "rate-limited-contact-01"),
        json=_payload(),
    )
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "contact_rate_limited"
    assert db.query(ContactForm).filter_by(branch_id=branch.id).count() == 0


def test_crm_failure_is_logged_and_service_request_remains_accepted(
    client, db, monkeypatch,
):
    from app.modules.core.models import AuditLog

    _, host = _site(monkeypatch, db)

    def _fail(*args, **kwargs):
        raise RuntimeError("simulated CRM outage")

    monkeypatch.setattr(public_contact, "_create_marketing_lead", _fail)
    response = client.post(
        "/api/v1/hub/contact",
        headers=_headers(host, "crm-failure-contact-001"),
        json=_payload(
            marketing_consent=True,
            marketing_consent_version=MARKETING_CONSENT_VERSION,
        ),
    )

    assert response.status_code == 202
    form = db.query(ContactForm).filter_by(
        public_reference=response.json()["reference"]
    ).one()
    assert form.status == "accepted"
    assert form.crm_sync_status == "failed"
    assert form.lead_id is None
    failure_audit = db.query(AuditLog).filter_by(
        action="public_contact_crm_sync_failed",
        entity_id=form.id,
    ).one()
    assert "RuntimeError" in failure_audit.new_data
    assert "simulated CRM outage" not in failure_audit.new_data


def test_retention_purge_nulls_pii_but_keeps_provenance(
    client, db, monkeypatch,
):
    from app.modules.crm.models import Lead

    _, host = _site(monkeypatch, db)
    response = client.post(
        "/api/v1/hub/contact",
        headers=_headers(host, "retention-contact-00001"),
        json=_payload(
            marketing_consent=True,
            marketing_consent_version=MARKETING_CONSENT_VERSION,
        ),
    )
    assert response.status_code == 202
    form = db.query(ContactForm).filter_by(
        public_reference=response.json()["reference"]
    ).one()
    lead = db.query(Lead).filter_by(public_contact_form_id=form.id).one()
    cutoff = datetime.utcnow()
    form.retention_until = cutoff - timedelta(seconds=1)
    lead.retention_until = cutoff - timedelta(seconds=1)
    db.commit()

    result = public_contact.purge_expired_public_contact_pii(
        db,
        now=cutoff,
    )
    db.commit()
    db.expire_all()

    form = db.query(ContactForm).filter_by(id=form.id).one()
    lead = db.query(Lead).filter_by(id=lead.id).one()
    assert result == {"contacts": 1, "leads": 1}
    assert (form.full_name, form.phone, form.email, form.subject, form.message) == (
        None,
        None,
        None,
        None,
        None,
    )
    assert form.status == "purged"
    assert form.purged_at == cutoff
    assert form.service_disclosure_version == SERVICE_CONTACT_DISCLOSURE_VERSION
    assert form.marketing_consent_version == MARKETING_CONSENT_VERSION
    assert (lead.full_name, lead.phone, lead.email, lead.notes) == (
        None,
        None,
        None,
        None,
    )
    assert lead.purged_at == cutoff
    assert lead.marketing_consent_version == MARKETING_CONSENT_VERSION


# ── GET /hub/contact-forms — staff visibility (CL-02B follow-up) ───────────
# A CRM Lead is only created for explicit marketing_consent, but every
# submission is a real "please contact me" request from the guest — it must
# never be invisible to staff just because the guest declined marketing.

def test_contact_forms_list_shows_non_consenting_submissions_to_staff(
    client, db, monkeypatch, manager_headers,
):
    branch, host = _site(monkeypatch, db)
    submit = client.post(
        "/api/v1/hub/contact",
        headers=_headers(host, "staff-visibility-00001"),
        json=_payload(purpose="booking_request", marketing_consent=False),
    )
    assert submit.status_code == 202
    reference = submit.json()["reference"]

    response = client.get(
        "/api/v1/hub/contact-forms",
        headers=manager_headers,
        params={"branch_id": branch.id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["public_reference"] == reference
    assert item["marketing_consent"] is False
    assert item["crm_sync_status"] == "not_requested"
    assert item["lead_id"] is None
    # Staff need the actual request content to follow up manually — decrypted
    # transparently through the ORM, same as any other EncryptedString field.
    assert item["full_name"] == "زائر اختبار"
    assert item["subject"] == "استفسار عن الإقامة"


def test_contact_forms_list_requires_manager_role(
    client, db, monkeypatch, cashier_headers,
):
    branch, host = _site(monkeypatch, db)
    client.post(
        "/api/v1/hub/contact",
        headers=_headers(host, "role-gate-00001"),
        json=_payload(),
    )

    response = client.get(
        "/api/v1/hub/contact-forms",
        headers=cashier_headers,
        params={"branch_id": branch.id},
    )

    assert response.status_code == 403


def test_contact_forms_list_filters_by_crm_sync_status_and_scopes_to_branch(
    client, db, monkeypatch, manager_headers,
):
    branch_a, host_a = _site(monkeypatch, db, host="branch-a.test")
    other_branch = make_branch(db)
    db.commit()
    monkeypatch.setattr(
        settings,
        "CHAT_PUBLIC_HOST_BRANCH_MAP",
        {host_a: branch_a.id, "branch-b.test": other_branch.id},
    )

    client.post(
        "/api/v1/hub/contact",
        headers=_headers(host_a, "scope-consenting-00001"),
        json=_payload(
            marketing_consent=True,
            marketing_consent_version=MARKETING_CONSENT_VERSION,
        ),
    )
    client.post(
        "/api/v1/hub/contact",
        headers=_headers(host_a, "scope-nonconsenting-00001"),
        json=_payload(marketing_consent=False),
    )
    client.post(
        "/api/v1/hub/contact",
        headers=_headers("branch-b.test", "scope-other-branch-00001"),
        json=_payload(marketing_consent=False),
    )

    response = client.get(
        "/api/v1/hub/contact-forms",
        headers=manager_headers,
        params={"branch_id": branch_a.id, "crm_sync_status": "not_requested"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["crm_sync_status"] == "not_requested"
