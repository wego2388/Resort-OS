"""app/modules/beach/services.py — Business logic"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.beach import crud
from app.modules.beach.models import BeachInventory, BeachLocation, BeachTransaction
from app.modules.beach.schemas import (
    B2BCheckinRequest, BeachLocationCheckinRequest, BeachReservationCreate,
    BeachSellRequest,
)
from app.resort_os.beach_engine import (
    B2BContractState,
    BeachInventoryState,
    calculate_b2b_price,
    calculate_inventory_delta,
    calculate_tx_price,
    is_contract_overdue,
    validate_b2b_checkin,
    validate_entry,
    would_exceed_credit_limit,
)

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


class BeachConcurrencyError(Exception):
    """عملية بيع/تشيك-إن تانية ماسكة صف سعة الشاطئ لنفس الفرع/اليوم دلوقتي، أو
    موقع فعلي (BeachLocation) مشغول بالفعل/بيتسجّل دخوله دلوقتي — 409، مش 400
    (زي pms.services.BookingConflictError بالظبط: بيغطّي الحالتين "القفل نفسه
    مشغول" و"الحالة التجارية بتاعت المصدر متعارضة" تحت نفس الاستثناء/الكود)."""


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
        return {
            "entry":          adult,
            "entry_child":    child,
            "entry_resident": resident,
            "entry_towel":    adult + towel,
            "towel_rent":     towel,
        }
    except Exception:
        return {
            "entry":          Decimal("200"),
            "entry_child":    Decimal("100"),
            "entry_resident": Decimal("150"),
            "entry_towel":    Decimal("250"),
            "towel_rent":     Decimal("50"),
        }


def get_base_prices(db: Session, branch_id: int) -> dict[str, Decimal]:
    """نسخة عامة من _get_base_prices — يستخدمها الـ router عشان يضيف الأسعار
    لرد GET /beach/inventory (باج حقيقي كان هنا: شاشة POS الشاطئ كانت مبنية
    على افتراض إن /beach/inventory بيرجّع adult_price/child_price/... جاهزة،
    بس الأسعار الحقيقية كانت متخزنة في جدول settings ومحسوبة سيرفر-سايد وقت
    البيع بس، مفيش أي endpoint كان بيرجّعها للفرونت إند قبل كده — يعني شاشة
    الشاطئ كانت بتعرض "NaN" في كل سعر لكل الوقت)."""
    return _get_base_prices(db, branch_id)


def _vat(amount: Decimal) -> Decimal:
    return (amount * Decimal(str(settings.VAT_PERCENTAGE)) / Decimal("100")).quantize(Decimal("0.01"))


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
    tx = _sell_ticket_no_commit(db, branch_id, data, tx_date)
    db.commit()
    db.refresh(tx)
    return tx


def _sell_ticket_no_commit(
    db: Session,
    branch_id: int,
    data: BeachSellRequest,
    tx_date: Optional[date] = None,
) -> BeachTransaction:
    """جسم sell_ticket الفعلي، من غير commit/refresh نهائي — مفصولة عشان
    checkin_location (تحت) تقدر تدمجها في transaction واحدة أطول (قفل موقع +
    بيع تذكرة + تحديث حالة الموقع) بدل ما تنادي sell_ticket العامة اللي
    بتعمل commit لوحدها وتُنهي الـ transaction بدري — لو حصل كده، قفل صف
    الموقع (SELECT FOR UPDATE) هيتفك بمجرد الـ commit ده قبل ما نتأكد إن
    تحديث حالة الموقع اتسجّل، وبيرجع نفس فئة سباق lost-update اللي القفل
    أصلاً اتحط عشان يمنعها."""
    tx_date = tx_date or _business_today()

    folio_id = data.folio_id
    if not folio_id and data.room_id:
        from app.modules.pms.services import find_active_folio_for_room  # noqa: PLC0415
        folio_id = find_active_folio_for_room(db, branch_id, data.room_id)
        if not folio_id:
            raise ValueError(f"مفيش ضيف مسجّل دخول في الغرفة {data.room_id} حاليًا")

    # جلب/إنشاء inventory + قفل الصف طول الـ transaction (راجع _lock_inventory_or_raise)
    inv_row = crud.get_or_create_inventory(db, branch_id, tx_date)
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
    # خصم مجموعة العميل الدائم — تلقائي بالكامل، بيتحسب على السعر الأصلي
    # قبل الـ VAT (نفس اتفاقية dining._customer_group_discount_amount).
    # الـ VAT بيتحسب على gross_total من غير خصم (زي dining بالظبط — الخصم
    # بيقلل الصافي المُحصَّل، مش بيغيّر الإقرار الضريبي على السعر المعلن).
    discount = _customer_group_discount_amount(db, data.customer_id, gross_total)
    vat      = _vat(gross_total)
    total    = max(Decimal("0"), gross_total - discount)

    # تحديث inventory
    cap_delta, towel_delta = calculate_inventory_delta(data.tx_type, data.quantity)
    crud.apply_inventory_delta(db, inv_row, cap_delta, towel_delta)

    # ربط العملية بوردية الكاشير المفتوحة (لو موجودة) — نفس الباترن المستخدم
    # في finance.services.add_payment، عشان مبيعات الشاطئ تظهر في تقرير نهاية
    # الوردية بدل ما تفضل غير مرتبطة بأي وردية.
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
        "folio_id":        folio_id,
        "b2b_contract_id": data.b2b_contract_id,
        "customer_id":     data.customer_id,
        "notes":           data.notes,
        "shift_id":        shift_id,
        "location_id":     data.location_id,
        "client_local_id": data.local_id,
    })

    # قيد الإيراد يترحّل فورًا في الحالتين — بس لحساب مختلف حسب طريقة الدفع:
    # كاش فوري → Dr Cash؛ محمّل على غرفة → Dr ذمم الفوليو (والكاش الحقيقي
    # بيتسجّل لاحقًا وقت تسوية الفوليو، راجع finance.services.add_payment).
    #
    # ⚠️ باج حقيقي كان هنا (اتصلح 2026-07-07، فجوة معمارية موثّقة في
    # CLAUDE.md §18): التعليق القديم هنا كان بيدّعي إن "الإيراد بيتسجّل وقت
    # تسوية الفوليو" — لكن التسوية (add_payment) عمرها ما كانت بترحّل أي
    # قيد خالص، يعني إيراد الشاطئ الحقيقي من كل عملية بيع محمّلة على غرفة
    # كان غايب تمامًا عن دفتر الأستاذ، نفس فئة الباج بالظبط في restaurant/cafe.
    if tx.folio_id:
        try:
            from app.modules.finance import crud as finance_crud  # noqa: PLC0415
            from app.modules.finance.schemas import FolioChargeCreate  # noqa: PLC0415
            finance_crud.add_charge(db, tx.folio_id, FolioChargeCreate(
                charge_type="beach",
                description=f"شاطئ — {tx.tx_type} × {tx.quantity}",
                amount=tx.total_amount,
                vat_amount=tx.vat_amount,
                posted_at=datetime.combine(tx.tx_date, datetime.min.time()),
                ref_beach_tx_id=tx.id,
            ))
            # ⚠️ باج حقيقي كان هنا (اتصلح 2026-07-04): نفس باج restaurant/cafe —
            # add_charge لوحدها بتضيف الصف بس مبتحدّثش Folio.total المخزّن.
            folio = finance_crud.get_folio(db, tx.folio_id)
            if folio:
                finance_crud.recalculate_folio_total(db, folio)
            _post_beach_folio_charge_journal(db, tx)
        except Exception:
            pass  # ميمنعش إتمام البيع لو فشل نشر الـ charge على الفوليو
    else:
        _post_beach_revenue_journal(db, tx)
    if tx.customer_id:
        from app.modules.crm.services import record_customer_visit  # noqa: PLC0415
        record_customer_visit(db, tx.customer_id, tx.total_amount + tx.vat_amount, tx.tx_date)

    return tx


def _post_beach_revenue_journal(db: Session, tx: "BeachTransaction") -> None:
    """Dr. Cash (1100) / Cr. Beach Revenue (4300) — دفع كاش فوري."""
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    post_simple_revenue_journal(
        db, tx.branch_id, tx.tx_date,
        debit_account_code="1100", credit_account_code="4300",
        amount=(tx.total_amount or Decimal("0")) + (tx.vat_amount or Decimal("0")),
        reference=f"BCH-{tx.id:06d}" if tx.id else "BCH-NEW",
        description=f"إيرادات شاطئ — {tx.tx_type}",
        source="beach", source_id=tx.id,
    )


def _post_beach_folio_charge_journal(db: Session, tx: "BeachTransaction") -> None:
    """Dr. ذمم الفوليو (1150) / Cr. إيراد الشاطئ (4300) — عملية محمّلة على
    فوليو غرفة. راجع restaurant.services._post_order_folio_charge_journal
    للتفاصيل الكاملة — نفس المنطق بالظبط."""
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    post_simple_revenue_journal(
        db, tx.branch_id, tx.tx_date,
        debit_account_code="1150", credit_account_code="4300",
        amount=(tx.total_amount or Decimal("0")) + (tx.vat_amount or Decimal("0")),
        reference=f"BCH-{tx.id:06d}" if tx.id else "BCH-NEW",
        description=f"إيرادات شاطئ (محمّل على الغرفة) — {tx.tx_type}",
        source="beach_folio_charge", source_id=tx.id,
    )


def _contract_state(contract_row: "B2BContract", checked_in_today: int) -> B2BContractState:
    """يبني B2BContractState من صف B2BContract — نقطة واحدة عشان أي حقل
    جديد (زي valid_from/valid_until) يتضاف مرة واحدة بس، مش يتكرر في 3 أماكن."""
    return B2BContractState(
        contract_id=contract_row.id,
        hotel_name=contract_row.hotel_name,
        daily_quota=contract_row.daily_quota,
        checked_in_today=checked_in_today,
        entry_price=contract_row.entry_price,
        towel_price=contract_row.towel_price,
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
    tx_date = tx_date or _business_today()

    contract_row = crud.get_b2b_contract(db, data.contract_id)
    if not contract_row:
        raise ValueError(f"العقد {data.contract_id} غير موجود")

    contract_day = crud.get_or_create_contract_day(db, data.contract_id, tx_date)
    contract_day = _lock_contract_day_or_raise(db, contract_day)
    contract_state = _contract_state(contract_row, contract_day.checked_in_count)

    validation = validate_b2b_checkin(contract_state, data.guests_count, tx_date)
    if not validation.valid:
        raise ValueError(validation.error)

    # التحقق من inventory — نفس قفل الصف المستخدم في sell_ticket
    inv_row = crud.get_or_create_inventory(db, branch_id, tx_date)
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

    total = calculate_b2b_price(contract_state, data.guests_count, data.with_towel)
    vat   = _vat(total)

    # تحقق من حد الائتمان — قبل أي تعديل فعلي على inventory/checked_in_count
    # عشان لو اتخطى الحد، محدش يتأثر ولا يتحتاج عكس. راجع تعليق B2BContract
    # في models.py: حد ائتمان صريح (مش None) معناه مدير الإيرادات قرر عمدًا
    # إن الفندق ده يستاهل حد أقصى للرصيد المستحق — تخطيه لازم يترفض بوضوح
    # (زي استنفاد الحصة اليومية بالظبط)، مش يتحول لمجرد تحذير صامت ممكن حد
    # يتجاهله تحت ضغط الشغل (نفس فئة الأخطاء الصامتة اللي اتصلحت في موديولات
    # تانية قبل كده في هذا المشروع). المقارنة على أساس `total` (قبل الضريبة)
    # مش `total + vat` — عشان تفضل متسقة مع B2BContractDay.total_amount نفسه
    # (نفس العمود اللي بيتجمع منه outstanding_balance وبيُعرض كـ "إيراد B2B"
    # في اللوحة الحيّة أصلاً)، مش رقم تاني بمعنى مختلف شوية.
    if contract_row.credit_limit is not None:
        outstanding = crud.get_b2b_outstanding_balance(db, data.contract_id, contract_row.last_settled_at)
        if would_exceed_credit_limit(outstanding, total, contract_row.credit_limit):
            raise ValueError(
                f"تخطّى حد الائتمان لعقد {contract_row.hotel_name} — "
                f"الرصيد المستحق حاليًا {outstanding:,.2f} ج.م + هذه العملية "
                f"{total:,.2f} ج.م هيتعدّى الحد المسموح "
                f"{contract_row.credit_limit:,.2f} ج.م. سوّي الحساب مع الفندق "
                f"أو ارفع حد الائتمان من شاشة إدارة عقود B2B قبل المتابعة."
            )

    cap_delta, towel_delta = calculate_inventory_delta(tx_type, data.guests_count)
    crud.apply_inventory_delta(db, inv_row, cap_delta, towel_delta)

    crud.increment_b2b_checkins(db, data.contract_id, tx_date, data.guests_count, total)

    # تحذير الحصة (warning إذا بقي ≤ 5) — لازم يتحسب على العدد بعد الزيادة
    # (increment_b2b_checkins فوق)، وإلا التحذير كان هيتأخر تسجيل دخول واحد
    # كامل عن اللحظة الفعلية اللي الحصة توصل فيها للحد (باج توقيت حقيقي).
    updated_day = crud.get_or_create_contract_day(db, data.contract_id, tx_date)
    updated_state = _contract_state(contract_row, updated_day.checked_in_count)
    if updated_state.quota_warning and not updated_day.notified_quota_warning:
        updated_day.notified_quota_warning = True
        db.flush()
        if contract_row.contact_phone:
            try:
                from app.core.kernel.whatsapp import send_whatsapp_message  # noqa: PLC0415
                send_whatsapp_message(
                    contract_row.contact_phone,
                    f"تنبيه: حصة {contract_row.hotel_name} اليومية في الخيمة بيتش أوشكت على الانتهاء (≤5 متبقي).",
                )
            except Exception:
                pass  # ميمنعش إتمام تسجيل الدخول لو فشل إرسال التنبيه

    tx = crud.create_transaction(db, {
        "branch_id":       branch_id,
        "tx_type":         tx_type,
        "quantity":        data.guests_count,
        "unit_price":      contract_row.entry_price,
        "total_amount":    total,
        "vat_amount":      vat,
        "surge_applied":   False,
        "tx_date":         tx_date,
        "cashier_id":      data.cashier_id,
        "b2b_contract_id": data.contract_id,
    })

    _post_beach_revenue_journal(db, tx)

    db.commit()
    db.refresh(tx)
    return tx


def void_transaction(db: Session, tx_id: int, voided_by: int, reason: str) -> BeachTransaction:
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

    # عكس الـ inventory
    inv_row = crud.get_or_create_inventory(db, tx.branch_id, tx.tx_date)
    cap_delta, towel_delta = calculate_inventory_delta(tx.tx_type, tx.quantity)
    crud.apply_inventory_delta(db, inv_row, -cap_delta, -towel_delta)

    # عكس الأثر المالي — نفس التفرّع اللي حصل وقت sell_ticket بالظبط
    if tx.folio_id:
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

    # عكس رصيد B2B المستحق لو العملية كانت تشيك-إن فندق شريك — راجع تعليق
    # crud.decrement_b2b_checkins: باج حقيقي كان هنا قبل إضافة حد الائتمان
    # (الإلغاء كان بيعكس كل حاجة إلا رصيد الفندق نفسه).
    if tx.b2b_contract_id:
        crud.decrement_b2b_checkins(db, tx.b2b_contract_id, tx.tx_date, tx.quantity, tx.total_amount)

    tx = crud.void_transaction(db, tx, voided_by, reason)
    db.commit()
    db.refresh(tx)
    return tx


def _post_beach_revenue_reversal_journal(db: Session, tx: "BeachTransaction") -> None:
    """عكس _post_beach_revenue_journal بالظبط — Dr. Beach Revenue (4300) /
    Cr. Cash (1100) — بيلغي أثر قيد البيع الأصلي في الدفاتر."""
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    post_simple_revenue_journal(
        db, tx.branch_id, _business_today(),
        debit_account_code="4300", credit_account_code="1100",
        amount=(tx.total_amount or Decimal("0")) + (tx.vat_amount or Decimal("0")),
        reference=f"BCH-VOID-{tx.id:06d}",
        description=f"إلغاء عملية شاطئ — {tx.tx_type}",
        source="beach_void", source_id=tx.id,
    )


def _post_beach_folio_charge_reversal_journal(db: Session, tx: "BeachTransaction") -> None:
    """عكس _post_beach_folio_charge_journal — Dr. إيراد الشاطئ (4300) /
    Cr. ذمم الفوليو (1150)."""
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    post_simple_revenue_journal(
        db, tx.branch_id, _business_today(),
        debit_account_code="4300", credit_account_code="1150",
        amount=(tx.total_amount or Decimal("0")) + (tx.vat_amount or Decimal("0")),
        reference=f"BCH-VOID-{tx.id:06d}",
        description=f"إلغاء عملية شاطئ (محمّل على الغرفة) — {tx.tx_type}",
        source="beach_folio_void", source_id=tx.id,
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
        ("ضريبة القيمة", f"{tx.vat_amount:,.2f} EGP"),
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
    """حالة حصص/ائتمان كل فنادق B2B النشطة اليوم — بيوصل quota_warning
    (≤5 أشخاص متبقين) من beach_engine.B2BContractState + حالة الائتمان
    (outstanding_balance/credit_limit/is_overdue) لنفس اللوحة الحيّة، بنفس
    نمط عرض العقود المنتهية (is_valid_today) اللي اتضاف قبل كده."""
    day = day or _business_today()
    rows = crud.list_b2b_contracts_with_today_usage(db, branch_id, day)

    result = []
    for contract, checked_in_today in rows:
        state = _contract_state(contract, checked_in_today)
        outstanding = crud.get_b2b_outstanding_balance(db, contract.id, contract.last_settled_at)
        result.append({
            "contract_id":        state.contract_id,
            "hotel_name":         state.hotel_name,
            "daily_quota":        state.daily_quota,
            "checked_in_today":   state.checked_in_today,
            "remaining_quota":    state.remaining_quota,
            "is_quota_exhausted": state.is_quota_exhausted,
            "quota_warning":      state.quota_warning,
            "is_valid_today":     state.is_valid_on(day),
            "credit_limit":       contract.credit_limit,
            "outstanding_balance": outstanding,
            "credit_exceeded":    (
                contract.credit_limit is not None and outstanding > contract.credit_limit
            ),
            "is_overdue":         contract.is_overdue,
            "payment_terms_days": contract.payment_terms_days,
        })
    return result


def settle_b2b_contract(
    db: Session, contract_id: int, settled_through: Optional[date] = None,
) -> "B2BContract":
    """يسجّل تسوية (تحصيل) رصيد الفندق الشريك — يُستدعى لما الفندق يدفع
    فاتورته الدورية. بيصفّر الرصيد المستحق فعليًا لحد تاريخ التسوية وبيلغي
    علم التأخر."""
    contract = crud.get_b2b_contract(db, contract_id)
    if not contract:
        raise ValueError(f"العقد {contract_id} غير موجود")
    settled_through = settled_through or _business_today()
    if contract.last_settled_at and settled_through < contract.last_settled_at:
        raise ValueError("تاريخ التسوية لا يمكن أن يكون قبل آخر تسوية مسجّلة")
    contract = crud.settle_b2b_contract(db, contract, settled_through)
    db.commit()
    db.refresh(contract)
    return contract


def mark_b2b_contracts_overdue(db: Session, today: Optional[date] = None) -> int:
    """يفحص كل عقود B2B النشطة ويُحدّث is_overdue حسب مهلة السداد
    (payment_terms_days) لكل عقد — الجزء القابل للاختبار من مهمة Celery
    الدورية (نفس نمط timeshare_tasks._mark_overdue: دالة service خالصة بتاخد
    db + today وتُرجع عدد العقود المتأثرة، والـ task نفسه بس wrapper حول
    SessionLocal + استدعاء الدالة دي). بيرسل تنبيه واتساب مرة واحدة بس لكل
    دخول في حالة التأخر (notified_overdue) — نفس نمط quota_warning في
    b2b_checkin، عشان مبعتش رسالة كل يوم للفندق طول ما لسه متأخر."""
    today = today or _business_today()
    contracts = crud.list_active_b2b_contracts_for_overdue_check(db)
    changed = 0
    for contract in contracts:
        oldest_unsettled = crud.get_b2b_oldest_unsettled_day(db, contract.id, contract.last_settled_at)
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
    db: Session, reservation_id: int, cashier_id: Optional[int] = None,
) -> "BeachReservation":
    """تسجيل دخول فوري لحجز شاطئ عبر مسح QR — يحوّل الحجز لعملية بيع حقيقية
    (يستهلك capacity/فوط زي أي تذكرة عادية) ويحدّث حالة الحجز لـ checked_in."""
    res = crud.get_reservation(db, reservation_id)
    if not res:
        raise ValueError(f"الحجز {reservation_id} غير موجود")
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
