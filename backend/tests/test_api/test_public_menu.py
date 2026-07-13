"""
tests/test_api/test_public_menu.py
Public (Guest QR) endpoints — بدون auth

راجع DINING_CUTOVER_PLAN.md Batch 6 — بورتت لـ /dining/public/* بدل
/restaurant/public/* (فجوة تكافؤ حقيقية اتقفلت قبل حذف restaurant/cafe،
راجع dining/api/router.py's "Public Endpoints" docstring للتفاصيل الكاملة).

يتحقق من:
1. GET /dining/public/menu → 200 بدون token
2. POST /dining/public/orders → 201 بدون token
3. GET /dining/public/orders/{id} → 200 بدون token
4. GET /dining/outlets/{id}/items → 401 بدون token (internal endpoint مازال محمي)
5. POST /dining/public/orders → 400 لو item غير متاح
6. GET /dining/public/outlets → 200 بدون token (Batch 6 frontend: موقع الحجز
   العام apps/public's DiningView.vue محتاجها تعرف outlet_id لكل منفذ قبل
   ما تنادي /dining/public/menu — راجع docstring PublicOutletRead)
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


def make_outlet(db, branch):
    from app.modules.dining import services as dining_services
    from app.modules.dining.schemas import OutletCreate
    return dining_services.create_outlet(db, OutletCreate(
        branch_id=branch.id, name="مطعم QR", outlet_type="restaurant",
        revenue_account_code="4200",
    ))


def make_category(db, branch, outlet):
    from app.modules.dining.models import DiningCategory
    cat = DiningCategory(branch_id=branch.id, outlet_id=outlet.id, name="مشويات", name_ar="مشويات")
    db.add(cat)
    db.commit()
    return cat


def make_item(db, branch, outlet, category, available=True):
    from app.modules.dining.models import DiningItem
    item = DiningItem(
        branch_id=branch.id,
        outlet_id=outlet.id,
        category_id=category.id,
        name="كباب",
        name_ar="كباب",
        price=Decimal("60.00"),
        is_available=available,
    )
    db.add(item)
    db.commit()
    return item


def make_table(db, branch, outlet):
    from app.modules.dining.models import VenueTable
    t = VenueTable(branch_id=branch.id, outlet_id=outlet.id, table_number="T5",
                   capacity=4, status="available")
    db.add(t)
    db.commit()
    return t


class TestPublicMenuEndpoint:
    def test_public_menu_no_auth_required(self, client: TestClient, db):
        """GET /dining/public/menu يشتغل بدون token."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        resp = client.get("/api/v1/dining/public/menu",
                          params={"outlet_id": outlet.id})
        assert resp.status_code == 200

    def test_public_menu_returns_items(self, client: TestClient, db):
        """القائمة ترجع الأصناف المتاحة فقط مع categories."""
        branch   = make_branch(db)
        outlet   = make_outlet(db, branch)
        category = make_category(db, branch, outlet)
        item     = make_item(db, branch, outlet, category)

        resp = client.get("/api/v1/dining/public/menu",
                          params={"outlet_id": outlet.id, "table_id": 1})
        assert resp.status_code == 200

        data = resp.json()
        assert "categories" in data
        assert "items" in data
        assert data["branch_id"] == branch.id
        assert data["outlet_id"] == outlet.id
        item_ids = [i["id"] for i in data["items"]]
        assert item.id in item_ids

    def test_public_menu_no_internal_fields(self, client: TestClient, db):
        """الـ cost و station مش موجودين في الـ public response."""
        branch   = make_branch(db)
        outlet   = make_outlet(db, branch)
        category = make_category(db, branch, outlet)
        make_item(db, branch, outlet, category)

        resp = client.get("/api/v1/dining/public/menu",
                          params={"outlet_id": outlet.id})
        items = resp.json()["items"]
        if items:
            assert "cost"    not in items[0]
            assert "station" not in items[0]

    def test_public_menu_unknown_outlet_returns_404(self, client: TestClient, db):
        resp = client.get("/api/v1/dining/public/menu", params={"outlet_id": 999999})
        assert resp.status_code == 404

    def test_internal_menu_still_requires_auth(self, client: TestClient, db):
        """الـ internal endpoint لازم يفضل محمي — Public مش فتح كل حاجة."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        resp = client.get(f"/api/v1/dining/outlets/{outlet.id}/items")
        assert resp.status_code == 401


class TestPublicOutletsEndpoint:
    def test_no_auth_required(self, client: TestClient, db):
        branch = make_branch(db)
        make_outlet(db, branch)
        resp = client.get("/api/v1/dining/public/outlets", params={"branch_id": branch.id})
        assert resp.status_code == 200

    def test_returns_active_outlets_with_minimal_fields(self, client: TestClient, db):
        """id/name/name_ar/outlet_type بس — بدون revenue_account_code أو أي
        بيانات داخلية (راجع docstring PublicOutletRead)."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)

        resp = client.get("/api/v1/dining/public/outlets", params={"branch_id": branch.id})
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == outlet.id
        assert data[0]["outlet_type"] == "restaurant"
        assert "revenue_account_code" not in data[0]
        assert "branch_id" not in data[0]

    def test_excludes_inactive_outlets(self, client: TestClient, db):
        from app.modules.dining import services as dining_services
        from app.modules.dining.schemas import OutletUpdate

        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        dining_services.update_outlet(db, outlet.id, OutletUpdate(is_active=False))

        resp = client.get("/api/v1/dining/public/outlets", params={"branch_id": branch.id})
        assert resp.json() == []

    def test_scoped_to_branch_id(self, client: TestClient, db):
        branch_a = make_branch(db)
        branch_b = make_branch(db)
        make_outlet(db, branch_a)
        make_outlet(db, branch_b)

        resp = client.get("/api/v1/dining/public/outlets", params={"branch_id": branch_a.id})
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] != 0


class TestPublicOrderEndpoint:
    def test_create_guest_order_no_auth(self, client: TestClient, db):
        """POST /dining/public/orders يشتغل بدون token."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        cat    = make_category(db, branch, outlet)
        item   = make_item(db, branch, outlet, cat)
        table  = make_table(db, branch, outlet)

        payload = {
            "outlet_id":    outlet.id,
            "table_id":     table.id,
            "guests_count": 2,
            "items": [{"item_id": item.id, "quantity": 1}],
        }
        resp = client.post("/api/v1/dining/public/orders", json=payload)
        assert resp.status_code == 201, resp.text

        data = resp.json()
        assert "order_id"     in data
        assert "order_number" in data
        assert data["status"] in ("open", "in_kitchen", "held")
        assert data["items_count"] == 1
        assert data["message"]  # رسالة غير فارغة

    def test_create_guest_order_unavailable_item(self, client: TestClient, db):
        """صنف is_available=False → 400."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        cat    = make_category(db, branch, outlet)
        item   = make_item(db, branch, outlet, cat, available=False)

        payload = {
            "outlet_id": outlet.id,
            "items": [{"item_id": item.id, "quantity": 1}],
        }
        resp = client.post("/api/v1/dining/public/orders", json=payload)
        assert resp.status_code == 400

    def test_create_guest_order_empty_items_rejected(self, client: TestClient, db):
        """items فارغة → 422 Validation Error."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        payload = {"outlet_id": outlet.id, "items": []}
        resp = client.post("/api/v1/dining/public/orders", json=payload)
        assert resp.status_code == 422

    def test_create_guest_order_without_table(self, client: TestClient, db):
        """table_id=None مسموح (takeaway من الـ lobby مثلاً)."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        cat    = make_category(db, branch, outlet)
        item   = make_item(db, branch, outlet, cat)

        payload = {
            "outlet_id": outlet.id,
            "table_id":  None,
            "items": [{"item_id": item.id, "quantity": 2}],
        }
        resp = client.post("/api/v1/dining/public/orders", json=payload)
        assert resp.status_code == 201
        assert resp.json()["items_count"] == 2

    def test_create_guest_order_unknown_outlet_returns_404(self, client: TestClient, db):
        resp = client.post("/api/v1/dining/public/orders", json={
            "outlet_id": 999999, "items": [{"item_id": 1, "quantity": 1}],
        })
        assert resp.status_code == 404


class TestPublicOrderStatusEndpoint:
    def test_get_order_status_no_auth(self, client: TestClient, db):
        """GET /dining/public/orders/{id} يشتغل بدون token."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        cat    = make_category(db, branch, outlet)
        item   = make_item(db, branch, outlet, cat)

        create_resp = client.post("/api/v1/dining/public/orders", json={
            "outlet_id": outlet.id,
            "items": [{"item_id": item.id, "quantity": 2}],
        })
        assert create_resp.status_code == 201
        order_id = create_resp.json()["order_id"]

        status_resp = client.get(f"/api/v1/dining/public/orders/{order_id}")
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
        resp = client.get("/api/v1/dining/public/orders/999999")
        assert resp.status_code == 404

    def test_full_qr_flow(self, client: TestClient, db):
        """
        Flow كامل:
        1. اجلب القائمة بدون auth
        2. قدّم طلب بدون auth
        3. تابع حالة الطلب بدون auth
        """
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        cat    = make_category(db, branch, outlet)
        item   = make_item(db, branch, outlet, cat)
        table  = make_table(db, branch, outlet)

        # Step 1: fetch menu
        menu_resp = client.get("/api/v1/dining/public/menu",
                               params={"outlet_id": outlet.id, "table_id": table.id})
        assert menu_resp.status_code == 200
        menu = menu_resp.json()
        assert len(menu["items"]) >= 1

        # Step 2: place order
        order_resp = client.post("/api/v1/dining/public/orders", json={
            "outlet_id": outlet.id,
            "table_id":  table.id,
            "items": [{"item_id": menu["items"][0]["id"], "quantity": 1}],
        })
        assert order_resp.status_code == 201
        order_id = order_resp.json()["order_id"]

        # Step 3: poll status
        poll_resp = client.get(f"/api/v1/dining/public/orders/{order_id}")
        assert poll_resp.status_code == 200
        assert poll_resp.json()["order_id"] == order_id
