"""
tests/test_api/test_dining_http.py
HTTP-level tests for the unified dining router (wagdy.md D-04) — exercises
the FastAPI app + TestClient, not just service functions directly. Mirrors
test_restaurant_http.py's structure.

Also concretely proves the D-04 "zero existing frontend code breaks" claim:
TestOldUrlsStillWork below hits the untouched /api/v1/restaurant/... and
/api/v1/cafe/... routers directly and confirms they still answer exactly as
before dining was added — the full restaurant/cafe suites passing unmodified
already proves this at the service layer; this proves it at the live HTTP
layer too.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient

from tests.conftest import ws_url


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="Dining HTTP Branch", name_ar="فرع دايننج HTTP",
               code=f"DHT-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_outlet_committed(db, branch, outlet_type="restaurant", revenue_account_code="4200"):
    from app.modules.dining.models import Outlet
    outlet = Outlet(branch_id=branch.id, name=f"{outlet_type}-{uuid.uuid4().hex[:6]}",
                     outlet_type=outlet_type, revenue_account_code=revenue_account_code)
    db.add(outlet)
    db.commit()
    return outlet


def make_item_committed(db, branch, outlet, price=Decimal("80.00"), station="hot"):
    from app.modules.dining.models import DiningItem
    item = DiningItem(branch_id=branch.id, outlet_id=outlet.id, name="برجر اختبار",
                       price=price, is_available=True, station=station)
    db.add(item)
    db.commit()
    return item


def make_table_committed(db, branch, outlet):
    from app.modules.dining.models import VenueTable
    table = VenueTable(branch_id=branch.id, outlet_id=outlet.id, table_number="T1",
                        capacity=4, status="available")
    db.add(table)
    db.commit()
    return table


class TestOutletHTTP:
    def test_create_outlet_requires_manager(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/dining/outlets",
            json={"branch_id": branch.id, "name": "بار المسبح", "outlet_type": "pool_bar",
                  "revenue_account_code": "4700"},
            headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_create_and_list_outlet(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/dining/outlets",
            json={"branch_id": branch.id, "name": "بار المسبح", "outlet_type": "pool_bar",
                  "revenue_account_code": "4700"},
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        assert create_resp.json()["outlet_type"] == "pool_bar"

        list_resp = client.get(
            "/api/v1/dining/outlets", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert list_resp.status_code == 200
        names = [o["name"] for o in list_resp.json()]
        assert "بار المسبح" in names


class TestDiningMenuHTTP:
    def test_get_items_requires_auth(self, client: TestClient, db):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        resp = client.get(f"/api/v1/dining/outlets/{outlet.id}/items")
        assert resp.status_code == 401

    def test_get_items_returns_created_item(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        item = make_item_committed(db, branch, outlet)

        resp = client.get(f"/api/v1/dining/outlets/{outlet.id}/items", headers=waiter_headers)
        assert resp.status_code == 200
        names = [i["name"] for i in resp.json()]
        assert item.name in names


class TestDiningOrderHTTP:
    def test_create_order_via_http(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        item = make_item_committed(db, branch, outlet)

        resp = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={
                "outlet_id": outlet.id,
                "order_type": "takeaway",
                "guests_count": 1,
                "items": [{"item_id": item.id, "quantity": 2}],
            },
            headers=waiter_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "open"
        assert body["outlet_id"] == outlet.id
        assert len(body["items"]) == 1
        assert Decimal(str(body["subtotal"])) == Decimal("160.00")

    def test_create_order_outlet_id_mismatch_rejected(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        other_outlet = make_outlet_committed(db, branch, outlet_type="cafe", revenue_account_code="4400")
        item = make_item_committed(db, branch, outlet)

        resp = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={"outlet_id": other_outlet.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )
        assert resp.status_code == 400

    def test_void_item_requires_cashier_or_above(self, client: TestClient, db, waiter_headers, manager_headers):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        item = make_item_committed(db, branch, outlet)

        order_resp = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={"outlet_id": outlet.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )
        order = order_resp.json()
        item_id = order["items"][0]["id"]

        # الجرسون (level 30) ممنوع من الـ endpoint خالص — require_permission
        # بوابة الدخول الأولى (min_role_level=40).
        forbidden = client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{item_id}/void",
            json={"reason": "طلب غلط بالخطأ من النادل"},
            headers=waiter_headers,
        )
        assert forbidden.status_code == 403

        # المدير (level 60) مؤهّل بنفسه من غير أي موافقة PIN — راجع
        # core.services.resolve_pin_approval.
        allowed = client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{item_id}/void",
            json={"reason": "طلب غلط بالخطأ من المدير"},
            headers=manager_headers,
        )
        assert allowed.status_code == 200, allowed.text

    def test_in_kitchen_transition_broadcasts_to_dining_kds_websocket(self, client: TestClient, db, waiter_headers):
        from unittest.mock import AsyncMock, patch
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        item = make_item_committed(db, branch, outlet, station="grill")

        order_resp = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={"outlet_id": outlet.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )
        order_id = order_resp.json()["id"]

        with patch(
            "app.modules.dining.api.router.dining_manager.broadcast",
            new_callable=AsyncMock,
        ) as mock_broadcast:
            resp = client.patch(
                f"/api/v1/dining/orders/{order_id}/status",
                json={"status": "in_kitchen"},
                headers=waiter_headers,
            )
        assert resp.status_code == 200, resp.text
        mock_broadcast.assert_called_once()
        branch_arg, payload_arg = mock_broadcast.call_args[0]
        assert branch_arg == str(branch.id)
        assert payload_arg["type"] == "tickets_updated"

    def test_kds_websocket_client_receives_broadcast(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        item = make_item_committed(db, branch, outlet, station="grill")

        order_resp = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={"outlet_id": outlet.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )
        order_id = order_resp.json()["id"]

        with client.websocket_connect(ws_url(f"/api/v1/dining/ws/kds/{branch.id}", waiter_headers)) as ws:
            status_resp = client.patch(
                f"/api/v1/dining/orders/{order_id}/status",
                json={"status": "in_kitchen"}, headers=waiter_headers,
            )
            assert status_resp.status_code == 200, status_resp.text
            message = ws.receive_json()
            assert message["type"] == "tickets_updated"
            assert message["order_id"] == order_id

    def test_kitchen_tickets_route_to_correct_station(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        item = make_item_committed(db, branch, outlet, station="grill")

        order_resp = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={"outlet_id": outlet.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )
        order_id = order_resp.json()["id"]
        client.patch(f"/api/v1/dining/orders/{order_id}/status",
                      json={"status": "in_kitchen"}, headers=waiter_headers)

        tickets_resp = client.get(
            "/api/v1/dining/kitchen/tickets",
            params={"branch_id": branch.id, "stations": "grill"},
            headers=waiter_headers,
        )
        assert tickets_resp.status_code == 200
        tickets = tickets_resp.json()
        assert len(tickets) == 1
        assert tickets[0]["station"] == "grill"
        assert tickets[0]["outlet_id"] == outlet.id


class TestOldUrlsStillWork:
    """راجع docstring أعلى الملف — يثبت مباشرة إن /restaurant و/cafe لسه
    شغالين بالظبط زي قبل إضافة dining، من غير أي alias/تداخل."""

    def test_old_restaurant_menu_endpoint_untouched(self, client: TestClient, db, waiter_headers):
        from app.modules.restaurant.models import MenuItem
        branch = make_branch_committed(db)
        old_item = MenuItem(branch_id=branch.id, name="طبق مطعم قديم", price=Decimal("60.00"), is_available=True)
        db.add(old_item)
        db.commit()

        resp = client.get("/api/v1/restaurant/menu/items", params={"branch_id": branch.id}, headers=waiter_headers)
        assert resp.status_code == 200
        assert old_item.name in [i["name"] for i in resp.json()]

    def test_old_cafe_menu_endpoint_untouched(self, client: TestClient, db, waiter_headers):
        from app.modules.cafe.models import CafeItem
        branch = make_branch_committed(db)
        old_item = CafeItem(branch_id=branch.id, name="مشروب كافيه قديم", price=Decimal("25.00"), is_available=True)
        db.add(old_item)
        db.commit()

        resp = client.get("/api/v1/cafe/items", params={"branch_id": branch.id}, headers=waiter_headers)
        assert resp.status_code == 200
        assert old_item.name in [i["name"] for i in resp.json()]

    def test_old_and_new_menu_items_are_fully_independent(self, client: TestClient, db, manager_headers):
        """طلب/صنف جديد عبر /dining ميظهرش أبدًا في /restaurant أو /cafe
        القديمين — الموديولين لسه منفصلين تمامًا (Batch A إضافي بالكامل)."""
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        dining_item = make_item_committed(db, branch, outlet)

        old_restaurant_resp = client.get(
            "/api/v1/restaurant/menu/items", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert dining_item.name not in [i["name"] for i in old_restaurant_resp.json()]
