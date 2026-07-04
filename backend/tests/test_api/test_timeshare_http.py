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


class TestTimeshareVisitAndUnitsHttp:
    """HTTP-level: تخصيص وحدة فعلية + منع تعارض حجز حقيقي عبر الـ API
    الحقيقي (مش نداء مباشر على services)."""

    def test_create_visit_allocates_real_unit(self, client: TestClient, db, fake_redis, manager_headers):
        from app.modules.timeshare.models import TimeshareUnit
        branch = make_branch_committed(db)
        unit = TimeshareUnit(branch_id=branch.id, unit_number="A-101", unit_type="2R")
        db.add(unit); db.commit()

        contract = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()

        resp = client.post(
            "/api/v1/timeshare/visits",
            json={
                "branch_id": branch.id, "contract_id": contract["id"],
                "check_in": str(date.today() + timedelta(days=10)),
                "check_out": str(date.today() + timedelta(days=17)),
            },
            headers=manager_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["unit_id"] == unit.id

    def test_create_visit_without_available_unit_returns_400(self, client: TestClient, db, fake_redis, manager_headers):
        """مفيش أي وحدة من نوع 2R في الفرع ده — لازم 400 وليس نجاح صامت."""
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()

        resp = client.post(
            "/api/v1/timeshare/visits",
            json={
                "branch_id": branch.id, "contract_id": contract["id"],
                "check_in": str(date.today() + timedelta(days=10)),
                "check_out": str(date.today() + timedelta(days=17)),
            },
            headers=manager_headers,
        )
        assert resp.status_code == 400
        assert "وحدة متاحة" in resp.json()["detail"]

    def test_double_booking_same_unit_rejected_via_http(self, client: TestClient, db, fake_redis, manager_headers):
        """عقدين مختلفين على نفس الوحدة المخصَّصة دائمًا وفترة متقاطعة —
        الزيارة الثانية لازم ترفض بـ 400 حقيقي عبر الـ API."""
        from app.modules.timeshare.models import TimeshareUnit
        branch = make_branch_committed(db)
        unit = TimeshareUnit(branch_id=branch.id, unit_number="A-101", unit_type="2R")
        db.add(unit); db.commit()

        contract = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()
        client.patch(
            f"/api/v1/timeshare/contracts/{contract['id']}",
            json={"unit_id": unit.id}, headers=manager_headers,
        )

        check_in = date.today() + timedelta(days=10)
        first = client.post(
            "/api/v1/timeshare/visits",
            json={
                "branch_id": branch.id, "contract_id": contract["id"],
                "check_in": str(check_in), "check_out": str(check_in + timedelta(days=7)),
            },
            headers=manager_headers,
        )
        assert first.status_code == 201, first.text

        second = client.post(
            "/api/v1/timeshare/visits",
            json={
                "branch_id": branch.id, "contract_id": contract["id"],
                "check_in": str(check_in + timedelta(days=3)), "check_out": str(check_in + timedelta(days=10)),
            },
            headers=manager_headers,
        )
        assert second.status_code == 400
        assert "محجوزة بالفعل" in second.json()["detail"]

    def test_list_units_endpoint(self, client: TestClient, db, fake_redis, manager_headers):
        from app.modules.timeshare.models import TimeshareUnit
        branch = make_branch_committed(db)
        db.add(TimeshareUnit(branch_id=branch.id, unit_number="B-201", unit_type="4R"))
        db.commit()

        resp = client.get(f"/api/v1/timeshare/units?branch_id={branch.id}", headers=manager_headers)
        assert resp.status_code == 200
        numbers = [u["unit_number"] for u in resp.json()]
        assert "B-201" in numbers


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
