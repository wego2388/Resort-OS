"""app/modules/inventory/api/router.py"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from app.core.deps import (
    DbDep, get_current_active_user, get_employee_user, get_manager_user, require_permission,
)
from app.modules.core import services as core_services
from app.modules.finance.services import FinancialConfigurationError
from app.modules.inventory import crud, services
from app.modules.inventory.schemas import (
    CategoryCreate, CategoryRead, ProductCreate, ProductRead, ProductUpdate,
    PurchaseOrderCreate, PurchaseOrderRead, ReceiveItemsRequest,
    StockMovementCreate, StockMovementRead, SupplierCreate, SupplierRead, SupplierUpdate,
    WarehouseCreate, WarehouseRead,
    PurchaseRequestCreate, PurchaseRequestRead,
    ApproveRequest, ConvertToPurchaseOrderRequest, RejectRequest,
    StockCountCreate, StockCountRead, SubmitStockCountRequest,
)
from app.modules.core.schemas import PaginatedResponse

router = APIRouter(tags=["inventory"])


def _assert_inventory_branch(db, user, branch_id: int, action_desc: str) -> None:
    """Gate 4B-style branch isolation — كانت غايبة بالكامل من موديول
    المخزون (اتكشف 2026-07-28، نفس فئة الباج في CRM/timeshare/beach/الصيانة)."""
    try:
        core_services.assert_branch_access(db, user, branch_id, action_desc)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))


@router.get("/inventory/warehouses", response_model=list[WarehouseRead])
def list_warehouses(db: DbDep, user=Depends(get_current_active_user), branch_id: int = Query(...)):
    _assert_inventory_branch(db, user, branch_id, "عرض المخازن")
    return crud.list_warehouses(db, branch_id)


@router.post("/inventory/warehouses", response_model=WarehouseRead,
             status_code=status.HTTP_201_CREATED)
def create_warehouse(data: WarehouseCreate, db: DbDep, user=Depends(get_manager_user)):
    _assert_inventory_branch(db, user, data.branch_id, "إنشاء مخزن")
    return services.create_warehouse(db, data)


@router.get("/inventory/categories", response_model=list[CategoryRead])
def list_categories(db: DbDep, user=Depends(get_current_active_user), branch_id: int = Query(...)):
    _assert_inventory_branch(db, user, branch_id, "عرض فئات المخزون")
    return crud.list_categories(db, branch_id)


@router.post("/inventory/categories", response_model=CategoryRead,
             status_code=status.HTTP_201_CREATED)
def create_category(data: CategoryCreate, db: DbDep, user=Depends(get_manager_user)):
    _assert_inventory_branch(db, user, data.branch_id, "إنشاء فئة مخزون")
    return services.create_category(db, data)


@router.get("/inventory/products", response_model=PaginatedResponse)
def list_products(
    db: DbDep, user=Depends(get_current_active_user),
    branch_id: int = Query(...),
    category_id: Optional[int] = Query(None),
    low_stock_only: bool = Query(False),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
):
    _assert_inventory_branch(db, user, branch_id, "عرض أصناف المخزون")
    items, total = crud.list_products(db, branch_id, category_id, low_stock_only, search,
                                      skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[ProductRead.model_validate(p) for p in items])


@router.post("/inventory/products", response_model=ProductRead,
             status_code=status.HTTP_201_CREATED)
def create_product(data: ProductCreate, db: DbDep, user=Depends(get_manager_user)):
    _assert_inventory_branch(db, user, data.branch_id, "إنشاء صنف مخزون")
    try:
        return services.create_product(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/inventory/products/barcode-labels", response_model=None)
def download_barcode_labels_pdf(
    db: DbDep, user=Depends(get_manager_user),
    branch_id: int = Query(...),
    product_ids: str = Query(..., description="أرقام الأصناف مفصولة بفاصلة، مثال: 1,2,3"),
):
    _assert_inventory_branch(db, user, branch_id, "تحميل ملصقات الباركود")
    try:
        ids = [int(x) for x in product_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "product_ids لازم تكون أرقام مفصولة بفاصلة")
    try:
        pdf = services.generate_barcode_labels_pdf(db, branch_id, ids)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=barcode-labels.pdf"},
    )


@router.get("/inventory/products/{product_id}", response_model=ProductRead)
def get_product(product_id: int, db: DbDep, user=Depends(get_current_active_user)):
    p = crud.get_product(db, product_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الصنف غير موجود")
    _assert_inventory_branch(db, user, p.branch_id, "عرض صنف مخزون")
    return ProductRead.model_validate(p)


@router.patch("/inventory/products/{product_id}", response_model=ProductRead)
def update_product(product_id: int, data: ProductUpdate, db: DbDep, user=Depends(get_manager_user)):
    p = crud.get_product(db, product_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الصنف غير موجود")
    _assert_inventory_branch(db, user, p.branch_id, "تعديل صنف مخزون")
    try:
        return services.update_product(db, product_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.get("/inventory/movements", response_model=PaginatedResponse)
def list_movements(
    db: DbDep, user=Depends(get_current_active_user),
    branch_id: int = Query(...),
    product_id: Optional[int] = Query(None),
    movement_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
):
    _assert_inventory_branch(db, user, branch_id, "عرض حركات المخزون")
    items, total = crud.list_movements(db, branch_id, product_id, movement_type,
                                       skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[StockMovementRead.model_validate(m) for m in items])


@router.post("/inventory/movements", response_model=StockMovementRead,
             status_code=status.HTTP_201_CREATED)
def record_movement(data: StockMovementCreate, db: DbDep, user=Depends(get_manager_user)):
    _assert_inventory_branch(db, user, data.branch_id, "تسجيل حركة مخزون")
    try:
        return services.record_movement(db, data, moved_by=user.id)
    except services.InventoryConcurrencyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Supplier ─────────────────────────────────────────────────────────

@router.get("/inventory/suppliers", response_model=PaginatedResponse)
def list_suppliers(
    db: DbDep, user=Depends(get_current_active_user),
    branch_id: int = Query(...),
    active_only: bool = Query(True),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
):
    _assert_inventory_branch(db, user, branch_id, "عرض الموردين")
    items, total = crud.list_suppliers(db, branch_id, active_only, search,
                                       skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[SupplierRead.model_validate(s) for s in items])


@router.post("/inventory/suppliers", response_model=SupplierRead,
             status_code=status.HTTP_201_CREATED)
def create_supplier(data: SupplierCreate, db: DbDep, user=Depends(get_manager_user)):
    _assert_inventory_branch(db, user, data.branch_id, "إنشاء مورد")
    return services.create_supplier(db, data)


@router.get("/inventory/suppliers/{supplier_id}", response_model=SupplierRead)
def get_supplier(supplier_id: int, db: DbDep, user=Depends(get_current_active_user)):
    supplier = crud.get_supplier(db, supplier_id)
    if not supplier:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المورد غير موجود")
    _assert_inventory_branch(db, user, supplier.branch_id, "عرض مورد")
    return SupplierRead.model_validate(supplier)


@router.patch("/inventory/suppliers/{supplier_id}", response_model=SupplierRead)
def update_supplier(supplier_id: int, data: SupplierUpdate, db: DbDep, user=Depends(get_manager_user)):
    supplier = crud.get_supplier(db, supplier_id)
    if not supplier:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المورد غير موجود")
    _assert_inventory_branch(db, user, supplier.branch_id, "تعديل مورد")
    try:
        return services.update_supplier(db, supplier_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.get("/inventory/purchase-orders", response_model=PaginatedResponse)
def list_purchase_orders(
    db: DbDep, user=Depends(get_manager_user),
    branch_id: int = Query(...),
    po_status: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
):
    _assert_inventory_branch(db, user, branch_id, "عرض أوامر الشراء")
    items, total = crud.list_purchase_orders(db, branch_id, po_status,
                                             skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[PurchaseOrderRead.model_validate(po) for po in items])


@router.post("/inventory/purchase-orders", response_model=PurchaseOrderRead,
             status_code=status.HTTP_201_CREATED)
def create_purchase_order(data: PurchaseOrderCreate, db: DbDep, user=Depends(get_manager_user)):
    _assert_inventory_branch(db, user, data.branch_id, "إنشاء أمر شراء")
    return services.create_purchase_order(db, data)


@router.get("/inventory/purchase-orders/{po_id}", response_model=PurchaseOrderRead)
def get_purchase_order(po_id: int, db: DbDep, user=Depends(get_manager_user)):
    po = crud.get_purchase_order(db, po_id)
    if not po:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "أمر الشراء غير موجود")
    _assert_inventory_branch(db, user, po.branch_id, "عرض أمر شراء")
    return PurchaseOrderRead.model_validate(po)


@router.post("/inventory/purchase-orders/{po_id}/receive",
             response_model=PurchaseOrderRead)
def receive_purchase_order(po_id: int, req: ReceiveItemsRequest, db: DbDep,
                           user=Depends(get_manager_user)):
    po = crud.get_purchase_order(db, po_id)
    if not po:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "أمر الشراء غير موجود")
    _assert_inventory_branch(db, user, po.branch_id, "استلام أمر شراء")
    try:
        return services.receive_purchase_order(db, po_id, req, received_by=user.id)
    except FinancialConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {
            "code": "FINANCIAL_CONFIGURATION_ERROR", "message": str(exc),
        })
    except services.InventoryConcurrencyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Purchase Request Workflow ─────────────────────────────────────────

@router.post("/inventory/purchase-requests", response_model=PurchaseRequestRead,
             status_code=status.HTTP_201_CREATED)
def create_purchase_request(data: PurchaseRequestCreate, db: DbDep,
                             user=Depends(get_current_active_user)):
    _assert_inventory_branch(db, user, data.branch_id, "إنشاء طلب شراء")
    try:
        return services.create_purchase_request(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/inventory/purchase-requests", response_model=PaginatedResponse)
def list_purchase_requests(
    db: DbDep, user=Depends(get_current_active_user),
    branch_id: int = Query(...),
    pr_status: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
):
    _assert_inventory_branch(db, user, branch_id, "عرض طلبات الشراء")
    items, total = crud.list_purchase_requests(db, branch_id, pr_status,
                                               skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[PurchaseRequestRead.model_validate(pr) for pr in items])


@router.get("/inventory/purchase-requests/{request_id}", response_model=PurchaseRequestRead)
def get_purchase_request(request_id: int, db: DbDep, user=Depends(get_current_active_user)):
    pr = crud.get_purchase_request(db, request_id)
    if not pr:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "طلب الشراء غير موجود")
    _assert_inventory_branch(db, user, pr.branch_id, "عرض طلب شراء")
    return PurchaseRequestRead.model_validate(pr)


@router.patch("/inventory/purchase-requests/{request_id}/approve",
              response_model=PurchaseRequestRead)
def approve_purchase_request(request_id: int, body: ApproveRequest, db: DbDep,
                              user=Depends(get_manager_user)):
    pr = crud.get_purchase_request(db, request_id)
    if not pr:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "طلب الشراء غير موجود")
    _assert_inventory_branch(db, user, pr.branch_id, "اعتماد طلب شراء")
    try:
        return services.approve_purchase_request(db, request_id, user.id, body.level, body.notes)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.patch("/inventory/purchase-requests/{request_id}/reject",
              response_model=PurchaseRequestRead)
def reject_purchase_request(request_id: int, body: RejectRequest, db: DbDep,
                             user=Depends(get_manager_user)):
    pr = crud.get_purchase_request(db, request_id)
    if not pr:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "طلب الشراء غير موجود")
    _assert_inventory_branch(db, user, pr.branch_id, "رفض طلب شراء")
    try:
        return services.reject_purchase_request(db, request_id, user.id, body.level,
                                                body.reason, body.notes)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/inventory/purchase-requests/{request_id}/convert",
             response_model=PurchaseOrderRead)
def convert_purchase_request(request_id: int, body: ConvertToPurchaseOrderRequest, db: DbDep,
                              user=Depends(get_manager_user)):
    pr = crud.get_purchase_request(db, request_id)
    if not pr:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "طلب الشراء غير موجود")
    _assert_inventory_branch(db, user, pr.branch_id, "تحويل طلب شراء لأمر شراء")
    try:
        return services.convert_to_purchase_order(db, request_id, body.supplier_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Stock Count ───────────────────────────────────────────────────────

@router.post("/inventory/stock-counts", response_model=StockCountRead,
             status_code=status.HTTP_201_CREATED)
def create_stock_count(data: StockCountCreate, db: DbDep, user=Depends(get_manager_user)):
    _assert_inventory_branch(db, user, data.branch_id, "بدء جرد مخزون")
    return services.create_stock_count(db, data)


@router.get("/inventory/stock-counts", response_model=PaginatedResponse)
def list_stock_counts(
    db: DbDep, user=Depends(get_employee_user),
    branch_id: int = Query(...),
    sc_status: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
):
    # ⚠️ باج صلاحيات حقيقي كان هنا (اتصلح 2026-07-28): get_current_active_user
    # (أوسع بوابة في المشروع) كانت بتسمح لأي حساب مسجّل يشوف بيانات جرد/فروقات
    # مخزون (تسريب محتمل) — بقت get_employee_user زي عمليات الجرد التانية.
    _assert_inventory_branch(db, user, branch_id, "عرض عمليات الجرد")
    items, total = crud.list_stock_counts(db, branch_id, sc_status,
                                          skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[StockCountRead.model_validate(sc) for sc in items])


def _get_stock_count_or_404(db, count_id: int):
    sc = crud.get_stock_count(db, count_id)
    if not sc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الجرد غير موجود")
    return sc


@router.patch("/inventory/stock-counts/{count_id}/submit",
              response_model=StockCountRead)
def submit_stock_count(count_id: int, req: SubmitStockCountRequest, db: DbDep,
                       user=Depends(get_employee_user)):
    # ⚠️ باج صلاحيات حقيقي كان هنا (اتصلح 2026-07-28): تسجيل كميات جرد
    # فعلية (submit) كان بلا أي حد أدنى للمستوى خالص (get_current_active_user)
    # — عكس create/approve المجاورين. بقت get_employee_user (نفس منطق
    # "لازم تكون موظف حقيقي على الأقل" اللي الصيانة بتستخدمه).
    sc = _get_stock_count_or_404(db, count_id)
    _assert_inventory_branch(db, user, sc.branch_id, "تسجيل كميات جرد")
    try:
        return services.submit_stock_count(db, count_id, req.lines)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.patch("/inventory/stock-counts/{count_id}/approve",
              response_model=StockCountRead,
              dependencies=[Depends(require_permission("inventory.approve_stock_count", "approve", min_role_level=60))])
def approve_stock_count(count_id: int, db: DbDep, user=Depends(get_current_active_user)):
    # اعتماد الجرد وظيفة محاسبية (2026-07-13، Operations & Control Layer —
    # قرار محمد صراحةً: "الموافقة على الجرد المحاسب") — مقصود أضيق من
    # require_permission فوق (اللي بيسمح لأي مدير+ بمستوى 60): هنا حصرًا
    # accountant، أو admin/super_admin كصلاحية إشرافية عليا (نفس نمط
    # الاستثناء الموجود في كل مكان تاني بالمشروع).
    if user.role not in ("accountant", "admin", "super_admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "اعتماد الجرد يقتصر على المحاسب")
    sc = _get_stock_count_or_404(db, count_id)
    _assert_inventory_branch(db, user, sc.branch_id, "اعتماد جرد مخزون")
    try:
        return services.approve_stock_count(db, count_id, approved_by=user.id)
    except services.InventoryConcurrencyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
