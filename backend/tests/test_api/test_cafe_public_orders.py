"""
tests/test_api/test_cafe_public_orders.py
Public (Guest QR) cafe ordering endpoints — بدون auth.

قبل ده: GET /cafe/public/menu كان موجود (read-only)، لكن مفيش أي endpoint
حقيقي يسمح للضيف بتقديم طلب فعلي من قائمة الكافيه عبر QR — الطلب كان
مقصور على get_waiter_user (POST /cafe/orders). ده كان بيمنع فعليًا سيناريو
"الضيف بيمسح QR طاولة كافيه/شمسية ويطلب" اللي restaurant بيدعمه بالفعل
عبر /restaurant/public/orders. هذا الملف بيتأكد من الـ endpoint الجديد
(POST /cafe/public/orders + GET /cafe/public/orders/{id}) بنفس نمط
tests/test_api/test_public_menu.py.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient


def make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(name="Cafe Public Branch", name_ar="فرع كافيه عام",
               code=f"CAFPUB-{uuid.uuid4().hex[:6].upper()}")
    db.add(b)
    db.commit()
    return b


def make_item(db, branch, available=True):
    from app.modules.cafe.models import CafeItem
    item = CafeItem(branch_id=branch.id, name="كابتشينو", price=Decimal("45.00"), is_available=available)
    db.add(item)
    db.commit()
    return item


def make_table(db, branch):
    from app.modules.cafe.models import CafeTable
    # اسم الطاولة هنا "شمسية 12" عمداً — الشمسيات ممثَّلة كصفوف CafeTable
    # عادية برقم مميز، مفيش موديل منفصل (راجع CLAUDE.md §13).
    table = CafeTable(branch_id=branch.id, table_number="شمسية 12", capacity=2, status="available")
    db.add(table)
    db.commit()
    return table


class TestCafePublicOrderEndpoint:
    def test_create_guest_order_no_auth(self, client: TestClient, db):
        """POST /cafe/public/orders يشتغل بدون token."""
        branch = make_branch(db)
        item   = make_item(db, branch)
        table  = make_table(db, branch)

        payload = {
            "branch_id": branch.id,
            "table_id":  table.id,
            "items": [{"item_id": item.id, "quantity": 2}],
        }
        resp = client.post("/api/v1/cafe/public/orders", json=payload)
        assert resp.status_code == 201

        data = resp.json()
        assert "order_id"     in data
        assert "order_number" in data
        assert data["status"] in ("open", "in_kitchen", "held")
        assert data["items_count"] == 2
        assert data["message"]

    def test_create_guest_order_unavailable_item(self, client: TestClient, db):
        """صنف is_available=False → 400."""
        branch = make_branch(db)
        item   = make_item(db, branch, available=False)

        resp = client.post("/api/v1/cafe/public/orders", json={
            "branch_id": branch.id,
            "items": [{"item_id": item.id, "quantity": 1}],
        })
        assert resp.status_code == 400

    def test_create_guest_order_empty_items_rejected(self, client: TestClient, db):
        """items فارغة → 422 Validation Error."""
        branch = make_branch(db)
        resp = client.post("/api/v1/cafe/public/orders", json={"branch_id": branch.id, "items": []})
        assert resp.status_code == 422

    def test_create_guest_order_without_table(self, client: TestClient, db):
        """table_id=None مسموح (takeaway)."""
        branch = make_branch(db)
        item   = make_item(db, branch)

        resp = client.post("/api/v1/cafe/public/orders", json={
            "branch_id": branch.id,
            "table_id":  None,
            "items": [{"item_id": item.id, "quantity": 1}],
        })
        assert resp.status_code == 201
        assert resp.json()["items_count"] == 1

    def test_internal_order_endpoint_still_requires_auth(self, client: TestClient, db):
        """الـ endpoint الداخلي (POST /cafe/orders) لازم يفضل محمي بـ get_waiter_user."""
        branch = make_branch(db)
        item   = make_item(db, branch)
        resp = client.post("/api/v1/cafe/orders", json={
            "branch_id": branch.id,
            "items": [{"item_id": item.id, "quantity": 1}],
        })
        assert resp.status_code == 401


class TestCafePublicOrderStatusEndpoint:
    def test_get_order_status_no_auth(self, client: TestClient, db):
        """GET /cafe/public/orders/{id} يشتغل بدون token."""
        branch = make_branch(db)
        item   = make_item(db, branch)

        create_resp = client.post("/api/v1/cafe/public/orders", json={
            "branch_id": branch.id,
            "items": [{"item_id": item.id, "quantity": 3}],
        })
        assert create_resp.status_code == 201
        order_id = create_resp.json()["order_id"]

        status_resp = client.get(f"/api/v1/cafe/public/orders/{order_id}")
        assert status_resp.status_code == 200

        data = status_resp.json()
        assert data["order_id"]    == order_id
        assert data["items_count"] == 3
        assert "message" in data
        assert "total"   in data
        assert "waiter_id" not in data
        assert "branch_id"  not in data

    def test_get_nonexistent_order_returns_404(self, client: TestClient, db):
        resp = client.get("/api/v1/cafe/public/orders/999999")
        assert resp.status_code == 404

    def test_full_qr_flow_sunbed_numbering(self, client: TestClient, db):
        """
        Flow كامل من شمسية (مش طاولة مطعم عادية) — يثبت إن نفس آلية
        الترقيم (table_number نصي حر) بتخدم طاولات الكافيه والشمسيات
        سوا من غير أي موديل/endpoint إضافي.
        """
        branch = make_branch(db)
        item   = make_item(db, branch)
        sunbed = make_table(db, branch)

        menu_resp = client.get("/api/v1/cafe/public/menu", params={"branch_id": branch.id})
        assert menu_resp.status_code == 200
        menu = menu_resp.json()
        assert len(menu["items"]) >= 1

        order_resp = client.post("/api/v1/cafe/public/orders", json={
            "branch_id": branch.id,
            "table_id":  sunbed.id,
            "items": [{"item_id": menu["items"][0]["id"], "quantity": 1}],
        })
        assert order_resp.status_code == 201
        order_id = order_resp.json()["order_id"]

        poll_resp = client.get(f"/api/v1/cafe/public/orders/{order_id}")
        assert poll_resp.status_code == 200
        assert poll_resp.json()["order_id"] == order_id
