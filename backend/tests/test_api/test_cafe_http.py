"""
tests/test_api/test_cafe_http.py
HTTP-level tests for the cafe module — TestClient through real routing,
permission dependencies and Pydantic validation (not direct service calls).

⚠️ Setup data created here must be `db.commit()`-ed, not `.flush()`-ed.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="Cafe HTTP Branch", name_ar="فرع كافيه",
               code=f"CAF-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_item_committed(db, branch, available=True):
    from app.modules.cafe.models import CafeItem
    item = CafeItem(branch_id=branch.id, name="كابتشينو", price=Decimal("45.00"), is_available=available)
    db.add(item)
    db.commit()
    return item


def make_table_committed(db, branch):
    from app.modules.cafe.models import CafeTable
    table = CafeTable(branch_id=branch.id, table_number=f"C-{uuid.uuid4().hex[:6].upper()}",
                       capacity=2, status="available")
    db.add(table)
    db.commit()
    return table


def make_category_committed(db, branch, name="Pizza", name_ar="بيتزا"):
    from app.modules.cafe.models import CafeCategory
    category = CafeCategory(branch_id=branch.id, name=name, name_ar=name_ar)
    db.add(category)
    db.commit()
    return category


class TestCafeOrderFlow:
    def test_create_order_via_http(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)

        resp = client.post(
            "/api/v1/cafe/orders",
            json={
                "branch_id": branch.id, "order_type": "takeaway",
                "items": [{"item_id": item.id, "quantity": 2}],
            },
            headers=waiter_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "open"
        assert Decimal(str(body["subtotal"])) == Decimal("90.00")

    def test_order_status_progresses_to_paid(self, client: TestClient, db, fake_redis, waiter_headers, cashier_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()

        # إتمام الدفع فعل مالي (كاشير أو أعلى بس — راجع update_order_status)
        resp = client.patch(
            f"/api/v1/cafe/orders/{order['id']}/status", json={"status": "paid"}, headers=cashier_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "paid"

    def test_waiter_cannot_mark_order_paid(self, client: TestClient, db, fake_redis, waiter_headers):
        """فعل مالي — الجرسون ملوش صلاحية يقفل حساب لوحده (نفس منطق void_order_item)."""
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()

        resp = client.patch(
            f"/api/v1/cafe/orders/{order['id']}/status", json={"status": "paid"}, headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_create_order_rejects_unavailable_item(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch, available=False)
        resp = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )
        assert resp.status_code == 400


class TestCafePermissions:
    def test_create_order_requires_waiter_level(self, client: TestClient, db, fake_redis):
        """customer-level token must not create cafe orders (waiter+ required)."""
        from tests.conftest import _create_test_user, _make_token
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        _create_test_user("cafe-customer@test.local", "customer")
        headers = {"Authorization": f"Bearer {_make_token('cafe-customer@test.local')}"}

        resp = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_create_item_requires_manager(self, client: TestClient, db, fake_redis, waiter_headers):
        """waiter (30) must not create cafe menu items (manager=60 required)."""
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/cafe/items",
            json={"branch_id": branch.id, "name": "شاي", "price": "20.00"},
            headers=waiter_headers,
        )
        assert resp.status_code == 403


class TestCafeValidation:
    def test_create_order_rejects_empty_items(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway", "items": []},
            headers=waiter_headers,
        )
        assert resp.status_code == 422

    def test_update_order_status_rejects_invalid_value(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()

        resp = client.patch(
            f"/api/v1/cafe/orders/{order['id']}/status", json={"status": "teleported"}, headers=waiter_headers,
        )
        assert resp.status_code == 422


class TestCafeHeldOrders:
    """Mirrors TestHeldOrders in test_restaurant_http.py — cafe waiters can
    park an order (fb_hold-equivalent) and resume it later."""

    def test_hold_order_creates_with_held_status(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)

        resp = client.post(
            "/api/v1/cafe/orders/hold",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["status"] == "held"

    def test_held_orders_list_only_shows_held(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)

        held_resp = client.post(
            "/api/v1/cafe/orders/hold",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )
        client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )

        resp = client.get("/api/v1/cafe/orders/held", params={"branch_id": branch.id}, headers=waiter_headers)
        assert resp.status_code == 200
        ids = [o["id"] for o in resp.json()]
        assert held_resp.json()["id"] in ids
        assert all(o["status"] == "held" for o in resp.json())

    def test_resume_held_order_to_open(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        held = client.post(
            "/api/v1/cafe/orders/hold",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()

        resp = client.patch(
            f"/api/v1/cafe/orders/{held['id']}/status", json={"status": "open"}, headers=waiter_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "open"


class TestCafeVoidOrderItem:
    """Mirrors TestVoidOrderItem in test_restaurant_http.py — cashier+ only,
    mandatory reason, recomputes totals, blocks double-void."""

    def test_void_requires_cashier_level(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()
        order_item_id = order["items"][0]["id"]

        resp = client.patch(
            f"/api/v1/cafe/orders/{order['id']}/items/{order_item_id}/void",
            json={"reason": "طلب خطأ"},
            headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_void_recomputes_order_total(self, client: TestClient, db, fake_redis, cashier_headers, waiter_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 2}]},
            headers=waiter_headers,
        ).json()
        order_item_id = order["items"][0]["id"]
        assert Decimal(str(order["subtotal"])) == Decimal("90.00")

        resp = client.patch(
            f"/api/v1/cafe/orders/{order['id']}/items/{order_item_id}/void",
            json={"reason": "العميل غيّر رأيه"},
            headers=cashier_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert Decimal(str(body["subtotal"])) == Decimal("0.00")
        assert body["items"][0]["status"] == "cancelled"
        assert body["items"][0]["voided_reason"] == "العميل غيّر رأيه"
        assert body["items"][0]["voided_by"] is not None

    def test_double_void_rejected(self, client: TestClient, db, fake_redis, cashier_headers, waiter_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()
        order_item_id = order["items"][0]["id"]

        client.patch(
            f"/api/v1/cafe/orders/{order['id']}/items/{order_item_id}/void",
            json={"reason": "الأول"},
            headers=cashier_headers,
        )
        resp = client.patch(
            f"/api/v1/cafe/orders/{order['id']}/items/{order_item_id}/void",
            json={"reason": "التاني"},
            headers=cashier_headers,
        )
        assert resp.status_code == 400

    def test_void_blocked_on_paid_order(self, client: TestClient, db, fake_redis, cashier_headers, waiter_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()
        order_item_id = order["items"][0]["id"]
        client.patch(f"/api/v1/cafe/orders/{order['id']}/status", json={"status": "paid"}, headers=cashier_headers)

        resp = client.patch(
            f"/api/v1/cafe/orders/{order['id']}/items/{order_item_id}/void",
            json={"reason": "بعد الدفع"},
            headers=cashier_headers,
        )
        assert resp.status_code == 400


class TestCafeExtras:
    """Mirrors the extras/modifiers coverage in test_restaurant_http.py —
    CafeMenuItemExtraGroup → CafeMenuItemExtra → CafeOrderItemExtra."""

    def test_create_order_with_extras_adds_price_addition(self, client: TestClient, db, fake_redis, manager_headers, waiter_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)

        group_resp = client.post(
            f"/api/v1/cafe/menu/items/{item.id}/extra-groups",
            json={
                "name": "إضافات", "min_select": 0, "max_select": 2,
                "options": [
                    {"name": "شوت اسبريسو", "price_addition": "10.00"},
                    {"name": "حليب نباتي", "price_addition": "5.00"},
                ],
            },
            headers=manager_headers,
        )
        assert group_resp.status_code == 201, group_resp.text
        option_ids = [o["id"] for o in group_resp.json()["options"]]

        resp = client.post(
            "/api/v1/cafe/orders",
            json={
                "branch_id": branch.id, "order_type": "takeaway",
                "items": [{"item_id": item.id, "quantity": 1, "extra_ids": option_ids}],
            },
            headers=waiter_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert Decimal(str(body["subtotal"])) == Decimal("60.00")
        assert len(body["items"][0]["extras"]) == 2

    def test_create_order_rejects_extra_below_min_select(self, client: TestClient, db, fake_redis, manager_headers, waiter_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)

        group_resp = client.post(
            f"/api/v1/cafe/menu/items/{item.id}/extra-groups",
            json={"name": "حجم", "min_select": 1, "max_select": 1, "options": [{"name": "كبير", "price_addition": "8.00"}]},
            headers=manager_headers,
        )
        assert group_resp.status_code == 201, group_resp.text

        resp = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1, "extra_ids": []}]},
            headers=waiter_headers,
        )
        assert resp.status_code == 400

    def test_create_order_rejects_extra_from_other_item(self, client: TestClient, db, fake_redis, manager_headers, waiter_headers):
        branch = make_branch_committed(db)
        item_a = make_item_committed(db, branch)
        item_b = make_item_committed(db, branch)

        group_resp = client.post(
            f"/api/v1/cafe/menu/items/{item_a.id}/extra-groups",
            json={"name": "إضافات أ", "min_select": 0, "max_select": 1, "options": [{"name": "إضافة أ", "price_addition": "5.00"}]},
            headers=manager_headers,
        )
        foreign_extra_id = group_resp.json()["options"][0]["id"]

        resp = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item_b.id, "quantity": 1, "extra_ids": [foreign_extra_id]}]},
            headers=waiter_headers,
        )
        assert resp.status_code == 400

    def test_item_with_no_extra_groups_rejects_extra_ids(self, client: TestClient, db, fake_redis, waiter_headers):
        """Bug-fix regression (mirrors restaurant): an item with zero
        extra_groups must still reject any extra_ids passed to it, not
        silently ignore them."""
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)

        resp = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1, "extra_ids": [9999]}]},
            headers=waiter_headers,
        )
        assert resp.status_code == 400


class TestCafeTableOccupancy:
    """Mirrors TestTableOccupancy in test_restaurant_http.py — cafe has its
    own dine-in tables (CafeTable), same occupied_at lifecycle."""

    def test_dine_in_order_stamps_occupied_at(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        table = make_table_committed(db, branch)

        client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "table_id": table.id, "order_type": "dine_in",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )

        resp = client.get("/api/v1/cafe/tables", params={"branch_id": branch.id}, headers=waiter_headers)
        found = next(t for t in resp.json() if t["id"] == table.id)
        assert found["status"] == "occupied"
        assert found["occupied_at"] is not None

    def test_paid_order_clears_occupied_at(self, client: TestClient, db, fake_redis, waiter_headers, cashier_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        table = make_table_committed(db, branch)

        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "table_id": table.id, "order_type": "dine_in",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()

        client.patch(f"/api/v1/cafe/orders/{order['id']}/status", json={"status": "paid"}, headers=cashier_headers)

        resp = client.get("/api/v1/cafe/tables", params={"branch_id": branch.id}, headers=waiter_headers)
        found = next(t for t in resp.json() if t["id"] == table.id)
        assert found["status"] == "available"
        assert found["occupied_at"] is None


class TestCafeInventoryDeduction:
    """Real gap found+fixed this session: CafeItem had no linked_product_id
    at all, so paying a cafe order never touched inventory (unlike restaurant's
    MenuItem.linked_product_id → _deduct_inventory_for_order)."""

    def test_paying_order_deducts_linked_stock(self, client: TestClient, db, fake_redis, waiter_headers, cashier_headers):
        from datetime import datetime as _dt
        from app.modules.inventory.models import Product, Warehouse
        from app.modules.inventory import services as inventory_services
        from app.modules.inventory.schemas import StockMovementCreate

        branch = make_branch_committed(db)
        warehouse = Warehouse(branch_id=branch.id, name="Cafe Store", code=f"CST-{uuid.uuid4().hex[:6].upper()}")
        db.add(warehouse)
        db.commit()

        product = Product(
            branch_id=branch.id, warehouse_id=warehouse.id, name="حبوب قهوة",
            sku=f"COF-{uuid.uuid4().hex[:6].upper()}", unit="kg",
            cost_price=Decimal("50.00"),
        )
        db.add(product)
        db.commit()

        # نجهّز رصيد أولي بحركة شراء
        inventory_services.record_movement(
            db,
            StockMovementCreate(
                branch_id=branch.id, product_id=product.id, warehouse_id=warehouse.id,
                movement_type="purchase_in", quantity=Decimal("10"), unit_cost=Decimal("50.00"),
                moved_at=_dt.utcnow(),
            ),
            moved_by=0,
        )

        from app.modules.cafe.models import CafeItem
        item = CafeItem(branch_id=branch.id, name="قهوة تركي", price=Decimal("30.00"),
                         is_available=True, linked_product_id=product.id)
        db.add(item)
        db.commit()

        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 3}]},
            headers=waiter_headers,
        ).json()

        resp = client.patch(f"/api/v1/cafe/orders/{order['id']}/status", json={"status": "paid"}, headers=cashier_headers)
        assert resp.status_code == 200, resp.text

        db.refresh(product)
        assert product.current_stock == Decimal("7.000")


class TestCafePublicMenu:
    """للموقع العام — بدون تسجيل دخول، نفس نمط restaurant/public/menu و pms/public/room-types."""

    def test_no_auth_required(self, client: TestClient, db, fake_redis):
        branch = make_branch_committed(db)
        category = make_category_committed(db, branch)
        item = make_item_committed(db, branch)
        item.category_id = category.id
        db.commit()

        resp = client.get("/api/v1/cafe/public/menu", params={"branch_id": branch.id})
        assert resp.status_code == 200
        body = resp.json()
        assert body["branch_id"] == branch.id
        assert len(body["categories"]) == 1
        assert body["categories"][0]["name_ar"] == "بيتزا"
        assert len(body["items"]) == 1
        assert body["items"][0]["name"] == "كابتشينو"
        assert Decimal(str(body["items"][0]["price"])) == Decimal("45.00")

    def test_excludes_unavailable_items(self, client: TestClient, db, fake_redis):
        from app.modules.cafe.models import CafeItem
        branch = make_branch_committed(db)
        available = make_item_committed(db, branch, available=True)
        unavailable = CafeItem(branch_id=branch.id, name="عصير خارج الخدمة",
                                price=Decimal("20.00"), is_available=False)
        db.add(unavailable)
        db.commit()

        resp = client.get("/api/v1/cafe/public/menu", params={"branch_id": branch.id})
        item_ids = [i["id"] for i in resp.json()["items"]]
        assert available.id in item_ids
        assert unavailable.id not in item_ids

    def test_empty_branch_returns_empty_lists(self, client: TestClient, db, fake_redis):
        branch = make_branch_committed(db)
        resp = client.get("/api/v1/cafe/public/menu", params={"branch_id": branch.id})
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["categories"] == []
