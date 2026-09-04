"""app/modules/beach/services.py — Business logic"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.beach import crud
from app.modules.beach.models import BeachInventory, BeachLocation, BeachTransaction
from app.modules.beach.schemas import (
    B2BCheckinRequest, BeachCartSellRequest, BeachLocationCheckinRequest,
    BeachReservationCreate, BeachSellRequest,
)
from app.resort_os.beach_engine import (
    BEACH_CAPACITY_SETTING_KEY,
    DEFAULT_BEACH_CAPACITY_MAX,
    B2BContractState,
    BeachInventoryState,
    calculate_inventory_delta,
    calculate_tx_price,
    is_contract_overdue,
    parse_beach_capacity_max,
    validate_b2b_checkin,
    validate_entry,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.modules.beach.models import B2BContract, B2BContractDay, BeachReservation


def _business_today() -> date:
    """تاريخ "النهاردة" بتوقيت المنتجع (settings.TIMEZONE)، مش توقيت نظام
    تشغيل السيرفر — راجع app.resort_os.timezone_utils.local_today للتفاصيل
    (نفس فئة الباج اللي اتكشفت واتصلحت قبل كده في HR/PMS/Timeshare: حدود
    اليوم — إعادة ضبط سعة الشاطئ، تصفير حصة B2B، تقرير نهاية اليوم — كانت
    بتتزاح بفرق التوقيت UTC↔Africa/Cairo لحد 3 ساعات كل يوم). Import محلي
    (مش أعلى الملف) عشان التستات تقدر تعمل monkeypatch على
    `app.resort_os.timezone_utils.local_today` مباشرة، زي نفس الباترن
    المستخدم في pms.services بالظبط."""
    from app.resort_os.timezone_utils import local_today  # noqa: PLC0415

    return local_today(settings.TIMEZONE)


def _configured_capacity_max(db: Session, branch_id: int) -> tuple[int, bool]:
    """Return (capacity, explicitly_configured).

    ``False`` preserves an existing daily row created with an intentional
    one-off capacity when neither a branch nor global setting exists.  New
    rows still use the safe 200-person fallback.
    """
    from app.modules.core.services import get_setting_value  # noqa: PLC0415

    raw = get_setting_value(db, BEACH_CAPACITY_SETTING_KEY, branch_id, default=None)
    if raw is None:
        return DEFAULT_BEACH_CAPACITY_MAX, False
    try:
        return parse_beach_capacity_max(raw), True
    except ValueError:
        logger.error(
            "Invalid %s setting for branch_id=%s; using safe fallback %s",
            BEACH_CAPACITY_SETTING_KEY,
            branch_id,
            DEFAULT_BEACH_CAPACITY_MAX,
        )
        return DEFAULT_BEACH_CAPACITY_MAX, True


def get_configured_capacity_max(db: Session, branch_id: int) -> int:
    """Effective maximum used when a new BeachInventory day is created."""
    return _configured_capacity_max(db, branch_id)[0]


def get_inventory(db: Session, branch_id: int, inv_date: Optional[date] = None) -> BeachInventory:
    """Get/create a daily row and apply today's configured capacity.

    Past rows remain immutable snapshots.  A setting change takes effect on
    today's existing row on its next read/sale, while the following day is
    created from the same branch-aware setting instead of a hard-coded 200.
    """
    inv_date = inv_date or _business_today()
    configured_max, explicitly_configured = _configured_capacity_max(db, branch_id)
    row = crud.get_inventory(db, branch_id, inv_date)
    if row is None:
        return crud.get_or_create_inventory(
            db, branch_id, inv_date, capacity_max=configured_max,
        )
    if (
        explicitly_configured
        and inv_date == _business_today()
        and row.capacity_max != configured_max
    ):
        row.capacity_max = configured_max
        db.flush()
    return row


class BeachConcurrencyError(Exception):
    """عملية بيع/تشيك-إن تانية ماسكة صف سعة الشاطئ لنفس الفرع/اليوم دلوقتي، أو
    موقع فعلي (BeachLocation) مشغول بالفعل/بيتسجّل دخوله دلوقتي — 409، مش 400
    (زي pms.services.BookingConflictError بالظبط: بيغطّي الحالتين "القفل نفسه
    مشغول" و"الحالة التجارية بتاعت المصدر متعارضة" تحت نفس الاستثناء/الكود)."""


class NoOpenShiftError(Exception):
    """محاولة تحصيل tender مباشر (كاش/بطاقة/محفظة) من غير وردية مفتوحة لنفس
    الكاشير والفرع — 409 NO_OPEN_SHIFT، نفس اتفاقية dining.services تمامًا
    (نفس error_code، نفس السلوك الأمامي في POSPaymentModal.vue). الدفع
    المباشر لازم يُنسب لوردية مفتوحة عشان يظهر في تقرير الوردية ومطابقة
    الكاش؛ من غيرها الكاش المحصّل هيبقى غير منسوب (orphaned)."""


def _lock_inventory_or_raise(db: Session, inv_row: BeachInventory) -> BeachInventory:
    """يقفل صف BeachInventory (SELECT FOR UPDATE NOWAIT) قبل أي تحقق/تعديل
    على السعة — بيمنع سباق كلاسيكي بين قراءة capacity_used والـ UPDATE لو
    عمليتين بيع حصلوا في نفس اللحظة بالظبط (زي double-booking للغرف، بس هنا
    للسعة اليومية للشاطئ). ⚠️ باج حقيقي كان هنا: كل عمليات البيع/التشيك-إن
    كانت بتقرا وتعدّل capacity_used/towels_used من غير أي قفل صف خالص — عكس
    غرف الفندق (pms.crud.lock_room_for_booking) اللي القفل ده متطبّق فيها من
    زمان. تحت حمل متزامن حقيقي (كذا كاشير/تابلت شاطئ بيبيعوا في نفس الثانية
    وقت السعة قريبة من الحد)، العملية الثانية كانت ممكن تعدّي validate_entry
    بقيمة قديمة وتتسبب في تجاوز السعة الفعلية (oversell)."""
    try:
        locked = crud.lock_inventory_for_update(db, inv_row.id)
    except OperationalError as exc:
        db.rollback()
        raise BeachConcurrencyError(
            "سعة الشاطئ مشغولة الآن بعملية بيع أخرى — حاول تاني خلال لحظات"
        ) from exc
    return locked or inv_row


def _lock_contract_day_or_raise(db: Session, day_row: "B2BContractDay") -> "B2BContractDay":
    """يقفل صف B2BContractDay (SELECT FOR UPDATE NOWAIT) قبل قراءة/تعديل
    checked_in_count — نفس فئة الباج بتاعة _lock_inventory_or_raise فوق: لو
    عمليتين تشيك-إن B2B حصلوا في نفس اللحظة بالظبط لنفس العقد/اليوم، كل واحدة
    كانت بتقرا checked_in_today قديم وتعدّي validate_b2b_checkin حتى لو مجموع
    الاتنين هيتخطى الحصة اليومية فعليًا (oversell على حصة الفندق الشريك)."""
    try:
        locked = crud.lock_contract_day_for_update(db, day_row.id)
    except OperationalError as exc:
        db.rollback()
        raise BeachConcurrencyError(
            "حصة B2B مشغولة الآن بعملية تشيك-إن أخرى — حاول تاني خلال لحظات"
        ) from exc
    return locked or day_row


def _lock_location_or_raise(db: Session, location: BeachLocation) -> BeachLocation:
    """يقفل صف BeachLocation (SELECT FOR UPDATE NOWAIT) قبل أي تحقق/تعديل على
    حالته — بيمنع سباق double check-in كلاسيكي لو كاشيرين مختلفين ضغطوا
    "تشيك-إن" على نفس الموقع الفعلي في نفس اللحظة بالظبط. نفس فئة
    _lock_inventory_or_raise/_lock_contract_day_or_raise بالظبط."""
    try:
        locked = crud.lock_location_for_update(db, location.id)
    except OperationalError as exc:
        db.rollback()
        raise BeachConcurrencyError(
            "الموقع مشغول الآن بعملية تشيك-إن أخرى — حاول تاني خلال لحظات"
        ) from exc
    return locked or location


def _get_base_prices(db: Session, branch_id: int) -> dict[str, Decimal]:
    """يجلب الأسعار من Settings في DB (adult/child/resident + towel).

    ⚠️ باج حقيقي كان هنا (اتكشف واتصلح 2026-07-03 أثناء كتابة تست لباج تاني):
    `get_setting()` بيرجّع صف `Setting` كامل (ORM object)، مش الـ string value —
    الكود القديم كان بيعمل `Decimal(get_setting(...) or "200")` يعني بيحاول
    يبني Decimal من الـ object نفسه مباشرة، وده كان بيرمي استثناء دايمًا لما
    فيه إعداد فعلي محفوظ (كان بيشتغل بالغلط بس لما مفيش إعداد خالص، لأن
    `None or "200"` بترجع "200" ويعدي عادي) — الـ `except Exception` كان بيبلع
    الاستثناء ده بصمت ويرجّع نفس القيم الافتراضية الجاهزة. النتيجة: أي سعر
    شاطئ مخصّص يتظبط من شاشة الإعدادات كان بيتجاهل بالكامل، والبيع الفعلي
    (`/beach/sell`) كان دايمًا بيستخدم الأسعار الافتراضية الجاهزة (200/100/
    150/50) بغض النظر عن أي تعديل حقيقي في الإعدادات."""
    try:
        from app.modules.core.crud import get_setting  # noqa: PLC0415

        def _price(key: str, default: str) -> Decimal:
            row = get_setting(db, key, branch_id=branch_id)
            return Decimal(row.value if row is not None else default)

        adult    = _price("beach.price.adult",    "200")
        child    = _price("beach.price.child",    "100")
        resident = _price("beach.price.resident", "150")
        towel    = _price("beach.price.towel",    "50")
        service  = _price("beach.price.outside_food_fee", "50")
        return {
            "entry":            adult,
            "entry_child":      child,
            "entry_resident":   resident,
            "entry_towel":      adult + towel,
            "towel_rent":       towel,
            "outside_food_fee": service,
        }
    except Exception:
        return {
            "entry":            Decimal("200"),
            "entry_child":      Decimal("100"),
            "entry_resident":   Decimal("150"),
            "entry_towel":      Decimal("250"),
            "towel_rent":       Decimal("50"),
            "outside_food_fee": Decimal("50"),
        }


def get_base_prices(db: Session, branch_id: int) -> dict[str, Decimal]:
    """نسخة عامة من _get_base_prices — يستخدمها الـ router عشان يضيف الأسعار
    لرد GET /beach/inventory (باج حقيقي كان هنا: شاشة POS الشاطئ كانت مبنية
    على افتراض إن /beach/inventory بيرجّع adult_price/child_price/... جاهزة،
    بس الأسعار الحقيقية كانت متخزنة في جدول settings ومحسوبة سيرفر-سايد وقت
    البيع بس، مفيش أي endpoint كان بيرجّعها للفرونت إند قبل كده — يعني شاشة
    الشاطئ كانت بتعرض "NaN" في كل سعر لكل الوقت)."""
    return _get_base_prices(db, branch_id)


BEACH_VAT_AMOUNT = Decimal("0.00")
"""قرار التشغيل 2026-08-15: أسعار الشاطئ نهائية ولا تُضاف عليها VAT.

``BeachTransaction.total_amount`` هو المبلغ الوحيد الذي يراه ويدفعه
الكاشير، وهو نفسه الذي يُسجَّل في الوردية والفوليو والحساب الآجل والدفتر.
وجود الثابت هنا يمنع رجوع الاختلاف القديم الذي كان يعرض 200 ج في الـPOS
والإيصال ثم يسجّل 228 ج في درج الوردية بسبب VAT مخفية.
"""


def _customer_group_discount_amount(db: Session, customer_id: Optional[int], gross_amount: Decimal) -> Decimal:
    """خصم مجموعة العميل الدائم (crm.CustomerGroup.discount_percentage) —
    راجع dining.services._customer_group_discount_amount (نفس المنطق
    بالظبط). الشاطئ مفيهوش أي مفهوم خصم شرطي (Happy Hour/بروموشن) زي
    dining، فده أول وأوحد نوع خصم على معاملة شاطئ حاليًا — لا يوجد تعارض
    "أفضل خصم يفوز" هنا لأن مفيش نوع تاني يتنافس معاه."""
    if not customer_id:
        return Decimal("0")
    from app.modules.crm.services import get_customer_group_discount_percentage  # noqa: PLC0415

    pct = get_customer_group_discount_percentage(db, customer_id)
    if pct <= 0:
        return Decimal("0")
    return (gross_amount * pct / Decimal("100")).quantize(Decimal("0.01"))


def sell_ticket(
    db: Session,
    branch_id: int,
    data: BeachSellRequest,
    tx_date: Optional[date] = None,
    acting_user_level: int = 100,
) -> BeachTransaction:
    """⚠️ فجوة حقيقية اتصلحت هنا (wagdy.md #13/#37): BeachPOSView كان عنده
    offline queue محلي منفصل (localStorage) بيعيد إرسال نفس طلب البيع بدون
    أي مفتاح idempotency وقت الـ retry — لو الـ request وصل السيرفر فعلاً
    وخصم السعة، لكن الرد ضاع (قطع نت لحظي بعد الإرسال مباشرة)، الـ retry
    كان هيعمل بيع تاني حقيقي (خصم سعة مزدوج) بدل ما يكتشف إنه اتسجّل بالفعل
    — نفس فئة الحماية اللي restaurant/cafe عندهم من الأول عبر
    client_local_id. راجع local_id في BeachSellRequest."""
    if data.local_id:
        existing = crud.get_transaction_by_local_id(db, data.local_id)
        if existing:
            return existing
    try:
        tx = _sell_ticket_no_commit(
            db, branch_id, data, tx_date, acting_user_level=acting_user_level,
        )
        db.commit()
        db.refresh(tx)
        return tx
    except Exception:
        db.rollback()
        raise


def sell_cart(
    db: Session,
    branch_id: int,
    data: BeachCartSellRequest,
    tx_date: Optional[date] = None,
    acting_user_level: int = 100,
) -> list[BeachTransaction]:
    """بيع سلة متعددة الأصناف (زي "2 بالغ + فوطة") كـ transaction واحدة
    atomic — إما كل صنف ينجح أو ولا واحد فيهم يترحّل، عكس اللي كان بيحصل
    قبل كده (POS بيبعت طلب منفصل لكل صنف، وأي فشل نصف طريق كان بيسيب سلة
    نص متسجّلة). idempotency على مستوى السلة كلها: لو ``cart_local_id``
    موجود ومعاد إرساله (retry بعد قطع نت)، بنرجّع نفس التذاكر اللي
    اتسجّلت قبل كده بدل ما نكرر البيع.

    كل صنف بيستخدم نفس مسار sell_ticket الداخلي (_sell_ticket_no_commit)
    حرفيًا — صفر منطق مكرر، بس من غير commit مستقل لكل صنف."""
    if data.cart_local_id:
        existing = crud.get_transactions_by_cart_local_id(db, data.cart_local_id)
        if existing:
            return existing

    tx_date = tx_date or _business_today()
    results: list[BeachTransaction] = []
    try:
        for index, item in enumerate(data.items):
            item_local_id = f"{data.cart_local_id}:{index}" if data.cart_local_id else None
            single = BeachSellRequest(
                tx_type=item.tx_type, quantity=item.quantity,
                cashier_id=data.cashier_id, folio_id=data.folio_id, room_id=data.room_id,
                b2b_contract_id=data.b2b_contract_id, customer_id=data.customer_id,
                credit_account_id=data.credit_account_id, notes=data.notes,
                location_id=data.location_id, local_id=item_local_id,
                payment_currency=data.payment_currency, payment_fx_rate=data.payment_fx_rate,
                payment_method=data.payment_method, payment_channel_id=data.payment_channel_id,
                approver_user_id=data.approver_user_id, approver_pin=data.approver_pin,
            )
            tx = _sell_ticket_no_commit(
                db, branch_id, single, tx_date, acting_user_level=acting_user_level,
            )
            results.append(tx)
        db.commit()
    except IntegrityError:
        # ريترّاي متزامن لنفس السلة بالظبط (نفس cart_local_id) — الـUNIQUE
        # على client_local_id بيرفض الإدراج الثاني؛ ده مش خطأ فعلي، السلة
        # الأولى اتسجّلت بالفعل. نرجّعها بدل ما نفشل بغلطة تقنية مربكة.
        db.rollback()
        if data.cart_local_id:
            existing = crud.get_transactions_by_cart_local_id(db, data.cart_local_id)
            if existing:
                return existing
        raise
    except Exception:
        db.rollback()
        raise
    for tx in results:
        db.refresh(tx)
    return results


def _sell_ticket_no_commit(
    db: Session,
    branch_id: int,
    data: BeachSellRequest,
    tx_date: Optional[date] = None,
    acting_user_level: int = 100,
) -> BeachTransaction:
    """جسم sell_ticket الفعلي، من غير commit/refresh نهائي — مفصولة عشان
    checkin_location (تحت) تقدر تدمجها في transaction واحدة أطول (قفل موقع +
    بيع تذكرة + تحديث حالة الموقع) بدل ما تنادي sell_ticket العامة اللي
    بتعمل commit لوحدها وتُنهي الـ transaction بدري — لو حصل كده، قفل صف
    الموقع (SELECT FOR UPDATE) هيتفك بمجرد الـ commit ده قبل ما نتأكد إن
    تحديث حالة الموقع اتسجّل، وبيرجع نفس فئة سباق lost-update اللي القفل
    أصلاً اتحط عشان يمنعها."""
    tx_date = tx_date or _business_today()

    # Personal credit is its own receivable source; it must never create a
    # folio charge even if a stale room/folio selection remains in the POS.
    is_personal_credit = data.payment_method == "credit_account"
    folio_id = None if is_personal_credit else data.folio_id
    if not is_personal_credit and not folio_id and data.room_id:
        from app.modules.pms.services import find_active_folio_for_room  # noqa: PLC0415
        folio_id = find_active_folio_for_room(db, branch_id, data.room_id)
        if not folio_id:
            raise ValueError(f"مفيش ضيف مسجّل دخول في الغرفة {data.room_id} حاليًا")

    # طريقة الدفع الفعلية المستخدمة — نفس القاعدة اللي كانت جوه create_transaction
    # تحت، محسوبة هنا بدري عشان نقدر نتحقق من الوردية/القناة قبل أي أثر جانبي
    # (خصم سعة، إنشاء تذكرة...).
    resolved_method = data.payment_method or ("room" if folio_id else "cash")
    is_direct_tender = not is_personal_credit and resolved_method in ("cash", "card", "wallet")

    # لا تسمح بدفع مباشر (كاش/كارت/محفظة) من غير وردية مفتوحة لنفس الكاشير —
    # نفس قاعدة dining.services (راجع finance_services._lock_open_shift_or_conflict).
    # بيتحقق منها *قبل* أي خصم سعة عشان الطلب المرفوض ميسيبش أثر جانبي جزئي.
    shift_row = None
    if is_direct_tender and data.cashier_id:
        from app.modules.finance import services as finance_services  # noqa: PLC0415

        shift_row = finance_services._lock_open_shift_or_conflict(db, branch_id, data.cashier_id)
        if not shift_row:
            raise NoOpenShiftError(
                "مفيش وردية مفتوحة لهذا الكاشير — لازم تفتح وردية قبل تحصيل دفع مباشر"
            )

    # قناة التحصيل الفعلية (صندوق/Visa CIB/...) — الفرع بدون أي قنوات
    # مُعرَّفة بيفضل يشتغل بمسار الحساب القديم (legacy fallback)، مش خطأ.
    channel_snapshot = {
        "payment_channel_id": None, "payment_channel_code": None,
        "payment_channel_name": None, "settlement_account_code": None,
    }
    settlement_account_code: Optional[str] = None
    if is_direct_tender:
        from app.modules.dining.payment_policy import resolve_tender_channel  # noqa: PLC0415

        resolution = resolve_tender_channel(db, branch_id, resolved_method, data.payment_channel_id)
        settlement_account_code = resolution.account_code
        channel_snapshot = resolution.channel_snapshot

    # جلب/إنشاء inventory + قفل الصف طول الـ transaction (راجع _lock_inventory_or_raise)
    inv_row = get_inventory(db, branch_id, tx_date)
    inv_row = _lock_inventory_or_raise(db, inv_row)
    inv_state = BeachInventoryState(
        towels_available=inv_row.towels_available,
        towels_used=inv_row.towels_used,
        capacity_used=inv_row.capacity_used,
        capacity_max=inv_row.capacity_max,
    )

    # validation
    validation = validate_entry(inv_state, data.tx_type, data.quantity)
    if not validation.valid:
        raise ValueError(validation.error)

    # حساب السعر
    base_prices = _get_base_prices(db, branch_id)
    surge_pct   = float(inv_row.surge_pct)
    unit_price  = calculate_tx_price(data.tx_type, base_prices, surge_pct)
    gross_total = unit_price * data.quantity
    # خصم مجموعة العميل الدائم — تلقائي بالكامل، بيتحسب على السعر الأصلي.
    # قرار التشغيل 2026-08-15: الشاطئ بلا VAT؛ السعر بعد الخصم هو المبلغ
    # النهائي نفسه في الشاشة والإيصال والتحصيل وتقفيل الوردية.
    discount = _customer_group_discount_amount(db, data.customer_id, gross_total)
    vat      = BEACH_VAT_AMOUNT
    total    = max(Decimal("0"), gross_total - discount)

    # تحديث inventory
    cap_delta, towel_delta = calculate_inventory_delta(data.tx_type, data.quantity)
    crud.apply_inventory_delta(db, inv_row, cap_delta, towel_delta)

    # ربط العملية بوردية الكاشير المفتوحة (لو موجودة) — نفس الباترن المستخدم
    # في finance.services.add_payment، عشان مبيعات الشاطئ تظهر في تقرير نهاية
    # الوردية بدل ما تفضل غير مرتبطة بأي وردية. لو دفع مباشر، shift_row
    # اتقفلت بالفعل فوق (نفس الصف، مش لوكاپ تاني غير مقفول).
    if shift_row is not None:
        shift_id = shift_row.id
    else:
        shift_id = None
        if data.cashier_id:
            from app.modules.finance.crud import get_open_shift  # noqa: PLC0415
            open_shift = get_open_shift(db, branch_id, data.cashier_id)
            if open_shift:
                shift_id = open_shift.id

    tx = crud.create_transaction(db, {
        "branch_id":       branch_id,
        "tx_type":         data.tx_type,
        "quantity":        data.quantity,
        "unit_price":      unit_price,
        "total_amount":    total,
        "discount_amount": discount,
        "vat_amount":      vat,
        "surge_applied":   surge_pct > 0,
        "tx_date":         tx_date,
        "cashier_id":      data.cashier_id,
        "payment_method":  resolved_method,
        "folio_id":        folio_id,
        "b2b_contract_id": data.b2b_contract_id,
        "customer_id":     data.customer_id,
        "notes":           data.notes,
        "shift_id":        shift_id,
        "location_id":     data.location_id,
        "client_local_id": data.local_id,
        **channel_snapshot,
    })

    # POS-03: نحفظ currency/fx_rate كـ transient attributes على الـ tx عشان
    # _record_shift_payment تقدر تقرأهم. BeachTransaction مالوش عمودين دول
    # (وده متعمّد — المبلغ المالي المسجّل دايمًا EGP-equivalent في total_amount).
    # الأداة دي (setattr على instance بعد الإنشاء) آمنة في SQLAlchemy طالما
    # الـ attribute مش عمود مُعرَّف في الـ mapper — بيتكون instance attribute
    # عادي، مش بيتحفظ في الداتابيز.
    if hasattr(data, "payment_currency") and data.payment_currency:
        object.__setattr__(tx, "_payment_currency", data.payment_currency)
    if hasattr(data, "payment_fx_rate") and data.payment_fx_rate:
        object.__setattr__(tx, "_payment_fx_rate", data.payment_fx_rate)

    # قيد الإيراد يترحّل فورًا في الحالتين — بس لحساب مختلف حسب طريقة الدفع:
    # كاش فوري → Dr Cash؛ محمّل على غرمة → Dr ذمم الفوليو (والكاش الحقيقي
    # بيتسجّل لاحقًا وقت تسوية الفوليو، راجع finance.services.add_payment).
    #
    # ⚠️ باج حقيقي كان هنا (اتصلح 2026-07-07، فجوة معمارية موثّقة في
    # CLAUDE.md §18): التعليق القديم هنا كان بيدّعي إن "الإيراد بيتسجّل وقت
    # تسوية الفوليو" — لكن التسوية (add_payment) عمرها ما كانت بترحّل أي
    # قيد خالص، يعني إيراد الشاطئ الحقيقي من كل عملية بيع محمّلة على غرفة
    # كان غايب تمامًا عن دفتر الأستاذ، نفس فئة الباج بالظبط في restaurant/cafe.
    if is_personal_credit:
        from app.modules.credit import crud as credit_crud  # noqa: PLC0415
        from app.modules.credit import services as credit_services  # noqa: PLC0415

        if data.credit_account_id:
            credit_account = credit_crud.get_account(db, data.credit_account_id)
            if not credit_account or credit_account.branch_id != branch_id:
                raise ValueError("الحساب الآجل غير موجود في هذا الفرع")
            if data.customer_id:
                if (
                    credit_account.holder_type != "customer"
                    or credit_account.customer_id != data.customer_id
                ):
                    raise ValueError("الحساب الآجل لا يخص العميل المحدد")
        else:
            credit_account = credit_crud.get_account_for_customer(
                db, data.customer_id, branch_id,
            )
        if not credit_account:
            raise ValueError(
                "لا يوجد حساب آجل مطابق في هذا الفرع"
            )
        # سعر الشاطئ نهائي بلا VAT؛ الحساب الآجل يستلم نفس إجمالي الشاشة.
        charge_amount = tx.total_amount or Decimal("0")
        credit_services.charge_to_account(
            db,
            credit_account.id,
            branch_id,
            charge_amount,
            data.cashier_id or 0,
            ref_beach_tx_id=tx.id,
            notes=f"بيع شاطئ {tx.tx_type} × {tx.quantity}",
            revenue_allocations=[("4300", charge_amount, "BEACH")],
            acting_user_level=acting_user_level,
            approver_user_id=data.approver_user_id,
            approver_pin=data.approver_pin,
            commit=False,
        )
    elif tx.folio_id:
        from app.modules.finance import services as finance_services  # noqa: PLC0415
        from app.modules.finance.schemas import FolioChargeCreate  # noqa: PLC0415
        # add_folio_charge بتقفل صف الفوليو (blocking) قبل الإدخال وتعيد
        # حساب الإجمالي من قراءة طازة — راجع Gate 1B (finance/services.py).
        # ⚠️ مراجعة Codex الثانية: كان فيه except Exception: pass هنا —
        # يعني بيع شاطئ محمّل على غرفة كان ممكن "ينجح" ويتسجّل تمامًا
        # (خصم سعة + تذكرة) من غير أي FolioCharge حقيقي لو الفوليو مقفول/
        # ملغي أو أي فشل تاني حصل. دلوقتي fail-closed **مع rollback صريح**:
        # مجرد عدم عمل commit مش كافي — الصفوف اللي اتعملها flush قبل كده
        # (التذكرة، تحديث السعة) بتفضل مرئية على أي جلسة تانية على نفس
        # الـconnection لحد ما rollback حقيقي يحصل (اتكشف فعليًا وقت كتابة
        # اختبار الأثر الجانبي لهذا الإصلاح)، فمينفعش نعتمد على "مفيش commit"
        # بس زي ما كنا فاكرين — لازم rollback صريح هنا.
        try:
            finance_services.add_folio_charge(db, tx.folio_id, FolioChargeCreate(
                charge_type="beach",
                description=f"شاطئ — {tx.tx_type} × {tx.quantity}",
                amount=tx.total_amount,
                vat_amount=tx.vat_amount,
                posted_at=datetime.combine(tx.tx_date, datetime.min.time()),
                ref_beach_tx_id=tx.id,
            ))
            _post_beach_folio_charge_journal(db, tx)
        except Exception:
            db.rollback()
            raise
    else:
        _post_beach_revenue_journal(db, tx, settlement_account_code)
        _record_shift_payment(db, tx, channel_snapshot)
    if tx.customer_id:
        from app.modules.crm.services import record_customer_visit  # noqa: PLC0415
        record_customer_visit(db, tx.customer_id, tx.total_amount, tx.tx_date)

    return tx


def _post_beach_revenue_journal(
    db: Session, tx: "BeachTransaction", settlement_account_code: Optional[str] = None,
) -> None:
    """Direct tender journal, using the configured GL account for its method.

    قرار التشغيل 2026-08-15: الشاطئ بلا VAT أو رسم خدمة. نستخدم نفس منشئ
    القيد الصارم المشترك لكن بقيمة ضريبة صفر؛ الناتج Dr وسيلة التحصيل / Cr
    إيراد الشاطئ بالمبلغ النهائي الظاهر للكاشير.

    ``settlement_account_code`` هو نفس الحساب اللي resolve_tender_channel
    حلّه وقت البيع (قناة تحصيل حقيقية أو fallback القديم) — بيتمرر من
    _sell_ticket_no_commit عشان يفضل نفس الحساب المستخدم فعليًا، مش إعادة
    حل مستقل ممكن يختلف نظريًا لو إعداد القناة اتغيّر في نفس اللحظة.
    ``None`` (نداء مباشر قديم بدون تمرير الباراميتر) يرجع لمسار legacy.

    towel_return مالوش قيمة مالية (0/0) — post_taxed_sale_journal الصارمة
    بترفض إجمالي صفر (على عكس post_simple_revenue_journal القديمة اللي
    كانت بترجع None بصمت)، فلازم نتخطى النداء هنا صراحةً بدل ما نسيب
    العملية التشغيلية (إرجاع الفوطة) تفشل بغلطة محاسبية غير حقيقية."""
    if (tx.total_amount or Decimal("0")) + (tx.vat_amount or Decimal("0")) <= 0:
        return
    from app.modules.finance.services import post_taxed_sale_journal  # noqa: PLC0415
    from app.modules.dining.payment_policy import resolve_direct_tender_account  # noqa: PLC0415

    method = tx.payment_method or "cash"
    debit_code = settlement_account_code or resolve_direct_tender_account(method)

    post_taxed_sale_journal(
        db, tx.branch_id, tx.tx_date,
        debit_account_code=debit_code, revenue_account_code="4300",
        net_revenue_amount=(tx.total_amount or Decimal("0")),
        vat_amount=(tx.vat_amount or Decimal("0")),
        reference=f"BCH-{tx.id:06d}" if tx.id else "BCH-NEW",
        description=f"إيرادات شاطئ ({method}) — {tx.tx_type}",
        source="beach", source_id=tx.id,
        cost_center_code="BEACH",
        # ⚠️ باج حقيقي اتكشف واتصلح هنا (أثناء بناء sell_cart): الافتراضي
        # commit_cost_centers=True كان بيعمل db.commit() ضمني (عبر
        # ensure_default_cost_centers) وسط أي عملية بيع شاطئ — يعني حتى
        # sell_ticket المفرد كان بيقفل الـtransaction بدري من غير قصد، وسلة
        # متعددة الأصناف (sell_cart) كانت بتفقد الـatomicity بالكامل: أول
        # صنف ينجح كان بيتثبّت فعليًا في الداتابيز قبل ما نوصل حتى للصنف
        # التاني، فرفض صنف لاحق مايقدرش يرجع الصنف الناجح. نفس الحل
        # المستخدم في dining.services (Gate 1B) لكل مسار strict atomic.
        commit_cost_centers=False,
    )


def _record_shift_payment(db: Session, tx: "BeachTransaction", channel_snapshot: Optional[dict] = None) -> None:
    """⚠️ باج حقيقي اتصلح: migration 504f42d2c755 (2026-07-15) جهّزت
    Payment.folio_id nullable/ref_order_id صراحةً "عشان مبيعات الشاطئ/
    الدايننج المباشرة تظهر في تقرير نهاية الوردية" — بس عمرها ما كان فيه
    كود بيكتب Payment فعليًا لبيع شاطئ مباشر. النتيجة: tx.shift_id كان
    بيتسجّل على BeachTransaction نفسها (تعليقه فوق في sell_ticket بيقول
    نفس النية بالظبط)، لكن build_shift_end_report/list_shift_invoices
    (finance.services) بيقروا Payment.shift_id بس — يعني مبيعات الشاطئ
    المباشرة (كاش/كارت فوري، مش محمّلة على غرفة) كانت غايبة تمامًا عن
    تقرير X/Z الوردية رغم كل البنية التحتية الجاهزة ليها. الحل: نسجّل
    Payment حقيقي (folio_id=None) هنا — نفس نمط finance.services.add_payment
    بالظبط، بس بدون فوليو. الشاطئ مالوش تمييز كاش/كارت حقيقي في البيانات
    (نفس القيد المحاسبي فوق بيعامل كل بيع مباشر كـ"كاش" دايمًا)، فـ method
    ثابتة "cash" هنا — نفس الافتراض المحاسبي الموجود بالفعل، مش افتراض جديد.

    POS-03: currency/fx_rate — لو الكاشير استلم كاش بعملة أجنبية، نمرّرهم
    لـ create_direct_payment عشان يظهروا في تقرير نهاية الوردية مع variance
    لكل عملة على حدة (راجع build_shift_end_report). amount دايمًا EGP-equivalent.
    الفكة دايمًا بالجنيه (قرار Mohamed 2026-08-05)."""
    if not tx.shift_id and not tx.cashier_id:
        return  # مفيش وردية ولا كاشير مرتبط — مفيش حاجة تتسجّل (تسجيل يدوي/API مباشر)
    from app.modules.finance import crud as finance_crud  # noqa: PLC0415

    # POS-03: استخرج currency/fx_rate لو اتبعتوا في طلب البيع
    currency = getattr(tx, "_payment_currency", None) or "EGP"
    fx_rate  = getattr(tx, "_payment_fx_rate", None)

    finance_crud.create_direct_payment(
        db, branch_id=tx.branch_id,
        # مهم: total_amount هو إجمالي الشاشة/الإيصال النهائي. لا تضف أي
        # مكوّن آخر هنا وإلا سيظهر فرق وهمي عند تقفيل الوردية.
        amount=(tx.total_amount or Decimal("0")),
        method=tx.payment_method or "cash",
        posted_at=datetime.combine(tx.tx_date, datetime.min.time()),
        shift_id=tx.shift_id, cashier_id=tx.cashier_id,
        reference=f"BCH-{tx.id:06d}" if tx.id else None,
        currency=currency,
        fx_rate=fx_rate,
        source="beach",
        channel_snapshot=channel_snapshot,
    )


def _post_beach_folio_charge_journal(db: Session, tx: "BeachTransaction") -> None:
    """Dr. ذمم الفوليو (1150) / Cr. إيراد الشاطئ (4300).

    عملية محمّلة على فوليو غرفة بالمبلغ النهائي نفسه؛ الشاطئ بلا VAT أو
    رسم خدمة بقرار التشغيل 2026-08-15.
    """
    from app.modules.finance.services import post_taxed_sale_journal  # noqa: PLC0415

    post_taxed_sale_journal(
        db, tx.branch_id, tx.tx_date,
        debit_account_code="1150", revenue_account_code="4300",
        net_revenue_amount=(tx.total_amount or Decimal("0")),
        vat_amount=(tx.vat_amount or Decimal("0")),
        reference=f"BCH-{tx.id:06d}" if tx.id else "BCH-NEW",
        description=f"إيرادات شاطئ (محمّل على الغرفة) — {tx.tx_type}",
        source="beach_folio_charge", source_id=tx.id,
        cost_center_code="BEACH",
        commit_cost_centers=False,  # راجع تعليق _post_beach_revenue_journal
    )


def _month_bounds(day: date) -> tuple[date, date]:
    """أول وآخر يوم في الشهر التقويمي اللي يحتوي ``day`` — يُستخدم لحساب
    استهلاك الحد الشهري الاسترشادي ولقطة guests_count وقت الترحيل الشهري."""
    start = day.replace(day=1)
    if start.month == 12:
        end = date(start.year, 12, 31)
    else:
        end = date(start.year, start.month + 1, 1) - timedelta(days=1)
    return start, end


def _contract_state(contract_row: "B2BContract", checked_in_this_month: int) -> B2BContractState:
    """يبني B2BContractState من صف B2BContract — نقطة واحدة عشان أي حقل
    جديد (زي valid_from/valid_until) يتضاف مرة واحدة بس، مش يتكرر في 3 أماكن."""
    return B2BContractState(
        contract_id=contract_row.id,
        hotel_name=contract_row.hotel_name,
        monthly_guest_cap=contract_row.monthly_guest_cap,
        checked_in_this_month=checked_in_this_month,
        monthly_fee=contract_row.monthly_fee,
        is_active=contract_row.is_active,
        valid_from=contract_row.valid_from,
        valid_until=contract_row.valid_until,
    )


def b2b_checkin(
    db: Session,
    branch_id: int,
    data: B2BCheckinRequest,
    tx_date: Optional[date] = None,
) -> BeachTransaction:
    """2026-08-20، طلب Mohamed صراحةً: عقد B2B بقى مبلغ شهري ثابت، فتشيك-إن
    الضيف بقى عدّاد بحت — مفيش سعر، مفيش رفض لو الحد الشهري الاسترشادي
    اتخطّى (تخطّيه مسموح صراحةً)، ومفيش قيد محاسبي هنا خالص (الإيراد
    بيترحّل مرة واحدة شهريًا — راجع post_b2b_monthly_fees). المتبقّي اللي
    لسه حقيقي فعليًا: صلاحية العقد + سعة/فوط الشاطئ الفعلية (قيود فيزيائية
    حقيقية، مش شرط عقد)."""
    tx_date = tx_date or _business_today()

    contract_row = crud.get_b2b_contract(db, data.contract_id)
    if not contract_row:
        raise ValueError(f"العقد {data.contract_id} غير موجود")

    contract_day = crud.get_or_create_contract_day(db, data.contract_id, tx_date)
    contract_day = _lock_contract_day_or_raise(db, contract_day)

    month_start, month_end = _month_bounds(tx_date)
    checked_in_this_month = crud.get_b2b_checked_in_count_for_month(db, data.contract_id, month_start, month_end)
    contract_state = _contract_state(contract_row, checked_in_this_month)

    validation = validate_b2b_checkin(contract_state, tx_date)
    if not validation.valid:
        raise ValueError(validation.error)

    # التحقق من inventory — نفس قفل الصف المستخدم في sell_ticket
    inv_row = get_inventory(db, branch_id, tx_date)
    inv_row = _lock_inventory_or_raise(db, inv_row)
    inv_state = BeachInventoryState(
        towels_available=inv_row.towels_available,
        towels_used=inv_row.towels_used,
        capacity_used=inv_row.capacity_used,
        capacity_max=inv_row.capacity_max,
    )
    tx_type = "entry_towel" if data.with_towel else "entry"
    inv_validation = validate_entry(inv_state, tx_type, data.guests_count)
    if not inv_validation.valid:
        raise ValueError(inv_validation.error)

    cap_delta, towel_delta = calculate_inventory_delta(tx_type, data.guests_count)
    crud.apply_inventory_delta(db, inv_row, cap_delta, towel_delta)

    crud.increment_b2b_checkins(db, data.contract_id, tx_date, data.guests_count)

    # تحذير الحد الشهري (warning إذا بقي ≤ 5) — لازم يتحسب على العدد بعد
    # الزيادة فوق، وإلا التحذير كان هيتأخر تسجيل دخول واحد كامل عن اللحظة
    # الفعلية اللي الحد يوصل فيها (نفس باج التوقيت اللي كان موجود في النسخة
    # اليومية القديمة). ``notified_quota_warning_period`` بيتقارن بأول يوم
    # في الشهر الحالي — بيتصفّر ضمنيًا كل شهر جديد من غير أي مهمة Celery
    # منفصلة تصفّره.
    updated_state = _contract_state(contract_row, checked_in_this_month + data.guests_count)
    if updated_state.quota_warning and contract_row.notified_quota_warning_period != month_start:
        contract_row.notified_quota_warning_period = month_start
        db.flush()
        if contract_row.contact_phone:
            try:
                from app.core.kernel.whatsapp import send_whatsapp_message  # noqa: PLC0415
                send_whatsapp_message(
                    contract_row.contact_phone,
                    f"تنبيه: الحد الشهري لـ {contract_row.hotel_name} في الخيمة بيتش أوشك على الانتهاء (≤5 متبقي هذا الشهر).",
                )
            except Exception:
                pass  # ميمنعش إتمام تسجيل الدخول لو فشل إرسال التنبيه

    tx = crud.create_transaction(db, {
        "branch_id":       branch_id,
        "tx_type":         tx_type,
        "quantity":        data.guests_count,
        "unit_price":      Decimal("0"),
        "total_amount":    Decimal("0"),
        "vat_amount":      Decimal("0"),
        "surge_applied":   False,
        "tx_date":         tx_date,
        "cashier_id":      data.cashier_id,
        "b2b_contract_id": data.contract_id,
    })

    # مفيش ترحيل إيراد هنا عمدًا — الرسم الشهري الثابت بيترحّل مرة واحدة
    # شهريًا (راجع post_b2b_monthly_fees)، مش لكل تشيك-إن.

    db.commit()
    db.refresh(tx)
    return tx


def void_transaction(db: Session, tx_id: int, voided_by: int, reason: str) -> BeachTransaction:
    """Void inventory, source settlement and journals as one database unit."""
    try:
        return _void_transaction_atomic(db, tx_id, voided_by, reason)
    except Exception:
        db.rollback()
        raise


def _void_transaction_atomic(
    db: Session, tx_id: int, voided_by: int, reason: str,
) -> BeachTransaction:
    """⚠️ باج محاسبي حقيقي كان هنا (اتصلح 2026-07-04): كان بيعكس المخزون بس —
    مايلمسش أي أثر مالي خالص. عملية كاش فوري كانت فضلة إيراد مسجّل في دفتر
    اليومية للأبد حتى بعد الإلغاء (مبالغة دائمة في الإيرادات)، وعملية محمّلة
    على غرفة (Charge to Room) كانت فضلة شحنة على فاتورة الضيف حتى لو الشاطئ
    نفسه ألغاها (الضيف كان هيتحاسب على حاجة اتلغت). دلوقتي الإلغاء بيعكس
    الأثر المالي فعليًا حسب نوع العملية وقت البيع."""
    tx = crud.get_transaction(db, tx_id)
    if not tx:
        raise ValueError(f"العملية {tx_id} غير موجودة")
    if tx.voided_at:
        raise ValueError("العملية ملغاة مسبقاً")

    # عكس الـ inventory — ⚠️ باج حقيقي كان هنا (اتصلح 2026-07-28): بعكس
    # sell_ticket/b2b_checkin (بيقفلوا الصف قبل أي تعديل، راجع
    # _lock_inventory_or_raise)، void_transaction كانت بتقرا وتعدّل
    # capacity_used/towels_used من غير أي قفل خالص — لو عملية بيع جديدة
    # حصلت في نفس اللحظة بالظبط على نفس الفرع/اليوم، الإلغاء ده كان ممكن
    # يبني على قراءة قديمة ويمسح أثر البيع الجديد بصمت (lost update، نفس
    # فئة الباج الموثّقة في lock_inventory_for_update's docstring بالظبط).
    inv_row = get_inventory(db, tx.branch_id, tx.tx_date)
    inv_row = _lock_inventory_or_raise(db, inv_row)
    cap_delta, towel_delta = calculate_inventory_delta(tx.tx_type, tx.quantity)
    crud.apply_inventory_delta(db, inv_row, -cap_delta, -towel_delta)

    # عكس الأثر المالي — نفس التفرّع اللي حصل وقت sell_ticket بالظبط.
    # الحساب الآجل له دفتر فرعي وقيد Dr 1160 مستقل؛ معاملته كبيع كاش هنا
    # كانت ستنشئ Cr 1100 وهمي وتترك مديونية العميل كما هي.
    #
    # تشيك-إن B2B (2026-08-20): مفيش أثر مالي خالص وقت التسجيل (الرسم
    # الشهري الثابت بيترحّل منفصل شهريًا — راجع b2b_checkin) فمفيش قيد
    # عكسي ولا دفعة وردية يتلغوا هنا. _post_beach_revenue_reversal_journal
    # كانت هترفض فعليًا (gross_amount=0 → ValueError) لو اتنادت على معاملة
    # زي دي.
    if tx.b2b_contract_id:
        pass
    elif tx.payment_method == "credit_account":
        from app.modules.credit import crud as credit_crud  # noqa: PLC0415
        from app.modules.credit import services as credit_services  # noqa: PLC0415

        charge = credit_crud.get_charge_for_source(db, ref_beach_tx_id=tx.id)
        if not charge:
            raise ValueError(
                "حركة الحساب الآجل الأصلية غير موجودة — لا يمكن إلغاء البيع بأمان"
            )
        credit_services.reverse_transaction(
            db,
            charge.id,
            tx.branch_id,
            f"إلغاء عملية شاطئ: {reason}",
            voided_by,
            expected_account_id=charge.credit_account_id,
            commit=False,
        )
    elif tx.folio_id:
        from app.modules.finance import crud as finance_crud  # noqa: PLC0415

        folio = finance_crud.get_folio(db, tx.folio_id)
        if folio and folio.status == "closed":
            raise ValueError(
                "لا يمكن إلغاء عملية شاطئ على فاتورة مقفولة بالفعل — راجع الحسابات يدويًا"
            )
        charge = finance_crud.get_charge_by_ref_beach_tx(db, tx.id)
        if charge:
            finance_crud.delete_charge(db, charge)
            if folio:
                finance_crud.recalculate_folio_total(db, folio)
            # عكس قيد _post_beach_folio_charge_journal الأصلي — الشحنة اتلغت
            # بالكامل يبقى الإيراد ده لازم يترد بالكامل، مش نسبي زي مرتجع
            # صنف جزئي (الشاطئ مفيهوش مفهوم "مرتجع صنف" — إلغاء العملية كلها).
            _post_beach_folio_charge_reversal_journal(db, tx)
    else:
        _post_beach_revenue_reversal_journal(db, tx)
        _void_shift_payment(db, tx, voided_by)

    # عكس عدّاد B2B اليومي (checked_in_count بس دلوقتي — مفيش مبلغ يتعكس
    # منذ 2026-08-20، راجع models.B2BContractDay) لو العملية كانت تشيك-إن
    # فندق شريك. القفل هنا نفس فئة قفل الـinventory فوق بالظبط — لو تشيك-إن
    # B2B جديد حصل في نفس اللحظة، الإلغاء كان ممكن يمسح أثره بصمت من غيره.
    if tx.b2b_contract_id:
        day_row = crud.get_or_create_contract_day(db, tx.b2b_contract_id, tx.tx_date)
        _lock_contract_day_or_raise(db, day_row)
        crud.decrement_b2b_checkins(db, tx.b2b_contract_id, tx.tx_date, tx.quantity)

    # ⚠️ باج حقيقي كان هنا (اتصلح 2026-07-28): إلغاء معاملة اتسجّلت عن طريق
    # خريطة الشاطئ الحية (checkin_location) كان بيعكس كل الأثر المالي/المخزني
    # بس مايلمسش BeachLocation خالص — الموقع كان يفضل "مشغول" ببيانات ضيف
    # وهمية للأبد بعد ما البيع نفسه اتلغى. بنصفّره فقط لو لسه بيأشّر على نفس
    # المعاملة دي بالظبط (current_transaction_id == tx.id) — لو الموقع
    # اتفضّى (checkout عادي) أو اتاح لضيف تاني بعدين، مالوش أي علاقة بالإلغاء
    # المتأخر ده، فمينفعش نلمسه.
    if tx.location_id:
        loc = crud.get_location(db, tx.location_id)
        if loc:
            loc = _lock_location_or_raise(db, loc)
            if loc.current_transaction_id == tx.id:
                loc.status = "available"
                loc.current_transaction_id = None
                loc.guest_name = None
                loc.guest_phone = None
                loc.guests_count = 0
                loc.towels_given = 0
                loc.checked_in_at = None
                loc.checked_in_by = None

    tx = crud.void_transaction(db, tx, voided_by, reason)
    db.commit()
    db.refresh(tx)
    return tx


def _void_shift_payment(db: Session, tx: "BeachTransaction", voided_by: int) -> None:
    """يعكس الـ Payment اللي _record_shift_payment سجّله وقت البيع (لو
    موجود) — وإلا تقرير نهاية الوردية هيفضل يحسب بيع اتلغى ضمن total_sales
    رغم إن القيد المحاسبي نفسه اتعكس بالفعل فوق (_post_beach_revenue_
    reversal_journal). راجع _record_shift_payment للتفاصيل الكاملة."""
    if not tx.id:
        return
    from app.modules.finance import crud as finance_crud  # noqa: PLC0415

    payment = finance_crud.get_direct_payment_by_reference(db, tx.branch_id, f"BCH-{tx.id:06d}")
    if payment:
        finance_crud.void_payment(db, payment, voided_by)


def _post_beach_revenue_reversal_journal(db: Session, tx: "BeachTransaction") -> None:
    """عكس _post_beach_revenue_journal — بيلغي أثر قيد البيع الأصلي (إيراد
    صافي + VAT payable) في الدفاتر بنفس السطور والنسب، مش قيد جديد بإجمالي
    gross على الإيراد بس (FIN-TAX-01، OPS-DATA-02 §11.2).

    ✅ فجوة حقيقية اتصلحت هنا (كانت موثّقة سابقًا كـ"خارج النطاق"): الطرف
    الآخر كان ثابت "1100" (كاش) دايمًا حتى لو البيع الأصلي كان بالكارت أو
    قناة تحصيل تانية — الإلغاء مايرجعش بالضرورة لنفس حساب الاستلام الأصلي.
    دلوقتي بيستخدم ``tx.settlement_account_code`` — لقطة الحساب الفعلي
    المحفوظة وقت البيع نفسه، مش إعداد القناة الحالي (ده ممكن يتغيّر بعد
    البيع). معاملات قديمة قبل payment_channels (snapshot=None) لسه بترجع
    لمسار legacy القديم (resolve_direct_tender_account) عشان توافق تاريخي."""
    from app.modules.finance.services import reverse_taxed_sale_journal  # noqa: PLC0415
    from app.modules.dining.payment_policy import resolve_direct_tender_account  # noqa: PLC0415

    debit_code = tx.settlement_account_code or resolve_direct_tender_account(tx.payment_method or "cash")

    reverse_taxed_sale_journal(
        db, tx.branch_id, _business_today(),
        debit_account_code=debit_code, revenue_account_code="4300",
        net_revenue_amount=(tx.total_amount or Decimal("0")),
        vat_amount=(tx.vat_amount or Decimal("0")),
        reference=f"BCH-VOID-{tx.id:06d}",
        description=f"إلغاء عملية شاطئ — {tx.tx_type}",
        source="beach_void", source_id=tx.id,
        cost_center_code="BEACH",
        commit_cost_centers=False,  # راجع تعليق _post_beach_revenue_journal
    )


def _post_beach_folio_charge_reversal_journal(db: Session, tx: "BeachTransaction") -> None:
    """عكس _post_beach_folio_charge_journal — بنفس سطور القيد الأصلي (إيراد
    صافي + VAT payable)، لا Dr Revenue بالإجمالي (FIN-TAX-01)."""
    from app.modules.finance.services import reverse_taxed_sale_journal  # noqa: PLC0415

    reverse_taxed_sale_journal(
        db, tx.branch_id, _business_today(),
        debit_account_code="1150", revenue_account_code="4300",
        net_revenue_amount=(tx.total_amount or Decimal("0")),
        vat_amount=(tx.vat_amount or Decimal("0")),
        reference=f"BCH-VOID-{tx.id:06d}",
        description=f"إلغاء عملية شاطئ (محمّل على الغرفة) — {tx.tx_type}",
        source="beach_folio_void", source_id=tx.id,
        cost_center_code="BEACH",
        commit_cost_centers=False,  # راجع تعليق _post_beach_revenue_journal
    )


TX_TYPE_LABELS: dict[str, str] = {
    "entry":          "دخول بالغ",
    "entry_child":    "دخول طفل",
    "entry_resident": "دخول مقيم",
    "entry_towel":    "دخول + فوطة",
    "towel_rent":     "إيجار فوطة",
    "towel_return":   "إعادة فوطة",
}


def generate_ticket_pdf(db: Session, tx_id: int) -> bytes:
    """يُولّد PDF تذكرة دخول الشاطئ (مقاس رول حراري 80mm — نفس مقاس طابعات الكاشير الحقيقية)."""
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    tx = crud.get_transaction(db, tx_id)
    if not tx:
        raise ValueError(f"العملية {tx_id} غير موجودة")

    tx_label = TX_TYPE_LABELS.get(tx.tx_type, tx.tx_type)
    fields = [
        ("نوع التذكرة",  tx_label),
        ("الكمية",       str(tx.quantity)),
        ("سعر الوحدة",   f"{tx.unit_price:,.2f} EGP"),
        ("التاريخ",      str(tx.tx_date)),
    ]
    if tx.surge_applied:
        fields.append(("Surge", "مطبّق"))

    return builder.receipt_pdf_thermal(
        reference=f"BCH-{tx.id:06d}",
        title="تذكرة دخول الشاطئ",
        fields=fields,
        total=float(tx.total_amount),
        currency="EGP",
        note="شكراً لزيارتك — الخيمة بيتش ريزورت",
    )


def set_surge(db: Session, branch_id: int, surge_pct: Decimal, inv_date: Optional[date] = None) -> BeachInventory:
    inv_date = inv_date or _business_today()
    if surge_pct < 0 or surge_pct > 200:
        raise ValueError("surge_pct يجب أن يكون بين 0 و 200")
    # Ensure a new day inherits the configured capacity before the surge row
    # is created by the lower-level persistence helper.
    get_inventory(db, branch_id, inv_date)
    row = crud.set_surge_manual(db, branch_id, inv_date, surge_pct)
    db.commit()
    db.refresh(row)
    return row


TX_TYPE_LABELS_AR: dict[str, str] = {
    "entry":          "دخول بالغ",
    "entry_child":    "دخول طفل",
    "entry_resident": "دخول مقيم",
    "entry_towel":    "دخول + فوطة",
    "towel_rent":     "إيجار فوطة",
    "towel_return":   "إعادة فوطة",
}


def _pct_change(current: Decimal, previous: Decimal) -> Optional[float]:
    if previous == 0:
        return None
    return round(float((current - previous) / previous * 100), 1)


def get_eod_report(db: Session, branch_id: int, report_date: Optional[date] = None) -> dict:
    """تقرير نهاية اليوم — إجمالي الدخول حسب النوع، إيرادات الفوط، ومقارنة
    بالأمس والأسبوع الماضي (نفس اليوم)."""
    report_date = report_date or _business_today()
    yesterday = report_date - timedelta(days=1)
    last_week = report_date - timedelta(days=7)

    today_data     = crud.get_eod_breakdown(db, branch_id, report_date)
    yesterday_data = crud.get_eod_breakdown(db, branch_id, yesterday)
    last_week_data = crud.get_eod_breakdown(db, branch_id, last_week)

    towel_price = _get_base_prices(db, branch_id).get("towel_rent", Decimal("50"))
    by_type = today_data["by_type"]
    towel_revenue = (
        by_type.get("towel_rent", {}).get("total_amount", Decimal("0"))
        + by_type.get("entry_towel", {}).get("quantity", 0) * towel_price
    )

    by_type_rows = [
        {
            "tx_type":      tx_type,
            "label":        TX_TYPE_LABELS_AR.get(tx_type, tx_type),
            "quantity":     data["quantity"],
            "count":        data["count"],
            "total_amount": data["total_amount"],
        }
        for tx_type, data in sorted(by_type.items())
    ]

    return {
        "date":              report_date,
        "total_entries":     today_data["total_entries"],
        "total_revenue":     today_data["total_revenue"],
        "b2b_entries":       today_data["b2b_entries"],
        "b2b_revenue":       today_data["b2b_revenue"],
        "towel_revenue":     towel_revenue,
        "voided_count":      today_data["voided_count"],
        "by_type":           by_type_rows,
        "yesterday": {
            "date":          yesterday,
            "total_entries": yesterday_data["total_entries"],
            "total_revenue": yesterday_data["total_revenue"],
        },
        "last_week": {
            "date":          last_week,
            "total_entries": last_week_data["total_entries"],
            "total_revenue": last_week_data["total_revenue"],
        },
        "vs_yesterday_pct":  _pct_change(today_data["total_revenue"], yesterday_data["total_revenue"]),
        "vs_last_week_pct":  _pct_change(today_data["total_revenue"], last_week_data["total_revenue"]),
    }


def generate_eod_report_pdf(db: Session, branch_id: int, report_date: Optional[date] = None) -> bytes:
    """PDF جاهز للطباعة لتقرير نهاية اليوم."""
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    report = get_eod_report(db, branch_id, report_date)

    headers = ["نوع العملية", "الكمية", "عدد العمليات", "الإجمالي (EGP)"]
    rows = [
        [r["label"], str(r["quantity"]), str(r["count"]), f"{r['total_amount']:,.2f}"]
        for r in report["by_type"]
    ]

    def _fmt_pct(pct: Optional[float]) -> str:
        if pct is None:
            return "—"
        arrow = "▲" if pct >= 0 else "▼"
        return f"{arrow} {abs(pct)}%"

    summary = [
        ("إجمالي الدخول",            str(report["total_entries"])),
        ("إجمالي الإيرادات",         f"{report['total_revenue']:,.2f} EGP"),
        ("دخول B2B",                 str(report["b2b_entries"])),
        ("إيرادات B2B",              f"{report['b2b_revenue']:,.2f} EGP"),
        ("إيرادات الفوط",            f"{report['towel_revenue']:,.2f} EGP"),
        ("عمليات ملغاة",             str(report["voided_count"])),
        ("مقارنة بالأمس",            _fmt_pct(report["vs_yesterday_pct"])),
        ("مقارنة بالأسبوع الماضي",   _fmt_pct(report["vs_last_week_pct"])),
    ]

    return builder.table_pdf(
        title="تقرير الشاطئ اليومي",
        subtitle=str(report["date"]),
        headers=headers,
        rows=rows,
        summary=summary,
        footer="الخيمة بيتش ريزورت",
    )


def get_b2b_quota_status(db: Session, branch_id: int, day: Optional[date] = None) -> list[dict]:
    """حالة الحد الشهري الاسترشادي + الائتمان لكل فنادق B2B النشطة — بيوصل
    quota_warning (≤5 متبقي من الحد الشهري) من beach_engine.B2BContractState
    + حالة الائتمان (outstanding_balance/credit_limit/is_overdue) لنفس
    اللوحة الحيّة. ``checked_in_today`` لسه معروض منفصل (إحصائية تشغيلية
    مفيدة للكاشير حتى لو الحد نفسه بقى شهري مش يومي)."""
    day = day or _business_today()
    month_start, month_end = _month_bounds(day)
    rows = crud.list_b2b_contracts_with_today_usage(db, branch_id, day)

    result = []
    for contract, checked_in_today in rows:
        checked_in_this_month = crud.get_b2b_checked_in_count_for_month(db, contract.id, month_start, month_end)
        state = _contract_state(contract, checked_in_this_month)
        outstanding = crud.get_b2b_outstanding_balance(db, contract.id, contract.last_settled_at)
        result.append({
            "contract_id":           state.contract_id,
            "hotel_name":            state.hotel_name,
            "checked_in_today":      checked_in_today,
            "monthly_guest_cap":     state.monthly_guest_cap,
            "checked_in_this_month": state.checked_in_this_month,
            "remaining_monthly_quota": state.remaining_monthly_quota,
            "quota_warning":         state.quota_warning,
            "is_valid_today":        state.is_valid_on(day),
            "monthly_fee":           contract.monthly_fee,
            "credit_limit":          contract.credit_limit,
            "outstanding_balance":   outstanding,
            "credit_exceeded":       (
                contract.credit_limit is not None and outstanding > contract.credit_limit
            ),
            "is_overdue":            contract.is_overdue,
            "payment_terms_days":    contract.payment_terms_days,
        })
    return result


def settle_b2b_contract(
    db: Session, contract_id: int, settled_through: Optional[date] = None,
    settlement_account_code: str = "1110",
) -> "B2BContract":
    """يسجّل تسوية (تحصيل) رصيد الفندق الشريك — يُستدعى لما الفندق يدفع
    فاتورته الدورية (عادة تحويل بنكي للمنتجع، مش كاش في درج كاشير الشاطئ —
    الحساب الافتراضي 1110 بنك، مش 1100 صندوق). بيرحّل قيد تحصيل حقيقي
    (Dr <settlement_account_code> / Cr 1165) بالمبلغ المستحق فعليًا قبل ما
    يصفّر الرصيد، وبيلغي علم التأخر.

    ✅ فجوة حقيقية اتصلحت هنا (2026-08-20): قبل كده التسوية كانت مجرد
    تصفير رصيد بدون أي أثر محاسبي — رصيد 1165 (ذمم فنادق شريكة) كان
    هيفضل متضخّم للأبد حتى بعد ما الفندق يدفع فعليًا. مفيش قيد لو الرصيد
    المستحق صفر أصلاً (عقد جديد لسه ما اتحاسبش عليه شهر، أو اتسوّى بالفعل).

    ⚠️ 3 باجات حقيقية اتصلحوا هنا (مراجعة Codex 2026-08-30، H-04):
    1. العقد كان بيتقرا من غير قفل — تسويتان متزامنتان لنفس العقد كان
       ممكن الاتنين يرحّلوا قيد تحصيل، وآخر واحد يكتب last_settled_at
       بيكسب بصمت (تحصيل مزدوج فعلي في الدفاتر).
    2. مفيش حد أعلى (`through`) على حساب الرصيد المستحق — تسوية بتاريخ
       معيّن كانت بتجمع كل الشهور المُرحَّلة **حتى المستقبلية**، مش تقف
       عند `settled_through` فعليًا.
    3. القيد كان بيترحّل عبر post_journal_entry (بتعمل commit داخلي)
       قبل تحديث last_settled_at بـcommit منفصل — فشل بينهم (كراش، خطأ
       شبكة) كان يسيب قيد تحصيل مُرحَّل فعليًا من غير أي علامة تسوية
       مقابلة، فالمرة الجاية outstanding يحسبه تاني ويرحّل قيد إضافي.
       دلوقتي عملية واحدة ذرية: القيد بيتبني بـflush بس (مش commit)،
       وlast_settled_at بيتحدّث في نفس الـtransaction، وcommit واحد
       بس في الآخر — إما الاتنين يحصلوا مع بعض أو ولا واحد."""
    from app.modules.finance import crud as finance_crud  # noqa: PLC0415
    from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate  # noqa: PLC0415
    from app.modules.finance.services import validate_period_open  # noqa: PLC0415

    contract = crud.lock_b2b_contract_for_update(db, contract_id)
    if not contract:
        raise ValueError(f"العقد {contract_id} غير موجود")
    settled_through = settled_through or _business_today()
    if settled_through > _business_today():
        raise ValueError("تاريخ التسوية لا يمكن أن يكون في المستقبل")
    if contract.last_settled_at and settled_through < contract.last_settled_at:
        raise ValueError("تاريخ التسوية لا يمكن أن يكون قبل آخر تسوية مسجّلة")

    outstanding = crud.get_b2b_outstanding_balance(
        db, contract_id, contract.last_settled_at, through=settled_through,
    )
    if outstanding > 0:
        settlement_account = finance_crud.get_account_by_code(db, contract.branch_id, settlement_account_code)
        receivable_account = finance_crud.get_account_by_code(db, contract.branch_id, "1165")
        if not settlement_account or not receivable_account:
            raise ValueError("حسابات التسوية أو ذمم الفنادق الشريكة غير معرّفة في دليل الحسابات")
        validate_period_open(db, contract.branch_id, settled_through)
        finance_crud.create_journal_entry(
            db,
            JournalEntryCreate(
                branch_id=contract.branch_id, entry_date=settled_through,
                reference=f"B2B-SETTLE-{contract.id}-{settled_through.isoformat()}",
                description=f"تسوية رصيد B2B — {contract.hotel_name}",
                source="beach_b2b_settlement", source_id=contract.id,
                lines=[
                    JournalLineCreate(account_id=settlement_account.id, debit=outstanding, credit=Decimal("0")),
                    JournalLineCreate(account_id=receivable_account.id, debit=Decimal("0"), credit=outstanding),
                ],
            ),
            user_id=0,
        )

    contract = crud.settle_b2b_contract(db, contract, settled_through)
    db.commit()
    db.refresh(contract)
    return contract


def post_b2b_monthly_fees(db: Session, today: Optional[date] = None) -> int:
    """يرحّل الرسم الشهري الثابت لكل عقد B2B نشط لسه ما ترحّلش له الشهر
    الحالي — الجزء القابل للاختبار من مهمة Celery الدورية (نفس نمط
    mark_b2b_contracts_overdue: دالة service خالصة بتاخد db + today وتُرجع
    عدد العقود اللي اترحّلها، والـ task نفسه بس wrapper حول SessionLocal +
    commit). idempotent على مستويين: B2BContractMonth.UniqueConstraint
    (contract_id, period_month) بيتحقق منه هنا قبل أي محاولة، وpost_taxed_
    sale_journal's فحص source/source_id/reference (لو الاتنين اتخطّوا لأي
    سبب، القيد نفسه برضو مايتكررش)."""
    from app.modules.finance.services import post_taxed_sale_journal  # noqa: PLC0415

    today = today or _business_today()
    month_start, month_end = _month_bounds(today)
    contracts = crud.list_active_b2b_contracts(db)
    billed = 0
    for contract in contracts:
        # العقد لازم يكون سارٍ في جزء على الأقل من الشهر ده — لو خلص خلاص
        # قبل بداية الشهر أو لسه ما بدأش لحد آخره، مفيش رسم يترحّل.
        if contract.valid_until < month_start or contract.valid_from > month_end:
            continue
        if crud.get_b2b_contract_month(db, contract.id, month_start):
            continue  # اترحّل بالفعل لهذا الشهر

        guests_count = crud.get_b2b_checked_in_count_for_month(db, contract.id, month_start, month_end)
        entry = post_taxed_sale_journal(
            db, contract.branch_id, today,
            debit_account_code="1165", revenue_account_code="4300",
            net_revenue_amount=contract.monthly_fee,
            reference=f"B2B-MONTHLY-{contract.id}-{month_start.isoformat()}",
            description=f"رسم شهري ثابت — {contract.hotel_name} ({month_start:%Y-%m})",
            source="beach_b2b_monthly", source_id=contract.id,
            cost_center_code="BEACH",
            commit_cost_centers=False,
        )
        crud.create_b2b_contract_month(
            db, contract.id, month_start, guests_count, contract.monthly_fee, entry.id,
        )
        billed += 1
    return billed


def mark_b2b_contracts_overdue(db: Session, today: Optional[date] = None) -> int:
    """يفحص كل عقود B2B النشطة ويُحدّث is_overdue حسب مهلة السداد
    (payment_terms_days) لكل عقد — الجزء القابل للاختبار من مهمة Celery
    الدورية (نفس نمط timeshare_tasks._mark_overdue: دالة service خالصة بتاخد
    db + today وتُرجع عدد العقود المتأثرة، والـ task نفسه بس wrapper حول
    SessionLocal + استدعاء الدالة دي). بيرسل تنبيه واتساب مرة واحدة بس لكل
    دخول في حالة التأخر (notified_overdue) — نفس نمط quota_warning في
    b2b_checkin، عشان مبعتش رسالة كل يوم للفندق طول ما لسه متأخر."""
    today = today or _business_today()
    contracts = crud.list_active_b2b_contracts(db)
    changed = 0
    for contract in contracts:
        oldest_unsettled = crud.get_b2b_oldest_unsettled_month(db, contract.id, contract.last_settled_at)
        overdue_now = is_contract_overdue(oldest_unsettled, today, contract.payment_terms_days)
        if overdue_now != contract.is_overdue:
            contract.is_overdue = overdue_now
            changed += 1
        if not overdue_now:
            contract.notified_overdue = False
            continue
        if not contract.notified_overdue:
            contract.notified_overdue = True
            if contract.contact_phone:
                try:
                    from app.core.kernel.whatsapp import send_whatsapp_message  # noqa: PLC0415
                    outstanding = crud.get_b2b_outstanding_balance(db, contract.id, contract.last_settled_at)
                    send_whatsapp_message(
                        contract.contact_phone,
                        f"تنبيه: رصيد {contract.hotel_name} المستحق للخيمة بيتش "
                        f"({outstanding:,.2f} ج.م) تخطّى مهلة السداد "
                        f"({contract.payment_terms_days} يوم) — برجاء التسوية.",
                    )
                except Exception:
                    pass  # ميمنعش تحديث حالة التأخر لو فشل إرسال التنبيه
    return changed


def check_in_reservation(
    db: Session, reservation_id: int, requesting_user, cashier_id: Optional[int] = None,
) -> "BeachReservation":
    """تسجيل دخول فوري لحجز شاطئ عبر مسح QR — يحوّل الحجز لعملية بيع حقيقية
    (يستهلك capacity/فوط زي أي تذكرة عادية) ويحدّث حالة الحجز لـ checked_in.

    Gate 1 containment (2026-07-17، BOLA/IDOR اتصلحت): get_cashier_user كان
    بيتحقق من مستوى الصلاحية بس، مش من الفرع — أي كاشير من أي فرع كان يقدر
    يسجّل دخول حجز فرع تاني بمجرد معرفة/تخمين رقمه.

    **تصحيح (جولة مراجعة Codex الثالثة):** requesting_user إجباري بلا أي
    default أو باب تخطٍ (internal_call اتشال بالكامل — مفيش أي caller
    إنتاجي حقيقي كان محتاجه، كان بس تسهيل لتستات الوحدة). تستات
    test_beach.py's TestQRCheckin بقت بتستخدم كاشير حقيقي مرتبط بالفرع
    (make_branch_linked_cashier) بدل أي bypass."""
    res = crud.get_reservation(db, reservation_id)
    if not res:
        raise ValueError(f"الحجز {reservation_id} غير موجود")
    from app.modules.core import services as core_services  # noqa: PLC0415

    core_services.assert_branch_access(db, requesting_user, res.branch_id, "تسجيل دخول حجز")
    if res.status == "checked_in":
        raise ValueError("تم تسجيل الدخول لهذا الحجز بالفعل")
    if res.status in ("cancelled", "no_show"):
        raise ValueError("هذا الحجز ملغى ولا يمكن تسجيل دخوله")

    sell_data = BeachSellRequest(
        tx_type="entry_towel" if res.with_towel else "entry",
        quantity=res.guests_count,
        cashier_id=cashier_id,
        notes=f"QR check-in — حجز #{res.id} ({res.guest_name})",
    )
    tx = sell_ticket(db, res.branch_id, sell_data)

    res = crud.update_reservation_status(db, res, "checked_in", tx_id=tx.id)
    db.commit()
    db.refresh(res)
    return res


def create_reservation(db: Session, data: BeachReservationCreate) -> "BeachReservation":
    # حساب التكلفة التقديرية
    base_prices = _get_base_prices(db, data.branch_id)
    tx_type = "entry_towel" if data.with_towel else "entry"
    unit_price = calculate_tx_price(tx_type, base_prices)
    total = unit_price * data.guests_count

    res = crud.create_reservation(db, data)
    res.total_amount = total
    db.flush()
    db.commit()
    db.refresh(res)
    return res


# ── Beach Locations (live map) ──────────────────────────────────────────

def list_locations(db: Session, branch_id: int, location_type: Optional[str] = None) -> list[BeachLocation]:
    return crud.list_locations(db, branch_id, location_type)


def bulk_add_locations(
    db: Session, branch_id: int, location_type: str, count: int,
) -> list[BeachLocation]:
    """يضيف ``count`` موقع جديد من نوع ``location_type`` — مرقّمين تلقائيًا
    بعد أعلى رقم موجود فعليًا (منسّق مع أي مواقع سابقة اتحذفت، مبيعيدش
    استخدام رقم اتحذف عشان ميتلخبطش مع تاريخ beach_transactions.location_id
    القديم)."""
    if not location_type.strip():
        raise ValueError("نوع الموقع مطلوب")
    start = crud.get_max_location_number(db, branch_id, location_type) + 1
    created = crud.bulk_create_locations(db, branch_id, location_type, count, start)
    db.commit()
    for loc in created:
        db.refresh(loc)
    return created


def bulk_remove_locations(
    db: Session, branch_id: int, location_type: str, count: int,
) -> list[BeachLocation]:
    """يحذف آخر ``count`` موقع *متاح* من نوع معيّن. لو أقل من ``count`` موقع
    متاح فعليًا (الباقي مشغول)، بيرفض العملية بالكامل بدل حذف جزئي غير متوقع
    — المدير لازم يشوف رسالة واضحة "X بس متاح" ويقرر بنفسه، مش نحذف عدد أقل
    بصمت من غير ما حد يلاحظ."""
    available = crud.get_removable_locations(db, branch_id, location_type, count)
    if len(available) < count:
        raise ValueError(
            f"مفيش إلا {len(available)} موقع متاح من نوع '{location_type}' — "
            f"مطلوب حذف {count}. المواقع المشغولة لازم تتفضّى (checkout) الأول."
        )
    crud.delete_locations(db, available)
    db.commit()
    return available


def update_location(
    db: Session, location_id: int,
    status: Optional[str] = None, grid_row: Optional[int] = None, grid_col: Optional[int] = None,
) -> BeachLocation:
    """تعديل مدير: تعطيل/تفعيل موقع (صيانة) أو نقل مكانه في الـ grid. رفض
    صريح لو حاول يحوّل موقع *مشغول* لـ out_of_service من غير ما الضيف
    يعمل checkout الأول — نفس فلسفة delete_location في الكود المرجعي، بس
    هنا "تعطيل" مش "حذف"."""
    loc = crud.get_location(db, location_id)
    if not loc:
        raise ValueError(f"الموقع {location_id} غير موجود")
    if status is not None:
        if status == "out_of_service" and loc.status == "occupied":
            raise ValueError(f"الموقع {loc.number} مشغول حاليًا — لازم checkout الأول قبل تعطيله")
        loc.status = status
    if grid_row is not None:
        loc.grid_row = grid_row
    if grid_col is not None:
        loc.grid_col = grid_col
    db.commit()
    db.refresh(loc)
    return loc


def checkin_location(
    db: Session, branch_id: int, location_id: int,
    data: BeachLocationCheckinRequest, cashier_id: Optional[int] = None,
    tx_date: Optional[date] = None,
) -> BeachLocation:
    """تسجيل دخول ضيف لموقع فعلي — بيقفل صف الموقع أولًا (SELECT FOR UPDATE
    NOWAIT، راجع _lock_location_or_raise) عشان يمنع double check-in، وبعدين
    بيبيع تذكرة دخول حقيقية عبر _sell_ticket_no_commit (نفس منطق sell_ticket
    العام بالظبط — تسعير/VAT/قيد محاسبي/CRM/Charge-to-Room، من غير أي تكرار
    كود) **من غير ما ده يعمل commit بينهم** — قفل الموقع، بيع التذكرة،
    وتحديث حالة الموقع كلهم بيتعمدوا (commit) مرة واحدة بس في الآخر، عشان
    القفل يفضل ماسك طول العملية كلها ولا يتفك بدري (لو استخدمنا sell_ticket
    العامة هنا، الـ commit بتاعها كان هيفك قفل الموقع قبل ما نحدّث حالته،
    وده بالظبط نوع سباق double-checkin اللي القفل ده متحط أصلاً عشان يمنعه)."""
    loc = crud.get_location(db, location_id)
    if not loc:
        raise ValueError(f"الموقع {location_id} غير موجود")
    if loc.branch_id != branch_id:
        raise ValueError(f"الموقع {location_id} لا ينتمي لهذا الفرع")

    loc = _lock_location_or_raise(db, loc)

    if loc.status == "out_of_service":
        raise ValueError(f"الموقع {loc.number} خارج الخدمة حاليًا")
    if loc.status == "occupied":
        raise BeachConcurrencyError(f"الموقع {loc.number} مشغول بالفعل")

    tx_type = "entry_towel" if data.with_towel else "entry"
    guest_label = f" — {data.guest_name}" if data.guest_name else ""
    sell_data = BeachSellRequest(
        tx_type=tx_type, quantity=data.guests_count, cashier_id=cashier_id,
        location_id=loc.id,
        notes=f"تشيك-إن موقع {loc.location_type} {loc.number}{guest_label}",
    )
    tx = _sell_ticket_no_commit(db, branch_id, sell_data, tx_date)

    loc.status = "occupied"
    loc.current_transaction_id = tx.id
    loc.guest_name = data.guest_name
    loc.guest_phone = data.guest_phone
    loc.guests_count = data.guests_count
    loc.towels_given = data.guests_count if data.with_towel else 0
    loc.checked_in_at = datetime.utcnow()
    loc.checked_in_by = cashier_id

    db.commit()
    db.refresh(loc)
    return loc


def checkout_location(
    db: Session, branch_id: int, location_id: int, cashier_id: Optional[int] = None,
    tx_date: Optional[date] = None,
) -> BeachLocation:
    """يفضّي موقع فعلي بعد ما الضيف يمشي — بيرجّع الفوط لمخزون اليوم (لو كان
    فيه) عبر تذكرة "towel_return" حقيقية (نفس تدفّق sell_ticket القياسي، مش
    تعديل مباشر على BeachInventory)، وبيصفّر بيانات الضيف على الموقع.

    ⚠️ قرار متعمد: checkout **مبيلمسش BeachInventory.capacity_used خالص** —
    الشاطئ هنا شغال بمنطق "تذكرة دخول يومية" (زي أي تذكرة تانية اتباعت من
    POS)، مش "حجز وقتي لمقعد بيتحرر لما الضيف يمشي". يعني لو موقع اتفضّى
    الساعة 2 الضهر، الشخص ده لسه محسوب ضمن "دخول اليوم" فعليًا — ده هو نفس
    سلوك النظام المرجعي (elkheima-beach-resort's map_checkout) ومتسق مع
    التصميم الحالي لـ BeachInventory في الموديول ده (راجع تعليق BeachLocation
    في models.py للتفاصيل الكاملة)."""
    loc = crud.get_location(db, location_id)
    if not loc:
        raise ValueError(f"الموقع {location_id} غير موجود")
    if loc.branch_id != branch_id:
        raise ValueError(f"الموقع {location_id} لا ينتمي لهذا الفرع")

    loc = _lock_location_or_raise(db, loc)

    if loc.status != "occupied":
        raise ValueError(f"الموقع {loc.number} مش مشغول حاليًا")

    if loc.towels_given > 0:
        return_data = BeachSellRequest(
            tx_type="towel_return", quantity=loc.towels_given, cashier_id=cashier_id,
            location_id=loc.id,
            notes=f"استرجاع فوط — checkout موقع {loc.location_type} {loc.number}",
        )
        _sell_ticket_no_commit(db, branch_id, return_data, tx_date)

    loc.status = "available"
    loc.current_transaction_id = None
    loc.guest_name = None
    loc.guest_phone = None
    loc.guests_count = 0
    loc.towels_given = 0
    loc.checked_in_at = None
    loc.checked_in_by = None

    db.commit()
    db.refresh(loc)
    return loc
