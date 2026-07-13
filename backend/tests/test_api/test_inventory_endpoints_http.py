"""
tests/test_api/test_inventory_endpoints_http.py
HTTP-level tests for inventory router endpoints not already covered by
test_inventory_http.py (purchase-order receive flow, permission gates,
validation): warehouses, categories, products list/get/update, barcode
labels, movements, purchase-requests full workflow, and stock counts.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="Inventory Endpoints Branch", name_ar="فرع مخزون",
               code=f"INVE-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def create_product(client: TestClient, branch_id: int, headers: dict, **overrides) -> dict:
    payload = {
        "branch_id": branch_id, "name": "منتج اختبار", "sku": f"SKU-{uuid.uuid4().hex[:8]}",
        "unit": "kg", "cost_price": "10.00",
    }
    payload.update(overrides)
    resp = client.post("/api/v1/inventory/products", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestWarehousesAndCategories:
    def test_create_and_list_warehouse(self, client: TestClient, db, manager_headers, waiter_headers):
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/inventory/warehouses",
            json={"branch_id": branch.id, "name": "المخزن الرئيسي", "code": f"WH-{uuid.uuid4().hex[:6]}"},
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text

        list_resp = client.get("/api/v1/inventory/warehouses", params={"branch_id": branch.id}, headers=waiter_headers)
        assert list_resp.status_code == 200
        assert any(w["id"] == create_resp.json()["id"] for w in list_resp.json())

    def test_create_warehouse_requires_manager(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/inventory/warehouses",
            json={"branch_id": branch.id, "name": "مخزن", "code": "WH-X"},
            headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_create_and_list_category(self, client: TestClient, db, manager_headers, waiter_headers):
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/inventory/categories",
            json={"branch_id": branch.id, "name": "مشروبات"},
            headers=manager_headers,
        )
        assert create_resp.status_code == 201

        list_resp = client.get("/api/v1/inventory/categories", params={"branch_id": branch.id}, headers=waiter_headers)
        assert any(c["id"] == create_resp.json()["id"] for c in list_resp.json())


class TestProductsEndpoints:
    def test_get_and_update_product(self, client: TestClient, db, manager_headers, waiter_headers):
        branch = make_branch_committed(db)
        product = create_product(client, branch.id, manager_headers, name="أرز")

        get_resp = client.get(f"/api/v1/inventory/products/{product['id']}", headers=waiter_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "أرز"

        update_resp = client.patch(
            f"/api/v1/inventory/products/{product['id']}", json={"cost_price": "15.00"}, headers=manager_headers,
        )
        assert update_resp.status_code == 200
        assert Decimal(str(update_resp.json()["cost_price"])) == Decimal("15.00")

    def test_get_missing_product_404(self, client: TestClient, waiter_headers):
        resp = client.get("/api/v1/inventory/products/999999999", headers=waiter_headers)
        assert resp.status_code == 404

    def test_list_filters_low_stock_only(self, client: TestClient, db, manager_headers):
        # ProductCreate مفيهوش current_stock (بيتحدد بس عن طريق stock movements) —
        # فبنحدد current_stock مباشرة على الصف بعد الإنشاء عشان نتحكم في السيناريو.
        from app.modules.inventory.models import Product
        branch = make_branch_committed(db)
        low = create_product(client, branch.id, manager_headers, name="نافد", reorder_point="10")
        ok = create_product(client, branch.id, manager_headers, name="متاح", reorder_point="10")
        db.query(Product).filter(Product.id == low["id"]).update({"current_stock": Decimal("0")})
        db.query(Product).filter(Product.id == ok["id"]).update({"current_stock": Decimal("100")})
        db.commit()

        resp = client.get(
            "/api/v1/inventory/products", params={"branch_id": branch.id, "low_stock_only": True}, headers=manager_headers,
        )
        names = [p["name"] for p in resp.json()["items"]]
        assert "نافد" in names
        assert "متاح" not in names

    def test_barcode_labels_pdf(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        product = create_product(client, branch.id, manager_headers)
        resp = client.get(
            "/api/v1/inventory/products/barcode-labels",
            params={"branch_id": branch.id, "product_ids": str(product["id"])},
            headers=manager_headers,
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"

    def test_barcode_labels_rejects_non_numeric_ids(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/inventory/products/barcode-labels",
            params={"branch_id": branch.id, "product_ids": "abc,def"},
            headers=manager_headers,
        )
        assert resp.status_code == 400


class TestMovementsEndpoint:
    def test_record_and_list_movement(self, client: TestClient, db, manager_headers):
        from datetime import datetime
        branch = make_branch_committed(db)
        product = create_product(client, branch.id, manager_headers)
        warehouse = client.post(
            "/api/v1/inventory/warehouses",
            json={"branch_id": branch.id, "name": "مخزن الحركات", "code": f"WH-{uuid.uuid4().hex[:6]}"},
            headers=manager_headers,
        ).json()

        create_resp = client.post(
            "/api/v1/inventory/movements",
            json={
                "branch_id": branch.id, "product_id": product["id"], "warehouse_id": warehouse["id"],
                "movement_type": "purchase_in", "quantity": "50", "unit_cost": "10.00",
                "moved_at": datetime.utcnow().isoformat(),
            },
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text

        list_resp = client.get(
            "/api/v1/inventory/movements", params={"branch_id": branch.id, "product_id": product["id"]},
            headers=manager_headers,
        )
        assert list_resp.json()["total"] == 1


class TestPurchaseRequestWorkflow:
    def test_full_lifecycle_create_approve_convert(self, client: TestClient, db, waiter_headers, manager_headers):
        branch = make_branch_committed(db)
        product = create_product(client, branch.id, manager_headers)

        create_resp = client.post(
            "/api/v1/inventory/purchase-requests",
            json={
                "branch_id": branch.id, "requester_id": 1, "department": "المطبخ",
                "items": [{"product_id": product["id"], "quantity_requested": "20", "unit": "kg", "estimated_unit_cost": "10.00"}],
            },
            headers=waiter_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        pr = create_resp.json()

        list_resp = client.get("/api/v1/inventory/purchase-requests", params={"branch_id": branch.id}, headers=waiter_headers)
        assert any(r["id"] == pr["id"] for r in list_resp.json()["items"])

        get_resp = client.get(f"/api/v1/inventory/purchase-requests/{pr['id']}", headers=waiter_headers)
        assert get_resp.status_code == 200

        approve_dept = client.patch(
            f"/api/v1/inventory/purchase-requests/{pr['id']}/approve",
            json={"level": "dept"}, headers=manager_headers,
        )
        assert approve_dept.status_code == 200, approve_dept.text

        approve_fin = client.patch(
            f"/api/v1/inventory/purchase-requests/{pr['id']}/approve",
            json={"level": "finance"}, headers=manager_headers,
        )
        assert approve_fin.status_code == 200, approve_fin.text
        assert approve_fin.json()["status"] == "finance_approved"

        convert_resp = client.post(f"/api/v1/inventory/purchase-requests/{pr['id']}/convert", headers=manager_headers)
        assert convert_resp.status_code == 200, convert_resp.text

    def test_get_missing_request_404(self, client: TestClient, waiter_headers):
        resp = client.get("/api/v1/inventory/purchase-requests/999999999", headers=waiter_headers)
        assert resp.status_code == 404

    def test_reject_request(self, client: TestClient, db, waiter_headers, manager_headers):
        branch = make_branch_committed(db)
        product = create_product(client, branch.id, manager_headers)
        pr = client.post(
            "/api/v1/inventory/purchase-requests",
            json={
                "branch_id": branch.id, "requester_id": 1, "department": "الصيانة",
                "items": [{"product_id": product["id"], "quantity_requested": "5", "unit": "piece", "estimated_unit_cost": "50.00"}],
            },
            headers=waiter_headers,
        ).json()

        resp = client.patch(
            f"/api/v1/inventory/purchase-requests/{pr['id']}/reject",
            json={"level": "dept", "reason": "ميزانية غير متاحة"},
            headers=manager_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"


class TestStockCountWorkflow:
    def test_create_list_submit_and_approve(
        self, client: TestClient, db, waiter_headers, manager_headers, accountant_headers,
    ):
        branch = make_branch_committed(db)
        product = create_product(client, branch.id, manager_headers, current_stock="100")

        create_resp = client.post(
            "/api/v1/inventory/stock-counts",
            json={
                "branch_id": branch.id, "count_date": str(date.today()), "counted_by": 1,
                "product_ids": [product["id"]],
            },
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        count = create_resp.json()
        assert len(count["lines"]) == 1
        line_id = count["lines"][0]["id"]

        list_resp = client.get("/api/v1/inventory/stock-counts", params={"branch_id": branch.id}, headers=waiter_headers)
        assert any(c["id"] == count["id"] for c in list_resp.json()["items"])

        submit_resp = client.patch(
            f"/api/v1/inventory/stock-counts/{count['id']}/submit",
            json={"lines": [{"line_id": line_id, "counted_quantity": "95"}]},
            headers=waiter_headers,
        )
        assert submit_resp.status_code == 200, submit_resp.text
        assert submit_resp.json()["status"] == "submitted"

        # اعتماد الجرد وظيفة محاسبية حصرًا (2026-07-13، Operations & Control
        # Layer — قرار محمد صراحةً: "الموافقة على الجرد المحاسب") — مدير
        # عادي (بدون دور محاسب) مرفوض هنا، راجع test_approve_denied_for_manager_without_accountant_role تحت.
        approve_resp = client.patch(
            f"/api/v1/inventory/stock-counts/{count['id']}/approve", headers=accountant_headers,
        )
        assert approve_resp.status_code == 200, approve_resp.text
        assert approve_resp.json()["status"] == "adjustment_posted"

    def test_approve_denied_for_manager_without_accountant_role(
        self, client: TestClient, db, waiter_headers, manager_headers,
    ):
        """راجع Operations & Control Layer (2026-07-13): اعتماد الجرد يقتصر
        على accountant/admin/super_admin — مدير عادي (level 60، كان مؤهّلًا
        قبل هذا التعديل عبر require_permission min_role_level=60) بقى مرفوض
        صراحةً بـ 403، مش مجرد نظري."""
        branch = make_branch_committed(db)
        product = create_product(client, branch.id, manager_headers, current_stock="10")
        count = client.post(
            "/api/v1/inventory/stock-counts",
            json={"branch_id": branch.id, "count_date": str(date.today()), "counted_by": 1, "product_ids": [product["id"]]},
            headers=manager_headers,
        ).json()
        line_id = count["lines"][0]["id"]
        client.patch(
            f"/api/v1/inventory/stock-counts/{count['id']}/submit",
            json={"lines": [{"line_id": line_id, "counted_quantity": "10"}]},
            headers=waiter_headers,
        )
        resp = client.patch(f"/api/v1/inventory/stock-counts/{count['id']}/approve", headers=manager_headers)
        assert resp.status_code == 403

    def test_approve_denied_for_waiter_without_explicit_grant(self, client: TestClient, db, waiter_headers, manager_headers):
        branch = make_branch_committed(db)
        product = create_product(client, branch.id, manager_headers, current_stock="10")
        count = client.post(
            "/api/v1/inventory/stock-counts",
            json={"branch_id": branch.id, "count_date": str(date.today()), "counted_by": 1, "product_ids": [product["id"]]},
            headers=manager_headers,
        ).json()
        line_id = count["lines"][0]["id"]
        client.patch(
            f"/api/v1/inventory/stock-counts/{count['id']}/submit",
            json={"lines": [{"line_id": line_id, "counted_quantity": "10"}]},
            headers=waiter_headers,
        )
        resp = client.patch(f"/api/v1/inventory/stock-counts/{count['id']}/approve", headers=waiter_headers)
        assert resp.status_code == 403
