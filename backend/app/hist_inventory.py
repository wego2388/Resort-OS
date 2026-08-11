"""HIST-01 — مولّد بيانات المخزون/المشتريات/الصيانة التاريخية ليوليو 2026
(OPS-DATA-02 §10.6). بيستخدم services الحقيقية بس (inventory.services.
record_movement/consume_stock/create_purchase_order/receive_purchase_order،
maintenance.services.create_work_order/complete_work_order/update_work_order/
add_part_to_wo) — صفر SQL مباشر، صفر float.

⚠️ الحساب المالي مصمَّم عمدًا (نفس أسلوب باقي مولّدات HIST-01 — أرقام
مضبوطة مسبقًا، مش عشوائية) عشان يطابق §10.6 بالظبط:
  رصيد افتتاحي 420,000 + مشتريات مستلمة 160,000 − استهلاك 185,000
  = تقييم ختامي 395,000 (مطابق تمامًا لرقم البريف، بدون أي stock adjustment).
كل سعر وحدة على أمر الشراء = cost_price الافتتاحي لنفس الصنف بالظبط —
عشان المتوسط المرجّح (weighted average) في crud.receive_purchase_order
يفضل ثابت من غير أي انحراف، فالتقييم الختامي يبقى قابل للتحقق حسابيًا
(current_stock × cost_price لكل صنف) مش مجرد رقم مفترض.

⚠️ أصلين خفيفين (assets) بيتعملوا هنا بس (بدون بيانات إهلاك — دي مسؤولية
مولّد الأصول الثابتة §10.7 المنفصل) عشان اختبار "تحرير الأصل بعد الإكمال/
الإلغاء" (§10.6 بند 5) يحتاج أصل حقيقي مرتبط بأمر صيانة critical — باقي
أوامر الصيانة (preventive/corrective/pending_parts) بلا asset_id عمدًا،
مفيش تضارب مع §10.7 لاحقًا (أصول مختلفة تمامًا، أكواد HIST-MAINT-AST-*)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from app.resort_os.clock import scenario_clock

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.operational_history_seed import ScenarioContext


def generate(db: "Session", ctx: "ScenarioContext") -> dict:
    from app.modules.inventory import services as inv_services
    from app.modules.inventory.schemas import (
        CategoryCreate, ProductCreate, PurchaseOrderCreate, PurchaseOrderItemCreate,
        ReceiveItemsRequest, StockMovementCreate, SupplierCreate, WarehouseCreate,
    )
    from app.modules.maintenance import services as maint_services
    from app.modules.maintenance.schemas import (
        AssetCreate, WorkOrderCreate, WorkOrderPartCreate, WorkOrderUpdate,
    )

    branch_id = ctx.branch_id
    tz_name = ctx.tz_name
    from zoneinfo import ZoneInfo  # noqa: PLC0415
    tz = ZoneInfo(tz_name)
    month_start = date(ctx.period_year, ctx.period_month, 1)

    with scenario_clock(datetime(ctx.period_year, ctx.period_month, 1, 9, 0, tzinfo=tz)):
        warehouse = inv_services.create_warehouse(db, WarehouseCreate(
            branch_id=branch_id, name="Main Store HIST", name_ar="المخزن الرئيسي",
            code="HIST-WH-01",
        ))
        categories = {
            key: inv_services.create_category(db, CategoryCreate(
                branch_id=branch_id, name=name, name_ar=name_ar,
            ))
            for key, name, name_ar in [
                ("fb", "Food & Beverage", "أغذية ومشروبات"),
                ("hsk", "Housekeeping", "تدبير منزلي"),
                ("maint", "Maintenance", "صيانة"),
                ("beach", "Beach & Retail", "شاطئ وتجزئة"),
            ]
        }
        db.flush()

        # ── منتجات + رصيد افتتاحي (420,000 بالظبط) ───────────────────────
        # (category_key, name, sku, cost_price, opening_qty, reorder_point)
        product_specs = [
            ("fb", "أرز وحبوب - HIST", "HIST-FB-001", Decimal("20.00"), Decimal("4000"), Decimal("500")),
            ("fb", "زيت طبخ - HIST", "HIST-FB-002", Decimal("60.00"), Decimal("1000"), Decimal("900")),
            ("hsk", "مناشف ومستلزمات نظافة - HIST", "HIST-HSK-001", Decimal("40.00"), Decimal("2000"), Decimal("300")),
            ("maint", "قطع غيار عامة - HIST", "HIST-MNT-001", Decimal("200.00"), Decimal("600"), Decimal("150")),
            ("beach", "منتجات شاطئ للبيع - HIST", "HIST-BCH-001", Decimal("80.00"), Decimal("1000"), Decimal("200")),
        ]
        products = {}
        for key, name, sku, cost, opening_qty, reorder_point in product_specs:
            product = inv_services.create_product(db, ProductCreate(
                branch_id=branch_id, category_id=categories[key].id, warehouse_id=warehouse.id,
                name=name, sku=sku, unit="piece", cost_price=cost,
                min_stock=reorder_point / 2, reorder_point=reorder_point,
            ))
            db.flush()
            inv_services.record_movement(db, StockMovementCreate(
                branch_id=branch_id, product_id=product.id, warehouse_id=warehouse.id,
                movement_type="adjustment", quantity=opening_qty, unit_cost=cost,
                reference_type="opening_balance", moved_at=datetime.combine(month_start, datetime.min.time()),
                notes="HIST-01 رصيد افتتاحي 2026-06-30",
            ), moved_by=0)
            products[sku] = product
        p_rice, p_oil, p_towels, p_parts, p_beach = (
            products["HIST-FB-001"], products["HIST-FB-002"], products["HIST-HSK-001"],
            products["HIST-MNT-001"], products["HIST-BCH-001"],
        )

        # ── موردون + 5 أوامر شراء (مستلَم 160,000 بالظبط: 4 كامل + 1 جزئي) ──
        suppliers = {
            key: inv_services.create_supplier(db, SupplierCreate(
                branch_id=branch_id, name=name, payment_terms_days=30,
            ))
            for key, name in [
                ("fb", "مورد أغذية عام - HIST"), ("hsk", "مورد مستلزمات نظافة - HIST"),
                ("maint", "مورد قطع غيار - HIST"), ("beach", "مورد تجزئة شاطئية - HIST"),
            ]
        }
        db.flush()

        def _receive_po(supplier_key: str, product, ordered_qty: Decimal, received_qty: Decimal,
                         order_offset: int, receive_offset: int):
            po = inv_services.create_purchase_order(db, PurchaseOrderCreate(
                branch_id=branch_id, supplier_id=suppliers[supplier_key].id,
                ordered_at=month_start + timedelta(days=order_offset),
                expected_at=month_start + timedelta(days=order_offset + 5),
                items=[PurchaseOrderItemCreate(
                    product_id=product.id, ordered_qty=ordered_qty, unit_cost=product.cost_price,
                )],
            ))
            item = po.items[0]
            po = inv_services.receive_purchase_order(db, po.id, ReceiveItemsRequest(
                items=[{"item_id": item.id, "received_qty": received_qty}],
                warehouse_id=warehouse.id,
                received_at=month_start + timedelta(days=receive_offset),
            ), received_by=ctx.actor_id)
            return po

        po1 = _receive_po("fb", p_rice, Decimal("2000"), Decimal("2000"), 2, 5)       # 40,000 full
        po2 = _receive_po("fb", p_oil, Decimal("300"), Decimal("300"), 3, 6)          # 18,000 full
        po3 = _receive_po("hsk", p_towels, Decimal("500"), Decimal("500"), 4, 8)      # 20,000 full
        po4 = _receive_po("maint", p_parts, Decimal("300"), Decimal("200"), 5, 12)    # 40,000 partial (300 ordered)
        po5 = _receive_po("beach", p_beach, Decimal("525"), Decimal("525"), 6, 10)    # 42,000 full
        assert po4.status == "partial"
        for po in (po1, po2, po3, po5):
            assert po.status == "received"

        # ── استهلاك/COGS (185,000 بالظبط: مطبخ 100,000 + تدبير منزلي
        # 50,000 + صيانة 35,000 — الشاطئ/التجزئة مش بيتستهلك الشهر ده) ─────
        def _issue(product, qty: Decimal, offset: int, dept: str):
            inv_services.consume_stock(
                db, branch_id=branch_id, product_id=product.id, warehouse_id=warehouse.id,
                quantity=qty, reference_type="manual_issue", moved_by=0,
                allow_negative=False,
            )

        _issue(p_rice, Decimal("3500"), 15, "kitchen")   # 70,000
        _issue(p_oil, Decimal("500"), 16, "kitchen")     # 30,000  → مطبخ = 100,000
        _issue(p_towels, Decimal("1250"), 17, "housekeeping")  # 50,000
        _issue(p_parts, Decimal("125"), 18, "maintenance")     # 25,000 (باقي 10,000 عبر قطع أوامر الصيانة تحت)

        # ── أصول خفيفة (بدون بيانات إهلاك — راجع docstring) لاختبار تحرير
        # الأصل بعد إكمال/إلغاء أمر صيانة critical ──────────────────────
        asset_ac = maint_services.create_asset(db, AssetCreate(
            branch_id=branch_id, name="مكيف الاستقبال - HIST", code="HIST-MAINT-AST-01",
            category="hvac",
        ))
        asset_pump = maint_services.create_asset(db, AssetCreate(
            branch_id=branch_id, name="مضخة مياه - HIST", code="HIST-MAINT-AST-02",
            category="plumbing",
        ))
        db.flush()

        # ── 10 أوامر صيانة (preventive×3, corrective×3, pending_parts×1,
        # completed×2 [بقطع من المخزون — تكمّل الـ10,000 الباقية للصيانة]،
        # cancelled×1) ─────────────────────────────────────────────────
        def _create_wo(title: str, order_type: str, priority: str = "medium",
                        asset_id: int | None = None, offset: int = 20):
            return maint_services.create_work_order(db, WorkOrderCreate(
                branch_id=branch_id, asset_id=asset_id, title=title, order_type=order_type,
                priority=priority, scheduled_date=month_start + timedelta(days=offset),
            ), reported_by=0)

        for i in range(3):
            _create_wo(f"صيانة وقائية دورية HIST #{i + 1}", "preventive", offset=8 + i)
        for i in range(3):
            _create_wo(f"صيانة تصحيحية HIST #{i + 1}", "corrective", offset=14 + i)

        wo_pending_parts = _create_wo("صيانة بانتظار قطع غيار - HIST", "corrective", offset=19)
        maint_services.update_work_order(db, wo_pending_parts.id, WorkOrderUpdate(status="pending_parts"))

        wo_completed_1 = _create_wo(
            "إصلاح مكيف الاستقبال - HIST", "corrective", priority="critical",
            asset_id=asset_ac.id, offset=20,
        )
        maint_services.add_part_to_wo(db, wo_completed_1.id, WorkOrderPartCreate(
            product_id=p_parts.id, part_name=p_parts.name, quantity=Decimal("30"),
        ), added_by=0)
        maint_services.complete_work_order(db, wo_completed_1.id)

        wo_completed_2 = _create_wo("صيانة عادية بقطعة صغيرة - HIST", "corrective", offset=21)
        maint_services.add_part_to_wo(db, wo_completed_2.id, WorkOrderPartCreate(
            product_id=p_parts.id, part_name=p_parts.name, quantity=Decimal("20"),
        ), added_by=0)
        maint_services.complete_work_order(db, wo_completed_2.id)

        wo_cancelled = _create_wo(
            "إصلاح مضخة مياه - HIST (اتلغى)", "corrective", priority="critical",
            asset_id=asset_pump.id, offset=22,
        )
        maint_services.update_work_order(db, wo_cancelled.id, WorkOrderUpdate(status="cancelled"))

        db.commit()

    return {
        "counts": {
            "products": len(product_specs),
            "purchase_orders": 5,
            "purchase_orders_partial": 1,
            "work_orders": 10,
            "work_orders_completed": 2,
            "work_orders_cancelled": 1,
            "work_orders_pending_parts": 1,
            "assets_created": 2,
        },
        "totals": {
            "opening_valuation": "420000.00",
            "purchases_received": "160000.00",
            "consumption": "185000.00",
            "expected_closing_valuation": "395000.00",
        },
    }
