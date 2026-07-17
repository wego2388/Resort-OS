"""
tests/test_api/test_cafe_public_orders.py
Public (Guest QR) cafe-outlet ordering — بدون auth.

راجع DINING_CUTOVER_PLAN.md Batch 6 — بورتت لـ dining.Outlet(outlet_type='cafe')
عبر /dining/public/* بدل /cafe/public/* (نفس آلية test_public_menu.py's
restaurant-outlet coverage بالظبط، هنا بس للتأكيد إن outlet_type='cafe'
بيشتغل بنفس الـ endpoint الموحّد من غير أي كود خاص). قبل ده: GET
/cafe/public/menu كان موجود (read-only)، لكن مفيش أي endpoint حقيقي يسمح
للضيف بتقديم طلب فعلي من قائمة الكافيه عبر QR — الطلب كان مقصور على
get_waiter_user (POST /cafe/orders)، فاتضاف POST/GET /cafe/public/orders
بنفس نمط restaurant وقتها. dining.Outlet الموحّد ورّث نفس القدرة تلقائيًا.
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


def make_cafe_outlet(db, branch):
    from app.modules.dining import services as dining_services
    from app.modules.dining.schemas import OutletCreate
    return dining_services.create_outlet(db, OutletCreate(
        branch_id=branch.id, name="كافيه عام", outlet_type="cafe",
        revenue_account_code="4400",
    ))


def make_item(db, branch, outlet, available=True):
    from app.modules.dining.models import DiningItem
    item = DiningItem(branch_id=branch.id, outlet_id=outlet.id, name="كابتشينو",
                       price=Decimal("45.00"), is_available=available, station="bar")
    db.add(item)
    db.commit()
    return item


def make_table(db, branch, outlet):
    from app.modules.dining.models import VenueTable
    # اسم الطاولة هنا "شمسية 12" عمداً — الشمسيات ممثَّلة كصفوف VenueTable
    # عادية برقم مميز، مفيش موديل منفصل (راجع CLAUDE.md §13).
    table = VenueTable(branch_id=branch.id, outlet_id=outlet.id, table_number="شمسية 12",
                       capacity=2, status="available")
    db.add(table)
    db.commit()
    return table


def enable_self_order(db, branch):
    """Gate 1 containment: الطلب الذاتي مقفول افتراضيًا خلف بوابتين معًا —
    راجع نفس الدالة في test_public_menu.py."""
    from app.core.config import settings
    from app.modules.core.crud import upsert_setting
    settings.DINING_SELF_ORDER_ENABLED = True
    upsert_setting(db, "dining.self_order_enabled", "true", branch_id=branch.id)
    db.commit()


class TestCafePublicOrderEndpoint:
    def test_create_guest_order_no_auth(self, client: TestClient, db):
        """POST /dining/public/orders (outlet_type=cafe) يشتغل بدون token."""
        branch = make_branch(db)
        enable_self_order(db, branch)
        outlet = make_cafe_outlet(db, branch)
        item   = make_item(db, branch, outlet)
        table  = make_table(db, branch, outlet)

        payload = {
            "outlet_id": outlet.id,
            "table_id":  table.id,
            "items": [{"item_id": item.id, "quantity": 2}],
        }
        resp = client.post("/api/v1/dining/public/orders", json=payload)
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
        enable_self_order(db, branch)
        outlet = make_cafe_outlet(db, branch)
        item   = make_item(db, branch, outlet, available=False)

        resp = client.post("/api/v1/dining/public/orders", json={
            "outlet_id": outlet.id,
            "items": [{"item_id": item.id, "quantity": 1}],
        })
        assert resp.status_code == 400

    def test_internal_order_endpoint_still_requires_auth(self, client: TestClient, db):
        """الـ endpoint الداخلي (POST /dining/outlets/{id}/orders) لازم يفضل
        محمي بـ get_waiter_user."""
        branch = make_branch(db)
        outlet = make_cafe_outlet(db, branch)
        item   = make_item(db, branch, outlet)
        resp = client.post(f"/api/v1/dining/outlets/{outlet.id}/orders", json={
            "outlet_id": outlet.id,
            "items": [{"item_id": item.id, "quantity": 1}],
        })
        assert resp.status_code == 401


class TestCafePublicOrderStatusEndpoint:
    def test_full_qr_flow_sunbed_numbering(self, client: TestClient, db):
        """
        Flow كامل من شمسية (مش طاولة مطعم عادية) — يثبت إن نفس آلية
        الترقيم (table_number نصي حر) بتخدم طاولات الكافيه والشمسيات
        سوا من غير أي موديل/endpoint إضافي، على نفس الـ endpoint الموحّد.
        """
        branch = make_branch(db)
        enable_self_order(db, branch)
        outlet = make_cafe_outlet(db, branch)
        item   = make_item(db, branch, outlet)
        sunbed = make_table(db, branch, outlet)

        menu_resp = client.get("/api/v1/dining/public/menu", params={"outlet_id": outlet.id})
        assert menu_resp.status_code == 200
        menu = menu_resp.json()
        assert len(menu["items"]) >= 1

        order_resp = client.post("/api/v1/dining/public/orders", json={
            "outlet_id": outlet.id,
            "table_id":  sunbed.id,
            "items": [{"item_id": menu["items"][0]["id"], "quantity": 1}],
        })
        assert order_resp.status_code == 201
        order_id = order_resp.json()["order_id"]

        # Gate 1 containment (جولة مراجعة Codex الثالثة): متابعة حالة
        # الطلب مقفولة تمامًا لحد Gate 8 — راجع get_guest_order_status.
        poll_resp = client.get(f"/api/v1/dining/public/orders/{order_id}")
        assert poll_resp.status_code == 404, poll_resp.text
