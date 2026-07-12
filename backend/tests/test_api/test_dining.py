"""
tests/test_api/test_dining.py
Service/CRUD-level tests for the unified dining module (wagdy.md D-01→D-04,
"Dining Module Merge"). Mirrors test_restaurant.py's structure — same
business rules, now exercised through app.modules.dining instead of the
two parallel restaurant/cafe modules, plus outlet-specific coverage
(revenue_account_code routing, cross-outlet isolation) that has no
restaurant/cafe equivalent because the concept didn't exist there.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.modules.dining import crud, services
from app.modules.dining.schemas import (
    DiningItemRecipeLineCreate, DiningItemVariantCreate,
    DiningItemVariantRecipeLineCreate, OrderCreate, OrderItemCreate,
    OutletCreate,
)


def make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(name="Dining Branch", name_ar="فرع دايننج",
               code=f"DIN-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_outlet(db, branch, outlet_type="restaurant", revenue_account_code="4200"):
    outlet = services.create_outlet(db, OutletCreate(
        branch_id=branch.id, name=f"{outlet_type}-{uuid.uuid4().hex[:6]}",
        outlet_type=outlet_type, revenue_account_code=revenue_account_code,
    ))
    return outlet


def make_item(db, branch, outlet, available=True, station="hot", price=Decimal("55.00")):
    from app.modules.dining.models import DiningItem
    item = DiningItem(
        branch_id=branch.id, outlet_id=outlet.id, name="شاورما دجاج",
        price=price, is_available=available, station=station,
    )
    db.add(item)
    db.commit()
    return item


def make_table(db, branch, outlet, status="available"):
    from app.modules.dining.models import VenueTable
    t = VenueTable(
        branch_id=branch.id, outlet_id=outlet.id,
        table_number=f"T-{uuid.uuid4().hex[:6].upper()}",
        capacity=4, status=status,
    )
    db.add(t)
    db.commit()
    return t


def make_order(db, branch, outlet, item, table=None, quantity=2):
    data = OrderCreate(
        outlet_id=outlet.id,
        table_id=table.id if table else None,
        order_type="dine_in" if table else "takeaway",
        guests_count=2,
        items=[OrderItemCreate(item_id=item.id, quantity=quantity)],
    )
    return services.create_order(db, branch.id, data, waiter_id=1)


def make_finance_accounts(db, branch, revenue_code="4200"):
    from app.modules.finance.models import Account
    cash = Account(branch_id=branch.id, code="1100", name="Cash", account_type="asset")
    revenue = Account(branch_id=branch.id, code=revenue_code, name="Dining Revenue", account_type="revenue")
    guest_ledger = Account(branch_id=branch.id, code="1150", name="ذمم الفوليو", account_type="asset")
    db.add_all([cash, revenue, guest_ledger])
    db.commit()
    return cash, revenue


class TestOutlet:

    def test_create_outlet(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch, outlet_type="bar", revenue_account_code="4600")
        assert outlet.id is not None
        assert outlet.outlet_type == "bar"
        assert outlet.revenue_account_code == "4600"

    def test_new_outlet_type_needs_zero_schema_change(self, db):
        """أهم وعد في الدمج: outlet جديد (Pool Bar، Rooftop) = صف جديد بس،
        صفر migration، صفر كود جديد."""
        branch = make_branch(db)
        pool_bar = make_outlet(db, branch, outlet_type="pool_bar", revenue_account_code="4700")
        item = make_item(db, branch, pool_bar)
        order = make_order(db, branch, pool_bar, item)
        assert order.outlet_id == pool_bar.id


class TestMenuItem:

    def test_create_item(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        assert item.id is not None
        assert item.is_available is True

    def test_unavailable_item_raises(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, available=False)
        data = OrderCreate(
            outlet_id=outlet.id, order_type="takeaway",
            items=[OrderItemCreate(item_id=item.id, quantity=1)],
        )
        with pytest.raises(ValueError, match="غير متاح"):
            services.create_order(db, branch.id, data)

    def test_nonexistent_item_raises(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        data = OrderCreate(
            outlet_id=outlet.id, order_type="takeaway",
            items=[OrderItemCreate(item_id=9999, quantity=1)],
        )
        with pytest.raises(ValueError):
            services.create_order(db, branch.id, data)

    def test_nonexistent_outlet_raises(self, db):
        branch = make_branch(db)
        data = OrderCreate(
            outlet_id=9999, order_type="takeaway",
            items=[OrderItemCreate(item_id=1, quantity=1)],
        )
        with pytest.raises(ValueError, match="المنفذ"):
            services.create_order(db, branch.id, data)


class TestOrder:

    def test_create_dine_in_order(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        table = make_table(db, branch, outlet)
        order = make_order(db, branch, outlet, item, table)
        assert order.order_number.startswith("ORD-")
        assert order.status == "open"
        assert order.outlet_id == outlet.id
        assert order.subtotal > Decimal("0")
        assert order.total > order.subtotal

    def test_create_dine_in_sets_table_occupied(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        table = make_table(db, branch, outlet)
        make_order(db, branch, outlet, item, table)
        db.refresh(table)
        assert table.status == "occupied"

    def test_order_with_out_of_service_table_raises(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        table = make_table(db, branch, outlet, status="out_of_service")
        data = OrderCreate(
            outlet_id=outlet.id, table_id=table.id, order_type="dine_in",
            items=[OrderItemCreate(item_id=item.id, quantity=1)],
        )
        with pytest.raises(ValueError, match="خارج الخدمة"):
            services.create_order(db, branch.id, data)

    def test_subtotal_correct(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("55.00"))
        order = make_order(db, branch, outlet, item, quantity=2)
        assert order.subtotal == Decimal("110.00")

    def test_hold_order(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        data = OrderCreate(
            outlet_id=outlet.id, order_type="takeaway",
            items=[OrderItemCreate(item_id=item.id, quantity=1)],
        )
        order = services.create_order(db, branch.id, data, hold=True)
        assert order.status == "held"

    def test_add_items_to_open_order(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("55.00"))
        order = make_order(db, branch, outlet, item, quantity=1)
        original_subtotal = order.subtotal
        updated = services.add_items_to_order(db, order.id, [OrderItemCreate(item_id=item.id, quantity=1)])
        assert updated.subtotal == original_subtotal * 2
        assert len(updated.items) == 2

    def test_add_items_to_paid_order_raises(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item)
        services.update_order_status(db, order.id, "paid")
        with pytest.raises(ValueError):
            services.add_items_to_order(db, order.id, [OrderItemCreate(item_id=item.id, quantity=1)])


class TestOrderStatus:

    def test_update_status_to_in_kitchen(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, station="grill")
        order = make_order(db, branch, outlet, item)
        updated = services.update_order_status(db, order.id, "in_kitchen")
        assert updated.status == "in_kitchen"

    def test_in_kitchen_creates_station_ticket(self, db):
        """راجع models.DiningKitchenTicket — التذكرة لازم تتوجّه لمحطة
        الصنف الفعلية (grill هنا)، مش قيمة ثابتة."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, station="grill")
        order = make_order(db, branch, outlet, item)
        services.update_order_status(db, order.id, "in_kitchen")
        tickets = services.get_kds_tickets(db, branch.id)
        assert len(tickets) == 1
        assert tickets[0].station == "grill"
        assert tickets[0].order_id == order.id

    def test_pay_order_frees_table(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        table = make_table(db, branch, outlet)
        order = make_order(db, branch, outlet, item, table)
        make_finance_accounts(db, branch)
        services.update_order_status(db, order.id, "paid")
        db.refresh(table)
        assert table.status == "available"

    def test_cannot_change_paid_order_status(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item)
        make_finance_accounts(db, branch)
        services.update_order_status(db, order.id, "paid")
        with pytest.raises(ValueError, match="paid"):
            services.update_order_status(db, order.id, "in_kitchen")

    def test_order_not_found_raises(self, db):
        with pytest.raises(ValueError):
            services.update_order_status(db, 9999, "paid")


class TestRevenueAccountRouting:
    """wagdy.md D-03 — لب الإصلاح: حساب الإيراد خاصية على Outlet نفسه، مش
    literal ثابت في الكود. منفذين مختلفين لازم يرحّلوا لحسابين مختلفين."""

    def test_restaurant_outlet_posts_to_its_own_revenue_account(self, db):
        from app.modules.finance import crud as finance_crud

        branch = make_branch(db)
        outlet = make_outlet(db, branch, outlet_type="restaurant", revenue_account_code="4200")
        item = make_item(db, branch, outlet)
        make_finance_accounts(db, branch, revenue_code="4200")
        order = make_order(db, branch, outlet, item)

        services.update_order_status(db, order.id, "paid")

        entries, total = finance_crud.list_journal_entries(db, branch.id, source="dining")
        assert total == 1
        codes = {line.account.code for line in entries[0].lines}
        assert "4200" in codes
        assert "1100" in codes

    def test_bar_outlet_posts_to_its_own_revenue_account(self, db):
        """منفذ جديد (بار) بحساب إيراد مستقل تمامًا — نفس المسار، حساب مختلف."""
        from app.modules.finance import crud as finance_crud

        branch = make_branch(db)
        outlet = make_outlet(db, branch, outlet_type="bar", revenue_account_code="4600")
        item = make_item(db, branch, outlet)
        make_finance_accounts(db, branch, revenue_code="4600")
        order = make_order(db, branch, outlet, item)

        services.update_order_status(db, order.id, "paid")

        entries, total = finance_crud.list_journal_entries(db, branch.id, source="dining")
        assert total == 1
        codes = {line.account.code for line in entries[0].lines}
        assert "4600" in codes


class TestVoidAndRefund:

    def test_void_item_before_payment_by_manager(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item, quantity=2)
        target_item = order.items[0]

        updated = services.void_order_item(
            db, order.id, target_item.id, "طلب غلط", voided_by=1,
            acting_user_level=60,
        )
        assert updated.total < order.total or updated.subtotal == Decimal("0")

    def test_void_below_manager_needs_pin(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item)
        target_item = order.items[0]
        with pytest.raises(ValueError, match="موافقة مدير"):
            services.void_order_item(
                db, order.id, target_item.id, "طلب غلط", voided_by=1,
                acting_user_level=40,
            )

    def test_refund_requires_paid_order(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item)
        target_item = order.items[0]
        with pytest.raises(ValueError, match="المدفوعة"):
            services.refund_order_item(db, order.id, target_item.id, "سبب", refunded_by=1)

    def test_refund_after_payment_tracks_refunded_amount(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        make_finance_accounts(db, branch)
        order = make_order(db, branch, outlet, item, quantity=1)
        services.update_order_status(db, order.id, "paid")
        target_item = order.items[0]

        updated = services.refund_order_item(db, order.id, target_item.id, "غير راضٍ", refunded_by=1)
        assert updated.refunded_amount > Decimal("0")
        assert updated.status == "refunded"


class TestVariants:

    def test_variant_required_when_item_has_variants(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("25.00"))
        services.add_variant(db, item.id, DiningItemVariantCreate(name="كبير", price=Decimal("35.00")))
        db.refresh(item)

        data = OrderCreate(
            outlet_id=outlet.id, order_type="takeaway",
            items=[OrderItemCreate(item_id=item.id, quantity=1)],
        )
        with pytest.raises(ValueError, match="حجم"):
            services.create_order(db, branch.id, data)

    def test_variant_price_replaces_base_price(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("25.00"))
        variant = services.add_variant(db, item.id, DiningItemVariantCreate(name="كبير", price=Decimal("35.00")))

        data = OrderCreate(
            outlet_id=outlet.id, order_type="takeaway",
            items=[OrderItemCreate(item_id=item.id, variant_id=variant.id, quantity=1)],
        )
        order = services.create_order(db, branch.id, data)
        assert order.subtotal == Decimal("35.00")

    def test_variant_recipe_line_independent_from_base_item(self, db):
        """راجع CLAUDE.md §18 'Variants حقيقية' — وصفة المتغيّر منفصلة تمامًا
        عن وصفة الصنف الأساسي، مش عمود variant_id على نفس جدول الوصفة."""
        from app.modules.inventory.models import Product, Warehouse

        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        wh = Warehouse(branch_id=branch.id, name="Main", code="WH1")
        db.add(wh); db.commit()
        product = Product(branch_id=branch.id, name="Milk", sku="MLK1", unit="L",
                           cost_price=Decimal("10.00"), warehouse_id=wh.id)
        db.add(product); db.commit()

        variant = services.add_variant(db, item.id, DiningItemVariantCreate(name="كبير", price=Decimal("35.00")))
        services.add_variant_recipe_line(db, variant.id, DiningItemVariantRecipeLineCreate(
            product_id=product.id, quantity_per_unit=Decimal("0.3"),
        ))
        db.refresh(item)
        # الصنف الأساسي مالوش أي وصفة — بس المتغيّر عنده وصفة مستقلة
        assert item.recipe_lines == []
        assert len(variant.recipe_lines) == 1


class TestDiscount:

    def test_apply_discount_with_outlet_scope(self, db):
        """راجع resort_os/discount_engine.py — scope_type='outlet' لازم
        يفرّق فعليًا بين outlet_type ديناميكي، مش نص ثابت 'restaurant'/'cafe'."""
        from datetime import date
        from app.modules.finance.models import ConditionalDiscount

        branch = make_branch(db)
        outlet = make_outlet(db, branch, outlet_type="bar")
        item = make_item(db, branch, outlet, price=Decimal("100.00"))
        rule = ConditionalDiscount(
            branch_id=branch.id,
            condition_type="total_amount", condition_value=">=0",
            discount_type="percentage", discount_value=Decimal("10"),
            max_uses=-1, valid_from=date(2020, 1, 1), valid_until=date(2030, 1, 1),
            priority=1, is_active=True,
            scope_type="outlet", scope_outlet="bar",
        )
        db.add(rule); db.commit()

        order = make_order(db, branch, outlet, item, quantity=1)
        updated = services.apply_order_discount(db, order.id)
        assert updated.discount_amount == Decimal("10.00")


class TestFoodCostReport:

    def test_report_excludes_items_without_recipe(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("50.00"))
        make_finance_accounts(db, branch)
        order = make_order(db, branch, outlet, item, quantity=1)
        services.update_order_status(db, order.id, "paid")

        from datetime import date, timedelta
        report = services.get_food_cost_report(
            db, branch.id, date.today() - timedelta(days=1), date.today() + timedelta(days=1),
        )
        assert report.summary.items_missing_recipe == 1
        assert report.summary.total_revenue == Decimal("0")

    def test_report_includes_items_with_recipe(self, db):
        from app.modules.inventory.models import Product, Warehouse

        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("50.00"))
        wh = Warehouse(branch_id=branch.id, name="Main", code="WH2")
        db.add(wh); db.commit()
        product = Product(branch_id=branch.id, name="Beef", sku="BF1", unit="kg",
                           cost_price=Decimal("100.00"), warehouse_id=wh.id)
        db.add(product); db.commit()
        services.add_recipe_line(db, item.id, DiningItemRecipeLineCreate(
            product_id=product.id, quantity_per_unit=Decimal("0.2"),
        ))
        make_finance_accounts(db, branch)
        order = make_order(db, branch, outlet, item, quantity=1)
        services.update_order_status(db, order.id, "paid")

        from datetime import date, timedelta
        report = services.get_food_cost_report(
            db, branch.id, date.today() - timedelta(days=1), date.today() + timedelta(days=1),
        )
        assert report.summary.items_missing_recipe == 0
        assert report.summary.total_revenue == Decimal("50.00")
        assert report.summary.total_theoretical_cost == Decimal("20.00")


class TestCrossOutletIsolation:
    """اختبار مباشر لأهم وعد في الدمج: outlets مختلفة بتتقاسم نفس الكود، بس
    البيانات معزولة تمامًا عن بعض (منتجين، طاولات، طلبات)."""

    def test_items_scoped_to_their_outlet(self, db):
        branch = make_branch(db)
        restaurant = make_outlet(db, branch, outlet_type="restaurant")
        cafe = make_outlet(db, branch, outlet_type="cafe", revenue_account_code="4400")
        r_item = make_item(db, branch, restaurant)
        c_item = make_item(db, branch, cafe)

        r_items = crud.list_items(db, restaurant.id)
        c_items = crud.list_items(db, cafe.id)
        assert [i.id for i in r_items] == [r_item.id]
        assert [i.id for i in c_items] == [c_item.id]

    def test_orders_scoped_to_branch_and_filterable_by_outlet(self, db):
        branch = make_branch(db)
        restaurant = make_outlet(db, branch, outlet_type="restaurant")
        cafe = make_outlet(db, branch, outlet_type="cafe", revenue_account_code="4400")
        r_item = make_item(db, branch, restaurant)
        c_item = make_item(db, branch, cafe)
        r_order = make_order(db, branch, restaurant, r_item)
        c_order = make_order(db, branch, cafe, c_item)

        all_orders, total = crud.list_orders(db, branch.id)
        assert total == 2
        r_only, r_total = crud.list_orders(db, branch.id, outlet_id=restaurant.id)
        assert r_total == 1
        assert r_only[0].id == r_order.id
