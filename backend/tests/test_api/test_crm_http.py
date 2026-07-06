"""
tests/test_api/test_crm_http.py
HTTP-level tests for the CRM module — TestClient through real routing,
permission dependencies and Pydantic validation (not direct service calls).

Regression coverage for a real routing bug found+fixed this session:
frontend/apps/admin/src/views/CRMView.vue's entire "leads" tab calls
`GET /api/v1/crm/leads` and `PATCH /api/v1/crm/leads/{id}` — the `Lead` model
and every crud function (create_lead/list_leads/get_lead/update_lead) already
existed and worked, but ZERO route was wired in api/router.py, and there
were no Pydantic schemas for Lead at all. Same class of bug as the
GET /restaurant/menu/categories 404 documented in CLAUDE.md § 11.6.

⚠️ Setup data created here must be `db.commit()`-ed, not `.flush()`-ed.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="CRM HTTP Branch", name_ar="فرع عملاء",
               code=f"CRM-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_customer_committed(db, branch):
    from app.modules.crm.models import Customer
    c = Customer(branch_id=branch.id, full_name="ياسمين حسن", segment="regular", source="walk_in")
    db.add(c)
    db.commit()
    return c


class TestCRMLeadsFlow:
    def test_create_list_and_advance_lead(self, client: TestClient, db, fake_redis, manager_headers):
        """Full round-trip through the exact endpoints CRMView.vue calls."""
        branch = make_branch_committed(db)

        create_resp = client.post(
            "/api/v1/crm/leads",
            json={
                "branch_id": branch.id, "full_name": "سيف الدين",
                "phone": "01099999999", "interest": "timeshare",
            },
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        lead = create_resp.json()
        assert lead["stage"] == "new"

        list_resp = client.get(
            "/api/v1/crm/leads", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert list_resp.status_code == 200
        ids = [l["id"] for l in list_resp.json()]
        assert lead["id"] in ids

        advance_resp = client.patch(
            f"/api/v1/crm/leads/{lead['id']}", json={"stage": "contacted"}, headers=manager_headers,
        )
        assert advance_resp.status_code == 200, advance_resp.text
        assert advance_resp.json()["stage"] == "contacted"

    def test_lead_won_is_terminal(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        lead = client.post(
            "/api/v1/crm/leads",
            json={"branch_id": branch.id, "full_name": "نور الهدى", "interest": "leasing"},
            headers=manager_headers,
        ).json()

        won_resp = client.patch(
            f"/api/v1/crm/leads/{lead['id']}", json={"stage": "won"}, headers=manager_headers,
        )
        assert won_resp.status_code == 200, won_resp.text
        assert won_resp.json()["won_at"] is not None

        second_resp = client.patch(
            f"/api/v1/crm/leads/{lead['id']}", json={"stage": "qualified"}, headers=manager_headers,
        )
        assert second_resp.status_code == 400

    def test_lead_lost_records_reason(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        lead = client.post(
            "/api/v1/crm/leads",
            json={"branch_id": branch.id, "full_name": "كريم عادل"},
            headers=manager_headers,
        ).json()

        lost_resp = client.patch(
            f"/api/v1/crm/leads/{lead['id']}",
            json={"stage": "lost", "lost_reason": "اختار منتجع آخر"},
            headers=manager_headers,
        )
        assert lost_resp.status_code == 200, lost_resp.text
        assert lost_resp.json()["lost_reason"] == "اختار منتجع آخر"
        assert lost_resp.json()["lost_at"] is not None

    def test_lead_lost_requires_reason(self, client: TestClient, db, fake_redis, manager_headers):
        """⚠️ باج حقيقي كان هنا: كان ممكن تقفل lead بحالة 'lost' من غير أي
        سبب — على عكس Opportunity.update_opportunity اللي بيرفض 'lost' من
        غير lost_reason من زمان. النتيجة: تقرير 'ليه بنخسر عملاء محتملين'
        كان ممكن يطلع فاضي لمعظم السجلات. اتصلح بنفس قاعدة Opportunity."""
        branch = make_branch_committed(db)
        lead = client.post(
            "/api/v1/crm/leads",
            json={"branch_id": branch.id, "full_name": "بدون سبب خسارة"},
            headers=manager_headers,
        ).json()

        resp = client.patch(
            f"/api/v1/crm/leads/{lead['id']}", json={"stage": "lost"}, headers=manager_headers,
        )
        assert resp.status_code == 400
        assert "سبب" in resp.json()["detail"]


class TestCRMPermissions:
    def test_blacklist_customer_requires_manager(self, client: TestClient, db, fake_redis):
        """Any authenticated user (waiter) must not be able to blacklist a
        customer — manager+ required, unlike most other CRM endpoints."""
        from tests.conftest import _create_test_user, _make_token
        branch = make_branch_committed(db)
        customer = make_customer_committed(db, branch)
        _create_test_user("crm-waiter@test.local", "waiter")
        headers = {"Authorization": f"Bearer {_make_token('crm-waiter@test.local')}"}

        resp = client.post(
            f"/api/v1/crm/customers/{customer.id}/blacklist",
            json={"reason": "شيك بدون رصيد"},
            headers=headers,
        )
        assert resp.status_code == 403


class TestCRMValidation:
    def test_create_lead_rejects_invalid_interest(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/crm/leads",
            json={"branch_id": branch.id, "full_name": "عميل", "interest": "spaceship"},
            headers=manager_headers,
        )
        assert resp.status_code == 422

    def test_update_lead_rejects_invalid_stage(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        lead = client.post(
            "/api/v1/crm/leads", json={"branch_id": branch.id, "full_name": "عميل آخر"},
            headers=manager_headers,
        ).json()

        resp = client.patch(
            f"/api/v1/crm/leads/{lead['id']}", json={"stage": "negotiation"}, headers=manager_headers,
        )
        assert resp.status_code == 422


class TestCRMCampaigns:
    """Regression coverage — same bug class as TestCRMLeadsFlow above: the
    Campaign model + crud + services already existed in full, but zero route
    was ever wired in api/router.py, so the feature was completely dead."""

    def test_create_list_update_campaign(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)

        create_resp = client.post(
            "/api/v1/crm/campaigns",
            json={
                "branch_id": branch.id, "name": "حملة الصيف",
                "campaign_type": "social_media",
                "start_date": "2026-07-01", "end_date": "2026-08-31",
                "budget": "5000.00",
            },
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        campaign = create_resp.json()
        assert campaign["status"] == "planned"
        assert campaign["revenue_attributed"] == "0.00"

        list_resp = client.get(
            "/api/v1/crm/campaigns", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert list_resp.status_code == 200
        ids = [c["id"] for c in list_resp.json()["items"]]
        assert campaign["id"] in ids

        get_resp = client.get(f"/api/v1/crm/campaigns/{campaign['id']}", headers=manager_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "حملة الصيف"

        update_resp = client.patch(
            f"/api/v1/crm/campaigns/{campaign['id']}",
            json={"status": "active", "leads_generated": 12, "revenue_attributed": "3200.50"},
            headers=manager_headers,
        )
        assert update_resp.status_code == 200, update_resp.text
        updated = update_resp.json()
        assert updated["status"] == "active"
        assert updated["leads_generated"] == 12
        assert updated["revenue_attributed"] == "3200.50"

    def test_create_campaign_rejects_end_before_start(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/crm/campaigns",
            json={
                "branch_id": branch.id, "name": "حملة خاطئة",
                "campaign_type": "email",
                "start_date": "2026-08-31", "end_date": "2026-07-01",
                "budget": "1000",
            },
            headers=manager_headers,
        )
        assert resp.status_code == 400

    def test_create_campaign_rejects_invalid_type(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/crm/campaigns",
            json={
                "branch_id": branch.id, "name": "حملة", "campaign_type": "carrier_pigeon",
                "start_date": "2026-07-01", "end_date": "2026-08-01", "budget": "100",
            },
            headers=manager_headers,
        )
        assert resp.status_code == 422

    def test_waiter_cannot_create_campaign(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/crm/campaigns",
            json={
                "branch_id": branch.id, "name": "حملة", "campaign_type": "email",
                "start_date": "2026-07-01", "end_date": "2026-08-01", "budget": "100",
            },
            headers=waiter_headers,
        )
        assert resp.status_code == 403


class TestCallNotes:
    """Regression coverage — same bug class as TestCRMLeadsFlow/TestCRMCampaigns
    above: the CallNote model already existed in full, but zero schema/crud/
    route was ever wired, so the feature was completely dead (404 always)."""

    def _make_lead(self, client, branch, headers):
        return client.post(
            "/api/v1/crm/leads",
            json={"branch_id": branch.id, "full_name": "عميل محتمل", "interest": "timeshare"},
            headers=headers,
        ).json()

    def test_create_and_list_call_notes(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        lead = self._make_lead(client, branch, manager_headers)

        create_resp = client.post(
            f"/api/v1/crm/leads/{lead['id']}/call-notes",
            json={
                "branch_id": branch.id, "lead_id": lead["id"],
                "direction": "outbound", "duration_min": 6,
                "summary": "اتكلمنا عن أسعار التايم شير", "outcome": "interested",
            },
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        note = create_resp.json()
        assert note["outcome"] == "interested"
        assert note["lead_id"] == lead["id"]

        list_resp = client.get(
            f"/api/v1/crm/leads/{lead['id']}/call-notes", headers=manager_headers,
        )
        assert list_resp.status_code == 200
        ids = [n["id"] for n in list_resp.json()]
        assert note["id"] in ids

    def test_create_call_note_rejects_unknown_lead(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/crm/leads/999999/call-notes",
            json={
                "branch_id": branch.id, "lead_id": 999999,
                "summary": "ملاحظة على عميل غير موجود",
            },
            headers=manager_headers,
        )
        assert resp.status_code == 404

    def test_list_call_notes_rejects_unknown_lead(self, client: TestClient, db, fake_redis, manager_headers):
        resp = client.get("/api/v1/crm/leads/999999/call-notes", headers=manager_headers)
        assert resp.status_code == 404

    def test_create_call_note_rejects_mismatched_lead_id(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        lead = self._make_lead(client, branch, manager_headers)
        other_lead = self._make_lead(client, branch, manager_headers)

        resp = client.post(
            f"/api/v1/crm/leads/{lead['id']}/call-notes",
            json={"branch_id": branch.id, "lead_id": other_lead["id"], "summary": "غير متطابق"},
            headers=manager_headers,
        )
        assert resp.status_code == 400

    def test_create_call_note_rejects_invalid_outcome(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        lead = self._make_lead(client, branch, manager_headers)

        resp = client.post(
            f"/api/v1/crm/leads/{lead['id']}/call-notes",
            json={
                "branch_id": branch.id, "lead_id": lead["id"],
                "summary": "نتيجة غير معروفة", "outcome": "will_call_back_never",
            },
            headers=manager_headers,
        )
        assert resp.status_code == 422


class TestLeadSources:
    """Regression coverage — same bug class as TestCallNotes above: the
    LeadSource model and Lead.source_id FK already existed in full, but zero
    schema/crud/route was ever wired, so there was no way to register a lead
    source (website/referral/social_media/...) via the API at all —
    Lead.source_id was inert from both ends."""

    def test_create_and_list_lead_sources(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)

        create_resp = client.post(
            "/api/v1/crm/lead-sources",
            json={"branch_id": branch.id, "name": "فيسبوك"},
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        source = create_resp.json()
        assert source["name"] == "فيسبوك"
        assert source["is_active"] is True

        list_resp = client.get(
            "/api/v1/crm/lead-sources", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert list_resp.status_code == 200
        ids = [s["id"] for s in list_resp.json()]
        assert source["id"] in ids

    def test_create_lead_source_requires_manager(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/crm/lead-sources",
            json={"branch_id": branch.id, "name": "إعلان"},
            headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_lead_can_be_linked_to_a_real_source(self, client: TestClient, db, fake_redis, manager_headers):
        """يتأكد إن Lead.source_id مش inert فعليًا — مصدر حقيقي اتسجّل عن طريق
        الـ API نفسه ينفع يترّبط بعميل محتمل جديد ويرجع صح في القراءة."""
        branch = make_branch_committed(db)
        source = client.post(
            "/api/v1/crm/lead-sources",
            json={"branch_id": branch.id, "name": "معرض سياحي"},
            headers=manager_headers,
        ).json()

        lead_resp = client.post(
            "/api/v1/crm/leads",
            json={"branch_id": branch.id, "full_name": "عميل من المعرض", "source_id": source["id"]},
            headers=manager_headers,
        )
        assert lead_resp.status_code == 201, lead_resp.text
        assert lead_resp.json()["source_id"] == source["id"]
