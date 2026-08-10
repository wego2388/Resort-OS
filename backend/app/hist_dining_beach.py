"""HIST-01 — مولّد بيانات الدايننج والشاطئ التاريخية ليوليو 2026 (OPS-DATA-02
§10.4). بيستخدم services الحقيقية بس (open_shift/create_order/
add_items_to_order/settle_order/void_order_item/refund_order_item/
apply_order_discount/close_shift/sell_ticket/b2b_checkin/void_transaction)
— صفر SQL مباشر.

⚠️ قرارات نطاق موثّقة صراحةً (نفس مبدأ hist_leasing.py/hist_timeshare.py):
- "5% حساب شخصي" (personal credit) من مزيج طرق الدفع في §10.4 مؤجَّل —
  محتاج إعداد عميل CRM بحد ائتمان منفصل، خارج نطاق دفعة الدايننج/الشاطئ
  الأساسية دي. المزيج المطبَّق فعليًا: cash/card/room بس، بنسب تقريبية
  (مش هدف صارم — §10.4 نفسها بتقول "المستهدف" مش رقم إلزامي).
- الطاقم (كاشيرين) مش موجود بعد (مولّد HR/الموظفين لسه ما اتبناش) — الملف
  ده بينشئ كاشيرين اصطناعيين (2) خاصين بيه، موثّق كاعتماد ذاتي الاكتفاء
  زي باقي المولّدات.
- "الدفع على حساب الغرفة" (room charge) بيحاول يلاقي فوليو حقيقي مفتوح
  (لو pms_bookings module اشتغل قبله في نفس الدفعة) — لو مفيش، بيتخطى
  السيناريو ده بهدوء (مسجَّل في العدادات) بدل ما يفشل.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from zoneinfo import ZoneInfo

from app.resort_os.clock import scenario_clock

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.operational_history_seed import ScenarioContext

_RESTAURANT_ORDERS = 110   # × 1500.00 = 165,000.00
_CAFE_ORDERS = 80          # × 1500.00 = 120,000.00
_BEACH_TRANSACTIONS = 110  # × 1200.00 = 132,000.00
_SHIFTS_PER_DAY = 2
# ⚠️ "card"/"wallet" مش مُهيّئين محاسبيًا افتراضيًا (settings.
# DINING_CARD_SETTLEMENT_ACCOUNT/DINING_WALLET_SETTLEMENT_ACCOUNT — إعداد
# نشر deployment-level، لا يصح لمولّد بيانات يفرضه برمجيًا). المزيج هنا
# اتحصر عمدًا في cash (المُهيَّأ افتراضيًا دايمًا) — راجع docstring الملف
# لبند "5% حساب شخصي"/"30% كارت" المؤجَّل لنفس السبب.
_TENDER_CYCLE = ("cash",)


@dataclass
class _RunningState:
    counts: dict = field(default_factory=lambda: {
        "restaurant_orders": 0, "cafe_orders": 0, "beach_transactions": 0,
        "shifts_closed": 0, "voids": 0, "refunds": 0, "discounts": 0,
        "split_tender_orders": 0, "room_charge_orders": 0,
        "b2b_checkins": 0, "beach_voids": 0, "variance_shifts": 0,
    })
    tender_index: int = 0


def generate(db: "Session", ctx: "ScenarioContext") -> dict:
    from app.core.kernel.models.user import User, UserRole
    from app.core.kernel.security import get_password_hash
    from app.modules.beach import crud as beach_crud, services as beach_services
    from app.modules.beach.schemas import B2BCheckinRequest, B2BContractCreate, BeachSellRequest
    from app.modules.dining import services as dining_services
    from app.modules.dining.schemas import OrderCreate, OrderItemCreate, OutletCreate, DiningItemCreate
    from app.modules.finance import services as finance_services
    from app.modules.pms.models import Booking, BookingRoom
    from app.modules.finance.schemas import CashierShiftClose, CashierShiftOpen

    branch_id = ctx.branch_id
    tz = ZoneInfo(ctx.tz_name)
    year, month = ctx.period_year, ctx.period_month
    month_start = date(year, month, 1)
    days_in_month = calendar.monthrange(year, month)[1]
    if ctx.period_end_day is not None:
        days_in_month = min(days_in_month, ctx.period_end_day)
    state = _RunningState()

    with scenario_clock(datetime(year, month, 1, 6, 0, tzinfo=tz)):
        cashier1 = User(
            email=f"hist-cashier1-{branch_id}@resort.invalid",
            password_hash=get_password_hash("hist01-synthetic-not-for-login"),
            full_name="كاشير HIST-1", role=UserRole.CASHIER, is_active=True,
        )
        cashier2 = User(
            email=f"hist-cashier2-{branch_id}@resort.invalid",
            password_hash=get_password_hash("hist01-synthetic-not-for-login"),
            full_name="كاشير HIST-2", role=UserRole.CASHIER, is_active=True,
        )
        db.add_all([cashier1, cashier2])
        db.flush()

        restaurant = dining_services.create_outlet(db, OutletCreate(
            branch_id=branch_id, name="Restaurant HIST", name_ar="مطعم HIST",
            outlet_type="restaurant", revenue_account_code="4200",
        ))
        cafe = dining_services.create_outlet(db, OutletCreate(
            branch_id=branch_id, name="Cafe HIST", name_ar="كافيه HIST",
            outlet_type="cafe", revenue_account_code="4400",
        ))
        from app.modules.dining import crud as dining_crud
        restaurant_item = dining_crud.create_item(db, DiningItemCreate(
            branch_id=branch_id, outlet_id=restaurant.id, name="وجبة HIST",
            name_ar="وجبة HIST", price=Decimal("300.00"), station="hot",
        ))
        cafe_item = dining_crud.create_item(db, DiningItemCreate(
            branch_id=branch_id, outlet_id=cafe.id, name="مشروب HIST",
            name_ar="مشروب HIST", price=Decimal("250.00"), station="bar",
        ))
        db.flush()

        b2b_contract = beach_crud.create_b2b_contract(db, B2BContractCreate(
            branch_id=branch_id, hotel_name="HIST Partner Hotel",
            hotel_name_ar="فندق شريك HIST", daily_quota=50,
            entry_price=Decimal("180.00"), towel_price=Decimal("0"),
            valid_from=month_start, valid_until=date(year + 1, month, 1),
        ))
        db.flush()

    # فوليو حقيقي مفتوح لضيف checked_in فعليًا (لو pms_bookings اشتغل قبل
    # كده في نفس الدفعة) — لـ"الدفع على حساب الغرفة" (راجع docstring
    # الملف). ⚠️ باج حقيقي اتصلح هنا (اتكشف وقت Phase 8 Local apply ضد
    # PostgreSQL حقيقي — مش SQLite tests): dining.services.settle_order's
    # "room" tender محتاج charge_to_room_id = Room.id فعليًا (بيستخدمه في
    # find_active_folio_for_room(db, branch_id, room_id) عشان يلاقي
    # الفوليو بنفسه)، مش Folio.id مباشرة زي ما كان مكتوب هنا. في تستات
    # SQLite الأصلية كان Folio.id بيتساوي بالصدفة برقم Room.id صغير
    # (بيانات قليلة، IDs متتالية من واحد) فالباج كان مستخبي — أول تشغيلة
    # حقيقية ضد قاعدة فيها حجوزات/فواتير أكتر (Folio.id="34" مثلاً) كشفته
    # فورًا: "مفيش ضيف مسجّل دخول في الغرفة 34".
    open_booking = (
        db.query(Booking)
        .filter(Booking.branch_id == branch_id, Booking.status == "checked_in",
                Booking.folio_id.isnot(None))
        .first()
    )
    open_folio_room_id = (
        db.query(BookingRoom.room_id).filter(BookingRoom.booking_id == open_booking.id).scalar()
        if open_booking else None
    )

    restaurant_remaining = _RESTAURANT_ORDERS
    cafe_remaining = _CAFE_ORDERS
    beach_remaining = _BEACH_TRANSACTIONS
    global_order_index = 0
    global_beach_index = 0

    total_shifts = days_in_month * _SHIFTS_PER_DAY
    for shift_no in range(total_shifts):
        day_offset, half = divmod(shift_no, _SHIFTS_PER_DAY)
        the_day = month_start + timedelta(days=day_offset)
        shift_hour = 8 if half == 0 else 16
        cashier = cashier1 if shift_no % 2 == 0 else cashier2

        with scenario_clock(datetime(the_day.year, the_day.month, the_day.day, shift_hour, 0, tzinfo=tz)):
            shift = finance_services.open_shift(db, cashier.id, cashier.id, CashierShiftOpen(
                branch_id=branch_id, opening_float=Decimal("500.00"),
            ))

            # عدد أوردرات/معاملات هذه الوردية — توزيع تقريبي متساوٍ على
            # الورديات الـ62، بالباقي بيتجمّع في آخر ورديات كل نوع.
            shifts_left = total_shifts - shift_no
            r_this_shift = min(restaurant_remaining, -(-restaurant_remaining // shifts_left))
            c_this_shift = min(cafe_remaining, -(-cafe_remaining // shifts_left))
            b_this_shift = min(beach_remaining, -(-beach_remaining // shifts_left))

            for _ in range(r_this_shift):
                global_order_index += 1
                _run_dining_order(
                    db, dining_services, OrderCreate, OrderItemCreate,
                    branch_id, restaurant.id, restaurant_item.id, qty=5,
                    order_no=global_order_index, cashier_id=cashier.id, state=state,
                    open_folio_room_id=open_folio_room_id, outlet_kind="restaurant_orders",
                )
                restaurant_remaining -= 1

            for _ in range(c_this_shift):
                global_order_index += 1
                _run_dining_order(
                    db, dining_services, OrderCreate, OrderItemCreate,
                    branch_id, cafe.id, cafe_item.id, qty=6,
                    order_no=global_order_index, cashier_id=cashier.id, state=state,
                    open_folio_room_id=open_folio_room_id, outlet_kind="cafe_orders",
                )
                cafe_remaining -= 1

            for _ in range(b_this_shift):
                global_beach_index += 1
                _run_beach_transaction(
                    db, beach_services, BeachSellRequest, branch_id,
                    tx_no=global_beach_index, cashier_id=cashier.id, state=state,
                )
                beach_remaining -= 1

            # B2B check-in — أول ورديتين بس (2 نداء إجمالًا، خارج هدف
            # الـ132,000 الأساسي — راجع docstring الملف).
            if shift_no < 2:
                beach_services.b2b_checkin(db, branch_id, B2BCheckinRequest(
                    contract_id=b2b_contract.id, guests_count=4, with_towel=False,
                    cashier_id=cashier.id,
                ))
                state.counts["b2b_checkins"] += 1

            report = finance_services.build_shift_end_report(db, shift.id)
            counted = report.expected_cash
            if shift_no in (10, 40):  # فرقين صغيرين موثّقين — راجع §10.4
                counted = counted + Decimal("15.00")
                state.counts["variance_shifts"] += 1
            finance_services.close_shift(db, shift.id, cashier.id, CashierShiftClose(
                counted_cash=counted,
            ))
            state.counts["shifts_closed"] += 1

    return {
        "counts": state.counts,
        "totals": {
            "restaurant_gross": str(Decimal(_RESTAURANT_ORDERS) * Decimal("1500.00")),
            "cafe_gross": str(Decimal(_CAFE_ORDERS) * Decimal("1500.00")),
            "beach_gross": str(Decimal(_BEACH_TRANSACTIONS) * Decimal("1200.00")),
        },
    }


def _next_tender(state: _RunningState) -> str:
    method = _TENDER_CYCLE[state.tender_index % len(_TENDER_CYCLE)]
    state.tender_index += 1
    return method


def _run_dining_order(
    db, dining_services, OrderCreate, OrderItemCreate,
    branch_id: int, outlet_id: int, item_id: int, qty: int,
    order_no: int, cashier_id: int, state: _RunningState,
    open_folio_room_id, outlet_kind: str,
) -> None:
    order = dining_services.create_order(db, branch_id, OrderCreate(
        outlet_id=outlet_id, order_type="dine_in",
        items=[OrderItemCreate(item_id=item_id, quantity=qty)],
    ), waiter_id=cashier_id)
    state.counts[outlet_kind] += 1

    # سيناريو 1: خصم (PIN مش لازم — acting_user_level=100 نفس اتفاقية أي
    # نداء داخلي موثوق، راجع services.apply_order_discount).
    if order_no == 1:
        dining_services.apply_order_discount(db, order.id, applied_by=cashier_id, acting_user_level=100)
        state.counts["discounts"] += 1

    # سيناريو 2: إلغاء صنف قبل التسوية.
    if order_no == 2:
        dining_services.void_order_item(
            db, order.id, order.items[0].id, reason="HIST-01 demo void",
            voided_by=cashier_id, acting_user_level=100,
        )
        state.counts["voids"] += 1
        return  # الطلب بقى بلا أصناف فعلية — مفيش تسوية له

    if order_no == 50 and open_folio_room_id is not None:
        # سيناريو "الدفع على حساب الغرفة" — charge_to_room_id لازم يكون
        # Room.id حقيقي (settle_order بيستخدمه في find_active_folio_for_
        # room داخليًا)، مش Folio.id (راجع الباج الموثّق في generate()).
        dining_services.settle_order(
            db, order.id,
            tenders=[{"method": "room", "amount": None, "charge_to_room_id": open_folio_room_id}],
            settled_by=cashier_id,
        )
        state.counts["room_charge_orders"] += 1
        return

    if order_no == 60:
        # سيناريو split tender — مبلغين منفصلين (نفس الطريقة، كاش) بيغطّوا
        # الإجمالي — بيمرّن مسار "أكتر من tender واحد" الفعلي (settle_order
        # بيتحقق إن مجموعهم يساوي order.total بالظبط)، من غير الاعتماد على
        # "card" غير المُهيَّأ محاسبيًا افتراضيًا (راجع docstring الملف).
        half = (order.total / 2).quantize(Decimal("0.01"))
        other_half = order.total - half
        dining_services.settle_order(
            db, order.id, tenders=[
                {"method": "cash", "amount": half}, {"method": "cash", "amount": other_half},
            ],
            settled_by=cashier_id,
        )
        state.counts["split_tender_orders"] += 1
        return

    method = _next_tender(state)
    dining_services.settle_order(
        db, order.id, tenders=[{"method": method, "amount": None}], settled_by=cashier_id,
    )

    if order_no == 70:
        # سيناريو refund — بعد التسوية
        dining_services.refund_order_item(
            db, order.id, order.items[0].id, reason="HIST-01 demo refund", refunded_by=cashier_id,
        )
        state.counts["refunds"] += 1


def _run_beach_transaction(
    db, beach_services, BeachSellRequest, branch_id: int,
    tx_no: int, cashier_id: int, state: _RunningState,
) -> None:
    tx = beach_services.sell_ticket(db, branch_id, BeachSellRequest(
        tx_type="entry", quantity=6, cashier_id=cashier_id, payment_method="cash",
    ))
    state.counts["beach_transactions"] += 1
    if tx_no == 5:
        beach_services.void_transaction(db, tx.id, voided_by=cashier_id, reason="HIST-01 demo void")
        state.counts["beach_voids"] += 1
