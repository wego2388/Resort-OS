"""
tests/test_api/test_dining_paid_atomicity.py
Gate 1B — failure-injection + cardinality tests for dining's strict "paid"
unit of work (dining.services._mark_order_paid, called via
services.update_order_status). راجع docs/audits/gate-1b-financial-atomicity-plan.md.

SQLite-compatible on purpose: real Postgres row-level locking (SELECT ...
FOR UPDATE actually blocking/rejecting under real concurrent processes) is
tested separately in test_dining_paid_concurrency.py (Postgres-only, skips
by default — راجع نمط tests/test_dining_migration.py). هنا بنختبر عقد إدارة
المعاملة نفسه (commit واحد بالظبط عند النجاح، rollback كامل عند أي فشل،
تحويل الاستثناء الصح لكل حالة) عن طريق محاكاة فشل القفل (OperationalError)
بـ monkeypatch بدل عمليات متزامنة حقيقية — SQLite بيتجاهل with_for_update
فعليًا فمش قادر يثبت القفل نفسه، بس قادر يثبت إن الكود اللي بيتعامل مع فشل
القفل (except OperationalError → دومين exception → rollback) شغال صح.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.modules.dining import crud, services
from app.modules.finance.services import FinancialConfigurationError, FolioClosedError
from app.modules.inventory.services import InventoryConcurrencyError, InventoryConfigurationError

from tests.conftest import TestingSessionLocal
from tests.test_api.test_dining import (
    make_branch, make_finance_accounts, make_item, make_order, make_outlet,
)


def make_product_linked_item(db, branch, outlet, price=Decimal("50.00"), cost_price=Decimal("10.00")):
    """صنف مربوط 1:1 بمنتج مخزون حقيقي (لا وصفة) — عشان نقدر نفشّل خصم
    المخزون تحت معاملة الدفع الصارمة من غير تعقيد وصفة/BOM."""
    from app.modules.dining.models import DiningItem
    from app.modules.inventory import services as inventory_services
    from app.modules.inventory.schemas import ProductCreate, WarehouseCreate

    warehouse = inventory_services.create_warehouse(
        db, WarehouseCreate(branch_id=branch.id, name="مخزن اختبار", code=f"WH-{uuid.uuid4().hex[:6].upper()}"),
    )
    product = inventory_services.create_product(
        db, ProductCreate(
            branch_id=branch.id, warehouse_id=warehouse.id,
            name="مكوّن اختبار", sku=f"SKU-{uuid.uuid4().hex[:6].upper()}", unit="piece",
            cost_price=cost_price,
        ),
    )
    product.current_stock = Decimal("1000")
    db.commit()
    item = DiningItem(branch_id=branch.id, outlet_id=outlet.id, name="صنف مرتبط بمخزون",
                       price=price, is_available=True, linked_product_id=product.id)
    db.add(item)
    db.commit()
    return item, product


def make_folio(db, branch, status="open"):
    from app.modules.finance import crud as finance_crud
    from app.modules.finance.schemas import FolioCreate
    from datetime import datetime, timedelta
    folio = finance_crud.create_folio(db, FolioCreate(
        branch_id=branch.id, guest_name="ضيف اختبار Gate 1B",
        check_in=datetime.utcnow(), check_out=datetime.utcnow() + timedelta(days=1),
    ))
    if status != "open":
        folio.status = status
    db.commit()
    return folio


def assert_order_not_paid_in_fresh_session(order_id: int):
    """يفتح جلسة طازة تمامًا (زي عملية تانية) ويتأكد إن حالة الطلب لسه مش
    'paid' — راجع نمط test_beach.py's dbA/dbB لاستخدام TestingSessionLocal
    مباشرة عشان نتجنب الاعتماد على identity map جلسة التست نفسها."""
    from app.modules.dining.models import DiningOrder
    fresh = TestingSessionLocal()
    try:
        fresh_order = fresh.query(DiningOrder).filter(DiningOrder.id == order_id).first()
        assert fresh_order is not None
        assert fresh_order.status != "paid", (
            "الطلب اتسجّل 'paid' في قاعدة البيانات رغم إن معاملة الدفع "
            "المفروض تكون فشلت بالكامل — انتهاك مباشر لقاعدة commit واحد بس"
        )
        return fresh_order
    finally:
        fresh.close()


def assert_no_journal_entries(branch_id: int, source: str):
    from app.modules.finance import crud as finance_crud
    fresh = TestingSessionLocal()
    try:
        entries, total = finance_crud.list_journal_entries(fresh, branch_id, source=source)
        assert total == 0, f"قيد محاسبي اتسجّل رغم فشل معاملة الدفع بالكامل ({source})"
    finally:
        fresh.close()


def assert_no_stock_movements(branch_id: int, product_id: int):
    from app.modules.inventory.models import StockMovement
    fresh = TestingSessionLocal()
    try:
        count = (
            fresh.query(StockMovement)
            .filter(StockMovement.branch_id == branch_id, StockMovement.product_id == product_id)
            .count()
        )
        assert count == 0, "حركة مخزون اتسجّلت رغم فشل معاملة الدفع بالكامل"
    finally:
        fresh.close()


class TestExactlyOneCommit:
    def test_paid_transition_commits_exactly_once(self, db, monkeypatch):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item, quantity=1)

        commit_calls = []
        original_commit = db.commit

        def counting_commit():
            commit_calls.append(1)
            return original_commit()

        monkeypatch.setattr(db, "commit", counting_commit)

        result = services.update_order_status(db, order.id, "paid")
        assert result.status == "paid"
        assert len(commit_calls) == 1, f"توقعنا commit واحد بالظبط، حصل {len(commit_calls)}"

    def test_cost_center_seeding_path_still_commits_exactly_once(self, db, monkeypatch):
        """أول قيد يترحّل لفرع جديد بيحتاج يزرع مراكز التكلفة الافتراضية —
        قبل Gate 1B كان ده بيعمل commit مستقل جوه ensure_default_cost_centers.
        دلوقتي لازم يبقى flush-only، فالـ commit الإجمالي يفضل واحد بس حتى
        في أول عملية دفع لفرع جديد بالكامل."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch, revenue_account_code="4200")
        make_finance_accounts(db, branch)  # لا يزرع مراكز التكلفة — بس الحسابات
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item, quantity=1)

        from app.modules.finance.models import CostCenter
        assert db.query(CostCenter).filter_by(branch_id=branch.id).count() == 0

        commit_calls = []
        original_commit = db.commit

        def counting_commit():
            commit_calls.append(1)
            return original_commit()

        monkeypatch.setattr(db, "commit", counting_commit)

        result = services.update_order_status(db, order.id, "paid")
        assert result.status == "paid"
        assert len(commit_calls) == 1
        assert db.query(CostCenter).filter_by(branch_id=branch.id).count() > 0


class TestFailureInjectionZeroSideEffects:
    """كل تست هنا يفشّل خطوة معيّنة داخل _mark_order_paid، ثم يفتح جلسة طازة
    (TestingSessionLocal منفصلة تمامًا) ويتأكد إن مفيش أي أثر مالي اتسجّل —
    لا تغيير حالة الطلب لـ paid، لا FolioCharge، لا StockMovement، لا
    JournalEntry، ولا حتى مركز تكلفة (لو الفشل قبل نهاية المعاملة)."""

    def test_missing_gl_account_aborts_everything(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        # عمدًا من غير make_finance_accounts — حساب 1100/4200 مش موجودين
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item, quantity=1)

        with pytest.raises(FinancialConfigurationError):
            services.update_order_status(db, order.id, "paid")

        assert_order_not_paid_in_fresh_session(order.id)
        assert_no_journal_entries(branch.id, "dining")

    def test_folio_closed_aborts_everything(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item, quantity=1)
        folio = make_folio(db, branch, status="closed")
        order.folio_id = folio.id
        db.commit()

        with pytest.raises(FolioClosedError):
            services.update_order_status(db, order.id, "paid")

        assert_order_not_paid_in_fresh_session(order.id)
        assert_no_journal_entries(branch.id, "dining_folio_charge")

        # ولا حتى الشحنة نفسها اتسجّلت
        from app.modules.finance.models import FolioCharge
        fresh = TestingSessionLocal()
        try:
            count = fresh.query(FolioCharge).filter(FolioCharge.folio_id == folio.id).count()
            assert count == 0
        finally:
            fresh.close()

    def test_inventory_lock_contention_aborts_everything(self, db, monkeypatch):
        """يحاكي عملية تانية ماسكة صف المنتج (نفس أسلوب
        test_inventory.py::test_concurrent_movement_raises_concurrency_error)
        — الطلب مفروض يفشل بالكامل بـ InventoryConcurrencyError، مش يكمل
        من غير أثر مخزون زي السلوك القديم (continue الصامت)."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        item, product = make_product_linked_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item, quantity=1)

        from app.modules.inventory import crud as inventory_crud
        from tests.conftest import make_lock_not_available_error

        def _raise_locked(*_args, **_kwargs):
            raise make_lock_not_available_error()

        monkeypatch.setattr(inventory_crud, "lock_product_for_update", _raise_locked)

        with pytest.raises(InventoryConcurrencyError):
            services.update_order_status(db, order.id, "paid")

        assert_order_not_paid_in_fresh_session(order.id)
        assert_no_stock_movements(branch.id, product.id)
        assert_no_journal_entries(branch.id, "dining")

    def test_unrelated_inventory_operational_error_is_not_masked(self, db, monkeypatch):
        """مراجعة Codex الثانية: OperationalError مش متعلق بقفل صف (هنا:
        فقدان اتصال) لازم يتصعّد كخطأ حقيقي، مش يتحول لـInventoryConcurrencyError
        مضلّلة — الفرق الوحيد المسموح هو SQLSTATE 55P03 فعليًا."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        item, product = make_product_linked_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item, quantity=1)

        from app.modules.inventory import crud as inventory_crud
        from tests.conftest import make_unrelated_operational_error

        def _raise_unrelated(*_args, **_kwargs):
            raise make_unrelated_operational_error()

        monkeypatch.setattr(inventory_crud, "lock_product_for_update", _raise_unrelated)

        with pytest.raises(OperationalError) as exc_info:
            services.update_order_status(db, order.id, "paid")
        assert not isinstance(exc_info.value, InventoryConcurrencyError)
        assert_order_not_paid_in_fresh_session(order.id)

    def test_cogs_failure_aborts_everything_including_revenue_journal(self, db):
        """1200/5200 (المخزون/COGS) مش متعرّفين — COGS بيفشل، ومفروض ده
        يوقف كل حاجة كمان (بما فيها قيد الإيراد اللي اتسجّل قبله في نفس
        المعاملة، مش بس خصم المخزون نفسه)."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        from app.modules.finance.models import Account
        # 1100/4200 بس — من غير 1200/5200
        db.add_all([
            Account(branch_id=branch.id, code="1100", name="Cash", account_type="asset"),
            Account(branch_id=branch.id, code="4200", name="Revenue", account_type="revenue"),
        ])
        db.commit()
        item, product = make_product_linked_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item, quantity=1)

        with pytest.raises(FinancialConfigurationError):
            services.update_order_status(db, order.id, "paid")

        assert_order_not_paid_in_fresh_session(order.id)
        assert_no_stock_movements(branch.id, product.id)
        assert_no_journal_entries(branch.id, "dining")

    def test_missing_linked_product_aborts_everything(self, db, monkeypatch):
        """مراجعة Codex الثانية: linked_product_id بيشير لمنتج محذوف/غير
        موجود — قبل الإصلاح كان بيتجاوز بصمت (continue) زي "الصنف مفهوش
        منتج مرتبط أصلاً"، رغم إنها حالتين مختلفتين تمامًا (إعداد ناقص مقابل
        عدم ربط مقصود). دلوقتي لازم يفشل بوضوح.

        ``linked_product_id`` عليه FK حقيقي (``ON DELETE SET NULL``)، فمش
        ممكن نبني صف dangling فعلي في قاعدة بيانات الاختبار (SQLite بيفرض
        الـFK هنا) — بنحاكي بـmonkeypatch إن get_product رجع None لمنتج
        اتمسح فعلاً بين لحظة إنشاء الطلب ولحظة الدفع (سباق حقيقي ممكن)،
        عشان نختبر مسار الكود الدفاعي نفسه من غير الاعتماد على حالة قاعدة
        بيانات مستحيلة."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        item, product = make_product_linked_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item, quantity=1)

        from app.modules.inventory import crud as inventory_crud
        original_get_product = inventory_crud.get_product

        def _missing_product(db_arg, product_id):
            if product_id == product.id:
                return None
            return original_get_product(db_arg, product_id)

        monkeypatch.setattr(inventory_crud, "get_product", _missing_product)

        with pytest.raises(InventoryConfigurationError):
            services.update_order_status(db, order.id, "paid")

        assert_order_not_paid_in_fresh_session(order.id)
        assert_no_journal_entries(branch.id, "dining")

    def test_cross_branch_linked_product_aborts_everything(self, db):
        """مراجعة Codex الثانية: المنتج المرتبط بيخص فرع تاني عن فرع الطلب —
        كان ممكن يتخصم بصمت من مخزون فرع غلط تمامًا. دلوقتي لازم يفشل."""
        from app.modules.dining.models import DiningItem
        from app.modules.inventory import services as inventory_services
        from app.modules.inventory.schemas import ProductCreate, WarehouseCreate

        branch = make_branch(db)
        other_branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)

        # المخزن/المنتج اتعملوا لفرع تاني عمدًا (other_branch)، بينما
        # الصنف/المنفذ/الطلب كلهم لفرع branch — نفس فئة الباج المتوقعة.
        other_warehouse = inventory_services.create_warehouse(
            db, WarehouseCreate(branch_id=other_branch.id, name="مخزن فرع تاني",
                                 code=f"WH-{uuid.uuid4().hex[:6].upper()}"),
        )
        product = inventory_services.create_product(
            db, ProductCreate(
                branch_id=other_branch.id, warehouse_id=other_warehouse.id,
                name="منتج فرع تاني", sku=f"SKU-{uuid.uuid4().hex[:6].upper()}", unit="piece",
                cost_price=Decimal("5.00"),
            ),
        )
        item = DiningItem(branch_id=branch.id, outlet_id=outlet.id, name="صنف بمنتج فرع تاني",
                           price=Decimal("40.00"), is_available=True, linked_product_id=product.id)
        db.add(item)
        db.commit()
        order = make_order(db, branch, outlet, item, quantity=1)

        with pytest.raises(InventoryConfigurationError):
            services.update_order_status(db, order.id, "paid")

        assert_order_not_paid_in_fresh_session(order.id)
        assert_no_stock_movements(other_branch.id, product.id)
        assert_no_journal_entries(branch.id, "dining")

    def test_linked_product_without_warehouse_aborts_everything(self, db):
        """مراجعة Codex الثانية: منتج مرتبط بس من غير مخزن (warehouse_id
        فاضي) — كان بيتجاوز بصمت، دلوقتي لازم يفشل بدل ما الدفع يكمل من
        غير أي خصم مخزون حقيقي."""
        from app.modules.dining.models import DiningItem
        from app.modules.inventory import services as inventory_services
        from app.modules.inventory.schemas import ProductCreate

        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        product = inventory_services.create_product(
            db, ProductCreate(
                branch_id=branch.id, warehouse_id=None,
                name="منتج بلا مخزن", sku=f"SKU-{uuid.uuid4().hex[:6].upper()}", unit="piece",
                cost_price=Decimal("5.00"),
            ),
        )
        item = DiningItem(branch_id=branch.id, outlet_id=outlet.id, name="صنف بمنتج بلا مخزن",
                           price=Decimal("30.00"), is_available=True, linked_product_id=product.id)
        db.add(item)
        db.commit()
        order = make_order(db, branch, outlet, item, quantity=1)

        with pytest.raises(InventoryConfigurationError):
            services.update_order_status(db, order.id, "paid")

        assert_order_not_paid_in_fresh_session(order.id)
        assert_no_journal_entries(branch.id, "dining")

    def test_product_with_cross_branch_warehouse_aborts_everything(self, db):
        """مراجعة Codex الثالثة (Gate 1B): المنتج نفسه بيخص فرع الطلب الصح
        (product.branch_id == order.branch_id)، لكن **المخزن المرتبط بيه**
        بيخص فرع تاني تمامًا — create_product مافيهاش أي تحقق إن
        warehouse_id بتاعه نفس فرع المنتج، فالحالة دي ممكنة فعليًا. الفحص
        القديم (product.branch_id بس) كان بيسيبها تمر. دلوقتي لازم تفشل،
        وبدون أي أثر جزئي: لا طلب مدفوع، لا StockMovement، لا JournalEntry."""
        from app.modules.dining.models import DiningItem
        from app.modules.inventory import crud as inventory_crud
        from app.modules.inventory import services as inventory_services
        from app.modules.inventory.schemas import ProductCreate, WarehouseCreate

        branch = make_branch(db)
        other_branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)

        # المخزن لفرع تاني عمدًا، بينما المنتج نفسه لفرع الطلب الصح.
        cross_warehouse = inventory_services.create_warehouse(
            db, WarehouseCreate(branch_id=other_branch.id, name="مخزن فرع تاني",
                                 code=f"WH-{uuid.uuid4().hex[:6].upper()}"),
        )
        product = inventory_services.create_product(
            db, ProductCreate(
                branch_id=branch.id, warehouse_id=cross_warehouse.id,
                name="منتج بمخزن فرع تاني", sku=f"SKU-{uuid.uuid4().hex[:6].upper()}", unit="piece",
                cost_price=Decimal("5.00"),
            ),
        )
        assert product.branch_id == branch.id  # المنتج فرعه صح
        assert cross_warehouse.branch_id != branch.id  # لكن مخزنه لفرع تاني
        item = DiningItem(branch_id=branch.id, outlet_id=outlet.id, name="صنف بمخزن فرع تاني",
                           price=Decimal("40.00"), is_available=True, linked_product_id=product.id)
        db.add(item)
        db.commit()
        order = make_order(db, branch, outlet, item, quantity=1)

        with pytest.raises(InventoryConfigurationError):
            services.update_order_status(db, order.id, "paid")

        assert_order_not_paid_in_fresh_session(order.id)
        assert_no_journal_entries(branch.id, "dining")

        fresh = TestingSessionLocal()
        try:
            from app.modules.inventory.models import StockMovement
            count = fresh.query(StockMovement).filter(StockMovement.product_id == product.id).count()
            assert count == 0, "حركة مخزون اتسجّلت رغم إن المخزن يخص فرع تاني عن الطلب"
        finally:
            fresh.close()

    def test_recipe_product_missing_in_strict_mode_aborts_everything(self, db, monkeypatch):
        """مراجعة Codex الثالثة: تثبيت صريح إن سطر وصفة بيشير لمنتج غير
        موجود (مش الحالة linked_product_id المباشرة المُختبرة في مكان
        تاني) بيفشل تحت strict=True، مش يتجاوز بصمت.

        product_id على DiningItemRecipeLine عليه FK حقيقي (``ON DELETE
        RESTRICT``)، فمش ممكن نبني صف dangling فعلي بحذف المنتج مباشرة
        (SQLite بيفرض الـFK هنا زي أي بيئة إنتاج حقيقية) — بنحاكي بـ
        monkeypatch إن get_product رجع None لمنتج الوصفة تحديدًا، عشان
        نختبر مسار الكود الدفاعي نفسه من غير الاعتماد على حالة قاعدة
        بيانات مستحيلة (نفس أسلوب test_missing_linked_product_aborts_everything)."""
        from app.modules.dining.models import DiningItem
        from app.modules.dining.schemas import DiningItemRecipeLineCreate
        from app.modules.inventory import services as inventory_services
        from app.modules.inventory.schemas import ProductCreate, WarehouseCreate

        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        item = DiningItem(branch_id=branch.id, outlet_id=outlet.id, name="صنف بوصفة",
                           price=Decimal("50.00"), is_available=True)
        db.add(item)
        db.commit()

        warehouse = inventory_services.create_warehouse(
            db, WarehouseCreate(branch_id=branch.id, name="مخزن اختبار",
                                 code=f"WH-{uuid.uuid4().hex[:6].upper()}"),
        )
        product = inventory_services.create_product(
            db, ProductCreate(
                branch_id=branch.id, warehouse_id=warehouse.id,
                name="مكوّن وصفة", sku=f"SKU-{uuid.uuid4().hex[:6].upper()}", unit="piece",
                cost_price=Decimal("5.00"),
            ),
        )
        services.add_recipe_line(db, item.id, DiningItemRecipeLineCreate(
            product_id=product.id, quantity_per_unit=Decimal("1"),
        ))
        order = make_order(db, branch, outlet, item, quantity=1)

        from app.modules.inventory import crud as inventory_crud
        original_get_product = inventory_crud.get_product

        def _missing_recipe_product(db_arg, product_id):
            if product_id == product.id:
                return None
            return original_get_product(db_arg, product_id)

        monkeypatch.setattr(inventory_crud, "get_product", _missing_recipe_product)

        with pytest.raises(InventoryConfigurationError):
            services.update_order_status(db, order.id, "paid")

        assert_order_not_paid_in_fresh_session(order.id)
        assert_no_journal_entries(branch.id, "dining")


class TestOrderTotalValidation:
    def test_zero_total_order_rejected(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("55.00"))
        order = make_order(db, branch, outlet, item, quantity=1)
        # نفس سيناريو food_cost_report.py::test_cancelled_item_excluded_from_sales
        # — لو الصنف الوحيد اتلغى، الإجمالي بيرجع صفر
        services.void_order_item(db, order.id, order.items[0].id, "غلط", voided_by=1)

        with pytest.raises(services.InvalidOrderTotalError):
            services.update_order_status(db, order.id, "paid")

        assert_order_not_paid_in_fresh_session(order.id)


class TestPaymentMethodFolioConsistency:
    """مراجعة Codex الثانية (Gate 1B): payment_method وorder.folio_id لازم
    يتطابقوا دايمًا — مينفعش القيد يترحّل على ذمم الفوليو بينما payment_method
    بيدّعي كاش/بطاقة، ولا العكس (طلب 'room' من غير فوليو حقيقي أصلاً)."""

    def test_room_method_without_charge_to_room_id_or_folio_rejected(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item, quantity=1)

        with pytest.raises(services.InvalidPaymentMethodError):
            services.update_order_status(db, order.id, "paid", payment_method="room")

        assert_order_not_paid_in_fresh_session(order.id)

    def test_charge_to_room_id_with_cash_method_rejected(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item, quantity=1)

        with pytest.raises(services.InvalidPaymentMethodError):
            services.update_order_status(
                db, order.id, "paid", charge_to_room_id=1, payment_method="cash",
            )

        assert_order_not_paid_in_fresh_session(order.id)

    def test_charge_to_room_id_with_card_method_rejected(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item, quantity=1)

        with pytest.raises(services.InvalidPaymentMethodError):
            services.update_order_status(
                db, order.id, "paid", charge_to_room_id=1, payment_method="card",
            )

        assert_order_not_paid_in_fresh_session(order.id)

    def test_preexisting_folio_id_without_explicit_method_defaults_to_room(self, db):
        """مراجعة Codex الثانية: وجود order.folio_id بالفعل مع عدم إرسال
        payment_method يجب أن يجعل الطريقة 'room'، مش 'cash' الافتراضية
        القديمة (كانت بتناقض القيد المحاسبي الفعلي)."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item, quantity=1)

        from app.modules.finance import crud as finance_crud
        from app.modules.finance.schemas import FolioCreate
        from datetime import datetime, timedelta
        folio = finance_crud.create_folio(db, FolioCreate(
            branch_id=branch.id, guest_name="ضيف اختبار",
            check_in=datetime.utcnow(), check_out=datetime.utcnow() + timedelta(days=1),
        ))
        order.folio_id = folio.id
        db.commit()

        result = services.update_order_status(db, order.id, "paid")
        assert result.payment_method == "room"
        assert result.folio_id == folio.id


class TestOrderLockStaleIdentityMap:
    def test_get_order_for_update_returns_fresh_value_not_stale_identity_map(self, db):
        """نفس نمط test_beach.py's dbA/dbB (السطور 270-314) — يثبت إن
        get_order_for_update بيرجّع القيمة الملتزمة فعليًا مش نسخة قديمة من
        identity map الجلسة، حتى لو كانت الجلسة عملت قراءة سابقة غير مقفولة
        لنفس الصف (زي assert_branch_access في الراوتر قبل القفل)."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item, quantity=1)

        dbA = TestingSessionLocal()
        dbB = TestingSessionLocal()
        try:
            # الاتنين بيعملوا قراءة أولى غير مقفولة (زي branch check بيعمله
            # الراوتر قبل القفل) — الاتنين بيشوفوا total الأصلي.
            orderA = crud.get_order(dbA, order.id)
            orderB = crud.get_order(dbB, order.id)
            original_total = orderA.total

            # A بتقفل وتغيّر total (يمثّل تعديل حقيقي حصل في معاملة تانية
            # اتقفلت قبل B)، وتعمل commit.
            lockedA = crud.get_order_for_update(dbA, order.id)
            lockedA.total = original_total + Decimal("999.00")
            dbA.commit()

            # B بتقفل بعد كده — لازم تشوف القيمة الجديدة (اللي A التزمها)،
            # مش القيمة القديمة المخزّنة في identity map بتاعتها.
            lockedB = crud.get_order_for_update(dbB, order.id)
            assert lockedB.total == original_total + Decimal("999.00"), (
                "get_order_for_update رجّع total قديم من identity map الجلسة "
                "بدل القيمة الحقيقية المُعتمدة حديثًا — نفس فئة باج "
                "CLAUDE.md §13 بند ⓫"
            )
        finally:
            dbB.rollback()
            dbA.close()


class TestFolioLockStaleIdentityMap:
    def test_lock_folio_for_update_returns_fresh_total(self, db):
        branch = make_branch(db)
        folio = make_folio(db, branch)

        from app.modules.finance import crud as finance_crud

        dbA = TestingSessionLocal()
        dbB = TestingSessionLocal()
        try:
            folioA = finance_crud.get_folio(dbA, folio.id)
            folioB = finance_crud.get_folio(dbB, folio.id)
            assert folioA.total == Decimal("0")
            assert folioB.total == Decimal("0")

            lockedA = finance_crud.lock_folio_for_update(dbA, folio.id)
            lockedA.total = Decimal("150.00")
            dbA.commit()

            lockedB = finance_crud.lock_folio_for_update(dbB, folio.id)
            assert lockedB.total == Decimal("150.00"), (
                "lock_folio_for_update رجّع total قديم من identity map "
                "الجلسة بدل القيمة الحقيقية المُعتمدة حديثًا"
            )
        finally:
            dbB.rollback()
            dbA.close()


class TestSameOrderDoublePayment:
    def test_order_already_paid_rejected_on_second_attempt(self, db):
        """محاكاة sequential للسباق: أول محاولة تنجح، الثانية (زي لو كانت
        جاية من عملية تانية بعد ما الأولى خلصت) لازم ترفض بكود مميّز، مش
        نجاح صامت تاني."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item, quantity=1)

        first = services.update_order_status(db, order.id, "paid")
        assert first.status == "paid"

        with pytest.raises(services.OrderAlreadyPaidError):
            services.update_order_status(db, order.id, "paid")

    def test_order_lock_contention_raises_concurrency_error(self, db, monkeypatch):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item, quantity=1)

        from tests.conftest import make_lock_not_available_error

        def _raise_locked(*_args, **_kwargs):
            raise make_lock_not_available_error()

        monkeypatch.setattr(crud, "get_order_for_update", _raise_locked)

        with pytest.raises(services.OrderPaymentConcurrencyError):
            services.update_order_status(db, order.id, "paid")

        assert_order_not_paid_in_fresh_session(order.id)

    def test_unrelated_order_operational_error_is_not_masked(self, db, monkeypatch):
        """مراجعة Codex الثانية: OperationalError مش متعلق بقفل صف الطلب
        لازم يتصعّد كخطأ حقيقي، مش يتحول لـOrderPaymentConcurrencyError
        مضلّلة."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item, quantity=1)

        from tests.conftest import make_unrelated_operational_error

        def _raise_unrelated(*_args, **_kwargs):
            raise make_unrelated_operational_error()

        monkeypatch.setattr(crud, "get_order_for_update", _raise_unrelated)

        with pytest.raises(OperationalError) as exc_info:
            services.update_order_status(db, order.id, "paid")
        assert not isinstance(exc_info.value, services.OrderPaymentConcurrencyError)
        assert_order_not_paid_in_fresh_session(order.id)


class TestRouterErrorCodeMapping:
    """راجع app/modules/dining/api/router.py::update_order_status — يتأكد
    من العقد الدقيق (كود الحالة + error_code) لكل حالة فشل، مش بس 4xx/5xx عام."""

    def _make_branch_linked_headers(self, db, branch, role="cashier") -> dict[str, str]:
        from datetime import date, timedelta
        from tests.conftest import _create_test_user, _make_token, open_cashier_shift
        from app.modules.hr.models import Employee

        email = f"{role}-{uuid.uuid4().hex[:10]}@test.local"
        user_id = _create_test_user(email, role)
        emp = Employee(
            branch_id=branch.id, employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
            full_name=f"{role} اختبار ذرّية الدفع", national_id="29001011234567",
            position=role, department="F&B", basic_salary=Decimal("4000.00"),
            hire_date=date.today() - timedelta(days=365), user_id=user_id,
        )
        db.add(emp)
        db.commit()
        # Gate 4A: الكاشير اللي بيحصّل دفع مباشر لازم يكون له وردية مفتوحة.
        open_cashier_shift(db, branch.id, user_id)
        return {"Authorization": f"Bearer {_make_token(email)}"}

    def test_missing_gl_account_returns_503_with_exact_code(self, client: TestClient, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item, quantity=1)
        headers = self._make_branch_linked_headers(db, branch, "cashier")

        resp = client.patch(
            f"/api/v1/dining/orders/{order.id}/status",
            json={"status": "paid"}, headers=headers,
        )
        assert resp.status_code == 503
        assert resp.json()["detail"]["error_code"] == "FINANCIAL_CONFIGURATION_ERROR"

    def test_invalid_order_total_returns_400_with_exact_code(self, client: TestClient, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item, quantity=1)
        services.void_order_item(db, order.id, order.items[0].id, "غلط", voided_by=1)
        headers = self._make_branch_linked_headers(db, branch, "cashier")

        resp = client.patch(
            f"/api/v1/dining/orders/{order.id}/status",
            json={"status": "paid"}, headers=headers,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["error_code"] == "INVALID_ORDER_TOTAL"

    def test_already_paid_returns_409_with_exact_code(self, client: TestClient, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item, quantity=1)
        headers = self._make_branch_linked_headers(db, branch, "cashier")

        first = client.patch(
            f"/api/v1/dining/orders/{order.id}/status",
            json={"status": "paid"}, headers=headers,
        )
        assert first.status_code == 200, first.text

        second = client.patch(
            f"/api/v1/dining/orders/{order.id}/status",
            json={"status": "paid"}, headers=headers,
        )
        assert second.status_code == 409
        assert second.json()["detail"]["error_code"] == "ORDER_ALREADY_PAID"

    def test_cross_branch_paid_attempt_rejected_403(self, client: TestClient, db):
        home_branch = make_branch(db)
        other_branch = make_branch(db)
        outlet = make_outlet(db, home_branch)
        make_finance_accounts(db, home_branch)
        item = make_item(db, home_branch, outlet)
        order = make_order(db, home_branch, outlet, item, quantity=1)
        # كاشير مرتبط بفرع مختلف تمامًا عن فرع الطلب
        headers = self._make_branch_linked_headers(db, other_branch, "cashier")

        resp = client.patch(
            f"/api/v1/dining/orders/{order.id}/status",
            json={"status": "paid"}, headers=headers,
        )
        assert resp.status_code == 403

    def test_cross_branch_cancelled_attempt_rejected_403(self, client: TestClient, db):
        """راجع خطة Gate 1B — التحقق من الفرع لازم يتطبّق على كل تحويل حالة
        (مش 'paid' بس)، بما فيه 'cancelled'."""
        home_branch = make_branch(db)
        other_branch = make_branch(db)
        outlet = make_outlet(db, home_branch)
        item = make_item(db, home_branch, outlet)
        order = make_order(db, home_branch, outlet, item, quantity=1)
        headers = self._make_branch_linked_headers(db, other_branch, "waiter")

        resp = client.patch(
            f"/api/v1/dining/orders/{order.id}/status",
            json={"status": "cancelled"}, headers=headers,
        )
        assert resp.status_code == 403

    def test_super_admin_bypasses_branch_check(self, client: TestClient, db, super_admin_headers):
        """راجع خطة Gate 1B — تخطي super_admin الكامل (Decision 0003) لازم
        يفضل شغال حتى بعد فرض assert_branch_access على الـ endpoint كله."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item, quantity=1)

        # Gate 4A: تحصيل الدفع المباشر بيتطلب وردية مفتوحة للكاشير المسدّد —
        # هنا الـ super_admin هو اللي بيسدّد؛ نفتح له وردية على فرع الطلب.
        from tests.conftest import open_cashier_shift
        from app.core.kernel.models.user import User
        sa_user = db.query(User).filter(User.email == "super_admin@test.local").first()
        assert sa_user is not None
        open_cashier_shift(db, branch.id, sa_user.id)

        resp = client.patch(
            f"/api/v1/dining/orders/{order.id}/status",
            json={"status": "paid"}, headers=super_admin_headers,
        )
        assert resp.status_code == 200, resp.text

    def test_invalid_payment_method_returns_400_with_exact_code(self, client: TestClient, db):
        """مراجعة Codex الثالثة — العقد الدقيق لـInvalidPaymentMethodError
        على مستوى HTTP، مش service layer بس."""
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item, quantity=1)
        headers = self._make_branch_linked_headers(db, branch, "cashier")

        resp = client.patch(
            f"/api/v1/dining/orders/{order.id}/status",
            json={"status": "paid", "payment_method": "room"}, headers=headers,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["error_code"] == "INVALID_PAYMENT_METHOD"

    def test_inventory_configuration_error_returns_503_with_exact_code(
        self, client: TestClient, db,
    ):
        """مراجعة Codex الثالثة — العقد الدقيق لـInventoryConfigurationError
        على مستوى HTTP (منتج مرتبط بلا مخزن)."""
        from app.modules.dining.models import DiningItem
        from app.modules.inventory import services as inventory_services
        from app.modules.inventory.schemas import ProductCreate

        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        product = inventory_services.create_product(
            db, ProductCreate(
                branch_id=branch.id, warehouse_id=None,
                name="منتج بلا مخزن HTTP", sku=f"SKU-{uuid.uuid4().hex[:6].upper()}", unit="piece",
                cost_price=Decimal("5.00"),
            ),
        )
        item = DiningItem(branch_id=branch.id, outlet_id=outlet.id, name="صنف بمنتج بلا مخزن",
                           price=Decimal("30.00"), is_available=True, linked_product_id=product.id)
        db.add(item)
        db.commit()
        order = make_order(db, branch, outlet, item, quantity=1)
        headers = self._make_branch_linked_headers(db, branch, "cashier")

        resp = client.patch(
            f"/api/v1/dining/orders/{order.id}/status",
            json={"status": "paid"}, headers=headers,
        )
        assert resp.status_code == 503
        assert resp.json()["detail"]["error_code"] == "INVENTORY_CONFIGURATION_ERROR"

    def test_unrelated_operational_error_returns_secure_500_no_leakage(
        self, client: TestClient, db, monkeypatch,
    ):
        """مراجعة Codex الثالثة — خطأ قاعدة بيانات مش متعلق بقفل (فقدان
        اتصال مثلًا) لازم يوصل كـ500 عام بدون أي تسريب SQL/driver/مسارات
        ملفات في جسم الاستجابة — على مستوى HTTP الحقيقي، مش service layer
        بس (SecureErrorMiddleware)."""
        from tests.conftest import make_unrelated_operational_error

        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item, quantity=1)
        headers = self._make_branch_linked_headers(db, branch, "cashier")

        def _raise_unrelated(*_args, **_kwargs):
            raise make_unrelated_operational_error("connection lost mid-request")

        monkeypatch.setattr(crud, "get_order_for_update", _raise_unrelated)

        resp = client.patch(
            f"/api/v1/dining/orders/{order.id}/status",
            json={"status": "paid"}, headers=headers,
        )
        assert resp.status_code == 500
        body = resp.json()
        # مفيش أي تسريب لتفاصيل SQL/driver/مسارات ملفات في جسم الاستجابة
        body_text = str(body).lower()
        assert "sql" not in body_text
        assert "psycopg" not in body_text
        assert "traceback" not in body_text
        assert "/home/" not in body_text
        assert ".py" not in body_text
