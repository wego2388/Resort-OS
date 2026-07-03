"""
tests/test_api/test_pos_full_cycle_http.py
End-to-end HTTP-level order-to-payment cycle for restaurant + cafe POS —
written during a QA pass that could not complete a live browser walkthrough
(environment blocked interactive login this session). These tests exercise
the exact same request shapes the fixed frontend views now send, end to end
through real routing/permission dependencies, to compensate for the missing
live verification:

  create order → send to kitchen (KitchenTicket created, routed by station)
  → advance KDS ticket → complete payment (cashier+) → verify table freed +
  VAT/service-charge totals math (14% / 12%, per app/core/config.py defaults).

Two real bugs found+fixed this session, exercised here:
  1. CafePOSView.vue was posting {menu_item_id, unit_price, outlet_type,
     payment_method} — none of which match CafeOrderCreate (needs
     items[].item_id) — so every cafe order from the POS screen 422'd.
     test_cafe_full_cycle_matches_fixed_frontend_payload uses the corrected
     shape end to end.
  2. update_order_status allowed ANY waiter (role level 30) to transition an
     order straight to "paid" — a real financial action (folio charge,
     revenue journal, inventory deduction) with no cashier-level gate, unlike
     the equivalent void_order_item endpoint. Fixed to require cashier+ for
     the "paid" transition specifically; covered by
     TestOrderPaymentPermission in test_restaurant_http.py and
     test_waiter_cannot_mark_order_paid in test_cafe_http.py, and exercised
     again here as part of the full cycle.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient


def make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(name="Full Cycle Branch", name_ar="فرع اختبار كامل",
               code=f"FC-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_table(db, branch):
    from app.modules.restaurant.models import DiningTable
    t = DiningTable(branch_id=branch.id, table_number="F1", capacity=4, status="available")
    db.add(t)
    db.commit()
    return t


class TestRestaurantFullCycle:
    def test_order_to_payment_cycle_with_real_vat_and_service_charge(
        self, client: TestClient, db, waiter_headers, cashier_headers,
    ):
        from app.modules.restaurant.models import MenuItem

        branch = make_branch(db)
        table = make_table(db, branch)
        fish = MenuItem(branch_id=branch.id, name="Grilled Sea Bass", price=Decimal("85.00"), station="grill")
        pasta = MenuItem(branch_id=branch.id, name="Seafood Pasta", price=Decimal("75.00"), station="hot")
        db.add_all([fish, pasta])
        db.commit()

        # 1) واحد ياخد الطلب (نادل)
        order = client.post(
            "/api/v1/restaurant/orders",
            params={"branch_id": branch.id},
            json={
                "table_id": table.id, "order_type": "dine_in", "guests_count": 2,
                "items": [
                    {"menu_item_id": fish.id, "quantity": 1},
                    {"menu_item_id": pasta.id, "quantity": 2},
                ],
            },
            headers=waiter_headers,
        ).json()
        assert order["status"] == "open"

        subtotal = Decimal("85.00") + Decimal("75.00") * 2  # 235.00
        assert Decimal(str(order["subtotal"])) == subtotal
        assert Decimal(str(order["vat_amount"])) == (subtotal * Decimal("0.14")).quantize(Decimal("0.01"))
        assert Decimal(str(order["service_charge"])) == (subtotal * Decimal("0.12")).quantize(Decimal("0.01"))
        expected_total = subtotal + Decimal(str(order["vat_amount"])) + Decimal(str(order["service_charge"]))
        assert Decimal(str(order["total"])) == expected_total

        # 2) يتبعت للمطبخ — لازم تذكرتين منفصلتين (grill + hot)
        resp = client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/status",
            json={"status": "in_kitchen"}, headers=waiter_headers,
        )
        assert resp.status_code == 200, resp.text

        tickets_resp = client.get(
            "/api/v1/restaurant/kitchen/tickets",
            params={"branch_id": branch.id, "module": "restaurant", "stations": "hot,grill,cold,dessert"},
            headers=waiter_headers,
        )
        tickets = tickets_resp.json()
        stations = {t["station"] for t in tickets if t["order_id"] == order["id"]}
        assert stations == {"grill", "hot"}

        # 3) كل تذكرة تتقدّم على شاشة الـ KDS بتاعتها لحد "done"
        for ticket in tickets:
            if ticket["order_id"] != order["id"]:
                continue
            r1 = client.patch(
                f"/api/v1/restaurant/kitchen/tickets/{ticket['id']}/status",
                json={"status": "in_progress"}, headers=waiter_headers,
            )
            assert r1.status_code == 200
            r2 = client.patch(
                f"/api/v1/restaurant/kitchen/tickets/{ticket['id']}/status",
                json={"status": "done"}, headers=waiter_headers,
            )
            assert r2.status_code == 200

        # 4) نادل ملوش صلاحية يقفل الحساب
        denied = client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/status",
            json={"status": "paid"}, headers=waiter_headers,
        )
        assert denied.status_code == 403

        # 5) الكاشير بيقفل الحساب فعليًا
        paid = client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/status",
            json={"status": "paid"}, headers=cashier_headers,
        )
        assert paid.status_code == 200, paid.text
        assert paid.json()["status"] == "paid"
        assert Decimal(str(paid.json()["total"])) == expected_total

        # 6) الطاولة اترجعت متاحة
        tables_resp = client.get(
            "/api/v1/restaurant/tables", params={"branch_id": branch.id}, headers=waiter_headers,
        )
        found = next(t for t in tables_resp.json() if t["id"] == table.id)
        assert found["status"] == "available"


class TestCafeFullCycle:
    def test_cafe_full_cycle_matches_fixed_frontend_payload(
        self, client: TestClient, db, fake_redis, waiter_headers, cashier_headers,
    ):
        """نفس الـ shape اللي CafePOSView.vue بيبعته دلوقتي بعد الإصلاح —
        item_id (مش menu_item_id)، من غير outlet_type/payment_method/unit_price."""
        from app.modules.cafe.models import CafeItem

        branch = make_branch(db)
        pizza = CafeItem(branch_id=branch.id, name="Margherita", price=Decimal("220.00"), is_available=True)
        db.add(pizza)
        db.commit()

        payload = {
            "branch_id": branch.id,
            "order_type": "takeaway",
            "items": [{"item_id": pizza.id, "quantity": 2, "notes": None}],
        }
        order = client.post("/api/v1/cafe/orders", json=payload, headers=waiter_headers).json()
        assert order["status"] == "open"
        subtotal = Decimal("220.00") * 2
        assert Decimal(str(order["subtotal"])) == subtotal

        # in_kitchen (بار) — نفس اللي CafePOSView.submitOrder() بيعمله دلوقتي
        r1 = client.patch(
            f"/api/v1/cafe/orders/{order['id']}/status",
            json={"status": "in_kitchen"}, headers=waiter_headers,
        )
        assert r1.status_code == 200, r1.text

        # الدفع فوري عند الكاونتر — كاشير بس
        denied = client.patch(
            f"/api/v1/cafe/orders/{order['id']}/status",
            json={"status": "paid"}, headers=waiter_headers,
        )
        assert denied.status_code == 403

        paid = client.patch(
            f"/api/v1/cafe/orders/{order['id']}/status",
            json={"status": "paid"}, headers=cashier_headers,
        )
        assert paid.status_code == 200, paid.text
        assert paid.json()["status"] == "paid"
        expected_total = subtotal + (subtotal * Decimal("0.14")).quantize(Decimal("0.01")) + (subtotal * Decimal("0.12")).quantize(Decimal("0.01"))
        assert Decimal(str(paid.json()["total"])) == expected_total
