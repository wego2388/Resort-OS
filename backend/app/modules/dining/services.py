"""app/modules/dining/services.py — Business logic (يرمي ValueError، لا HTTPException).

يدمج restaurant/services.py + cafe/services.py في محرك طلبات واحد — راجع
docstrings models.py لتبرير القرارات المعمارية (Variants، station، إلخ).

تصحيح مهم عن الموديولين الأصليين (wagdy.md D-03): حسابات الإيراد الثابتة
4200 (مطعم) / 4400 (كافيه) بقت ``outlet.revenue_account_code`` — خاصية على
سجل الـ outlet نفسه، مش literal في الكود. أي outlet جديد (بار مسبح، بوفيه)
بياخد حساب إيراد مستقل من غير أي تعديل هنا.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.dining import crud
from app.modules.dining.models import (
    DiningItem, DiningItemVariant, DiningItemVariantRecipeLine,
    DiningItemRecipeLine, DiningKitchenTicket, DiningOrder, Outlet,
)
from app.modules.dining.schemas import (
    CogsTrendPoint, DiningItemRecipeLineCreate, DiningItemRecipeLineUpdate,
    DiningItemVariantCreate, DiningItemVariantRecipeLineCreate,
    DiningItemVariantRecipeLineUpdate, DiningItemVariantUpdate,
    FoodCostReportLine, FoodCostReportResponse, GrossMarginSummary, OrderCreate,
)
from app.resort_os.discount_engine import DiscountRule, OrderContext, OrderLineItem, calculate_discount
from app.resort_os.food_cost_engine import DEFAULT_FOOD_COST_THRESHOLD_PCT, compute_food_cost_result, exceeds_threshold
from app.resort_os.timezone_utils import (
    local_date_to_utc_range, local_now, local_today,
    utc_naive_to_local_date, utc_naive_to_local_time,
)

logger = logging.getLogger(__name__)


def _get_order_or_404(db: Session, order_id: int) -> DiningOrder:
    order = crud.get_order(db, order_id)
    if not order:
        raise ValueError(f"الطلب {order_id} غير موجود")
    return order


def _get_outlet_or_404(db: Session, outlet_id: int) -> Outlet:
    outlet = crud.get_outlet(db, outlet_id)
    if not outlet:
        raise ValueError(f"المنفذ {outlet_id} غير موجود")
    return outlet


def _service_charge_pct(outlet: Optional[Outlet]) -> Decimal:
    """نسبة رسم الخدمة الفعلية للمنفذ — override بتاع الـ outlet لو موجود،
    وإلا settings.SERVICE_CHARGE_PERCENTAGE العام (نفس سلوك restaurant/cafe
    الحالي بالظبط، الاتنين كانوا بيستخدموا نفس القيمة العامة)."""
    if outlet is not None and outlet.default_service_charge_pct is not None:
        return outlet.default_service_charge_pct / Decimal("100")
    return Decimal(str(settings.SERVICE_CHARGE_PERCENTAGE)) / Decimal("100")


def _resolve_extras(
    db: Session, item: DiningItem, extra_ids: list[int],
    extra_texts: Optional[dict[int, str]] = None,
) -> tuple[list[dict], Decimal]:
    """راجع restaurant.services._resolve_extras — نفس منطق قوائم الاختيار
    (pick_list) بالظبط، زائد مجموعات النص الحر (group_type="text") — راجع
    docstring models.DiningItemExtraGroup. ``extra_texts`` = group_id ->
    إجابة نصية (مثال حقيقي: "كام سمكة؟" -> "3 سمكات")."""
    extra_texts = extra_texts or {}
    if not item.extra_groups and not extra_ids and not extra_texts:
        return [], Decimal("0")

    valid_extra_ids = {
        extra.id for group in item.extra_groups if group.group_type == "pick_list"
        for extra in group.options
    }
    for extra_id in extra_ids:
        if extra_id not in valid_extra_ids:
            raise ValueError(f"الإضافة {extra_id} لا تنتمي لصنف '{item.name}'")

    selected = set(extra_ids)
    extras_data: list[dict] = []
    price_addition = Decimal("0")

    for group in item.extra_groups:
        if group.group_type == "text":
            text_value = (extra_texts.get(group.id) or "").strip()
            if not text_value:
                if group.min_select >= 1:
                    raise ValueError(f"لازم تدخل قيمة لـ '{group.name}'")
                continue
            extras_data.append({
                "extra_id":       None,
                "extra_name":     group.name,
                "price_addition": Decimal("0"),
                "text_value":     text_value,
            })
            continue

        group_selected = [opt for opt in group.options if opt.id in selected]
        if len(group_selected) < group.min_select:
            raise ValueError(f"لازم تختار {group.min_select} على الأقل من '{group.name}'")
        if len(group_selected) > group.max_select:
            raise ValueError(f"أقصى اختيار من '{group.name}' هو {group.max_select}")
        for opt in group_selected:
            if not opt.is_available:
                raise ValueError(f"الإضافة '{opt.name}' غير متاحة حالياً")
            extras_data.append({
                "extra_id":       opt.id,
                "extra_name":     opt.name,
                "price_addition": opt.price_addition,
            })
            price_addition += opt.price_addition

    return extras_data, price_addition


def _resolve_variant(db: Session, item: DiningItem, variant_id: Optional[int]) -> Optional[DiningItemVariant]:
    """راجع restaurant.services._resolve_variant — نفس المنطق بالظبط."""
    available_variants = [v for v in item.variants if v.is_available]
    if not available_variants:
        if variant_id is not None:
            raise ValueError(f"الصنف '{item.name}' مفهوش متغيّرات — لا يمكن تحديد variant_id")
        return None
    if variant_id is None:
        raise ValueError(f"لازم تختار حجم/نوع لـ '{item.name}'")
    variant = next((v for v in available_variants if v.id == variant_id), None)
    if not variant:
        raise ValueError(f"المتغيّر {variant_id} غير موجود أو غير متاح لهذا الصنف")
    return variant


def _effective_recipe(item: DiningItem, variant: Optional[DiningItemVariant]) -> list:
    """راجع restaurant.services._effective_recipe — نفس المنطق بالظبط."""
    if variant is not None and variant.recipe_lines:
        return variant.recipe_lines
    return item.recipe_lines


# ─────────────────────── Recipe / BOM ──────────────────────────────────

def compute_item_cost(item: DiningItem) -> Decimal:
    """راجع restaurant.services.compute_menu_item_cost — نفس المنطق بالظبط."""
    if item.recipe_lines:
        total = Decimal("0")
        for line in item.recipe_lines:
            unit_cost = (line.product.cost_price if line.product else None) or Decimal("0")
            total += line.quantity_per_unit * unit_cost
        return total.quantize(Decimal("0.01"))
    return item.cost if item.cost is not None else Decimal("0")


def build_recipe_line_read(line: DiningItemRecipeLine) -> dict:
    unit_cost = (line.product.cost_price if line.product else None) or Decimal("0")
    return {
        "id": line.id,
        "item_id": line.item_id,
        "product_id": line.product_id,
        "product_name": line.product.name if line.product else "",
        "product_unit": line.product.unit if line.product else "",
        "quantity_per_unit": line.quantity_per_unit,
        "unit_cost": unit_cost,
        "line_cost": (line.quantity_per_unit * unit_cost).quantize(Decimal("0.01")),
        "notes": line.notes,
    }


def add_recipe_line(db: Session, item_id: int, data: DiningItemRecipeLineCreate) -> DiningItemRecipeLine:
    from app.modules.inventory import crud as inventory_crud  # noqa: PLC0415

    item = crud.get_item(db, item_id)
    if not item:
        raise ValueError(f"الصنف {item_id} غير موجود")
    product = inventory_crud.get_product(db, data.product_id)
    if not product:
        raise ValueError(f"المنتج {data.product_id} غير موجود في المخزون")
    if product.branch_id != item.branch_id:
        raise ValueError("المنتج المخزني لازم يكون من نفس فرع الصنف")
    if any(line.product_id == data.product_id for line in item.recipe_lines):
        raise ValueError(f"المنتج '{product.name}' مضاف بالفعل لوصفة هذا الصنف")

    line = crud.create_recipe_line(db, item_id, data)
    db.commit()
    db.refresh(line)
    return line


def update_recipe_line(db: Session, line_id: int, data: DiningItemRecipeLineUpdate) -> DiningItemRecipeLine:
    line = crud.get_recipe_line(db, line_id)
    if not line:
        raise ValueError(f"سطر الوصفة {line_id} غير موجود")
    line = crud.update_recipe_line(db, line, data)
    db.commit()
    db.refresh(line)
    return line


def remove_recipe_line(db: Session, line_id: int) -> None:
    if not crud.delete_recipe_line(db, line_id):
        raise ValueError(f"سطر الوصفة {line_id} غير موجود")
    db.commit()


# ─────────────────────── Variants ──────────────────────────────────────

def compute_variant_cost(variant: DiningItemVariant) -> Decimal:
    total = Decimal("0")
    for line in variant.recipe_lines:
        unit_cost = (line.product.cost_price if line.product else None) or Decimal("0")
        total += line.quantity_per_unit * unit_cost
    return total.quantize(Decimal("0.01"))


def build_variant_recipe_line_read(line: DiningItemVariantRecipeLine) -> dict:
    unit_cost = (line.product.cost_price if line.product else None) or Decimal("0")
    return {
        "id": line.id,
        "variant_id": line.variant_id,
        "product_id": line.product_id,
        "product_name": line.product.name if line.product else "",
        "product_unit": line.product.unit if line.product else "",
        "quantity_per_unit": line.quantity_per_unit,
        "unit_cost": unit_cost,
        "line_cost": (line.quantity_per_unit * unit_cost).quantize(Decimal("0.01")),
        "notes": line.notes,
    }


def build_variant_read(variant: DiningItemVariant) -> dict:
    return {
        "id": variant.id,
        "item_id": variant.item_id,
        "name": variant.name,
        "name_ar": variant.name_ar,
        "price": variant.price,
        "is_available": variant.is_available,
        "sort_order": variant.sort_order,
        "recipe_lines": [build_variant_recipe_line_read(line) for line in variant.recipe_lines],
        "computed_cost": compute_variant_cost(variant),
    }


def add_variant(db: Session, item_id: int, data: DiningItemVariantCreate) -> DiningItemVariant:
    item = crud.get_item(db, item_id)
    if not item:
        raise ValueError(f"الصنف {item_id} غير موجود")
    if any(v.name == data.name for v in item.variants):
        raise ValueError(f"يوجد بالفعل متغيّر بالاسم '{data.name}' لهذا الصنف")

    variant = crud.create_variant(db, item_id, data)
    db.commit()
    db.refresh(variant)
    return variant


def update_variant(db: Session, variant_id: int, data: DiningItemVariantUpdate) -> DiningItemVariant:
    variant = crud.get_variant(db, variant_id)
    if not variant:
        raise ValueError(f"المتغيّر {variant_id} غير موجود")
    variant = crud.update_variant(db, variant, data)
    db.commit()
    db.refresh(variant)
    return variant


def remove_variant(db: Session, variant_id: int) -> None:
    if not crud.delete_variant(db, variant_id):
        raise ValueError(f"المتغيّر {variant_id} غير موجود")
    db.commit()


def add_variant_recipe_line(db: Session, variant_id: int, data: DiningItemVariantRecipeLineCreate) -> DiningItemVariantRecipeLine:
    from app.modules.inventory import crud as inventory_crud  # noqa: PLC0415

    variant = crud.get_variant(db, variant_id)
    if not variant:
        raise ValueError(f"المتغيّر {variant_id} غير موجود")
    product = inventory_crud.get_product(db, data.product_id)
    if not product:
        raise ValueError(f"المنتج {data.product_id} غير موجود في المخزون")
    item = crud.get_item(db, variant.item_id)
    if item and product.branch_id != item.branch_id:
        raise ValueError("المنتج المخزني لازم يكون من نفس فرع الصنف")
    if any(line.product_id == data.product_id for line in variant.recipe_lines):
        raise ValueError(f"المنتج '{product.name}' مضاف بالفعل لوصفة هذا المتغيّر")

    line = crud.create_variant_recipe_line(db, variant_id, data)
    db.commit()
    db.refresh(line)
    return line


def update_variant_recipe_line(db: Session, line_id: int, data: DiningItemVariantRecipeLineUpdate) -> DiningItemVariantRecipeLine:
    line = crud.get_variant_recipe_line(db, line_id)
    if not line:
        raise ValueError(f"سطر الوصفة {line_id} غير موجود")
    line = crud.update_variant_recipe_line(db, line, data)
    db.commit()
    db.refresh(line)
    return line


def remove_variant_recipe_line(db: Session, line_id: int) -> None:
    if not crud.delete_variant_recipe_line(db, line_id):
        raise ValueError(f"سطر الوصفة {line_id} غير موجود")
    db.commit()


# ─────────────────────── Orders ────────────────────────────────────────

def create_order(
    db: Session,
    branch_id: int,
    data: OrderCreate,
    waiter_id: Optional[int] = None,
    hold: bool = False,
) -> DiningOrder:
    outlet = _get_outlet_or_404(db, data.outlet_id)

    if data.table_id:
        table = crud.get_table(db, data.table_id)
        if not table:
            raise ValueError(f"الطاولة {data.table_id} غير موجودة")
        if table.status == "out_of_service":
            raise ValueError(f"الطاولة {table.table_number} خارج الخدمة")

    items_data = []
    subtotal = Decimal("0")

    for item_req in data.items:
        item = crud.get_item(db, item_req.item_id)
        if not item:
            raise ValueError(f"الصنف {item_req.item_id} غير موجود")
        if not item.is_available:
            raise ValueError(f"الصنف '{item.name}' غير متاح حالياً")

        variant = _resolve_variant(db, item, item_req.variant_id)
        base_price = variant.price if variant else item.price
        item_name = f"{item.name} - {variant.name}" if variant else item.name

        extras_data, extra_price_per_unit = _resolve_extras(db, item, item_req.extra_ids, item_req.extra_texts)

        line_total = (base_price + extra_price_per_unit) * item_req.quantity
        subtotal += line_total
        items_data.append({
            "item_id":    item_req.item_id,
            "variant_id": variant.id if variant else None,
            "name":       item_name,
            "unit_price": base_price,
            "quantity":   item_req.quantity,
            "notes":      item_req.notes,
            "extras":     extras_data,
        })

    vat_pct    = Decimal(str(settings.VAT_PERCENTAGE)) / Decimal("100")
    svc_pct    = _service_charge_pct(outlet)
    vat_amount = (subtotal * vat_pct).quantize(Decimal("0.01"))
    svc_charge = (subtotal * svc_pct).quantize(Decimal("0.01"))
    total      = subtotal + vat_amount + svc_charge

    order_number = crud.generate_order_number(db, branch_id)

    order = crud.create_order_with_items(
        db=db,
        branch_id=branch_id,
        outlet_id=outlet.id,
        order_number=order_number,
        order_type=data.order_type,
        table_id=data.table_id,
        guests_count=data.guests_count,
        notes=data.notes,
        subtotal=subtotal,
        vat_amount=vat_amount,
        service_charge=svc_charge,
        total=total,
        waiter_id=waiter_id,
        items_data=items_data,
        status="held" if hold else "open",
        customer_id=data.customer_id,
    )

    if data.table_id and data.order_type == "dine_in":
        table = crud.get_table(db, data.table_id)
        if table:
            crud.update_table_status(db, table, "occupied")

    db.commit()
    db.refresh(order)
    return order


def add_items_to_order(db: Session, order_id: int, items: list) -> DiningOrder:
    """راجع restaurant.services.add_items_to_order — نفس المنطق بالظبط."""
    from app.modules.dining.models import DiningOrderItem, DiningOrderItemExtra  # noqa: PLC0415

    order = _get_order_or_404(db, order_id)
    if order.status in ("paid", "cancelled"):
        raise ValueError(f"لا يمكن إضافة أصناف لطلب بحالة {order.status}")

    outlet = crud.get_outlet(db, order.outlet_id)
    added_subtotal = Decimal("0")
    for item_req in items:
        item = crud.get_item(db, item_req.item_id)
        if not item:
            raise ValueError(f"الصنف {item_req.item_id} غير موجود")
        if not item.is_available:
            raise ValueError(f"الصنف '{item.name}' غير متاح حالياً")

        variant = _resolve_variant(db, item, item_req.variant_id)
        base_price = variant.price if variant else item.price
        item_name  = f"{item.name} - {variant.name}" if variant else item.name
        extras_data, extra_price = _resolve_extras(db, item, item_req.extra_ids, item_req.extra_texts)

        new_item = DiningOrderItem(
            order_id  = order.id,
            item_id   = item_req.item_id,
            variant_id= variant.id if variant else None,
            name      = item_name,
            unit_price= base_price,
            quantity  = item_req.quantity,
            notes     = item_req.notes,
            status    = "pending",
        )
        db.add(new_item)
        db.flush()

        for e in extras_data:
            db.add(DiningOrderItemExtra(
                order_item_id  = new_item.id,
                extra_id       = e["extra_id"],
                extra_name     = e["extra_name"],
                price_addition = e["price_addition"],
                text_value     = e.get("text_value"),
            ))

        added_subtotal += (base_price + extra_price) * item_req.quantity

    vat_pct   = Decimal(str(settings.VAT_PERCENTAGE)) / Decimal("100")
    svc_pct   = _service_charge_pct(outlet)
    new_sub   = order.subtotal + added_subtotal
    new_vat   = (new_sub * vat_pct).quantize(Decimal("0.01"))
    new_svc   = (new_sub * svc_pct).quantize(Decimal("0.01"))
    new_total = new_sub + new_vat + new_svc - order.discount_amount

    order.subtotal       = new_sub
    order.vat_amount     = new_vat
    order.service_charge = new_svc
    order.total          = new_total

    db.commit()
    db.refresh(order)
    return order


def sync_offline_order(
    db: Session,
    branch_id: int,
    data,  # OrderSyncRequest
    waiter_id: Optional[int] = None,
):
    """راجع restaurant.services.sync_offline_order — نفس عقد fulfilled/
    partial/rejected بالظبط (07-BUSINESS-RULES.md § 9)، idempotent عبر
    client_local_id."""
    existing = crud.get_order_by_local_id(db, data.local_id)
    if existing:
        return {
            "order_id": existing.id,
            "status": "fulfilled",
            "fulfilled_items": existing.items,
            "rejected_items": [],
            "message": "الطلب اتسجّل بالفعل (retry آمن)",
        }

    fulfilled_requests = []
    rejected_items = []

    for item_req in data.items:
        item = crud.get_item(db, item_req.item_id)
        if not item or not item.is_available:
            rejected_items.append({
                "item_id": item_req.item_id,
                "name": item.name if item else f"#{item_req.item_id}",
                "reason": "out_of_stock",
                "available_qty": 0,
                "requested_qty": item_req.quantity,
            })
        else:
            fulfilled_requests.append(item_req)

    if not fulfilled_requests:
        return {
            "order_id": None,
            "status": "rejected",
            "fulfilled_items": [],
            "rejected_items": rejected_items,
            "message": "كل الأصناف غير متاحة حالياً",
        }

    sync_order_data = OrderCreate(
        outlet_id=data.outlet_id,
        table_id=data.table_id,
        order_type=data.order_type,
        guests_count=data.guests_count,
        notes=data.notes,
        items=fulfilled_requests,
    )
    order = create_order(db, branch_id, sync_order_data, waiter_id=waiter_id)
    order.client_local_id = data.local_id
    db.commit()
    db.refresh(order)

    order = update_order_status(db, order.id, "in_kitchen")
    db.commit()
    db.refresh(order)

    return {
        "order_id": order.id,
        "status": "partial" if rejected_items else "fulfilled",
        "fulfilled_items": order.items,
        "rejected_items": rejected_items,
        "message": (
            "تم تنفيذ الطلب جزئياً — راجع الأصناف المرفوضة" if rejected_items
            else "تم تنفيذ الطلب بالكامل"
        ),
    }


def update_order_status(
    db: Session, order_id: int, new_status: str,
    charge_to_room_id: Optional[int] = None,
    payment_method: Optional[str] = None,
) -> DiningOrder:
    order = _get_order_or_404(db, order_id)

    if order.status in ("paid", "cancelled"):
        raise ValueError(f"لا يمكن تغيير حالة طلب '{order.status}'")

    if new_status == "paid" and payment_method:
        order.payment_method = payment_method
    elif new_status == "paid" and not order.payment_method:
        order.payment_method = "cash"

    if new_status == "paid" and charge_to_room_id and not order.folio_id:
        from app.modules.pms.services import find_active_folio_for_room  # noqa: PLC0415
        folio_id = find_active_folio_for_room(db, order.branch_id, charge_to_room_id)
        if not folio_id:
            raise ValueError(f"مفيش ضيف مسجّل دخول في الغرفة {charge_to_room_id} حاليًا")
        order.folio_id = folio_id

    order = crud.update_order_status(db, order, new_status)

    # إرسال ticket لكل محطة (hot/grill/cold/bar/dessert) عند تحويل الطلب
    # لـ in_kitchen — راجع restaurant.services.update_order_status للتبرير
    # الكامل. هنا موحّد عبر كل الـ outlets (مفيش فرق مطعم/كافيه في الكود).
    if new_status == "in_kitchen":
        active_items = [item for item in order.items if item.status != "cancelled"]
        item_ids = {item.item_id for item in active_items}
        station_by_item = {
            di.id: di.station
            for di in db.query(DiningItem).filter(DiningItem.id.in_(item_ids)).all()
        } if item_ids else {}

        items_by_station: dict[str, list[dict]] = {}
        for item in active_items:
            station = station_by_item.get(item.item_id, "hot")
            items_by_station.setdefault(station, []).append({
                "order_item_id": item.id,
                "name":          item.name,
                "quantity":      item.quantity,
                "notes":         item.notes,
            })

        for station, items_snapshot in items_by_station.items():
            crud.create_kitchen_ticket(
                db,
                order_id=order.id,
                branch_id=order.branch_id,
                outlet_id=order.outlet_id,
                station=station,
                items_snapshot=items_snapshot,
            )

    if new_status in ("paid", "cancelled") and order.table_id:
        table = crud.get_table(db, order.table_id)
        if table:
            crud.update_table_status(db, table, "available")

    if new_status == "paid" and order.folio_id:
        try:
            from app.modules.finance import crud as finance_crud  # noqa: PLC0415
            from app.modules.finance.schemas import FolioChargeCreate  # noqa: PLC0415
            charge_data = FolioChargeCreate(
                charge_type="dining",
                description=f"طلب {order.order_number}",
                amount=order.subtotal,
                vat_amount=order.vat_amount,
                service_charge=order.service_charge,
                posted_at=datetime.utcnow(),
                ref_order_id=order.id,
            )
            finance_crud.add_charge(db, order.folio_id, charge_data)
            folio = finance_crud.get_folio(db, order.folio_id)
            if folio:
                finance_crud.recalculate_folio_total(db, folio)
        except Exception:
            pass  # ميمنعش إتمام الدفع لو فشل نشر الـ charge على الفوليو

    # قيد إيراد المنفذ — بيترحّل فورًا في الحالتين (كاش/محمّل على فوليو
    # غرفة)، بس لحساب مختلف حسب طريقة الدفع (راجع
    # restaurant.services._post_order_folio_charge_journal للتبرير الكامل).
    # الحساب نفسه بقى outlet.revenue_account_code (wagdy.md D-03) بدل
    # 4200/4400 الثابتين في restaurant/cafe الأصليين.
    if new_status == "paid":
        _deduct_inventory_for_order(db, order)
        outlet = crud.get_outlet(db, order.outlet_id)
        revenue_account = outlet.revenue_account_code if outlet else "4200"
        if order.folio_id:
            _post_order_folio_charge_journal(db, order, revenue_account)
        else:
            _post_order_revenue_journal(db, order, revenue_account)
        if order.customer_id:
            from app.modules.crm.services import record_customer_visit  # noqa: PLC0415
            visit_date = (
                utc_naive_to_local_date(order.created_at, settings.TIMEZONE)
                if order.created_at else local_today(settings.TIMEZONE)
            )
            record_customer_visit(db, order.customer_id, order.total, visit_date)

    db.commit()
    db.refresh(order)
    return order


def _deduct_inventory_for_order(db: Session, order: DiningOrder) -> None:
    """راجع restaurant.services._deduct_inventory_for_order — نفس أولوية
    الخصم بالظبط (وصفة حقيقية → ربط 1:1 قديم → تجاوز صامت)."""
    from app.modules.inventory import crud as inventory_crud  # noqa: PLC0415
    from app.modules.inventory import services as inventory_services  # noqa: PLC0415

    for order_item in order.items:
        if order_item.status == "cancelled":
            continue
        try:
            item = crud.get_item(db, order_item.item_id)
            if not item:
                continue
            variant = crud.get_variant(db, order_item.variant_id) if order_item.variant_id else None
            recipe_lines = _effective_recipe(item, variant)
            if recipe_lines:
                for line in recipe_lines:
                    product = inventory_crud.get_product(db, line.product_id)
                    if not product or not product.warehouse_id:
                        continue
                    inventory_services.consume_stock(
                        db,
                        branch_id=order.branch_id,
                        product_id=product.id,
                        warehouse_id=product.warehouse_id,
                        quantity=line.quantity_per_unit * order_item.quantity,
                        reference_type="dining_order",
                        reference_id=order.id,
                        moved_by=0,
                        allow_negative=True,
                    )
                continue
            if not item.linked_product_id:
                continue
            product = inventory_crud.get_product(db, item.linked_product_id)
            if not product or not product.warehouse_id:
                continue
            inventory_services.consume_stock(
                db,
                branch_id=order.branch_id,
                product_id=product.id,
                warehouse_id=product.warehouse_id,
                quantity=Decimal(order_item.quantity),
                reference_type="dining_order",
                reference_id=order.id,
                moved_by=0,
            )
        except Exception:
            continue


def _post_order_revenue_journal(db: Session, order: DiningOrder, revenue_account_code: str) -> None:
    """Dr. Cash (1100) / Cr. إيراد المنفذ (outlet.revenue_account_code) —
    دفع كاش/كارت فوري."""
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    post_simple_revenue_journal(
        db, order.branch_id, local_today(settings.TIMEZONE),
        debit_account_code="1100", credit_account_code=revenue_account_code,
        amount=order.total or Decimal("0"),
        reference=f"ORD-{order.order_number}",
        description=f"إيرادات دايننج — {order.order_number}",
        source="dining", source_id=order.id,
    )


def _post_order_folio_charge_journal(db: Session, order: DiningOrder, revenue_account_code: str) -> None:
    """Dr. ذمم الفوليو (1150) / Cr. إيراد المنفذ — طلب محمّل على فوليو
    غرفة. راجع restaurant.services._post_order_folio_charge_journal."""
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    post_simple_revenue_journal(
        db, order.branch_id, local_today(settings.TIMEZONE),
        debit_account_code="1150", credit_account_code=revenue_account_code,
        amount=order.total or Decimal("0"),
        reference=f"ORD-{order.order_number}",
        description=f"إيرادات دايننج (محمّل على الغرفة) — {order.order_number}",
        source="dining_folio_charge", source_id=order.id,
    )


def void_order_item(
    db: Session, order_id: int, item_id: int, reason: str, voided_by: int,
    acting_user_level: int = 100, approver_user_id: Optional[int] = None,
    approver_pin: Optional[str] = None,
) -> DiningOrder:
    """راجع restaurant.services.void_order_item — نفس المنطق بالظبط، بما
    فيه موافقة PIN عبر core.services.resolve_pin_approval (مفيش نظام
    موافقة موازي)."""
    order = _get_order_or_404(db, order_id)
    if order.status in ("paid", "cancelled"):
        raise ValueError(f"لا يمكن إلغاء صنف من طلب '{order.status}' — استخدم مرتجع بعد الدفع")

    item = crud.get_order_item(db, order_id, item_id)
    if not item:
        raise ValueError(f"الصنف {item_id} غير موجود في هذا الطلب")
    if item.status == "cancelled":
        raise ValueError("الصنف ده ملغي بالفعل")

    from app.modules.core import crud as core_crud, services as core_services  # noqa: PLC0415
    from app.modules.core.schemas import AuditLogCreate  # noqa: PLC0415

    approved_by = core_services.resolve_pin_approval(
        db, acting_user_level, approver_user_id, approver_pin, min_approver_level=60,
    )

    crud.void_order_item(db, item, reason, voided_by)
    core_crud.create_audit_log(db, AuditLogCreate(
        user_id=voided_by, approved_by=approved_by, branch_id=order.branch_id,
        action="void_order_item", entity_type="dining_order_item", entity_id=item.id,
        new_data=json.dumps({"reason": reason}),
    ))

    subtotal = Decimal("0")
    for i in order.items:
        if i.status == "cancelled":
            continue
        extras_total = sum((e.price_addition for e in i.extras), Decimal("0"))
        subtotal += (i.unit_price + extras_total) * i.quantity

    outlet = crud.get_outlet(db, order.outlet_id)
    vat_pct    = Decimal(str(settings.VAT_PERCENTAGE)) / Decimal("100")
    svc_pct    = _service_charge_pct(outlet)
    vat_amount = (subtotal * vat_pct).quantize(Decimal("0.01"))
    svc_charge = (subtotal * svc_pct).quantize(Decimal("0.01"))

    discount_amount = order.discount_amount
    applied_rule_id = order.applied_discount_rule_id
    if applied_rule_id:
        discount_amount, applied_rule_id = _recompute_discount_for_rule(
            db, applied_rule_id, subtotal, order,
        )

    total = max(Decimal("0"), subtotal + vat_amount + svc_charge - discount_amount)

    order.subtotal                 = subtotal
    order.vat_amount               = vat_amount
    order.service_charge           = svc_charge
    order.discount_amount          = discount_amount
    order.applied_discount_rule_id = applied_rule_id
    order.total                    = total

    db.commit()
    db.refresh(order)
    return order


def bump_order_item_status(db: Session, order_id: int, item_id: int, new_status: str) -> DiningOrder:
    """يبدّل حالة صنف واحد داخل طلب دايننج (pending → in_kitchen → ready →
    served) — تأكيد صنف بصنف من شاشة الـ KDS، بدل الاضطرار لتأكيد التذكرة
    كلها. راجع restaurant.services.bump_order_item_status — نفس المنطق
    بالظبط. لما كل أصناف تذكرة معيّنة (محطة واحدة) تبقى ready/served/
    cancelled، التذكرة نفسها بتتحوّل لـ 'done' تلقائيًا."""
    order = _get_order_or_404(db, order_id)
    item = crud.get_order_item(db, order_id, item_id)
    if not item:
        raise ValueError(f"الصنف {item_id} غير موجود في هذا الطلب")
    if item.status in ("cancelled", "refunded"):
        raise ValueError(f"لا يمكن تغيير حالة صنف {item.status}")

    crud.update_order_item_status(db, item, new_status)
    _sync_kitchen_tickets_for_order(db, order)

    db.commit()
    db.refresh(order)
    return order


def _sync_kitchen_tickets_for_order(db: Session, order: DiningOrder) -> None:
    """يحدّث حالة تذاكر المطبخ المرتبطة بالطلب ده حسب حالة أصنافها الفعلية —
    تذكرة تبقى 'done' لو كل أصنافها ready/served/cancelled، أو 'in_progress'
    لو أي صنف بدأ يتحرّك من pending. راجع
    restaurant.services._sync_kitchen_tickets_for_order — نفس المنطق
    بالظبط (تُستدعى بعد أي bump فردي، مش بعد التأكيد اليدوي الكامل)."""
    tickets = crud.list_tickets_for_order(db, order.id)
    if not tickets:
        return
    status_by_item_id = {item.id: item.status for item in order.items}
    for ticket in tickets:
        if ticket.status == "done":
            continue
        item_ids = [entry.get("order_item_id") for entry in ticket.items_snapshot]
        statuses = [status_by_item_id[iid] for iid in item_ids if iid in status_by_item_id]
        if not statuses:
            continue
        if all(s in ("ready", "served", "cancelled") for s in statuses):
            crud.update_ticket_status(db, ticket.id, "done")
        elif ticket.status == "pending" and any(s != "pending" for s in statuses):
            crud.update_ticket_status(db, ticket.id, "in_progress")


def _order_local_date_and_time(order: DiningOrder) -> tuple[date, time]:
    """راجع restaurant.services._order_local_date_and_time — نفس المنطق بالظبط."""
    if not order.created_at:
        now_local = local_now(settings.TIMEZONE)
        return now_local.date(), now_local.time()
    return (
        utc_naive_to_local_date(order.created_at, settings.TIMEZONE),
        utc_naive_to_local_time(order.created_at, settings.TIMEZONE),
    )


def _normalize_order_date(order_date) -> date:
    if isinstance(order_date, datetime):
        return utc_naive_to_local_date(order_date, settings.TIMEZONE)
    if isinstance(order_date, date):
        return order_date
    return local_today(settings.TIMEZONE)


def _build_discount_line_items(db: Session, order: DiningOrder) -> list[OrderLineItem]:
    """راجع restaurant.services._build_discount_line_items — استعلام واحد
    لكل الأصناف المميزة، بدون N+1."""
    active_items = [i for i in order.items if i.status != "cancelled"]
    item_ids = {i.item_id for i in active_items}
    category_by_item: dict[int, int | None] = {}
    if item_ids:
        category_by_item = dict(
            db.query(DiningItem.id, DiningItem.category_id)
            .filter(DiningItem.id.in_(item_ids))
            .all()
        )
    return [
        OrderLineItem(
            item_id=i.item_id,
            quantity=i.quantity,
            unit_price=i.unit_price,
            category_id=category_by_item.get(i.item_id),
        )
        for i in active_items
    ]


def _recompute_discount_for_rule(
    db: Session, rule_id: int, new_subtotal: Decimal, order: DiningOrder,
) -> tuple[Decimal, Optional[int]]:
    """راجع restaurant.services._recompute_discount_for_rule — نفس المنطق بالظبط."""
    try:
        from app.modules.finance.models import ConditionalDiscount  # noqa: PLC0415
        from app.modules.finance.services import discount_rule_from_orm  # noqa: PLC0415
    except ImportError:
        return Decimal("0"), None

    rule_orm = db.query(ConditionalDiscount).filter(ConditionalDiscount.id == rule_id).first()
    if not rule_orm or not rule_orm.is_active:
        return Decimal("0"), None
    order_date, order_time = _order_local_date_and_time(order)
    outlet = crud.get_outlet(db, order.outlet_id)
    ctx = OrderContext(
        total_amount=new_subtotal,
        item_count=0,
        order_date=_normalize_order_date(order_date),
        order_time=order_time,
        outlet=outlet.outlet_type if outlet else None,
        line_items=_build_discount_line_items(db, order),
    )
    result = calculate_discount(new_subtotal, [discount_rule_from_orm(rule_orm)], ctx)
    return result.amount_saved, result.rule_id


def refund_order_item(db: Session, order_id: int, item_id: int, reason: str, refunded_by: int) -> DiningOrder:
    """راجع restaurant.services.refund_order_item — نفس المنطق بالظبط."""
    order = _get_order_or_404(db, order_id)
    if order.status != "paid":
        raise ValueError(f"المرتجع بعد الدفع متاح بس للطلبات المدفوعة — الطلب ده حالته '{order.status}'")

    item = crud.get_order_item(db, order_id, item_id)
    if not item:
        raise ValueError(f"الصنف {item_id} غير موجود في هذا الطلب")
    if item.status in ("cancelled", "refunded"):
        raise ValueError("الصنف ده ملغي/مرتجع بالفعل")

    extras_total = sum((e.price_addition for e in item.extras), Decimal("0"))
    item_gross = (item.unit_price + extras_total) * item.quantity
    share_ratio = (item_gross / order.subtotal) if order.subtotal > 0 else Decimal("0")
    refund_vat = (order.vat_amount * share_ratio).quantize(Decimal("0.01"))
    refund_svc = (order.service_charge * share_ratio).quantize(Decimal("0.01"))
    refund_amount = item_gross + refund_vat + refund_svc

    crud.refund_order_item(db, item, reason, refunded_by)
    order.refunded_amount = (order.refunded_amount or Decimal("0")) + refund_amount

    active_items = [i for i in order.items if i.status not in ("cancelled", "refunded")]
    if not active_items:
        order.status = "refunded"

    outlet = crud.get_outlet(db, order.outlet_id)
    revenue_account = outlet.revenue_account_code if outlet else "4200"
    if order.folio_id:
        _reduce_folio_charge_for_refund(db, order, refund_amount, revenue_account)
    else:
        _post_order_refund_reversal_journal(db, order, refund_amount, revenue_account)

    db.commit()
    db.refresh(order)
    return order


def _reduce_folio_charge_for_refund(db: Session, order: DiningOrder, refund_amount: Decimal, revenue_account_code: str) -> None:
    """راجع restaurant.services._reduce_folio_charge_for_refund — نفس
    المنطق بالظبط، بما فيه فلترة charge_type + folio_id (منع تلبيس على
    شحنة outlet تاني في نفس الفوليو، نفس الباج اللي اتصلح هناك)."""
    try:
        from app.modules.finance import crud as finance_crud  # noqa: PLC0415
        from app.modules.finance.models import FolioCharge  # noqa: PLC0415

        charge = (
            db.query(FolioCharge)
            .filter_by(ref_order_id=order.id, folio_id=order.folio_id, charge_type="dining")
            .first()
        )
        if not charge:
            return
        folio = finance_crud.get_folio(db, order.folio_id)
        if not folio or folio.status == "closed":
            return
        gross_before = charge.amount + charge.vat_amount + charge.service_charge
        new_gross = max(Decimal("0"), gross_before - refund_amount)
        ratio = (new_gross / gross_before) if gross_before > 0 else Decimal("0")
        charge.amount = (charge.amount * ratio).quantize(Decimal("0.01"))
        charge.vat_amount = (charge.vat_amount * ratio).quantize(Decimal("0.01"))
        charge.service_charge = (charge.service_charge * ratio).quantize(Decimal("0.01"))
        db.flush()
        finance_crud.recalculate_folio_total(db, folio)
        _post_order_folio_refund_reversal_journal(db, order, refund_amount, revenue_account_code)
    except Exception:
        logger.error(
            "_reduce_folio_charge_for_refund فشل — طلب %s مرتجع %.2f ج — الفوليو %s قد يحتاج تصحيح يدوي",
            order.order_number, refund_amount, order.folio_id, exc_info=True,
        )


def _post_order_folio_refund_reversal_journal(db: Session, order: DiningOrder, refund_amount: Decimal, revenue_account_code: str) -> None:
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    post_simple_revenue_journal(
        db, order.branch_id, local_today(settings.TIMEZONE),
        debit_account_code=revenue_account_code, credit_account_code="1150",
        amount=refund_amount,
        reference=f"ORD-REFUND-{order.order_number}",
        description=f"مرتجع بعد الدفع (محمّل على الغرفة) — {order.order_number}",
        source="dining_folio_refund", source_id=order.id,
    )


def _post_order_refund_reversal_journal(db: Session, order: DiningOrder, refund_amount: Decimal, revenue_account_code: str) -> None:
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    post_simple_revenue_journal(
        db, order.branch_id, local_today(settings.TIMEZONE),
        debit_account_code=revenue_account_code, credit_account_code="1100",
        amount=refund_amount,
        reference=f"ORD-REFUND-{order.order_number}",
        description=f"مرتجع بعد الدفع — {order.order_number}",
        source="dining_refund", source_id=order.id,
    )


def _order_item_statuses(db: Session, item_ids: set[int]) -> dict[int, str]:
    """(order_item_id → status) لمجموعة أصناف — استعلام واحد بدل N+1 لكل
    تذكرة عند تجميع عدة تذاكر مع بعض. راجع
    restaurant.services._order_item_statuses — نفس المنطق بالظبط."""
    if not item_ids:
        return {}
    from app.modules.dining.models import DiningOrderItem  # noqa: PLC0415
    return dict(db.query(DiningOrderItem.id, DiningOrderItem.status).filter(DiningOrderItem.id.in_(item_ids)).all())


def _ticket_read_dict(ticket: DiningKitchenTicket, status_by_item_id: dict[int, str]) -> dict:
    """يبني dict متوافق مع KitchenTicketRead — بيضيف حالة كل صنف اللحظية
    (status) جوه items_snapshot من DiningOrderItem.status الحقيقي، بدل ما
    يفضل items_snapshot (JSON ثابت وقت إنشاء التذكرة) بيقول 'pending'
    للأبد حتى لو الصنف اتأكد فعليًا (bump فردي — راجع bump_order_item_status).
    راجع restaurant.services._ticket_read_dict — نفس المنطق بالظبط."""
    items_snapshot = [
        {**entry, "status": status_by_item_id.get(entry.get("order_item_id"), "pending")}
        for entry in ticket.items_snapshot
    ]
    return {
        "id": ticket.id,
        "branch_id": ticket.branch_id,
        "outlet_id": ticket.outlet_id,
        "order_id": ticket.order_id,
        "station": ticket.station,
        "items_snapshot": items_snapshot,
        "status": ticket.status,
        "created_at": ticket.created_at,
    }


def get_kds_tickets(
    db: Session,
    branch_id: int,
    outlet_id: Optional[int] = None,
    stations: Optional[list[str]] = None,
) -> list[dict]:
    """يرجّع تذاكر الـ KDS المعلقة لفرع معيّن — كل تذكرة بترجع مع حالة كل
    صنف اللحظية (راجع _ticket_read_dict)، استعلام واحد لكل الأصناف عبر كل
    التذاكر المرجّعة، مش N+1 لكل تذكرة. راجع restaurant.services.get_kds_tickets."""
    tickets = crud.list_pending_tickets(db, branch_id, outlet_id=outlet_id, stations=stations)
    item_ids = {
        entry.get("order_item_id")
        for t in tickets
        for entry in t.items_snapshot
        if entry.get("order_item_id") is not None
    }
    status_by_item_id = _order_item_statuses(db, item_ids)
    return [_ticket_read_dict(t, status_by_item_id) for t in tickets]


def update_kitchen_ticket_status(db: Session, ticket_id: int, new_status: str) -> dict:
    """يحدّث حالة تذكرة كاملة يدويًا (pending/in_progress/done) — تأكيد
    دفعة واحدة، بدل صنف بصنف (راجع bump_order_item_status). لو التذكرة
    اتأكدت كاملة (done)، أي صنف لسه pending/in_kitchen جواها بيترقّى لـ
    'ready' تلقائيًا — عشان DiningOrderItem.status وحالة التذكرة يفضلوا
    متسقين. راجع restaurant.services.update_kitchen_ticket_status."""
    from app.modules.dining.models import DiningOrderItem  # noqa: PLC0415

    ticket = crud.update_ticket_status(db, ticket_id, new_status)
    if not ticket:
        raise ValueError(f"التذكرة {ticket_id} غير موجودة")

    if new_status == "done" and ticket.items_snapshot:
        item_ids = {
            entry.get("order_item_id") for entry in ticket.items_snapshot
            if entry.get("order_item_id") is not None
        }
        if item_ids:
            db.query(DiningOrderItem).filter(
                DiningOrderItem.id.in_(item_ids),
                DiningOrderItem.status.in_(("pending", "in_kitchen")),
            ).update({"status": "ready"}, synchronize_session=False)

    db.commit()
    db.refresh(ticket)

    item_ids = {e.get("order_item_id") for e in ticket.items_snapshot if e.get("order_item_id") is not None}
    return _ticket_read_dict(ticket, _order_item_statuses(db, item_ids))


def generate_receipt_pdf(db: Session, order_id: int) -> bytes:
    """راجع restaurant.services.generate_receipt_pdf — نفس شكل الإيصال
    الحراري 80mm."""
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    order = _get_order_or_404(db, order_id)
    table_label = order.table.table_number if order.table else "—"

    fields = [
        ("رقم الطلب",    order.order_number),
        ("نوع الطلب",    order.order_type),
        ("الطاولة",      table_label),
    ]
    for item in order.items:
        fields.append((f"{item.quantity}× {item.name}", f"{item.unit_price:,.2f} EGP"))
    fields += [
        ("المجموع قبل الضريبة", f"{order.subtotal:,.2f} EGP"),
        ("ضريبة (VAT)",  f"{order.vat_amount:,.2f} EGP"),
        ("رسوم الخدمة",  f"{order.service_charge:,.2f} EGP"),
    ]
    if order.discount_amount and order.discount_amount > 0:
        fields.append(("الخصم", f"-{order.discount_amount:,.2f} EGP"))

    return builder.receipt_pdf_thermal(
        reference=order.order_number,
        title="إيصال الطلب",
        fields=fields,
        total=float(order.total),
        currency="EGP",
        note="شكراً لزيارتكم — الخيمة بيتش ريزورت",
    )


def apply_order_discount(db: Session, order_id: int) -> DiningOrder:
    """راجع restaurant.services.apply_order_discount — نفس المنطق بالظبط،
    بس outlet=outlet.outlet_type ديناميكي بدل نص ثابت "restaurant"/"cafe"،
    فقواعد scope_type="outlet" تفرّق فعليًا بين أي عدد من الـ outlets."""
    order = _get_order_or_404(db, order_id)

    if order.status in ("paid", "cancelled"):
        raise ValueError("لا يمكن تطبيق خصم على طلب مغلق")

    rules: list[DiscountRule] = []
    try:
        from app.modules.finance.models import ConditionalDiscount  # noqa: PLC0415
        from app.modules.finance.services import discount_rule_from_orm  # noqa: PLC0415
        rules_orm = (
            db.query(ConditionalDiscount)
            .filter(
                ConditionalDiscount.branch_id == order.branch_id,
                ConditionalDiscount.is_active.is_(True),
            )
            .all()
        )
        rules = [discount_rule_from_orm(r) for r in rules_orm]
    except ImportError:
        pass

    outlet = crud.get_outlet(db, order.outlet_id)
    total_items = sum(item.quantity for item in order.items)
    order_date, order_time = _order_local_date_and_time(order)
    ctx = OrderContext(
        total_amount=order.subtotal,
        item_count=total_items,
        order_date=order_date,
        order_time=order_time,
        outlet=outlet.outlet_type if outlet else None,
        line_items=_build_discount_line_items(db, order),
    )

    result = calculate_discount(order.subtotal, rules, ctx)
    order = crud.update_order_discount(
        db, order,
        discount_amount=result.amount_saved,
        rule_id=result.rule_id,
    )

    if result.applied and result.rule_id:
        try:
            from app.modules.finance.crud import increment_discount_uses  # noqa: PLC0415
            increment_discount_uses(db, result.rule_id)
        except ImportError:
            pass

    db.commit()
    db.refresh(order)
    return order


# ─────────────────────── Reporting / Food Cost ────────────────────────

def get_food_cost_report(
    db: Session,
    branch_id: int,
    date_from: date,
    date_to: date,
    outlet_id: Optional[int] = None,
    threshold_pct: Decimal = DEFAULT_FOOD_COST_THRESHOLD_PCT,
) -> FoodCostReportResponse:
    """راجع restaurant.services.get_food_cost_report للتبرير الكامل — نفس
    منطق التجميع بمفتاح (item_id, variant_id) بالظبط. ``outlet_id`` اختياري
    (None = كل الـ outlets في الفرع مجمّعين معًا)."""
    range_start, _ = local_date_to_utc_range(date_from, settings.TIMEZONE)
    _, range_end = local_date_to_utc_range(date_to, settings.TIMEZONE)

    items = crud.list_items_for_food_cost(db, branch_id, outlet_id)
    sales_rows = crud.get_paid_order_items_for_food_cost(db, branch_id, range_start, range_end, outlet_id)

    ReportKey = tuple[int, Optional[int]]  # (item_id, variant_id)
    qty_by_key: dict[ReportKey, int] = defaultdict(int)
    revenue_by_key: dict[ReportKey, Decimal] = defaultdict(lambda: Decimal("0"))
    by_day: dict[date, dict[ReportKey, list]] = defaultdict(lambda: defaultdict(lambda: [0, Decimal("0")]))

    for item_id, variant_id, unit_price, quantity, created_at in sales_rows:
        key = (item_id, variant_id)
        line_revenue = unit_price * quantity
        qty_by_key[key] += quantity
        revenue_by_key[key] += line_revenue
        local_day = utc_naive_to_local_date(created_at, settings.TIMEZONE)
        day_entry = by_day[local_day][key]
        day_entry[0] += quantity
        day_entry[1] += line_revenue

    lines: list[FoodCostReportLine] = []
    unit_cost_by_key: dict[ReportKey, Decimal] = {}
    recipe_key_ids: set[ReportKey] = set()
    total_revenue = Decimal("0")
    total_theoretical_cost = Decimal("0")
    items_missing_recipe = 0
    items_missing_recipe_revenue = Decimal("0")

    for item in items:
        available_variants = [v for v in item.variants if v.is_available]
        report_units: list[tuple[Optional[int], str, list]] = (
            [(v.id, f"{item.name} - {v.name}", _effective_recipe(item, v)) for v in available_variants]
            if available_variants
            else [(None, item.name, item.recipe_lines)]
        )

        for variant_id, display_name, effective_recipe_lines in report_units:
            key = (item.id, variant_id)
            has_recipe = bool(effective_recipe_lines)
            recipe_lines = [
                ((line.product.cost_price if line.product else None) or Decimal("0"), line.quantity_per_unit)
                for line in effective_recipe_lines
            ]
            quantity_sold = qty_by_key.get(key, 0)
            revenue = revenue_by_key.get(key, Decimal("0"))
            result = compute_food_cost_result(recipe_lines, quantity_sold, revenue)
            unit_cost_by_key[key] = result.theoretical_unit_cost
            if has_recipe:
                recipe_key_ids.add(key)

            if quantity_sold > 0:
                if has_recipe:
                    total_revenue += revenue
                    total_theoretical_cost += result.theoretical_total_cost
                else:
                    items_missing_recipe += 1
                    items_missing_recipe_revenue += revenue

            lines.append(FoodCostReportLine(
                item_id=item.id,
                item_name=display_name,
                variant_id=variant_id,
                has_recipe=has_recipe,
                quantity_sold=quantity_sold,
                revenue=revenue,
                theoretical_unit_cost=result.theoretical_unit_cost,
                theoretical_total_cost=result.theoretical_total_cost,
                food_cost_pct=result.food_cost_pct if has_recipe else None,
                gross_margin_amount=result.gross_margin_amount,
                gross_margin_pct=result.gross_margin_pct if has_recipe else None,
                exceeds_threshold=has_recipe and exceeds_threshold(result.food_cost_pct, threshold_pct),
            ))

    trend: list[CogsTrendPoint] = []
    current = date_from
    while current <= date_to:
        day_revenue = Decimal("0")
        day_cost = Decimal("0")
        for key, (qty, item_revenue) in by_day.get(current, {}).items():
            if key in recipe_key_ids:
                day_revenue += item_revenue
                day_cost += unit_cost_by_key.get(key, Decimal("0")) * qty
        day_cost = day_cost.quantize(Decimal("0.01"))
        trend.append(CogsTrendPoint(
            date=current,
            revenue=day_revenue,
            theoretical_cost=day_cost,
            food_cost_pct=(day_cost / day_revenue * 100).quantize(Decimal("0.01")) if day_revenue > 0 else None,
        ))
        current += timedelta(days=1)

    summary_pct = (total_theoretical_cost / total_revenue * 100).quantize(Decimal("0.01")) if total_revenue > 0 else None
    summary_margin_pct = (
        ((total_revenue - total_theoretical_cost) / total_revenue * 100).quantize(Decimal("0.01"))
        if total_revenue > 0 else None
    )
    summary = GrossMarginSummary(
        branch_id=branch_id,
        outlet_id=outlet_id,
        date_from=date_from,
        date_to=date_to,
        threshold_pct=threshold_pct,
        total_revenue=total_revenue,
        total_theoretical_cost=total_theoretical_cost,
        food_cost_pct=summary_pct,
        gross_margin_amount=(total_revenue - total_theoretical_cost).quantize(Decimal("0.01")),
        gross_margin_pct=summary_margin_pct,
        items_missing_recipe=items_missing_recipe,
        items_missing_recipe_revenue=items_missing_recipe_revenue,
    )

    alerts = [line for line in lines if line.exceeds_threshold]
    return FoodCostReportResponse(lines=lines, alerts=alerts, trend=trend, summary=summary)


def generate_food_cost_excel(
    db: Session, branch_id: int, date_from: date, date_to: date,
    outlet_id: Optional[int] = None,
    threshold_pct: Decimal = DEFAULT_FOOD_COST_THRESHOLD_PCT,
) -> bytes:
    """راجع restaurant.services.generate_food_cost_excel — نفس المنطق بالظبط."""
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    report = get_food_cost_report(db, branch_id, date_from, date_to, outlet_id, threshold_pct)

    rows = [
        [
            line.item_name, "نعم" if line.has_recipe else "لا (تكلفة غير معروفة)",
            line.quantity_sold, line.revenue, line.theoretical_total_cost,
            line.food_cost_pct if line.food_cost_pct is not None else "—",
            line.gross_margin_amount, "نعم" if line.exceeds_threshold else "لا",
        ]
        for line in report.lines
    ]

    return builder.excel(
        sheets=[{
            "name": "تكلفة الطعام",
            "headers": ["الصنف", "وصفة مسجّلة؟", "الكمية المباعة", "الإيراد",
                        "التكلفة النظرية", "نسبة التكلفة %", "هامش الربح", "تخطّى الحد؟"],
            "rows": rows,
            "col_types": ["text", "text", "number", "currency", "currency", "text", "currency", "text"],
            "summary": {
                "إجمالي الإيراد": report.summary.total_revenue,
                "إجمالي التكلفة النظرية": report.summary.total_theoretical_cost,
                "هامش الربح الإجمالي": report.summary.gross_margin_amount,
                "أصناف بدون وصفة": report.summary.items_missing_recipe,
            },
        }],
        title=f"تقرير تكلفة الطعام (دايننج) — {date_from} إلى {date_to}",
    )


# ─────────────────────── Outlet ────────────────────────────────────────

def create_outlet(db: Session, data) -> Outlet:
    outlet = crud.create_outlet(db, data)
    db.commit()
    db.refresh(outlet)
    return outlet


def update_outlet(db: Session, outlet_id: int, data) -> Outlet:
    outlet = crud.get_outlet(db, outlet_id)
    if not outlet:
        raise ValueError(f"المنفذ {outlet_id} غير موجود")
    outlet = crud.update_outlet(db, outlet, data)
    db.commit()
    db.refresh(outlet)
    return outlet
