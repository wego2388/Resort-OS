"""app/modules/dining/services.py — Business logic (يرمي ValueError، لا HTTPException).

يدمج restaurant/services.py + cafe/services.py في محرك طلبات واحد — راجع
docstrings models.py لتبرير القرارات المعمارية (Variants، station، إلخ).

تصحيح مهم عن الموديولين الأصليين (wagdy.md D-03): حسابات الإيراد الثابتة
4200 (مطعم) / 4400 (كافيه) بقت ``outlet.revenue_account_code`` — خاصية على
سجل الـ outlet نفسه، مش literal في الكود. أي outlet جديد (بار مسبح، بوفيه)
بياخد حساب إيراد مستقل من غير أي تعديل هنا.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db_errors import is_lock_not_available
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


class OrderPaymentConcurrencyError(Exception):
    """صف الطلب مشغول بعملية دفع أخرى (SELECT FOR UPDATE NOWAIT فشل) — 409
    ORDER_PAYMENT_IN_PROGRESS (راجع خطة Gate 1B)."""


class OrderAlreadyPaidError(Exception):
    """الطلب اتدفع بالفعل — اتكشف تحت قفل صف الطلب نفسه، مش من قراءة سابقة
    غير مقفولة — 409 ORDER_ALREADY_PAID (راجع خطة Gate 1B)."""


class InvalidOrderTotalError(Exception):
    """إجمالي الطلب صفر أو سالب وقت محاولة تحويله لـ "مدفوع" — 400
    INVALID_ORDER_TOTAL (راجع خطة Gate 1B)."""


class InvalidPaymentMethodError(Exception):
    """تناقض بين payment_method وحالة الفوليو (Gate 1B، مراجعة Codex
    الثانية) — 400 INVALID_PAYMENT_METHOD. القاعدة: order.folio_id
    (تحويل فعلي على فوليو ضيف) وpayment_method="room" لازم يتطابقوا
    دايمًا، مينفعش نرحّل قيد فوليو بينما payment_method بيدّعي كاش/بطاقة/
    محفظة، ولا العكس (طلب "room" من غير فوليو حقيقي أصلاً)."""


class IdempotencyConflictError(Exception):
    """نفس Idempotency-Key اتبعت لطلب/بنية دفع مختلفة عن أول استخدام لها
    (Gate 4A) — 409 IDEMPOTENCY_KEY_CONFLICT. المفتاح بيتولّد مرة لكل محاولة
    منطقية ويُعاد استخدامه عند retry بنفس النية فقط؛ إعادة استخدامه لنية
    مختلفة غلط عميل واضح لازم يترفض بدل ما يرجّع نتيجة أول محاولة بالغلط."""


class NoOpenShiftError(Exception):
    """محاولة تحصيل tender مباشر (كاش/بطاقة/محفظة) من غير وردية مفتوحة لنفس
    الكاشير والفرع (Gate 4A) — 409 NO_OPEN_SHIFT. الدفع المباشر لازم يُنسب
    لوردية مفتوحة عشان يظهر في تقرير الوردية ومطابقة الكاش؛ من غيرها الكاش
    المحصّل هيبقى غير منسوب (orphaned) — نفس القاعدة اللي كانت مفقودة تمامًا
    قبل Gate 4."""


class PaymentAllocationError(Exception):
    """مجموع الـ tenders لا يساوي إجمالي الطلب بدقة Decimal، أو tender بمبلغ
    غير صالح (Gate 4A) — 400 PAYMENT_ALLOCATION_MISMATCH."""


# ── Order state machine (Gate 4C) ──────────────────────────────────────
# جدول واحد مركزي لكل الانتقالات المسموحة بدل شروط ad-hoc متناثرة (كل mutation
# كانت بتفحص `status in ("paid","cancelled")` لوحدها). الرحلة الطبيعية:
# held → open → in_kitchen → served → paid → refunded. cancelled نهائية من أي
# حالة نشطة. الرجوع (served→open) والقفز غير المنطقي مرفوضين. الانتقال لنفس
# الحالة (no-op) مسموح دايمًا (idempotent). paid/refunded ليهم بواباتهم
# الخاصة (settle_order/refund_order_item) — موجودين هنا للاكتمال بس.
ORDER_TRANSITIONS: dict[str, set[str]] = {
    "held":       {"open", "in_kitchen", "served", "paid", "cancelled"},
    "open":       {"held", "in_kitchen", "served", "paid", "cancelled"},
    "in_kitchen": {"served", "paid", "cancelled"},
    "served":     {"paid", "cancelled"},
    "paid":       {"refunded"},
    "cancelled":  set(),
    "refunded":   set(),
}


def assert_order_transition(current: str, target: str) -> None:
    """يرفع ValueError لو الانتقال من current لـ target مش مسموح في
    ORDER_TRANSITIONS. الانتقال لنفس الحالة مسموح (idempotent)."""
    if target == current:
        return
    if target not in ORDER_TRANSITIONS.get(current, set()):
        allowed = ORDER_TRANSITIONS.get(current, set())
        if not allowed:
            raise ValueError(f"لا يمكن تغيير حالة طلب '{current}' (حالة نهائية)")
        raise ValueError(
            f"انتقال غير مسموح: '{current}' → '{target}' "
            f"(المسموح: {', '.join(sorted(allowed))})"
        )


def _get_order_or_404(db: Session, order_id: int) -> DiningOrder:
    order = crud.get_order(db, order_id)
    if not order:
        raise ValueError(f"الطلب {order_id} غير موجود")
    return order


def _lock_order_or_conflict(db: Session, order_id: int) -> DiningOrder:
    """يقفل صف الطلب (SELECT FOR UPDATE NOWAIT) ويترجم فشل القفل لـ
    OrderPaymentConcurrencyError (409) — Gate 4 (جولة مراجعة Codex الأولى):
    المسار الموحّد لكل mutation بيقرا-ثم-يكتب حالة/مبلغ الطلب. قبل الجولة دي
    settle_order/refund_order_item بس كانوا بيقفلوا الطلب؛ باقي الـ mutations
    (تحويل حالة، إضافة أصناف، إلغاء صنف، نقل طاولة، دمج، خصم) كانوا بيقروا
    غير مقفول، فسباق دفع + إلغاء (مثلاً) كان ممكن يسيب طلب مدفوع متعلّم
    cancelled (باج حقيقي مُثبَت). كل mutation بقى يقفل الطلب ويعيد فحص حالته
    تحت القفل، بنفس نمط الـ NOWAIT+409 الموجود بالظبط."""
    try:
        order = crud.get_order_for_update(db, order_id)
    except OperationalError as exc:
        if not is_lock_not_available(exc):
            raise
        raise OrderPaymentConcurrencyError(
            f"الطلب #{order_id} مشغول الآن بعملية أخرى — حاول تاني خلال لحظات"
        ) from exc
    if not order:
        raise ValueError(f"الطلب {order_id} غير موجود")
    return order


def _get_outlet_or_404(db: Session, outlet_id: int) -> Outlet:
    outlet = crud.get_outlet(db, outlet_id)
    if not outlet:
        raise ValueError(f"المنفذ {outlet_id} غير موجود")
    return outlet


_ORDER_TYPE_SVC_OVERRIDE_ATTR = {
    "takeaway":     "takeaway_service_charge_pct",
    "delivery":     "delivery_service_charge_pct",
    "room_service": "room_service_service_charge_pct",
}


def _service_charge_pct(outlet: Optional[Outlet], order_type: str = "dine_in") -> Decimal:
    """نسبة رسم الخدمة الفعلية للمنفذ + قناة الطلب — override بتاع القناة
    (takeaway/delivery/room_service) لو موجود، وإلا override عام للمنفذ لو
    موجود، وإلا settings.SERVICE_CHARGE_PERCENTAGE العام.

    2026-07-16 (بحث مقارنة Click القديم): Click كان بيفرّق فعليًا في
    التسعير حسب القناة — عادة takeaway/delivery من غير رسم خدمة (مفيش
    خدمة طاولة فعلية) وroom_service أحيانًا أعلى. **القيم دي كلها NULL
    افتراضيًا** — صفر تغيير سلوك على أي منفذ موجود لحد ما مدير يفعّلها
    صراحةً من إعدادات المنفذ (قرار تسعير حي يستاهل موافقة Mohamed، مش
    افتراض تلقائي)."""
    if outlet is not None:
        override_attr = _ORDER_TYPE_SVC_OVERRIDE_ATTR.get(order_type)
        if override_attr is not None:
            override = getattr(outlet, override_attr, None)
            if override is not None:
                return override / Decimal("100")
        if outlet.default_service_charge_pct is not None:
            return outlet.default_service_charge_pct / Decimal("100")
    return Decimal(str(settings.SERVICE_CHARGE_PERCENTAGE)) / Decimal("100")


# مركز التكلفة (finance.CostCenter.code — Batch 3) المقابل لـ outlet_type —
# مبني على نفس ROOM/REST/CAFE/BEACH/TS اللي finance.services.DEFAULT_COST_CENTERS
# بتستخدمها كمصدر حقيقة وحيد. outlet_type غير معروف (مش "restaurant"/"cafe")
# → None عمدًا (مفيش مركز تكلفة رابع/خامس مخترع هنا، نفس الـ 5 الموجودين بس).
_OUTLET_TYPE_TO_COST_CENTER = {"restaurant": "REST", "cafe": "CAFE"}


def _outlet_cost_center_code(outlet: Optional[Outlet]) -> Optional[str]:
    if outlet is None:
        return None
    return _OUTLET_TYPE_TO_COST_CENTER.get(outlet.outlet_type)


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


def _is_item_available_now(item: DiningItem) -> bool:
    """يتحقق إن الصنف داخل نافذة تقديمه الحالية (available_from_time/
    available_until_time) — راجع restaurant.services._is_item_available_now
    — نفس المنطق بالظبط (NULL في الاتنين = بدون قيد وقتي، نافذة عابرة
    لمنتصف الليل مدعومة، local_now مش وقت السيرفر الخام)."""
    start, end = item.available_from_time, item.available_until_time
    if start is None and end is None:
        return True
    start = start or time.min
    end = end or time.max
    now_time = local_now(settings.TIMEZONE).time()
    if start <= end:
        return start <= now_time <= end
    return now_time >= start or now_time <= end


def _check_item_available_now(item: DiningItem) -> None:
    """يرفع ValueError برسالة عربية واضحة لو الصنف خارج نافذة تقديمه
    الحالية — يُستدعى وقت إضافة صنف لطلب (إنشاء طلب جديد أو إضافة لطلب
    مفتوح)، مش وقت عرض المنيو بس. راجع restaurant.services._check_item_available_now."""
    if _is_item_available_now(item):
        return
    start = item.available_from_time.strftime("%H:%M") if item.available_from_time else "00:00"
    end = item.available_until_time.strftime("%H:%M") if item.available_until_time else "23:59"
    raise ValueError(f"الصنف '{item.name}' متاح فقط من {start} إلى {end}")


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

def assert_guest_self_order_enabled(db: Session, branch_id: int) -> None:
    """Gate 1 containment (Decision 0001 point 3 / PRODUCTION_READINESS_AUDIT
    C-02): unauthenticated guest self-ordering is closed by default.

    **تصحيح (جولة مراجعة Codex الثالثة):** AGENTS.md بيمنع الاعتماد على
    core.Setting (حر، قابل للتعديل عبر API الإعدادات) كبوابة أمان لوحدها.
    لازم الاتنين معًا: settings.DINING_SELF_ORDER_ENABLED (typed،
    deployment-level، مش قابل للتغيير من غير deploy/restart) + core.Setting
    الخاص بالفرع (dining.self_order_enabled). أي واحد بس متفعّل مش كافي."""
    from app.core.config import settings  # noqa: PLC0415
    from app.modules.core import services as core_services  # noqa: PLC0415

    if not settings.DINING_SELF_ORDER_ENABLED:
        raise ValueError("الطلب الذاتي غير متاح حاليًا — نادِ الجرسون لطلب الطلب أو الحساب")

    raw_value = core_services.get_setting_value(
        db, "dining.self_order_enabled", branch_id=branch_id, default="false",
    )
    enabled = str(raw_value).strip().lower() in ("1", "true", "yes", "y", "نعم")
    if not enabled:
        raise ValueError("الطلب الذاتي غير متاح حاليًا — نادِ الجرسون لطلب الطلب أو الحساب")


def create_order(
    db: Session,
    branch_id: int,
    data: OrderCreate,
    waiter_id: Optional[int] = None,
    hold: bool = False,
    guest_session_id: Optional[int] = None,
    guest_public_reference: Optional[str] = None,
) -> DiningOrder:
    outlet = _get_outlet_or_404(db, data.outlet_id)
    if outlet.branch_id != branch_id:
        # Gate 1 containment (جولة تصحيح ثانية): دايمًا صحيح للمسار
        # العام/الداخلي الحاليين (branch_id بيتحسب من outlet.branch_id
        # نفسه في الـ3 callers الموجودين) — دفاع عن أي caller مستقبلي
        # يبعت branch_id تاني بالغلط أو عمدًا.
        raise ValueError(f"المنفذ {data.outlet_id} لا يتبع هذا الفرع")

    if data.table_id is not None:
        table = crud.get_table(db, data.table_id)
        if not table:
            raise ValueError(f"الطاولة {data.table_id} غير موجودة")
        if table.branch_id != branch_id:
            raise ValueError(f"الطاولة {data.table_id} لا تتبع هذا الفرع")
        if table.status == "out_of_service":
            raise ValueError(f"الطاولة {table.table_number} خارج الخدمة")
        # Gate 4C: قفل صف الطاولة (blocking) ثم فحص طلب نشط — يسلسل أي
        # محاولتين متزامنتين يفتحوا طلب على نفس الطاولة، مع partial unique
        # index (uq_active_order_per_table) كـ backstop نهائي على مستوى الـ DB.
        crud.lock_table_for_update(db, data.table_id)
        conflicting = crud.get_active_order_for_table(db, data.table_id)
        if conflicting:
            raise ValueError(
                f"الطاولة {table.table_number} مشغولة بطلب نشط بالفعل ({conflicting.order_number})"
            )

    items_data = []
    subtotal = Decimal("0")

    for item_req in data.items:
        item = crud.get_item(db, item_req.item_id)
        if not item:
            raise ValueError(f"الصنف {item_req.item_id} غير موجود")
        if item.outlet_id != data.outlet_id or item.branch_id != branch_id:
            raise ValueError(f"الصنف {item_req.item_id} لا يتبع هذا المنفذ")
        if not item.is_available:
            raise ValueError(f"الصنف '{item.name}' غير متاح حالياً")
        _check_item_available_now(item)

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
    svc_pct    = _service_charge_pct(outlet, data.order_type)
    vat_amount = (subtotal * vat_pct).quantize(Decimal("0.01"))
    svc_charge = (subtotal * svc_pct).quantize(Decimal("0.01"))

    # رسم توصيل ثابت — بس delivery، ولقطة وقت الإنشاء (رسم ثابت مش نسبة،
    # فمش محتاج إعادة حساب لما الأصناف تتغيّر بعدين، راجع add_items_to_order
    # وvoid_order_item تحت).
    delivery_fee = Decimal("0")
    if data.order_type == "delivery" and outlet is not None and outlet.delivery_fee:
        delivery_fee = outlet.delivery_fee

    # خصم مجموعة العميل الدائم (standing discount) — تلقائي بالكامل لو
    # الطلب مرتبط بعميل عنده مجموعة نشطة، من غير أي تدخّل يدوي أو موافقة
    # PIN (مختلف عن apply_order_discount اللي بيطبّق قاعدة خصم شرطية —
    # راجع _resolve_order_discount تحت لقرار "الأفضل يفوز، مش تراكم" لما
    # الاتنين يتقابلوا لاحقًا على نفس الطلب).
    discount_amount = _customer_group_discount_amount(db, data.customer_id, subtotal)
    total = max(Decimal("0"), subtotal + vat_amount + svc_charge + delivery_fee - discount_amount)

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
        discount_amount=discount_amount,
        delivery_fee=delivery_fee,
        created_by=waiter_id,
        guest_session_id=guest_session_id,
        guest_public_reference=guest_public_reference,
    )

    if guest_session_id is not None:
        from app.modules.core import crud as core_crud  # noqa: PLC0415
        from app.modules.core.schemas import AuditLogCreate  # noqa: PLC0415
        core_crud.create_audit_log(db, AuditLogCreate(
            branch_id=branch_id,
            action="guest_order_created",
            entity_type="dining_order",
            entity_id=order.id,
            new_data=json.dumps({
                "public_reference": guest_public_reference,
                "outlet_id": outlet.id,
                "table_id": data.table_id,
            }, ensure_ascii=False, sort_keys=True),
        ))

    if data.table_id and data.order_type == "dine_in":
        table = crud.get_table(db, data.table_id)
        if table:
            crud.update_table_status(db, table, "occupied")

    try:
        db.commit()
    except IntegrityError as exc:
        # backstop: partial unique index منع طلبين نشطين على نفس الطاولة
        # (سباق فات فحص get_active_order_for_table تحت القفل) — رسالة واضحة
        # بدل خطأ DB خام.
        db.rollback()
        if "uq_active_order_per_table" in str(getattr(exc, "orig", exc)):
            raise ValueError("الطاولة مشغولة بطلب نشط بالفعل (سباق فتح مزدوج)") from exc
        raise
    db.refresh(order)
    return order


def add_items_to_order(db: Session, order_id: int, items: list, added_by: Optional[int] = None) -> DiningOrder:
    """راجع restaurant.services.add_items_to_order — نفس المنطق بالظبط.
    Gate 4C: كل صنف جديد بيحفظ مين أضافه (added_by) للتدقيق."""
    from app.modules.dining.models import DiningOrderItem, DiningOrderItemExtra  # noqa: PLC0415

    # Gate 4 (جولة مراجعة Codex الأولى): قفل الطلب + إعادة فحص الحالة تحت
    # القفل — عشان إضافة أصناف مايتسابقش مع دفع نفس الطلب.
    order = _lock_order_or_conflict(db, order_id)
    if order.status not in ("held", "open", "in_kitchen", "served"):
        raise ValueError(f"لا يمكن إضافة أصناف لطلب بحالة {order.status}")

    outlet = crud.get_outlet(db, order.outlet_id)
    added_subtotal = Decimal("0")
    for item_req in items:
        item = crud.get_item(db, item_req.item_id)
        if not item:
            raise ValueError(f"الصنف {item_req.item_id} غير موجود")
        if not item.is_available:
            raise ValueError(f"الصنف '{item.name}' غير متاح حالياً")
        _check_item_available_now(item)

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
            added_by  = added_by,
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
    svc_pct   = _service_charge_pct(outlet, order.order_type)
    new_sub   = order.subtotal + added_subtotal
    new_vat   = (new_sub * vat_pct).quantize(Decimal("0.01"))
    new_svc   = (new_sub * svc_pct).quantize(Decimal("0.01"))

    # ⚠️ باج حقيقي كان هنا (اتصلح أثناء ربط خصم مجموعة العميل): الخصم
    # القديم (discount_amount) كان بيتطبّق زي ما هو على subtotal الجديد
    # الأكبر من غير أي إعادة حساب — لو الطلب كان عليه خصم نسبة مئوية شرطية
    # مطبّق قبل إضافة الأصناف دي، القيمة كانت بتفضل مجمّدة عند رقم قديم
    # أصغر من المفروض (نفس فئة الباج اللي void_order_item كان بيتفاداه
    # بـ _recompute_discount_for_rule بالفعل، بس add_items_to_order ماكانش
    # بيعمل كده خالص). دلوقتي بيعيد حساب أفضل خصم (مجموعة أو قاعدة شرطية)
    # زي void_order_item بالظبط.
    discount_amount, applied_rule_id = _resolve_order_discount(db, order, new_sub)
    # order.delivery_fee رسم ثابت اتحدد وقت الإنشاء — بيفضل زي ما هو هنا،
    # مش بيتصفّر ولا بيتعاد حسابه (راجع تعليق DiningOrder.delivery_fee).
    new_total = max(Decimal("0"), new_sub + new_vat + new_svc + order.delivery_fee - discount_amount)

    order.subtotal                 = new_sub
    order.vat_amount               = new_vat
    order.service_charge           = new_svc
    order.discount_amount          = discount_amount
    order.applied_discount_rule_id = applied_rule_id
    order.total                    = new_total

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
    settled_by: Optional[int] = None,
    acting_user_level: int = 100,
    idempotency_key: Optional[str] = None,
) -> DiningOrder:
    """يغيّر حالة الطلب. التحويل لـ "مدفوع" وحده بقى وحدة عمل صارمة منفصلة
    (_mark_order_paid → settle_order — Gate 1B/4A: قفل صف الطلب، idempotency
    guard، إنشاء Payment منسوب للكاشير/الوردية، شحنة فوليو/خصم مخزون/قيد
    محاسبي من غير أي بلع أخطاء صامت، وcommit واحد بس). باقي التحويلات
    سلوكها القديم زي ما هو بالظبط — مفيش أثر مالي فيهم غير تحرير الطاولة.

    ⚠️ transition state machine: التحويلات المسموحة بتتحقق من جدول واحد
    مركزي (ORDER_TRANSITIONS) بدل شرط ad-hoc — راجع assert_order_transition."""
    if new_status == "paid":
        return _mark_order_paid(
            db, order_id,
            charge_to_room_id=charge_to_room_id,
            payment_method=payment_method,
            settled_by=settled_by,
            acting_user_level=acting_user_level,
            idempotency_key=idempotency_key,
        )

    # Gate 4 (جولة مراجعة Codex الأولى): نقفل صف الطلب ونعيد فحص حالته تحت
    # القفل — سباق تحويل حالة (إلغاء/تعليق) مع دفع نفس الطلب كان ممكن يسيب
    # طلب مدفوع متعلّم cancelled. النمط نفسه بتاع settle_order/refund بالظبط.
    order = _lock_order_or_conflict(db, order_id)

    assert_order_transition(order.status, new_status)

    # M4 (state invariant): تحويل in_kitchen→in_kitchen no-op حقيقي — قبل
    # كده كان بيعيد إنشاء تذاكر مطبخ مكررة رغم إنه idempotent. لازم نلتقط
    # الحالة السابقة قبل الكتابة عشان نعرف هل ده أول دخول للمطبخ ولا إعادة.
    previous_status = order.status

    order = crud.update_order_status(db, order, new_status)

    # إرسال ticket لكل محطة (hot/grill/cold/bar/dessert) عند تحويل الطلب
    # لـ in_kitchen — راجع restaurant.services.update_order_status للتبرير
    # الكامل. هنا موحّد عبر كل الـ outlets (مفيش فرق مطعم/كافيه في الكود).
    # M4: بس أول دخول للمطبخ (previous_status != "in_kitchen") بيولّد تذاكر —
    # إعادة إرسال طلب أصلاً in_kitchen مابتنشئش تذاكر مكررة.
    if new_status == "in_kitchen" and previous_status != "in_kitchen":
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

    if new_status == "cancelled" and order.table_id:
        table = crud.get_table(db, order.table_id)
        if table:
            crud.update_table_status(db, table, "available")

    db.commit()
    db.refresh(order)
    return order


def _settlement_intent_hash(order_id: int, tenders: list[dict]) -> str:
    """sha256 لبنية التسوية الأساسية — نفس order_id + نفس مجموعة الـ tenders
    (طريقة/مبلغ/غرفة، مرتبة) = نفس الـ hash. أساس idempotency: retry بنفس
    النية بيطابق، ونية مختلفة بنفس المفتاح بتترفض 409. المبلغ None (دفع
    كامل بـ tender واحد) بيتمثّل كـ "full" عشان يفضل ثابت عبر إعادة المحاولة."""
    norm = sorted(
        (
            str(t["method"]),
            "full" if t.get("amount") is None else str(Decimal(str(t["amount"])).quantize(Decimal("0.01"))),
            t.get("charge_to_room_id"),
        )
        for t in tenders
    )
    canonical = json.dumps(
        {"order_id": order_id, "tenders": norm},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def settle_order(
    db: Session,
    order_id: int,
    *,
    tenders: list[dict],
    settled_by: Optional[int] = None,
    acting_user_level: int = 100,
    idempotency_key: Optional[str] = None,
) -> DiningOrder:
    """وحدة العمل الصارمة الموحّدة لتحصيل طلب دايننج (Gate 4A) — المسار
    الوحيد لتحويل طلب لـ "مدفوع"، سواء بـ tender واحد (paid) أو أكتر (split).
    commit واحد بس؛ أي فشل بيعمل rollback كامل صريح.

    ``tenders``: list of {"method": cash|card|wallet|room, "amount": Decimal|None,
    "charge_to_room_id": Optional[int]}. amount=None مسموح فقط لـ tender واحد
    (يعني "الإجمالي كله"). مجموع المبالغ لازم يساوي order.total بدقة Decimal.

    عقد الذرّية (الـ brief §2.3): في نفس المعاملة — قفل الطلب وإعادة فحصه،
    idempotency guard، شحنة الفوليو للجزء المحمّل على الغرفة، Payment لكل
    tender مباشر منسوب للكاشير/الوردية، خصم المخزون، القيد المحاسبي الصح لكل
    allocation، زيارة العميل، حالة الطلب والطاولة، وصف DiningSettlement.
    """
    from app.modules.dining.payment_policy import (  # noqa: PLC0415
        ALL_TENDER_METHODS, is_direct_method, resolve_direct_tender_account,
    )
    from app.modules.finance import services as finance_services  # noqa: PLC0415

    try:
        order = _lock_order_or_conflict(db, order_id)

        intent_hash = _settlement_intent_hash(order_id, tenders)

        # idempotency guard — قبل أي فحص حالة، عشان replay ناجح يرجّع نفس
        # النتيجة حتى لو الطلب بقى "paid".
        if idempotency_key:
            existing = crud.get_settlement_by_key(db, order.branch_id, idempotency_key)
            if existing is not None:
                if existing.order_id == order_id and existing.intent_hash == intent_hash:
                    db.rollback()  # مفيش تعديل — نسيب القفل ونرجّع النتيجة الموجودة
                    return _get_order_or_404(db, order_id)
                raise IdempotencyConflictError(
                    "نفس مفتاح الـ idempotency اتبعت لعملية دفع مختلفة — "
                    "استخدم مفتاح جديد لمحاولة جديدة"
                )

        if order.status == "paid":
            raise OrderAlreadyPaidError(f"الطلب #{order_id} مدفوع بالفعل")
        if order.status in ("cancelled", "refunded"):
            raise ValueError(f"لا يمكن تحصيل طلب بحالة '{order.status}'")

        if (order.total or Decimal("0")) <= 0:
            raise InvalidOrderTotalError(f"إجمالي الطلب #{order_id} غير صالح (صفر أو سالب)")

        # ── تطبيع وتحقق الـ tenders ──────────────────────────────────
        if not tenders:
            raise PaymentAllocationError("لازم tender واحد على الأقل")
        none_amounts = [t for t in tenders if t.get("amount") is None]
        if none_amounts and len(tenders) > 1:
            raise PaymentAllocationError("amount=None (الإجمالي كله) مسموح فقط لـ tender واحد")

        norm: list[dict] = []
        for t in tenders:
            method = t["method"]
            if method not in ALL_TENDER_METHODS:
                raise PaymentAllocationError(f"طريقة دفع غير معروفة: {method}")
            amount = order.total if t.get("amount") is None else Decimal(str(t["amount"])).quantize(Decimal("0.01"))
            if amount <= 0:
                raise PaymentAllocationError(f"مبلغ tender غير صالح: {amount}")
            norm.append({"method": method, "amount": amount, "charge_to_room_id": t.get("charge_to_room_id")})

        # M1 (جولة مراجعة Codex الأولى): مقارنة Decimal دقيقة بعد quantize
        # للطرفين — مش tolerance ± 0.01 اللي كان بيسمح بانحراف قرش كامل يعدّي
        # (الـ brief §2.1: "لا tolerance غامضة تسمح بزيادة/نقص فعلي"). كل
        # مبلغ tender متكوّنتز أصلاً لـ 0.01، وorder.total عمود Numeric(_,2)،
        # فمجموع الـ tenders الصح لازم يساوي order.total بالظبط.
        total_tenders = sum((t["amount"] for t in norm), Decimal("0")).quantize(Decimal("0.01"))
        order_total_q = (order.total or Decimal("0")).quantize(Decimal("0.01"))
        if total_tenders != order_total_q:
            raise PaymentAllocationError(
                f"مجموع الدفعات ({total_tenders:.2f}) لا يساوي إجمالي الطلب ({order_total_q:.2f})"
            )

        direct = [t for t in norm if is_direct_method(t["method"])]
        room = [t for t in norm if t["method"] == "room"]

        # حل حساب GL لكل tender مباشر (fail-closed) قبل أي تعديل — أي طريقة
        # غير مهيّأة (card/wallet) بترفع PaymentMethodNotConfiguredError فورًا.
        for t in direct:
            t["account"] = resolve_direct_tender_account(t["method"])

        # tender مباشر محتاج وردية مفتوحة لنفس الكاشير والفرع (الـ brief §2.1).
        # الإنفاذ بيتفعّل كل ما فيه كاشير محدد (settled_by) — وده **دايمًا**
        # صحيح على مسار الإنتاج الوحيد (الـ router بيفرض كاشير+ ويمرّر user.id،
        # راجع PATCH .../status و.../split-bill)، فالـ invariant مضمون في
        # الإنتاج بالكامل. settled_by=None يعني مفيش actor كاشير أصلاً (نداء
        # داخلي/قديم، مش مسار HTTP) — في الحالة دي الـ tender بيتسجّل بدون
        # نسبة وردية بدل ما نرفض بالغلط "كاشير بلا وردية" وهو مفيش كاشير أصلاً.
        # Gate 4 (جولة مراجعة Codex الأولى): نقفل صف الوردية (NOWAIT) بدل
        # قراءة غير مقفولة — عشان نسب الـ Payment للوردية يتسلسل فعليًا ضد
        # close_shift (نفس الصف). ترتيب القفل ثابت: Order (اتقفل فوق) قبل
        # Shift — مفيش مسار تاني بياخد Shift قبل Order، فمفيش deadlock. لو
        # الوردية بتتقفل الآن → ShiftCloseInProgressError (409 retry).
        shift_id = None
        if direct and settled_by is not None:
            open_shift = finance_services._lock_open_shift_or_conflict(db, order.branch_id, settled_by)
            if not open_shift:
                raise NoOpenShiftError(
                    "مفيش وردية مفتوحة لهذا الكاشير — لازم تفتح وردية قبل تحصيل دفع مباشر"
                )
            shift_id = open_shift.id

        # حل فوليو كل tender غرفة
        for t in room:
            room_id = t.get("charge_to_room_id")
            if room_id:
                from app.modules.pms.services import find_active_folio_for_room  # noqa: PLC0415
                folio_id = find_active_folio_for_room(db, order.branch_id, room_id)
                if not folio_id:
                    raise ValueError(f"مفيش ضيف مسجّل دخول في الغرفة {room_id} حاليًا")
            elif order.folio_id:
                folio_id = order.folio_id
            else:
                raise InvalidPaymentMethodError(
                    "الدفع على الغرفة محتاج charge_to_room_id أو فوليو مرتبط بالطلب بالفعل"
                )
            t["folio_id"] = folio_id

        # تناقض: فوليو مرتبط بالطلب بالفعل لكن مفيش أي tender غرفة (قيد فوليو
        # هيترحّل بينما الدفع بيدّعي كاش/بطاقة) — نفس شبكة أمان Gate 1B.
        if order.folio_id and not room:
            raise InvalidPaymentMethodError(
                f"الطلب مرتبط بفوليو #{order.folio_id} لكن مفيش دفعة 'room' — "
                "القيد المحاسبي لازم يتطابق مع طريقة الدفع"
            )

        # ── تنفيذ التسوية ────────────────────────────────────────────
        single_tender = len(norm) == 1
        if single_tender:
            order.payment_method = norm[0]["method"]
        else:
            order.payment_method = "split:" + ",".join(t["method"] for t in norm)
        if room and not order.folio_id:
            order.folio_id = room[0]["folio_id"]

        order = crud.update_order_status(db, order, "paid")
        if order.table_id:
            table = crud.get_table(db, order.table_id)
            if table:
                crud.update_table_status(db, table, "available")

        outlet = crud.get_outlet(db, order.outlet_id)
        revenue_account = outlet.revenue_account_code if outlet else "4200"

        for t in room:
            _settle_room_tender(db, order, t, revenue_account, single_tender=single_tender)
        for t in direct:
            _settle_direct_tender(
                db, order, t, revenue_account, cashier_id=settled_by, shift_id=shift_id,
            )

        # خصم المخزون مرة واحدة للطلب كله جوه المعاملة الصارمة.
        _deduct_inventory_for_order(db, order, commit=False, strict=True)

        if order.customer_id:
            from app.modules.crm.services import record_customer_visit  # noqa: PLC0415
            visit_date = (
                utc_naive_to_local_date(order.created_at, settings.TIMEZONE)
                if order.created_at else local_today(settings.TIMEZONE)
            )
            record_customer_visit(db, order.customer_id, order.total, visit_date)

        # M2 (جولة مراجعة Codex الأولى): لقطة توزيع الـ tenders — مصدر تاريخي
        # مستقل عن حالة Payment (تقرير الوردية بيجمع حصة الغرفة من هنا،
        # والإيصال التاريخي يعيد بناء الـ split بدون سعر منيو حالي).
        tender_breakdown = [
            {
                "method": t["method"],
                "amount": str(t["amount"]),
                **({"account": t["account"]} if t.get("account") else {}),
                **({"folio_id": t["folio_id"]} if t.get("folio_id") else {}),
            }
            for t in norm
        ]
        crud.create_settlement(
            db, branch_id=order.branch_id, order_id=order.id,
            idempotency_key=idempotency_key, intent_hash=intent_hash,
            total=order.total, cashier_id=settled_by if direct else None,
            shift_id=shift_id, created_by=settled_by,
            tender_breakdown=tender_breakdown,
        )

        # Gate 8: a linked "request bill" is operational state only. Close
        # it in this same strict payment transaction after all financial
        # effects succeeded and before the single commit.
        from app.modules.core import services as core_services  # noqa: PLC0415
        core_services.resolve_bill_requests_for_paid_order(db, order, settled_by)

        db.commit()
        db.refresh(order)
        return order
    except Exception:
        db.rollback()
        raise


def _settle_room_tender(
    db: Session, order: DiningOrder, tender: dict, revenue_account_code: str,
    *, single_tender: bool,
) -> None:
    """جزء الطلب المحمّل على فوليو غرفة — شحنة فوليو + قيد Dr ذمم(1150)/Cr
    إيراد. tender واحد كامل: نفس شكل Gate 1B بالظبط (amount=net_subtotal،
    القيد بـ order.total). split: حصة متناسبة، ومجموع (amount+vat+svc) =
    tender.amount بالظبط (البواقي بتتحط في amount) عشان الإيراد المرحّل =
    order.total بالضبط."""
    from app.modules.finance import services as finance_services  # noqa: PLC0415
    from app.modules.finance.schemas import FolioChargeCreate  # noqa: PLC0415

    folio_id = tender["folio_id"]
    if single_tender:
        discount = order.discount_amount or Decimal("0")
        net_subtotal = max(Decimal("0"), order.subtotal - discount)
        charge_data = FolioChargeCreate(
            charge_type="dining", description=f"طلب {order.order_number}",
            amount=net_subtotal, vat_amount=order.vat_amount,
            service_charge=order.service_charge,
            posted_at=datetime.utcnow(), ref_order_id=order.id,
        )
        finance_services.add_folio_charge(db, folio_id, charge_data)
        _post_order_folio_charge_journal(db, order, revenue_account_code, commit_cost_centers=False, strict=True)
        return

    amount = tender["amount"]
    ratio = (amount / order.total) if order.total > 0 else Decimal("0")
    vat_share = (order.vat_amount * ratio).quantize(Decimal("0.01"))
    svc_share = (order.service_charge * ratio).quantize(Decimal("0.01"))
    amt_share = amount - vat_share - svc_share
    charge_data = FolioChargeCreate(
        charge_type="dining", description=f"طلب {order.order_number} (split)",
        amount=amt_share, vat_amount=vat_share, service_charge=svc_share,
        posted_at=datetime.utcnow(), ref_order_id=order.id,
    )
    finance_services.add_folio_charge(db, folio_id, charge_data)
    outlet = crud.get_outlet(db, order.outlet_id)
    finance_services.post_simple_revenue_journal(
        db, order.branch_id, local_today(settings.TIMEZONE),
        debit_account_code="1150", credit_account_code=revenue_account_code,
        amount=amount, reference=f"ORD-{order.order_number}",
        description=f"إيرادات دايننج (محمّل على الغرفة، split) — {order.order_number}",
        source="dining_folio_charge", source_id=order.id,
        cost_center_code=_outlet_cost_center_code(outlet),
        commit_cost_centers=False, strict=True,
    )


def _settle_direct_tender(
    db: Session, order: DiningOrder, tender: dict, revenue_account_code: str,
    *, cashier_id: Optional[int], shift_id: Optional[int],
) -> None:
    """tender مباشر (cash/card/wallet) — Payment حقيقي منسوب للكاشير/الوردية
    (عشان يظهر في تقرير الوردية) + قيد Dr <حساب الطريقة>/Cr إيراد. حساب
    الطريقة اتحل fail-closed في settle_order (cash→1100، card/wallet→حساب
    مهيّأ أو رفض)."""
    from app.modules.finance import crud as finance_crud  # noqa: PLC0415
    from app.modules.finance import services as finance_services  # noqa: PLC0415

    amount = tender["amount"]
    method = tender["method"]
    account = tender["account"]

    finance_crud.create_direct_payment(
        db, branch_id=order.branch_id, amount=amount, method=method,
        posted_at=datetime.utcnow(), shift_id=shift_id, cashier_id=cashier_id,
        reference=f"ORD-{order.order_number}", ref_order_id=order.id, source="dining",
    )
    outlet = crud.get_outlet(db, order.outlet_id)
    finance_services.post_simple_revenue_journal(
        db, order.branch_id, local_today(settings.TIMEZONE),
        debit_account_code=account, credit_account_code=revenue_account_code,
        amount=amount, reference=f"ORD-{order.order_number}",
        description=f"إيرادات دايننج ({method}) — {order.order_number}",
        source="dining", source_id=order.id,
        cost_center_code=_outlet_cost_center_code(outlet),
        commit_cost_centers=False, strict=True,
    )


def _mark_order_paid(
    db: Session,
    order_id: int,
    *,
    charge_to_room_id: Optional[int],
    payment_method: Optional[str],
    settled_by: Optional[int] = None,
    acting_user_level: int = 100,
    idempotency_key: Optional[str] = None,
) -> DiningOrder:
    """تحصيل طلب بـ tender واحد (المسار العادي من PATCH .../status=paid) —
    بيبني tender واحد ويمرّره لـ settle_order (المسار الموحّد). يحل طريقة
    الدفع النهائية من payment_method/charge_to_room_id/فوليو الطلب بنفس
    منطق Gate 1B بالظبط (peek غير مقفول لبناء الـ tender؛ settle_order بيعيد
    القفل والتحقق كله تحت قفل صف الطلب)."""
    order = crud.get_order(db, order_id)
    if not order:
        raise ValueError(f"الطلب {order_id} غير موجود")

    # عقد payment_method/فوليو (Gate 1B) — يترفض 400 قبل أي أثر.
    if charge_to_room_id and payment_method and payment_method != "room":
        raise InvalidPaymentMethodError(
            f"مينفعش تحدد charge_to_room_id مع payment_method='{payment_method}' "
            "— لازم يبقى 'room' لو الدفع محمّل على غرفة"
        )
    if payment_method == "room" and not charge_to_room_id and not order.folio_id:
        raise InvalidPaymentMethodError(
            "payment_method='room' محتاج charge_to_room_id أو فوليو مرتبط بالطلب بالفعل"
        )

    if payment_method:
        method = payment_method
    elif order.folio_id or charge_to_room_id:
        method = "room"
    elif order.payment_method and order.payment_method in ("cash", "card", "wallet", "room"):
        method = order.payment_method
    else:
        method = "cash"

    tender = {"method": method, "amount": None, "charge_to_room_id": charge_to_room_id}
    return settle_order(
        db, order_id, tenders=[tender], settled_by=settled_by,
        acting_user_level=acting_user_level, idempotency_key=idempotency_key,
    )


def _deduct_inventory_for_order(
    db: Session, order: DiningOrder, *, commit: bool = True, strict: bool = False,
) -> None:
    """راجع restaurant.services._deduct_inventory_for_order — نفس أولوية
    الخصم بالظبط (وصفة حقيقية → ربط 1:1 قديم → تجاوز صامت).

    commit/strict (Gate 1B): زي consume_stock بالظبط. الافتراضي (True/False)
    يحافظ على السلوك القديم — بيتجاوز (continue) أي بند فشل خصمه بصمت عشان
    فشل مكوّن واحد ميوقفش تحصيل الطلب كله (استخدام split_bill/التوافق
    الخلفي). strict=True (دفع طلب دايننج فقط) بيوقف عند أول فشل ويرفعه —
    استهلاك المخزون بقى جزء من معاملة الدفع الصارمة اللي لازم تفشل كلها أو
    تنجح كلها، مش تكمل من غير أثر مخزون حقيقي بصمت."""
    from app.modules.inventory import crud as inventory_crud  # noqa: PLC0415
    from app.modules.inventory import services as inventory_services  # noqa: PLC0415
    from app.modules.inventory.services import InventoryConfigurationError  # noqa: PLC0415

    outlet = crud.get_outlet(db, order.outlet_id)
    cost_center_code = _outlet_cost_center_code(outlet)

    def _skip_or_raise(strict_message: str) -> None:
        """مراجعة Codex الثانية (Gate 1B): كل "تجاوز صامت" هنا كان بيتحول
        continue بدون تمييز — يعني إعداد ناقص حقيقي (منتج/مخزن محذوف، منتج
        من فرع تاني) كان بيتجاوز بصمت زي بالظبط "الصنف مفهوش وصفة ولا منتج
        مرتبط" (الحالة الوحيدة المقصودة فعلاً تتجاوز). strict=True بقى يفشل
        بوضوح لأي حالة غير الحالة المقصودة دي، مش يكمل من غير خصم مخزون
        حقيقي بصمت."""
        if strict:
            raise InventoryConfigurationError(strict_message)

    for order_item in order.items:
        if order_item.status == "cancelled":
            continue
        try:
            item = crud.get_item(db, order_item.item_id)
            if not item:
                _skip_or_raise(
                    f"صنف الطلب #{order_item.id} بيشير لـDiningItem #{order_item.item_id} غير موجود"
                )
                continue
            variant = crud.get_variant(db, order_item.variant_id) if order_item.variant_id else None
            recipe_lines = _effective_recipe(item, variant)
            if recipe_lines:
                for line in recipe_lines:
                    product = inventory_crud.get_product(db, line.product_id)
                    if not product:
                        _skip_or_raise(
                            f"منتج الوصفة #{line.product_id} (لصنف #{item.id}) غير موجود"
                        )
                        continue
                    if product.branch_id != order.branch_id:
                        _skip_or_raise(
                            f"منتج الوصفة #{product.id} يخص فرع #{product.branch_id}، "
                            f"مش فرع الطلب #{order.branch_id}"
                        )
                        continue
                    if not product.warehouse_id:
                        _skip_or_raise(f"منتج الوصفة #{product.id} من غير مخزن مرتبط")
                        continue
                    # مراجعة Codex الثالثة: التحقق السابق كان بيتأكد من فرع
                    # المنتج بس — منتج فرع A ممكن يتربط بمخزن فرع B فعليًا
                    # (create_product مافيهاش أي تحقق إن warehouse_id بتاعه
                    # نفس فرع المنتج). لازم نتأكد المخزن نفسه موجود وتابع
                    # لفرع الطلب فعلاً قبل الخصم.
                    warehouse = inventory_crud.get_warehouse(db, product.warehouse_id)
                    if not warehouse:
                        _skip_or_raise(
                            f"مخزن منتج الوصفة #{product.id} (#{product.warehouse_id}) غير موجود"
                        )
                        continue
                    if warehouse.branch_id != order.branch_id:
                        _skip_or_raise(
                            f"مخزن منتج الوصفة #{product.id} يخص فرع #{warehouse.branch_id}، "
                            f"مش فرع الطلب #{order.branch_id}"
                        )
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
                        cost_center_code=cost_center_code,
                        commit=commit,
                        strict=strict,
                    )
                continue
            if not item.linked_product_id:
                # الحالة الوحيدة المقصودة عمدًا تتجاوز حتى في strict=True —
                # الصنف مفهوش وصفة ولا منتج مرتبط أصلاً (مش إعداد ناقص).
                continue
            product = inventory_crud.get_product(db, item.linked_product_id)
            if not product:
                _skip_or_raise(f"المنتج المرتبط #{item.linked_product_id} (لصنف #{item.id}) غير موجود")
                continue
            if product.branch_id != order.branch_id:
                _skip_or_raise(
                    f"المنتج المرتبط #{product.id} يخص فرع #{product.branch_id}، "
                    f"مش فرع الطلب #{order.branch_id}"
                )
                continue
            if not product.warehouse_id:
                _skip_or_raise(f"المنتج المرتبط #{product.id} من غير مخزن مرتبط")
                continue
            # مراجعة Codex الثالثة: نفس تحقق المخزن اللي اتضاف لفرع الوصفة
            # فوق — منتج فرع A ممكن يتربط بمخزن فرع B فعليًا (create_product
            # مافيهاش أي تحقق إن warehouse_id بتاعه نفس فرع المنتج).
            warehouse = inventory_crud.get_warehouse(db, product.warehouse_id)
            if not warehouse:
                _skip_or_raise(
                    f"مخزن المنتج المرتبط #{product.id} (#{product.warehouse_id}) غير موجود"
                )
                continue
            if warehouse.branch_id != order.branch_id:
                _skip_or_raise(
                    f"مخزن المنتج المرتبط #{product.id} يخص فرع #{warehouse.branch_id}، "
                    f"مش فرع الطلب #{order.branch_id}"
                )
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
                cost_center_code=cost_center_code,
                commit=commit,
                strict=strict,
            )
        except InventoryConfigurationError:
            raise
        except Exception:
            if strict:
                raise
            continue


def _post_order_revenue_journal(
    db: Session, order: DiningOrder, revenue_account_code: str,
    *, commit_cost_centers: bool = True, strict: bool = False,
) -> None:
    """Dr. Cash (1100) / Cr. إيراد المنفذ (outlet.revenue_account_code) —
    دفع كاش/كارت فوري. commit_cost_centers/strict: راجع
    finance.post_simple_revenue_journal — الافتراضي بيحافظ على السلوك
    القديم (بيبتلع الفشل)، والنداء الصارم (دفع طلب دايننج) بيرفع
    FinancialConfigurationError بدل ما يبتلع."""
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    outlet = crud.get_outlet(db, order.outlet_id)
    post_simple_revenue_journal(
        db, order.branch_id, local_today(settings.TIMEZONE),
        debit_account_code="1100", credit_account_code=revenue_account_code,
        amount=order.total or Decimal("0"),
        reference=f"ORD-{order.order_number}",
        description=f"إيرادات دايننج — {order.order_number}",
        source="dining", source_id=order.id,
        cost_center_code=_outlet_cost_center_code(outlet),
        commit_cost_centers=commit_cost_centers, strict=strict,
    )


def _post_order_folio_charge_journal(
    db: Session, order: DiningOrder, revenue_account_code: str,
    *, commit_cost_centers: bool = True, strict: bool = False,
) -> None:
    """Dr. ذمم الفوليو (1150) / Cr. إيراد المنفذ — طلب محمّل على فوليو
    غرفة. راجع restaurant.services._post_order_folio_charge_journal.
    commit_cost_centers/strict: نفس _post_order_revenue_journal بالظبط."""
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    outlet = crud.get_outlet(db, order.outlet_id)
    post_simple_revenue_journal(
        db, order.branch_id, local_today(settings.TIMEZONE),
        debit_account_code="1150", credit_account_code=revenue_account_code,
        amount=order.total or Decimal("0"),
        reference=f"ORD-{order.order_number}",
        description=f"إيرادات دايننج (محمّل على الغرفة) — {order.order_number}",
        source="dining_folio_charge", source_id=order.id,
        commit_cost_centers=commit_cost_centers, strict=strict,
        cost_center_code=_outlet_cost_center_code(outlet),
    )


def void_order_item(
    db: Session, order_id: int, item_id: int, reason: str, voided_by: int,
    acting_user_level: int = 100, approver_user_id: Optional[int] = None,
    approver_pin: Optional[str] = None,
) -> DiningOrder:
    """راجع restaurant.services.void_order_item — نفس المنطق بالظبط، بما
    فيه موافقة PIN عبر core.services.resolve_pin_approval (مفيش نظام
    موافقة موازي).

    Gate 4 (جولة مراجعة Codex الأولى): قفل الطلب + إعادة فحص الحالة تحت
    القفل — عشان إلغاء صنف مايتسابقش مع دفع نفس الطلب."""
    order = _lock_order_or_conflict(db, order_id)
    if order.status in ("paid", "cancelled"):
        raise ValueError(f"لا يمكن إلغاء صنف من طلب '{order.status}' — استخدم مرتجع بعد الدفع")

    item = crud.get_order_item(db, order_id, item_id)
    if not item:
        raise ValueError(f"الصنف {item_id} غير موجود في هذا الطلب")
    if item.status == "cancelled":
        raise ValueError("الصنف ده ملغي بالفعل")

    from app.modules.core import policy_engine  # noqa: PLC0415

    approved_by = policy_engine.require_approval(
        db, "void_order_item",
        acting_user_level=acting_user_level,
        approver_user_id=approver_user_id, approver_pin=approver_pin,
    )

    crud.void_order_item(db, item, reason, voided_by)
    policy_engine.record_policy_audit(
        db, "void_order_item",
        user_id=voided_by, approved_by=approved_by, branch_id=order.branch_id,
        entity_type="dining_order_item", entity_id=item.id,
        data={"reason": reason},
    )

    subtotal = Decimal("0")
    for i in order.items:
        if i.status == "cancelled":
            continue
        extras_total = sum((e.price_addition for e in i.extras), Decimal("0"))
        subtotal += (i.unit_price + extras_total) * i.quantity

    outlet = crud.get_outlet(db, order.outlet_id)
    vat_pct    = Decimal(str(settings.VAT_PERCENTAGE)) / Decimal("100")
    svc_pct    = _service_charge_pct(outlet, order.order_type)
    vat_amount = (subtotal * vat_pct).quantize(Decimal("0.01"))
    svc_charge = (subtotal * svc_pct).quantize(Decimal("0.01"))

    # راجع _resolve_order_discount — بيعيد حساب أفضل خصم (مجموعة العميل
    # الدائمة أو القاعدة الشرطية المطبّقة يدويًا لو موجودة) على subtotal
    # الجديد بعد الإلغاء، مش بس القاعدة الشرطية زي قبل كده (باج مشابه
    # لـ add_items_to_order كان ممكن يسيب خصم مجموعة العميل مجمّد على رقم
    # قديم بعد إلغاء صنف).
    discount_amount, applied_rule_id = _resolve_order_discount(db, order, subtotal)

    # order.delivery_fee رسم ثابت اتحدد وقت الإنشاء — بيفضل زي ما هو (نفس
    # منطق add_items_to_order بالظبط).
    total = max(Decimal("0"), subtotal + vat_amount + svc_charge + order.delivery_fee - discount_amount)

    order.subtotal                 = subtotal
    order.vat_amount               = vat_amount
    order.service_charge           = svc_charge
    order.discount_amount          = discount_amount
    order.applied_discount_rule_id = applied_rule_id
    order.total                    = total

    db.commit()
    db.refresh(order)
    return order


def transfer_order_table(db: Session, order_id: int, table_id: int) -> DiningOrder:
    """نقل طلب مفتوح من طاولة لأخرى — الضيوف اتحركوا فعليًا لطاولة تانية،
    والكاشير/النادل محتاج ينقل الطلب الجاري من غير ما يلغيه ويعمل واحد
    جديد. راجع restaurant.services.transfer_order_table — نفس المنطق
    بالظبط (الطاولة الجديدة لازم تكون في نفس الفرع، مش خارج الخدمة، ومش
    مشغولة بطلب مفتوح تاني).

    Gate 4 (جولة مراجعة Codex الأولى): قفل الطلب + قفل الطاولة الجديدة
    (blocking) + إعادة فحص الحالة تحت القفل — عشان نقل الطاولة مايتسابقش مع
    دفع الطلب، ولا مع نقل/فتح طلب تاني على نفس الطاولة الوجهة."""
    order = _lock_order_or_conflict(db, order_id)
    if order.status in ("paid", "cancelled"):
        raise ValueError(f"لا يمكن نقل طلب بحالة '{order.status}'")

    new_table = crud.get_table(db, table_id)
    if not new_table:
        raise ValueError(f"الطاولة {table_id} غير موجودة")
    if new_table.branch_id != order.branch_id:
        raise ValueError("الطاولة المطلوبة لا تنتمي لنفس فرع الطلب")
    if new_table.status == "out_of_service":
        raise ValueError(f"الطاولة {new_table.table_number} خارج الخدمة")
    if order.table_id == table_id:
        raise ValueError(f"الطلب بالفعل على الطاولة {new_table.table_number}")

    crud.lock_table_for_update(db, table_id)
    conflicting = crud.get_active_order_for_table(db, table_id, exclude_order_id=order.id)
    if conflicting:
        raise ValueError(f"الطاولة {new_table.table_number} مشغولة بطلب آخر ({conflicting.order_number})")

    old_table_id = order.table_id
    order.table_id = table_id
    crud.update_table_status(db, new_table, "occupied")
    if old_table_id and old_table_id != table_id:
        old_table = crud.get_table(db, old_table_id)
        if old_table:
            crud.update_table_status(db, old_table, "available")

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "uq_active_order_per_table" in str(getattr(exc, "orig", exc)):
            raise ValueError("الطاولة المطلوبة مشغولة بطلب نشط بالفعل (سباق نقل مزدوج)") from exc
        raise
    db.refresh(order)
    return order


def transfer_order_waiter(
    db: Session, order_id: int, new_waiter_id: int, changed_by: int, reason: str,
) -> DiningOrder:
    """M5 (جولة مراجعة Codex الأولى — الـ brief §2.6 بند 3): تغيير النادل
    المسند لطلب مفتوح. بيقفل الطلب ويعيد فحص حالته، بيتحقق إن النادل الجديد
    موجود، بيغيّر waiter_id (assigned waiter) بس **بيسيب created_by زي ما هو**
    (تاريخ المنشئ الأصلي مايتمسحش)، وبيكتب AuditLog(action="transfer_waiter").
    الطلبات المقفولة (paid/cancelled/refunded) مايتنقلش نادلها."""
    from app.core.kernel.models.user import User  # noqa: PLC0415
    from app.modules.core import policy_engine  # noqa: PLC0415

    order = _lock_order_or_conflict(db, order_id)
    if order.status in ("paid", "cancelled", "refunded"):
        raise ValueError(f"لا يمكن تغيير نادل طلب بحالة '{order.status}'")

    new_waiter = db.query(User).filter(User.id == new_waiter_id).first()
    if not new_waiter or not new_waiter.is_active:
        raise ValueError("النادل الجديد غير موجود أو غير نشط")
    if order.waiter_id == new_waiter_id:
        raise ValueError("الطلب مسند بالفعل لهذا النادل")

    old_waiter_id = order.waiter_id
    order.waiter_id = new_waiter_id  # created_by ثابت — التاريخ محفوظ

    policy_engine.record_policy_audit(
        db, "transfer_waiter",
        user_id=changed_by, approved_by=None, branch_id=order.branch_id,
        entity_type="dining_order", entity_id=order.id,
        data={
            "old_waiter_id": old_waiter_id,
            "new_waiter_id": new_waiter_id,
            "created_by": order.created_by,
            "reason": reason,
        },
    )

    db.commit()
    db.refresh(order)
    return order


def merge_orders(db: Session, source_id: int, target_id: int, merged_by: int) -> DiningOrder:
    """P-08 — دمج أوردرين مفتوحَين: ينقل كل أصناف source لـ target ثم يلغيه.
    الشرط: كلا الأوردرين في نفس الفرع، وكلاهما open/in_kitchen."""
    from app.modules.dining.models import DiningOrderItem  # noqa: PLC0415

    if source_id == target_id:
        raise ValueError("لا يمكن دمج أوردر مع نفسه")

    # Gate 4 (جولة مراجعة Codex الأولى): قفل الطلبين بترتيب حتمي (id تصاعدي)
    # عشان دمجان متزامنان بترتيب معكوس مايعملوش deadlock، وإعادة فحص حالتهما
    # تحت القفل قبل أي تعديل (عشان الدمج مايتسابقش مع دفع أي منهما).
    first_id, second_id = sorted((source_id, target_id))
    _lock_order_or_conflict(db, first_id)
    _lock_order_or_conflict(db, second_id)

    source = _get_order_or_404(db, source_id)
    target = _get_order_or_404(db, target_id)

    if source.branch_id != target.branch_id:
        raise ValueError("الأوردران في فرعَين مختلفَين")
    if source.status in ("paid", "cancelled"):
        raise ValueError(f"لا يمكن دمج أوردر بحالة '{source.status}'")
    if target.status in ("paid", "cancelled"):
        raise ValueError(f"لا يمكن الدمج في أوردر بحالة '{target.status}'")

    # نقل الأصناف
    db.query(DiningOrderItem).filter(
        DiningOrderItem.order_id == source_id
    ).update({"order_id": target_id})

    # تحديث total الهدف
    target.total = (target.total or 0) + (source.total or 0)

    # تحرير طاولة الـ source لو اتفرّغت
    if source.table_id:
        src_table = crud.get_table(db, source.table_id)
        if src_table:
            crud.update_table_status(db, src_table, "available")

    # إلغاء الـ source
    source.status = "cancelled"
    source.notes = (source.notes or "") + f" | مدموج في #{target.order_number} بواسطة user#{merged_by}"

    db.commit()
    db.refresh(target)
    return target


def split_bill(
    db: Session,
    order_id: int,
    payments: list[dict],
    settled_by: Optional[int] = None,
    acting_user_level: int = 100,
    idempotency_key: Optional[str] = None,
) -> DiningOrder:
    """P-07 — تقسيم الفاتورة على أكثر من طريقة دفع (Gate 4A: بقى وحدة عمل
    صارمة كاملة عبر settle_order، مش مسار موازٍ). كل payment له amount +
    payment_method + charge_to_room_id (اختياري). المجموع لازم يساوي
    order.total بدقة Decimal. كل tender مباشر بيتعمله Payment منسوب للكاشير/
    الوردية، وكل tender غرفة بيتعمله شحنة فوليو متناسبة — الاتنين في نفس
    المعاملة الذرّية بتاعة settle_order مع idempotency guard."""
    tenders = [
        {
            "method": p["payment_method"],
            "amount": Decimal(str(p["amount"])),
            "charge_to_room_id": p.get("charge_to_room_id"),
        }
        for p in payments
    ]
    return settle_order(
        db, order_id, tenders=tenders, settled_by=settled_by,
        acting_user_level=acting_user_level, idempotency_key=idempotency_key,
    )


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


def _customer_group_discount_amount(db: Session, customer_id: Optional[int], subtotal: Decimal) -> Decimal:
    """خصم مجموعة العميل الدائم (crm.CustomerGroup.discount_percentage) على
    الـ subtotal — صفر لو مفيش عميل مرتبط أو مجموعته موقوفة/غير موجودة.
    راجع crm.services.get_customer_group_discount_percentage للمنطق الكامل."""
    from app.modules.crm.services import get_customer_group_discount_percentage  # noqa: PLC0415

    pct = get_customer_group_discount_percentage(db, customer_id)
    if pct <= 0:
        return Decimal("0")
    return (subtotal * pct / Decimal("100")).quantize(Decimal("0.01"))


def _resolve_order_discount(db: Session, order: DiningOrder, subtotal: Decimal) -> tuple[Decimal, Optional[int]]:
    """أفضل خصم للطلب على الـ subtotal الحالي — بيقارن بين نوعين مختلفين
    تمامًا ومستقلين عن بعض: (أ) خصم مجموعة العميل الدائم (تلقائي، بلا أي
    إجراء يدوي — _customer_group_discount_amount فوق) و(ب) قاعدة خصم شرطية
    (happy hour/بروموشن) اتطبّقت يدويًا من قبل على الطلب ده (لو موجودة،
    بإعادة حسابها على subtotal الجديد عبر _recompute_discount_for_rule).

    **قرار سياسة تجارية (Batch 2، customer groups)**: الاتنين ميتجمعوش
    (لا stacking) — الأعلى قيمة بس هو اللي يتطبّق فعليًا، نفس فلسفة "أفضل
    عرض للضيف الواحد" المتّبعة في discount_engine.calculate_discount نفسها
    (بتاخد أعلى priority بين القواعد الشرطية، مش تجمعهم). لو الفايز خصم
    المجموعة، بيرجّع rule_id=None — يعني القاعدة الشرطية (لو كانت مطبّقة)
    بتتنحّى بدون ما تُحسب مستخدمة (uses_count متتزودش)، لأنها فعليًا ملهاش
    أثر على المبلغ النهائي في اللحظة دي."""
    group_amount = _customer_group_discount_amount(db, order.customer_id, subtotal)

    rule_amount, rule_id = Decimal("0"), None
    if order.applied_discount_rule_id:
        rule_amount, rule_id = _recompute_discount_for_rule(db, order.applied_discount_rule_id, subtotal, order)

    if rule_amount >= group_amount:
        return rule_amount, rule_id
    return group_amount, None


def refund_order_item(db: Session, order_id: int, item_id: int, reason: str, refunded_by: int) -> DiningOrder:
    """راجع restaurant.services.refund_order_item — نفس المنطق الأساسي، مع
    إصلاح باج محاسبي حقيقي حول تناسب الخصم (راجع تعليق item_gross تحت).

    Gate 4C: بيقفل صف الطلب (get_order_for_update NOWAIT) ويعيد فحص حالة
    الصنف تحت القفل — مرتجعان متزامنان لنفس الصنف: واحد بس ينجح، والتاني
    يترفض (409 مشغول أو 'مرتجع بالفعل')، فمفيش عكس مالي مكرر. commit واحد،
    وأي فشل بيعمل rollback كامل."""
    try:
        order = _lock_order_or_conflict(db, order_id)
        return _refund_order_item_locked(db, order, order_id, item_id, reason, refunded_by)
    except Exception:
        db.rollback()
        raise


def _refund_order_item_locked(
    db: Session, order: DiningOrder, order_id: int, item_id: int, reason: str, refunded_by: int,
) -> DiningOrder:
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
    # ⚠️ باج محاسبي حقيقي اتصلح: كان بيحسب refund_amount = item_gross + نصيب
    # الـ VAT/service_charge بس — من غير أي نصيب من order.discount_amount.
    # القيد الأصلي وقت الدفع بيرحّل order.total (صافي بعد الخصم —
    # _post_order_revenue_journal)، فمرتجع صنف واحد من طلب عليه خصم كان بيعكس
    # إيراد أكتر مما اترحّل فعليًا لنفس الصنف ده، وبيسيب باقي الطلب بقيمة أقل
    # من الصح في دفتر الأستاذ (ولنفس السبب في رصيد شحنة الفوليو). النصيب من
    # الخصم لازم يتناسب بنفس share_ratio (الخصم بيتحسب على subtotal زي الـ
    # VAT/service_charge بالظبط)، عشان مجموع مرتجعات كل الأصناف يرجع بالظبط
    # لـ order.total الأصلي.
    refund_discount = (order.discount_amount * share_ratio).quantize(Decimal("0.01")) if order.discount_amount else Decimal("0")
    refund_amount = max(Decimal("0"), item_gross - refund_discount + refund_vat + refund_svc)

    crud.refund_order_item(db, item, reason, refunded_by)
    order.refunded_amount = (order.refunded_amount or Decimal("0")) + refund_amount

    active_items = [i for i in order.items if i.status not in ("cancelled", "refunded")]
    if not active_items:
        order.status = "refunded"
        # M4 (جولة مراجعة Codex الأولى): طلب اترجّع بالكامل بيحرّر الطاولة —
        # قبل كده كانت تفضل "مشغولة" للأبد (نفس منطق cancel/paid). الحالة
        # "refunded" خارج مجموعة الطلب النشط، فمفيش طلب فعلي بيحجز الطاولة.
        if order.table_id:
            table = crud.get_table(db, order.table_id)
            if table:
                crud.update_table_status(db, table, "available")

    outlet = crud.get_outlet(db, order.outlet_id)
    revenue_account = outlet.revenue_account_code if outlet else "4200"
    # Gate 4 (جولة مراجعة Codex الأولى — High 3/4): العكس بيتقاد بالـ tenders
    # الأصلية الفعلية (مش boolean folio_id)، ولكل جزء بحسابه الصح، وfail-closed.
    _post_refund_reversals(db, order, refund_amount, revenue_account, refunded_by)

    db.commit()
    db.refresh(order)
    return order


def _post_refund_reversals(
    db: Session, order: DiningOrder, refund_amount: Decimal,
    revenue_account_code: str, refunded_by: int,
) -> None:
    """يعكس مرتجع صنف بالتناسب على *كل* الـ tenders الأصلية اللي حصّلت الطلب
    (Gate 4، جولة مراجعة Codex الأولى — High 3/4).

    الباج القديم (High 3): كان بيفرّع على ``order.folio_id`` boolean بس —
    طلب split (كاش + غرفة) folio_id بتاعه set لأن *جزء* اتحمّل على الغرفة،
    فكان بياخد مسار "عكس فوليو" لوحده ويسيب حصة الكاش المباشرة من غير أي عكس
    خالص (positive_direct_total بيفضل زي ما هو). دلوقتي العكس بيتوزّع بالتناسب
    على كل tender أصلي حسب حصته من order.total:
      • كل tender مباشر (Payment موجب) → Payment عكسي سالب بحصته + قيد Dr
        إيراد / Cr *حساب الطريقة الأصلي نفسه* (cash→1100، card/wallet→حساب
        المقاصّة المهيّأ عبر resolve_direct_tender_account، مش 1100 ثابت — High 4b).
      • حصة الغرفة (order.total - مجموع المباشر، لو الطلب عليه فوليو) → تقليل
        شحنة الفوليو + قيد Dr إيراد / Cr 1150.

    كله fail-closed (High 4a): أي فشل محاسبي بيرفع استثناء → refund_order_item
    بيعمل rollback كامل (حالة الطلب/الصنف + كل صفوف العكس)، مش يبتلع بصمت."""
    from app.modules.dining.payment_policy import resolve_direct_tender_account  # noqa: PLC0415
    from app.modules.finance import crud as finance_crud  # noqa: PLC0415
    from app.modules.finance import services as finance_services  # noqa: PLC0415

    order_total = order.total or Decimal("0")
    if order_total <= 0 or refund_amount <= 0:
        return

    direct_payments = [
        p for p in finance_crud.list_direct_payments_for_order(db, order.id)
        if p.voided_at is None and p.amount > 0
    ]
    direct_total = sum((p.amount for p in direct_payments), Decimal("0"))

    # بنود التوزيع بترتيب حتمي: المباشرة الأول (كل دفعة بند)، والغرفة آخر بند
    # عشان الباقي (rounding remainder) يقع على حصة الغرفة.
    parts: list[tuple[str, Decimal, object]] = [("direct", p.amount, p) for p in direct_payments]
    if order.folio_id:
        room_total = max(Decimal("0"), order_total - direct_total)
        if room_total > 0:
            parts.append(("room", room_total, None))
    if not parts:
        return

    shift_id = None
    if any(kind == "direct" for kind, _, _ in parts):
        open_shift = finance_services._lock_open_shift_or_conflict(db, order.branch_id, refunded_by)
        if not open_shift:
            # Gate 4 review (2026-07-21, finding N1): refund_order_item is
            # manager-gated (min_role_level=60) — refunded_by is almost
            # always a manager approving the refund, not a cashier running a
            # drawer, so they rarely have an open shift of their own. Without
            # this fallback the reversed cash Payment gets shift_id=None and
            # never reduces any shift's expected_cash in build_shift_end_
            # report, even though the cash physically left a real drawer.
            # Only resolve this when exactly one shift is open at the branch
            # (the unambiguous case — that's the drawer the cash came from);
            # zero or multiple open shifts stay unattributed rather than
            # guess which cashier's drawer to charge.
            open_shifts, _ = finance_crud.list_shifts(db, order.branch_id, status="open", limit=2)
            if len(open_shifts) == 1:
                open_shift = finance_services._lock_open_shift_or_conflict(
                    db, order.branch_id, open_shifts[0].cashier_id,
                )
        if open_shift:
            shift_id = open_shift.id

    cost_center_code = _outlet_cost_center_code(crud.get_outlet(db, order.outlet_id))
    allocated = Decimal("0")
    last_idx = len(parts) - 1
    for idx, (kind, amount, payment) in enumerate(parts):
        if idx == last_idx:
            share = refund_amount - allocated
        else:
            share = (refund_amount * amount / order_total).quantize(Decimal("0.01"))
            allocated += share
        if share <= 0:
            continue
        if kind == "direct":
            # حساب الطريقة الأصلي نفسه — cash→1100، card/wallet→حساب المقاصّة
            # المهيّأ. لو الطريقة اتشالت تهيئتها بعد البيع، fail-closed (503).
            account = resolve_direct_tender_account(payment.method)
            finance_crud.create_direct_payment(
                db, branch_id=order.branch_id, amount=-share, method=payment.method,
                posted_at=datetime.utcnow(), shift_id=shift_id, cashier_id=refunded_by,
                reference=f"ORD-REFUND-{order.order_number}", ref_order_id=order.id,
                source="dining_refund", original_payment_id=payment.id,
            )
            finance_services.post_simple_revenue_journal(
                db, order.branch_id, local_today(settings.TIMEZONE),
                debit_account_code=revenue_account_code, credit_account_code=account,
                amount=share, reference=f"ORD-REFUND-{order.order_number}",
                description=f"مرتجع بعد الدفع ({payment.method}) — {order.order_number}",
                source="dining_refund", source_id=order.id,
                cost_center_code=cost_center_code,
                commit_cost_centers=False, strict=True,
            )
        else:  # room
            _reduce_folio_charge_for_refund(db, order, share, revenue_account_code)


def _reduce_folio_charge_for_refund(db: Session, order: DiningOrder, refund_amount: Decimal, revenue_account_code: str) -> None:
    """يقلّل شحنة فوليو الطلب بحصة الغرفة من المرتجع + قيد عكسي Dr إيراد / Cr
    1150. Gate 4 (High 4a): fail-closed — لو الشحنة مش موجودة أو الفوليو
    مقفول/مفقود، بيرفع ValueError بدل ما يبتلع الفشل بعد logging (اللي كان
    بيسيب الطلب 'refunded' من غير عكس محاسبي مقابل — أثر جزئي متناقض).

    بيفلتر charge_type + folio_id (منع تلبيس على شحنة outlet تاني في نفس
    الفوليو، نفس الباج اللي اتصلح في المصدر الأصلي)."""
    from app.modules.finance import crud as finance_crud  # noqa: PLC0415
    from app.modules.finance.models import FolioCharge  # noqa: PLC0415

    charge = (
        db.query(FolioCharge)
        .filter_by(ref_order_id=order.id, folio_id=order.folio_id, charge_type="dining")
        .first()
    )
    if not charge:
        raise ValueError(
            f"مفيش شحنة فوليو مطابقة للطلب {order.order_number} — لا يمكن عكس حصة الغرفة من المرتجع"
        )
    folio = finance_crud.get_folio(db, order.folio_id)
    if not folio:
        raise ValueError("الفوليو المرتبط بالطلب غير موجود — لا يمكن عكس المرتجع")
    if folio.status == "closed":
        raise ValueError(
            "الفوليو مقفول (تم checkout الضيف) — مينفعش عكس مرتجع الغرفة تلقائيًا، محتاج تسوية محاسبية يدوية"
        )
    gross_before = charge.amount + charge.vat_amount + charge.service_charge
    new_gross = max(Decimal("0"), gross_before - refund_amount)
    ratio = (new_gross / gross_before) if gross_before > 0 else Decimal("0")
    charge.amount = (charge.amount * ratio).quantize(Decimal("0.01"))
    charge.vat_amount = (charge.vat_amount * ratio).quantize(Decimal("0.01"))
    charge.service_charge = (charge.service_charge * ratio).quantize(Decimal("0.01"))
    db.flush()
    finance_crud.recalculate_folio_total(db, folio)
    _post_order_folio_refund_reversal_journal(db, order, refund_amount, revenue_account_code)


def _post_order_folio_refund_reversal_journal(db: Session, order: DiningOrder, refund_amount: Decimal, revenue_account_code: str) -> None:
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    outlet = crud.get_outlet(db, order.outlet_id)
    # Gate 4 (High 4a): strict=True — فشل ترحيل القيد بيرفع بدل ما يرجّع None
    # بصمت، عشان عكس شحنة الفوليو والقيد المقابل يفشلوا كوحدة واحدة.
    post_simple_revenue_journal(
        db, order.branch_id, local_today(settings.TIMEZONE),
        debit_account_code=revenue_account_code, credit_account_code="1150",
        amount=refund_amount,
        reference=f"ORD-REFUND-{order.order_number}",
        description=f"مرتجع بعد الدفع (محمّل على الغرفة) — {order.order_number}",
        source="dining_folio_refund", source_id=order.id,
        cost_center_code=_outlet_cost_center_code(outlet),
        commit_cost_centers=False, strict=True,
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


def apply_order_discount(
    db: Session, order_id: int, applied_by: Optional[int] = None,
    acting_user_level: int = 100, approver_user_id: Optional[int] = None,
    approver_pin: Optional[str] = None,
) -> DiningOrder:
    """راجع restaurant.services.apply_order_discount — نفس المنطق بالظبط،
    بس outlet=outlet.outlet_type ديناميكي بدل نص ثابت "restaurant"/"cafe"،
    فقواعد scope_type="outlet" تفرّق فعليًا بين أي عدد من الـ outlets.

    قرار Mohamed (2026-07-13): الكاشير صفر صلاحية خصم خالص — أي محاولة
    تطبيق خصم من مستوى أقل من مدير (level < 60) محتاجة موافقة PIN مدير/
    محاسب حاضر فعليًا، عبر core.services.resolve_pin_approval بالظبط زي
    void_order_item، بغض النظر عن نتيجة قاعدة الخصم (حتى لو مفيش قاعدة
    سارية أصلاً والنتيجة صفر — الموافقة على *محاولة* التطبيق نفسها).

    Gate 4 (جولة مراجعة Codex الأولى): قفل الطلب + إعادة فحص الحالة تحت
    القفل — عشان تطبيق الخصم مايتسابقش مع دفع نفس الطلب."""
    order = _lock_order_or_conflict(db, order_id)

    if order.status in ("paid", "cancelled"):
        raise ValueError("لا يمكن تطبيق خصم على طلب مغلق")

    from app.modules.core import policy_engine  # noqa: PLC0415

    approved_by = policy_engine.require_approval(
        db, "apply_order_discount",
        acting_user_level=acting_user_level,
        approver_user_id=approver_user_id, approver_pin=approver_pin,
    )

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

    # الأفضل للضيف يفوز — مش تراكم (راجع _resolve_order_discount للتبرير
    # الكامل). لو خصم مجموعة العميل الدائم أكبر من القاعدة الشرطية المُقيَّمة
    # هنا، هو اللي بيتطبّق فعليًا بدل نتيجة الزرار، وrule_id بيتسجّل None
    # (القاعدة الشرطية معدتش "استخدمت" فعليًا في اللحظة دي).
    group_amount = _customer_group_discount_amount(db, order.customer_id, order.subtotal)
    conditional_wins = result.amount_saved >= group_amount
    final_amount = result.amount_saved if conditional_wins else group_amount
    final_rule_id = result.rule_id if conditional_wins else None

    order = crud.update_order_discount(
        db, order,
        discount_amount=final_amount,
        rule_id=final_rule_id,
    )

    policy_engine.record_policy_audit(
        db, "apply_discount",
        user_id=applied_by, approved_by=approved_by, branch_id=order.branch_id,
        entity_type="dining_order", entity_id=order.id,
        data={
            "applied": result.applied,
            "conditional_discount_amount": str(result.amount_saved),
            "conditional_rule_id": result.rule_id,
            "customer_group_discount_amount": str(group_amount),
            "final_discount_amount": str(final_amount),
            "final_rule_id": final_rule_id,
        },
    )

    if conditional_wins and result.applied and result.rule_id:
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
