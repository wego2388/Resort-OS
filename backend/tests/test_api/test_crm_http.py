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
from datetime import date, timedelta

from fastapi.testclient import TestClient

from tests.test_api.test_pms import make_room, make_room_type


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


class TestLeadDetailsUpdate:
    """⚠️ فجوة حقيقية كانت هنا: الـ endpoint الوحيد لتعديل lead
    (PATCH /crm/leads/{id}) كان بيغيّر الـ stage بس — مفيش أي طريقة تصلح
    بيها بيانات أساسية غلط (مصدر خاطئ، رقم هاتف غلط) بعد الإنشاء غير
    الدخول على الداتابيز مباشرة. اتضاف PATCH /crm/leads/{id}/details."""

    def test_reassign_lead_source_and_fix_phone(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        source_a = client.post(
            "/api/v1/crm/lead-sources", json={"branch_id": branch.id, "name": "مصدر أ"},
            headers=manager_headers,
        ).json()
        source_b = client.post(
            "/api/v1/crm/lead-sources", json={"branch_id": branch.id, "name": "مصدر ب"},
            headers=manager_headers,
        ).json()
        lead = client.post(
            "/api/v1/crm/leads",
            json={"branch_id": branch.id, "full_name": "عميل قابل للتعديل",
                  "source_id": source_a["id"], "phone": "01000000000"},
            headers=manager_headers,
        ).json()
        assert lead["source_id"] == source_a["id"]

        resp = client.patch(
            f"/api/v1/crm/leads/{lead['id']}/details",
            json={"source_id": source_b["id"], "phone": "01011112222"},
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        updated = resp.json()
        assert updated["source_id"] == source_b["id"]
        assert updated["phone"] == "01011112222"
        assert updated["stage"] == "new"  # التعديل ما بيغيّرش الـ stage

    def test_cannot_edit_details_of_closed_lead(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        lead = client.post(
            "/api/v1/crm/leads",
            json={"branch_id": branch.id, "full_name": "عميل مغلق"},
            headers=manager_headers,
        ).json()
        client.patch(
            f"/api/v1/crm/leads/{lead['id']}",
            json={"stage": "lost", "lost_reason": "غير مهتم"},
            headers=manager_headers,
        )

        resp = client.patch(
            f"/api/v1/crm/leads/{lead['id']}/details",
            json={"phone": "01099998888"},
            headers=manager_headers,
        )
        assert resp.status_code == 400


class TestCustomerDuplicates:
    """⚠️ باج حقيقي كان هنا: مفيش أي تحقق من تكرار رقم الهاتف/الإيميل عند
    إنشاء عميل CRM — الاستقبال يقدر يسجّل نفس العميل مرتين بالغلط فيتقسم
    total_spent/visits_count على سجلين بدل ما يتراكموا صح."""

    def test_rejects_duplicate_phone_same_branch(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        first = client.post(
            "/api/v1/crm/customers",
            json={"branch_id": branch.id, "full_name": "عميل أول", "phone": "01055554444"},
            headers=manager_headers,
        )
        assert first.status_code == 201

        second = client.post(
            "/api/v1/crm/customers",
            json={"branch_id": branch.id, "full_name": "عميل مكرر", "phone": "01055554444"},
            headers=manager_headers,
        )
        assert second.status_code == 400
        assert "عميل أول" in second.json()["detail"]

    def test_rejects_duplicate_email_same_branch(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        first = client.post(
            "/api/v1/crm/customers",
            json={"branch_id": branch.id, "full_name": "عميل بريد", "email": "dup@example.com"},
            headers=manager_headers,
        )
        assert first.status_code == 201

        second = client.post(
            "/api/v1/crm/customers",
            json={"branch_id": branch.id, "full_name": "عميل بريد مكرر", "email": "dup@example.com"},
            headers=manager_headers,
        )
        assert second.status_code == 400

    def test_allows_customers_without_phone_or_email(self, client: TestClient, db, fake_redis, manager_headers):
        """عميلين من غير هاتف/إيميل (walk-in) — الاتنين لازم يتسمحوا (مفيش
        تعارض لأن مفيش قيمة أصلًا للمقارنة عليها)."""
        branch = make_branch_committed(db)
        first = client.post(
            "/api/v1/crm/customers",
            json={"branch_id": branch.id, "full_name": "زائر ١"},
            headers=manager_headers,
        )
        second = client.post(
            "/api/v1/crm/customers",
            json={"branch_id": branch.id, "full_name": "زائر ٢"},
            headers=manager_headers,
        )
        assert first.status_code == 201
        assert second.status_code == 201


class TestLeadConvertHttp:
    """wagdy.md C-03 — POST /crm/leads/{id}/convert عبر التوجيه الحقيقي
    (permission dependency + الاستدعاء المتقاطع لـ pms.services.create_booking)."""

    def test_convert_lead_success(self, client: TestClient, db, fake_redis, cashier_headers):
        branch = make_branch_committed(db)
        room_type = make_room_type(db, branch)
        room = make_room(db, branch, room_type)

        lead_resp = client.post(
            "/api/v1/crm/leads",
            json={"branch_id": branch.id, "full_name": "غادة سمير",
                  "phone": "01066677788", "interest": "booking"},
            headers=cashier_headers,
        )
        assert lead_resp.status_code == 201, lead_resp.text
        lead_id = lead_resp.json()["id"]

        check_in = (date.today() + timedelta(days=3)).isoformat()
        check_out = (date.today() + timedelta(days=5)).isoformat()
        convert_resp = client.post(
            f"/api/v1/crm/leads/{lead_id}/convert",
            json={"check_in": check_in, "check_out": check_out, "room_ids": [room.id]},
            headers=cashier_headers,
        )
        assert convert_resp.status_code == 201, convert_resp.text
        body = convert_resp.json()
        assert body["lead"]["stage"] == "won"
        assert body["lead"]["booking_id"] == body["booking_id"]
        assert body["booking_number"]

        # الـ lead بقى نهائي — أي محاولة تعديل تانية لازم تترفض
        stage_resp = client.patch(
            f"/api/v1/crm/leads/{lead_id}", json={"stage": "contacted"}, headers=cashier_headers,
        )
        assert stage_resp.status_code == 400

    def test_convert_lead_requires_cashier_or_above(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db)
        room_type = make_room_type(db, branch)
        room = make_room(db, branch, room_type)

        lead = _create_lead_direct(db, branch)

        resp = client.post(
            f"/api/v1/crm/leads/{lead.id}/convert",
            json={
                "check_in": (date.today() + timedelta(days=1)).isoformat(),
                "check_out": (date.today() + timedelta(days=2)).isoformat(),
                "room_ids": [room.id],
            },
            headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_convert_lead_room_conflict_returns_409(self, client: TestClient, db, fake_redis, cashier_headers):
        branch = make_branch_committed(db)
        room_type = make_room_type(db, branch)
        room = make_room(db, branch, room_type)
        check_in = (date.today() + timedelta(days=10)).isoformat()
        check_out = (date.today() + timedelta(days=12)).isoformat()

        # حجز أول يمسك الغرفة في نفس المدى
        first_lead = _create_lead_direct(db, branch)
        first_resp = client.post(
            f"/api/v1/crm/leads/{first_lead.id}/convert",
            json={"check_in": check_in, "check_out": check_out, "room_ids": [room.id]},
            headers=cashier_headers,
        )
        assert first_resp.status_code == 201, first_resp.text

        second_lead = _create_lead_direct(db, branch)
        conflict_resp = client.post(
            f"/api/v1/crm/leads/{second_lead.id}/convert",
            json={"check_in": check_in, "check_out": check_out, "room_ids": [room.id]},
            headers=cashier_headers,
        )
        assert conflict_resp.status_code == 409


def _create_lead_direct(db, branch):
    from app.modules.crm.crud import create_lead
    return create_lead(db, {
        "branch_id": branch.id, "full_name": "عميل اختبار",
        "phone": "01000000000", "interest": "booking", "stage": "new",
    })


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
