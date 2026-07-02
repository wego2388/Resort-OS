"""
tests/test_api/test_public_menu.py
Public (Guest QR) endpoints — بدون auth

يتحقق من:
1. GET /restaurant/public/menu → 200 بدون token
2. POST /restaurant/public/orders → 201 بدون token
3. GET /restaurant/public/orders/{id} → 200 بدون token
4. GET /restaurant/menu/items → 401 بدون token (internal endpoint مازال محمي)
5. POST /restaurant/public/orders → 400 لو item غير متاح
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient


def make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(name="QR Branch", name_ar="فرع QR",
               code=f"QR-{uuid.uuid4().hex[:6].upper()}")
    db.add(b)
    db.commit()
    return b


def make_category(db, branch):
    from app.modules.restaurant.models import MenuCategory
    cat = MenuCategory(branch_id=branch.id, name="مشويات", name_ar="مشويات")
    db.add(cat)
    db.commit()
    return cat


def make_item(db, branch, category, available=True):
    from app.modules.restaurant.models import MenuItem
    item = MenuItem(
        branch_id=branch.id,
        category_id=category.id,
        name="كباب",
        name_ar="كباب",
        price=Decimal("60.00"),
        is_available=available,
    )
    db.add(item)
    db.commit()
    return item


def make_table(db, branch):
    from app.modules.restaurant.models import DiningTable
    t = DiningTable(branch_id=branch.id, table_number="T5",
                    capacity=4, status="available")
    db.add(t)
    db.commit()
    return t


class TestPublicMenuEndpoint:
    def test_public_menu_no_auth_required(self, client: TestClient, db):
        """GET /restaurant/public/menu يشتغل بدون token."""
        branch = make_branch(db)
        resp = client.get("/api/v1/restaurant/public/menu",
                          params={"branch_id": branch.id})
        assert resp.status_code == 200

    def test_public_menu_returns_items(self, client: TestClient, db):
        """القائمة ترجع الأصناف المتاحة فقط مع categories."""
        branch   = make_branch(db)
        category = make_category(db, branch)
        item     = make_item(db, branch, category)

        resp = client.get("/api/v1/restaurant/public/menu",
                          params={"branch_id": branch.id, "table_id": 1})
        assert resp.status_code == 200

        data = resp.json()
        assert "categories" in data
        assert "items" in data
        assert data["branch_id"] == branch.id
        item_ids = [i["id"] for i in data["items"]]
        assert item.id in item_ids

    def test_public_menu_no_internal_fields(self, client: TestClient, db):
        """الـ cost و station مش موجودين في الـ public response."""
        branch   = make_branch(db)
        category = make_category(db, branch)
        make_item(db, branch, category)

        resp = client.get("/api/v1/restaurant/public/menu",
                          params={"branch_id": branch.id})
        items = resp.json()["items"]
        if items:
            assert "cost"    not in items[0]
            assert "station" not in items[0]

    def test_internal_menu_still_requires_auth(self, client: TestClient, db):
        """الـ internal endpoint لازم يفضل محمي — Public مش فتح كل حاجة."""
        branch = make_branch(db)
        resp = client.get("/api/v1/restaurant/menu/items",
                          params={"branch_id": branch.id})
        assert resp.status_code == 401


class TestPublicOrderEndpoint:
    def test_create_guest_order_no_auth(self, client: TestClient, db):
        """POST /restaurant/public/orders يشتغل بدون token."""
        branch = make_branch(db)
        cat    = make_category(db, branch)
        item   = make_item(db, branch, cat)
        table  = make_table(db, branch)

        payload = {
            "branch_id":    branch.id,
            "table_id":     table.id,
            "guests_count": 2,
            "items": [{"menu_item_id": item.id, "quantity": 1}],
        }
        resp = client.post("/api/v1/restaurant/public/orders", json=payload)
        assert resp.status_code == 201

        data = resp.json()
        assert "order_id"     in data
        assert "order_number" in data
        assert data["status"] in ("open", "in_kitchen", "held")
        assert data["items_count"] == 1
        assert data["message"]  # رسالة غير فارغة

    def test_create_guest_order_unavailable_item(self, client: TestClient, db):
        """صنف is_available=False → 400."""
        branch = make_branch(db)
        cat    = make_category(db, branch)
        item   = make_item(db, branch, cat, available=False)

        payload = {
            "branch_id": branch.id,
            "items": [{"menu_item_id": item.id, "quantity": 1}],
        }
        resp = client.post("/api/v1/restaurant/public/orders", json=payload)
        assert resp.status_code == 400

    def test_create_guest_order_empty_items_rejected(self, client: TestClient, db):
        """items فارغة → 422 Validation Error."""
        branch = make_branch(db)
        payload = {"branch_id": branch.id, "items": []}
        resp = client.post("/api/v1/restaurant/public/orders", json=payload)
        assert resp.status_code == 422

    def test_create_guest_order_without_table(self, client: TestClient, db):
        """table_id=None مسموح (takeaway من الـ lobby مثلاً)."""
        branch = make_branch(db)
        cat    = make_category(db, branch)
        item   = make_item(db, branch, cat)

        payload = {
            "branch_id": branch.id,
            "table_id":  None,
            "items": [{"menu_item_id": item.id, "quantity": 2}],
        }
        resp = client.post("/api/v1/restaurant/public/orders", json=payload)
        assert resp.status_code == 201
        assert resp.json()["items_count"] == 2


class TestPublicOrderStatusEndpoint:
    def test_get_order_status_no_auth(self, client: TestClient, db):
        """GET /restaurant/public/orders/{id} يشتغل بدون token."""
        branch = make_branch(db)
        cat    = make_category(db, branch)
        item   = make_item(db, branch, cat)

        create_resp = client.post("/api/v1/restaurant/public/orders", json={
            "branch_id": branch.id,
            "items": [{"menu_item_id": item.id, "quantity": 2}],
        })
        assert create_resp.status_code == 201
        order_id = create_resp.json()["order_id"]

        status_resp = client.get(f"/api/v1/restaurant/public/orders/{order_id}")
        assert status_resp.status_code == 200

        data = status_resp.json()
        assert data["order_id"]    == order_id
        assert data["items_count"] == 2
        assert "message" in data
        assert "total"   in data
        # لا يوجد waiter_id أو بيانات داخلية
        assert "waiter_id"  not in data
        assert "branch_id"  not in data

    def test_get_nonexistent_order_returns_404(self, client: TestClient, db):
        """Order غير موجود → 404."""
        resp = client.get("/api/v1/restaurant/public/orders/999999")
        assert resp.status_code == 404

    def test_full_qr_flow(self, client: TestClient, db):
        """
        Flow كامل:
        1. اجلب القائمة بدون auth
        2. قدّم طلب بدون auth
        3. تابع حالة الطلب بدون auth
        """
        branch = make_branch(db)
        cat    = make_category(db, branch)
        item   = make_item(db, branch, cat)
        table  = make_table(db, branch)

        # Step 1: fetch menu
        menu_resp = client.get("/api/v1/restaurant/public/menu",
                               params={"branch_id": branch.id, "table_id": table.id})
        assert menu_resp.status_code == 200
        menu = menu_resp.json()
        assert len(menu["items"]) >= 1

        # Step 2: place order
        order_resp = client.post("/api/v1/restaurant/public/orders", json={
            "branch_id": branch.id,
            "table_id":  table.id,
            "items": [{"menu_item_id": menu["items"][0]["id"], "quantity": 1}],
        })
        assert order_resp.status_code == 201
        order_id = order_resp.json()["order_id"]

        # Step 3: poll status
        poll_resp = client.get(f"/api/v1/restaurant/public/orders/{order_id}")
        assert poll_resp.status_code == 200
        assert poll_resp.json()["order_id"] == order_id
