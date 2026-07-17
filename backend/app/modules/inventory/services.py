"""app/modules/inventory/services.py"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.resort_os.timezone_utils import local_today

from app.modules.inventory import crud
from app.modules.inventory.models import (
    Product, PurchaseOrder, PurchaseRequest, StockCount, StockCountLine, StockMovement, Supplier, Warehouse,
)
from app.modules.inventory.schemas import (
    CategoryCreate, ProductCreate, ProductUpdate,
    PurchaseOrderCreate, PurchaseOrderItemCreate, ReceiveItemsRequest,
    StockMovementCreate, SupplierCreate, SupplierUpdate, WarehouseCreate,
    PurchaseRequestCreate, StockCountCreate,
)

logger = logging.getLogger(__name__)


class InventoryConcurrencyError(Exception):
    """عملية مخزون تانية ماسكة صف الصنف دلوقتي (SELECT FOR UPDATE NOWAIT فشل) —
    409، مش 400 (زي beach.services.BeachConcurrencyError بالظبط)."""


def create_warehouse(db: Session, data: WarehouseCreate):
    obj = crud.create_warehouse(db, data)
    db.commit(); db.refresh(obj)
    return obj


def create_category(db: Session, data: CategoryCreate):
    obj = crud.create_category(db, data)
    db.commit(); db.refresh(obj)
    return obj


# ── Supplier ─────────────────────────────────────────────────────────

def get_supplier_or_404(db: Session, supplier_id: int) -> Supplier:
    supplier = crud.get_supplier(db, supplier_id)
    if not supplier:
        raise ValueError(f"المورد {supplier_id} غير موجود")
    return supplier


def create_supplier(db: Session, data: SupplierCreate) -> Supplier:
    obj = crud.create_supplier(db, data)
    db.commit(); db.refresh(obj)
    return obj


def update_supplier(db: Session, supplier_id: int, data: SupplierUpdate) -> Supplier:
    supplier = get_supplier_or_404(db, supplier_id)
    obj = crud.update_supplier(db, supplier, data)
    db.commit(); db.refresh(obj)
    return obj


def get_product_or_404(db: Session, product_id: int) -> Product:
    p = crud.get_product(db, product_id)
    if not p:
        raise ValueError(f"الصنف {product_id} غير موجود")
    return p


# ── Barcode Labels ───────────────────────────────────────────────────────
# ملصقات باركود (رفوف/مخزن) — 3 أعمدة × 8 صفوف على ورقة A4 لكل صنف، Code128
# مبني هنا داخل resort-os (مش wego-core) لأنه domain-specific للـ inventory
# labels ومش قدرة عامة (generic capability) تستاهل تتضاف لـ ReportBuilder.

_LABEL_COLS = 3
_LABEL_ROWS = 8


def generate_barcode_labels_pdf(db: Session, branch_id: int, product_ids: list[int]) -> bytes:
    from io import BytesIO  # noqa: PLC0415

    from reportlab.graphics.barcode.code128 import Code128  # noqa: PLC0415
    from reportlab.lib.pagesizes import A4  # noqa: PLC0415
    from reportlab.lib.units import cm  # noqa: PLC0415
    from reportlab.pdfgen import canvas as rl_canvas  # noqa: PLC0415

    products = crud.get_products_by_ids(db, branch_id, product_ids)
    if not products:
        raise ValueError("لا توجد أصناف مطابقة لهذا الفرع")

    buf = BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4

    margin = 1 * cm
    label_w = (page_w - 2 * margin) / _LABEL_COLS
    label_h = (page_h - 2 * margin) / _LABEL_ROWS
    per_page = _LABEL_COLS * _LABEL_ROWS

    for i, product in enumerate(products):
        pos_in_page = i % per_page
        if i > 0 and pos_in_page == 0:
            c.showPage()
        col = pos_in_page % _LABEL_COLS
        row = pos_in_page // _LABEL_COLS

        x0 = margin + col * label_w
        y0 = page_h - margin - (row + 1) * label_h

        c.setFont("Helvetica", 8)
        name = product.name_ar or product.name
        c.drawCentredString(x0 + label_w / 2, y0 + label_h - 14, name[:28])

        barcode = Code128(product.sku, barHeight=label_h * 0.45, barWidth=0.9)
        barcode.drawOn(c, x0 + (label_w - barcode.width) / 2, y0 + label_h * 0.3)

        c.setFont("Helvetica", 7)
        c.drawCentredString(x0 + label_w / 2, y0 + 6, product.sku)

    c.save()
    return buf.getvalue()


def create_product(db: Session, data: ProductCreate) -> Product:
    if crud.get_product_by_sku(db, data.branch_id, data.sku):
        raise ValueError(f"الـ SKU '{data.sku}' مستخدم مسبقاً")
    obj = crud.create_product(db, data)
    db.commit(); db.refresh(obj)
    return obj


def update_product(db: Session, product_id: int, data: ProductUpdate) -> Product:
    product = get_product_or_404(db, product_id)
    obj = crud.update_product(db, product, data)
    db.commit(); db.refresh(obj)
    return obj


def record_movement(
    db: Session,
    data: StockMovementCreate,
    moved_by: int,
    allow_negative: bool = False,
):
    """يُسجّل حركة مخزون ويُحدّث الرصيد.

    allow_negative=False (الافتراضي، وسلوك كل نداءات هذه الدالة القديمة قبل
    وصفات المطعم/الكافيه): لو الخصم هيرجّع الرصيد سالب، بيرفض الحركة بالكامل
    (ValueError → 400) — مناسب للحركات اليدوية (جرد، تحويل، شراء) اللي لازم
    تعكس رصيد حقيقي دايمًا.

    allow_negative=True (يُستخدم من استهلاك وصفات المطعم/الكافيه بس —
    consume_stock عبر _deduct_inventory_for_order): بيسمح بالرصيد يبقى
    سالب مع تسجيل تحذير، بدل ما يرفض الخصم بصمت أو يمنع إتمام البيع. غرفة
    طعام حقيقية، مش مخزن — إيقاف بيع صنف بسبب فرق جرد بسيط في مكوّن واحد
    أسوأ تشغيليًا من رصيد سالب مؤقت لحد ما يتصحّح بالجرد التالي."""
    product = get_product_or_404(db, data.product_id)
    would_go_negative = data.quantity < 0 and abs(data.quantity) > product.current_stock
    if would_go_negative and not allow_negative:
        raise ValueError(
            f"الكمية المطلوبة ({abs(data.quantity)}) أكبر من الرصيد الحالي ({product.current_stock})"
        )
    if would_go_negative and allow_negative:
        logger.warning(
            "مخزون سالب: الصنف #%s (%s) — الرصيد %s هيبقى %s بعد خصم %s (reference=%s/%s)",
            product.id, product.name, product.current_stock,
            product.current_stock + data.quantity, abs(data.quantity),
            data.reference_type, data.reference_id,
        )
    mov = crud.create_movement(db, data, moved_by)
    try:
        crud.adjust_stock(db, product, data.quantity, allow_negative=allow_negative)
    except OperationalError as exc:
        db.rollback()
        raise InventoryConcurrencyError(
            f"الصنف {product.id} مشغول الآن بعملية مخزون أخرى — حاول تاني خلال لحظات"
        ) from exc
    db.commit(); db.refresh(mov)
    return mov


def consume_stock(
    db: Session,
    branch_id: int,
    product_id: int,
    warehouse_id: int,
    quantity: Decimal,
    reference_type: Optional[str] = None,
    reference_id: Optional[int] = None,
    moved_by: int = 0,
    allow_negative: bool = False,
    cost_center_code: Optional[str] = None,
):
    """اختصار لخصم من المخزون — يُستدعى من Dining (ربط 1:1 قديم أو استهلاك
    وصفة). راجع توثيق allow_negative في record_movement.

    cost_center_code (Batch 3): مركز التكلفة (REST/CAFE...) اللي الاستهلاك
    ده بيخصه — بيتوسم على قيد الـ COGS (راجع _post_cogs_journal)، عشان
    تقرير مركز التكلفة يقدر يحسب المصروف مش الإيراد بس."""
    product = get_product_or_404(db, product_id)
    avg_cost = product.cost_price or Decimal("0")

    data = StockMovementCreate(
        branch_id=branch_id,
        product_id=product_id,
        warehouse_id=warehouse_id,
        movement_type="consumption",
        quantity=-abs(quantity),
        unit_cost=avg_cost,
        reference_type=reference_type,
        reference_id=reference_id,
        moved_at=datetime.utcnow(),
    )
    mov = record_movement(db, data, moved_by, allow_negative=allow_negative)

    # COGS Journal Entry
    cogs_amount = avg_cost * abs(quantity)
    if cogs_amount > 0:
        _post_cogs_journal(db, branch_id, cogs_amount, reference_type, reference_id, moved_by, cost_center_code)

    return mov


def _post_cogs_journal(
    db: Session,
    branch_id: int,
    amount: Decimal,
    ref_type: Optional[str],
    ref_id: Optional[int],
    user_id: int,
    cost_center_code: Optional[str] = None,
) -> None:
    """يُنشئ قيد COGS إذا كانت الحسابات مُعرَّفة."""
    try:
        from app.modules.finance.crud import get_account_by_code, create_journal_entry, get_cost_center_by_code  # noqa: PLC0415
        from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate  # noqa: PLC0415
        from app.modules.finance.services import ensure_default_cost_centers  # noqa: PLC0415

        cogs_acc  = get_account_by_code(db, branch_id, "5200")
        inv_acc   = get_account_by_code(db, branch_id, "1200")
        if not cogs_acc or not inv_acc:
            return

        cost_center_id = None
        if cost_center_code:
            cc = get_cost_center_by_code(db, branch_id, cost_center_code)
            if not cc:
                ensure_default_cost_centers(db, branch_id)
                cc = get_cost_center_by_code(db, branch_id, cost_center_code)
            cost_center_id = cc.id if cc else None

        entry_data = JournalEntryCreate(
            branch_id=branch_id,
            # #tz-fix: local_today بدل _date.today() — تاريخ قيد COGS لازم
            # يكون بتوقيت المنتجع مش UTC، عشان يتطابق مع تاريخ الطلب نفسه
            # في التقارير المحاسبية اليومية.
            entry_date=local_today(settings.TIMEZONE),
            reference=f"COGS-{ref_type or 'manual'}-{ref_id or 0}",
            description=f"تكلفة بضاعة مستهلكة — {ref_type or ''}",
            source="inventory",
            source_id=ref_id,
            lines=[
                JournalLineCreate(account_id=cogs_acc.id, debit=amount, credit=Decimal("0"),
                                   cost_center_id=cost_center_id),
                JournalLineCreate(account_id=inv_acc.id, debit=Decimal("0"), credit=amount,
                                   cost_center_id=cost_center_id),
            ],
        )
        create_journal_entry(db, entry_data, user_id)
    except Exception:
        pass  # لا نوقف استهلاك المخزون إذا فشل القيد


def get_po_or_404(db: Session, po_id: int) -> PurchaseOrder:
    po = crud.get_purchase_order(db, po_id)
    if not po:
        raise ValueError(f"أمر الشراء {po_id} غير موجود")
    return po


def create_purchase_order(db: Session, data: PurchaseOrderCreate) -> PurchaseOrder:
    po = crud.create_purchase_order(db, data)
    db.commit(); db.refresh(po)
    return po


def receive_purchase_order(
    db: Session,
    po_id: int,
    req: ReceiveItemsRequest,
    received_by: int,
) -> PurchaseOrder:
    po = get_po_or_404(db, po_id)
    if po.status in ("received", "cancelled"):
        raise ValueError(f"أمر الشراء في حالة '{po.status}' ولا يمكن استلامه")
    try:
        po, received_value = crud.receive_purchase_order(
            db, po, req.items, req.warehouse_id, req.received_at, received_by,
        )
    except OperationalError as exc:
        db.rollback()
        raise InventoryConcurrencyError(
            "أحد الأصناف في أمر الشراء ده مشغول الآن بعملية مخزون أخرى — حاول تاني خلال لحظات"
        ) from exc
    _post_purchase_receipt_journal(db, po, received_value, received_by)
    db.commit(); db.refresh(po)
    return po


def _post_purchase_receipt_journal(
    db: Session, po: PurchaseOrder, received_value: Decimal, user_id: int,
) -> None:
    """Dr. مخزون البضاعة (1200) / Cr. موردون - ذمم دائنة (2200).

    ⚠️ باج محاسبي حقيقي كان هنا (اتصلح): استلام أمر شراء كان بيحدّث
    current_stock/cost_price ويسجّل StockMovement حقيقي (المتطلب الصريح من
    Mohamed 2026-07-14 — كان شغال بالفعل)، بس عمره ما كان بيرحّل أي قيد
    يومية خالص — لا Dr على حساب المخزون (1200)، لا Cr على أي حساب موردين
    (ماكانش موجود أصلاً في دليل الحسابات). النتيجة: حساب 1200 كان بيتقيّد
    عليه Cr بس (استهلاك COGS، راجع _post_cogs_journal) من غير أي Dr مقابل
    من المشتريات — رصيده كان هيتجه سالب دايمًا مع الوقت، ومفيش أي أثر
    لالتزام المنتجع تجاه مورّديه في الميزانية العمومية أو دفتر اليومية،
    مخالفة مباشرة لـ CLAUDE.md §5.2 (Finance First — حركة المخزون لازم
    تفضل قابلة للتتبّع محاسبيًا). المبلغ = قيمة **دفعة الاستلام دي بس**
    (مش إجمالي أمر الشراء) عشان الاستلام الجزئي يترحّل صح على مراحل."""
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    post_simple_revenue_journal(
        db, po.branch_id, po.received_at or local_today(settings.TIMEZONE),
        debit_account_code="1200", credit_account_code="2200",
        amount=received_value,
        reference=f"PO-{po.order_number}",
        description=f"استلام بضاعة — أمر شراء {po.order_number}"
                    + (f" ({po.supplier.name})" if po.supplier else ""),
        source="inventory_purchase", source_id=po.id,
        created_by=user_id,
    )


def get_low_stock_products(db: Session, branch_id: int) -> list[Product]:
    """يُستخدم من Celery لإشعارات المخزون المنخفض."""
    items, _ = crud.list_products(db, branch_id, low_stock_only=True, limit=500)
    return items


# ── Purchase Request Workflow ─────────────────────────────────────────

def create_purchase_request(db: Session, data: PurchaseRequestCreate) -> PurchaseRequest:
    """Creates a PR in draft state with its items."""
    total_estimated = Decimal("0")
    pr = crud.create_purchase_request_record(
        db,
        branch_id=data.branch_id,
        requester_id=data.requester_id,
        department=data.department,
        notes=data.notes,
        total_estimated=Decimal("0"),
    )
    for item_d in data.items:
        qty = item_d.quantity_requested
        cost = item_d.estimated_unit_cost
        total_estimated += qty * cost
        crud.create_pr_item(
            db,
            request_id=pr.id,
            product_id=item_d.product_id,
            quantity_requested=qty,
            unit=item_d.unit,
            estimated_unit_cost=cost,
        )
    pr.total_estimated = total_estimated
    db.flush()
    db.commit()
    db.refresh(pr)
    return pr


def approve_purchase_request(
    db: Session,
    request_id: int,
    approver_id: int,
    level: str,
    notes: Optional[str] = None,
) -> PurchaseRequest:
    """
    level='dept'    → status: draft → dept_approved
    level='finance' → status: dept_approved → finance_approved
    Creates a PurchaseApproval record.
    """
    request = crud.get_purchase_request(db, request_id)
    if not request:
        raise ValueError(f"طلب الشراء {request_id} غير موجود")
    if level == "dept" and request.status != "draft":
        raise ValueError("طلب الشراء يجب أن يكون في حالة draft للموافقة من القسم")
    if level == "finance" and request.status != "dept_approved":
        raise ValueError("طلب الشراء يجب أن يكون في حالة dept_approved للموافقة المالية")
    new_status = "dept_approved" if level == "dept" else "finance_approved"
    crud.update_pr_status(db, request, new_status)
    crud.create_approval(db, request.id, approver_id, level, "approved", notes)
    db.commit()
    db.refresh(request)
    return request


def reject_purchase_request(
    db: Session,
    request_id: int,
    approver_id: int,
    level: str,
    reason: str,
    notes: Optional[str] = None,
) -> PurchaseRequest:
    """Rejects a PR and creates a PurchaseApproval record with status=rejected."""
    request = crud.get_purchase_request(db, request_id)
    if not request:
        raise ValueError(f"طلب الشراء {request_id} غير موجود")
    if request.status in ("converted", "rejected"):
        raise ValueError(f"طلب الشراء في حالة '{request.status}' ولا يمكن رفضه")
    crud.update_pr_status(db, request, "rejected", rejected_reason=reason)
    crud.create_approval(db, request.id, approver_id, level, "rejected", notes)
    db.commit()
    db.refresh(request)
    return request


def convert_to_purchase_order(db: Session, request_id: int, supplier_id: int) -> PurchaseOrder:
    """
    Converts a finance_approved PR into a PurchaseOrder.
    PR status: finance_approved → converted

    ⚠️ باج حقيقي كان هنا (اتصلح): كان بيحط supplier_name="TBD (من طلب شراء #N)"
    ثابت — يعني مورد حقيقي عمره ما كان بيتحدد فعليًا عند التحويل، وده placeholder
    كان بيعدّي الـ validation بصمت (str عادي، مفيش قيد يمنعه). القرار: المورد
    بقى إجباري (supplier_id) وقت التحويل نفسه — أنسب لحظة لفرض "هنشتري من مين"
    فعليًا، بدل ما نسمح بأمر شراء بلا مورد حقيقي يتحرك للمرحلة الجاية (إرسال/
    استلام) من غيره. راجع ConvertToPurchaseOrderRequest في schemas.py."""
    from datetime import date as date_type  # avoid shadowing

    request = crud.get_purchase_request(db, request_id)
    if not request:
        raise ValueError(f"طلب الشراء {request_id} غير موجود")
    if request.status != "finance_approved":
        raise ValueError("طلب الشراء يجب أن يكون في حالة finance_approved للتحويل")

    supplier = get_supplier_or_404(db, supplier_id)
    if supplier.branch_id != request.branch_id:
        raise ValueError("المورد المحدد لا يتبع نفس فرع طلب الشراء")

    po_items = [
        PurchaseOrderItemCreate(
            product_id=item.product_id,
            ordered_qty=item.quantity_requested,
            unit_cost=item.estimated_unit_cost,
        )
        for item in request.items
    ]
    po_data = PurchaseOrderCreate(
        branch_id=request.branch_id,
        supplier_id=supplier.id,
        ordered_at=date_type.today(),
        items=po_items,
    )
    po = crud.create_purchase_order(db, po_data)
    crud.update_pr_status(db, request, "converted")
    db.commit()
    db.refresh(po)
    return po


# ── Stock Count ───────────────────────────────────────────────────────

def create_stock_count(
    db: Session,
    data: StockCountCreate,
) -> StockCount:
    """
    Creates a StockCount with lines for specified products (or all active products).
    system_quantity = product.current_stock at count time.
    """
    sc = StockCount(
        branch_id=data.branch_id,
        warehouse_id=data.warehouse_id,
        count_date=data.count_date,
        status="draft",
        counted_by=data.counted_by,
        notes=data.notes,
    )
    db.add(sc)
    db.flush()

    if data.product_ids:
        products = (
            db.query(Product)
            .filter(Product.id.in_(data.product_ids), Product.branch_id == data.branch_id)
            .all()
        )
    else:
        products = (
            db.query(Product)
            .filter(Product.branch_id == data.branch_id, Product.is_active.is_(True))
            .all()
        )

    for p in products:
        line = StockCountLine(
            count_id=sc.id,
            product_id=p.id,
            system_quantity=p.current_stock,
            counted_quantity=Decimal("0"),
            variance=Decimal("0"),
        )
        db.add(line)

    db.flush()
    db.commit()
    db.refresh(sc)
    return sc


def submit_stock_count(db: Session, count_id: int, lines_data: list[dict]) -> StockCount:
    """
    Updates counted_quantity per line and calculates variance.
    lines_data: [{"line_id": int, "counted_quantity": Decimal}]
    status: draft → submitted
    """
    sc = crud.get_stock_count(db, count_id)
    if not sc:
        raise ValueError(f"جرد المخزون {count_id} غير موجود")
    if sc.status != "draft":
        raise ValueError(f"جرد المخزون في حالة '{sc.status}' ولا يمكن إرساله")

    line_map = {line.id: line for line in sc.lines}
    for ld in lines_data:
        line = line_map.get(int(ld["line_id"]))
        if not line:
            continue
        counted = Decimal(str(ld["counted_quantity"]))
        line.counted_quantity = counted
        line.variance = counted - line.system_quantity

    sc.status = "submitted"
    db.flush()
    db.commit()
    db.refresh(sc)
    return sc


def approve_stock_count(db: Session, count_id: int, approved_by: int) -> StockCount:
    """
    Approves the count and posts adjustment movements.
    For each line with variance != 0:
      - Creates StockMovement(type='adjustment')
      - Updates product.current_stock
    status: submitted → approved → adjustment_posted
    """
    sc = crud.get_stock_count(db, count_id)
    if not sc:
        raise ValueError(f"جرد المخزون {count_id} غير موجود")
    if sc.status != "submitted":
        raise ValueError(f"جرد المخزون في حالة '{sc.status}' ولا يمكن اعتماده")

    sc.approved_by = approved_by
    sc.status = "approved"
    db.flush()

    warehouse_id = sc.warehouse_id

    # ترتيب الأصناف بـ product_id تصاعدي قبل القفل/التعديل — نفس نمط
    # crud.receive_purchase_order (اتساق ترتيب الأقفال عبر عمليات متزامنة،
    # مش ضروري لمنع deadlock حقيقي مع NOWAIT بس ممارسة سليمة).
    lines_sorted = sorted(sc.lines, key=lambda ln: ln.product_id)

    for line in lines_sorted:
        if line.variance == Decimal("0"):
            continue

        try:
            product = crud.lock_product_for_update(db, line.product_id)
        except OperationalError as exc:
            db.rollback()
            raise InventoryConcurrencyError(
                f"الصنف {line.product_id} مشغول الآن بعملية مخزون أخرى — حاول تاني خلال لحظات"
            ) from exc
        if not product:
            continue

        # Resolve warehouse
        wh_id = warehouse_id or product.warehouse_id
        if wh_id is None:
            wh = db.query(Warehouse).filter(Warehouse.branch_id == sc.branch_id).first()
            if wh:
                wh_id = wh.id
            else:
                # No warehouse available — update stock without movement
                product.current_stock = max(Decimal("0"), product.current_stock + line.variance)
                continue

        # Create adjustment movement
        mov = StockMovement(
            branch_id=sc.branch_id,
            product_id=line.product_id,
            warehouse_id=wh_id,
            movement_type="adjustment",
            quantity=line.variance,
            unit_cost=product.cost_price,
            reference_type="inventory_count",
            reference_id=sc.id,
            moved_by=approved_by,
            moved_at=datetime.utcnow(),
        )
        db.add(mov)

        # Update product stock
        product.current_stock = max(Decimal("0"), product.current_stock + line.variance)

    sc.status = "adjustment_posted"
    db.flush()
    db.commit()
    db.refresh(sc)
    return sc
