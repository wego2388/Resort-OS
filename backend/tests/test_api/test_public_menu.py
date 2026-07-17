"""
tests/test_api/test_public_menu.py
Public (Guest QR) endpoints — بدون auth

راجع DINING_CUTOVER_PLAN.md Batch 6 — بورتت لـ /dining/public/* بدل
/restaurant/public/* (فجوة تكافؤ حقيقية اتقفلت قبل حذف restaurant/cafe،
راجع dining/api/router.py's "Public Endpoints" docstring للتفاصيل الكاملة).

يتحقق من:
1. GET /dining/public/menu → 200 بدون token
2. POST /dining/public/orders → 201 بدون token (بعد تفعيل الطلب الذاتي
   صراحةً — مقفول افتراضيًا خلف بوابتين، راجع Gate 1 containment تحت)
3. GET /dining/public/orders/{id} → **مقفول تمامًا الآن (404 دايمًا)**،
   بغض النظر عن حالة الطلب الذاتي — راجع Codex round 3 (BOLA على طلبات
   POS/الكاشير عبر order_id متسلسل) وget_guest_order_status's docstring
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


def make_outlet(db, branch, name="مطعم QR"):
    from app.modules.dining import services as dining_services
    from app.modules.dining.schemas import OutletCreate
    return dining_services.create_outlet(db, OutletCreate(
        branch_id=branch.id, name=name, outlet_type="restaurant",
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


def enable_self_order(db, branch):
    """Gate 1 containment: الطلب الذاتي مقفول افتراضيًا خلف بوابتين معًا
    (جولة مراجعة Codex الثالثة) — settings.DINING_SELF_ORDER_ENABLED
    (typed، deployment-level) + core.Setting "dining.self_order_enabled"
    (الفرع). التستات اللي بتختبر مسار الطلب الفعلي (مش سلوك القفل نفسه)
    لازم تفعّل الاتنين صراحةً."""
    from app.core.config import settings
    from app.modules.core.crud import upsert_setting
    settings.DINING_SELF_ORDER_ENABLED = True
    upsert_setting(db, "dining.self_order_enabled", "true", branch_id=branch.id)
    db.commit()


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
        table    = make_table(db, branch, outlet)

        resp = client.get("/api/v1/dining/public/menu",
                          params={"outlet_id": outlet.id, "table_id": table.id})
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

    def test_public_menu_table_id_zero_returns_422_not_500(self, client: TestClient, db):
        """Gate 1 containment (جولة مراجعة Codex الثالثة): table_id=0 لازم
        يترفض 422 (Field(ge=1)) — مش يوصل لأي كود بيتعامل معاه كـ"مفيش
        طاولة" (truthiness bug) ولا يسبب 500."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        resp = client.get("/api/v1/dining/public/menu",
                          params={"outlet_id": outlet.id, "table_id": 0})
        assert resp.status_code == 422, resp.text

    def test_public_menu_unknown_outlet_returns_404(self, client: TestClient, db):
        resp = client.get("/api/v1/dining/public/menu", params={"outlet_id": 999999})
        assert resp.status_code == 404

    def test_public_menu_table_from_different_outlet_rejected(self, client: TestClient, db):
        """Gate 1 containment: table_id في الـQR لازم يتبع نفس outlet_id —
        فشل سريع وواضح لو الضيف مسح/خمّن مجموعة outlet/table غير متطابقة."""
        branch       = make_branch(db)
        outlet       = make_outlet(db, branch)
        other_outlet = make_outlet(db, branch, name="مطعم QR الآخر")
        foreign_table = make_table(db, branch, other_outlet)

        resp = client.get("/api/v1/dining/public/menu",
                          params={"outlet_id": outlet.id, "table_id": foreign_table.id})
        assert resp.status_code == 400

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
    def test_order_table_id_zero_returns_422_not_500(self, client: TestClient, db):
        """Gate 1 containment (جولة مراجعة Codex الثالثة): table_id=0 لازم
        يترفض 422 (Field(ge=1) على GuestOrderCreate/OrderCreate) — مش
        يتفهم كـ"مفيش طاولة" (كان ممكن يحصل ده مع truthiness check قديمة:
        `if data.table_id:` بتتجاهل 0 بدل ما تتحقق منه)، ولا يسبب 500."""
        branch = make_branch(db)
        enable_self_order(db, branch)
        outlet = make_outlet(db, branch)
        cat    = make_category(db, branch, outlet)
        item   = make_item(db, branch, outlet, cat)

        resp = client.post("/api/v1/dining/public/orders", json={
            "outlet_id": outlet.id,
            "table_id":  0,
            "items": [{"item_id": item.id, "quantity": 1}],
        })
        assert resp.status_code == 422, resp.text

    def test_self_order_disabled_by_default(self, client: TestClient, db):
        """Gate 1 containment (Decision 0001 / PRODUCTION_READINESS_AUDIT
        C-02): الطلب الذاتي غير المُشرَف عليه مقفول افتراضيًا — لا إعداد
        صريح = 400، مش 201. هذا هو السلوك الافتراضي الجديد؛ باقي تستات
        الكلاس دي بتفعّل الإعداد صراحةً عشان تختبر مسار الطلب نفسه."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        cat    = make_category(db, branch, outlet)
        item   = make_item(db, branch, outlet, cat)

        resp = client.post("/api/v1/dining/public/orders", json={
            "outlet_id": outlet.id,
            "items": [{"item_id": item.id, "quantity": 1}],
        })
        assert resp.status_code == 400, resp.text

    def test_table_from_different_outlet_rejected(self, client: TestClient, db):
        """Gate 1 containment: table_id لازم يتبع نفس outlet_id — منع ضيف
        يخمّن table_id تابع لمنفذ/فرع تاني تمامًا."""
        branch        = make_branch(db)
        enable_self_order(db, branch)
        outlet        = make_outlet(db, branch)
        other_outlet  = make_outlet(db, branch, name="مطعم QR الآخر")
        cat           = make_category(db, branch, outlet)
        item          = make_item(db, branch, outlet, cat)
        foreign_table = make_table(db, branch, other_outlet)

        resp = client.post("/api/v1/dining/public/orders", json={
            "outlet_id": outlet.id,
            "table_id":  foreign_table.id,
            "items": [{"item_id": item.id, "quantity": 1}],
        })
        assert resp.status_code == 400, resp.text

    def test_item_from_different_outlet_rejected(self, client: TestClient, db):
        """Gate 1 containment (جولة مراجعة Codex الثانية): item_id لازم
        يتبع نفس outlet_id — منع ضيف يطلب صنف من منفذ تاني (بنفس الفرع)
        عن طريق تمرير item_id مش تابع للـoutlet المُعلَن في الطلب."""
        branch = make_branch(db)
        enable_self_order(db, branch)
        outlet       = make_outlet(db, branch)
        other_outlet = make_outlet(db, branch, name="مطعم QR الآخر")
        cat          = make_category(db, branch, outlet)
        other_cat    = make_category(db, branch, other_outlet)
        foreign_item = make_item(db, branch, other_outlet, other_cat)

        resp = client.post("/api/v1/dining/public/orders", json={
            "outlet_id": outlet.id,
            "items": [{"item_id": foreign_item.id, "quantity": 1}],
        })
        assert resp.status_code == 400, resp.text

    def test_item_from_different_branch_rejected(self, client: TestClient, db):
        """Gate 1 containment (جولة مراجعة Codex الثانية): item_id لازم
        يتبع نفس branch_id — منع ضيف يطلب صنف من فرع مختلف تمامًا."""
        branch       = make_branch(db)
        other_branch = make_branch(db)
        enable_self_order(db, branch)
        outlet       = make_outlet(db, branch)
        other_outlet = make_outlet(db, other_branch)
        cat          = make_category(db, branch, outlet)
        other_cat    = make_category(db, other_branch, other_outlet)
        foreign_item = make_item(db, other_branch, other_outlet, other_cat)

        resp = client.post("/api/v1/dining/public/orders", json={
            "outlet_id": outlet.id,
            "items": [{"item_id": foreign_item.id, "quantity": 1}],
        })
        assert resp.status_code == 400, resp.text

    def test_create_guest_order_no_auth(self, client: TestClient, db):
        """POST /dining/public/orders يشتغل بدون token (بعد تفعيل الطلب
        الذاتي صراحةً — مقفول افتراضيًا، راجع test_self_order_disabled_by_default)."""
        branch = make_branch(db)
        enable_self_order(db, branch)
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
        enable_self_order(db, branch)
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
        enable_self_order(db, branch)
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
    def test_get_order_status_always_closed(self, client: TestClient, db):
        """Gate 1 containment (جولة مراجعة Codex الثالثة): الـendpoint ده
        مقفول تمامًا لحد Gate 8، بغض النظر عن dining.self_order_enabled —
        order_id رقم متسلسل قابل للتخمين بلا أي token، وبيقرا من نفس
        جدول الطلبات اللي فيه طلبات POS/الكاشير العادية كمان (ملهاش
        علاقة بالطلب الذاتي)، فتفعيل الطلب الذاتي لوحده مش كافي حماية."""
        branch = make_branch(db)
        enable_self_order(db, branch)
        outlet = make_outlet(db, branch)
        cat    = make_category(db, branch, outlet)
        item   = make_item(db, branch, outlet, cat)

        create_resp = client.post("/api/v1/dining/public/orders", json={
            "outlet_id": outlet.id,
            "items": [{"item_id": item.id, "quantity": 1}],
        })
        assert create_resp.status_code == 201, create_resp.text
        order_id = create_resp.json()["order_id"]

        resp = client.get(f"/api/v1/dining/public/orders/{order_id}")
        assert resp.status_code == 404, resp.text

    def test_get_nonexistent_order_returns_404(self, client: TestClient, db):
        """Order غير موجود (أو أي order_id تاني — الـendpoint مقفول
        بالكامل) → 404."""
        resp = client.get("/api/v1/dining/public/orders/999999")
        assert resp.status_code == 404

    def test_full_qr_flow_order_status_unavailable(self, client: TestClient, db):
        """
        Flow كامل — بس متابعة حالة الطلب بقت مقفولة عمدًا لحد Gate 8:
        1. اجلب القائمة بدون auth
        2. قدّم طلب بدون auth
        3. متابعة الحالة ترجع 404 (مش 200) — القفل مقصود، مش باج.
        """
        branch = make_branch(db)
        enable_self_order(db, branch)
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

        # Step 3: status polling مقفول عمدًا
        poll_resp = client.get(f"/api/v1/dining/public/orders/{order_id}")
        assert poll_resp.status_code == 404, poll_resp.text
