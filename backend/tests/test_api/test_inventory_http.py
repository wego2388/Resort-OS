"""
tests/test_api/test_inventory_http.py
HTTP-level tests for the inventory module — TestClient through real routing,
permission dependencies and Pydantic validation (not direct service calls).

⚠️ inventory is `always_on=True` in MODULE_REGISTRY — no module-enable step needed.
⚠️ Setup data created here must be `db.commit()`-ed, not `.flush()`-ed.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="Inventory HTTP Branch", name_ar="فرع مخازن",
               code=f"INV-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_warehouse_committed(db, branch):
    from app.modules.inventory.models import Warehouse
    wh = Warehouse(branch_id=branch.id, name="Main Store", code=f"WH-{uuid.uuid4().hex[:6].upper()}")
    db.add(wh)
    db.commit()
    return wh


def make_product_committed(db, branch):
    from app.modules.inventory.models import Product
    p = Product(branch_id=branch.id, name="أرز مصري", sku=f"SKU-{uuid.uuid4().hex[:8].upper()}",
                unit="kg", cost_price=Decimal("15.00"), min_stock=Decimal("10"), reorder_point=Decimal("20"))
    db.add(p)
    db.commit()
    return p


class TestPurchaseOrderFlow:
    def test_create_and_receive_purchase_order_updates_stock(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        warehouse = make_warehouse_committed(db, branch)
        product = make_product_committed(db, branch)

        create_resp = client.post(
            "/api/v1/inventory/purchase-orders",
            json={
                "branch_id": branch.id, "supplier_name": "شركة التوريد المصرية",
                "ordered_at": str(date.today()),
                "items": [{"product_id": product.id, "ordered_qty": "100.00", "unit_cost": "15.00"}],
            },
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        po = create_resp.json()
        assert po["status"] == "draft" or po["status"] == "ordered"
        item_id = po["items"][0]["id"]

        receive_resp = client.post(
            f"/api/v1/inventory/purchase-orders/{po['id']}/receive",
            json={
                "items": [{"item_id": item_id, "received_qty": "100.00"}],
                "warehouse_id": warehouse.id, "received_at": str(date.today()),
            },
            headers=manager_headers,
        )
        assert receive_resp.status_code == 200, receive_resp.text
        assert receive_resp.json()["status"] == "received"

        movements_resp = client.get(
            "/api/v1/inventory/movements", params={"branch_id": branch.id, "product_id": product.id},
            headers=manager_headers,
        )
        assert movements_resp.status_code == 200
        assert movements_resp.json()["total"] == 1
        assert movements_resp.json()["items"][0]["movement_type"] == "purchase_in"

    def test_receive_already_received_po_rejected(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        warehouse = make_warehouse_committed(db, branch)
        product = make_product_committed(db, branch)
        po = client.post(
            "/api/v1/inventory/purchase-orders",
            json={
                "branch_id": branch.id, "supplier_name": "مورد",
                "ordered_at": str(date.today()),
                "items": [{"product_id": product.id, "ordered_qty": "10.00", "unit_cost": "5.00"}],
            },
            headers=manager_headers,
        ).json()
        item_id = po["items"][0]["id"]
        receive_body = {
            "items": [{"item_id": item_id, "received_qty": "10.00"}],
            "warehouse_id": warehouse.id, "received_at": str(date.today()),
        }
        client.post(f"/api/v1/inventory/purchase-orders/{po['id']}/receive", json=receive_body, headers=manager_headers)

        second = client.post(f"/api/v1/inventory/purchase-orders/{po['id']}/receive", json=receive_body, headers=manager_headers)
        assert second.status_code == 400


class TestInventoryPermissions:
    def test_create_product_requires_manager(self, client: TestClient, db, cashier_headers):
        """cashier (40) must not create products — manager (60) required."""
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/inventory/products",
            json={"branch_id": branch.id, "name": "منتج", "sku": "SKU-X"},
            headers=cashier_headers,
        )
        assert resp.status_code == 403

    def test_record_movement_requires_manager(self, client: TestClient, db, cashier_headers):
        branch = make_branch_committed(db)
        product = make_product_committed(db, branch)
        warehouse = make_warehouse_committed(db, branch)
        resp = client.post(
            "/api/v1/inventory/movements",
            json={
                "branch_id": branch.id, "product_id": product.id, "warehouse_id": warehouse.id,
                "movement_type": "adjustment", "quantity": "5.00",
                "moved_at": "2026-01-01T00:00:00",
            },
            headers=cashier_headers,
        )
        assert resp.status_code == 403


class TestInventoryValidation:
    def test_create_product_rejects_duplicate_sku(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        product = make_product_committed(db, branch)
        resp = client.post(
            "/api/v1/inventory/products",
            json={"branch_id": branch.id, "name": "منتج آخر", "sku": product.sku},
            headers=manager_headers,
        )
        assert resp.status_code == 400

    def test_create_product_rejects_invalid_unit(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/inventory/products",
            json={"branch_id": branch.id, "name": "منتج", "sku": "SKU-UNIQ", "unit": "gallon"},
            headers=manager_headers,
        )
        assert resp.status_code == 422

    def test_create_purchase_order_rejects_empty_items(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/inventory/purchase-orders",
            json={"branch_id": branch.id, "supplier_name": "مورد", "ordered_at": str(date.today()), "items": []},
            headers=manager_headers,
        )
        assert resp.status_code == 422
