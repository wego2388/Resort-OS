"""tests/test_hist_inventory.py — HIST-01 Inventory/Purchasing/Maintenance
generator (OPS-DATA-02 §10.6).

⚠️ Warehouse.code فريد عالميًا (نفس منطق منتجع واحد اللي Employee.
employee_code بيتبعه — راجع test_hist_hr.py's docstring لنفس السبب بالظبط)
فالمولّد بيستخدم كود ثابت "HIST-WH-01". عشان كده الاختبارات هنا بتشغّل
المولّد **مرة واحدة بس** عبر فيكستشر class-scoped، مش مرة لكل test method."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.hist_inventory import generate as generate_inventory
from tests.conftest import TestingSessionLocal


def _seed_accounts(db: Session, branch_id: int) -> None:
    from app.modules.finance.models import Account
    for code, name, acc_type in [
        ("1200", "Inventory", "asset"), ("2200", "Accounts Payable", "liability"),
        ("5200", "COGS", "expense"),
    ]:
        db.add(Account(branch_id=branch_id, code=code, name=name, account_type=acc_type))
    db.commit()


class _Ctx:
    def __init__(self, branch_id: int):
        self.branch_id = branch_id
        self.period_year = 2026
        self.period_month = 7
        self.tz_name = "Africa/Cairo"
        self.actor_id = 1


@pytest.fixture(scope="class")
def branch_id(setup_db) -> int:
    from app.modules.core.models import Branch

    db = TestingSessionLocal()
    try:
        b = Branch(name="Test Inventory HIST", name_ar="اختبار مخزون تاريخي",
                   code=f"HI-{uuid.uuid4().hex[:6].upper()}")
        db.add(b)
        db.commit()
        _seed_accounts(db, b.id)
        generate_inventory(db, _Ctx(b.id))
        db.commit()
        return b.id
    finally:
        db.close()


class TestHistInventoryGenerator:
    def test_opening_balance_totals_420000(self, db: Session, branch_id: int):
        from app.modules.inventory.models import Product, StockMovement

        products = db.query(Product).filter(Product.branch_id == branch_id).all()
        assert len(products) == 5
        opening_total = sum(
            m.quantity * m.unit_cost
            for m in db.query(StockMovement)
            .filter(StockMovement.branch_id == branch_id, StockMovement.reference_type == "opening_balance")
            .all()
        )
        assert opening_total == Decimal("420000.00")

    def test_purchase_orders_received_value_totals_160000(self, db: Session, branch_id: int):
        from app.modules.finance.models import Account, JournalLine
        from app.modules.inventory.models import PurchaseOrder

        pos = db.query(PurchaseOrder).filter(PurchaseOrder.branch_id == branch_id).all()
        assert len(pos) == 5
        assert sum(1 for po in pos if po.status == "received") == 4
        assert sum(1 for po in pos if po.status == "partial") == 1

        inv_account = db.query(Account).filter_by(branch_id=branch_id, code="1200").first()
        lines = db.query(JournalLine).filter(JournalLine.account_id == inv_account.id).all()
        # 1200 بياخد Dr من الاستلامات و Cr من الاستهلاك
        assert sum(l.debit for l in lines) == Decimal("160000.00")
        assert sum(l.credit for l in lines) == Decimal("185000.00")

    def test_closing_valuation_matches_brief_exactly(self, db: Session, branch_id: int):
        from app.modules.inventory.models import Product

        products = db.query(Product).filter(Product.branch_id == branch_id).all()
        closing_valuation = sum(p.current_stock * p.cost_price for p in products)
        assert closing_valuation == Decimal("395000.00")
        assert all(p.current_stock >= 0 for p in products)

    def test_low_stock_product_detected(self, db: Session, branch_id: int):
        from app.modules.inventory import services as inv_services

        low_stock = inv_services.get_low_stock_products(db, branch_id)
        skus = {p.sku for p in low_stock}
        assert "HIST-FB-002" in skus  # زيت الطبخ: رصيد ختامي 800 < reorder_point 900

    def test_ten_work_orders_with_correct_status_split(self, db: Session, branch_id: int):
        from app.modules.maintenance.models import WorkOrder

        wos = db.query(WorkOrder).filter(WorkOrder.branch_id == branch_id).all()
        assert len(wos) == 10
        by_status: dict[str, int] = {}
        for wo in wos:
            by_status[wo.status] = by_status.get(wo.status, 0) + 1
        assert by_status.get("pending_parts") == 1
        assert by_status.get("completed") == 2
        assert by_status.get("cancelled") == 1
        assert by_status.get("open", 0) == 6

    def test_asset_released_after_completion_and_cancellation(self, db: Session, branch_id: int):
        from app.modules.maintenance.models import Asset

        assets = db.query(Asset).filter(Asset.branch_id == branch_id).order_by(Asset.id).all()
        assert len(assets) == 2
        # الاتنين كانوا critical (اتحطوا under_maintenance وقت الإنشاء) وبعدين
        # اتحرروا لـoperational بعد الإكمال/الإلغاء (_release_asset_if_no_open_orders)
        assert all(a.status == "operational" for a in assets)

    def test_work_order_parts_deducted_from_inventory(self, db: Session, branch_id: int):
        from app.modules.maintenance.models import WorkOrder, WorkOrderPart

        parts = (
            db.query(WorkOrderPart)
            .join(WorkOrder, WorkOrderPart.work_order_id == WorkOrder.id)
            .filter(WorkOrder.branch_id == branch_id, WorkOrderPart.product_id.isnot(None))
            .all()
        )
        total_parts_cost = sum(p.total_cost for p in parts)
        assert total_parts_cost == Decimal("10000.00")  # 30×200 + 20×200
