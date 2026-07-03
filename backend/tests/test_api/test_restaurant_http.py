"""
tests/test_api/test_restaurant_http.py
First real HTTP-level test — exercises the FastAPI app + TestClient, not just
service functions directly. Catches routing/wiring bugs (like the
GET /restaurant/menu vs /restaurant/menu/items mismatch found 2026-07-01)
that direct service-layer tests can never catch.

⚠️ Data created here must be committed (not just flushed) — HTTP requests go
through a *different* DB session (app.dependency_overrides[get_db]) than the
`db` fixture injected directly into a test function. See conftest.py's
_create_test_user / super_admin_headers docstring for the same gotcha.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="HTTP Test Branch", name_ar="فرع اختبار HTTP",
               code=f"HTP-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_menu_item_committed(db, branch):
    from app.modules.restaurant.models import MenuItem
    item = MenuItem(branch_id=branch.id, name="برجر اختبار", price=Decimal("80.00"), is_available=True)
    db.add(item)
    db.commit()
    return item


def make_table_committed(db, branch):
    from app.modules.restaurant.models import DiningTable
    table = DiningTable(branch_id=branch.id, table_number="T1", capacity=4, status="available")
    db.add(table)
    db.commit()
    return table


class TestRestaurantMenuHTTP:
    def test_get_menu_items_requires_auth(self, client: TestClient, db):
        branch = make_branch_committed(db)
        resp = client.get("/api/v1/restaurant/menu/items", params={"branch_id": branch.id})
        assert resp.status_code == 401

    def test_get_menu_items_returns_created_item(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)

        resp = client.get(
            "/api/v1/restaurant/menu/items",
            params={"branch_id": branch.id},
            headers=waiter_headers,
        )
        assert resp.status_code == 200
        names = [i["name"] for i in resp.json()]
        assert item.name in names


class TestRestaurantCategoriesHTTP:
    def test_get_categories_returns_created_category(self, client: TestClient, db, manager_headers, waiter_headers):
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/restaurant/menu/categories",
            json={"branch_id": branch.id, "name": "Burgers", "name_ar": "برجر"},
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text

        list_resp = client.get(
            "/api/v1/restaurant/menu/categories",
            params={"branch_id": branch.id},
            headers=waiter_headers,
        )
        assert list_resp.status_code == 200
        names = [c["name"] for c in list_resp.json()]
        assert "Burgers" in names


class TestRestaurantOrderHTTP:
    def test_create_order_via_http(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)

        resp = client.post(
            "/api/v1/restaurant/orders",
            params={"branch_id": branch.id},
            json={
                "order_type": "takeaway",
                "guests_count": 1,
                "items": [{"menu_item_id": item.id, "quantity": 2}],
            },
            headers=waiter_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "open"
        assert len(body["items"]) == 1
        assert body["items"][0]["quantity"] == 2
        assert Decimal(str(body["subtotal"])) == Decimal("160.00")

    def test_in_kitchen_transition_broadcasts_to_kds_websocket(self, client: TestClient, db, waiter_headers):
        """قبل كده: KDS كانت شاشات polling بس كل 15 ثانية — الـ WebSocket
        endpoint كان موجود بس محدّش بيبعت عليه رسالة أبداً حتى لو اتعمل
        تذكرة جديدة فعليًا. دلوقتي أي تذكرة جديدة/تحديث حالة بيبعت broadcast
        لأي شاشة KDS متصلة على نفس الفرع لحظيًا."""
        from unittest.mock import AsyncMock, patch
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)

        order_resp = client.post(
            "/api/v1/restaurant/orders", params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1,
                  "items": [{"menu_item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )
        order_id = order_resp.json()["id"]

        with patch(
            "app.modules.restaurant.api.router.restaurant_manager.broadcast",
            new_callable=AsyncMock,
        ) as mock_broadcast:
            resp = client.patch(
                f"/api/v1/restaurant/orders/{order_id}/status",
                json={"status": "in_kitchen"},
                headers=waiter_headers,
            )
        assert resp.status_code == 200, resp.text
        mock_broadcast.assert_called_once()
        branch_arg, payload_arg = mock_broadcast.call_args[0]
        assert branch_arg == str(branch.id)
        assert payload_arg["type"] == "tickets_updated"

    def test_create_order_rejects_unavailable_item(self, client: TestClient, db, waiter_headers):
        from app.modules.restaurant.models import MenuItem
        branch = make_branch_committed(db)
        item = MenuItem(branch_id=branch.id, name="غير متاح", price=Decimal("50.00"), is_available=False)
        db.add(item)
        db.commit()

        resp = client.post(
            "/api/v1/restaurant/orders",
            params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1, "items": [{"menu_item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )
        assert resp.status_code == 400

    def test_create_order_with_extras_adds_price_addition(self, client: TestClient, db, manager_headers, waiter_headers):
        from app.modules.restaurant.models import MenuItem

        branch = make_branch_committed(db)
        item = MenuItem(branch_id=branch.id, name="برجر بإضافات", price=Decimal("100.00"), is_available=True)
        db.add(item)
        db.commit()

        group_resp = client.post(
            f"/api/v1/restaurant/menu/items/{item.id}/extra-groups",
            json={
                "name": "إضافات", "min_select": 0, "max_select": 2,
                "options": [
                    {"name": "جبنة", "price_addition": "10.00"},
                    {"name": "بصل", "price_addition": "5.00"},
                ],
            },
            headers=manager_headers,
        )
        assert group_resp.status_code == 201, group_resp.text
        option_ids = [o["id"] for o in group_resp.json()["options"]]

        resp = client.post(
            "/api/v1/restaurant/orders",
            params={"branch_id": branch.id},
            json={
                "order_type": "takeaway", "guests_count": 1,
                "items": [{"menu_item_id": item.id, "quantity": 1, "extra_ids": option_ids}],
            },
            headers=waiter_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert Decimal(str(body["subtotal"])) == Decimal("115.00")
        assert len(body["items"][0]["extras"]) == 2

    def test_create_order_rejects_extra_below_min_select(self, client: TestClient, db, manager_headers, waiter_headers):
        from app.modules.restaurant.models import MenuItem

        branch = make_branch_committed(db)
        item = MenuItem(branch_id=branch.id, name="بيتزا بحجم إجباري", price=Decimal("80.00"), is_available=True)
        db.add(item)
        db.commit()

        group_resp = client.post(
            f"/api/v1/restaurant/menu/items/{item.id}/extra-groups",
            json={"name": "حجم", "min_select": 1, "max_select": 1, "options": [{"name": "كبير", "price_addition": "20.00"}]},
            headers=manager_headers,
        )
        assert group_resp.status_code == 201, group_resp.text

        resp = client.post(
            "/api/v1/restaurant/orders",
            params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1, "items": [{"menu_item_id": item.id, "quantity": 1, "extra_ids": []}]},
            headers=waiter_headers,
        )
        assert resp.status_code == 400

    def test_create_order_rejects_extra_from_other_item(self, client: TestClient, db, manager_headers, waiter_headers):
        from app.modules.restaurant.models import MenuItem

        branch = make_branch_committed(db)
        item_a = MenuItem(branch_id=branch.id, name="صنف أ", price=Decimal("50.00"), is_available=True)
        item_b = MenuItem(branch_id=branch.id, name="صنف ب", price=Decimal("50.00"), is_available=True)
        db.add_all([item_a, item_b])
        db.commit()

        group_resp = client.post(
            f"/api/v1/restaurant/menu/items/{item_a.id}/extra-groups",
            json={"name": "إضافات أ", "min_select": 0, "max_select": 1, "options": [{"name": "إضافة أ", "price_addition": "5.00"}]},
            headers=manager_headers,
        )
        foreign_extra_id = group_resp.json()["options"][0]["id"]

        resp = client.post(
            "/api/v1/restaurant/orders",
            params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1, "items": [{"menu_item_id": item_b.id, "quantity": 1, "extra_ids": [foreign_extra_id]}]},
            headers=waiter_headers,
        )
        assert resp.status_code == 400

    def test_create_order_requires_waiter_level(self, client: TestClient, db):
        """customer/guest-level tokens shouldn't be able to create orders."""
        from tests.conftest import _create_test_user, _make_token  # noqa: PLC0415

        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)
        _create_test_user("customer-http@test.local", "customer")
        headers = {"Authorization": f"Bearer {_make_token('customer-http@test.local')}"}

        resp = client.post(
            "/api/v1/restaurant/orders",
            params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1, "items": [{"menu_item_id": item.id, "quantity": 1}]},
            headers=headers,
        )
        assert resp.status_code == 403


class TestHeldOrders:
    def test_hold_order_creates_with_held_status(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)

        resp = client.post(
            "/api/v1/restaurant/orders/hold",
            params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1, "items": [{"menu_item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["status"] == "held"

    def test_held_orders_list_only_shows_held(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)

        held_resp = client.post(
            "/api/v1/restaurant/orders/hold",
            params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1, "items": [{"menu_item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )
        client.post(
            "/api/v1/restaurant/orders",
            params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1, "items": [{"menu_item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )

        resp = client.get("/api/v1/restaurant/orders/held", params={"branch_id": branch.id}, headers=waiter_headers)
        assert resp.status_code == 200
        ids = [o["id"] for o in resp.json()]
        assert held_resp.json()["id"] in ids
        assert all(o["status"] == "held" for o in resp.json())

    def test_resume_held_order_to_open(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)
        held = client.post(
            "/api/v1/restaurant/orders/hold",
            params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1, "items": [{"menu_item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()

        resp = client.patch(
            f"/api/v1/restaurant/orders/{held['id']}/status",
            json={"status": "open"},
            headers=waiter_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "open"


class TestOrderPaymentPermission:
    """إتمام الدفع (status='paid') فعل مالي فعلي — يقفل الطاولة، ينشر charge
    على الفوليو، يرحّل قيد إيراد، يخصم مخزون — نفس مستوى void_order_item.
    قبل الفحص ده كان أي نادل (level 30) يقدر يقفل حساب لوحده."""

    def test_waiter_cannot_mark_order_paid(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)
        order = client.post(
            "/api/v1/restaurant/orders",
            params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1, "items": [{"menu_item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()

        resp = client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/status",
            json={"status": "paid"},
            headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_cashier_can_mark_order_paid(self, client: TestClient, db, waiter_headers, cashier_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)
        order = client.post(
            "/api/v1/restaurant/orders",
            params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1, "items": [{"menu_item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()

        resp = client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/status",
            json={"status": "paid"},
            headers=cashier_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "paid"

    def test_waiter_can_still_send_order_to_kitchen(self, client: TestClient, db, waiter_headers):
        """التحقق ده ماحطّش على أي حالة تانية غير 'paid' — النادل لسه يقدر
        يبعت للمطبخ ويقدّم عادي."""
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)
        order = client.post(
            "/api/v1/restaurant/orders",
            params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1, "items": [{"menu_item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()

        resp = client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/status",
            json={"status": "in_kitchen"},
            headers=waiter_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "in_kitchen"


class TestVoidOrderItem:
    def test_void_requires_cashier_level(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)
        order = client.post(
            "/api/v1/restaurant/orders",
            params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1, "items": [{"menu_item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()
        order_item_id = order["items"][0]["id"]

        resp = client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/items/{order_item_id}/void",
            json={"reason": "طلب خطأ"},
            headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_void_recomputes_order_total(self, client: TestClient, db, cashier_headers, waiter_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)
        order = client.post(
            "/api/v1/restaurant/orders",
            params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1, "items": [{"menu_item_id": item.id, "quantity": 2}]},
            headers=waiter_headers,
        ).json()
        order_item_id = order["items"][0]["id"]
        assert Decimal(str(order["subtotal"])) == Decimal("160.00")

        resp = client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/items/{order_item_id}/void",
            json={"reason": "العميل غيّر رأيه"},
            headers=cashier_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert Decimal(str(body["subtotal"])) == Decimal("0.00")
        assert body["items"][0]["status"] == "cancelled"
        assert body["items"][0]["voided_reason"] == "العميل غيّر رأيه"
        assert body["items"][0]["voided_by"] is not None

    def test_double_void_rejected(self, client: TestClient, db, cashier_headers, waiter_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)
        order = client.post(
            "/api/v1/restaurant/orders",
            params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1, "items": [{"menu_item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()
        order_item_id = order["items"][0]["id"]

        client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/items/{order_item_id}/void",
            json={"reason": "الأول"},
            headers=cashier_headers,
        )
        resp = client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/items/{order_item_id}/void",
            json={"reason": "التاني"},
            headers=cashier_headers,
        )
        assert resp.status_code == 400


class TestTableOccupancy:
    def test_dine_in_order_stamps_occupied_at(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)
        table = make_table_committed(db, branch)

        client.post(
            "/api/v1/restaurant/orders",
            params={"branch_id": branch.id},
            json={"table_id": table.id, "order_type": "dine_in", "guests_count": 2, "items": [{"menu_item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )

        resp = client.get("/api/v1/restaurant/tables", params={"branch_id": branch.id}, headers=waiter_headers)
        found = next(t for t in resp.json() if t["id"] == table.id)
        assert found["status"] == "occupied"
        assert found["occupied_at"] is not None

    def test_paid_order_clears_occupied_at(self, client: TestClient, db, waiter_headers, cashier_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)
        table = make_table_committed(db, branch)

        order = client.post(
            "/api/v1/restaurant/orders",
            params={"branch_id": branch.id},
            json={"table_id": table.id, "order_type": "dine_in", "guests_count": 2, "items": [{"menu_item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()

        # إتمام الدفع فعل مالي (كاشير أو أعلى بس — راجع update_order_status)
        client.patch(f"/api/v1/restaurant/orders/{order['id']}/status", json={"status": "paid"}, headers=cashier_headers)

        resp = client.get("/api/v1/restaurant/tables", params={"branch_id": branch.id}, headers=waiter_headers)
        found = next(t for t in resp.json() if t["id"] == table.id)
        assert found["status"] == "available"
        assert found["occupied_at"] is None
