"""
tests/test_api/test_food_cost_report.py
Food Cost / COGS reporting — تكلفة نظرية (وصفة × كمية مباعة فعليًا) مقابل
الإيراد الفعلي، للدايننج الموحّد. راجع app.resort_os.food_cost_engine
للفورمولا الخام (مُختبرة بشكل منفصل ومستقل في test_engines/) — هنا بنختبر
التجميع من الداتابيز الحقيقية (وصفة + مبيعات مدفوعة فعليًا) اللي بتتغذى
للـ engine ده، وبعدين الـ HTTP endpoints (صلاحية مدير + فلترة المدى الزمني).

راجع DINING_CUTOVER_PLAN.md Batch 6 — بورتت من restaurant/cafe (اللي
اتحذفوا) لـ dining الموحّد. كان فيه كلاسين مكررين (Restaurant/Cafe) بنفس
السيناريوهات بالظبط — dining بيغطي الاتنين بـ outlet_type واحد.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.modules.dining import crud as dining_crud
from app.modules.dining import services as dining_services
from app.modules.dining.schemas import DiningItemRecipeLineCreate, OrderCreate, OrderItemCreate, OutletCreate


# ─────────────────────── Helpers ───────────────────────────────────────

def make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(name="Food Cost Branch", name_ar="فرع تكلفة الطعام",
               code=f"FC-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_outlet(db, branch, outlet_type="restaurant", revenue_account_code="4200"):
    return dining_services.create_outlet(db, OutletCreate(
        branch_id=branch.id, name=f"منفذ-{outlet_type}-{uuid.uuid4().hex[:6]}",
        outlet_type=outlet_type, revenue_account_code=revenue_account_code,
    ))


def make_item(db, branch, outlet, price=Decimal("55.00"), name="شاورما دجاج"):
    from app.modules.dining.models import DiningItem
    item = DiningItem(branch_id=branch.id, outlet_id=outlet.id, name=name, price=price, is_available=True)
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


def ensure_finance_accounts(db, branch, revenue_code="4200"):
    """كل حسابات الأستاذ اللي معاملة الدفع الصارمة (Gate 1B) محتاجاها فعليًا
    (Cash/فوليو/مخزون/COGS/إيراد المنفذ) — من غيرها post_simple_revenue_journal/
    _post_cogs_journal بيرفعوا FinancialConfigurationError (503) بدل ما
    يبتلعوا الفشل بصمت زي قبل. idempotent (query-or-create)."""
    from app.modules.finance.models import Account
    wanted = {
        "1100": ("Cash", "asset"),
        "1150": ("ذمم الفوليو", "asset"),
        "1200": ("مخزون البضاعة", "asset"),
        "5200": ("تكلفة البضاعة المباعة (COGS)", "expense"),
        revenue_code: ("إيراد المنفذ", "revenue"),
    }
    for code, (name, acc_type) in wanted.items():
        if not db.query(Account).filter_by(branch_id=branch.id, code=code).first():
            db.add(Account(branch_id=branch.id, code=code, name=name, account_type=acc_type))
    db.commit()


def make_paid_order(db, branch, outlet, item, quantity=2):
    ensure_finance_accounts(db, branch, revenue_code=outlet.revenue_account_code)
    data = OrderCreate(
        outlet_id=outlet.id, order_type="takeaway", guests_count=1,
        items=[OrderItemCreate(item_id=item.id, quantity=quantity)],
    )
    order = dining_services.create_order(db, branch.id, data, waiter_id=1)
    return dining_services.update_order_status(db, order.id, "paid")


class TestDiningFoodCostReport:
    """راجع app.modules.dining.services.get_food_cost_report."""

    def test_report_line_matches_engine_math(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("55.00"))
        beef = make_product(db, branch, cost_price=Decimal("180"))
        dining_services.add_recipe_line(
            db, item.id, DiningItemRecipeLineCreate(product_id=beef.id, quantity_per_unit=Decimal("0.1")),
        )  # unit cost = 0.1 * 180 = 18.00

        make_paid_order(db, branch, outlet, item, quantity=2)  # revenue = 110.00

        today = date.today()
        report = dining_services.get_food_cost_report(db, branch.id, today, today)
        line = next(l for l in report.lines if l.item_id == item.id)

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
        """(Gate 1B) طلب فيه صنفين — واحد بيتلغى بالكامل والتاني يفضل شغال،
        عشان الطلب يفضل بإجمالي موجب وقت الدفع (زي
        test_refunded_item_still_counted_towards_theoretical_cost بالظبط) —
        قبل Gate 1B كان ممكن ندفع طلب بإجمالي صفر (لو الصنف الوحيد اتلغى)،
        لكن دلوقتي INVALID_ORDER_TOTAL بيرفض ده عمدًا (راجع خطة Gate 1B)."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        ensure_finance_accounts(db, branch)
        item = make_item(db, branch, outlet)
        other_item = make_item(db, branch, outlet, name="عصير", price=Decimal("20.00"))
        data = OrderCreate(outlet_id=outlet.id, order_type="takeaway", guests_count=1,
                           items=[
                               OrderItemCreate(item_id=item.id, quantity=2),
                               OrderItemCreate(item_id=other_item.id, quantity=1),
                           ])
        order = dining_services.create_order(db, branch.id, data, waiter_id=1)
        dining_services.void_order_item(db, order.id, order.items[0].id, "غلط", voided_by=1)
        dining_services.update_order_status(db, order.id, "paid")

        today = date.today()
        report = dining_services.get_food_cost_report(db, branch.id, today, today)
        line = next(l for l in report.lines if l.item_id == item.id)
        assert line.quantity_sold == 0
        assert line.revenue == Decimal("0")

    def test_refunded_item_still_counted_towards_theoretical_cost(self, db):
        """مرتجع بعد الدفع — المكوّنات اتصرفت فعليًا وقت التحضير، فالكمية
        لازم تفضل معدودة في التكلفة النظرية رغم المرتجع المالي بعد كده.
        هنا طلب فيه صنفين مختلفين، بيترجع واحد بس — الطلب نفسه يفضل 'paid'
        (مش كل الأصناف اترجعت)، عشان نعزل سلوك الصنف عن سلوك الطلب."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        ensure_finance_accounts(db, branch)
        item = make_item(db, branch, outlet)
        other_item = make_item(db, branch, outlet, name="عصير", price=Decimal("20.00"))
        data = OrderCreate(
            outlet_id=outlet.id, order_type="takeaway", guests_count=1,
            items=[
                OrderItemCreate(item_id=item.id, quantity=2),
                OrderItemCreate(item_id=other_item.id, quantity=1),
            ],
        )
        order = dining_services.create_order(db, branch.id, data, waiter_id=1)
        order = dining_services.update_order_status(db, order.id, "paid")
        target_line = next(i for i in order.items if i.item_id == item.id)
        dining_services.refund_order_item(db, order.id, target_line.id, "عميل مش عايز", refunded_by=1)

        today = date.today()
        report = dining_services.get_food_cost_report(db, branch.id, today, today)
        line = next(l for l in report.lines if l.item_id == item.id)
        assert line.quantity_sold == 2
        assert line.revenue == Decimal("110.00")

    def test_fully_refunded_order_still_counted(self, db):
        """لما كل أصناف طلب مدفوع تترجع، الطلب نفسه بيتحول لـ status='refunded'
        (راجع services.refund_order_item) — لازم يفضل معدود في التقرير برضه،
        وإلا طلب كامل هيختفي تمامًا من تكلفة الطعام النظرية رغم إن التحضير
        الفعلي حصل. باج حقيقي اتكشف واتصلح أثناء كتابة الاختبار ده أصلًا."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        order = make_paid_order(db, branch, outlet, item, quantity=2)
        dining_services.refund_order_item(db, order.id, order.items[0].id, "عميل مش عايز", refunded_by=1)

        order_row = dining_crud.get_order(db, order.id)
        assert order_row.status == "refunded"  # تأكيد إن الطلب اتحول فعلاً

        today = date.today()
        report = dining_services.get_food_cost_report(db, branch.id, today, today)
        line = next(l for l in report.lines if l.item_id == item.id)
        assert line.quantity_sold == 2
        assert line.revenue == Decimal("110.00")

    def test_item_without_recipe_excluded_from_summary_but_shown_in_lines(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)  # مفيش وصفة
        make_paid_order(db, branch, outlet, item, quantity=2)

        today = date.today()
        report = dining_services.get_food_cost_report(db, branch.id, today, today)
        line = next(l for l in report.lines if l.item_id == item.id)

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
        outlet = make_outlet(db, branch)

        cheap_item = make_item(db, branch, outlet, price=Decimal("100.00"), name="صنف رخيص التكلفة")
        cheap_ingredient = make_product(db, branch, name="مكوّن رخيص", cost_price=Decimal("5"))
        dining_services.add_recipe_line(
            db, cheap_item.id, DiningItemRecipeLineCreate(product_id=cheap_ingredient.id, quantity_per_unit=Decimal("1")),
        )  # تكلفة 5 على سعر 100 = 5% — تحت الحد

        pricey_item = make_item(db, branch, outlet, price=Decimal("50.00"), name="صنف غالي التكلفة")
        pricey_ingredient = make_product(db, branch, name="مكوّن غالي", cost_price=Decimal("40"))
        dining_services.add_recipe_line(
            db, pricey_item.id, DiningItemRecipeLineCreate(product_id=pricey_ingredient.id, quantity_per_unit=Decimal("1")),
        )  # تكلفة 40 على سعر 50 = 80% — فوق الحد بكتير

        make_paid_order(db, branch, outlet, cheap_item, quantity=1)
        make_paid_order(db, branch, outlet, pricey_item, quantity=1)

        today = date.today()
        report = dining_services.get_food_cost_report(db, branch.id, today, today)
        alert_ids = {a.item_id for a in report.alerts}
        assert pricey_item.id in alert_ids
        assert cheap_item.id not in alert_ids

    def test_custom_threshold_pct_changes_alert_set(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("100.00"))
        ingredient = make_product(db, branch, cost_price=Decimal("20"))
        dining_services.add_recipe_line(
            db, item.id, DiningItemRecipeLineCreate(product_id=ingredient.id, quantity_per_unit=Decimal("1")),
        )  # تكلفة 20% بالظبط
        make_paid_order(db, branch, outlet, item, quantity=1)

        today = date.today()
        default_report = dining_services.get_food_cost_report(db, branch.id, today, today)
        assert default_report.alerts == []  # 20% < الحد الافتراضي 30%

        strict_report = dining_services.get_food_cost_report(
            db, branch.id, today, today, threshold_pct=Decimal("15"),
        )
        assert len(strict_report.alerts) == 1

    def test_trend_buckets_by_local_day_not_utc(self, db):
        """طلب اتعمل بتاريخ محدد — لازم يظهر في اليوم الصح بالـ trend، مش
        يوم تاني بسبب فرق UTC/توقيت القاهرة (راجع CLAUDE.md §13 ⓾). الصنف
        هنا لازم يكون معاه وصفة — الـ trend بيستبعد أصناف بدون وصفة عمداً
        (نفس استبعاد الملخص، راجع test_item_without_recipe_excluded_...)."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("55.00"))
        ingredient = make_product(db, branch, cost_price=Decimal("180"))
        dining_services.add_recipe_line(
            db, item.id, DiningItemRecipeLineCreate(product_id=ingredient.id, quantity_per_unit=Decimal("0.1")),
        )  # unit cost = 18.00
        order = make_paid_order(db, branch, outlet, item, quantity=2)

        yesterday = date.today() - timedelta(days=1)
        from app.resort_os.timezone_utils import local_date_to_utc_range
        from app.core.config import settings
        start, _ = local_date_to_utc_range(yesterday, settings.TIMEZONE)
        order_row = dining_crud.get_order(db, order.id)
        order_row.created_at = start + timedelta(hours=5)  # منتصف اليوم المحلي بالأمس
        db.commit()

        report = dining_services.get_food_cost_report(db, branch.id, yesterday, date.today())
        by_day = {point.date: point for point in report.trend}
        assert by_day[yesterday].revenue == Decimal("110.00")
        assert by_day[yesterday].theoretical_cost == Decimal("36.00")
        assert by_day[date.today()].revenue == Decimal("0")

    def test_date_range_excludes_orders_outside_range(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("55.00"))
        make_paid_order(db, branch, outlet, item, quantity=1)

        far_past_from = date.today() - timedelta(days=60)
        far_past_to = date.today() - timedelta(days=30)
        report = dining_services.get_food_cost_report(db, branch.id, far_past_from, far_past_to)
        line = next(l for l in report.lines if l.item_id == item.id)
        assert line.quantity_sold == 0
        assert line.revenue == Decimal("0")


class TestCafeOutletFoodCostReport:
    """يثبت إن outlet_type='cafe' بيشتغل بنفس آلية 'restaurant' بالظبط —
    مفيش كود خاص بأي outlet_type في منطق تكلفة الطعام."""

    def test_report_line_matches_engine_math(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch, outlet_type="cafe", revenue_account_code="4400")
        item = make_item(db, branch, outlet, price=Decimal("25.00"), name="قهوة عربية")
        beans = make_product(db, branch, name="بن قهوة", cost_price=Decimal("100"))
        dining_services.add_recipe_line(
            db, item.id, DiningItemRecipeLineCreate(product_id=beans.id, quantity_per_unit=Decimal("0.02")),
        )  # unit cost = 0.02 * 100 = 2.00

        make_paid_order(db, branch, outlet, item, quantity=3)  # revenue = 75.00

        today = date.today()
        report = dining_services.get_food_cost_report(db, branch.id, today, today)
        line = next(l for l in report.lines if l.item_id == item.id)

        assert line.has_recipe is True
        assert line.quantity_sold == 3
        assert line.revenue == Decimal("75.00")
        assert line.theoretical_unit_cost == Decimal("2.00")
        assert line.theoretical_total_cost == Decimal("6.00")
        assert line.food_cost_pct == Decimal("8.00")  # 6/75*100
        assert line.exceeds_threshold is False


# ─────────────────────── HTTP ──────────────────────────────────────────

def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="Food Cost HTTP Branch", name_ar="فرع HTTP",
               code=f"FCH-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_outlet_committed(db, branch, outlet_type="restaurant", revenue_account_code="4200"):
    return dining_services.create_outlet(db, OutletCreate(
        branch_id=branch.id, name=f"منفذ-HTTP-{outlet_type}-{uuid.uuid4().hex[:6]}",
        outlet_type=outlet_type, revenue_account_code=revenue_account_code,
    ))


def make_item_committed(db, branch, outlet, price=Decimal("55.00"), name="برجر اختبار"):
    from app.modules.dining.models import DiningItem
    item = DiningItem(branch_id=branch.id, outlet_id=outlet.id, name=name, price=price, is_available=True)
    db.add(item)
    db.commit()
    return item


def make_branch_linked_headers(db, branch, role="manager") -> dict[str, str]:
    """Gate 1B: PATCH /dining/orders/{id}/status بقى بيفرض assert_branch_access
    (super_admin بس بيتخطاه — manager مش استثناء) — manager_headers المشترك
    (conftest.py) بلا Employee/فرع خالص، فمحتاج مستخدم Employee-linked جديد."""
    from datetime import date, timedelta
    from decimal import Decimal as _D
    from tests.conftest import _create_test_user, _make_token, open_cashier_shift
    from app.modules.hr.models import Employee

    email = f"{role}-{uuid.uuid4().hex[:10]}@test.local"
    user_id = _create_test_user(email, role)
    emp = Employee(
        branch_id=branch.id, employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
        full_name=f"{role} اختبار تكلفة الطعام", national_id="29001011234567",
        position=role, department="F&B", basic_salary=_D("4000.00"),
        hire_date=date.today() - timedelta(days=365), user_id=user_id,
    )
    db.add(emp)
    db.commit()
    # Gate 4A: أي مشغّل POS بيحصّل دفع مباشر لازم يكون له وردية مفتوحة.
    open_cashier_shift(db, branch.id, user_id)
    return {"Authorization": f"Bearer {_make_token(email)}"}


class TestFoodCostReportHTTP:

    def test_requires_auth(self, client: TestClient, db):
        branch = make_branch_committed(db)
        resp = client.get("/api/v1/dining/reports/food-cost", params={"branch_id": branch.id})
        assert resp.status_code == 401

    def test_requires_manager_level(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/dining/reports/food-cost",
            params={"branch_id": branch.id},
            headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_manager_gets_report_with_defaults(self, client: TestClient, db, manager_headers, waiter_headers):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        ensure_finance_accounts(db, branch)
        item = make_item_committed(db, branch, outlet)

        manager_linked = make_branch_linked_headers(db, branch)
        order = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={"outlet_id": outlet.id, "order_type": "takeaway", "guests_count": 1,
                  "items": [{"item_id": item.id, "quantity": 2}]},
            headers=waiter_headers,
        ).json()
        paid = client.patch(
            f"/api/v1/dining/orders/{order['id']}/status",
            json={"status": "paid"}, headers=manager_linked,
        )
        assert paid.status_code == 200, paid.text

        resp = client.get(
            "/api/v1/dining/reports/food-cost",
            params={"branch_id": branch.id},
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        line = next(l for l in body["lines"] if l["item_id"] == item.id)
        assert line["quantity_sold"] == 2
        assert Decimal(str(line["revenue"])) == Decimal("110.00")
        assert body["summary"]["branch_id"] == branch.id

    def test_date_from_after_date_to_rejected(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/dining/reports/food-cost",
            params={
                "branch_id": branch.id,
                "date_from": str(date.today()),
                "date_to": str(date.today() - timedelta(days=1)),
            },
            headers=manager_headers,
        )
        assert resp.status_code == 400

    def test_export_returns_valid_excel_for_manager(self, client: TestClient, db, manager_headers, waiter_headers):
        """wagdy.md #16: تصدير Excel لتقرير تكلفة الطعام."""
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        item = make_item_committed(db, branch, outlet)
        order = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={"outlet_id": outlet.id, "order_type": "takeaway", "guests_count": 1,
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()
        client.patch(
            f"/api/v1/dining/orders/{order['id']}/status",
            json={"status": "paid"}, headers=manager_headers,
        )

        resp = client.get(
            f"/api/v1/dining/outlets/{outlet.id}/reports/food-cost/export",
            params={}, headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert len(resp.content) > 0

    def test_export_requires_manager(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        resp = client.get(
            f"/api/v1/dining/outlets/{outlet.id}/reports/food-cost/export",
            params={}, headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_cafe_outlet_requires_manager_level(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch, outlet_type="cafe", revenue_account_code="4400")
        resp = client.get(
            f"/api/v1/dining/outlets/{outlet.id}/reports/food-cost",
            params={},
            headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_cafe_outlet_manager_gets_report(self, client: TestClient, db, manager_headers, waiter_headers):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch, outlet_type="cafe", revenue_account_code="4400")
        ensure_finance_accounts(db, branch, revenue_code="4400")
        item = make_item_committed(db, branch, outlet, price=Decimal("25.00"), name="قهوة اختبار")

        manager_linked = make_branch_linked_headers(db, branch)
        order = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={"outlet_id": outlet.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 2}]},
            headers=waiter_headers,
        ).json()
        paid = client.patch(
            f"/api/v1/dining/orders/{order['id']}/status",
            json={"status": "paid"}, headers=manager_linked,
        )
        assert paid.status_code == 200, paid.text

        resp = client.get(
            f"/api/v1/dining/outlets/{outlet.id}/reports/food-cost",
            params={},
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        line = next(l for l in body["lines"] if l["item_id"] == item.id)
        assert line["quantity_sold"] == 2

    def test_cafe_outlet_export_returns_valid_excel(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch, outlet_type="cafe", revenue_account_code="4400")
        resp = client.get(
            f"/api/v1/dining/outlets/{outlet.id}/reports/food-cost/export",
            params={}, headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
