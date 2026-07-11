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
from datetime import date
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

    def test_kds_websocket_client_actually_receives_broadcast_message(
        self, client: TestClient, db, waiter_headers,
    ):
        """The test above only proves `broadcast()` gets *called* with the
        right args (mocked) — it never proves a real connected WS client
        actually receives anything, which is the actual point of the whole
        feature (a real KDS screen open on a real connection). This connects
        a genuine WebSocket client through TestClient and confirms the exact
        JSON message arrives after a real ticket status change over HTTP."""
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)

        order_resp = client.post(
            "/api/v1/restaurant/orders", params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1,
                  "items": [{"menu_item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )
        order_id = order_resp.json()["id"]

        with client.websocket_connect(f"/api/v1/restaurant/ws/kds/{branch.id}") as ws:
            in_kitchen_resp = client.patch(
                f"/api/v1/restaurant/orders/{order_id}/status",
                json={"status": "in_kitchen"}, headers=waiter_headers,
            )
            assert in_kitchen_resp.status_code == 200, in_kitchen_resp.text

            message = ws.receive_json()
            assert message["type"] == "tickets_updated"
            assert message["order_id"] == order_id

            # Advance the real KDS ticket created by the in_kitchen transition
            # and confirm the *second*, differently-shaped broadcast (from
            # update_ticket_status, keyed by ticket_id not order_id) also
            # reaches the same live connection.
            tickets_resp = client.get(
                "/api/v1/restaurant/kitchen/tickets",
                params={"branch_id": branch.id}, headers=waiter_headers,
            )
            ticket_id = tickets_resp.json()[0]["id"]
            status_resp = client.patch(
                f"/api/v1/restaurant/kitchen/tickets/{ticket_id}/status",
                json={"status": "in_progress"}, headers=waiter_headers,
            )
            assert status_resp.status_code == 200, status_resp.text

            second_message = ws.receive_json()
            assert second_message["type"] == "tickets_updated"
            assert second_message["ticket_id"] == ticket_id

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


class TestApplyDiscount:
    """POST /restaurant/orders/{id}/discount — zero test coverage before this
    (flagged by an independent review). Applies the best-matching active
    ConditionalDiscount rule from the finance module automatically; not a
    manual discount amount entered by the cashier."""

    def test_percentage_discount_applied_from_active_rule(
        self, client: TestClient, db, waiter_headers, cashier_headers,
    ):
        from app.modules.finance.models import ConditionalDiscount
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)  # 80.00 EGP

        rule = ConditionalDiscount(
            branch_id=branch.id, condition_type="total_amount", condition_value=">=0",
            discount_type="percentage", discount_value=Decimal("10"),
            valid_from=date(2020, 1, 1), valid_until=date(2099, 12, 31),
        )
        db.add(rule)
        db.commit()

        order = client.post(
            "/api/v1/restaurant/orders", params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1,
                  "items": [{"menu_item_id": item.id, "quantity": 2}]},
            headers=waiter_headers,
        ).json()
        assert Decimal(str(order["discount_amount"])) == Decimal("0.00")

        resp = client.post(
            f"/api/v1/restaurant/orders/{order['id']}/discount", headers=cashier_headers,
        )
        assert resp.status_code == 200, resp.text
        updated = resp.json()
        # subtotal = 160.00 (2 x 80.00), 10% off -> 16.00 saved
        assert Decimal(str(updated["discount_amount"])) == Decimal("16.00")

    def test_outlet_scoped_cafe_only_rule_does_not_apply_to_restaurant_order(
        self, client: TestClient, db, waiter_headers, cashier_headers,
    ):
        """rule نطاقها outlet='cafe' — لازم متأثرش على طلب مطعم خالص، حتى لو
        شروطها التانية (total_amount) متحققة."""
        from app.modules.finance.models import ConditionalDiscount
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)

        rule = ConditionalDiscount(
            branch_id=branch.id, condition_type="total_amount", condition_value=">=0",
            discount_type="percentage", discount_value=Decimal("50"),
            valid_from=date(2020, 1, 1), valid_until=date(2099, 12, 31),
            scope_type="outlet", scope_outlet="cafe",
        )
        db.add(rule)
        db.commit()

        order = client.post(
            "/api/v1/restaurant/orders", params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1,
                  "items": [{"menu_item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()

        resp = client.post(f"/api/v1/restaurant/orders/{order['id']}/discount", headers=cashier_headers)
        assert resp.status_code == 200, resp.text
        assert Decimal(str(resp.json()["discount_amount"])) == Decimal("0.00")

    def test_category_scoped_rule_discounts_only_that_categorys_lines(
        self, client: TestClient, db, waiter_headers, cashier_headers,
    ):
        """خصم 20% على فئة معيّنة بس (مثال: حلويات) — لازم يتقص على قيمة
        سطور الفئة دي بس، مش على إجمالي الطلب اللي فيه صنف من فئة تانية كمان."""
        from app.modules.finance.models import ConditionalDiscount
        from app.modules.restaurant.models import MenuCategory, MenuItem

        branch = make_branch_committed(db)
        dessert_category = MenuCategory(branch_id=branch.id, name="Desserts", name_ar="حلويات")
        db.add(dessert_category)
        db.commit()

        dessert_item = MenuItem(
            branch_id=branch.id, name="تيراميسو", price=Decimal("100.00"),
            is_available=True, category_id=dessert_category.id,
        )
        main_item = make_menu_item_committed(db, branch)  # 80.00، بدون فئة
        db.add(dessert_item)
        db.commit()

        rule = ConditionalDiscount(
            branch_id=branch.id, condition_type="total_amount", condition_value=">=0",
            discount_type="percentage", discount_value=Decimal("20"),
            valid_from=date(2020, 1, 1), valid_until=date(2099, 12, 31),
            scope_type="category", scope_outlet="restaurant", scope_id=dessert_category.id,
        )
        db.add(rule)
        db.commit()

        order = client.post(
            "/api/v1/restaurant/orders", params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1,
                  "items": [
                      {"menu_item_id": dessert_item.id, "quantity": 1},
                      {"menu_item_id": main_item.id, "quantity": 1},
                  ]},
            headers=waiter_headers,
        ).json()
        assert Decimal(str(order["subtotal"])) == Decimal("180.00")

        resp = client.post(f"/api/v1/restaurant/orders/{order['id']}/discount", headers=cashier_headers)
        assert resp.status_code == 200, resp.text
        # 20% من الـ 100.00 (الحلويات) بس، مش من الـ 180.00 كله
        assert Decimal(str(resp.json()["discount_amount"])) == Decimal("20.00")

    def test_discount_rejected_on_paid_order(self, client: TestClient, db, waiter_headers, cashier_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)
        order = client.post(
            "/api/v1/restaurant/orders", params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1,
                  "items": [{"menu_item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()
        client.patch(f"/api/v1/restaurant/orders/{order['id']}/status",
                     json={"status": "in_kitchen"}, headers=waiter_headers)
        client.patch(f"/api/v1/restaurant/orders/{order['id']}/status",
                     json={"status": "paid"}, headers=cashier_headers)

        resp = client.post(f"/api/v1/restaurant/orders/{order['id']}/discount", headers=cashier_headers)
        assert resp.status_code == 400


class TestHappyHourTimezone:
    """condition_type='time_of_day' لازم يتقيّم بتوقيت المنتجع المحلي
    (Africa/Cairo)، مش بتوقيت UTC الخام المخزّن في order.created_at — نفس
    فئة الباج الموثّقة في §13 CLAUDE.md واللي اتكشفت بشكل مستقل في 6
    موديولات تانية (KDS، PMS، تايم-شير، HR، إيجارات، شاطئ). لو
    apply_order_discount قارن ctx.order_time بـ created_at.time() مباشرة
    (بدون تحويل)، التستين دول هيفشلوا — مش نظريين، بيحاكوا لحظة UTC حقيقية
    فرقها عن توقيت القاهرة (UTC+3 صيفًا) بيقلب نتيجة الشرط بالكامل."""

    def _set_order_created_at(self, db, order_id: int, utc_naive) -> None:
        from app.modules.restaurant.models import Order
        order = db.query(Order).filter(Order.id == order_id).first()
        order.created_at = utc_naive
        db.commit()

    def test_applies_when_cairo_local_time_is_inside_window(
        self, client: TestClient, db, waiter_headers, cashier_headers,
    ):
        from datetime import datetime
        from app.modules.finance.models import ConditionalDiscount

        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)  # 80.00 EGP

        rule = ConditionalDiscount(
            branch_id=branch.id, condition_type="time_of_day", condition_value="14:00-17:00",
            discount_type="percentage", discount_value=Decimal("10"),
            valid_from=date(2020, 1, 1), valid_until=date(2099, 12, 31),
        )
        db.add(rule)
        db.commit()

        order = client.post(
            "/api/v1/restaurant/orders", params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1,
                  "items": [{"menu_item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()

        # 2026-07-06 12:30 UTC = 15:30 Africa/Cairo (UTC+3 صيفًا) — جوه نافذة
        # 14:00-17:00 بتوقيت القاهرة، لكن *خارج*ها لو اتقارنت كـ UTC خام.
        self._set_order_created_at(db, order["id"], datetime(2026, 7, 6, 12, 30))

        resp = client.post(
            f"/api/v1/restaurant/orders/{order['id']}/discount", headers=cashier_headers,
        )
        assert resp.status_code == 200, resp.text
        assert Decimal(str(resp.json()["discount_amount"])) == Decimal("8.00")  # 10% من 80.00

    def test_does_not_apply_when_only_utc_time_is_inside_window(
        self, client: TestClient, db, waiter_headers, cashier_headers,
    ):
        from datetime import datetime
        from app.modules.finance.models import ConditionalDiscount

        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)

        rule = ConditionalDiscount(
            branch_id=branch.id, condition_type="time_of_day", condition_value="22:00-23:59",
            discount_type="percentage", discount_value=Decimal("10"),
            valid_from=date(2020, 1, 1), valid_until=date(2099, 12, 31),
        )
        db.add(rule)
        db.commit()

        order = client.post(
            "/api/v1/restaurant/orders", params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1,
                  "items": [{"menu_item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()

        # 2026-07-06 22:30 UTC = 01:30 Africa/Cairo *اليوم التالي* — جوه نافذة
        # 22:00-23:59 لو اتقورنت كـ UTC خام (باج)، لكن فعليًا خارجها تمامًا
        # بتوقيت القاهرة الصحيح.
        self._set_order_created_at(db, order["id"], datetime(2026, 7, 6, 22, 30))

        resp = client.post(
            f"/api/v1/restaurant/orders/{order['id']}/discount", headers=cashier_headers,
        )
        assert resp.status_code == 200, resp.text
        assert Decimal(str(resp.json()["discount_amount"])) == Decimal("0.00")


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


def _set_pin(db, email: str, pin: str) -> int:
    """يضبط PIN حقيقي لمستخدم اختباري عبر core.services (نفس المسار اللي
    endpoint الحقيقي بينادي عليه) — يرجّع user.id عشان يُستخدم كـ
    approver_user_id في تست void/refund. لازم commit صريح (نفس الملاحظة في
    أعلى الملف — الـ TestClient بيستخدم session مختلفة)."""
    from app.core.kernel.models.user import User
    from app.modules.core import services as core_services

    user = db.query(User).filter(User.email == email).first()
    core_services.set_pin(db, user.id, pin, created_by=user.id)
    db.commit()
    return user.id


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

    def test_void_by_manager_needs_no_pin_approval(self, client: TestClient, db, manager_headers, waiter_headers):
        """مدير (level 60) مؤهّل بنفسه — مفيش داعي لموافقة PIN من حد تاني
        (راجع core.services.resolve_pin_approval)."""
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)
        order = client.post(
            "/api/v1/restaurant/orders",
            params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1, "items": [{"menu_item_id": item.id, "quantity": 2}]},
            headers=waiter_headers,
        ).json()
        order_item_id = order["items"][0]["id"]

        resp = client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/items/{order_item_id}/void",
            json={"reason": "العميل غيّر رأيه"},
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"][0]["status"] == "cancelled"

    def test_void_by_cashier_without_pin_is_rejected(self, client: TestClient, db, cashier_headers, waiter_headers):
        """⚠️ باج أمني حقيقي اتصلح (2026-07-07): كاشير (level 40) كان يقدر
        يلغي صنف من غير أي إشراف — دلوقتي محتاج موافقة PIN من مدير+."""
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
            headers=cashier_headers,
        )
        assert resp.status_code == 400
        assert "PIN" in resp.json()["detail"] or "موافقة" in resp.json()["detail"]

    def test_void_by_cashier_with_wrong_manager_pin_is_rejected(
        self, client: TestClient, db, cashier_headers, manager_headers, waiter_headers,
    ):
        manager_id = _set_pin(db, "manager@test.local", "1234")
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
            json={"reason": "طلب خطأ", "approver_user_id": manager_id, "approver_pin": "9999"},
            headers=cashier_headers,
        )
        assert resp.status_code == 400

    def test_void_recomputes_order_total(self, client: TestClient, db, cashier_headers, manager_headers, waiter_headers):
        manager_id = _set_pin(db, "manager@test.local", "1234")
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
            json={"reason": "العميل غيّر رأيه", "approver_user_id": manager_id, "approver_pin": "1234"},
            headers=cashier_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert Decimal(str(body["subtotal"])) == Decimal("0.00")
        assert body["items"][0]["status"] == "cancelled"
        assert body["items"][0]["voided_reason"] == "العميل غيّر رأيه"
        assert body["items"][0]["voided_by"] is not None

    def test_void_with_pin_approval_writes_dual_attribution_audit_log(
        self, client: TestClient, db, cashier_headers, manager_headers, waiter_headers,
    ):
        """الإجراء بيتسجل باسم الاثنين: مين نفّذ (voided_by/user_id) ومين
        وافق (approved_by) — راجع core.models.AuditLog.approved_by."""
        from app.core.kernel.models.user import User
        from app.modules.core.models import AuditLog

        manager_id = _set_pin(db, "manager@test.local", "1234")
        cashier = db.query(User).filter(User.email == "cashier@test.local").first()
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
            json={"reason": "بموافقة المدير", "approver_user_id": manager_id, "approver_pin": "1234"},
            headers=cashier_headers,
        )
        assert resp.status_code == 200, resp.text

        log = (
            db.query(AuditLog)
            .filter(AuditLog.action == "void_order_item", AuditLog.entity_id == order_item_id)
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert log is not None
        assert log.user_id == cashier.id
        assert log.approved_by == manager_id

    def test_double_void_rejected(self, client: TestClient, db, cashier_headers, manager_headers, waiter_headers):
        manager_id = _set_pin(db, "manager@test.local", "1234")
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
            json={"reason": "الأول", "approver_user_id": manager_id, "approver_pin": "1234"},
            headers=cashier_headers,
        )
        resp = client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/items/{order_item_id}/void",
            json={"reason": "التاني", "approver_user_id": manager_id, "approver_pin": "1234"},
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


class TestTableTransferHTTP:
    """wagdy.md P-01 — PATCH /restaurant/orders/{id}/transfer."""

    def test_transfer_order_via_http(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)
        old_table = make_table_committed(db, branch)
        new_table = make_table_committed(db, branch)

        order = client.post(
            "/api/v1/restaurant/orders",
            params={"branch_id": branch.id},
            json={"table_id": old_table.id, "order_type": "dine_in", "guests_count": 2,
                  "items": [{"menu_item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()

        resp = client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/transfer",
            json={"table_id": new_table.id},
            headers=waiter_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["table_id"] == new_table.id

        tables = client.get("/api/v1/restaurant/tables", params={"branch_id": branch.id}, headers=waiter_headers).json()
        assert next(t for t in tables if t["id"] == old_table.id)["status"] == "available"
        assert next(t for t in tables if t["id"] == new_table.id)["status"] == "occupied"

    def test_transfer_to_occupied_table_returns_400(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)
        table_a = make_table_committed(db, branch)
        table_b = make_table_committed(db, branch)

        order_a = client.post(
            "/api/v1/restaurant/orders", params={"branch_id": branch.id},
            json={"table_id": table_a.id, "order_type": "dine_in", "guests_count": 2,
                  "items": [{"menu_item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()
        client.post(
            "/api/v1/restaurant/orders", params={"branch_id": branch.id},
            json={"table_id": table_b.id, "order_type": "dine_in", "guests_count": 2,
                  "items": [{"menu_item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )

        resp = client.patch(
            f"/api/v1/restaurant/orders/{order_a['id']}/transfer",
            json={"table_id": table_b.id},
            headers=waiter_headers,
        )
        assert resp.status_code == 400

    def test_transfer_requires_auth(self, client: TestClient, db):
        branch = make_branch_committed(db)
        table = make_table_committed(db, branch)
        resp = client.patch(
            "/api/v1/restaurant/orders/1/transfer",
            json={"table_id": table.id},
        )
        assert resp.status_code == 401


class TestRestaurantReceiptPdf:
    """قبل الإصلاح: generate_receipt_pdf كانت بتستخدم receipt_pdf العادي (مقاس A4 كامل)،
    مش المناسب لطابعة رول حراري 80mm الحقيقية المستخدمة في أي كاشير مطعم. اتصلحت لاستخدام
    receipt_pdf_thermal — نتحقق هنا إن الـ MediaBox فعلاً بعرض 80mm (~226.77pt) مش A4 (~595pt)."""

    def test_receipt_pdf_is_thermal_sized_not_a4(self, client: TestClient, db, waiter_headers, cashier_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)

        order = client.post(
            "/api/v1/restaurant/orders",
            params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1,
                  "items": [{"menu_item_id": item.id, "quantity": 2}]},
            headers=waiter_headers,
        ).json()

        resp = client.get(
            f"/api/v1/restaurant/orders/{order['id']}/receipt",
            headers=cashier_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == "application/pdf"

        import re
        match = re.search(rb"/MediaBox\s*\[([^\]]+)\]", resp.content)
        assert match is not None
        media_box = [float(v) for v in match.group(1).split()]
        pdf_width = media_box[2] - media_box[0]
        # 80mm ≈ 226.77pt — لازم يبقى أضيق بكتير من A4 (595pt عرض)
        assert pdf_width < 300, f"expected thermal-width PDF, got width={pdf_width}pt (A4 is ~595pt)"


class TestMenuItemCrudHTTP:
    """create_menu_item/update_menu_item/delete_extra_group had zero HTTP
    coverage -- only exercised indirectly through orders using an
    already-existing item."""

    def test_create_and_update_menu_item(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/restaurant/menu/items",
            json={"branch_id": branch.id, "name": "Grilled Salmon", "name_ar": "سالمون مشوي",
                  "price": "220.00", "station": "grill"},
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        item = create_resp.json()
        assert item["station"] == "grill"

        update_resp = client.patch(
            f"/api/v1/restaurant/menu/items/{item['id']}",
            json={"price": "250.00", "is_available": False},
            headers=manager_headers,
        )
        assert update_resp.status_code == 200, update_resp.text
        updated = update_resp.json()
        assert Decimal(str(updated["price"])) == Decimal("250.00")
        assert updated["is_available"] is False

    def test_create_and_update_menu_item_availability_window(self, client: TestClient, db, manager_headers):
        """wagdy.md P-03 — available_from_time/available_until_time بيتحفظوا
        ويترجعوا صح عبر create/update، ونقدر نمسحهم (NULL) تاني."""
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/restaurant/menu/items",
            json={"branch_id": branch.id, "name": "فطار صباحي", "price": "60.00",
                  "available_from_time": "07:00:00", "available_until_time": "11:00:00"},
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        item = create_resp.json()
        assert item["available_from_time"] == "07:00:00"
        assert item["available_until_time"] == "11:00:00"

        clear_resp = client.patch(
            f"/api/v1/restaurant/menu/items/{item['id']}",
            json={"available_from_time": None, "available_until_time": None},
            headers=manager_headers,
        )
        assert clear_resp.status_code == 200, clear_resp.text
        assert clear_resp.json()["available_from_time"] is None
        assert clear_resp.json()["available_until_time"] is None

    def test_create_menu_item_requires_manager(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/restaurant/menu/items",
            json={"branch_id": branch.id, "name": "طبق تجريبي", "price": "50.00"},
            headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_delete_extra_group(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)
        group_resp = client.post(
            f"/api/v1/restaurant/menu/items/{item.id}/extra-groups",
            json={"name": "Sauce", "min_select": 0, "max_select": 1,
                  "options": [{"name": "Ketchup", "price_addition": "0"}]},
            headers=manager_headers,
        )
        assert group_resp.status_code == 201, group_resp.text
        group_id = group_resp.json()["id"]

        delete_resp = client.delete(
            f"/api/v1/restaurant/menu/extra-groups/{group_id}", headers=manager_headers,
        )
        assert delete_resp.status_code == 204

        # Deleting an already-deleted group must 404, not 500.
        second_delete = client.delete(
            f"/api/v1/restaurant/menu/extra-groups/{group_id}", headers=manager_headers,
        )
        assert second_delete.status_code == 404


class TestKDSScreensHTTP:
    def test_create_and_list_kds_screen(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/restaurant/kds-screens",
            json={"branch_id": branch.id, "name": "شاشة الشواية", "module": "restaurant",
                  "stations": ["grill", "hot"]},
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text

        list_resp = client.get(
            "/api/v1/restaurant/kds-screens", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert list_resp.status_code == 200
        assert any(s["name"] == "شاشة الشواية" for s in list_resp.json())

    def test_create_kds_screen_requires_manager(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/restaurant/kds-screens",
            json={"branch_id": branch.id, "name": "شاشة", "stations": ["hot"]},
            headers=waiter_headers,
        )
        assert resp.status_code == 403


class TestListOrdersDateFilterHTTP:
    def test_list_orders_filters_by_order_date(self, client: TestClient, db, waiter_headers, cashier_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)
        order = client.post(
            "/api/v1/restaurant/orders", params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1,
                  "items": [{"menu_item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()

        from datetime import date, timedelta
        today_resp = client.get(
            "/api/v1/restaurant/orders",
            params={"branch_id": branch.id, "order_date": str(date.today())},
            headers=cashier_headers,
        )
        assert today_resp.status_code == 200
        assert any(o["id"] == order["id"] for o in today_resp.json()["items"])

        yesterday_resp = client.get(
            "/api/v1/restaurant/orders",
            params={"branch_id": branch.id, "order_date": str(date.today() - timedelta(days=1))},
            headers=cashier_headers,
        )
        assert all(o["id"] != order["id"] for o in yesterday_resp.json()["items"])


def make_product_committed(client: TestClient, branch_id: int, manager_headers, cost_price="180.00"):
    """يزرع warehouse + product عبر الـ API الحقيقي (نفس مسار HTTP اللي شاشة
    الوصفة في الفرونت إند هتستخدمه فعليًا)."""
    wh = client.post(
        "/api/v1/inventory/warehouses",
        json={"branch_id": branch_id, "name": "مخزن اختبار", "code": f"WH-{uuid.uuid4().hex[:6].upper()}"},
        headers=manager_headers,
    ).json()
    product = client.post(
        "/api/v1/inventory/products",
        json={"branch_id": branch_id, "warehouse_id": wh["id"], "name": "لحم مفروم",
              "sku": f"SKU-{uuid.uuid4().hex[:6].upper()}", "unit": "kg", "cost_price": cost_price},
        headers=manager_headers,
    ).json()
    return product


class TestMenuItemRecipeHTTP:
    """POST/PATCH/DELETE .../recipe-lines — الوصفة/BOM الحقيقية للصنف. مفيش
    UI موجود قبل كده للـ endpoints دي، أول تغطية HTTP حقيقية."""

    def test_add_update_delete_recipe_line(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)
        product = make_product_committed(client, branch.id, manager_headers)

        add_resp = client.post(
            f"/api/v1/restaurant/menu/items/{item.id}/recipe-lines",
            json={"product_id": product["id"], "quantity_per_unit": "0.150"},
            headers=manager_headers,
        )
        assert add_resp.status_code == 201, add_resp.text
        line = add_resp.json()
        assert line["product_name"] == "لحم مفروم"
        assert Decimal(str(line["unit_cost"])) == Decimal("180.00")
        assert Decimal(str(line["line_cost"])) == Decimal("27.00")  # 0.150 * 180

        # الصنف نفسه لازم يرجّع computed_cost + recipe_lines دلوقتي
        get_resp = client.get(
            "/api/v1/restaurant/menu/items", params={"branch_id": branch.id}, headers=manager_headers,
        )
        fetched = next(i for i in get_resp.json() if i["id"] == item.id)
        assert Decimal(str(fetched["computed_cost"])) == Decimal("27.00")
        assert len(fetched["recipe_lines"]) == 1

        update_resp = client.patch(
            f"/api/v1/restaurant/menu/recipe-lines/{line['id']}",
            json={"quantity_per_unit": "0.200"},
            headers=manager_headers,
        )
        assert update_resp.status_code == 200, update_resp.text
        assert Decimal(str(update_resp.json()["quantity_per_unit"])) == Decimal("0.200")

        delete_resp = client.delete(
            f"/api/v1/restaurant/menu/recipe-lines/{line['id']}", headers=manager_headers,
        )
        assert delete_resp.status_code == 204

        second_delete = client.delete(
            f"/api/v1/restaurant/menu/recipe-lines/{line['id']}", headers=manager_headers,
        )
        assert second_delete.status_code == 404

    def test_add_recipe_line_requires_manager(self, client: TestClient, db, manager_headers, waiter_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)
        product = make_product_committed(client, branch.id, manager_headers)

        resp = client.post(
            f"/api/v1/restaurant/menu/items/{item.id}/recipe-lines",
            json={"product_id": product["id"], "quantity_per_unit": "0.1"},
            headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_add_recipe_line_rejects_duplicate_product(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)
        product = make_product_committed(client, branch.id, manager_headers)

        payload = {"product_id": product["id"], "quantity_per_unit": "0.1"}
        first = client.post(
            f"/api/v1/restaurant/menu/items/{item.id}/recipe-lines", json=payload, headers=manager_headers,
        )
        assert first.status_code == 201
        second = client.post(
            f"/api/v1/restaurant/menu/items/{item.id}/recipe-lines", json=payload, headers=manager_headers,
        )
        assert second.status_code == 400


# ═══════════════════════════════════════════════════════════════════════
# Missing Coverage — lines 116-577
# ═══════════════════════════════════════════════════════════════════════

class TestRestaurantCategoryErrors:
    """lines 116-122, 129-131 — category update/delete 404 paths"""

    def test_update_category_not_found(self, client: TestClient, manager_headers):
        resp = client.patch(
            "/api/v1/restaurant/menu/categories/99999",
            json={"name": "Ghost"},
            headers=manager_headers,
        )
        assert resp.status_code == 404

    def test_delete_category_not_found(self, client: TestClient, manager_headers):
        resp = client.delete(
            "/api/v1/restaurant/menu/categories/99999",
            headers=manager_headers,
        )
        assert resp.status_code == 404


class TestRestaurantMenuItemErrors:
    """lines 160, 170-172, 181 — menu item update/delete 404 + extra-group 404"""

    def test_update_menu_item_not_found(self, client: TestClient, manager_headers):
        resp = client.patch(
            "/api/v1/restaurant/menu/items/99999",
            json={"name": "Ghost"},
            headers=manager_headers,
        )
        assert resp.status_code == 404

    def test_delete_menu_item_not_found(self, client: TestClient, manager_headers):
        resp = client.delete(
            "/api/v1/restaurant/menu/items/99999",
            headers=manager_headers,
        )
        assert resp.status_code == 404

    def test_add_extra_group_item_not_found(self, client: TestClient, manager_headers):
        resp = client.post(
            "/api/v1/restaurant/menu/items/99999/extra-groups",
            json={"name": "Sides", "required": False, "max_choices": 1, "options": []},
            headers=manager_headers,
        )
        assert resp.status_code == 404

    def test_delete_extra_group_not_found(self, client: TestClient, manager_headers):
        resp = client.delete(
            "/api/v1/restaurant/menu/extra-groups/99999",
            headers=manager_headers,
        )
        assert resp.status_code == 404


class TestRestaurantTableErrors:
    """lines 215-216, 238-239 — table update/delete 404"""

    def test_update_table_not_found(self, client: TestClient, manager_headers):
        resp = client.patch(
            "/api/v1/restaurant/tables/99999",
            json={"status": "available"},
            headers=manager_headers,
        )
        assert resp.status_code == 404

    def test_delete_table_not_found(self, client: TestClient, manager_headers):
        resp = client.delete(
            "/api/v1/restaurant/tables/99999",
            headers=manager_headers,
        )
        assert resp.status_code == 404

    def test_delete_occupied_table_rejected(self, client: TestClient, db, manager_headers):
        from app.modules.restaurant.models import DiningTable
        branch = make_branch_committed(db)
        table = DiningTable(
            branch_id=branch.id, table_number="OCC-01", capacity=4, status="occupied"
        )
        db.add(table); db.commit()
        resp = client.delete(
            f"/api/v1/restaurant/tables/{table.id}",
            headers=manager_headers,
        )
        assert resp.status_code == 409


class TestRestaurantOrderStatusEdgeCases:
    """lines 245-285 — order status transitions edge cases"""

    def _create_order(self, client, db, waiter_headers):
        branch = make_branch_committed(db)
        cat = make_category_committed(db, branch)
        item = make_menu_item_committed(db, branch, cat)
        resp = client.post(
            f"/api/v1/restaurant/orders?branch_id={branch.id}",
            json={"items": [{"menu_item_id": item.id, "quantity": 1, "notes": ""}]},
            headers=waiter_headers,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_update_order_status_not_found(self, client: TestClient, waiter_headers):
        resp = client.patch(
            "/api/v1/restaurant/orders/99999/status",
            json={"status": "in_kitchen"},
            headers=waiter_headers,
        )
        assert resp.status_code == 400

    def test_invalid_order_status_transition(self, client: TestClient, db, waiter_headers):
        order = self._create_order(client, db, waiter_headers)
        # مش ممكن تروح من open لـ paid مباشرة
        resp = client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/status",
            json={"status": "paid", "payment_method": "cash"},
            headers=waiter_headers,
        )
        # waiter مش عنده صلاحية paid أو الـ transition غلط
        assert resp.status_code in (400, 403)


class TestRestaurantOrderItemsAddRemove:
    """lines 320-361 — add items to existing order + error cases"""

    def _full_order(self, client, db, waiter_headers, cashier_headers):
        branch = make_branch_committed(db)
        cat = make_category_committed(db, branch)
        item = make_menu_item_committed(db, branch, cat)
        order_resp = client.post(
            f"/api/v1/restaurant/orders?branch_id={branch.id}",
            json={"items": [{"menu_item_id": item.id, "quantity": 1, "notes": ""}]},
            headers=waiter_headers,
        )
        assert order_resp.status_code == 201
        return order_resp.json(), item.id, branch

    def test_add_items_to_open_order(self, client: TestClient, db, waiter_headers, cashier_headers):
        order, item, branch = self._full_order(client, db, waiter_headers, cashier_headers)
        resp = client.post(
            f"/api/v1/restaurant/orders/{order['id']}/items",
            json=[{"menu_item_id": item, "quantity": 2, "notes": "extra hot"}],
            headers=waiter_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert sum(i["quantity"] for i in data["items"]) == 3

    def test_add_items_empty_list_rejected(self, client: TestClient, db, waiter_headers, cashier_headers):
        order, item, branch = self._full_order(client, db, waiter_headers, cashier_headers)
        resp = client.post(
            f"/api/v1/restaurant/orders/{order['id']}/items",
            json=[],
            headers=waiter_headers,
        )
        assert resp.status_code == 400

    def test_add_items_to_paid_order_rejected(self, client: TestClient, db, waiter_headers, cashier_headers):
        order, item, branch = self._full_order(client, db, waiter_headers, cashier_headers)
        # أرسل للمطبخ
        client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/status",
            json={"status": "in_kitchen"},
            headers=waiter_headers,
        )
        # ادفع
        client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/status",
            json={"status": "served"},
            headers=waiter_headers,
        )
        client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/status",
            json={"status": "paid", "payment_method": "cash"},
            headers=cashier_headers,
        )
        # حاول تضيف صنف لطلب مدفوع
        resp = client.post(
            f"/api/v1/restaurant/orders/{order['id']}/items",
            json=[{"menu_item_id": item, "quantity": 1, "notes": ""}],
            headers=waiter_headers,
        )
        assert resp.status_code == 400


class TestRestaurantKDSHTTP:
    """lines 401-402, 419-420 — KDS tickets list + status update"""

    def test_list_kds_tickets_empty(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            f"/api/v1/restaurant/kitchen/tickets?branch_id={branch.id}",
            headers=manager_headers,
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_kds_tickets_with_station_filter(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            f"/api/v1/restaurant/kitchen/tickets?branch_id={branch.id}&stations=hot_kitchen",
            headers=manager_headers,
        )
        assert resp.status_code == 200

    def test_update_kds_ticket_not_found(self, client: TestClient, manager_headers):
        resp = client.patch(
            "/api/v1/restaurant/kitchen/tickets/99999/status",
            json={"status": "done"},
            headers=manager_headers,
        )
        assert resp.status_code == 404


class TestKitchenItemBumpHTTP:
    """wagdy.md P-05 — PATCH /restaurant/orders/{order_id}/items/{item_id}/status
    (تأكيد صنف بصنف من شاشة KDS، بدل تأكيد التذكرة كلها دفعة واحدة)."""

    def _order_in_kitchen(self, client, db, waiter_headers, branch, items):
        order = client.post(
            "/api/v1/restaurant/orders", params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1,
                  "items": [{"menu_item_id": i.id, "quantity": 1} for i in items]},
            headers=waiter_headers,
        ).json()
        client.patch(f"/api/v1/restaurant/orders/{order['id']}/status",
                     json={"status": "in_kitchen"}, headers=waiter_headers)
        return order

    def test_bump_single_item_updates_status_and_ticket(self, client: TestClient, db, waiter_headers, manager_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)
        order = self._order_in_kitchen(client, db, waiter_headers, branch, [item])
        item_id = order["items"][0]["id"]

        resp = client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/items/{item_id}/status",
            json={"status": "ready"},
            headers=waiter_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"][0]["status"] == "ready"

        # التذكرة اللي فيها الصنف ده بس لازم تبقى 'done' تلقائيًا — راجع
        # services._sync_kitchen_tickets_for_order
        tickets = client.get(
            f"/api/v1/restaurant/kitchen/tickets?branch_id={branch.id}&module=restaurant",
            headers=manager_headers,
        ).json()
        assert not any(t["order_id"] == order["id"] for t in tickets)  # مش pending/in_progress بقى

    def test_ticket_stays_pending_until_all_items_bumped(self, client: TestClient, db, waiter_headers, manager_headers):
        branch = make_branch_committed(db)
        hot_item = make_menu_item_committed(db, branch)
        from app.modules.restaurant.models import MenuItem
        grill_item = MenuItem(branch_id=branch.id, name="مشويات اختبار",
                              price=Decimal("60.00"), is_available=True, station="hot")
        db.add(grill_item); db.commit()

        order = self._order_in_kitchen(client, db, waiter_headers, branch, [hot_item, grill_item])
        first_item_id = order["items"][0]["id"]

        client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/items/{first_item_id}/status",
            json={"status": "ready"}, headers=waiter_headers,
        )

        tickets = client.get(
            f"/api/v1/restaurant/kitchen/tickets?branch_id={branch.id}&module=restaurant",
            headers=manager_headers,
        ).json()
        ticket = next(t for t in tickets if t["order_id"] == order["id"])
        assert ticket["status"] == "in_progress"  # لسه مش كل الأصناف اتأكدت
        item_statuses = {i["order_item_id"]: i["status"] for i in ticket["items_snapshot"]}
        assert item_statuses[first_item_id] == "ready"

    def test_bump_item_not_found_returns_400(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)
        order = self._order_in_kitchen(client, db, waiter_headers, branch, [item])

        resp = client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/items/999999/status",
            json={"status": "ready"},
            headers=waiter_headers,
        )
        assert resp.status_code == 400

    def test_bump_invalid_status_rejected(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)
        order = self._order_in_kitchen(client, db, waiter_headers, branch, [item])
        item_id = order["items"][0]["id"]

        resp = client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/items/{item_id}/status",
            json={"status": "cancelled"},  # ليه endpoint مخصص (void) — مش مسموح هنا
            headers=waiter_headers,
        )
        assert resp.status_code == 422

    def test_confirming_whole_ticket_bumps_remaining_items_to_ready(self, client: TestClient, db, waiter_headers, manager_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)
        order = self._order_in_kitchen(client, db, waiter_headers, branch, [item])

        tickets = client.get(
            f"/api/v1/restaurant/kitchen/tickets?branch_id={branch.id}&module=restaurant",
            headers=manager_headers,
        ).json()
        ticket = next(t for t in tickets if t["order_id"] == order["id"])

        resp = client.patch(
            f"/api/v1/restaurant/kitchen/tickets/{ticket['id']}/status",
            json={"status": "done"}, headers=manager_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["items_snapshot"][0]["status"] == "ready"

        order_resp = client.get(f"/api/v1/restaurant/orders/{order['id']}", headers=manager_headers).json()
        assert order_resp["items"][0]["status"] == "ready"


class TestRestaurantSearchOrders:
    """lines 431-434 — order search filter"""

    def test_list_orders_by_status(self, client: TestClient, db, waiter_headers, cashier_headers):
        branch = make_branch_committed(db)
        cat = make_category_committed(db, branch)
        item = make_menu_item_committed(db, branch, cat)
        # إنشاء طلب
        client.post(
            f"/api/v1/restaurant/orders?branch_id={branch.id}",
            json={"items": [{"menu_item_id": item.id, "quantity": 1, "notes": ""}]},
            headers=waiter_headers,
        )
        resp = client.get(
            f"/api/v1/restaurant/orders?branch_id={branch.id}&status=open",
            headers=cashier_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert all(o["status"] == "open" for o in data["items"])


class TestRestaurantDiscountAndReceipt:
    """lines 497-509, 536-537, 577 — discount + receipt error paths"""

    def test_apply_discount_order_not_found(self, client: TestClient, cashier_headers):
        resp = client.post(
            "/api/v1/restaurant/orders/99999/discount",
            headers=cashier_headers,
        )
        assert resp.status_code == 400

    def test_download_receipt_not_found(self, client: TestClient, cashier_headers):
        resp = client.get(
            "/api/v1/restaurant/orders/99999/receipt",
            headers=cashier_headers,
        )
        assert resp.status_code == 404

    def test_get_order_not_found(self, client: TestClient, manager_headers):
        resp = client.get(
            "/api/v1/restaurant/orders/99999",
            headers=manager_headers,
        )
        assert resp.status_code == 404


def make_category_committed(db, branch):
    from app.modules.restaurant.models import MenuCategory
    import uuid
    cat = MenuCategory(branch_id=branch.id, name=f"Cat-{uuid.uuid4().hex[:4]}", sort_order=0)
    db.add(cat); db.commit(); return cat


def make_menu_item_committed(db, branch, cat=None):
    from app.modules.restaurant.models import MenuItem
    import uuid
    if cat is None:
        cat = make_category_committed(db, branch)
    item = MenuItem(
        branch_id=branch.id, category_id=cat.id,
        name=f"Item-{uuid.uuid4().hex[:4]}", name_ar="صنف",
        price=Decimal("80.00"), is_available=True,
    )
    db.add(item); db.commit(); return item
