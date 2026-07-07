"""
tests/test_api/test_food_cost_report.py
Food Cost / COGS reporting — تكلفة نظرية (وصفة × كمية مباعة فعليًا) مقابل
الإيراد الفعلي، لكل من restaurant وcafe. راجع app.resort_os.food_cost_engine
للفورمولا الخام (مُختبرة بشكل منفصل ومستقل في test_engines/) — هنا بنختبر
التجميع من الداتابيز الحقيقية (وصفة + مبيعات مدفوعة فعليًا) اللي بتتغذى
للـ engine ده، وبعدين الـ HTTP endpoints (صلاحية مدير + فلترة المدى الزمني).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.modules.restaurant.schemas import MenuItemRecipeLineCreate, OrderCreate, OrderItemCreate
from app.modules.restaurant import services as restaurant_services
from app.modules.restaurant import crud as restaurant_crud
from app.modules.cafe.schemas import CafeItemRecipeLineCreate, CafeOrderCreate, CafeOrderItemCreate
from app.modules.cafe import services as cafe_services


# ─────────────────────── Helpers — restaurant ─────────────────────────

def make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(name="Food Cost Branch", name_ar="فرع تكلفة الطعام",
               code=f"FC-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_menu_item(db, branch, price=Decimal("55.00"), name="شاورما دجاج"):
    from app.modules.restaurant.models import MenuItem
    item = MenuItem(branch_id=branch.id, name=name, price=price, is_available=True)
    db.add(item)
    db.commit()
    return item


def make_product(db, branch, name="لحم مفروم", unit="kg", cost_price=Decimal("180")):
    from app.modules.inventory.schemas import ProductCreate, WarehouseCreate
    from app.modules.inventory import services as inventory_services

    warehouse = inventory_services.create_warehouse(
        db, WarehouseCreate(branch_id=branch.id, name="مخزن اختبار", code=f"WH-{uuid.uuid4().hex[:6].upper()}"),
    )
    product = inventory_services.create_product(
        db, ProductCreate(
            branch_id=branch.id, warehouse_id=warehouse.id,
            name=name, sku=f"SKU-{uuid.uuid4().hex[:6].upper()}", unit=unit,
            cost_price=cost_price,
        ),
    )
    return product


def make_paid_order(db, branch, item, quantity=2):
    data = OrderCreate(
        order_type="takeaway", guests_count=1,
        items=[OrderItemCreate(menu_item_id=item.id, quantity=quantity)],
    )
    order = restaurant_services.create_order(db, branch.id, data, waiter_id=1)
    return restaurant_services.update_order_status(db, order.id, "paid")


# ─────────────────────── Helpers — cafe ───────────────────────────────

def make_cafe_item(db, branch, price=Decimal("25.00"), name="قهوة عربية"):
    from app.modules.cafe.models import CafeItem
    item = CafeItem(branch_id=branch.id, name=name, price=price, is_available=True)
    db.add(item)
    db.commit()
    return item


def make_cafe_paid_order(db, branch, item, quantity=2):
    data = CafeOrderCreate(
        branch_id=branch.id, order_type="takeaway",
        items=[CafeOrderItemCreate(item_id=item.id, quantity=quantity)],
    )
    order = cafe_services.create_order(db, data, waiter_id=1)
    return cafe_services.update_order_status(db, order.id, "paid")


class TestRestaurantFoodCostReport:
    """راجع app.modules.restaurant.services.get_food_cost_report."""

    def test_report_line_matches_engine_math(self, db):
        branch = make_branch(db)
        item = make_menu_item(db, branch, price=Decimal("55.00"))
        beef = make_product(db, branch, cost_price=Decimal("180"))
        restaurant_services.add_recipe_line(
            db, item.id, MenuItemRecipeLineCreate(product_id=beef.id, quantity_per_unit=Decimal("0.1")),
        )  # unit cost = 0.1 * 180 = 18.00

        make_paid_order(db, branch, item, quantity=2)  # revenue = 110.00

        today = date.today()
        report = restaurant_services.get_food_cost_report(db, branch.id, today, today)
        line = next(l for l in report.lines if l.menu_item_id == item.id)

        assert line.has_recipe is True
        assert line.quantity_sold == 2
        assert line.revenue == Decimal("110.00")
        assert line.theoretical_unit_cost == Decimal("18.00")
        assert line.theoretical_total_cost == Decimal("36.00")
        assert line.food_cost_pct == Decimal("32.73")  # 36/110*100 rounded
        assert line.exceeds_threshold is True  # > الحد الافتراضي 30%

        assert report.summary.total_revenue == Decimal("110.00")
        assert report.summary.total_theoretical_cost == Decimal("36.00")
        assert report.summary.food_cost_pct == Decimal("32.73")
        assert line in report.alerts

    def test_cancelled_item_excluded_from_sales(self, db):
        branch = make_branch(db)
        item = make_menu_item(db, branch)
        data = OrderCreate(order_type="takeaway", guests_count=1,
                           items=[OrderItemCreate(menu_item_id=item.id, quantity=2)])
        order = restaurant_services.create_order(db, branch.id, data, waiter_id=1)
        restaurant_services.void_order_item(db, order.id, order.items[0].id, "غلط", voided_by=1)
        restaurant_services.update_order_status(db, order.id, "paid")

        today = date.today()
        report = restaurant_services.get_food_cost_report(db, branch.id, today, today)
        line = next(l for l in report.lines if l.menu_item_id == item.id)
        assert line.quantity_sold == 0
        assert line.revenue == Decimal("0")

    def test_refunded_item_still_counted_towards_theoretical_cost(self, db):
        """مرتجع بعد الدفع — المكوّنات اتصرفت فعليًا وقت التحضير، فالكمية
        لازم تفضل معدودة في التكلفة النظرية رغم المرتجع المالي بعد كده.
        هنا طلب فيه صنفين مختلفين، بيترجع واحد بس — الطلب نفسه يفضل 'paid'
        (مش كل الأصناف اترجعت)، عشان نعزل سلوك الصنف عن سلوك الطلب."""
        branch = make_branch(db)
        item = make_menu_item(db, branch)
        other_item = make_menu_item(db, branch, name="عصير", price=Decimal("20.00"))
        data = OrderCreate(
            order_type="takeaway", guests_count=1,
            items=[
                OrderItemCreate(menu_item_id=item.id, quantity=2),
                OrderItemCreate(menu_item_id=other_item.id, quantity=1),
            ],
        )
        order = restaurant_services.create_order(db, branch.id, data, waiter_id=1)
        order = restaurant_services.update_order_status(db, order.id, "paid")
        target_line = next(i for i in order.items if i.menu_item_id == item.id)
        restaurant_services.refund_order_item(db, order.id, target_line.id, "عميل مش عايز", refunded_by=1)

        today = date.today()
        report = restaurant_services.get_food_cost_report(db, branch.id, today, today)
        line = next(l for l in report.lines if l.menu_item_id == item.id)
        assert line.quantity_sold == 2
        assert line.revenue == Decimal("110.00")

    def test_fully_refunded_order_still_counted(self, db):
        """لما كل أصناف طلب مدفوع تترجع، الطلب نفسه بيتحول لـ status='refunded'
        (راجع services.refund_order_item) — لازم يفضل معدود في التقرير برضه،
        وإلا طلب كامل هيختفي تمامًا من تكلفة الطعام النظرية رغم إن التحضير
        الفعلي حصل. باج حقيقي اتكشف واتصلح أثناء كتابة الاختبار ده."""
        branch = make_branch(db)
        item = make_menu_item(db, branch)
        order = make_paid_order(db, branch, item, quantity=2)
        restaurant_services.refund_order_item(db, order.id, order.items[0].id, "عميل مش عايز", refunded_by=1)

        order_row = restaurant_crud.get_order(db, order.id)
        assert order_row.status == "refunded"  # تأكيد إن الطلب اتحول فعلاً

        today = date.today()
        report = restaurant_services.get_food_cost_report(db, branch.id, today, today)
        line = next(l for l in report.lines if l.menu_item_id == item.id)
        assert line.quantity_sold == 2
        assert line.revenue == Decimal("110.00")

    def test_item_without_recipe_excluded_from_summary_but_shown_in_lines(self, db):
        branch = make_branch(db)
        item = make_menu_item(db, branch)  # مفيش وصفة
        make_paid_order(db, branch, item, quantity=2)

        today = date.today()
        report = restaurant_services.get_food_cost_report(db, branch.id, today, today)
        line = next(l for l in report.lines if l.menu_item_id == item.id)

        assert line.has_recipe is False
        assert line.food_cost_pct is None
        assert line.gross_margin_pct is None
        assert line.exceeds_threshold is False  # مينفعش نُنذر على تكلفة غير معروفة
        assert line not in report.alerts

        assert report.summary.items_missing_recipe == 1
        assert report.summary.items_missing_recipe_revenue == Decimal("110.00")
        # مُستبعد تمامًا من الإجمالي المالي (مش معتبر تكلفته صفر)
        assert report.summary.total_revenue == Decimal("0")
        assert report.summary.total_theoretical_cost == Decimal("0")
        assert report.summary.food_cost_pct is None

    def test_alerts_only_include_items_exceeding_threshold(self, db):
        branch = make_branch(db)

        cheap_item = make_menu_item(db, branch, price=Decimal("100.00"), name="صنف رخيص التكلفة")
        cheap_ingredient = make_product(db, branch, name="مكوّن رخيص", cost_price=Decimal("5"))
        restaurant_services.add_recipe_line(
            db, cheap_item.id, MenuItemRecipeLineCreate(product_id=cheap_ingredient.id, quantity_per_unit=Decimal("1")),
        )  # تكلفة 5 على سعر 100 = 5% — تحت الحد

        pricey_item = make_menu_item(db, branch, price=Decimal("50.00"), name="صنف غالي التكلفة")
        pricey_ingredient = make_product(db, branch, name="مكوّن غالي", cost_price=Decimal("40"))
        restaurant_services.add_recipe_line(
            db, pricey_item.id, MenuItemRecipeLineCreate(product_id=pricey_ingredient.id, quantity_per_unit=Decimal("1")),
        )  # تكلفة 40 على سعر 50 = 80% — فوق الحد بكتير

        make_paid_order(db, branch, cheap_item, quantity=1)
        make_paid_order(db, branch, pricey_item, quantity=1)

        today = date.today()
        report = restaurant_services.get_food_cost_report(db, branch.id, today, today)
        alert_ids = {a.menu_item_id for a in report.alerts}
        assert pricey_item.id in alert_ids
        assert cheap_item.id not in alert_ids

    def test_custom_threshold_pct_changes_alert_set(self, db):
        branch = make_branch(db)
        item = make_menu_item(db, branch, price=Decimal("100.00"))
        ingredient = make_product(db, branch, cost_price=Decimal("20"))
        restaurant_services.add_recipe_line(
            db, item.id, MenuItemRecipeLineCreate(product_id=ingredient.id, quantity_per_unit=Decimal("1")),
        )  # تكلفة 20% بالظبط
        make_paid_order(db, branch, item, quantity=1)

        today = date.today()
        default_report = restaurant_services.get_food_cost_report(db, branch.id, today, today)
        assert default_report.alerts == []  # 20% < الحد الافتراضي 30%

        strict_report = restaurant_services.get_food_cost_report(
            db, branch.id, today, today, threshold_pct=Decimal("15"),
        )
        assert len(strict_report.alerts) == 1

    def test_trend_buckets_by_local_day_not_utc(self, db):
        """طلب اتعمل بتاريخ محدد — لازم يظهر في اليوم الصح بالـ trend، مش
        يوم تاني بسبب فرق UTC/توقيت القاهرة (راجع CLAUDE.md §13 ⓾). الصنف
        هنا لازم يكون معاه وصفة — الـ trend بيستبعد أصناف بدون وصفة عمداً
        (نفس استبعاد الملخص، راجع test_item_without_recipe_excluded_...)."""
        branch = make_branch(db)
        item = make_menu_item(db, branch, price=Decimal("55.00"))
        ingredient = make_product(db, branch, cost_price=Decimal("180"))
        restaurant_services.add_recipe_line(
            db, item.id, MenuItemRecipeLineCreate(product_id=ingredient.id, quantity_per_unit=Decimal("0.1")),
        )  # unit cost = 18.00
        order = make_paid_order(db, branch, item, quantity=2)

        yesterday = date.today() - timedelta(days=1)
        from app.resort_os.timezone_utils import local_date_to_utc_range
        from app.core.config import settings
        start, _ = local_date_to_utc_range(yesterday, settings.TIMEZONE)
        order_row = restaurant_crud.get_order(db, order.id)
        order_row.created_at = start + timedelta(hours=5)  # منتصف اليوم المحلي بالأمس
        db.commit()

        report = restaurant_services.get_food_cost_report(db, branch.id, yesterday, date.today())
        by_day = {point.date: point for point in report.trend}
        assert by_day[yesterday].revenue == Decimal("110.00")
        assert by_day[yesterday].theoretical_cost == Decimal("36.00")
        assert by_day[date.today()].revenue == Decimal("0")

    def test_date_range_excludes_orders_outside_range(self, db):
        branch = make_branch(db)
        item = make_menu_item(db, branch, price=Decimal("55.00"))
        make_paid_order(db, branch, item, quantity=1)

        far_past_from = date.today() - timedelta(days=60)
        far_past_to = date.today() - timedelta(days=30)
        report = restaurant_services.get_food_cost_report(db, branch.id, far_past_from, far_past_to)
        line = next(l for l in report.lines if l.menu_item_id == item.id)
        assert line.quantity_sold == 0
        assert line.revenue == Decimal("0")


class TestCafeFoodCostReport:
    """نفس اختبارات restaurant الأساسية، بس على جداول cafe."""

    def test_report_line_matches_engine_math(self, db):
        branch = make_branch(db)
        item = make_cafe_item(db, branch, price=Decimal("25.00"))
        beans = make_product(db, branch, name="بن قهوة", cost_price=Decimal("100"))
        cafe_services.add_recipe_line(
            db, item.id, CafeItemRecipeLineCreate(product_id=beans.id, quantity_per_unit=Decimal("0.02")),
        )  # unit cost = 0.02 * 100 = 2.00

        make_cafe_paid_order(db, branch, item, quantity=3)  # revenue = 75.00

        today = date.today()
        report = cafe_services.get_food_cost_report(db, branch.id, today, today)
        line = next(l for l in report.lines if l.cafe_item_id == item.id)

        assert line.has_recipe is True
        assert line.quantity_sold == 3
        assert line.revenue == Decimal("75.00")
        assert line.theoretical_unit_cost == Decimal("2.00")
        assert line.theoretical_total_cost == Decimal("6.00")
        assert line.food_cost_pct == Decimal("8.00")  # 6/75*100
        assert line.exceeds_threshold is False

    def test_cancelled_item_excluded_from_sales(self, db):
        branch = make_branch(db)
        item = make_cafe_item(db, branch)
        data = CafeOrderCreate(branch_id=branch.id, order_type="takeaway",
                               items=[CafeOrderItemCreate(item_id=item.id, quantity=2)])
        order = cafe_services.create_order(db, data, waiter_id=1)
        cafe_services.void_order_item(db, order.id, order.items[0].id, "غلط", voided_by=1)
        cafe_services.update_order_status(db, order.id, "paid")

        today = date.today()
        report = cafe_services.get_food_cost_report(db, branch.id, today, today)
        line = next(l for l in report.lines if l.cafe_item_id == item.id)
        assert line.quantity_sold == 0

    def test_item_without_recipe_excluded_from_summary(self, db):
        branch = make_branch(db)
        item = make_cafe_item(db, branch)
        make_cafe_paid_order(db, branch, item, quantity=2)

        today = date.today()
        report = cafe_services.get_food_cost_report(db, branch.id, today, today)
        line = next(l for l in report.lines if l.cafe_item_id == item.id)
        assert line.has_recipe is False
        assert report.summary.items_missing_recipe == 1
        assert report.summary.total_revenue == Decimal("0")


# ─────────────────────── HTTP ──────────────────────────────────────────

def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="Food Cost HTTP Branch", name_ar="فرع HTTP",
               code=f"FCH-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_menu_item_committed(db, branch, price=Decimal("55.00")):
    from app.modules.restaurant.models import MenuItem
    item = MenuItem(branch_id=branch.id, name="برجر اختبار", price=price, is_available=True)
    db.add(item)
    db.commit()
    return item


def make_cafe_item_committed(db, branch, price=Decimal("25.00")):
    from app.modules.cafe.models import CafeItem
    item = CafeItem(branch_id=branch.id, name="قهوة اختبار", price=price, is_available=True)
    db.add(item)
    db.commit()
    return item


class TestFoodCostReportHTTP:

    def test_requires_auth(self, client: TestClient, db):
        branch = make_branch_committed(db)
        resp = client.get("/api/v1/restaurant/reports/food-cost", params={"branch_id": branch.id})
        assert resp.status_code == 401

    def test_requires_manager_level(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/restaurant/reports/food-cost",
            params={"branch_id": branch.id},
            headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_manager_gets_report_with_defaults(self, client: TestClient, db, manager_headers, waiter_headers):
        branch = make_branch_committed(db)
        item = make_menu_item_committed(db, branch)

        order = client.post(
            "/api/v1/restaurant/orders", params={"branch_id": branch.id},
            json={"order_type": "takeaway", "guests_count": 1,
                  "items": [{"menu_item_id": item.id, "quantity": 2}]},
            headers=waiter_headers,
        ).json()
        client.patch(
            f"/api/v1/restaurant/orders/{order['id']}/status",
            json={"status": "paid"}, headers=manager_headers,
        )

        resp = client.get(
            "/api/v1/restaurant/reports/food-cost",
            params={"branch_id": branch.id},
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        line = next(l for l in body["lines"] if l["menu_item_id"] == item.id)
        assert line["quantity_sold"] == 2
        assert Decimal(str(line["revenue"])) == Decimal("110.00")
        assert body["summary"]["branch_id"] == branch.id

    def test_date_from_after_date_to_rejected(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/restaurant/reports/food-cost",
            params={
                "branch_id": branch.id,
                "date_from": str(date.today()),
                "date_to": str(date.today() - timedelta(days=1)),
            },
            headers=manager_headers,
        )
        assert resp.status_code == 400

    def test_cafe_requires_manager_level(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/cafe/reports/food-cost",
            params={"branch_id": branch.id},
            headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_cafe_manager_gets_report(self, client: TestClient, db, manager_headers, waiter_headers):
        branch = make_branch_committed(db)
        item = make_cafe_item_committed(db, branch)

        order = client.post(
            "/api/v1/cafe/orders", params={"branch_id": branch.id},
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 2}]},
            headers=waiter_headers,
        ).json()
        client.patch(
            f"/api/v1/cafe/orders/{order['id']}/status",
            json={"status": "paid"}, headers=manager_headers,
        )

        resp = client.get(
            "/api/v1/cafe/reports/food-cost",
            params={"branch_id": branch.id},
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        line = next(l for l in body["lines"] if l["cafe_item_id"] == item.id)
        assert line["quantity_sold"] == 2
