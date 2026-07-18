"""
tests/test_api/test_inventory.py
Integration tests for inventory module.
"""
from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.modules.inventory.schemas import (
    ProductCreate, StockMovementCreate, SupplierCreate, WarehouseCreate,
    PurchaseRequestCreate, PurchaseRequestItemCreate,
    StockCountCreate,
)
from app.modules.inventory import services, crud


@pytest.fixture
def branch(db: Session):
    import uuid
    from app.modules.core.models import Branch
    b = Branch(name="Test", name_ar="اختبار", code=f"INV-{uuid.uuid4().hex[:6].upper()}")
    db.add(b); db.flush()
    return b


@pytest.fixture
def warehouse(db: Session, branch):
    import uuid
    data = WarehouseCreate(branch_id=branch.id, name="المخزن الرئيسي",
                           code=f"WH-{uuid.uuid4().hex[:6].upper()}")
    return services.create_warehouse(db, data)


@pytest.fixture
def supplier(db: Session, branch):
    data = SupplierCreate(branch_id=branch.id, name="شركة التوريد المصرية")
    return services.create_supplier(db, data)


@pytest.fixture
def product(db: Session, branch, warehouse):
    import uuid
    data = ProductCreate(
        branch_id=branch.id, warehouse_id=warehouse.id,
        name="زيت طعام", sku=f"OIL-{uuid.uuid4().hex[:6].upper()}", unit="liter",
        cost_price=Decimal("20"), min_stock=Decimal("5"),
        reorder_point=Decimal("10"),
    )
    return services.create_product(db, data)


class TestProduct:

    def test_create_product(self, db, branch, warehouse):
        import uuid
        data = ProductCreate(
            branch_id=branch.id, name="سكر",
            sku=f"SGR-{uuid.uuid4().hex[:6].upper()}", unit="kg",
        )
        p = services.create_product(db, data)
        assert p.id is not None
        assert p.current_stock == Decimal("0")

    def test_duplicate_sku_raises(self, db, branch, product):
        data = ProductCreate(
            branch_id=branch.id, name="نفس الـ sku",
            sku=product.sku, unit="liter",
        )
        with pytest.raises(ValueError, match="SKU"):
            services.create_product(db, data)

    def test_product_not_found_404(self, db):
        with pytest.raises(ValueError):
            services.get_product_or_404(db, 9999)


class TestBarcodeLabels:

    def test_generate_labels_for_one_product(self, db, branch, product):
        pdf = services.generate_barcode_labels_pdf(db, branch.id, [product.id])
        assert pdf.startswith(b"%PDF")

    def test_generate_labels_multi_page(self, db, branch, warehouse):
        import uuid
        ids = []
        for i in range(30):  # > 24 per page (3x8 grid) forces a 2nd page
            data = ProductCreate(
                branch_id=branch.id, warehouse_id=warehouse.id,
                name=f"صنف {i}", sku=f"SKU-{uuid.uuid4().hex[:8].upper()}", unit="piece",
            )
            ids.append(services.create_product(db, data).id)
        pdf = services.generate_barcode_labels_pdf(db, branch.id, ids)
        assert pdf.startswith(b"%PDF")

    def test_no_matching_products_raises(self, db, branch):
        with pytest.raises(ValueError):
            services.generate_barcode_labels_pdf(db, branch.id, [9999])

    def test_ignores_product_from_other_branch(self, db, branch, product):
        import uuid
        from app.modules.core.models import Branch
        other = Branch(name="Other", name_ar="آخر", code=f"OTH-{uuid.uuid4().hex[:6].upper()}")
        db.add(other); db.flush()
        with pytest.raises(ValueError):
            services.generate_barcode_labels_pdf(db, other.id, [product.id])


class TestStockMovement:

    def test_purchase_in_increases_stock(self, db, branch, product, warehouse):
        data = StockMovementCreate(
            branch_id=branch.id, product_id=product.id,
            warehouse_id=warehouse.id, movement_type="purchase_in",
            quantity=Decimal("50"), unit_cost=Decimal("20"),
            moved_at=datetime.utcnow(),
        )
        services.record_movement(db, data, moved_by=1)
        db.refresh(product)
        assert product.current_stock == Decimal("50")

    def test_consumption_decreases_stock(self, db, branch, product, warehouse):
        # أولاً أضف مخزون
        add = StockMovementCreate(
            branch_id=branch.id, product_id=product.id,
            warehouse_id=warehouse.id, movement_type="purchase_in",
            quantity=Decimal("100"), unit_cost=Decimal("20"),
            moved_at=datetime.utcnow(),
        )
        services.record_movement(db, add, moved_by=1)

        # ثم استهلك
        services.consume_stock(
            db, branch.id, product.id, warehouse.id,
            quantity=Decimal("30"), moved_by=1,
        )
        db.refresh(product)
        assert product.current_stock == Decimal("70")

    def test_cannot_consume_more_than_stock(self, db, branch, product, warehouse):
        with pytest.raises(ValueError, match="أكبر من الرصيد"):
            services.consume_stock(
                db, branch.id, product.id, warehouse.id,
                quantity=Decimal("999"), moved_by=1,
            )

    def test_low_stock_detection(self, db, branch, product, warehouse):
        # product.reorder_point = 10, current_stock = 0
        low = services.get_low_stock_products(db, branch.id)
        assert any(p.id == product.id for p in low)

    def test_concurrent_movement_raises_concurrency_error(self, db, branch, product, warehouse, monkeypatch):
        """باج حقيقي كان هنا: adjust_stock كان بيقرا/يعدّل current_stock من
        غير أي قفل صف (عكس beach.crud.lock_inventory_for_update و
        pms.crud.lock_room_for_booking) — بينادى عليها من 3+ أماكن (مطعم/
        كافيه عبر consume_stock، استلام أمر شراء، اعتماد جرد مخزون)، يعني
        تحت حمل متزامن حقيقي (كاشير مطعم وكافيه بيستهلكوا نفس الصنف في نفس
        اللحظة) كانت ممكن تحصل lost update فعلي على current_stock. اتصلح
        بقفل صف Product (SELECT FOR UPDATE NOWAIT) قبل أي تعديل — هنا بنحاكي
        عملية تانية ماسكة الصف بمحاكاة OperationalError من القفل نفسه (نفس
        أسلوب test_concurrent_sale_raises_concurrency_error في test_beach.py)."""
        from tests.conftest import make_lock_not_available_error

        def _raise_locked(*_args, **_kwargs):
            raise make_lock_not_available_error()

        monkeypatch.setattr(crud, "lock_product_for_update", _raise_locked)

        data = StockMovementCreate(
            branch_id=branch.id, product_id=product.id,
            warehouse_id=warehouse.id, movement_type="purchase_in",
            quantity=Decimal("10"), unit_cost=Decimal("20"),
            moved_at=datetime.utcnow(),
        )
        with pytest.raises(services.InventoryConcurrencyError, match="مشغول"):
            services.record_movement(db, data, moved_by=1)

    def test_unrelated_operational_error_is_not_masked_as_concurrency(
        self, db, branch, product, warehouse, monkeypatch,
    ):
        """مراجعة Codex الثانية (Gate 1B): مش كل OperationalError معناها
        "الصف مشغول" — لازم يتحول لخطأ تزامن (409) بس لو SQLSTATE فعليًا
        55P03 (lock_not_available). أي مشكلة قاعدة بيانات تانية (هنا: فقدان
        اتصال) لازم تتصعّد كخطأ حقيقي، مش تتغطى بـ"الصنف مشغول" مضلّلة."""
        from tests.conftest import make_unrelated_operational_error

        def _raise_unrelated(*_args, **_kwargs):
            raise make_unrelated_operational_error()

        monkeypatch.setattr(crud, "lock_product_for_update", _raise_unrelated)

        data = StockMovementCreate(
            branch_id=branch.id, product_id=product.id,
            warehouse_id=warehouse.id, movement_type="purchase_in",
            quantity=Decimal("10"), unit_cost=Decimal("20"),
            moved_at=datetime.utcnow(),
        )
        with pytest.raises(OperationalError) as exc_info:
            services.record_movement(db, data, moved_by=1)
        assert not isinstance(exc_info.value, services.InventoryConcurrencyError)

    def test_consume_stock_lock_failure_rolls_back_and_session_stays_usable(
        self, db, branch, product, warehouse, monkeypatch,
    ):
        """مراجعة Codex الثالثة (Gate 1B): consume_stock's أول قفل (على
        product.cost_price الطازة) كان بيرفع InventoryConcurrencyError من
        غير db.rollback() — على PostgreSQL الحقيقي ده بيسيب الـtransaction
        في حالة "aborted"، وأي استخدام تاني لنفس الـsession (حتى قراءة
        عادية) بيفشل بـInFailedSqlTransaction لحد ما rollback حقيقي يحصل.
        هنا بنثبت: (أ) الاستثناء الصح اتاخد، (ب) الـsession نفسها تفضل
        قابلة للاستخدام فعليًا بعد كده (عملية تانية على نفس الـdb تنجح)."""
        from tests.conftest import make_lock_not_available_error

        def _raise_locked(*_args, **_kwargs):
            raise make_lock_not_available_error()

        monkeypatch.setattr(crud, "lock_product_for_update", _raise_locked)

        with pytest.raises(services.InventoryConcurrencyError, match="مشغول"):
            services.consume_stock(
                db, branch_id=branch.id, product_id=product.id,
                warehouse_id=warehouse.id, quantity=Decimal("1"),
                allow_negative=True,
            )

        # الـsession لازم تفضل قابلة للاستخدام فعليًا — لا InFailedSqlTransaction
        # ولا أي حالة "poisoned" — نثبت ده بعملية DB حقيقية تانية بعد التقاط
        # الخطأ مباشرة، من غير أي rollback/close يدوي من التست نفسه.
        monkeypatch.undo()
        fresh_read = crud.get_product(db, product.id)
        assert fresh_read is not None
        assert fresh_read.id == product.id

        result = services.consume_stock(
            db, branch_id=branch.id, product_id=product.id,
            warehouse_id=warehouse.id, quantity=Decimal("1"),
            allow_negative=True,
        )
        assert result is not None

    def test_consume_stock_uses_freshly_locked_cost_price_not_stale_read(
        self, db, branch, product, warehouse,
    ):
        """مراجعة Codex الثانية (Gate 1B): consume_stock كان بيقرا
        product.cost_price عبر get_product_or_404 (قراءة غير مقفولة) قبل
        ما record_movement يقفل نفس الصف — يعني StockMovement.unit_cost
        وقيمة COGS كانوا ممكن يُبنوا على cost_price قديم. نفس نمط
        test_beach.py's dbA/dbB (السطور ~270-314): جلستين حقيقيتين منفصلتين
        على نفس الـStaticPool engine — A تعدّل cost_price وتعتمد (commit)،
        وB (اللي عندها قراءة أقدم لنفس المنتج في identity map بتاعتها)
        لازم تستخدم القيمة الجديدة المُعتمَدة، مش القديمة المخزّنة."""
        from tests.conftest import TestingSessionLocal
        from app.modules.finance.models import Account

        db.add_all([
            Account(branch_id=branch.id, code="1200", name="Inventory", account_type="asset"),
            Account(branch_id=branch.id, code="5200", name="COGS", account_type="expense"),
        ])
        db.commit()

        dbA = TestingSessionLocal()
        dbB = TestingSessionLocal()
        try:
            # الاتنين بيعملوا قراءة أولى غير مقفولة لنفس المنتج — زي
            # get_product_or_404 القديمة قبل الإصلاح — فيشوفوا cost_price
            # الأصلي (20) في identity map كل جلسة.
            productA = crud.get_product(dbA, product.id)
            productB = crud.get_product(dbB, product.id)
            assert productA.cost_price == Decimal("20")
            assert productB.cost_price == Decimal("20")

            # A تقفل، تغيّر cost_price، تعتمد — القيمة الحقيقية بقت 35 دلوقتي.
            lockedA = crud.lock_product_for_update(dbA, productA.id)
            lockedA.cost_price = Decimal("35")
            dbA.commit()

            # B تستهلك مخزون بعد كده — لازم unit_cost/COGS تتبني على 35
            # (القيمة الحقيقية المُعتمَدة)، مش 20 (القيمة القديمة في
            # identity map جلسة B من القراءة الأولى).
            mov = services.consume_stock(
                dbB, branch_id=branch.id, product_id=product.id,
                warehouse_id=warehouse.id, quantity=Decimal("2"),
                allow_negative=True,
            )
            assert mov.unit_cost == Decimal("35"), (
                f"unit_cost={mov.unit_cost} — لسه بيستخدم cost_price قديم "
                "(20) من identity map بدل القيمة الحقيقية المُعتمَدة حديثًا (35)"
            )

            from app.modules.finance import crud as finance_crud
            entries, total = finance_crud.list_journal_entries(dbB, branch.id, source="inventory")
            assert total == 1
            cogs_line = next(l for l in entries[0].lines if l.debit > 0)
            assert cogs_line.debit == Decimal("70.00"), (
                f"قيد COGS = {cogs_line.debit}, متوقع 70.00 (2 × 35) — مبني "
                "على cost_price قديم"
            )
        finally:
            dbB.rollback()
            dbA.close()


class TestPurchaseOrder:

    def test_create_and_receive(self, db, branch, product, warehouse):
        from app.modules.inventory.schemas import (
            PurchaseOrderCreate, PurchaseOrderItemCreate, ReceiveItemsRequest,
        )
        from datetime import date

        po_data = PurchaseOrderCreate(
            branch_id=branch.id,
            supplier_name="مورد الزيوت",
            ordered_at=date.today(),
            items=[PurchaseOrderItemCreate(
                product_id=product.id,
                ordered_qty=Decimal("100"),
                unit_cost=Decimal("18"),
            )],
        )
        po = services.create_purchase_order(db, po_data)
        assert po.status == "draft"
        assert po.order_number.startswith("PO-")

        # استلام
        req = ReceiveItemsRequest(
            items=[{"item_id": po.items[0].id, "received_qty": 100}],
            warehouse_id=warehouse.id,
            received_at=date.today(),
        )
        po = services.receive_purchase_order(db, po.id, req, received_by=1)
        assert po.status == "received"
        db.refresh(product)
        assert product.current_stock == Decimal("100")

    def test_cannot_receive_cancelled_po(self, db, branch, product, warehouse):
        from app.modules.inventory.schemas import (
            PurchaseOrderCreate, PurchaseOrderItemCreate, ReceiveItemsRequest,
        )

        po_data = PurchaseOrderCreate(
            branch_id=branch.id, supplier_name="مورد",
            ordered_at=date.today(),
            items=[PurchaseOrderItemCreate(
                product_id=product.id, ordered_qty=Decimal("10"), unit_cost=Decimal("5"),
            )],
        )
        po = services.create_purchase_order(db, po_data)
        # نغير الحالة يدوياً
        po.status = "cancelled"
        db.flush(); db.commit()

        req = ReceiveItemsRequest(
            items=[{"item_id": po.items[0].id, "received_qty": 10}],
            warehouse_id=warehouse.id, received_at=date.today(),
        )
        with pytest.raises(ValueError):
            services.receive_purchase_order(db, po.id, req, received_by=1)


class TestPurchaseApproval:

    def test_create_purchase_request(self, db, branch, product):
        data = PurchaseRequestCreate(
            branch_id=branch.id,
            requester_id=1,
            department="Kitchen",
            notes="Monthly order",
            items=[
                PurchaseRequestItemCreate(
                    product_id=product.id,
                    quantity_requested=Decimal("10"),
                    unit="liter",
                    estimated_unit_cost=Decimal("20"),
                )
            ],
        )
        pr = services.create_purchase_request(db, data)
        assert pr.id is not None
        assert pr.status == "draft"
        assert pr.total_estimated == Decimal("200")
        assert len(pr.items) == 1
        assert pr.items[0].product_id == product.id

    def test_dept_approval_workflow(self, db, branch, product):
        data = PurchaseRequestCreate(
            branch_id=branch.id,
            requester_id=1,
            department="Bar",
            items=[
                PurchaseRequestItemCreate(
                    product_id=product.id,
                    quantity_requested=Decimal("5"),
                    unit="liter",
                    estimated_unit_cost=Decimal("10"),
                )
            ],
        )
        pr = services.create_purchase_request(db, data)
        pr = services.approve_purchase_request(db, pr.id, approver_id=2, level="dept")
        assert pr.status == "dept_approved"
        assert len(pr.approvals) == 1
        assert pr.approvals[0].level == "dept"
        assert pr.approvals[0].status == "approved"
        assert pr.approvals[0].approver_id == 2

    def test_finance_approval_after_dept(self, db, branch, product):
        data = PurchaseRequestCreate(
            branch_id=branch.id,
            requester_id=1,
            department="Housekeeping",
            items=[
                PurchaseRequestItemCreate(
                    product_id=product.id,
                    quantity_requested=Decimal("3"),
                    unit="piece",
                    estimated_unit_cost=Decimal("15"),
                )
            ],
        )
        pr = services.create_purchase_request(db, data)
        services.approve_purchase_request(db, pr.id, approver_id=2, level="dept")
        pr = services.approve_purchase_request(db, pr.id, approver_id=3, level="finance")
        assert pr.status == "finance_approved"
        assert len(pr.approvals) == 2

    def test_reject_pr(self, db, branch, product):
        data = PurchaseRequestCreate(
            branch_id=branch.id,
            requester_id=1,
            department="Maintenance",
            items=[
                PurchaseRequestItemCreate(
                    product_id=product.id,
                    quantity_requested=Decimal("2"),
                    unit="piece",
                    estimated_unit_cost=Decimal("50"),
                )
            ],
        )
        pr = services.create_purchase_request(db, data)
        pr = services.reject_purchase_request(
            db, pr.id, approver_id=2, level="dept", reason="Budget exceeded"
        )
        assert pr.status == "rejected"
        assert pr.rejected_reason == "Budget exceeded"
        assert len(pr.approvals) == 1
        assert pr.approvals[0].status == "rejected"

    def test_cannot_approve_wrong_state(self, db, branch, product):
        data = PurchaseRequestCreate(
            branch_id=branch.id,
            requester_id=1,
            department="Pool",
            items=[
                PurchaseRequestItemCreate(
                    product_id=product.id,
                    quantity_requested=Decimal("1"),
                    unit="piece",
                    estimated_unit_cost=Decimal("100"),
                )
            ],
        )
        pr = services.create_purchase_request(db, data)
        # Cannot do finance approval before dept approval
        with pytest.raises(ValueError, match="dept_approved"):
            services.approve_purchase_request(db, pr.id, approver_id=2, level="finance")

    def test_convert_to_purchase_order(self, db, branch, product, supplier):
        data = PurchaseRequestCreate(
            branch_id=branch.id,
            requester_id=1,
            department="Restaurant",
            items=[
                PurchaseRequestItemCreate(
                    product_id=product.id,
                    quantity_requested=Decimal("20"),
                    unit="liter",
                    estimated_unit_cost=Decimal("18"),
                )
            ],
        )
        pr = services.create_purchase_request(db, data)
        services.approve_purchase_request(db, pr.id, approver_id=2, level="dept")
        services.approve_purchase_request(db, pr.id, approver_id=3, level="finance")
        po = services.convert_to_purchase_order(db, pr.id, supplier.id)
        assert po.id is not None
        assert po.status == "draft"
        assert po.total_amount == Decimal("360")  # 20 * 18
        assert po.supplier_id == supplier.id
        assert po.supplier_name == supplier.name  # لقطة (snapshot) — مش "TBD" بعد الآن
        db.refresh(pr)
        assert pr.status == "converted"

    def test_convert_requires_valid_supplier_in_same_branch(self, db, branch, product):
        """المورد لازم يتبع نفس فرع طلب الشراء — منع تلبيس مورد فرع تاني
        (نفس فئة الحماية الموجودة في كل مكان تاني بالمشروع بين الفروع)."""
        import uuid

        from app.modules.core.models import Branch

        other_branch = Branch(name="Other", name_ar="فرع آخر", code=f"OTH-{uuid.uuid4().hex[:6].upper()}")
        db.add(other_branch); db.flush()
        other_supplier = services.create_supplier(
            db, SupplierCreate(branch_id=other_branch.id, name="مورد فرع تاني"),
        )

        data = PurchaseRequestCreate(
            branch_id=branch.id, requester_id=1, department="Restaurant",
            items=[PurchaseRequestItemCreate(
                product_id=product.id, quantity_requested=Decimal("5"),
                unit="liter", estimated_unit_cost=Decimal("10"),
            )],
        )
        pr = services.create_purchase_request(db, data)
        services.approve_purchase_request(db, pr.id, approver_id=2, level="dept")
        services.approve_purchase_request(db, pr.id, approver_id=3, level="finance")
        with pytest.raises(ValueError, match="فرع"):
            services.convert_to_purchase_order(db, pr.id, other_supplier.id)


class TestStockCount:

    def test_create_stock_count(self, db, branch, product, warehouse):
        data = StockCountCreate(
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            count_date=date.today(),
            counted_by=1,
        )
        sc = services.create_stock_count(db, data)
        assert sc.id is not None
        assert sc.status == "draft"
        # product belongs to this branch so it should appear
        assert len(sc.lines) >= 1
        line = next((l for l in sc.lines if l.product_id == product.id), None)
        assert line is not None

    def test_create_stock_count_specific_products(self, db, branch, product, warehouse):
        data = StockCountCreate(
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            count_date=date.today(),
            counted_by=1,
            product_ids=[product.id],
        )
        sc = services.create_stock_count(db, data)
        assert len(sc.lines) == 1
        assert sc.lines[0].product_id == product.id
        assert sc.lines[0].system_quantity == product.current_stock

    def test_submit_and_approve_count(self, db, branch, product, warehouse):
        # Add initial stock
        move_data = StockMovementCreate(
            branch_id=branch.id,
            product_id=product.id,
            warehouse_id=warehouse.id,
            movement_type="purchase_in",
            quantity=Decimal("100"),
            unit_cost=Decimal("20"),
            moved_at=datetime.utcnow(),
        )
        services.record_movement(db, move_data, moved_by=1)
        db.refresh(product)
        assert product.current_stock == Decimal("100")

        # Create stock count
        data = StockCountCreate(
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            count_date=date.today(),
            counted_by=1,
            product_ids=[product.id],
        )
        sc = services.create_stock_count(db, data)
        line = sc.lines[0]
        assert line.system_quantity == Decimal("100")

        # Submit with variance (physically counted 95)
        sc = services.submit_stock_count(db, sc.id, [
            {"line_id": line.id, "counted_quantity": Decimal("95")},
        ])
        assert sc.status == "submitted"
        db.refresh(sc)
        updated_line = next(l for l in sc.lines if l.id == line.id)
        assert updated_line.variance == Decimal("-5")

        # Approve — adjustment should be posted
        sc = services.approve_stock_count(db, sc.id, approved_by=2)
        assert sc.status == "adjustment_posted"
        assert sc.approved_by == 2

        db.refresh(product)
        assert product.current_stock == Decimal("95")

    def test_cannot_submit_non_draft_count(self, db, branch, product, warehouse):
        data = StockCountCreate(
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            count_date=date.today(),
            counted_by=1,
            product_ids=[product.id],
        )
        sc = services.create_stock_count(db, data)
        line = sc.lines[0]

        # Submit first time
        services.submit_stock_count(db, sc.id, [
            {"line_id": line.id, "counted_quantity": Decimal("0")},
        ])

        # Cannot submit again (already submitted)
        with pytest.raises(ValueError, match="submitted"):
            services.submit_stock_count(db, sc.id, [
                {"line_id": line.id, "counted_quantity": Decimal("0")},
            ])
