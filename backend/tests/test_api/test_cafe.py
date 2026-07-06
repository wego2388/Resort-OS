"""
tests/test_api/test_cafe.py
Integration tests for cafe module.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.modules.cafe.schemas import CafeOrderCreate, CafeOrderItemCreate
from app.modules.cafe import services, crud


def make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(name="Cafe Branch", name_ar="كافيه",
               code=f"CAF-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_cafe_item(db, branch, available=True):
    from app.modules.cafe.models import CafeItem
    item = CafeItem(
        branch_id=branch.id,
        name="قهوة عربية",
        price=Decimal("25.00"),
        is_available=available,
    )
    db.add(item)
    db.commit()
    return item


def make_cafe_table(db, branch):
    from app.modules.cafe.models import CafeTable
    t = CafeTable(
        branch_id=branch.id,
        table_number=f"C-{uuid.uuid4().hex[:6].upper()}",
        capacity=2,
        status="available",
    )
    db.add(t)
    db.commit()
    return t


def make_order(db, branch, item, table=None):
    data = CafeOrderCreate(
        branch_id=branch.id,
        table_id=table.id if table else None,
        order_type="dine_in" if table else "takeaway",
        items=[CafeOrderItemCreate(item_id=item.id, quantity=1)],
    )
    return services.create_order(db, data)


class TestCafeOrder:

    def test_create_order(self, db):
        branch = make_branch(db)
        item = make_cafe_item(db, branch)
        order = make_order(db, branch, item)
        assert order.id is not None
        assert order.status == "open"
        assert order.subtotal == Decimal("25.00")

    def test_create_order_with_table(self, db):
        branch = make_branch(db)
        item = make_cafe_item(db, branch)
        table = make_cafe_table(db, branch)
        data = CafeOrderCreate(
            branch_id=branch.id,
            table_id=table.id,
            order_type="dine_in",
            items=[CafeOrderItemCreate(item_id=item.id, quantity=2)],
        )
        order = services.create_order(db, data)
        assert order.table_id == table.id
        assert order.subtotal == Decimal("50.00")

    def test_unavailable_item_raises(self, db):
        branch = make_branch(db)
        item = make_cafe_item(db, branch, available=False)
        data = CafeOrderCreate(
            branch_id=branch.id,
            order_type="takeaway",
            items=[CafeOrderItemCreate(item_id=item.id, quantity=1)],
        )
        with pytest.raises(ValueError, match="غير متاح"):
            services.create_order(db, data)

    def test_nonexistent_item_raises(self, db):
        branch = make_branch(db)
        data = CafeOrderCreate(
            branch_id=branch.id,
            order_type="takeaway",
            items=[CafeOrderItemCreate(item_id=9999, quantity=1)],
        )
        with pytest.raises(ValueError):
            services.create_order(db, data)

    def test_vat_and_service_charge_applied(self, db):
        branch = make_branch(db)
        item = make_cafe_item(db, branch)
        order = make_order(db, branch, item)
        assert order.vat_amount > Decimal("0")
        assert order.total > order.subtotal


class TestCafeOrderStatus:

    def test_update_status_to_in_kitchen(self, db):
        branch = make_branch(db)
        item = make_cafe_item(db, branch)
        order = make_order(db, branch, item)
        updated = services.update_order_status(db, order.id, "in_kitchen")
        assert updated.status == "in_kitchen"

    def test_pay_order(self, db):
        branch = make_branch(db)
        item = make_cafe_item(db, branch)
        order = make_order(db, branch, item)
        paid = services.update_order_status(db, order.id, "paid")
        assert paid.status == "paid"

    def test_cannot_change_paid_status(self, db):
        branch = make_branch(db)
        item = make_cafe_item(db, branch)
        order = make_order(db, branch, item)
        services.update_order_status(db, order.id, "paid")
        with pytest.raises(ValueError, match="paid"):
            services.update_order_status(db, order.id, "open")

    def test_cancel_order(self, db):
        branch = make_branch(db)
        item = make_cafe_item(db, branch)
        order = make_order(db, branch, item)
        cancelled = services.update_order_status(db, order.id, "cancelled")
        assert cancelled.status == "cancelled"

    def test_order_not_found_raises(self, db):
        with pytest.raises(ValueError):
            services.update_order_status(db, 9999, "paid")


def make_finance_accounts(db, branch):
    """يزرع 1100 (نقدية) و4400 (إيرادات الكافيه) — الحسابين اللي
    cafe.services بيدوّر عليهم بالكود عند ترحيل قيد الإيراد."""
    from app.modules.finance.models import Account
    cash = Account(branch_id=branch.id, code="1100", name="Cash", account_type="asset")
    revenue = Account(branch_id=branch.id, code="4400", name="Cafe Revenue", account_type="revenue")
    db.add_all([cash, revenue])
    db.commit()
    return cash, revenue


class TestCafeRevenueJournalPosting:
    """Gap حقيقي: دفع طلب كافيه كان يُنشئ FolioCharge(charge_type='cafe')
    بس — من غير أي قيد يومية، فحساب 4400 كان صفر دايماً."""

    def test_paying_order_posts_balanced_journal_entry(self, db):
        from app.modules.finance import crud as finance_crud
        branch = make_branch(db)
        item = make_cafe_item(db, branch)
        cash, revenue = make_finance_accounts(db, branch)
        order = make_order(db, branch, item)

        services.update_order_status(db, order.id, "paid")

        entries, total = finance_crud.list_journal_entries(db, branch.id, source="cafe")
        assert total == 1
        entry = entries[0]
        assert entry.source_id == order.id
        total_debit = sum(l.debit for l in entry.lines)
        total_credit = sum(l.credit for l in entry.lines)
        assert total_debit == total_credit == order.total

        db.refresh(cash)
        db.refresh(revenue)
        cash_line = next(l for l in entry.lines if l.account_id == cash.id)
        revenue_line = next(l for l in entry.lines if l.account_id == revenue.id)
        assert cash_line.debit == order.total
        assert revenue_line.credit == order.total

    def test_missing_accounts_does_not_block_payment(self, db):
        """لو الحسابات مش موجودة، الدفع لازم ينجح عادي — نفس فلسفة
        pms._post_checkout_journal."""
        branch = make_branch(db)
        item = make_cafe_item(db, branch)
        order = make_order(db, branch, item)

        paid = services.update_order_status(db, order.id, "paid")
        assert paid.status == "paid"

        from app.modules.finance import crud as finance_crud
        _, total = finance_crud.list_journal_entries(db, branch.id, source="cafe")
        assert total == 0


class TestCafeRefundFolioEdgeCases:
    """services._reduce_folio_charge_for_refund — الفرعين اللي مش مغطيين عبر
    HTTP: (أ) الطلب مربوط بـ folio_id بس مفيش FolioCharge فعلي مطابق (مثلاً
    فشلت الشحنة الأولى بصمت)، و(ب) الفوليو مقفول (status='closed') فمينفعش
    نلمس شحناته بعد قفله. الحالتين دول مش سهل الوصول ليهم عن طريق الـ HTTP
    endpoints العادية فبنبني الحالة يدويًا هنا على مستوى service."""

    def test_refund_when_folio_charge_missing_does_not_crash(self, db):
        from datetime import datetime as _dt
        from app.modules.finance.models import Folio

        branch = make_branch(db)
        item = make_cafe_item(db, branch)
        order = make_order(db, branch, item)
        services.update_order_status(db, order.id, "paid")

        # نربط الطلب بفوليو حقيقي يدويًا من غير ما ننشئ FolioCharge مطابق —
        # بيحاكي حالة نشر الشحنة الأولى اللي فشلت بصمت (except Exception: pass).
        folio = Folio(branch_id=branch.id, guest_name="ضيف اختبار مرتجع",
                       check_in=_dt.utcnow(), check_out=_dt.utcnow(), status="open")
        db.add(folio); db.commit()
        order.folio_id = folio.id
        db.commit()

        refunded = services.refund_order_item(db, order.id, order.items[0].id, "اختبار", refunded_by=1)
        assert refunded.status == "refunded"
        db.refresh(folio)
        assert folio.total == Decimal("0")  # مفيش شحنة أصلاً فمفيش أي تغيير

    def test_refund_skips_closed_folio(self, db):
        from datetime import datetime as _dt
        from app.modules.finance import crud as finance_crud
        from app.modules.finance.models import Folio
        from app.modules.finance.schemas import FolioChargeCreate

        branch = make_branch(db)
        item = make_cafe_item(db, branch)
        order = make_order(db, branch, item)
        services.update_order_status(db, order.id, "paid")

        folio = Folio(branch_id=branch.id, guest_name="ضيف اختبار مرتجع ٢",
                       check_in=_dt.utcnow(), check_out=_dt.utcnow(), status="open")
        db.add(folio); db.commit()
        finance_crud.add_charge(db, folio.id, FolioChargeCreate(
            charge_type="cafe", description="طلب كافيه", amount=order.subtotal,
            vat_amount=order.vat_amount, posted_at=_dt.utcnow(), ref_order_id=order.id,
        ))
        db.commit()
        finance_crud.recalculate_folio_total(db, folio)
        order.folio_id = folio.id
        folio.status = "closed"  # الفوليو اتقفل بعد الشحنة، قبل ما الضيف يعمل مرتجع
        db.commit()
        total_before = folio.total
        assert total_before > Decimal("0")

        refunded = services.refund_order_item(db, order.id, order.items[0].id, "اختبار", refunded_by=1)
        assert refunded.status == "refunded"
        db.refresh(folio)
        assert folio.total == total_before  # مقفول، فما اتلمسش رغم المرتجع


def make_product(db, branch, name="عجينة بيتزا", unit="kg", cost_price=Decimal("40"),
                  initial_stock=Decimal("20")):
    """نفس test_restaurant.make_product بالظبط — راجعه للتفاصيل."""
    from app.modules.inventory.schemas import ProductCreate, StockMovementCreate, WarehouseCreate
    from app.modules.inventory import services as inventory_services
    from datetime import datetime as _dt

    warehouse = inventory_services.create_warehouse(
        db, WarehouseCreate(branch_id=branch.id, name="مخزن الكافيه", code=f"WH-{uuid.uuid4().hex[:6].upper()}"),
    )
    product = inventory_services.create_product(
        db, ProductCreate(
            branch_id=branch.id, warehouse_id=warehouse.id,
            name=name, sku=f"SKU-{uuid.uuid4().hex[:6].upper()}", unit=unit,
            cost_price=cost_price,
        ),
    )
    if initial_stock > 0:
        inventory_services.record_movement(
            db, StockMovementCreate(
                branch_id=branch.id, product_id=product.id, warehouse_id=warehouse.id,
                movement_type="purchase_in", quantity=initial_stock, unit_cost=cost_price,
                moved_at=_dt.utcnow(),
            ), moved_by=1,
        )
    db.refresh(product)
    return product


class TestCafeItemRecipe:
    """وصفة/BOM حقيقية لصنف كافيه — نفس نمط
    test_restaurant.TestMenuItemRecipe بالظبط، عبر cafe.services."""

    def test_add_recipe_line_creates_line(self, db):
        branch = make_branch(db)
        item = make_cafe_item(db, branch)
        dough = make_product(db, branch, name="عجينة بيتزا", unit="kg", cost_price=Decimal("40"))

        from app.modules.cafe.schemas import CafeItemRecipeLineCreate
        line = services.add_recipe_line(
            db, item.id, CafeItemRecipeLineCreate(product_id=dough.id, quantity_per_unit=Decimal("0.300")),
        )
        assert line.id is not None
        db.refresh(item)
        assert len(item.recipe_lines) == 1

    def test_add_recipe_line_rejects_duplicate_product(self, db):
        branch = make_branch(db)
        item = make_cafe_item(db, branch)
        dough = make_product(db, branch)

        from app.modules.cafe.schemas import CafeItemRecipeLineCreate
        services.add_recipe_line(db, item.id, CafeItemRecipeLineCreate(product_id=dough.id, quantity_per_unit=Decimal("0.1")))
        with pytest.raises(ValueError, match="مضاف بالفعل"):
            services.add_recipe_line(db, item.id, CafeItemRecipeLineCreate(product_id=dough.id, quantity_per_unit=Decimal("0.2")))

    def test_compute_cost_from_recipe(self, db):
        branch = make_branch(db)
        item = make_cafe_item(db, branch)
        dough = make_product(db, branch, name="عجينة بيتزا", unit="kg", cost_price=Decimal("40"))
        mozzarella = make_product(db, branch, name="موتزاريلا", unit="kg", cost_price=Decimal("250"))

        from app.modules.cafe.schemas import CafeItemRecipeLineCreate
        services.add_recipe_line(db, item.id, CafeItemRecipeLineCreate(product_id=dough.id, quantity_per_unit=Decimal("0.300")))
        services.add_recipe_line(db, item.id, CafeItemRecipeLineCreate(product_id=mozzarella.id, quantity_per_unit=Decimal("0.150")))

        db.refresh(item)
        # 0.300 * 40 + 0.150 * 250 = 12 + 37.5 = 49.5
        assert services.compute_cafe_item_cost(item) == Decimal("49.50")

    def test_compute_cost_falls_back_to_manual_cost_without_recipe(self, db):
        branch = make_branch(db)
        from app.modules.cafe.models import CafeItem
        item = CafeItem(branch_id=branch.id, name="كابتشينو", price=Decimal("18.00"), cost=Decimal("5.00"))
        db.add(item)
        db.commit()
        assert services.compute_cafe_item_cost(item) == Decimal("5.00")

    def test_paying_order_deducts_all_recipe_ingredients(self, db):
        branch = make_branch(db)
        item = make_cafe_item(db, branch)  # make_order هنا quantity=1
        dough = make_product(db, branch, name="عجينة بيتزا", unit="kg", cost_price=Decimal("40"), initial_stock=Decimal("5"))
        mozzarella = make_product(db, branch, name="موتزاريلا", unit="kg", cost_price=Decimal("250"), initial_stock=Decimal("2"))

        from app.modules.cafe.schemas import CafeItemRecipeLineCreate
        services.add_recipe_line(db, item.id, CafeItemRecipeLineCreate(product_id=dough.id, quantity_per_unit=Decimal("0.300")))
        services.add_recipe_line(db, item.id, CafeItemRecipeLineCreate(product_id=mozzarella.id, quantity_per_unit=Decimal("0.150")))
        db.refresh(item)

        order = make_order(db, branch, item)
        services.update_order_status(db, order.id, "paid")

        db.refresh(dough); db.refresh(mozzarella)
        assert dough.current_stock == Decimal("5") - Decimal("0.300")
        assert mozzarella.current_stock == Decimal("2") - Decimal("0.150")

    def test_recipe_deduction_allows_negative_stock(self, db):
        branch = make_branch(db)
        item = make_cafe_item(db, branch)
        dough = make_product(db, branch, name="عجينة بيتزا", unit="kg", cost_price=Decimal("40"), initial_stock=Decimal("0.1"))

        from app.modules.cafe.schemas import CafeItemRecipeLineCreate
        services.add_recipe_line(db, item.id, CafeItemRecipeLineCreate(product_id=dough.id, quantity_per_unit=Decimal("0.300")))
        db.refresh(item)

        order = make_order(db, branch, item)
        paid = services.update_order_status(db, order.id, "paid")
        assert paid.status == "paid"

        db.refresh(dough)
        assert dough.current_stock == Decimal("0.1") - Decimal("0.300")
