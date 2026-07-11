"""
tests/test_api/test_cafe_coverage.py
رفع coverage بتاع cafe/api/router.py من 56% لـ 85%+
تركيز على: variants، recipe lines، extra groups، food cost، sales report، offline sync
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient


# ═══════════════════════════════════════════════════════════════════════
# Setup helpers — نفس نمط test_cafe_http.py
# ═══════════════════════════════════════════════════════════════════════

def _branch(db):
    from app.modules.core.models import Branch
    b = Branch(name=f"CovBranch-{uuid.uuid4().hex[:6]}", code=f"COV-{uuid.uuid4().hex[:6].upper()}")
    db.add(b); db.commit(); return b


def _category(db, branch_id, name="Coffee"):
    from app.modules.cafe.models import CafeCategory
    c = CafeCategory(branch_id=branch_id, name=name, name_ar=f"{name} AR")
    db.add(c); db.commit(); return c


def _item(db, branch_id, cat_id=None, name="Cappuccino", price="35", available=True):
    from app.modules.cafe.models import CafeItem
    i = CafeItem(branch_id=branch_id, category_id=cat_id, name=name,
                 price=Decimal(price), is_available=available, station="bar")
    db.add(i); db.commit(); return i


def _variant(db, item_id, name="Large", price="45"):
    from app.modules.cafe.models import CafeItemVariant
    v = CafeItemVariant(cafe_item_id=item_id, name=name, price=Decimal(price), is_available=True)
    db.add(v); db.commit(); return v


def _product(db, branch_id, sku=None):
    from app.modules.inventory.models import Product
    p = Product(branch_id=branch_id, sku=sku or f"SKU-{uuid.uuid4().hex[:6]}",
                name="Ingredient", unit="g", cost_price=Decimal("0.01"))
    db.add(p); db.commit(); return p


# ═══════════════════════════════════════════════════════════════════════
# Category CRUD
# ═══════════════════════════════════════════════════════════════════════

def test_cafe_update_category(client: TestClient, manager_headers, db):
    br = _branch(db)
    cat = _category(db, br.id)
    resp = client.patch(f"/api/v1/cafe/categories/{cat.id}",
                        json={"name": "Hot Drinks"}, headers=manager_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Hot Drinks"


def test_cafe_update_category_not_found(client: TestClient, manager_headers):
    resp = client.patch("/api/v1/cafe/categories/99999",
                        json={"name": "X"}, headers=manager_headers)
    assert resp.status_code == 404


def test_cafe_delete_category(client: TestClient, manager_headers, db):
    br = _branch(db)
    cat = _category(db, br.id, name="TempCat")
    resp = client.delete(f"/api/v1/cafe/categories/{cat.id}", headers=manager_headers)
    assert resp.status_code == 204


def test_cafe_delete_category_not_found(client: TestClient, manager_headers):
    resp = client.delete("/api/v1/cafe/categories/99999", headers=manager_headers)
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# Variants
# ═══════════════════════════════════════════════════════════════════════

def test_cafe_add_variant(client: TestClient, manager_headers, db):
    br = _branch(db)
    cat = _category(db, br.id)
    item = _item(db, br.id, cat.id)

    resp = client.post(f"/api/v1/cafe/items/{item.id}/variants",
                       json={"name": "Large", "name_ar": "كبير", "price": "45.00", "is_available": True},
                       headers=manager_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Large"
    assert Decimal(data["price"]) == Decimal("45")


def test_cafe_add_variant_item_not_found(client: TestClient, manager_headers):
    resp = client.post("/api/v1/cafe/items/99999/variants",
                       json={"name": "L", "price": "40.00"}, headers=manager_headers)
    assert resp.status_code in (400, 404)


def test_cafe_update_variant(client: TestClient, manager_headers, db):
    br = _branch(db)
    cat = _category(db, br.id)
    item = _item(db, br.id, cat.id)
    variant = _variant(db, item.id, name="S", price="25")

    resp = client.patch(f"/api/v1/cafe/variants/{variant.id}",
                        json={"price": "27.00", "is_available": False},
                        headers=manager_headers)
    assert resp.status_code == 200
    assert Decimal(resp.json()["price"]) == Decimal("27")
    assert resp.json()["is_available"] is False


def test_cafe_update_variant_not_found(client: TestClient, manager_headers):
    resp = client.patch("/api/v1/cafe/variants/99999",
                        json={"price": "30.00"}, headers=manager_headers)
    assert resp.status_code in (400, 404)


def test_cafe_delete_variant(client: TestClient, manager_headers, db):
    br = _branch(db)
    cat = _category(db, br.id)
    item = _item(db, br.id, cat.id)
    variant = _variant(db, item.id)

    resp = client.delete(f"/api/v1/cafe/variants/{variant.id}", headers=manager_headers)
    assert resp.status_code == 204


def test_cafe_delete_variant_not_found(client: TestClient, manager_headers):
    resp = client.delete("/api/v1/cafe/variants/99999", headers=manager_headers)
    assert resp.status_code in (400, 404)


# ═══════════════════════════════════════════════════════════════════════
# Variant Recipe Lines
# ═══════════════════════════════════════════════════════════════════════

def test_cafe_add_variant_recipe_line(client: TestClient, manager_headers, db):
    br = _branch(db)
    cat = _category(db, br.id)
    item = _item(db, br.id, cat.id)
    variant = _variant(db, item.id)
    product = _product(db, br.id)

    resp = client.post(f"/api/v1/cafe/variants/{variant.id}/recipe-lines",
                       json={"product_id": product.id, "quantity_per_unit": "200.000"},
                       headers=manager_headers)
    assert resp.status_code == 201
    assert resp.json()["product_id"] == product.id


def test_cafe_update_variant_recipe_line(client: TestClient, manager_headers, db):
    from app.modules.cafe.models import CafeItemVariantRecipeLine
    br = _branch(db)
    cat = _category(db, br.id)
    item = _item(db, br.id, cat.id)
    variant = _variant(db, item.id)
    product = _product(db, br.id)
    line = CafeItemVariantRecipeLine(variant_id=variant.id, product_id=product.id,
                                     quantity_per_unit=Decimal("20"))
    db.add(line); db.commit()

    resp = client.patch(f"/api/v1/cafe/variant-recipe-lines/{line.id}",
                        json={"quantity_per_unit": "25.000"},
                        headers=manager_headers)
    assert resp.status_code == 200
    assert Decimal(resp.json()["quantity_per_unit"]) == Decimal("25")


def test_cafe_delete_variant_recipe_line(client: TestClient, manager_headers, db):
    from app.modules.cafe.models import CafeItemVariantRecipeLine
    br = _branch(db)
    cat = _category(db, br.id)
    item = _item(db, br.id, cat.id)
    variant = _variant(db, item.id)
    product = _product(db, br.id)
    line = CafeItemVariantRecipeLine(variant_id=variant.id, product_id=product.id,
                                     quantity_per_unit=Decimal("10"))
    db.add(line); db.commit()

    resp = client.delete(f"/api/v1/cafe/variant-recipe-lines/{line.id}", headers=manager_headers)
    assert resp.status_code == 204


# ═══════════════════════════════════════════════════════════════════════
# Item Recipe Lines
# ═══════════════════════════════════════════════════════════════════════

def test_cafe_add_item_recipe_line(client: TestClient, manager_headers, db):
    br = _branch(db)
    cat = _category(db, br.id)
    item = _item(db, br.id, cat.id, name="Tea")
    product = _product(db, br.id)

    resp = client.post(f"/api/v1/cafe/items/{item.id}/recipe-lines",
                       json={"product_id": product.id, "quantity_per_unit": "5.000"},
                       headers=manager_headers)
    assert resp.status_code == 201
    assert resp.json()["product_id"] == product.id


def test_cafe_update_item_recipe_line(client: TestClient, manager_headers, db):
    from app.modules.cafe.models import CafeItemRecipeLine
    br = _branch(db)
    cat = _category(db, br.id)
    item = _item(db, br.id, cat.id, name="Latte")
    product = _product(db, br.id)
    line = CafeItemRecipeLine(cafe_item_id=item.id, product_id=product.id,
                              quantity_per_unit=Decimal("100"))
    db.add(line); db.commit()

    resp = client.patch(f"/api/v1/cafe/recipe-lines/{line.id}",
                        json={"quantity_per_unit": "120.000"},
                        headers=manager_headers)
    assert resp.status_code == 200
    assert Decimal(resp.json()["quantity_per_unit"]) == Decimal("120")


def test_cafe_delete_item_recipe_line(client: TestClient, manager_headers, db):
    from app.modules.cafe.models import CafeItemRecipeLine
    br = _branch(db)
    cat = _category(db, br.id)
    item = _item(db, br.id, cat.id, name="Mocha")
    product = _product(db, br.id)
    line = CafeItemRecipeLine(cafe_item_id=item.id, product_id=product.id,
                              quantity_per_unit=Decimal("15"))
    db.add(line); db.commit()

    resp = client.delete(f"/api/v1/cafe/recipe-lines/{line.id}", headers=manager_headers)
    assert resp.status_code == 204


# ═══════════════════════════════════════════════════════════════════════
# Extra Groups
# ═══════════════════════════════════════════════════════════════════════

def test_cafe_create_extra_group(client: TestClient, manager_headers, db):
    br = _branch(db)
    cat = _category(db, br.id)
    item = _item(db, br.id, cat.id)

    resp = client.post(f"/api/v1/cafe/menu/items/{item.id}/extra-groups",
                       json={"name": "Milk Type", "name_ar": "نوع الحليب",
                             "min_select": 0, "max_select": 1,
                             "options": [{"name": "Oat Milk", "price_addition": "5.00"}]},
                       headers=manager_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Milk Type"
    assert len(data["options"]) == 1


def test_cafe_create_extra_group_item_not_found(client: TestClient, manager_headers):
    resp = client.post("/api/v1/cafe/menu/items/99999/extra-groups",
                       json={"name": "X", "min_select": 0, "max_select": 1, "options": []},
                       headers=manager_headers)
    assert resp.status_code == 404


def test_cafe_delete_extra_group(client: TestClient, manager_headers, db):
    from app.modules.cafe.models import CafeMenuItemExtraGroup
    br = _branch(db)
    cat = _category(db, br.id)
    item = _item(db, br.id, cat.id)
    grp = CafeMenuItemExtraGroup(cafe_item_id=item.id, name="Size", min_select=0, max_select=1)
    db.add(grp); db.commit()

    resp = client.delete(f"/api/v1/cafe/menu/extra-groups/{grp.id}", headers=manager_headers)
    assert resp.status_code == 204


def test_cafe_delete_extra_group_not_found(client: TestClient, manager_headers):
    resp = client.delete("/api/v1/cafe/menu/extra-groups/99999", headers=manager_headers)
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# Tables CRUD
# ═══════════════════════════════════════════════════════════════════════

def test_cafe_update_table(client: TestClient, manager_headers, db):
    from app.modules.cafe.models import CafeTable
    br = _branch(db)
    table = CafeTable(branch_id=br.id, table_number="C99", capacity=2, status="available")
    db.add(table); db.commit()

    resp = client.patch(f"/api/v1/cafe/tables/{table.id}",
                        json={"capacity": 6}, headers=manager_headers)
    assert resp.status_code == 200
    assert resp.json()["capacity"] == 6


def test_cafe_update_table_not_found(client: TestClient, manager_headers):
    resp = client.patch("/api/v1/cafe/tables/99999", json={"capacity": 4}, headers=manager_headers)
    assert resp.status_code == 404


def test_cafe_delete_table(client: TestClient, manager_headers, db):
    from app.modules.cafe.models import CafeTable
    br = _branch(db)
    table = CafeTable(branch_id=br.id, table_number="C98", capacity=2, status="available")
    db.add(table); db.commit()

    resp = client.delete(f"/api/v1/cafe/tables/{table.id}", headers=manager_headers)
    assert resp.status_code == 204


# ═══════════════════════════════════════════════════════════════════════
# Food Cost Report
# ═══════════════════════════════════════════════════════════════════════

def test_cafe_food_cost_report_ok(client: TestClient, manager_headers, db):
    br = _branch(db)
    today = date.today()
    resp = client.get(
        f"/api/v1/cafe/reports/food-cost?branch_id={br.id}"
        f"&date_from={today - timedelta(days=7)}&date_to={today}",
        headers=manager_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert "lines" in data or "items" in data or "alerts" in data


def test_cafe_food_cost_report_invalid_dates(client: TestClient, manager_headers, db):
    br = _branch(db)
    resp = client.get(
        f"/api/v1/cafe/reports/food-cost?branch_id={br.id}&date_from=2026-07-10&date_to=2026-07-01",
        headers=manager_headers,
    )
    assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════
# Cafe Sales Dashboard Report
# ═══════════════════════════════════════════════════════════════════════

def test_cafe_sales_report_empty(client: TestClient, manager_headers, db):
    br = _branch(db)
    today = date.today()
    resp = client.get(
        f"/api/v1/cafe/reports/sales?branch_id={br.id}"
        f"&date_from={today}&date_to={today}",
        headers=manager_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_orders"] == 0
    assert data["total_revenue"] == 0.0
    assert data["top_items"] == []


def test_cafe_sales_report_with_data(client: TestClient, manager_headers, db):
    br = _branch(db)
    cat = _category(db, br.id, name="Cold Drinks")
    item = _item(db, br.id, cat.id, name="Orange Juice", price="20")

    # طلب مدفوع
    from app.modules.cafe.models import CafeOrder, CafeOrderItem
    order = CafeOrder(
        branch_id=br.id, order_number=f"CAF-TST-{uuid.uuid4().hex[:6].upper()}",
        order_type="takeaway", subtotal=Decimal("20"), vat_amount=Decimal("2.80"),
        service_charge=Decimal("0"), total=Decimal("22.80"),
        status="paid", payment_method="cash",
    )
    db.add(order); db.flush()
    oi = CafeOrderItem(
        order_id=order.id, item_id=item.id,
        name="Orange Juice", unit_price=Decimal("20"), quantity=1, status="served",
    )
    db.add(oi); db.commit()

    today = date.today()
    resp = client.get(
        f"/api/v1/cafe/reports/sales?branch_id={br.id}"
        f"&date_from={today}&date_to={today}",
        headers=manager_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_orders"] >= 1
    assert data["total_revenue"] > 0


def test_cafe_sales_report_invalid_dates(client: TestClient, manager_headers, db):
    br = _branch(db)
    resp = client.get(
        f"/api/v1/cafe/reports/sales?branch_id={br.id}&date_from=2026-07-10&date_to=2026-07-01",
        headers=manager_headers,
    )
    assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════
# Offline Sync
# ═══════════════════════════════════════════════════════════════════════

def test_cafe_offline_sync_idempotent(client: TestClient, waiter_headers, db):
    """نفس local_id مرتين — يرجع نفس order_id بدون تكرار"""
    br = _branch(db)
    cat = _category(db, br.id)
    item = _item(db, br.id, cat.id)

    local_id = f"OFFLINE-{uuid.uuid4().hex[:8]}"
    payload = {
        "local_id": local_id,
        "table_id": None,
        "order_type": "takeaway",
        "items": [{"item_id": item.id, "quantity": 1, "variant_id": None, "extras": []}],
        "subtotal": float(item.price),
        "vat_amount": 4.90,
        "service_charge": 0,
        "total": float(item.price) + 4.90,
        "payment_method": "cash",
    }

    r1 = client.post(f"/api/v1/cafe/orders/sync?branch_id={br.id}", json=payload, headers=waiter_headers)
    assert r1.status_code == 200
    order_id = r1.json()["order_id"]
    assert r1.json()["status"] == "fulfilled"

    r2 = client.post(f"/api/v1/cafe/orders/sync?branch_id={br.id}", json=payload, headers=waiter_headers)
    assert r2.status_code == 200
    assert r2.json()["order_id"] == order_id
    assert r2.json()["status"] == "fulfilled"


def test_cafe_offline_sync_new_order(client: TestClient, waiter_headers, db):
    """sync بدون local_id — بيعمل طلب جديد"""
    br = _branch(db)
    cat = _category(db, br.id)
    item = _item(db, br.id, cat.id)

    payload = {
        "table_id": None,
        "order_type": "takeaway",
        "items": [{"item_id": item.id, "quantity": 2, "variant_id": None, "extras": []}],
        "subtotal": float(item.price) * 2,
        "vat_amount": 9.80,
        "service_charge": 0,
        "total": float(item.price) * 2 + 9.80,
        "payment_method": "cash",
    }

    r = client.post(f"/api/v1/cafe/orders/sync?branch_id={br.id}", json=payload, headers=waiter_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["order_id"] > 0
    assert data["status"] in ("fulfilled", "partial")


def test_cafe_create_and_update_item_availability_window(client: TestClient, manager_headers, db):
    """wagdy.md P-03 — available_from_time/available_until_time على
    CafeItem (نفس restaurant.MenuItem بالظبط، راجع
    test_restaurant_http.TestMenuItemCrudHTTP)."""
    br = _branch(db)
    create_resp = client.post(
        "/api/v1/cafe/items",
        json={"branch_id": br.id, "name": "عصير الصباح", "price": "30.00",
              "available_from_time": "07:00:00", "available_until_time": "11:00:00"},
        headers=manager_headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    item = create_resp.json()
    assert item["available_from_time"] == "07:00:00"
    assert item["available_until_time"] == "11:00:00"

    update_resp = client.patch(
        f"/api/v1/cafe/items/{item['id']}",
        json={"available_until_time": "12:00:00"},
        headers=manager_headers,
    )
    assert update_resp.status_code == 200, update_resp.text
    assert update_resp.json()["available_until_time"] == "12:00:00"
    assert update_resp.json()["available_from_time"] == "07:00:00"
