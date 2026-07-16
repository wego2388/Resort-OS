"""
tests/test_api/test_dining_http.py
HTTP-level tests for the unified dining router (wagdy.md D-04) — exercises
the FastAPI app + TestClient, not just service functions directly.

راجع DINING_CUTOVER_PLAN.md Batch 6 (2026-07-13) — restaurant/cafe اتحذفوا
بالكامل من المشروع، فـ TestOldUrlsStillWork (كانت بتثبت إن /restaurant
و/cafe لسه شغالين جنب /dining أثناء الفترة الانتقالية) اتشالت — مفيش
/restaurant أو /cafe تاني يتأكد إنه شغال.
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


def _set_shift_pin(db, email: str, pin: str) -> int:
    """نفس نمط _set_shift_pin في test_finance_http.py — يضبط PIN حقيقي عبر
    core.services (مش تلاعب مباشر بالداتابيز) ويرجّع user.id."""
    from app.core.kernel.models.user import User
    from app.modules.core import services as core_services

    user = db.query(User).filter(User.email == email).first()
    core_services.set_pin(db, user.id, pin, created_by=user.id)
    db.commit()
    return user.id


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

    def test_create_and_update_item_availability_window(self, client: TestClient, db, manager_headers):
        """wagdy.md P-03 — available_from_time/available_until_time بيتحفظوا
        ويترجعوا صح عبر create/update، ونقدر نمسحهم (NULL) تاني. راجع
        restaurant.tests.test_create_and_update_menu_item_availability_window."""
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        create_resp = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/items",
            json={"branch_id": branch.id, "outlet_id": outlet.id, "name": "فطار صباحي",
                  "price": "60.00", "available_from_time": "07:00:00", "available_until_time": "11:00:00"},
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        item = create_resp.json()
        assert item["available_from_time"] == "07:00:00"
        assert item["available_until_time"] == "11:00:00"

        clear_resp = client.patch(
            f"/api/v1/dining/items/{item['id']}",
            json={"available_from_time": None, "available_until_time": None},
            headers=manager_headers,
        )
        assert clear_resp.status_code == 200, clear_resp.text
        assert clear_resp.json()["available_from_time"] is None
        assert clear_resp.json()["available_until_time"] is None


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

    def test_takeaway_service_charge_override_applies(self, client: TestClient, db, waiter_headers):
        """2026-07-16، بحث مقارنة Click القديم: takeaway_service_charge_pct
        override على المنفذ — لو صفر، مفيش رسم خدمة على طلبات التيك أواي
        بس، النسبة العامة (12%) تفضل سارية على dine_in/باقي القنوات."""
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        outlet.takeaway_service_charge_pct = Decimal("0")
        db.commit()
        item = make_item_committed(db, branch, outlet)

        resp = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={"outlet_id": outlet.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 2}]},
            headers=waiter_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert Decimal(str(body["subtotal"])) == Decimal("160.00")
        assert Decimal(str(body["service_charge"])) == Decimal("0.00")
        assert Decimal(str(body["vat_amount"])) == Decimal("22.40")
        assert Decimal(str(body["total"])) == Decimal("182.40")

    def test_delivery_fee_added_to_total_and_survives_item_void(
        self, client: TestClient, db, waiter_headers, manager_headers,
    ):
        """رسم توصيل ثابت (delivery_fee) بيتضاف للـ total — ولازم يفضل زي
        ما هو حتى بعد إلغاء صنف (رسم ثابت مش نسبة، مش لازم يتصفّر)."""
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        outlet.delivery_fee = Decimal("15.00")
        db.commit()
        item = make_item_committed(db, branch, outlet)

        order_resp = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={"outlet_id": outlet.id, "order_type": "delivery",
                  "items": [{"item_id": item.id, "quantity": 2}]},
            headers=waiter_headers,
        )
        assert order_resp.status_code == 201, order_resp.text
        order = order_resp.json()
        # subtotal=160 → vat=22.40، svc=19.20 (12% عام، مفيش override
        # delivery)، delivery_fee=15 → total=216.60
        assert Decimal(str(order["delivery_fee"])) == Decimal("15.00")
        assert Decimal(str(order["total"])) == Decimal("216.60")

        # الصنف سطر واحد بكمية 2 — إلغاؤه بيلغي السطر كله (مش وحدة واحدة
        # بس)، فـ subtotal/vat/svc كلهم بيرجعوا صفر. delivery_fee لازم
        # يفضل 15 بالظبط رغم كده (رسم ثابت، مش نسبة من الأصناف) — إثبات
        # أقوى إنه مش بيتصفّر مع باقي الحسابات.
        item_id = order["items"][0]["id"]
        void_resp = client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{item_id}/void",
            json={"reason": "إلغاء السطر بالكامل"},
            headers=manager_headers,
        )
        assert void_resp.status_code == 200, void_resp.text
        after = void_resp.json()
        assert Decimal(str(after["subtotal"])) == Decimal("0.00")
        assert Decimal(str(after["delivery_fee"])) == Decimal("15.00")
        assert Decimal(str(after["total"])) == Decimal("15.00")

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


class TestDiningDiscountHTTP:
    """قرار Mohamed 2026-07-13: الكاشير صفر صلاحية خصم خالص — أي محاولة
    تطبيق خصم من مستوى أقل من مدير محتاجة موافقة PIN مدير/محاسب حاضر عبر
    core.services.resolve_pin_approval (نفس نمط void، مفيش نظام موافقة
    موازي). راجع services.apply_order_discount."""

    def _order_id(self, client, db, waiter_headers, branch, outlet, item):
        order_resp = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={"outlet_id": outlet.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )
        return order_resp.json()["id"]

    def test_cashier_apply_discount_without_pin_rejected(
        self, client: TestClient, db, waiter_headers, cashier_headers,
    ):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        item = make_item_committed(db, branch, outlet)
        order_id = self._order_id(client, db, waiter_headers, branch, outlet, item)

        resp = client.post(
            f"/api/v1/dining/orders/{order_id}/discount", json={}, headers=cashier_headers,
        )
        assert resp.status_code == 400
        assert "موافقة" in resp.json()["detail"]

    def test_manager_apply_discount_self_qualified(
        self, client: TestClient, db, waiter_headers, manager_headers,
    ):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        item = make_item_committed(db, branch, outlet)
        order_id = self._order_id(client, db, waiter_headers, branch, outlet, item)

        resp = client.post(
            f"/api/v1/dining/orders/{order_id}/discount", json={}, headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text

    def test_cashier_apply_discount_with_valid_manager_pin_succeeds(
        self, client: TestClient, db, waiter_headers, cashier_headers, manager_headers,
    ):
        manager_id = _set_shift_pin(db, "manager@test.local", "5566")
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        item = make_item_committed(db, branch, outlet)
        order_id = self._order_id(client, db, waiter_headers, branch, outlet, item)

        resp = client.post(
            f"/api/v1/dining/orders/{order_id}/discount",
            json={"approver_user_id": manager_id, "approver_pin": "5566"},
            headers=cashier_headers,
        )
        assert resp.status_code == 200, resp.text

    def test_cashier_apply_discount_wrong_pin_rejected(
        self, client: TestClient, db, waiter_headers, cashier_headers, manager_headers,
    ):
        manager_id = _set_shift_pin(db, "manager@test.local", "5566")
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        item = make_item_committed(db, branch, outlet)
        order_id = self._order_id(client, db, waiter_headers, branch, outlet, item)

        resp = client.post(
            f"/api/v1/dining/orders/{order_id}/discount",
            json={"approver_user_id": manager_id, "approver_pin": "0000"},
            headers=cashier_headers,
        )
        assert resp.status_code == 400


class TestDiningKitchenItemBumpHTTP:
    """راجع restaurant.tests.TestKitchenItemBumpHTTP (wagdy.md P-05) — نفس
    السيناريوهات بالظبط، على PATCH /dining/orders/{order_id}/items/{item_id}/status
    (فجوة تكافؤ أُغلقت قبل حذف restaurant/cafe — DINING_CUTOVER_PLAN.md Batch 1)."""

    def _order_in_kitchen(self, client, db, waiter_headers, branch, outlet, items):
        order = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={"outlet_id": outlet.id, "order_type": "takeaway", "guests_count": 1,
                  "items": [{"item_id": i.id, "quantity": 1} for i in items]},
            headers=waiter_headers,
        ).json()
        client.patch(f"/api/v1/dining/orders/{order['id']}/status",
                     json={"status": "in_kitchen"}, headers=waiter_headers)
        return order

    def test_bump_single_item_updates_status_and_ticket(self, client: TestClient, db, waiter_headers, manager_headers):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        item = make_item_committed(db, branch, outlet)
        order = self._order_in_kitchen(client, db, waiter_headers, branch, outlet, [item])
        item_id = order["items"][0]["id"]

        resp = client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{item_id}/status",
            json={"status": "ready"},
            headers=waiter_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"][0]["status"] == "ready"

        # التذكرة اللي فيها الصنف ده بس لازم تبقى 'done' تلقائيًا — راجع
        # services._sync_kitchen_tickets_for_order
        tickets = client.get(
            "/api/v1/dining/kitchen/tickets",
            params={"branch_id": branch.id},
            headers=manager_headers,
        ).json()
        assert not any(t["order_id"] == order["id"] for t in tickets)  # مش pending/in_progress بقى

    def test_ticket_stays_pending_until_all_items_bumped(self, client: TestClient, db, waiter_headers, manager_headers):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        hot_item = make_item_committed(db, branch, outlet, station="hot")
        grill_item = make_item_committed(db, branch, outlet, station="hot")

        order = self._order_in_kitchen(client, db, waiter_headers, branch, outlet, [hot_item, grill_item])
        first_item_id = order["items"][0]["id"]

        client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{first_item_id}/status",
            json={"status": "ready"}, headers=waiter_headers,
        )

        tickets = client.get(
            "/api/v1/dining/kitchen/tickets",
            params={"branch_id": branch.id},
            headers=manager_headers,
        ).json()
        ticket = next(t for t in tickets if t["order_id"] == order["id"])
        assert ticket["status"] == "in_progress"  # لسه مش كل الأصناف اتأكدت
        item_statuses = {i["order_item_id"]: i["status"] for i in ticket["items_snapshot"]}
        assert item_statuses[first_item_id] == "ready"

    def test_bump_item_not_found_returns_400(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        item = make_item_committed(db, branch, outlet)
        order = self._order_in_kitchen(client, db, waiter_headers, branch, outlet, [item])

        resp = client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/999999/status",
            json={"status": "ready"},
            headers=waiter_headers,
        )
        assert resp.status_code == 400

    def test_bump_invalid_status_rejected(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        item = make_item_committed(db, branch, outlet)
        order = self._order_in_kitchen(client, db, waiter_headers, branch, outlet, [item])
        item_id = order["items"][0]["id"]

        resp = client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{item_id}/status",
            json={"status": "cancelled"},  # ليه endpoint مخصص (void) — مش مسموح هنا
            headers=waiter_headers,
        )
        assert resp.status_code == 422

    def test_bump_cancelled_item_rejected(self, client: TestClient, db, waiter_headers, manager_headers):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        item = make_item_committed(db, branch, outlet)
        order = self._order_in_kitchen(client, db, waiter_headers, branch, outlet, [item])
        item_id = order["items"][0]["id"]

        client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{item_id}/void",
            json={"reason": "طلب غلط"}, headers=manager_headers,
        )
        resp = client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{item_id}/status",
            json={"status": "ready"}, headers=waiter_headers,
        )
        assert resp.status_code == 400

    def test_confirming_whole_ticket_bumps_remaining_items_to_ready(self, client: TestClient, db, waiter_headers, manager_headers):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        item = make_item_committed(db, branch, outlet)
        order = self._order_in_kitchen(client, db, waiter_headers, branch, outlet, [item])

        tickets = client.get(
            "/api/v1/dining/kitchen/tickets",
            params={"branch_id": branch.id},
            headers=manager_headers,
        ).json()
        ticket = next(t for t in tickets if t["order_id"] == order["id"])

        resp = client.patch(
            f"/api/v1/dining/kitchen/tickets/{ticket['id']}/status",
            json={"status": "done"}, headers=manager_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["items_snapshot"][0]["status"] == "ready"

        order_resp = client.get(f"/api/v1/dining/orders/{order['id']}", headers=manager_headers).json()
        assert order_resp["items"][0]["status"] == "ready"


class TestDiningTableTransferHTTP:
    """راجع restaurant.tests.TestTableTransferHTTP (wagdy.md P-01) — نفس
    السيناريوهات بالظبط، على PATCH /dining/orders/{order_id}/transfer
    (فجوة تكافؤ أُغلقت قبل حذف restaurant/cafe — DINING_CUTOVER_PLAN.md Batch 1)."""

    def test_transfer_order_via_http(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        item = make_item_committed(db, branch, outlet)
        old_table = make_table_committed(db, branch, outlet)
        new_table = make_table_committed(db, branch, outlet)

        order = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={"outlet_id": outlet.id, "table_id": old_table.id, "order_type": "dine_in",
                  "guests_count": 2, "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()

        resp = client.patch(
            f"/api/v1/dining/orders/{order['id']}/transfer",
            json={"table_id": new_table.id},
            headers=waiter_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["table_id"] == new_table.id

        tables = client.get(
            f"/api/v1/dining/outlets/{outlet.id}/tables", headers=waiter_headers,
        ).json()
        assert next(t for t in tables if t["id"] == old_table.id)["status"] == "available"
        assert next(t for t in tables if t["id"] == new_table.id)["status"] == "occupied"

    def test_transfer_to_occupied_table_returns_400(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        item = make_item_committed(db, branch, outlet)
        table_a = make_table_committed(db, branch, outlet)
        table_b = make_table_committed(db, branch, outlet)

        order_a = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={"outlet_id": outlet.id, "table_id": table_a.id, "order_type": "dine_in",
                  "guests_count": 2, "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()
        client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={"outlet_id": outlet.id, "table_id": table_b.id, "order_type": "dine_in",
                  "guests_count": 2, "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )

        resp = client.patch(
            f"/api/v1/dining/orders/{order_a['id']}/transfer",
            json={"table_id": table_b.id},
            headers=waiter_headers,
        )
        assert resp.status_code == 400

    def test_transfer_requires_auth(self, client: TestClient, db):
        resp = client.patch("/api/v1/dining/orders/1/transfer", json={"table_id": 1})
        assert resp.status_code == 401




class TestSplitBillHTTP:
    """P-07 — تقسيم الفاتورة على أكثر من طريقة دفع."""

    def _create_paid_order(self, client, db, cashier_headers):
        """Helper — ينشئ order ويرجعه جاهزاً للاختبار (status=open)."""
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        item = make_item_committed(db, branch, outlet, price=Decimal("100.00"))
        resp = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={"outlet_id": outlet.id, "branch_id": branch.id,
                  "order_type": "dine_in", "items": [{"item_id": item.id, "quantity": 1}]},
            headers=cashier_headers,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_split_bill_two_methods(self, client: TestClient, db, cashier_headers):
        """كاش 60 + بطاقة 40 لطلب إجماليه 100 (مع VAT يساوي الـ total بالظبط)."""
        order = self._create_paid_order(client, db, cashier_headers)
        order_total = Decimal(str(order["total"]))

        # تقسيم بنسب عشوائية تساوي الإجمالي بالظبط
        amt1 = (order_total / 2).quantize(Decimal("0.01"))
        amt2 = order_total - amt1

        resp = client.post(
            f"/api/v1/dining/orders/{order['id']}/split-bill",
            json={"payments": [
                {"amount": float(amt1), "payment_method": "cash"},
                {"amount": float(amt2), "payment_method": "card"},
            ]},
            headers=cashier_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "paid"
        assert "split" in data["payment_method"]

    def test_split_bill_total_mismatch_rejected(self, client: TestClient, db, cashier_headers):
        """مجموع الدفعات أقل من الإجمالي → 400."""
        order = self._create_paid_order(client, db, cashier_headers)
        order_total = float(order["total"])

        resp = client.post(
            f"/api/v1/dining/orders/{order['id']}/split-bill",
            json={"payments": [
                {"amount": round(order_total * 0.4, 2), "payment_method": "cash"},
                {"amount": round(order_total * 0.4, 2), "payment_method": "card"},
            ]},
            headers=cashier_headers,
        )
        assert resp.status_code == 400
        assert "لا يساوي" in resp.json()["detail"]

    def test_split_bill_already_paid_rejected(self, client: TestClient, db, cashier_headers):
        """فاتورة مدفوعة بالفعل → 400."""
        order = self._create_paid_order(client, db, cashier_headers)
        order_total = float(order["total"])
        amt1 = round(order_total / 2, 2)
        amt2 = round(order_total - amt1, 2)
        payload = {"payments": [
            {"amount": amt1, "payment_method": "cash"},
            {"amount": amt2, "payment_method": "card"},
        ]}
        # الدفعة الأولى تنجح
        resp1 = client.post(f"/api/v1/dining/orders/{order['id']}/split-bill",
                            json=payload, headers=cashier_headers)
        assert resp1.status_code == 200
        # الدفعة الثانية ترفض
        resp2 = client.post(f"/api/v1/dining/orders/{order['id']}/split-bill",
                            json=payload, headers=cashier_headers)
        assert resp2.status_code == 400
        assert "paid" in resp2.json()["detail"]

    def test_split_bill_requires_cashier_auth(self, client: TestClient, db):
        """بدون auth → 401."""
        resp = client.post("/api/v1/dining/orders/1/split-bill",
                           json={"payments": [{"amount": 50, "payment_method": "cash"},
                                              {"amount": 50, "payment_method": "card"}]})
        assert resp.status_code == 401

    def test_split_bill_single_payment_schema_rejected(self, client: TestClient, db, cashier_headers):
        """SplitBillRequest يشترط min_length=2 — دفعة واحدة → 422."""
        order = self._create_paid_order(client, db, cashier_headers)
        resp = client.post(
            f"/api/v1/dining/orders/{order['id']}/split-bill",
            json={"payments": [{"amount": float(order["total"]), "payment_method": "cash"}]},
            headers=cashier_headers,
        )
        assert resp.status_code == 422
