"""
app/modules/dining/_services/_helpers.py
Extracted from app/modules/dining/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from datetime import time
from decimal import Decimal
from typing import Optional
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.db_errors import is_lock_not_available
from app.modules.dining import crud
from app.modules.dining.models import DiningItem, DiningItemVariant, DiningOrder, Outlet
from app.resort_os.dining_pricing import snapshot_price_component
from app.modules.dining._services._exceptions import (
    OrderPaymentConcurrencyError,
)


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


def _service_charge_pct(db: Session, outlet: Optional[Outlet], order_type: str = "dine_in") -> Decimal:
    """نسبة رسم الخدمة الفعلية للمنفذ + قناة الطلب — override بتاع القناة
    (takeaway/delivery/room_service) لو موجود، وإلا override عام للمنفذ لو
    موجود، وإلا إعداد service_charge_percentage الفعلي (شاشة الإعدادات →
    core.services.get_effective_service_charge_percentage، مش env ثابت).

    2026-07-16 (بحث مقارنة Click القديم): Click كان بيفرّق فعليًا في
    التسعير حسب القناة — عادة takeaway/delivery من غير رسم خدمة (مفيش
    خدمة طاولة فعلية) وroom_service أحيانًا أعلى. **القيم دي كلها NULL
    افتراضيًا** — صفر تغيير سلوك على أي منفذ موجود لحد ما مدير يفعّلها
    صراحةً من إعدادات المنفذ (قرار تسعير حي يستاهل موافقة Mohamed، مش
    افتراض تلقائي).

    2026-08-03: كان بيقرأ settings.SERVICE_CHARGE_PERCENTAGE (env) مباشرة
    كـfallback أخير — تعديل مدير للنسبة من شاشة الإعدادات مالوش أي أثر
    فعلي. راجع core.services._effective_percentage_setting للتفاصيل."""
    if outlet is not None:
        override_attr = _ORDER_TYPE_SVC_OVERRIDE_ATTR.get(order_type)
        if override_attr is not None:
            override = getattr(outlet, override_attr, None)
            if override is not None:
                return override / Decimal("100")
        if outlet.default_service_charge_pct is not None:
            return outlet.default_service_charge_pct / Decimal("100")

    from app.modules.core.services import get_effective_service_charge_percentage  # noqa: PLC0415
    branch_id = outlet.branch_id if outlet is not None else None
    return get_effective_service_charge_percentage(db, branch_id) / Decimal("100")


def _order_price_components(order: DiningOrder) -> tuple[Decimal, Decimal, Decimal]:
    """Aggregate active order snapshots by legacy-vs-final price contract."""
    subtotal = Decimal("0")
    exclusive_subtotal = Decimal("0")
    listed_gross_total = Decimal("0")
    for item in order.items:
        if item.status in ("cancelled", "refunded"):
            continue
        quantity = Decimal(item.quantity)
        base_net = item.unit_price * quantity
        subtotal += base_net
        if item.listed_unit_price is None:
            exclusive_subtotal += base_net
        else:
            listed_gross_total += item.listed_unit_price * quantity
        for extra in item.extras:
            extra_net = extra.price_addition * quantity
            subtotal += extra_net
            if extra.listed_price_addition is None:
                exclusive_subtotal += extra_net
            else:
                listed_gross_total += extra.listed_price_addition * quantity
    return subtotal, exclusive_subtotal, listed_gross_total


def _snapshot_selected_extras(
    extras_data: list[dict],
    *,
    is_final_price: bool,
    vat_pct: Decimal,
    service_pct: Decimal,
) -> tuple[list[dict], Decimal, Decimal, Decimal]:
    """Convert selected modifier prices to accounting snapshots."""
    net_total = Decimal("0")
    exclusive_total = Decimal("0")
    listed_total = Decimal("0")
    for extra in extras_data:
        net_price, listed_price = snapshot_price_component(
            extra["price_addition"],
            is_final_price=is_final_price,
            vat_pct=vat_pct,
            service_pct=service_pct,
        )
        extra["price_addition"] = net_price
        extra["listed_price_addition"] = listed_price
        net_total += net_price
        if listed_price is None:
            exclusive_total += net_price
        else:
            listed_total += listed_price
    return extras_data, net_total, exclusive_total, listed_total


# مركز التكلفة (finance.CostCenter.code — Batch 3) المقابل لـ outlet_type —
# مبني على نفس ROOM/REST/CAFE/BEACH/TS اللي finance.services.DEFAULT_COST_CENTERS
# بتستخدمها كمصدر حقيقة وحيد. outlet_type غير معروف (مش "restaurant"/"cafe")
# → None عمدًا (مفيش مركز تكلفة رابع/خامس مخترع هنا، نفس الـ 5 الموجودين بس).
_OUTLET_TYPE_TO_COST_CENTER = {"restaurant": "REST", "cafe": "CAFE"}


def _outlet_cost_center_code(outlet: Optional[Outlet]) -> Optional[str]:
    if outlet is None:
        return None
    return _OUTLET_TYPE_TO_COST_CENTER.get(outlet.outlet_type)


def _build_outlet_revenue_splits(
    db: Session, order: "DiningOrder", fallback_outlet_id: int
) -> list[tuple["Outlet", Decimal]]:
    """يحسب توزيع الإيراد per-outlet من أصناف الطلب.

    لكل صنف نشيط (غير ملغي/مردود)، نجمع unit_price*quantity حسب outlet_id
    الصنف (DiningOrderItem.outlet_id) — إذا كان NULL أو الـ outlet غير موجود
    نرجع لـ order.outlet_id (التوافق مع القديم).

    يرجع list of (outlet, subtotal_share) — الـ subtotal_share بدون VAT/SVC
    (بيتحسب للإيراد الصافي فقط). VAT/SVC والخصم بيتوزّعوا نسبياً وقت تسجيل
    القيد في `_settle_direct_tender` و`_settle_room_tender`.

    لو كل الأصناف من نفس الـ outlet — يرجع list بعنصر واحد (المسار العادي).
    """
    from collections import defaultdict  # noqa: PLC0415

    # جمع subtotal per outlet_id (الأصناف النشطة فقط)
    outlet_subtotals: dict[int, Decimal] = defaultdict(Decimal)
    for item in order.items:
        if item.status in ("cancelled", "refunded"):
            continue
        effective_outlet_id = item.outlet_id if item.outlet_id else fallback_outlet_id
        line_total = item.unit_price * item.quantity
        outlet_subtotals[effective_outlet_id] += line_total

    if not outlet_subtotals:
        # لو مفيش أصناف نشطة — رجّع الـ outlet الأصلي بالمجموع الكامل
        fallback = crud.get_outlet(db, fallback_outlet_id)
        return [(fallback, order.subtotal or Decimal("0"))] if fallback else []

    result = []
    for oid, sub in outlet_subtotals.items():
        outlet = crud.get_outlet(db, oid)
        if outlet:
            result.append((outlet, sub))
        else:
            # outlet محذوف — رجّع للـ fallback
            fallback = crud.get_outlet(db, fallback_outlet_id)
            if fallback:
                result.append((fallback, sub))

    return result


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
                "extra_name_ar":  group.name_ar,
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
                "extra_name_ar":  opt.name_ar,
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
    # قرار موثّق: local_now بتتقرا هنا عبر الواجهة (services.py) مش استيراد
    # مباشر — تستات test_dining.py بتعمل patch("app.modules.dining.services.
    # local_now") صراحةً، ولازم الاستدعاء الفعلي يشوف النسخة المبدّلة دي.
    from app.modules.dining import services as _dining_services  # noqa: PLC0415
    now_time = _dining_services.local_now(settings.TIMEZONE).time()
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
