"""
tests/test_api/test_timeshare_http.py
HTTP-level tests for the timeshare module — TestClient through real routing,
permission dependencies and Pydantic validation (not direct service calls).

⚠️ Setup data created here must be `db.commit()`-ed, not `.flush()`-ed.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="Timeshare HTTP Branch", name_ar="فرع تايم شير",
               code=f"TS-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def contract_payload(branch_id: int) -> dict:
    return {
        "branch_id": branch_id,
        "customer_name": "منى عبد الله",
        "room_type": "2R",
        "nights_per_year": 7,
        "season": "high",
        "total_value": "100000.00",
        "down_payment": "20000.00",
        "installments": 4,
        "installment_period": 1,
        "first_installment_date": str(date.today() + timedelta(days=30)),
        "start_date": str(date.today()),
    }


class TestTimeshareContractFlow:
    def test_create_contract_generates_installment_schedule(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)

        resp = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        )
        assert resp.status_code == 201, resp.text
        contract = resp.json()
        assert contract["status"] == "active" or contract["status"] == "draft"
        assert contract["contract_number"]

        get_resp = client.get(f"/api/v1/timeshare/contracts/{contract['id']}", headers=manager_headers)
        assert get_resp.status_code == 200
        assert len(get_resp.json()["installments_list"]) == 4

    def test_pay_installment_updates_status(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()
        inst_id = contract["installments_list"][0]["id"]
        inst_amount = contract["installments_list"][0]["amount"]

        pay_resp = client.post(
            f"/api/v1/timeshare/installments/{inst_id}/pay",
            json={"paid_amount": inst_amount, "payment_method": "cash"},
            headers=manager_headers,
        )
        assert pay_resp.status_code == 200, pay_resp.text
        assert pay_resp.json()["status"] == "paid"
        assert Decimal(str(pay_resp.json()["paid_amount"])) == Decimal(str(inst_amount))

    def test_cancel_contract_via_http(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()

        cancel_resp = client.post(
            f"/api/v1/timeshare/contracts/{contract['id']}/cancel",
            json={"cancel_amount": "5000.00"},
            headers=manager_headers,
        )
        assert cancel_resp.status_code == 200, cancel_resp.text
        assert cancel_resp.json()["status"] == "cancelled"


class TestTimesharePermissions:
    def test_create_contract_requires_manager(self, client: TestClient, db, fake_redis, cashier_headers):
        """cashier (40) must not be able to create timeshare contracts (manager=60 required)."""
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=cashier_headers,
        )
        assert resp.status_code == 403

    def test_cancel_contract_requires_manager(self, client: TestClient, db, fake_redis, manager_headers, cashier_headers):
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()

        resp = client.post(
            f"/api/v1/timeshare/contracts/{contract['id']}/cancel",
            json={"cancel_amount": "0"},
            headers=cashier_headers,
        )
        assert resp.status_code == 403


class TestTimeshareValidation:
    def test_create_contract_rejects_invalid_room_type(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        payload = contract_payload(branch.id)
        payload["room_type"] = "10R"
        resp = client.post("/api/v1/timeshare/contracts", json=payload, headers=manager_headers)
        assert resp.status_code == 422

    def test_create_contract_rejects_down_payment_exceeding_total(self, client: TestClient, db, fake_redis, manager_headers):
        """down_payment > total_value is a business rule (ValueError -> 400), not a schema constraint."""
        branch = make_branch_committed(db)
        payload = contract_payload(branch.id)
        payload["down_payment"] = "200000.00"
        resp = client.post("/api/v1/timeshare/contracts", json=payload, headers=manager_headers)
        assert resp.status_code == 400

    def test_pay_installment_rejects_invalid_method(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()
        inst_id = contract["installments_list"][0]["id"]

        resp = client.post(
            f"/api/v1/timeshare/installments/{inst_id}/pay",
            json={"paid_amount": "1000.00", "payment_method": "crypto"},
            headers=manager_headers,
        )
        assert resp.status_code == 422
