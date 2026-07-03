"""
tests/test_api/test_crm_endpoints_http.py
HTTP-level tests for CRM router endpoints not already covered by
test_crm_http.py (leads flow) or test_crm.py/test_crm_leads.py (service
layer): customers CRUD, interactions listing, opportunities listing,
activities listing — all at the real HTTP layer (status codes, pagination,
role gates, 404s).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="CRM Endpoints Branch", name_ar="فرع عملاء",
               code=f"CRME-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def create_customer(client: TestClient, branch_id: int, headers: dict, **overrides) -> dict:
    payload = {"branch_id": branch_id, "full_name": "عميل اختبار", "segment": "regular", "source": "walk_in"}
    payload.update(overrides)
    resp = client.post("/api/v1/crm/customers", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestCustomersEndpoints:
    def test_create_list_get_and_update(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        customer = create_customer(client, branch.id, waiter_headers, full_name="نورا حسن")

        list_resp = client.get("/api/v1/crm/customers", params={"branch_id": branch.id}, headers=waiter_headers)
        assert list_resp.status_code == 200
        assert any(c["id"] == customer["id"] for c in list_resp.json()["items"])

        get_resp = client.get(f"/api/v1/crm/customers/{customer['id']}", headers=waiter_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["full_name"] == "نورا حسن"

        update_resp = client.patch(
            f"/api/v1/crm/customers/{customer['id']}", json={"segment": "vip"}, headers=waiter_headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["segment"] == "vip"

    def test_get_missing_customer_404(self, client: TestClient, waiter_headers):
        resp = client.get("/api/v1/crm/customers/999999999", headers=waiter_headers)
        assert resp.status_code == 404

    def test_search_filters_by_name(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        create_customer(client, branch.id, waiter_headers, full_name="أحمد الششتاوي")
        create_customer(client, branch.id, waiter_headers, full_name="مريم عادل")

        resp = client.get(
            "/api/v1/crm/customers", params={"branch_id": branch.id, "search": "ششتاوي"}, headers=waiter_headers,
        )
        names = [c["full_name"] for c in resp.json()["items"]]
        assert "أحمد الششتاوي" in names
        assert "مريم عادل" not in names

    def test_blacklist_requires_manager_not_just_active_user(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        customer = create_customer(client, branch.id, waiter_headers)
        resp = client.post(
            f"/api/v1/crm/customers/{customer['id']}/blacklist",
            json={"reason": "شيك مرتد"}, headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_blacklist_and_unblacklist_round_trip(self, client: TestClient, db, waiter_headers, manager_headers):
        branch = make_branch_committed(db)
        customer = create_customer(client, branch.id, waiter_headers)

        bl_resp = client.post(
            f"/api/v1/crm/customers/{customer['id']}/blacklist",
            json={"reason": "سلوك غير لائق"}, headers=manager_headers,
        )
        assert bl_resp.status_code == 200
        assert bl_resp.json()["blacklisted"] is True

        unbl_resp = client.delete(f"/api/v1/crm/customers/{customer['id']}/blacklist", headers=manager_headers)
        assert unbl_resp.status_code == 200
        assert unbl_resp.json()["blacklisted"] is False


class TestInteractionsEndpoints:
    def test_log_and_list_interactions(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        customer = create_customer(client, branch.id, waiter_headers)

        log_resp = client.post(
            "/api/v1/crm/interactions",
            json={
                "customer_id": customer["id"], "branch_id": branch.id,
                "interaction_type": "call", "direction": "outbound",
                "summary": "تأكيد الحجز", "occurred_at": datetime.utcnow().isoformat(),
            },
            headers=waiter_headers,
        )
        assert log_resp.status_code == 201, log_resp.text

        list_resp = client.get(f"/api/v1/crm/customers/{customer['id']}/interactions", headers=waiter_headers)
        assert list_resp.status_code == 200
        assert list_resp.json()["total"] == 1

    def test_log_interaction_for_missing_customer_returns_400(self, client: TestClient, waiter_headers):
        resp = client.post(
            "/api/v1/crm/interactions",
            json={
                "customer_id": 999999999, "branch_id": 1,
                "interaction_type": "call", "summary": "test",
                "occurred_at": datetime.utcnow().isoformat(),
            },
            headers=waiter_headers,
        )
        assert resp.status_code == 400


class TestOpportunitiesEndpoints:
    def test_create_and_list(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        customer = create_customer(client, branch.id, waiter_headers)

        create_resp = client.post(
            "/api/v1/crm/opportunities",
            json={
                "branch_id": branch.id, "customer_id": customer["id"], "title": "بيع وحدة تايم شير",
                "product_type": "timeshare", "expected_value": "50000.00",
            },
            headers=waiter_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        opp = create_resp.json()

        list_resp = client.get("/api/v1/crm/opportunities", params={"branch_id": branch.id}, headers=waiter_headers)
        assert any(o["id"] == opp["id"] for o in list_resp.json()["items"])

    def test_filter_by_stage(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        customer = create_customer(client, branch.id, waiter_headers)
        client.post(
            "/api/v1/crm/opportunities",
            json={
                "branch_id": branch.id, "customer_id": customer["id"], "title": "فرصة 1",
                "product_type": "leasing", "expected_value": "1000",
            },
            headers=waiter_headers,
        )
        resp = client.get(
            "/api/v1/crm/opportunities", params={"branch_id": branch.id, "stage": "won"}, headers=waiter_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0  # لسه في lead، مش won


class TestActivitiesEndpoints:
    def test_create_and_list(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        customer = create_customer(client, branch.id, waiter_headers)

        create_resp = client.post(
            "/api/v1/crm/activities",
            json={
                "branch_id": branch.id, "customer_id": customer["id"], "activity_type": "follow_up",
                "title": "متابعة بعد أسبوع", "due_date": str(date.today() + timedelta(days=7)),
            },
            headers=waiter_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        activity = create_resp.json()

        list_resp = client.get(
            "/api/v1/crm/activities", params={"branch_id": branch.id, "customer_id": customer["id"]},
            headers=waiter_headers,
        )
        assert any(a["id"] == activity["id"] for a in list_resp.json()["items"])

    def test_filter_by_due_before(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        customer = create_customer(client, branch.id, waiter_headers)
        client.post(
            "/api/v1/crm/activities",
            json={
                "branch_id": branch.id, "customer_id": customer["id"], "activity_type": "meeting",
                "title": "اجتماع بعيد", "due_date": str(date.today() + timedelta(days=60)),
            },
            headers=waiter_headers,
        )
        resp = client.get(
            "/api/v1/crm/activities",
            params={"branch_id": branch.id, "due_before": str(date.today() + timedelta(days=10))},
            headers=waiter_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
