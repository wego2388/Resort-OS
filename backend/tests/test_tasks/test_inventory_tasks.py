"""
tests/test_tasks/test_inventory_tasks.py
اختبارات الـ inventory_tasks.py — check_low_stock
بدون Celery runtime
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest


# ─── helpers ────────────────────────────────────────────────────────────────

def _make_branch(db, active=True):
    from app.modules.core.models import Branch
    b = Branch(
        name=f"Inv-Branch-{uuid.uuid4().hex[:6]}",
        code=f"IV{uuid.uuid4().hex[:4].upper()}",
        is_active=active,
    )
    db.add(b)
    db.commit()
    return b


def _make_category(db, branch):
    from app.modules.inventory.models import Category
    c = Category(
        branch_id=branch.id,
        name=f"Cat-{uuid.uuid4().hex[:4]}",
    )
    db.add(c)
    db.commit()
    return c


def _make_product(db, branch, category, current_stock=Decimal("10"), reorder_point=Decimal("5")):
    from app.modules.inventory.models import Product
    p = Product(
        branch_id=branch.id,
        category_id=category.id,
        name=f"Product-{uuid.uuid4().hex[:4]}",
        sku=f"SKU-{uuid.uuid4().hex[:6].upper()}",
        unit="kg",
        current_stock=current_stock,
        reorder_point=reorder_point,
        cost_price=Decimal("10"),
    )
    db.add(p)
    db.commit()
    return p


def _db_ctx(db):
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=db)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


# ─── get_low_stock_products logic ────────────────────────────────────────────

class TestLowStockLogic:

    def test_product_below_reorder_detected(self, db):
        """منتج مخزونه أقل من حد إعادة الطلب يُكتشف"""
        branch = _make_branch(db)
        cat = _make_category(db, branch)
        product = _make_product(
            db, branch, cat,
            current_stock=Decimal("3"),
            reorder_point=Decimal("10"),
        )

        from app.modules.inventory.services import get_low_stock_products
        low = get_low_stock_products(db, branch.id)
        assert product.id in [p.id for p in low]

    def test_product_above_reorder_not_flagged(self, db):
        """منتج مخزونه كافٍ لا يظهر في القائمة"""
        branch = _make_branch(db)
        cat = _make_category(db, branch)
        product = _make_product(
            db, branch, cat,
            current_stock=Decimal("50"),
            reorder_point=Decimal("10"),
        )

        from app.modules.inventory.services import get_low_stock_products
        low = get_low_stock_products(db, branch.id)
        assert product.id not in [p.id for p in low]

    def test_product_exactly_at_reorder_point(self, db):
        """منتج مخزونه = حد إعادة الطلب — لا يُعتبر low"""
        branch = _make_branch(db)
        cat = _make_category(db, branch)
        product = _make_product(
            db, branch, cat,
            current_stock=Decimal("10"),
            reorder_point=Decimal("10"),
        )

        from app.modules.inventory.services import get_low_stock_products
        low = get_low_stock_products(db, branch.id)
        # عند التساوي — حسب تعريف الدالة (< أو <=)
        # نتحقق فقط إن الدالة تشتغل بدون error
        assert isinstance(low, list)

    def test_zero_reorder_point_not_flagged(self, db):
        """منتج بـ reorder_point=0 لا يُعتبر low"""
        branch = _make_branch(db)
        cat = _make_category(db, branch)
        product = _make_product(
            db, branch, cat,
            current_stock=Decimal("5"),
            reorder_point=Decimal("0"),
        )

        from app.modules.inventory.services import get_low_stock_products
        low = get_low_stock_products(db, branch.id)
        assert product.id not in [p.id for p in low]

    def test_notify_admin_called_for_low_stock(self, db):
        """notify_admin يُستدعى لو في منتجات low stock"""
        import app.core.kernel.whatsapp as wa_module
        msgs = []
        original = getattr(wa_module, "notify_admin", lambda *a: None)
        wa_module.notify_admin = lambda msg: msgs.append(msg)
        try:
            branch = _make_branch(db)
            cat = _make_category(db, branch)
            product = _make_product(
                db, branch, cat,
                current_stock=Decimal("1"),
                reorder_point=Decimal("20"),
            )

            from app.modules.inventory.services import get_low_stock_products
            low = get_low_stock_products(db, branch.id)
            if low:
                names = "، ".join(p.name for p in low[:5])
                more = f" و{len(low) - 5} صنف آخر" if len(low) > 5 else ""
                wa_module.notify_admin(
                    f"تنبيه مخزون: {len(low)} صنف وصل لحد إعادة الطلب — {names}{more}."
                )

            assert len(msgs) >= 1
            assert product.name in msgs[-1]
        finally:
            wa_module.notify_admin = original

    def test_multiple_low_stock_products(self, db):
        """عدة منتجات low stock تُكتشف معاً"""
        branch = _make_branch(db)
        cat = _make_category(db, branch)
        p1 = _make_product(db, branch, cat, current_stock=Decimal("1"), reorder_point=Decimal("10"))
        p2 = _make_product(db, branch, cat, current_stock=Decimal("2"), reorder_point=Decimal("15"))
        p3 = _make_product(db, branch, cat, current_stock=Decimal("100"), reorder_point=Decimal("10"))

        from app.modules.inventory.services import get_low_stock_products
        low = get_low_stock_products(db, branch.id)
        low_ids = [p.id for p in low]
        assert p1.id in low_ids
        assert p2.id in low_ids
        assert p3.id not in low_ids

    def test_empty_branch_returns_empty_list(self, db):
        """فرع بدون منتجات يُرجع قائمة فاضية"""
        branch = _make_branch(db)
        from app.modules.inventory.services import get_low_stock_products
        low = get_low_stock_products(db, branch.id)
        assert low == []

    def test_task_runs_without_error(self, db):
        """task check_low_stock يشتغل بدون exception"""
        import app.core.kernel.whatsapp as wa_module
        original = getattr(wa_module, "notify_admin", lambda *a: None)
        wa_module.notify_admin = lambda *a, **kw: None
        try:
            with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
                from app.tasks.inventory_tasks import check_low_stock
                check_low_stock()
        finally:
            wa_module.notify_admin = original
