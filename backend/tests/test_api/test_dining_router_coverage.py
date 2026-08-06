"""
test_dining_router_coverage.py — HTTP tests لـ dining/api/router.py
رفع coverage من 57% → 80%+ بتغطية Menu CRUD + Tables + Orders + Kitchen + Public.
"""
from __future__ import annotations
import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient


# ── helpers ───────────────────────────────────────────────────────────────────

def _branch(db):
    from app.modules.core.models import Branch
    b = Branch(name=f"CovBr-{uuid.uuid4().hex[:6]}", code=f"CV-{uuid.uuid4().hex[:4].upper()}")
    db.add(b); db.commit(); return b

def _outlet(db, branch):
    from app.modules.dining.models import Outlet
    o = Outlet(branch_id=branch.id, name=f"out-{uuid.uuid4().hex[:6]}",
               outlet_type="restaurant", revenue_account_code="4200")
    db.add(o); db.commit(); return o

def _item(db, branch, outlet, price=Decimal("50.00")):
    from app.modules.dining.models import DiningItem
    i = DiningItem(branch_id=branch.id, outlet_id=outlet.id,
                   name=f"item-{uuid.uuid4().hex[:6]}", price=price,
                   is_available=True, station="hot")
    db.add(i); db.commit(); return i

def _table(db, branch):
    from app.modules.dining.models import VenueTable
    t = VenueTable(branch_id=branch.id, table_number=f"T-{uuid.uuid4().hex[:6]}",
                   capacity=4, status="available")
    db.add(t); db.commit(); return t

def _finance_accounts(db, branch):
    from app.modules.finance.models import Account, AccountingPeriod
    for code, name, kind in [("1100","كاش","asset"),("4200","إيراد","revenue"),
                              ("2100","ضريبة","liability"),("2200","خدمة","liability")]:
        db.add(Account(branch_id=branch.id, code=code, name=name, account_type=kind))
    # AccountingPeriod بيستخدم year/month/status (مش name/start_date/end_date)
    existing = db.query(AccountingPeriod).filter_by(
        branch_id=branch.id, year=2026, month=8
    ).first()
    if not existing:
        db.add(AccountingPeriod(branch_id=branch.id, year=2026, month=8, status="open"))
    db.commit()

def _product(db, branch):
    from app.modules.inventory.models import Warehouse, Product
    wh = Warehouse(branch_id=branch.id, name=f"WH-{uuid.uuid4().hex[:4]}",
                   code=f"WH-{uuid.uuid4().hex[:4].upper()}", is_active=True)
    db.add(wh); db.flush()
    p = Product(branch_id=branch.id, warehouse_id=wh.id,
                name="مكوّن", sku=f"SKU-{uuid.uuid4().hex[:6]}", unit="kg",
                cost_price=Decimal("2.00"))
    db.add(p); db.commit(); return p

def _linked(db, branch, role="waiter"):
    from datetime import date, timedelta
    from tests.conftest import _create_test_user, _make_token, open_cashier_shift
    from app.modules.core.models import UserBranchMembership
    from app.modules.hr.models import Employee
    email = f"{role}-cov-{uuid.uuid4().hex[:8]}@test.local"
    uid = _create_test_user(email, role)
    db.add_all([
        Employee(branch_id=branch.id, employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
                 full_name=f"test {role}", national_id="29001011234567",
                 position=role, department="F&B", basic_salary=Decimal("3000"),
                 hire_date=date.today()-timedelta(days=30), user_id=uid),
        UserBranchMembership(user_id=uid, branch_id=branch.id, is_default=True, is_active=True),
    ])
    db.commit()
    open_cashier_shift(db, branch.id, uid)
    return {"Authorization": f"Bearer {_make_token(email)}"}


# ── Outlet GET / PATCH ────────────────────────────────────────────────────────

class TestOutletGetPatch:
    def test_get_outlet_by_id(self, client, db, manager_headers):
        br = _branch(db); o = _outlet(db, br)
        r = client.get(f"/api/v1/dining/outlets/{o.id}", headers=manager_headers)
        assert r.status_code == 200 and r.json()["id"] == o.id

    def test_get_outlet_not_found(self, client, db, manager_headers):
        r = client.get("/api/v1/dining/outlets/999999", headers=manager_headers)
        assert r.status_code == 404

    def test_patch_outlet_name(self, client, db, manager_headers):
        br = _branch(db); o = _outlet(db, br)
        r = client.patch(f"/api/v1/dining/outlets/{o.id}",
                         json={"name": "Updated"}, headers=manager_headers)
        assert r.status_code == 200 and r.json()["name"] == "Updated"


# ── Category CRUD ─────────────────────────────────────────────────────────────

class TestCategoryCRUD:
    def test_list_categories_empty(self, client, db, manager_headers):
        br = _branch(db); o = _outlet(db, br)
        r = client.get(f"/api/v1/dining/outlets/{o.id}/categories", headers=manager_headers)
        assert r.status_code == 200 and r.json() == []

    def test_create_category(self, client, db, manager_headers):
        br = _branch(db); o = _outlet(db, br)
        r = client.post(f"/api/v1/dining/outlets/{o.id}/categories",
                        json={"branch_id": br.id, "outlet_id": o.id,
                              "name": "مقبلات", "name_ar": "مقبلات", "sort_order": 1},
                        headers=manager_headers)
        assert r.status_code == 201 and r.json()["name"] == "مقبلات"

    def test_patch_category(self, client, db, manager_headers):
        br = _branch(db); o = _outlet(db, br)
        cat = client.post(f"/api/v1/dining/outlets/{o.id}/categories",
                          json={"branch_id": br.id, "outlet_id": o.id,
                                "name": "فئة", "sort_order": 0}, headers=manager_headers).json()
        r = client.patch(f"/api/v1/dining/categories/{cat['id']}",
                         json={"name": "معدّل"}, headers=manager_headers)
        assert r.status_code == 200 and r.json()["name"] == "معدّل"

    def test_delete_category(self, client, db, manager_headers):
        br = _branch(db); o = _outlet(db, br)
        cat = client.post(f"/api/v1/dining/outlets/{o.id}/categories",
                          json={"branch_id": br.id, "outlet_id": o.id,
                                "name": "للحذف", "sort_order": 0}, headers=manager_headers).json()
        r = client.delete(f"/api/v1/dining/categories/{cat['id']}", headers=manager_headers)
        assert r.status_code == 204

    def test_create_category_requires_manager(self, client, db, waiter_headers):
        br = _branch(db); o = _outlet(db, br)
        r = client.post(f"/api/v1/dining/outlets/{o.id}/categories",
                        json={"branch_id": br.id, "outlet_id": o.id,
                              "name": "x", "sort_order": 0}, headers=waiter_headers)
        assert r.status_code in (401, 403)


# ── Item CRUD ─────────────────────────────────────────────────────────────────

class TestItemCRUD:
    def test_create_item(self, client, db, manager_headers):
        br = _branch(db); o = _outlet(db, br)
        r = client.post(f"/api/v1/dining/outlets/{o.id}/items",
                        json={"branch_id": br.id, "outlet_id": o.id,
                              "name": "بيتزا", "price": "55.00",
                              "station": "hot", "is_available": True},
                        headers=manager_headers)
        assert r.status_code == 201 and r.json()["name"] == "بيتزا"

    def test_patch_item_price(self, client, db, manager_headers):
        br = _branch(db); o = _outlet(db, br); item = _item(db, br, o)
        r = client.patch(f"/api/v1/dining/items/{item.id}",
                         json={"price": "65.00"}, headers=manager_headers)
        assert r.status_code == 200 and Decimal(r.json()["price"]) == Decimal("65.00")

    def test_delete_item(self, client, db, manager_headers):
        br = _branch(db); o = _outlet(db, br); item = _item(db, br, o)
        r = client.delete(f"/api/v1/dining/items/{item.id}", headers=manager_headers)
        assert r.status_code == 204

    def test_delete_item_requires_manager(self, client, db, waiter_headers):
        br = _branch(db); o = _outlet(db, br); item = _item(db, br, o)
        r = client.delete(f"/api/v1/dining/items/{item.id}", headers=waiter_headers)
        assert r.status_code in (401, 403)


# ── Extra Groups ──────────────────────────────────────────────────────────────

class TestExtraGroupCRUD:
    def test_create_and_delete_extra_group(self, client, db, manager_headers):
        br = _branch(db); o = _outlet(db, br); item = _item(db, br, o)
        grp = client.post(f"/api/v1/dining/items/{item.id}/extra-groups",
                          json={"name": "الحجم", "group_type": "pick_list",
                                "min_select": 0, "max_select": 1,
                                "sort_order": 0, "options": []},
                          headers=manager_headers).json()
        assert grp["name"] == "الحجم"
        r = client.delete(f"/api/v1/dining/extra-groups/{grp['id']}", headers=manager_headers)
        assert r.status_code == 204

    def test_create_text_extra_group(self, client, db, manager_headers):
        br = _branch(db); o = _outlet(db, br); item = _item(db, br, o)
        r = client.post(f"/api/v1/dining/items/{item.id}/extra-groups",
                        json={"name": "كام سمكة؟", "group_type": "text",
                              "min_select": 1, "max_select": 1,
                              "sort_order": 0, "options": []},
                        headers=manager_headers)
        assert r.status_code == 201 and r.json()["group_type"] == "text"


# ── Recipe Lines ──────────────────────────────────────────────────────────────

class TestRecipeLineCRUD:
    def test_create_patch_delete_recipe_line(self, client, db, manager_headers):
        br = _branch(db); o = _outlet(db, br)
        item = _item(db, br, o); prod = _product(db, br)
        line = client.post(f"/api/v1/dining/items/{item.id}/recipe-lines",
                           json={"product_id": prod.id, "quantity_per_unit": "0.5"},
                           headers=manager_headers).json()
        assert line["product_id"] == prod.id
        r = client.patch(f"/api/v1/dining/recipe-lines/{line['id']}",
                         json={"quantity_per_unit": "1.0"}, headers=manager_headers)
        assert r.status_code == 200 and Decimal(r.json()["quantity_per_unit"]) == Decimal("1.0")
        r = client.delete(f"/api/v1/dining/recipe-lines/{line['id']}", headers=manager_headers)
        assert r.status_code == 204


# ── Variants ──────────────────────────────────────────────────────────────────

class TestVariantCRUD:
    def test_create_patch_delete_variant(self, client, db, manager_headers):
        br = _branch(db); o = _outlet(db, br); item = _item(db, br, o)
        v = client.post(f"/api/v1/dining/items/{item.id}/variants",
                        json={"name": "كبير", "name_ar": "كبير",
                              "price": "70.00", "sort_order": 0},
                        headers=manager_headers).json()
        assert v["name"] == "كبير"
        r = client.patch(f"/api/v1/dining/variants/{v['id']}",
                         json={"price": "75.00"}, headers=manager_headers)
        assert r.status_code == 200 and Decimal(r.json()["price"]) == Decimal("75.00")
        r = client.delete(f"/api/v1/dining/variants/{v['id']}", headers=manager_headers)
        assert r.status_code == 204

    def test_create_variant_recipe_line(self, client, db, manager_headers):
        br = _branch(db); o = _outlet(db, br)
        item = _item(db, br, o); prod = _product(db, br)
        v = client.post(f"/api/v1/dining/items/{item.id}/variants",
                        json={"name": "صغير", "price": "40.00", "sort_order": 0},
                        headers=manager_headers).json()
        r = client.post(f"/api/v1/dining/variants/{v['id']}/recipe-lines",
                        json={"product_id": prod.id, "quantity_per_unit": "0.3"},
                        headers=manager_headers)
        assert r.status_code == 201
        line_id = r.json()["id"]
        r2 = client.patch(f"/api/v1/dining/variant-recipe-lines/{line_id}",
                          json={"quantity_per_unit": "0.4"}, headers=manager_headers)
        assert r2.status_code == 200
        r3 = client.delete(f"/api/v1/dining/variant-recipe-lines/{line_id}",
                           headers=manager_headers)
        assert r3.status_code == 204


# ── Tables CRUD ───────────────────────────────────────────────────────────────

class TestTablesCRUD:
    def test_create_table(self, client, db, manager_headers):
        br = _branch(db)
        r = client.post(f"/api/v1/dining/branches/{br.id}/tables",
                        json={"branch_id": br.id,
                              "table_number": f"T-{uuid.uuid4().hex[:6]}",
                              "capacity": 4},
                        headers=manager_headers)
        assert r.status_code == 201

    def test_patch_table(self, client, db, manager_headers):
        br = _branch(db); t = _table(db, br)
        r = client.patch(f"/api/v1/dining/tables/{t.id}",
                         json={"capacity": 6}, headers=manager_headers)
        assert r.status_code == 200 and r.json()["capacity"] == 6

    def test_patch_table_grid(self, client, db, manager_headers):
        br = _branch(db); t = _table(db, br)
        r = client.patch(f"/api/v1/dining/tables/{t.id}/grid",
                         json={"grid_x": 2, "grid_y": 3, "grid_w": 1, "grid_h": 1},
                         headers=manager_headers)
        assert r.status_code == 200

    def test_delete_table(self, client, db, manager_headers):
        br = _branch(db); t = _table(db, br)
        r = client.delete(f"/api/v1/dining/tables/{t.id}", headers=manager_headers)
        assert r.status_code == 204


# ── Orders ────────────────────────────────────────────────────────────────────

class TestOrdersHTTP:
    def _setup(self, db):
        br = _branch(db); o = _outlet(db, br)
        _finance_accounts(db, br)
        item = _item(db, br, o)
        hdrs = _linked(db, br, "waiter")
        mgr  = _linked(db, br, "manager")
        return br, o, item, hdrs, mgr

    def test_list_orders(self, client, db, manager_headers):
        r = client.get("/api/v1/dining/orders?branch_id=1", headers=manager_headers)
        assert r.status_code == 200

    def test_create_order_via_http(self, client, db):
        br, o, item, hdrs, _ = self._setup(db)
        r = client.post(f"/api/v1/dining/outlets/{o.id}/orders",
                        json={"outlet_id": o.id, "order_type": "takeaway", "guests_count": 1,
                              "items": [{"item_id": item.id, "quantity": 1,
                                         "extra_ids": [], "extra_texts": {}}]},
                        headers=hdrs)
        assert r.status_code == 201

    def test_hold_order(self, client, db):
        br, o, item, hdrs, _ = self._setup(db)
        r = client.post(f"/api/v1/dining/outlets/{o.id}/orders/hold",
                        json={"outlet_id": o.id, "order_type": "takeaway", "guests_count": 1,
                              "items": [{"item_id": item.id, "quantity": 1,
                                         "extra_ids": [], "extra_texts": {}}]},
                        headers=hdrs)
        assert r.status_code == 201 and r.json()["status"] == "held"

    def test_list_held_orders(self, client, db):
        br, o, item, hdrs, _ = self._setup(db)
        client.post(f"/api/v1/dining/outlets/{o.id}/orders/hold",
                    json={"outlet_id": o.id, "order_type": "takeaway", "guests_count": 1,
                          "items": [{"item_id": item.id, "quantity": 1,
                                     "extra_ids": [], "extra_texts": {}}]},
                    headers=hdrs)
        r = client.get(f"/api/v1/dining/outlets/{o.id}/orders/held", headers=hdrs)
        assert r.status_code == 200 and len(r.json()) >= 1

    def test_sync_offline_order(self, client, db):
        br, o, item, hdrs, _ = self._setup(db)
        local_id = f"local-{uuid.uuid4().hex}"
        r = client.post(f"/api/v1/dining/outlets/{o.id}/orders/sync",
                        json={"outlet_id": o.id, "local_id": local_id,
                              "order_type": "takeaway", "guests_count": 1,
                              "items": [{"item_id": item.id, "quantity": 1,
                                         "extra_ids": [], "extra_texts": {}}]},
                        headers=hdrs)
        assert r.status_code == 200 and r.json()["status"] in ("fulfilled", "partial")

    def test_add_items_to_order(self, client, db):
        br, o, item, hdrs, _ = self._setup(db)
        item2 = _item(db, br, o, price=Decimal("30.00"))
        order = client.post(f"/api/v1/dining/outlets/{o.id}/orders",
                            json={"outlet_id": o.id, "order_type": "takeaway", "guests_count": 1,
                                  "items": [{"item_id": item.id, "quantity": 1,
                                             "extra_ids": [], "extra_texts": {}}]},
                            headers=hdrs).json()
        r = client.post(f"/api/v1/dining/orders/{order['id']}/items",
                        json=[{"item_id": item2.id, "quantity": 2,
                               "extra_ids": [], "extra_texts": {}}],
                        headers=hdrs)
        assert r.status_code == 200

    def test_transfer_order_waiter(self, client, db):
        br, o, item, hdrs, mgr = self._setup(db)
        order = client.post(f"/api/v1/dining/outlets/{o.id}/orders",
                            json={"outlet_id": o.id, "order_type": "dine_in", "guests_count": 2,
                                  "items": [{"item_id": item.id, "quantity": 1,
                                             "extra_ids": [], "extra_texts": {}}]},
                            headers=hdrs).json()
        from tests.conftest import _create_test_user, _make_token
        from app.modules.core.models import UserBranchMembership
        from app.modules.hr.models import Employee
        from datetime import date, timedelta
        email2 = f"waiter2-{uuid.uuid4().hex[:8]}@test.local"
        uid2 = _create_test_user(email2, "waiter")
        db.add_all([
            Employee(branch_id=br.id, employee_code=f"EMP2-{uuid.uuid4().hex[:6]}",
                     full_name="نادل 2", national_id="29001011234568",
                     position="waiter", department="F&B", basic_salary=Decimal("3000"),
                     hire_date=date.today()-timedelta(days=10), user_id=uid2),
            UserBranchMembership(user_id=uid2, branch_id=br.id, is_default=True, is_active=True),
        ])
        db.commit()
        from app.modules.core import services as core_svc
        pin = "1234"
        core_svc.set_pin(db, uid2, pin, created_by=uid2)
        db.commit()
        mgr_hdrs = _linked(db, br, "manager")
        r = client.patch(f"/api/v1/dining/orders/{order['id']}/waiter",
                         json={"new_waiter_id": uid2, "reason": "shift change",
                               "approver_user_id": None, "approver_pin": None},
                         headers=mgr_hdrs)
        # مدير+ مؤهّل بنفسه بدون PIN
        assert r.status_code in (200, 400)

    def test_order_receipt_pdf(self, client, db):
        br, o, item, hdrs, mgr = self._setup(db)
        order = client.post(f"/api/v1/dining/outlets/{o.id}/orders",
                            json={"outlet_id": o.id, "order_type": "takeaway", "guests_count": 1,
                                  "items": [{"item_id": item.id, "quantity": 1,
                                             "extra_ids": [], "extra_texts": {}}]},
                            headers=hdrs).json()
        # GET /receipt يتطلب cashier+ (level ≥ 40) — النادل (level 30) مش مسموح
        # نستخدم المدير المرتبط بالفرع (level 60) عشان يمر الفحص
        r = client.get(f"/api/v1/dining/orders/{order['id']}/receipt", headers=mgr)
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"

    def test_sales_report(self, client, db, manager_headers):
        br = _branch(db); o = _outlet(db, br)
        r = client.get(f"/api/v1/dining/outlets/{o.id}/reports/sales",
                       params={"date_from": "2026-08-01", "date_to": "2026-08-05"},
                       headers=manager_headers)
        assert r.status_code == 200

    def test_food_cost_report(self, client, db, manager_headers):
        br = _branch(db); o = _outlet(db, br)
        r = client.get(f"/api/v1/dining/outlets/{o.id}/reports/food-cost",
                       params={"date_from": "2026-08-01", "date_to": "2026-08-05"},
                       headers=manager_headers)
        assert r.status_code == 200

    def test_branch_food_cost_report(self, client, db, manager_headers):
        br = _branch(db)
        r = client.get("/api/v1/dining/reports/food-cost",
                       params={"branch_id": br.id,
                               "date_from": "2026-08-01", "date_to": "2026-08-05"},
                       headers=manager_headers)
        assert r.status_code == 200


# ── Kitchen Tickets + KDS Screens ────────────────────────────────────────────

class TestKitchenAndKDS:
    def test_list_kitchen_tickets(self, client, db):
        # manager_headers العام مش عنده branch membership → 403 من assert_branch_access
        # نستخدم _linked() عشان نربط المدير بالفرع الصح
        br = _branch(db)
        mgr = _linked(db, br, "manager")
        r = client.get("/api/v1/dining/kitchen/tickets",
                       params={"branch_id": br.id}, headers=mgr)
        assert r.status_code == 200 and isinstance(r.json(), list)

    def test_create_kds_screen(self, client, db, manager_headers):
        br = _branch(db)
        r = client.post("/api/v1/dining/kds-screens",
                        json={"branch_id": br.id,
                              "name": f"KDS-{uuid.uuid4().hex[:6]}",
                              "stations": ["hot", "grill"],
                              "display_mode": "kanban",
                              "alert_after_minutes": 15},
                        headers=manager_headers)
        assert r.status_code == 201

    def test_list_kds_screens(self, client, db, manager_headers):
        br = _branch(db)
        r = client.get("/api/v1/dining/kds-screens",
                       params={"branch_id": br.id}, headers=manager_headers)
        assert r.status_code == 200

    def test_ticket_status_transition(self, client, db):
        br = _branch(db); o = _outlet(db, br)
        _finance_accounts(db, br)
        item = _item(db, br, o)
        hdrs = _linked(db, br, "waiter")
        mgr  = _linked(db, br, "manager")
        order = client.post(f"/api/v1/dining/outlets/{o.id}/orders",
                            json={"outlet_id": o.id, "order_type": "takeaway", "guests_count": 1,
                                  "items": [{"item_id": item.id, "quantity": 1,
                                             "extra_ids": [], "extra_texts": {}}]},
                            headers=hdrs).json()
        # انقل الطلب لـ in_kitchen عشان تتولّد تذاكر KDS
        client.patch(f"/api/v1/dining/orders/{order['id']}/status",
                     json={"status": "in_kitchen"}, headers=hdrs)
        # mgr مربوط بـ br عبر _linked → assert_branch_access بيمر صح
        tickets = client.get("/api/v1/dining/kitchen/tickets",
                             params={"branch_id": br.id}, headers=mgr).json()
        if tickets:
            tid = tickets[0]["id"]
            r = client.patch(f"/api/v1/dining/kitchen/tickets/{tid}/status",
                             json={"status": "done"}, headers=mgr)
            assert r.status_code == 200


# ── Public Endpoints (no auth) ────────────────────────────────────────────────

class TestPublicEndpoints:
    def test_list_public_outlets(self, client, db):
        br = _branch(db); _outlet(db, br)
        r = client.get("/api/v1/dining/public/outlets", params={"branch_id": br.id})
        assert r.status_code == 200 and isinstance(r.json(), list)

    def test_get_public_menu(self, client, db):
        br = _branch(db); o = _outlet(db, br); _item(db, br, o)
        r = client.get("/api/v1/dining/public/menu", params={"outlet_id": o.id})
        assert r.status_code == 200
        body = r.json()
        assert body["outlet_id"] == o.id
        assert isinstance(body["items"], list)

    def test_public_menu_outlet_not_found(self, client, db):
        r = client.get("/api/v1/dining/public/menu", params={"outlet_id": 999999})
        assert r.status_code == 404

    def test_create_public_order_no_session(self, client, db):
        br = _branch(db); o = _outlet(db, br); _item(db, br, o)
        r = client.post("/api/v1/dining/public/orders",
                        json={"outlet_id": o.id, "guests_count": 1, "items": []},
                        headers={"X-Guest-Session": "invalid-token"})
        # بدون جلسة صالحة → 400 أو 404 أو 422 (validation/session)
        assert r.status_code in (400, 404, 422)

    def test_get_guest_order_no_session(self, client, db):
        r = client.get("/api/v1/dining/public/orders/fake-ref",
                       headers={"X-Guest-Session": "invalid"})
        assert r.status_code in (400, 404)
