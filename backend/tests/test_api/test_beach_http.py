"""
tests/test_api/test_beach_http.py
HTTP-level tests for the beach module — TestClient through real routing,
permission dependencies and Pydantic validation (not direct service calls).

⚠️ Setup data created here must be `db.commit()`-ed, not `.flush()`-ed — the
HTTP request goes through a different DB session (app.dependency_overrides
[get_db]) than the `db` fixture injected directly into the test function.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="Beach HTTP Branch", name_ar="فرع شاطئ",
               code=f"BCH-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


class TestBeachReservationFlow:
    def test_reservation_checkin_consumes_inventory(self, client: TestClient, db, fake_redis, cashier_headers):
        """Full round-trip: create reservation -> checkin -> capacity_used goes up."""
        branch = make_branch_committed(db)

        before = client.get(
            "/api/v1/beach/inventory", params={"branch_id": branch.id}, headers=cashier_headers,
        )
        assert before.status_code == 200, before.text
        cap_before = before.json()["capacity_used"]

        create_resp = client.post(
            "/api/v1/beach/reservations",
            json={
                "branch_id": branch.id,
                "guest_name": "أحمد محمود",
                "reservation_date": str(date.today()),
                "guests_count": 2,
                "with_towel": False,
            },
            headers=cashier_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        reservation = create_resp.json()
        assert reservation["status"] == "pending"
        assert Decimal(str(reservation["total_amount"])) > 0

        checkin_resp = client.post(
            f"/api/v1/beach/reservations/{reservation['id']}/checkin",
            headers=cashier_headers,
        )
        assert checkin_resp.status_code == 200, checkin_resp.text
        checked_in = checkin_resp.json()
        assert checked_in["status"] == "checked_in"
        assert checked_in["tx_id"] is not None

        after = client.get(
            "/api/v1/beach/inventory", params={"branch_id": branch.id}, headers=cashier_headers,
        )
        assert after.json()["capacity_used"] == cap_before + 2

    def test_double_checkin_rejected(self, client: TestClient, db, fake_redis, cashier_headers):
        branch = make_branch_committed(db)
        reservation = client.post(
            "/api/v1/beach/reservations",
            json={
                "branch_id": branch.id, "guest_name": "سارة علي",
                "reservation_date": str(date.today()), "guests_count": 1,
            },
            headers=cashier_headers,
        ).json()

        client.post(f"/api/v1/beach/reservations/{reservation['id']}/checkin", headers=cashier_headers)
        second = client.post(f"/api/v1/beach/reservations/{reservation['id']}/checkin", headers=cashier_headers)
        assert second.status_code == 400

    def test_reservation_public_view_no_auth(self, client: TestClient, db, fake_redis):
        """QR page reads reservation info without login."""
        branch = make_branch_committed(db)
        from app.modules.beach.models import BeachReservation
        res = BeachReservation(
            branch_id=branch.id, guest_name="ضيف QR", reservation_date=date.today(),
            guests_count=1, with_towel=False, status="pending", total_amount=Decimal("200.00"),
        )
        db.add(res)
        db.commit()

        resp = client.get(f"/api/v1/beach/reservations/{res.id}/public")
        assert resp.status_code == 200
        assert resp.json()["guest_name"] == "ضيف QR"


class TestBeachSellPermissions:
    def test_sell_requires_cashier_level(self, client: TestClient, db, fake_redis):
        """A waiter-level token must not be able to sell beach tickets (cashier+ required)."""
        from tests.conftest import _create_test_user, _make_token
        branch = make_branch_committed(db)
        _create_test_user("beach-waiter@test.local", "waiter")
        headers = {"Authorization": f"Bearer {_make_token('beach-waiter@test.local')}"}

        resp = client.post(
            "/api/v1/beach/sell",
            params={"branch_id": branch.id},
            json={"tx_type": "entry", "quantity": 1},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_surge_set_requires_manager(self, client: TestClient, db, fake_redis, cashier_headers):
        """Cashier-level token must not be allowed to set surge pricing (manager+ only)."""
        branch = make_branch_committed(db)
        resp = client.patch(
            "/api/v1/beach/surge",
            params={"branch_id": branch.id},
            json={"surge_pct": "50"},
            headers=cashier_headers,
        )
        assert resp.status_code == 403

    def test_surge_set_by_manager_reflected_in_price(self, client: TestClient, db, fake_redis, manager_headers, cashier_headers):
        branch = make_branch_committed(db)
        surge_resp = client.patch(
            "/api/v1/beach/surge",
            params={"branch_id": branch.id},
            json={"surge_pct": "50"},
            headers=manager_headers,
        )
        assert surge_resp.status_code == 200, surge_resp.text
        assert Decimal(str(surge_resp.json()["surge_pct"])) == Decimal("50")

        sell_resp = client.post(
            "/api/v1/beach/sell",
            params={"branch_id": branch.id},
            json={"tx_type": "entry", "quantity": 1},
            headers=cashier_headers,
        )
        assert sell_resp.status_code == 201, sell_resp.text
        assert sell_resp.json()["surge_applied"] is True


class TestBeachValidation:
    def test_sell_rejects_invalid_tx_type(self, client: TestClient, db, fake_redis, cashier_headers):
        """tx_type outside the allowed pattern must 422, not 500 or a silent pass."""
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/beach/sell",
            params={"branch_id": branch.id},
            json={"tx_type": "free_beer", "quantity": 1},
            headers=cashier_headers,
        )
        assert resp.status_code == 422

    def test_sell_rejects_zero_quantity(self, client: TestClient, db, fake_redis, cashier_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/beach/sell",
            params={"branch_id": branch.id},
            json={"tx_type": "entry", "quantity": 0},
            headers=cashier_headers,
        )
        assert resp.status_code == 422

    def test_sell_exceeding_capacity_rejected(self, client: TestClient, db, fake_redis, cashier_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/beach/sell",
            params={"branch_id": branch.id},
            json={"tx_type": "entry", "quantity": 999999},
            headers=cashier_headers,
        )
        assert resp.status_code == 400


class TestBeachB2BContracts:
    def test_b2b_checkin_and_quota_status_via_http(self, client: TestClient, db, fake_redis, super_admin_headers, cashier_headers):
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/beach/b2b-contracts",
            json={
                "branch_id": branch.id,
                "hotel_name": "Grand Resort Hotel",
                "daily_quota": 10,
                "entry_price": "150.00",
                "valid_from": str(date.today()),
                "valid_until": str(date.today() + timedelta(days=30)),
            },
            headers=super_admin_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        contract = create_resp.json()

        checkin_resp = client.post(
            "/api/v1/beach/b2b-checkin",
            params={"branch_id": branch.id},
            json={"contract_id": contract["id"], "guests_count": 3, "with_towel": False},
            headers=cashier_headers,
        )
        assert checkin_resp.status_code == 201, checkin_resp.text

        status_resp = client.get(
            "/api/v1/beach/b2b-contracts/status",
            params={"branch_id": branch.id},
            headers=cashier_headers,
        )
        assert status_resp.status_code == 200
        entry = next(s for s in status_resp.json() if s["contract_id"] == contract["id"])
        assert entry["checked_in_today"] == 3
        assert entry["remaining_quota"] == 7

    def test_b2b_contract_create_requires_admin(self, client: TestClient, db, fake_redis, manager_headers):
        """manager-level (60) must not be allowed to create a B2B contract (admin=80 required)."""
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/beach/b2b-contracts",
            json={
                "branch_id": branch.id,
                "hotel_name": "Some Hotel",
                "daily_quota": 10,
                "entry_price": "150.00",
                "valid_from": str(date.today()),
                "valid_until": str(date.today() + timedelta(days=30)),
            },
            headers=manager_headers,
        )
        assert resp.status_code == 403
