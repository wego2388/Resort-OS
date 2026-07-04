"""app/modules/beach/services.py — Business logic"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.beach import crud
from app.modules.beach.models import BeachInventory, BeachTransaction
from app.modules.beach.schemas import (
    B2BCheckinRequest, BeachReservationCreate, BeachSellRequest,
)
from app.resort_os.beach_engine import (
    B2BContractState,
    BeachInventoryState,
    calculate_b2b_price,
    calculate_inventory_delta,
    calculate_tx_price,
    validate_b2b_checkin,
    validate_entry,
)


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


def sell_ticket(
    db: Session,
    branch_id: int,
    data: BeachSellRequest,
    tx_date: Optional[date] = None,
) -> BeachTransaction:
    tx_date = tx_date or date.today()

    folio_id = data.folio_id
    if not folio_id and data.room_id:
        from app.modules.pms.services import find_active_folio_for_room  # noqa: PLC0415
        folio_id = find_active_folio_for_room(db, branch_id, data.room_id)
        if not folio_id:
            raise ValueError(f"مفيش ضيف مسجّل دخول في الغرفة {data.room_id} حاليًا")

    # جلب/إنشاء inventory
    inv_row = crud.get_or_create_inventory(db, branch_id, tx_date)
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
    total       = unit_price * data.quantity
    vat         = _vat(total)

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
        "vat_amount":      vat,
        "surge_applied":   surge_pct > 0,
        "tx_date":         tx_date,
        "cashier_id":      data.cashier_id,
        "folio_id":        folio_id,
        "b2b_contract_id": data.b2b_contract_id,
        "customer_id":     data.customer_id,
        "notes":           data.notes,
        "shift_id":        shift_id,
    })

    # قيد الإيراد بس لو مفيش folio (كاش فوري) — لو محمّل على غرفة، بننشر
    # charge على الفوليو بدل ما نسجّل إيراد فوري، والإيراد بيتسجّل وقت
    # تسوية الفوليو كله عند خروج الضيف (نفس منطق restaurant/cafe)
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
        except Exception:
            pass  # ميمنعش إتمام البيع لو فشل نشر الـ charge على الفوليو
    else:
        _post_beach_revenue_journal(db, tx)
    if tx.customer_id:
        from app.modules.crm.services import record_customer_visit  # noqa: PLC0415
        record_customer_visit(db, tx.customer_id, tx.total_amount + tx.vat_amount, tx.tx_date)

    db.commit()
    db.refresh(tx)
    return tx


def _post_beach_revenue_journal(db: Session, tx: "BeachTransaction") -> None:
    """Dr. Cash (1100) / Cr. Beach Revenue (4300)."""
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    post_simple_revenue_journal(
        db, tx.branch_id, tx.tx_date,
        debit_account_code="1100", credit_account_code="4300",
        amount=(tx.total_amount or Decimal("0")) + (tx.vat_amount or Decimal("0")),
        reference=f"BCH-{tx.id:06d}" if tx.id else "BCH-NEW",
        description=f"إيرادات شاطئ — {tx.tx_type}",
        source="beach", source_id=tx.id,
    )


def b2b_checkin(
    db: Session,
    branch_id: int,
    data: B2BCheckinRequest,
    tx_date: Optional[date] = None,
) -> BeachTransaction:
    tx_date = tx_date or date.today()

    contract_row = crud.get_b2b_contract(db, data.contract_id)
    if not contract_row:
        raise ValueError(f"العقد {data.contract_id} غير موجود")

    contract_day = crud.get_or_create_contract_day(db, data.contract_id, tx_date)
    contract_state = B2BContractState(
        contract_id=contract_row.id,
        hotel_name=contract_row.hotel_name,
        daily_quota=contract_row.daily_quota,
        checked_in_today=contract_day.checked_in_count,
        entry_price=contract_row.entry_price,
        towel_price=contract_row.towel_price,
        is_active=contract_row.is_active,
    )

    validation = validate_b2b_checkin(contract_state, data.guests_count)
    if not validation.valid:
        raise ValueError(validation.error)

    # التحقق من inventory
    inv_row = crud.get_or_create_inventory(db, branch_id, tx_date)
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

    cap_delta, towel_delta = calculate_inventory_delta(tx_type, data.guests_count)
    crud.apply_inventory_delta(db, inv_row, cap_delta, towel_delta)

    crud.increment_b2b_checkins(db, data.contract_id, tx_date, data.guests_count, total)

    # تحذير الحصة (warning إذا بقي ≤ 5) — لازم يتحسب على العدد بعد الزيادة
    # (increment_b2b_checkins فوق)، وإلا التحذير كان هيتأخر تسجيل دخول واحد
    # كامل عن اللحظة الفعلية اللي الحصة توصل فيها للحد (باج توقيت حقيقي).
    updated_day = crud.get_or_create_contract_day(db, data.contract_id, tx_date)
    updated_state = B2BContractState(
        contract_id=contract_row.id,
        hotel_name=contract_row.hotel_name,
        daily_quota=contract_row.daily_quota,
        checked_in_today=updated_day.checked_in_count,
        entry_price=contract_row.entry_price,
        towel_price=contract_row.towel_price,
        is_active=contract_row.is_active,
    )
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
    else:
        _post_beach_revenue_reversal_journal(db, tx)

    tx = crud.void_transaction(db, tx, voided_by, reason)
    db.commit()
    db.refresh(tx)
    return tx


def _post_beach_revenue_reversal_journal(db: Session, tx: "BeachTransaction") -> None:
    """عكس _post_beach_revenue_journal بالظبط — Dr. Beach Revenue (4300) /
    Cr. Cash (1100) — بيلغي أثر قيد البيع الأصلي في الدفاتر."""
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    post_simple_revenue_journal(
        db, tx.branch_id, date.today(),
        debit_account_code="4300", credit_account_code="1100",
        amount=(tx.total_amount or Decimal("0")) + (tx.vat_amount or Decimal("0")),
        reference=f"BCH-VOID-{tx.id:06d}",
        description=f"إلغاء عملية شاطئ — {tx.tx_type}",
        source="beach_void", source_id=tx.id,
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
    inv_date = inv_date or date.today()
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
    report_date = report_date or date.today()
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
    """حالة حصص كل فنادق B2B النشطة اليوم — بيوصل quota_warning (≤5 أشخاص متبقين)
    من beach_engine.B2BContractState اللي كان موجود بس مش متوصّل لأي endpoint."""
    day = day or date.today()
    rows = crud.list_b2b_contracts_with_today_usage(db, branch_id, day)

    result = []
    for contract, checked_in_today in rows:
        state = B2BContractState(
            contract_id=contract.id,
            hotel_name=contract.hotel_name,
            daily_quota=contract.daily_quota,
            checked_in_today=checked_in_today,
            entry_price=contract.entry_price,
            towel_price=contract.towel_price,
            is_active=contract.is_active,
        )
        result.append({
            "contract_id":        state.contract_id,
            "hotel_name":         state.hotel_name,
            "daily_quota":        state.daily_quota,
            "checked_in_today":   state.checked_in_today,
            "remaining_quota":    state.remaining_quota,
            "is_quota_exhausted": state.is_quota_exhausted,
            "quota_warning":      state.quota_warning,
        })
    return result


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
