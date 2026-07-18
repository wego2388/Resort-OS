"""
tests/test_api/test_menu_item_variants.py
متغيّرات حقيقية (Variants) للدايننج — سعر ووصفة مستقلين تمامًا عن الصنف
الأساسي لكل حجم/نوع (مثال: كابتشينو صغير/كبير)، مختلف عن extras (رسم
إضافي فوق وصفة ثابتة). راجع app.modules.dining.models.DiningItemVariant
للتبرير الكامل.

بيغطي: CRUD المتغيّر + وصفته، إجبار اختيار متغيّر وقت الطلب لو الصنف عنده
متغيّرات، السعر الصح بيتسجّل على الطلب، خصم المخزون بيستخدم وصفة المتغيّر
مش وصفة الصنف الأساسي، وتقرير تكلفة الطعام بيفصل كل متغيّر في صف مستقل من
غير ازدواج في الإجمالي.

راجع DINING_CUTOVER_PLAN.md Batch 6 — بورتت من restaurant/cafe (اللي
اتحذفوا) لـ dining الموحّد. كان فيه كلاسين مكررين (Restaurant/Cafe) بنفس
السيناريوهات بالظبط — dining بيغطي الاتنين بـ outlet_type واحد فمفيش داعي
للتكرار، ماعدا التأكيد إن outlet_type='cafe' بيشتغل بنفس آلية 'restaurant'
(TestCafeOutletVariants تحت).
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.modules.dining import crud as dining_crud
from app.modules.dining import services as dining_services
from app.modules.dining.schemas import (
    DiningItemRecipeLineCreate, DiningItemVariantCreate, DiningItemVariantRecipeLineCreate,
    OrderCreate, OrderItemCreate, OutletCreate,
)
from app.modules.inventory import crud as inventory_crud


# ─────────────────────── Helpers ───────────────────────────────────────

def make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(name="Variants Branch", name_ar="فرع المتغيّرات",
               code=f"VAR-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_outlet(db, branch, outlet_type="restaurant", revenue_account_code="4200"):
    return dining_services.create_outlet(db, OutletCreate(
        branch_id=branch.id, name=f"منفذ-{outlet_type}-{uuid.uuid4().hex[:6]}",
        outlet_type=outlet_type, revenue_account_code=revenue_account_code,
    ))


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


def make_item(db, branch, outlet, price=Decimal("25.00"), name="كابتشينو"):
    from app.modules.dining.models import DiningItem
    item = DiningItem(branch_id=branch.id, outlet_id=outlet.id, name=name, price=price, is_available=True)
    db.add(item)
    db.commit()
    return item


def make_product(db, branch, name="حليب", unit="liter", cost_price=Decimal("0.05")):
    """كمية الوصفة في التستات دي (120/200) بتمثّل مل الحليب رمزيًا — الوحدة
    الحقيقية نفسها مش موضوع الاختبار، راجع Product.unit enum. current_stock
    بيتصفّر افتراضيًا؛ consume_stock بيسمح بمخزون سالب هنا (نفس مسار
    الوصفة الحقيقية _deduct_inventory_for_order، allow_negative=True)."""
    from app.modules.inventory.schemas import ProductCreate, WarehouseCreate
    from app.modules.inventory import services as inventory_services

    warehouse = inventory_services.create_warehouse(
        db, WarehouseCreate(branch_id=branch.id, name="مخزن اختبار", code=f"WH-{uuid.uuid4().hex[:6].upper()}"),
    )
    return inventory_services.create_product(
        db, ProductCreate(
            branch_id=branch.id, warehouse_id=warehouse.id,
            name=name, sku=f"SKU-{uuid.uuid4().hex[:6].upper()}", unit=unit,
            cost_price=cost_price,
        ),
    )


# ─────────────────────── Variant CRUD ──────────────────────────────────

class TestDiningVariantCrud:
    def test_add_variant_requires_manager(self, client: TestClient, db, waiter_headers):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        resp = client.post(
            f"/api/v1/dining/items/{item.id}/variants",
            json={"name": "كبير", "price": "35.00"},
            headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_add_variant_success(self, client: TestClient, db, manager_headers):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        resp = client.post(
            f"/api/v1/dining/items/{item.id}/variants",
            json={"name": "كبير", "price": "35.00"},
            headers=manager_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "كبير"
        assert Decimal(str(body["price"])) == Decimal("35.00")
        assert Decimal(str(body["computed_cost"])) == Decimal("0")  # مفيش وصفة لسه

        # الصنف بيظهر معاه المتغيّر في GET
        item_resp = client.get(
            f"/api/v1/dining/outlets/{outlet.id}/items",
            params={"available_only": False},
            headers=manager_headers,
        )
        found = next(i for i in item_resp.json() if i["id"] == item.id)
        assert len(found["variants"]) == 1
        assert found["variants"][0]["name"] == "كبير"

    def test_duplicate_variant_name_rejected(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        dining_services.add_variant(db, item.id, DiningItemVariantCreate(name="صغير", price=Decimal("25")))
        with pytest.raises(ValueError, match="متغيّر"):
            dining_services.add_variant(db, item.id, DiningItemVariantCreate(name="صغير", price=Decimal("30")))

    def test_update_and_delete_variant(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        variant = dining_services.add_variant(db, item.id, DiningItemVariantCreate(name="كبير", price=Decimal("35")))

        from app.modules.dining.schemas import DiningItemVariantUpdate
        updated = dining_services.update_variant(db, variant.id, DiningItemVariantUpdate(price=Decimal("40")))
        assert updated.price == Decimal("40")

        dining_services.remove_variant(db, variant.id)
        assert dining_crud.get_variant(db, variant.id) is None

    def test_variant_recipe_line_crud(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        milk = make_product(db, branch, name="حليب", cost_price=Decimal("0.05"))
        variant = dining_services.add_variant(db, item.id, DiningItemVariantCreate(name="كبير", price=Decimal("35")))

        line = dining_services.add_variant_recipe_line(
            db, variant.id, DiningItemVariantRecipeLineCreate(product_id=milk.id, quantity_per_unit=Decimal("200")),
        )
        assert line.quantity_per_unit == Decimal("200")

        # نفس المنتج مرتين مرفوض
        with pytest.raises(ValueError, match="مضاف بالفعل"):
            dining_services.add_variant_recipe_line(
                db, variant.id, DiningItemVariantRecipeLineCreate(product_id=milk.id, quantity_per_unit=Decimal("50")),
            )

        db.refresh(variant)
        assert dining_services.compute_variant_cost(variant) == Decimal("10.00")  # 200*0.05

        from app.modules.dining.schemas import DiningItemVariantRecipeLineUpdate
        dining_services.update_variant_recipe_line(db, line.id, DiningItemVariantRecipeLineUpdate(quantity_per_unit=Decimal("100")))
        db.refresh(variant)
        assert dining_services.compute_variant_cost(variant) == Decimal("5.00")

        dining_services.remove_variant_recipe_line(db, line.id)
        assert dining_crud.get_variant_recipe_line(db, line.id) is None


# ─────────────────────── Ordering with variants ─────────────────────────

class TestDiningOrderWithVariant:
    def _setup_item_with_two_variants(self, db, branch, outlet):
        item = make_item(db, branch, outlet, price=Decimal("25.00"), name="كابتشينو")
        milk = make_product(db, branch, name="حليب", cost_price=Decimal("0.05"))

        small = dining_services.add_variant(db, item.id, DiningItemVariantCreate(name="صغير", price=Decimal("25.00")))
        dining_services.add_variant_recipe_line(
            db, small.id, DiningItemVariantRecipeLineCreate(product_id=milk.id, quantity_per_unit=Decimal("120")),
        )
        large = dining_services.add_variant(db, item.id, DiningItemVariantCreate(name="كبير", price=Decimal("35.00")))
        dining_services.add_variant_recipe_line(
            db, large.id, DiningItemVariantRecipeLineCreate(product_id=milk.id, quantity_per_unit=Decimal("200")),
        )
        return item, milk, small, large

    def test_order_without_variant_rejected_when_item_has_variants(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item, _milk, _small, _large = self._setup_item_with_two_variants(db, branch, outlet)

        data = OrderCreate(outlet_id=outlet.id, order_type="takeaway", guests_count=1,
                           items=[OrderItemCreate(item_id=item.id, quantity=1)])
        with pytest.raises(ValueError, match="لازم تختار"):
            dining_services.create_order(db, branch.id, data, waiter_id=1)

    def test_order_with_unknown_variant_rejected(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item, _milk, _small, _large = self._setup_item_with_two_variants(db, branch, outlet)
        other_item = make_item(db, branch, outlet, name="غير ذلك")

        data = OrderCreate(outlet_id=outlet.id, order_type="takeaway", guests_count=1,
                           items=[OrderItemCreate(item_id=item.id, quantity=1, variant_id=999999)])
        with pytest.raises(ValueError, match="غير موجود"):
            dining_services.create_order(db, branch.id, data, waiter_id=1)

        # مفيش متغيّرات على الصنف التاني — تحديد variant_id مرفوض برضه
        data2 = OrderCreate(outlet_id=outlet.id, order_type="takeaway", guests_count=1,
                            items=[OrderItemCreate(item_id=other_item.id, quantity=1, variant_id=1)])
        with pytest.raises(ValueError, match="مفهوش متغيّرات"):
            dining_services.create_order(db, branch.id, data2, waiter_id=1)

    def test_order_uses_variant_price_and_deducts_variant_recipe(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        ensure_finance_accounts(db, branch)
        item, milk, small, large = self._setup_item_with_two_variants(db, branch, outlet)
        stock_before = inventory_crud.get_product(db, milk.id).current_stock

        data = OrderCreate(outlet_id=outlet.id, order_type="takeaway", guests_count=1,
                           items=[OrderItemCreate(item_id=item.id, quantity=2, variant_id=large.id)])
        order = dining_services.create_order(db, branch.id, data, waiter_id=1)

        assert order.subtotal == Decimal("70.00")  # 35 × 2 (سعر المتغيّر الكبير، مش سعر الصنف الأساسي 25)
        assert order.items[0].unit_price == Decimal("35.00")
        assert order.items[0].variant_id == large.id
        assert "كبير" in order.items[0].name

        order = dining_services.update_order_status(db, order.id, "paid")

        stock_after = inventory_crud.get_product(db, milk.id).current_stock
        # وصفة الحجم الكبير (200 مل) × كمية 2 = 400 مل اتخصمت — مش وصفة
        # الصغير (120 مل) ولا وصفة الصنف الأساسي (مفيش وصفة أصلاً هنا)
        assert stock_before - stock_after == Decimal("400")

    def test_small_variant_deducts_its_own_smaller_recipe(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        ensure_finance_accounts(db, branch)
        item, milk, small, large = self._setup_item_with_two_variants(db, branch, outlet)
        stock_before = inventory_crud.get_product(db, milk.id).current_stock

        data = OrderCreate(outlet_id=outlet.id, order_type="takeaway", guests_count=1,
                           items=[OrderItemCreate(item_id=item.id, quantity=1, variant_id=small.id)])
        order = dining_services.create_order(db, branch.id, data, waiter_id=1)
        assert order.subtotal == Decimal("25.00")
        dining_services.update_order_status(db, order.id, "paid")

        stock_after = inventory_crud.get_product(db, milk.id).current_stock
        assert stock_before - stock_after == Decimal("120")

    def test_item_without_variants_unaffected(self, db):
        """صنف عادي بدون متغيّرات — سلوكه زي ما كان بالظبط قبل الميزة دي،
        مفيش داعي لتحديد variant_id خالص."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("55.00"), name="شاورما")
        data = OrderCreate(outlet_id=outlet.id, order_type="takeaway", guests_count=1,
                           items=[OrderItemCreate(item_id=item.id, quantity=2)])
        order = dining_services.create_order(db, branch.id, data, waiter_id=1)
        assert order.subtotal == Decimal("110.00")
        assert order.items[0].variant_id is None
        assert order.items[0].name == "شاورما"


# ─────────────────────── Food cost report with variants ────────────────

class TestFoodCostReportWithVariants:
    def test_variants_reported_as_separate_non_double_counted_lines(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        ensure_finance_accounts(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("25.00"), name="كابتشينو")
        milk = make_product(db, branch, name="حليب", cost_price=Decimal("0.05"))

        small = dining_services.add_variant(db, item.id, DiningItemVariantCreate(name="صغير", price=Decimal("25.00")))
        dining_services.add_variant_recipe_line(
            db, small.id, DiningItemVariantRecipeLineCreate(product_id=milk.id, quantity_per_unit=Decimal("120")),
        )  # unit cost = 120 * 0.05 = 6.00
        large = dining_services.add_variant(db, item.id, DiningItemVariantCreate(name="كبير", price=Decimal("35.00")))
        dining_services.add_variant_recipe_line(
            db, large.id, DiningItemVariantRecipeLineCreate(product_id=milk.id, quantity_per_unit=Decimal("200")),
        )  # unit cost = 200 * 0.05 = 10.00

        small_order = dining_services.create_order(
            db, branch.id,
            OrderCreate(outlet_id=outlet.id, order_type="takeaway", guests_count=1,
                       items=[OrderItemCreate(item_id=item.id, quantity=3, variant_id=small.id)]),
            waiter_id=1,
        )
        dining_services.update_order_status(db, small_order.id, "paid")

        large_order = dining_services.create_order(
            db, branch.id,
            OrderCreate(outlet_id=outlet.id, order_type="takeaway", guests_count=1,
                       items=[OrderItemCreate(item_id=item.id, quantity=2, variant_id=large.id)]),
            waiter_id=1,
        )
        dining_services.update_order_status(db, large_order.id, "paid")

        today = date.today()
        report = dining_services.get_food_cost_report(db, branch.id, today, today)

        item_lines = [l for l in report.lines if l.item_id == item.id]
        # صف مستقل لكل متغيّر — مفيش صف "مجمّع" مضلّل للصنف الأساسي
        assert len(item_lines) == 2

        small_line = next(l for l in item_lines if l.variant_id == small.id)
        assert small_line.quantity_sold == 3
        assert small_line.revenue == Decimal("75.00")            # 25 × 3
        assert small_line.theoretical_unit_cost == Decimal("6.00")
        assert small_line.theoretical_total_cost == Decimal("18.00")  # 6 × 3
        assert "صغير" in small_line.item_name

        large_line = next(l for l in item_lines if l.variant_id == large.id)
        assert large_line.quantity_sold == 2
        assert large_line.revenue == Decimal("70.00")            # 35 × 2
        assert large_line.theoretical_unit_cost == Decimal("10.00")
        assert large_line.theoretical_total_cost == Decimal("20.00")  # 10 × 2
        assert "كبير" in large_line.item_name

        # الإجمالي = مجموع الاتنين، مش متوسط وهمي بينهم (18 + 20 = 38، 75 + 70 = 145)
        assert report.summary.total_revenue == Decimal("145.00")
        assert report.summary.total_theoretical_cost == Decimal("38.00")

    def test_variant_without_recipe_falls_back_to_item_recipe_for_costing(self, db):
        """متغيّر مفهوش وصفة خاصة بيه لسه — نفس fallback بتاع خصم المخزون
        (_effective_recipe) لازم يتطبّق على التقرير كمان، وإلا الاتنين
        هيختلفوا في "إيه الوصفة اللي فعليًا بتحكم الاستهلاك"."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        ensure_finance_accounts(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("25.00"))
        beans = make_product(db, branch, name="بن", cost_price=Decimal("2"))
        dining_services.add_recipe_line(
            db, item.id, DiningItemRecipeLineCreate(product_id=beans.id, quantity_per_unit=Decimal("3")),
        )  # وصفة الصنف الأساسي: تكلفة 6.00
        variant = dining_services.add_variant(db, item.id, DiningItemVariantCreate(name="عادي", price=Decimal("25.00")))
        # المتغيّر مفهوش وصفة خاصة بيه — لازم يستخدم وصفة الصنف الأساسي fallback

        order = dining_services.create_order(
            db, branch.id,
            OrderCreate(outlet_id=outlet.id, order_type="takeaway", guests_count=1,
                       items=[OrderItemCreate(item_id=item.id, quantity=1, variant_id=variant.id)]),
            waiter_id=1,
        )
        dining_services.update_order_status(db, order.id, "paid")

        today = date.today()
        report = dining_services.get_food_cost_report(db, branch.id, today, today)
        line = next(l for l in report.lines if l.item_id == item.id and l.variant_id == variant.id)
        assert line.has_recipe is True
        assert line.theoretical_unit_cost == Decimal("6.00")


# ─────────────────────── Cafe-outlet-type mirror ────────────────────────

class TestCafeOutletVariants:
    """يثبت إن outlet_type='cafe' بيشتغل بنفس آلية 'restaurant' بالظبط —
    مفيش كود خاص بأي outlet_type في منطق المتغيّرات."""

    def test_add_variant_and_order_uses_variant_price(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch, outlet_type="cafe", revenue_account_code="4400")
        ensure_finance_accounts(db, branch, revenue_code="4400")
        item = make_item(db, branch, outlet, price=Decimal("25.00"), name="كابتشينو")
        milk = make_product(db, branch, name="حليب", cost_price=Decimal("0.05"))

        large = dining_services.add_variant(db, item.id, DiningItemVariantCreate(name="كبير", price=Decimal("35.00")))
        dining_services.add_variant_recipe_line(
            db, large.id, DiningItemVariantRecipeLineCreate(product_id=milk.id, quantity_per_unit=Decimal("200")),
        )

        # اختيار متغيّر إجباري
        with pytest.raises(ValueError, match="لازم تختار"):
            dining_services.create_order(
                db, branch.id,
                OrderCreate(outlet_id=outlet.id, order_type="takeaway",
                           items=[OrderItemCreate(item_id=item.id, quantity=1)]),
                waiter_id=1,
            )

        stock_before = inventory_crud.get_product(db, milk.id).current_stock
        order = dining_services.create_order(
            db, branch.id,
            OrderCreate(outlet_id=outlet.id, order_type="takeaway",
                       items=[OrderItemCreate(item_id=item.id, quantity=2, variant_id=large.id)]),
            waiter_id=1,
        )
        assert order.subtotal == Decimal("70.00")
        assert order.items[0].variant_id == large.id

        dining_services.update_order_status(db, order.id, "paid")
        stock_after = inventory_crud.get_product(db, milk.id).current_stock
        assert stock_before - stock_after == Decimal("400")
