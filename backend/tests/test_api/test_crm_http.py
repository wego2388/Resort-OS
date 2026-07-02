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

⚠️ crm defaults to MODULE_REGISTRY.crm.default_enabled=False — must be
enabled globally (branch_id=None). See tests/conftest.py::enable_module_for_branch.
⚠️ Setup data created here must be `db.commit()`-ed, not `.flush()`-ed.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import enable_module_for_branch


def make_branch_committed(db, fake_redis):
    from app.modules.core.models import Branch
    b = Branch(name="CRM HTTP Branch", name_ar="فرع عملاء",
               code=f"CRM-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    enable_module_for_branch(db, fake_redis, "crm", branch_id=None)
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
        branch = make_branch_committed(db, fake_redis)

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
        branch = make_branch_committed(db, fake_redis)
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
        branch = make_branch_committed(db, fake_redis)
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


class TestCRMPermissions:
    def test_blacklist_customer_requires_manager(self, client: TestClient, db, fake_redis):
        """Any authenticated user (waiter) must not be able to blacklist a
        customer — manager+ required, unlike most other CRM endpoints."""
        from tests.conftest import _create_test_user, _make_token
        branch = make_branch_committed(db, fake_redis)
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
        branch = make_branch_committed(db, fake_redis)
        resp = client.post(
            "/api/v1/crm/leads",
            json={"branch_id": branch.id, "full_name": "عميل", "interest": "spaceship"},
            headers=manager_headers,
        )
        assert resp.status_code == 422

    def test_update_lead_rejects_invalid_stage(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db, fake_redis)
        lead = client.post(
            "/api/v1/crm/leads", json={"branch_id": branch.id, "full_name": "عميل آخر"},
            headers=manager_headers,
        ).json()

        resp = client.patch(
            f"/api/v1/crm/leads/{lead['id']}", json={"stage": "negotiation"}, headers=manager_headers,
        )
        assert resp.status_code == 422
