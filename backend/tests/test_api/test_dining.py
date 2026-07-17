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
from datetime import datetime, time
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.modules.dining import crud, services
from app.modules.dining.schemas import (
    DiningItemExtraCreate, DiningItemExtraGroupCreate,
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


def make_scheduled_item(db, branch, outlet, from_time=None, until_time=None):
    from app.modules.dining.models import DiningItem
    item = DiningItem(
        branch_id=branch.id, outlet_id=outlet.id, name="فطار إنجليزي",
        price=Decimal("70.00"), is_available=True,
        available_from_time=from_time, available_until_time=until_time,
    )
    db.add(item)
    db.commit()
    return item


class TestDiningItemAvailabilitySchedule:
    """wagdy.md P-03 — صنف يشتغل في أوقات محددة (إفطار 7-11، غداء 12-4،
    عشاء 7-11). راجع restaurant.tests.TestItemAvailabilitySchedule — نفس
    السيناريوهات بالظبط (فجوة تكافؤ أُغلقت قبل حذف restaurant/cafe —
    DINING_CUTOVER_PLAN.md Batch 1)."""

    def _order_data(self, outlet, item):
        return OrderCreate(
            outlet_id=outlet.id, order_type="takeaway",
            items=[OrderItemCreate(item_id=item.id, quantity=1)],
        )

    def test_item_without_window_always_available(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_scheduled_item(db, branch, outlet)  # NULL/NULL
        order = services.create_order(db, branch.id, self._order_data(outlet, item))
        assert order.id is not None

    def test_item_available_inside_window(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_scheduled_item(db, branch, outlet, time(7, 0), time(11, 0))
        with patch("app.modules.dining.services.local_now") as mock_now:
            mock_now.return_value = datetime(2026, 7, 12, 9, 0)  # 09:00 جوه 07:00-11:00
            order = services.create_order(db, branch.id, self._order_data(outlet, item))
        assert order.id is not None

    def test_item_unavailable_outside_window(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_scheduled_item(db, branch, outlet, time(7, 0), time(11, 0))
        with patch("app.modules.dining.services.local_now") as mock_now:
            mock_now.return_value = datetime(2026, 7, 12, 15, 0)  # 15:00 برّه 07:00-11:00
            with pytest.raises(ValueError, match="متاح فقط من"):
                services.create_order(db, branch.id, self._order_data(outlet, item))

    def test_item_available_at_exact_boundary(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_scheduled_item(db, branch, outlet, time(7, 0), time(11, 0))
        with patch("app.modules.dining.services.local_now") as mock_now:
            mock_now.return_value = datetime(2026, 7, 12, 11, 0)  # الحد الأقصى نفسه — شامل
            order = services.create_order(db, branch.id, self._order_data(outlet, item))
        assert order.id is not None

    def test_overnight_window_available_late_night(self, db):
        """بار مفتوح 22:00-02:00 (from > until) — نافذة عابرة لمنتصف الليل."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_scheduled_item(db, branch, outlet, time(22, 0), time(2, 0))
        with patch("app.modules.dining.services.local_now") as mock_now:
            mock_now.return_value = datetime(2026, 7, 12, 23, 30)
            order = services.create_order(db, branch.id, self._order_data(outlet, item))
        assert order.id is not None

    def test_overnight_window_available_early_morning(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_scheduled_item(db, branch, outlet, time(22, 0), time(2, 0))
        with patch("app.modules.dining.services.local_now") as mock_now:
            mock_now.return_value = datetime(2026, 7, 12, 1, 30)
            order = services.create_order(db, branch.id, self._order_data(outlet, item))
        assert order.id is not None

    def test_overnight_window_unavailable_midday(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_scheduled_item(db, branch, outlet, time(22, 0), time(2, 0))
        with patch("app.modules.dining.services.local_now") as mock_now:
            mock_now.return_value = datetime(2026, 7, 12, 12, 0)
            with pytest.raises(ValueError, match="متاح فقط من"):
                services.create_order(db, branch.id, self._order_data(outlet, item))

    def test_add_items_to_order_also_enforces_window(self, db):
        """add_items_to_order لازم يتحقق كمان — مش create_order بس."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        scheduled_item = make_scheduled_item(db, branch, outlet, time(7, 0), time(11, 0))
        order = make_order(db, branch, outlet, item)
        with patch("app.modules.dining.services.local_now") as mock_now:
            mock_now.return_value = datetime(2026, 7, 12, 15, 0)
            with pytest.raises(ValueError, match="متاح فقط من"):
                services.add_items_to_order(db, order.id, [OrderItemCreate(item_id=scheduled_item.id, quantity=1)])


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
        assert tickets[0]["station"] == "grill"
        assert tickets[0]["order_id"] == order.id

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

    def test_refund_item_on_discounted_order_allocates_discount_share(self, db):
        """⚠️ باج محاسبي حقيقي اتصلح: مرتجع صنف واحد من طلب عليه خصم (مجموعة
        عميل أو قاعدة شرطية) كان بيتحسب على item_gross + نصيب VAT/service_
        charge بس — من غير أي نصيب من order.discount_amount. القيد الأصلي
        وقت الدفع بيرحّل order.total (صافي بعد الخصم)، فده كان بيخلي مرتجع
        صنف واحد يعكس إيراد أكتر مما اترحّل فعليًا لنفس الصنف، ويسيب باقي
        الطلب برصيد أقل من الصح في دفتر الأستاذ.

        طلب صنفين منفصلين (100 ج لكل واحد، subtotal=200)، خصم مجموعة عميل
        10% (=20 ج)، VAT 14% (=28)، خدمة 12% (=24) → order.total = 232.
        مرتجع صنف واحد (نصيب 50%): نصيب الخصم = 10، فالمرتجع الصح =
        100 - 10 + 14 + 12 = 116 (مش 126 كان قبل الإصلاح). ورصيد إيراد
        المنفذ المتبقي في الدفتر بعد المرتجع لازم يبقى 232 - 116 = 116
        بالظبط — نفس قيمة الصنف التاني المتبقي فعليًا."""
        from app.modules.crm import services as crm_services
        from app.modules.crm.schemas import CustomerCreate, CustomerGroupCreate
        from app.modules.finance import crud as finance_crud

        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("100.00"))
        make_finance_accounts(db, branch)

        group = crm_services.create_customer_group(
            db, CustomerGroupCreate(branch_id=branch.id, name="Staff", discount_percentage=Decimal("10")),
        )
        customer = crm_services.create_customer(db, CustomerCreate(branch_id=branch.id, full_name="Staff"))
        crm_services.assign_customer_group(db, customer.id, group.id)

        order = services.create_order(
            db, branch.id,
            OrderCreate(
                outlet_id=outlet.id, order_type="takeaway", customer_id=customer.id,
                items=[
                    OrderItemCreate(item_id=item.id, quantity=1),
                    OrderItemCreate(item_id=item.id, quantity=1),
                ],
            ),
            waiter_id=1,
        )
        assert order.discount_amount == Decimal("20.00")
        assert order.total == Decimal("232.00")

        services.update_order_status(db, order.id, "paid")
        target_item = order.items[0]

        updated = services.refund_order_item(db, order.id, target_item.id, "سبب", refunded_by=1)
        assert updated.refunded_amount == Decimal("116.00")

        revenue_acc = finance_crud.get_account_by_code(db, branch.id, "4200")
        sums = finance_crud.sum_journal_lines_by_account(db, branch.id, None, datetime.now().date())
        debit_sum, credit_sum = sums.get(revenue_acc.id, (Decimal("0"), Decimal("0")))
        net_revenue_remaining = credit_sum - debit_sum
        assert net_revenue_remaining == Decimal("116.00")


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

    def test_apply_discount_below_manager_needs_pin(self, db):
        """قرار Mohamed 2026-07-13: الكاشير (level 40) صفر صلاحية خصم خالص —
        محتاج موافقة PIN مدير+ حتى لما فيه قاعدة خصم سارية هتنطبق فعليًا."""
        from datetime import date
        from app.modules.finance.models import ConditionalDiscount

        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("50.00"))
        rule = ConditionalDiscount(
            branch_id=branch.id,
            condition_type="total_amount", condition_value=">=0",
            discount_type="percentage", discount_value=Decimal("10"),
            max_uses=-1, valid_from=date(2020, 1, 1), valid_until=date(2030, 1, 1),
            priority=1, is_active=True,
        )
        db.add(rule); db.commit()
        order = make_order(db, branch, outlet, item, quantity=1)

        with pytest.raises(ValueError, match="موافقة مدير"):
            services.apply_order_discount(db, order.id, acting_user_level=40)

    def test_apply_discount_needs_pin_even_with_no_matching_rule(self, db):
        """نفس الحماية حتى لو مفيش قاعدة خصم سارية أصلاً هتنطبق — الموافقة
        على *محاولة* التطبيق نفسها، مش بس على نتيجة إيجابية."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("50.00"))
        order = make_order(db, branch, outlet, item, quantity=1)

        with pytest.raises(ValueError, match="موافقة مدير"):
            services.apply_order_discount(db, order.id, acting_user_level=40)

    def test_apply_discount_manager_self_qualified_boundary(self, db):
        """حد الصلاحية بالظبط (level=60 = manager) مؤهّل بنفسه من غير أي
        موافقة PIN — راجع core.services.resolve_pin_approval."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("50.00"))
        order = make_order(db, branch, outlet, item, quantity=1)

        updated = services.apply_order_discount(db, order.id, acting_user_level=60)
        assert updated.discount_amount == Decimal("0")  # مفيش قاعدة — بس اتنفذ من غير رفض

    def test_apply_discount_with_valid_manager_pin_succeeds_and_audits(self, db):
        """كاشير بموافقة PIN مدير صحيحة — الخصم بيتطبق، و AuditLog بيتسجّل
        بـ approved_by=مين وافق، user_id=مين نفّذ (منفصلين)."""
        from app.core.kernel.models.user import User
        from app.core.kernel.security import get_password_hash
        from app.modules.core import services as core_services
        from app.modules.core.models import AuditLog

        manager = User(email="disc-mgr@test.local", password_hash=get_password_hash("Test@12345"),
                        full_name="Discount Manager", role="manager", is_active=True)
        db.add(manager); db.commit()
        core_services.set_pin(db, manager.id, "9876", created_by=manager.id)
        db.commit()

        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("50.00"))
        order = make_order(db, branch, outlet, item, quantity=1)

        updated = services.apply_order_discount(
            db, order.id, applied_by=1, acting_user_level=40,
            approver_user_id=manager.id, approver_pin="9876",
        )
        assert updated.id == order.id

        log = (
            db.query(AuditLog)
            .filter(AuditLog.entity_type == "dining_order", AuditLog.entity_id == order.id,
                    AuditLog.action == "apply_discount")
            .first()
        )
        assert log is not None
        assert log.approved_by == manager.id
        assert log.user_id == 1

    def test_apply_discount_wrong_pin_rejected(self, db):
        from app.core.kernel.models.user import User
        from app.core.kernel.security import get_password_hash
        from app.modules.core import services as core_services

        manager = User(email="disc-mgr2@test.local", password_hash=get_password_hash("Test@12345"),
                        full_name="Discount Manager 2", role="manager", is_active=True)
        db.add(manager); db.commit()
        core_services.set_pin(db, manager.id, "1234", created_by=manager.id)
        db.commit()

        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("50.00"))
        order = make_order(db, branch, outlet, item, quantity=1)

        with pytest.raises(ValueError):
            services.apply_order_discount(
                db, order.id, acting_user_level=40,
                approver_user_id=manager.id, approver_pin="0000",
            )


class TestCustomerGroupDiscount:
    """خصم مجموعة العميل الدائم (crm.CustomerGroup) — تلقائي بالكامل، من
    غير أي موافقة PIN (مختلف عن apply_order_discount اللي بيطبّق قاعدة
    خصم شرطية يدويًا). راجع services._resolve_order_discount/
    _customer_group_discount_amount لقرار "الأفضل يفوز، مش تراكم"."""

    def _make_customer_with_group(self, db, branch, pct=Decimal("10")):
        from app.modules.crm import services as crm_services
        from app.modules.crm.schemas import CustomerCreate, CustomerGroupCreate

        group = crm_services.create_customer_group(
            db, CustomerGroupCreate(branch_id=branch.id, name="Staff", discount_percentage=pct),
        )
        customer = crm_services.create_customer(
            db, CustomerCreate(branch_id=branch.id, full_name="Staff Member"),
        )
        crm_services.assign_customer_group(db, customer.id, group.id)
        return customer, group

    def test_order_creation_applies_group_discount_automatically(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("100.00"))
        customer, _group = self._make_customer_with_group(db, branch, pct=Decimal("10"))

        order = services.create_order(
            db, branch.id,
            OrderCreate(outlet_id=outlet.id, order_type="takeaway", customer_id=customer.id,
                        items=[OrderItemCreate(item_id=item.id, quantity=1)]),
            waiter_id=1,
        )
        # subtotal=100 → discount 10% = 10.00 — تلقائي، مفيش أي نداء لـ
        # apply_order_discount ولا موافقة PIN هنا خالص.
        assert order.discount_amount == Decimal("10.00")
        assert order.total == order.subtotal + order.vat_amount + order.service_charge - Decimal("10.00")

    def test_no_customer_no_discount(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("100.00"))
        order = make_order(db, branch, outlet, item, quantity=1)
        assert order.discount_amount == Decimal("0")

    def test_add_items_recomputes_group_discount(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("100.00"))
        customer, _group = self._make_customer_with_group(db, branch, pct=Decimal("10"))

        order = services.create_order(
            db, branch.id,
            OrderCreate(outlet_id=outlet.id, order_type="takeaway", customer_id=customer.id,
                        items=[OrderItemCreate(item_id=item.id, quantity=1)]),
            waiter_id=1,
        )
        assert order.discount_amount == Decimal("10.00")  # 10% of 100

        updated = services.add_items_to_order(db, order.id, [OrderItemCreate(item_id=item.id, quantity=1)])
        # subtotal دلوقتي 200 — الخصم لازم يتحسب تاني (باج حقيقي كان هنا:
        # add_items_to_order كان بيسيب discount_amount زي ما هو من غير أي
        # إعادة حساب خالص).
        assert updated.discount_amount == Decimal("20.00")  # 10% of 200

    def test_void_item_recomputes_group_discount(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("100.00"))
        customer, _group = self._make_customer_with_group(db, branch, pct=Decimal("10"))

        order = services.create_order(
            db, branch.id,
            OrderCreate(outlet_id=outlet.id, order_type="takeaway", customer_id=customer.id,
                        items=[OrderItemCreate(item_id=item.id, quantity=2)]),
            waiter_id=1,
        )
        assert order.discount_amount == Decimal("20.00")  # 10% of 200
        item_id = order.items[0].id

        updated = services.void_order_item(db, order.id, item_id, "غلط طلب", voided_by=1, acting_user_level=60)
        assert updated.discount_amount == Decimal("0")  # كل الأصناف اتلغت — subtotal=0

    def test_manual_conditional_discount_loses_to_bigger_group_discount(self, db):
        """قرار سياسة تجارية (Batch 2): أفضل خصم للضيف يفوز، مش تراكم. لو
        خصم مجموعة العميل (هنا 20%) أكبر من القاعدة الشرطية المُطبَّقة يدويًا
        (هنا 10%)، خصم المجموعة هو اللي يتطبّق فعليًا — القاعدة الشرطية
        مبتتحسبش مستخدمة (uses_count متتزودش)."""
        from datetime import date

        from app.modules.finance.models import ConditionalDiscount

        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("100.00"))
        customer, _group = self._make_customer_with_group(db, branch, pct=Decimal("20"))

        rule = ConditionalDiscount(
            branch_id=branch.id,
            condition_type="total_amount", condition_value=">=0",
            discount_type="percentage", discount_value=Decimal("10"),
            max_uses=-1, valid_from=date(2020, 1, 1), valid_until=date(2030, 1, 1),
            priority=1, is_active=True,
        )
        db.add(rule); db.commit()
        uses_before = rule.uses_count

        order = services.create_order(
            db, branch.id,
            OrderCreate(outlet_id=outlet.id, order_type="takeaway", customer_id=customer.id,
                        items=[OrderItemCreate(item_id=item.id, quantity=1)]),
            waiter_id=1,
        )
        assert order.discount_amount == Decimal("20.00")  # خصم المجموعة التلقائي بس لحد دلوقتي

        updated = services.apply_order_discount(db, order.id, acting_user_level=60)
        assert updated.discount_amount == Decimal("20.00")  # لسه خصم المجموعة فايز (20 > 10)
        assert updated.applied_discount_rule_id is None  # القاعدة الشرطية معدتش "اتطبّقت"

        db.refresh(rule)
        assert rule.uses_count == uses_before  # مبتزيدش — معملتش فرق فعلي

    def test_manual_conditional_discount_wins_when_bigger_than_group(self, db):
        """نفس السيناريو، بس مقلوب: القاعدة الشرطية (30%) أكبر من خصم
        المجموعة (10%) — هي اللي تفوز، وrule_id بيتسجّل واستخدامها بيتزود."""
        from datetime import date

        from app.modules.finance.models import ConditionalDiscount

        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("100.00"))
        customer, _group = self._make_customer_with_group(db, branch, pct=Decimal("10"))

        rule = ConditionalDiscount(
            branch_id=branch.id,
            condition_type="total_amount", condition_value=">=0",
            discount_type="percentage", discount_value=Decimal("30"),
            max_uses=-1, valid_from=date(2020, 1, 1), valid_until=date(2030, 1, 1),
            priority=1, is_active=True,
        )
        db.add(rule); db.commit()

        order = services.create_order(
            db, branch.id,
            OrderCreate(outlet_id=outlet.id, order_type="takeaway", customer_id=customer.id,
                        items=[OrderItemCreate(item_id=item.id, quantity=1)]),
            waiter_id=1,
        )
        updated = services.apply_order_discount(db, order.id, acting_user_level=60)
        assert updated.discount_amount == Decimal("30.00")
        assert updated.applied_discount_rule_id == rule.id

        db.refresh(rule)
        assert rule.uses_count == 1


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


class TestExtraGroups:
    """اختبارات group_type — الفجوة الحقيقية اللي اتكشفت بمقارنة نظام
    "Click" القديم: free-text extra-group prompt (مثال حقيقي: "كام سمكة؟")
    مش pick-list بس. راجع docstring dining.models.DiningItemExtraGroup."""

    def test_pick_list_group_defaults_to_pick_list_type(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        group = crud.create_extra_group(db, item.id, DiningItemExtraGroupCreate(
            name="الإضافات", min_select=0, max_select=2,
            options=[DiningItemExtraCreate(name="جبنة إضافية", price_addition=Decimal("10.00"))],
        ))
        db.commit()
        assert group.group_type == "pick_list"
        assert len(group.options) == 1

    def test_pick_list_extra_adds_to_price(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("50.00"))
        group = crud.create_extra_group(db, item.id, DiningItemExtraGroupCreate(
            name="الإضافات", min_select=0, max_select=2,
            options=[DiningItemExtraCreate(name="جبنة إضافية", price_addition=Decimal("10.00"))],
        ))
        db.commit()
        extra_id = group.options[0].id

        data = OrderCreate(
            outlet_id=outlet.id, order_type="takeaway",
            items=[OrderItemCreate(item_id=item.id, quantity=1, extra_ids=[extra_id])],
        )
        order = services.create_order(db, branch.id, data, waiter_id=1)
        assert order.subtotal == Decimal("60.00")
        assert order.items[0].extras[0].extra_name == "جبنة إضافية"
        assert order.items[0].extras[0].text_value is None

    def test_text_group_required_rejects_missing_answer(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        crud.create_extra_group(db, item.id, DiningItemExtraGroupCreate(
            name="كام سمكة؟", group_type="text", min_select=1,
        ))
        db.commit()

        data = OrderCreate(
            outlet_id=outlet.id, order_type="takeaway",
            items=[OrderItemCreate(item_id=item.id, quantity=1)],
        )
        with pytest.raises(ValueError, match="لازم تدخل قيمة"):
            services.create_order(db, branch.id, data)

    def test_text_group_stores_free_text_answer(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("50.00"))
        group = crud.create_extra_group(db, item.id, DiningItemExtraGroupCreate(
            name="كام سمكة؟", group_type="text", min_select=1,
        ))
        db.commit()

        data = OrderCreate(
            outlet_id=outlet.id, order_type="takeaway",
            items=[OrderItemCreate(item_id=item.id, quantity=1, extra_texts={group.id: "3 سمكات"})],
        )
        order = services.create_order(db, branch.id, data, waiter_id=1)
        text_extra = order.items[0].extras[0]
        assert text_extra.text_value == "3 سمكات"
        assert text_extra.extra_id is None
        assert text_extra.price_addition == Decimal("0.00")
        # مجموعة النص ميزيدش سعر الصنف — نفس السعر الأساسي بالظبط
        assert order.subtotal == Decimal("50.00")

    def test_text_group_optional_when_min_select_zero(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        crud.create_extra_group(db, item.id, DiningItemExtraGroupCreate(
            name="ملاحظات خاصة", group_type="text", min_select=0,
        ))
        db.commit()

        data = OrderCreate(
            outlet_id=outlet.id, order_type="takeaway",
            items=[OrderItemCreate(item_id=item.id, quantity=1)],
        )
        order = services.create_order(db, branch.id, data)
        assert order.items[0].extras == []

    def test_add_items_to_order_resolves_text_extras(self, db):
        """راجع add_items_to_order — نفس منطق create_order للنص الحر."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("50.00"))
        group = crud.create_extra_group(db, item.id, DiningItemExtraGroupCreate(
            name="كام سمكة؟", group_type="text", min_select=1,
        ))
        db.commit()

        data = OrderCreate(
            outlet_id=outlet.id, order_type="takeaway",
            items=[OrderItemCreate(item_id=item.id, quantity=1, extra_texts={group.id: "سمكة واحدة"})],
        )
        order = services.create_order(db, branch.id, data, waiter_id=1)

        updated = services.add_items_to_order(
            db, order.id,
            [OrderItemCreate(item_id=item.id, quantity=1, extra_texts={group.id: "سمكتين"})],
        )
        new_item = [i for i in updated.items if i.extras and i.extras[0].text_value == "سمكتين"][0]
        assert new_item.extras[0].text_value == "سمكتين"


class TestFolioChargeDiscountConsistency:
    """التحقق من أن FolioCharge يطرح الخصم — يضمن توافق folio.total مع
    القيود المحاسبية عند تحميل طلب دايننج على غرفة (charge to room).

    الباج القديم: FolioCharge.amount كان = order.subtotal (قبل الخصم)،
    بينما القيد المحاسبي يرحّل order.total (بعد الخصم) — تناقض بفارق
    قيمة order.discount_amount.

    الإصلاح: amount = max(0, order.subtotal - order.discount_amount)
    حتى يكون (amount + vat + svc) = order.total بالظبط.
    """

    def _make_folio(self, db, branch):
        from datetime import datetime, timedelta
        from app.modules.finance.models import Folio
        folio = Folio(
            branch_id=branch.id,
            guest_name="ضيف اختبار",
            check_in=datetime.utcnow(),
            check_out=datetime.utcnow() + timedelta(days=2),
            status="open",
        )
        db.add(folio)
        db.commit()
        db.refresh(folio)
        return folio

    def _make_discount_rule(self, db, branch):
        from app.modules.finance.models import ConditionalDiscount
        from datetime import date, timedelta
        rule = ConditionalDiscount(
            branch_id=branch.id,
            condition_type="total_amount",
            condition_value="0",
            discount_type="percentage",
            discount_value=Decimal("10"),
            valid_from=date.today() - timedelta(days=1),
            valid_until=date.today() + timedelta(days=30),
            is_active=True,
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return rule

    def test_folio_charge_equals_order_total_no_discount(self, db):
        """بدون خصم: folio charge = subtotal + vat + svc = order.total."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch, revenue_account_code="4200")
        item = make_item(db, branch, outlet, price=Decimal("100.00"))
        make_finance_accounts(db, branch, revenue_code="4200")
        folio = self._make_folio(db, branch)

        order = make_order(db, branch, outlet, item, quantity=1)
        order.folio_id = folio.id
        db.commit()
        db.refresh(order)

        # لا خصم — الإجمالي = subtotal + vat + service
        assert order.discount_amount == Decimal("0.00")

        services.update_order_status(db, order.id, "paid", charge_to_room_id=None)
        db.refresh(folio)

        # folio.total يجب أن يساوي order.total بالظبط
        from app.modules.finance.models import FolioCharge
        charges = db.query(FolioCharge).filter_by(folio_id=folio.id).all()
        assert len(charges) == 1
        charge = charges[0]
        charge_total = charge.amount + charge.vat_amount + (charge.service_charge or Decimal("0"))
        db.refresh(order)
        assert charge_total == order.total, (
            f"FolioCharge total {charge_total} ≠ order.total {order.total} — تناقض محاسبي"
        )

    def test_folio_charge_amount_excludes_discount(self, db):
        """مع خصم: FolioCharge.amount = subtotal - discount (بعد الخصم)،
        وإجمالي الـ charge = order.total بالظبط."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch, revenue_account_code="4200")
        item = make_item(db, branch, outlet, price=Decimal("100.00"))
        make_finance_accounts(db, branch, revenue_code="4200")
        folio = self._make_folio(db, branch)

        order = make_order(db, branch, outlet, item, quantity=1)
        order.folio_id = folio.id
        db.commit()
        db.refresh(order)

        # نطبّق الخصم مباشرة على الأوردر (10 ج ثابت) بدون PIN لتجنب التعقيد
        discount_amount = Decimal("10.00")
        order.discount_amount = discount_amount
        order.total = max(Decimal("0"), order.subtotal + order.vat_amount + order.service_charge - discount_amount)
        db.commit()
        db.refresh(order)

        assert order.discount_amount == discount_amount, "الخصم لم يُطبّق — مراجعة الـ setup"

        # الآن ندفع الطلب كـ charge to room
        services.update_order_status(db, order.id, "paid", charge_to_room_id=None)
        db.refresh(folio)
        db.refresh(order)

        from app.modules.finance.models import FolioCharge
        charges = db.query(FolioCharge).filter_by(folio_id=folio.id).all()
        assert len(charges) == 1
        charge = charges[0]

        # المبلغ الأساسي في الـ charge يجب أن يكون بعد طرح الخصم
        expected_net_subtotal = max(Decimal("0"), order.subtotal - order.discount_amount)
        assert charge.amount == expected_net_subtotal, (
            f"charge.amount={charge.amount} ≠ net_subtotal={expected_net_subtotal} — الخصم لم يُطرح"
        )

        # الإجمالي الكلي للـ charge يجب أن يساوي order.total
        charge_total = charge.amount + charge.vat_amount + (charge.service_charge or Decimal("0"))
        assert charge_total == order.total, (
            f"FolioCharge total {charge_total} ≠ order.total {order.total} — تناقض محاسبي"
        )
