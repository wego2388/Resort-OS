"""
tests/test_api/test_cafe_http.py
HTTP-level tests for the cafe module — TestClient through real routing,
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


def make_room_and_folio_committed(db, branch):
    """يعمل حجز حقيقي checked_in (booking → checkin_booking) — نفس نمط
    test_refund_after_payment_http.make_room_and_folio — عشان نختبر Charge-to-Room
    الحقيقي للكافيه (find_active_folio_for_room بيدوّر على Booking فعلي)."""
    from app.modules.pms.models import Room, RoomType
    from app.modules.pms import services as pms_services
    from app.modules.pms.schemas import BookingCreate

    rt = RoomType(branch_id=branch.id, name=f"RT-{uuid.uuid4().hex[:6]}", base_rate=Decimal("500.00"), max_occupancy=2)
    db.add(rt); db.flush()
    room = Room(branch_id=branch.id, room_type_id=rt.id, name=f"R-{uuid.uuid4().hex[:6].upper()}",
                floor=1, status="available")
    db.add(room); db.flush()

    booking = pms_services.create_booking(db, BookingCreate(
        branch_id=branch.id, guest_name="نزيل كافيه اختبار", guest_phone="01000000099",
        check_in=date.today(), check_out=date.today() + timedelta(days=2),
        adults=2, children=0, room_ids=[room.id],
    ))
    booking = pms_services.checkin_booking(db, booking.id)

    from app.modules.finance import crud as finance_crud
    folio = finance_crud.get_folio(db, booking.folio_id)
    return room, folio


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


class TestCafeReceiptPdf:
    """قبل الإصلاح: generate_receipt_pdf كانت بتستخدم receipt_pdf العادي (مقاس A4 كامل)،
    مش المناسب لطابعة رول حراري 80mm الحقيقية. اتصلحت لاستخدام receipt_pdf_thermal."""

    def test_receipt_pdf_is_thermal_sized_not_a4(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)

        order = client.post(
            "/api/v1/cafe/orders",
            json={
                "branch_id": branch.id, "order_type": "takeaway",
                "items": [{"item_id": item.id, "quantity": 2}],
            },
            headers=waiter_headers,
        ).json()

        resp = client.get(f"/api/v1/cafe/orders/{order['id']}/receipt", headers=waiter_headers)
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == "application/pdf"

        import re
        match = re.search(rb"/MediaBox\s*\[([^\]]+)\]", resp.content)
        assert match is not None
        media_box = [float(v) for v in match.group(1).split()]
        pdf_width = media_box[2] - media_box[0]
        assert pdf_width < 300, f"expected thermal-width PDF, got width={pdf_width}pt (A4 is ~595pt)"

    def test_receipt_404_for_missing_order(self, client: TestClient, db, fake_redis, waiter_headers):
        resp = client.get("/api/v1/cafe/orders/999999/receipt", headers=waiter_headers)
        assert resp.status_code == 404


class TestCafeCategoriesAndItems:
    """GET/POST /cafe/categories, GET/POST /cafe/items, PATCH /cafe/items/{id} —
    كانوا موجودين في router بس مش مغطيين بأي HTTP test."""

    def test_list_categories_returns_created(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db)
        make_category_committed(db, branch, name="Drinks", name_ar="مشروبات")

        resp = client.get("/api/v1/cafe/categories", params={"branch_id": branch.id}, headers=waiter_headers)
        assert resp.status_code == 200
        names = [c["name"] for c in resp.json()]
        assert "Drinks" in names

    def test_create_category_via_manager(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/cafe/categories",
            json={"branch_id": branch.id, "name": "Desserts", "name_ar": "حلويات", "sort_order": 2},
            headers=manager_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "Desserts"
        assert body["name_ar"] == "حلويات"
        assert body["is_active"] is True
        assert body["id"] is not None

    def test_list_items_filters_by_category(self, client: TestClient, db, fake_redis, waiter_headers):
        from app.modules.cafe.models import CafeItem
        branch = make_branch_committed(db)
        cat_a = make_category_committed(db, branch, name="A", name_ar="أ")
        cat_b = make_category_committed(db, branch, name="B", name_ar="ب")
        item_a = CafeItem(branch_id=branch.id, name="Item A", price=Decimal("10.00"), category_id=cat_a.id)
        item_b = CafeItem(branch_id=branch.id, name="Item B", price=Decimal("20.00"), category_id=cat_b.id)
        db.add_all([item_a, item_b]); db.commit()

        resp = client.get(
            "/api/v1/cafe/items", params={"branch_id": branch.id, "category_id": cat_a.id}, headers=waiter_headers,
        )
        assert resp.status_code == 200
        ids = [i["id"] for i in resp.json()]
        assert item_a.id in ids
        assert item_b.id not in ids

    def test_create_item_via_manager(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/cafe/items",
            json={"branch_id": branch.id, "name": "شاي أحمر", "price": "15.00"},
            headers=manager_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "شاي أحمر"
        assert Decimal(str(body["price"])) == Decimal("15.00")
        assert body["is_available"] is True

    def test_update_item_changes_price_and_availability(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)

        resp = client.patch(
            f"/api/v1/cafe/items/{item.id}",
            json={"price": "55.00", "is_available": False},
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert Decimal(str(body["price"])) == Decimal("55.00")
        assert body["is_available"] is False

        db.refresh(item)
        assert item.price == Decimal("55.00")
        assert item.is_available is False

    def test_update_item_404_for_missing_item(self, client: TestClient, db, fake_redis, manager_headers):
        resp = client.patch("/api/v1/cafe/items/999999", json={"price": "10.00"}, headers=manager_headers)
        assert resp.status_code == 404


class TestCafeExtraGroupManagement:
    """POST .../extra-groups (404 branch) + DELETE .../extra-groups/{id} — لا
    تست ليهم خالص قبل كده."""

    def test_create_extra_group_404_for_missing_item(self, client: TestClient, db, fake_redis, manager_headers):
        resp = client.post(
            "/api/v1/cafe/menu/items/999999/extra-groups",
            json={"name": "حجم", "options": []},
            headers=manager_headers,
        )
        assert resp.status_code == 404

    def test_delete_extra_group_success(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        group_resp = client.post(
            f"/api/v1/cafe/menu/items/{item.id}/extra-groups",
            json={"name": "حجم", "min_select": 0, "max_select": 1,
                  "options": [{"name": "كبير", "price_addition": "5.00"}]},
            headers=manager_headers,
        )
        group_id = group_resp.json()["id"]

        resp = client.delete(f"/api/v1/cafe/menu/extra-groups/{group_id}", headers=manager_headers)
        assert resp.status_code == 204

        from app.modules.cafe.models import CafeMenuItemExtraGroup
        assert db.query(CafeMenuItemExtraGroup).filter_by(id=group_id).first() is None

    def test_delete_extra_group_404_for_missing_group(self, client: TestClient, db, fake_redis, manager_headers):
        resp = client.delete("/api/v1/cafe/menu/extra-groups/999999", headers=manager_headers)
        assert resp.status_code == 404


class TestCafeOrderListAndDetail:
    """GET /cafe/orders (list+pagination+date filter) و GET /cafe/orders/{id} —
    مفيش تست واحد بيستدعيهم قبل كده."""

    def test_list_orders_paginated(self, client: TestClient, db, fake_redis, waiter_headers, cashier_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        for _ in range(3):
            client.post(
                "/api/v1/cafe/orders",
                json={"branch_id": branch.id, "order_type": "takeaway",
                      "items": [{"item_id": item.id, "quantity": 1}]},
                headers=waiter_headers,
            )

        resp = client.get(
            "/api/v1/cafe/orders", params={"branch_id": branch.id, "page": 1, "size": 2}, headers=cashier_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert len(body["items"]) == 2
        assert body["page"] == 1

    def test_list_orders_filters_by_date(self, client: TestClient, db, fake_redis, waiter_headers, cashier_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )

        today_resp = client.get(
            "/api/v1/cafe/orders",
            params={"branch_id": branch.id, "order_date": date.today().isoformat()},
            headers=cashier_headers,
        )
        assert today_resp.status_code == 200
        assert today_resp.json()["total"] >= 1

        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        tomorrow_resp = client.get(
            "/api/v1/cafe/orders", params={"branch_id": branch.id, "order_date": tomorrow}, headers=cashier_headers,
        )
        assert tomorrow_resp.json()["total"] == 0

    def test_get_order_by_id(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()

        resp = client.get(f"/api/v1/cafe/orders/{order['id']}", headers=waiter_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == order["id"]
        assert resp.json()["order_number"] == order["order_number"]

    def test_get_order_404(self, client: TestClient, db, fake_redis, waiter_headers):
        resp = client.get("/api/v1/cafe/orders/999999", headers=waiter_headers)
        assert resp.status_code == 404


class TestCafeOrderStatusEdgeCases:
    def test_hold_order_rejects_unavailable_item(self, client: TestClient, db, fake_redis, waiter_headers):
        """/cafe/orders/hold بيعدّي بنفس services.create_order — الـ except
        ValueError branch (400) مش مغطى قبل كده لأن كل تستات hold كانت happy-path."""
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch, available=False)
        resp = client.post(
            "/api/v1/cafe/orders/hold",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )
        assert resp.status_code == 400

    def test_status_update_rejected_after_cancelled(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()
        client.patch(f"/api/v1/cafe/orders/{order['id']}/status", json={"status": "cancelled"}, headers=waiter_headers)

        resp = client.patch(
            f"/api/v1/cafe/orders/{order['id']}/status", json={"status": "open"}, headers=waiter_headers,
        )
        assert resp.status_code == 400


class TestCafeExtraGroupBusinessRules:
    """_resolve_extras branches اللي مش مغطيين: أقصى اختيار (max_select) و
    إضافة is_available=False."""

    def test_order_rejects_extra_selection_above_max(self, client: TestClient, db, fake_redis, manager_headers, waiter_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        group_resp = client.post(
            f"/api/v1/cafe/menu/items/{item.id}/extra-groups",
            json={"name": "إضافات", "min_select": 0, "max_select": 1,
                  "options": [{"name": "أ", "price_addition": "5.00"}, {"name": "ب", "price_addition": "5.00"}]},
            headers=manager_headers,
        )
        option_ids = [o["id"] for o in group_resp.json()["options"]]

        resp = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1, "extra_ids": option_ids}]},
            headers=waiter_headers,
        )
        assert resp.status_code == 400
        assert "أقصى اختيار" in resp.json()["detail"]

    def test_order_rejects_unavailable_extra(self, client: TestClient, db, fake_redis, manager_headers, waiter_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        group_resp = client.post(
            f"/api/v1/cafe/menu/items/{item.id}/extra-groups",
            json={"name": "إضافات", "min_select": 0, "max_select": 1,
                  "options": [{"name": "غير متاح", "price_addition": "5.00", "is_available": False}]},
            headers=manager_headers,
        )
        option_id = group_resp.json()["options"][0]["id"]

        resp = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1, "extra_ids": [option_id]}]},
            headers=waiter_headers,
        )
        assert resp.status_code == 400
        assert "غير متاحة" in resp.json()["detail"]


class TestCafeTableValidation:
    """services.create_order بيتحقق من الطاولة (موجودة + مش out_of_service) —
    الفرعين دول مش مغطيين قبل كده."""

    def test_order_rejects_missing_table(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        resp = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "table_id": 999999, "order_type": "dine_in",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )
        assert resp.status_code == 400

    def test_order_rejects_out_of_service_table(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        table = make_table_committed(db, branch)
        table.status = "out_of_service"
        db.commit()

        resp = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "table_id": table.id, "order_type": "dine_in",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )
        assert resp.status_code == 400


class TestCafeCustomerVisitTracking:
    """services.update_order_status بيستدعي crm.record_customer_visit لو
    الطلب مربوط بـ customer_id — مفيش تست بيتأكد إن total_spent/visits_count
    فعلاً بيتحدّثوا."""

    def test_paying_order_updates_customer_stats(self, client: TestClient, db, fake_redis, waiter_headers, cashier_headers):
        from app.modules.crm.models import Customer
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        customer = Customer(branch_id=branch.id, full_name="عميل كافيه", phone="01012345678")
        db.add(customer); db.commit()

        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway", "customer_id": customer.id,
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()
        assert order["customer_id"] == customer.id

        resp = client.patch(f"/api/v1/cafe/orders/{order['id']}/status", json={"status": "paid"}, headers=cashier_headers)
        assert resp.status_code == 200, resp.text

        db.refresh(customer)
        assert customer.visits_count == 1
        assert customer.total_spent == Decimal(str(order["total"]))
        assert customer.last_visit is not None


class TestCafeInventoryDeductionEdgeCases:
    """يكمّل TestCafeInventoryDeduction — يغطي: صنف ملغي بيتخطّى الخصم (لكن
    صنف تاني فعّال في نفس الطلب لازم يتخصم عادي)، منتج من غير warehouse_id،
    ورصيد غير كافٍ بيفشل بصمت من غير ما يمنع الدفع."""

    def test_cancelled_item_skipped_active_item_still_deducted(
        self, client: TestClient, db, fake_redis, waiter_headers, cashier_headers,
    ):
        from datetime import datetime as _dt
        from app.modules.inventory.models import Product, Warehouse
        from app.modules.inventory import services as inventory_services
        from app.modules.inventory.schemas import StockMovementCreate
        from app.modules.cafe.models import CafeItem

        branch = make_branch_committed(db)
        warehouse = Warehouse(branch_id=branch.id, name="Cafe Store 2", code=f"CST2-{uuid.uuid4().hex[:6].upper()}")
        db.add(warehouse); db.commit()

        product_a = Product(branch_id=branch.id, warehouse_id=warehouse.id, name="حليب",
                             sku=f"MLK-{uuid.uuid4().hex[:6].upper()}", unit="l", cost_price=Decimal("10.00"))
        product_b = Product(branch_id=branch.id, warehouse_id=warehouse.id, name="بن",
                             sku=f"BN-{uuid.uuid4().hex[:6].upper()}", unit="kg", cost_price=Decimal("30.00"))
        db.add_all([product_a, product_b]); db.commit()
        for p in (product_a, product_b):
            inventory_services.record_movement(db, StockMovementCreate(
                branch_id=branch.id, product_id=p.id, warehouse_id=warehouse.id,
                movement_type="purchase_in", quantity=Decimal("10"), unit_cost=p.cost_price, moved_at=_dt.utcnow(),
            ), moved_by=0)

        item_a = CafeItem(branch_id=branch.id, name="لاتيه", price=Decimal("40.00"),
                           is_available=True, linked_product_id=product_a.id)
        item_b = CafeItem(branch_id=branch.id, name="إسبريسو", price=Decimal("30.00"),
                           is_available=True, linked_product_id=product_b.id)
        db.add_all([item_a, item_b]); db.commit()

        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item_a.id, "quantity": 2}, {"item_id": item_b.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()
        order_item_a_id = next(i["id"] for i in order["items"] if i["item_id"] == item_a.id)

        # نلغي صنف A قبل الدفع — لازم يتخطّى خصم المخزون بتاعه، وB يتخصم عادي
        client.patch(
            f"/api/v1/cafe/orders/{order['id']}/items/{order_item_a_id}/void",
            json={"reason": "العميل عدل رأيه"}, headers=cashier_headers,
        )

        resp = client.patch(f"/api/v1/cafe/orders/{order['id']}/status", json={"status": "paid"}, headers=cashier_headers)
        assert resp.status_code == 200, resp.text

        db.refresh(product_a); db.refresh(product_b)
        assert product_a.current_stock == Decimal("10.000"), "الصنف الملغي ميتخصمش من المخزون"
        assert product_b.current_stock == Decimal("9.000"), "الصنف الفعّال لازم يتخصم عادي"

    def test_item_linked_to_product_without_warehouse_is_skipped(
        self, client: TestClient, db, fake_redis, waiter_headers, cashier_headers,
    ):
        from app.modules.inventory.models import Product
        from app.modules.cafe.models import CafeItem

        branch = make_branch_committed(db)
        product = Product(branch_id=branch.id, warehouse_id=None, name="سكر",
                           sku=f"SGR-{uuid.uuid4().hex[:6].upper()}", unit="kg", cost_price=Decimal("5.00"))
        db.add(product); db.commit()
        linked_item = CafeItem(branch_id=branch.id, name="شاي بسكر", price=Decimal("20.00"),
                                is_available=True, linked_product_id=product.id)
        db.add(linked_item); db.commit()

        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": linked_item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()

        resp = client.patch(f"/api/v1/cafe/orders/{order['id']}/status", json={"status": "paid"}, headers=cashier_headers)
        assert resp.status_code == 200, resp.text  # لازم ينجح الدفع رغم عدم وجود warehouse للمنتج

        db.refresh(product)
        assert product.current_stock == Decimal("0.000")

    def test_insufficient_stock_does_not_block_payment(
        self, client: TestClient, db, fake_redis, waiter_headers, cashier_headers,
    ):
        from datetime import datetime as _dt
        from app.modules.inventory.models import Product, Warehouse
        from app.modules.inventory import services as inventory_services
        from app.modules.inventory.schemas import StockMovementCreate
        from app.modules.cafe.models import CafeItem

        branch = make_branch_committed(db)
        warehouse = Warehouse(branch_id=branch.id, name="Cafe Store 3", code=f"CST3-{uuid.uuid4().hex[:6].upper()}")
        db.add(warehouse); db.commit()
        product = Product(branch_id=branch.id, warehouse_id=warehouse.id, name="كريمة",
                           sku=f"CRM-{uuid.uuid4().hex[:6].upper()}", unit="l", cost_price=Decimal("20.00"))
        db.add(product); db.commit()
        inventory_services.record_movement(db, StockMovementCreate(
            branch_id=branch.id, product_id=product.id, warehouse_id=warehouse.id,
            movement_type="purchase_in", quantity=Decimal("1"), unit_cost=Decimal("20.00"), moved_at=_dt.utcnow(),
        ), moved_by=0)

        linked_item = CafeItem(branch_id=branch.id, name="كابتشينو كريمة", price=Decimal("35.00"),
                                is_available=True, linked_product_id=product.id)
        db.add(linked_item); db.commit()

        # نطلب 5 وحدات بينما الرصيد وحدة واحدة بس — consume_stock هيرمي
        # ValueError، لازم يتبلع (except Exception: continue) والدفع ينجح عادي.
        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": linked_item.id, "quantity": 5}]},
            headers=waiter_headers,
        ).json()

        resp = client.patch(f"/api/v1/cafe/orders/{order['id']}/status", json={"status": "paid"}, headers=cashier_headers)
        assert resp.status_code == 200, resp.text

        db.refresh(product)
        assert product.current_stock == Decimal("1.000"), "الخصم فشل فلازم الرصيد يفضل زي ما هو"


class TestCafeVoidRefundEdgeCases:
    def test_void_rejects_item_not_in_order(self, client: TestClient, db, fake_redis, waiter_headers, cashier_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        order_a = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()
        order_b = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()
        item_from_b = order_b["items"][0]["id"]

        resp = client.patch(
            f"/api/v1/cafe/orders/{order_a['id']}/items/{item_from_b}/void",
            json={"reason": "صنف من طلب تاني"},
            headers=cashier_headers,
        )
        assert resp.status_code == 400

    def test_void_recomputes_total_keeping_remaining_item_extras(
        self, client: TestClient, db, fake_redis, manager_headers, waiter_headers, cashier_headers,
    ):
        branch = make_branch_committed(db)
        item_plain = make_item_committed(db, branch)
        item_with_extra = make_item_committed(db, branch)

        group_resp = client.post(
            f"/api/v1/cafe/menu/items/{item_with_extra.id}/extra-groups",
            json={"name": "إضافات", "min_select": 0, "max_select": 1,
                  "options": [{"name": "شوكولاتة", "price_addition": "8.00"}]},
            headers=manager_headers,
        )
        option_id = group_resp.json()["options"][0]["id"]

        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [
                      {"item_id": item_plain.id, "quantity": 1},
                      {"item_id": item_with_extra.id, "quantity": 1, "extra_ids": [option_id]},
                  ]},
            headers=waiter_headers,
        ).json()
        plain_order_item_id = next(i["id"] for i in order["items"] if i["item_id"] == item_plain.id)
        # 45 (عادي) + (45 + 8) (مع إضافة) = 98
        assert Decimal(str(order["subtotal"])) == Decimal("98.00")

        resp = client.patch(
            f"/api/v1/cafe/orders/{order['id']}/items/{plain_order_item_id}/void",
            json={"reason": "الغاء صنف"},
            headers=cashier_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # المتبقي بس الصنف اللي معاه الإضافة: 45 + 8 = 53
        assert Decimal(str(body["subtotal"])) == Decimal("53.00")


class TestCafeRefundValidation:
    """services.refund_order_item بيرمي ValueError في 3 حالات (طلب مش مدفوع،
    صنف مش موجود، صنف مرتجع/ملغي بالفعل) — مفيش تست HTTP كافيه بيغطيهم، وهم
    كمان بيغطوا router.py refund's except ValueError branch (400)."""

    def test_refund_rejected_for_unpaid_order(self, client: TestClient, db, fake_redis, waiter_headers, manager_headers):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()
        item_id = order["items"][0]["id"]

        resp = client.patch(
            f"/api/v1/cafe/orders/{order['id']}/items/{item_id}/refund",
            json={"reason": "اختبار مرتجع قبل الدفع"},
            headers=manager_headers,
        )
        assert resp.status_code == 400

    def test_refund_rejects_item_not_in_order(
        self, client: TestClient, db, fake_redis, waiter_headers, cashier_headers, manager_headers,
    ):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()
        client.patch(f"/api/v1/cafe/orders/{order['id']}/status", json={"status": "paid"}, headers=cashier_headers)

        resp = client.patch(
            f"/api/v1/cafe/orders/{order['id']}/items/999999/refund",
            json={"reason": "صنف مش موجود"},
            headers=manager_headers,
        )
        assert resp.status_code == 400

    def test_double_refund_rejected(
        self, client: TestClient, db, fake_redis, waiter_headers, cashier_headers, manager_headers,
    ):
        """طلب بصنفين عشان أول مرتجع ميقفلش الطلب كله (order.status يفضل 'paid')
        — وبكده المحاولة التانية بترفض بسبب 'الصنف ده ملغي/مرتجع بالفعل' مش
        بسبب 'الطلب مش مدفوع'."""
        branch = make_branch_committed(db)
        item_a = make_item_committed(db, branch)
        item_b = make_item_committed(db, branch)
        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item_a.id, "quantity": 1}, {"item_id": item_b.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()
        paid = client.patch(
            f"/api/v1/cafe/orders/{order['id']}/status", json={"status": "paid"}, headers=cashier_headers,
        ).json()
        item_id = next(i["id"] for i in paid["items"] if i["item_id"] == item_a.id)

        first = client.patch(
            f"/api/v1/cafe/orders/{order['id']}/items/{item_id}/refund",
            json={"reason": "الأول"}, headers=manager_headers,
        )
        assert first.status_code == 200, first.text
        assert first.json()["status"] == "paid"  # لسه فيه صنف تاني فعّال (b)

        second = client.patch(
            f"/api/v1/cafe/orders/{order['id']}/items/{item_id}/refund",
            json={"reason": "التاني"}, headers=manager_headers,
        )
        assert second.status_code == 400


class TestCafeChargeToRoom:
    """update_order_status(status='paid', charge_to_room_id=...) — مفيش تست
    واحد بيغطي المسار ده للكافيه قبل كده (موجود بالفعل لـ restaurant/beach)."""

    def test_charge_to_room_without_active_folio_rejected(
        self, client: TestClient, db, fake_redis, waiter_headers, cashier_headers,
    ):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()

        resp = client.patch(
            f"/api/v1/cafe/orders/{order['id']}/status",
            json={"status": "paid", "charge_to_room_id": 999999},
            headers=cashier_headers,
        )
        assert resp.status_code == 400
        assert "مسجّل دخول" in resp.json()["detail"]

    def test_charge_to_room_posts_folio_charge_and_recalculates_total(
        self, client: TestClient, db, fake_redis, waiter_headers, cashier_headers,
    ):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        room, folio = make_room_and_folio_committed(db, branch)
        assert folio.total == Decimal("0.00")

        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 2}]},
            headers=waiter_headers,
        ).json()

        resp = client.patch(
            f"/api/v1/cafe/orders/{order['id']}/status",
            json={"status": "paid", "charge_to_room_id": room.id},
            headers=cashier_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "paid"

        db.refresh(folio)
        # ⚠️ باج حقيقي اتصلح في هذا الجلسة (services.py:213-215): add_charge لوحدها
        # كانت بتضيف FolioCharge بس من غير ما تحدّث Folio.total المخزّن — أي شاشة
        # بتعرض العمود ده مباشرة كانت بتوريه صفر رغم وجود شحنات فعلية.
        expected_total = Decimal(str(body["subtotal"])) + Decimal(str(body["vat_amount"]))
        assert folio.total == expected_total
        assert folio.total > Decimal("0.00")


class TestCafeRefundReducesFolioCharge:
    """services._reduce_folio_charge_for_refund — مفيش تست بيغطيه للكافيه
    (بس موجود لـ restaurant في test_refund_after_payment_http.py)."""

    def test_refund_after_charge_to_room_reduces_folio_total_to_zero(
        self, client: TestClient, db, fake_redis, waiter_headers, cashier_headers, manager_headers,
    ):
        branch = make_branch_committed(db)
        item = make_item_committed(db, branch)
        room, folio = make_room_and_folio_committed(db, branch)

        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()
        paid = client.patch(
            f"/api/v1/cafe/orders/{order['id']}/status",
            json={"status": "paid", "charge_to_room_id": room.id},
            headers=cashier_headers,
        ).json()
        item_id = paid["items"][0]["id"]

        db.refresh(folio)
        assert folio.total > Decimal("0.00")

        resp = client.patch(
            f"/api/v1/cafe/orders/{paid['id']}/items/{item_id}/refund",
            json={"reason": "مرتجع بعد تحميل الغرفة"},
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text

        db.refresh(folio)
        assert folio.total == Decimal("0.00")
