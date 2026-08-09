"""app/modules/pms/services.py — Business logic"""
from __future__ import annotations

import logging

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)
from sqlalchemy.orm import Session

from app.modules.pms import crud
from app.modules.pms.models import Booking, NightAuditLog, RatePlan, RoomType
from app.modules.pms.schemas import BookingCreate, EarlyLateRequest, RatePlanCreate, RatePlanUpdate


class BookingConflictError(Exception):
    """غرفة محجوزة فعلاً أو ماسكاها transaction تانية الآن — 409، مش 400."""


def get_booking_or_404(db: Session, booking_id: int) -> Booking:
    b = crud.get_booking(db, booking_id)
    if not b:
        raise ValueError(f"الحجز {booking_id} غير موجود")
    return b


def _resolve_rate_plan(db: Session, data: BookingCreate, nights: int) -> Optional["RatePlan"]:
    """يتحقق من صلاحية خطة الأسعار المطلوبة (لو اتبعتت) قبل أي قفل غرف —
    مفيش داعي نقفل حاجة لو الخطة نفسها مش سارية. باج "الموديل موجود، الـ
    API صفر" حقيقي كان هنا: RatePlan كان عنده model + crud + router كامل
    (اتوصّل اليوم) بس create_booking عمرها ما كانت بتستخدمه — كل حجز كان
    بيتسعّر بـ room_type.base_rate الخام دايمًا، يعني مستحيل فعليًا تطبّق
    سعر موسم عالي/عرض خاص من غير ما تغيّر base_rate نفسه يدويًا لكل الغرف."""
    if not data.rate_plan_id:
        return None

    plan = crud.get_rate_plan(db, data.rate_plan_id)
    if not plan:
        raise ValueError(f"خطة الأسعار {data.rate_plan_id} غير موجودة")
    if plan.branch_id != data.branch_id:
        raise ValueError("خطة الأسعار لا تنتمي لهذا الفرع")
    if not plan.is_active:
        raise ValueError(f"خطة الأسعار '{plan.name}' غير مفعّلة")
    if data.check_in < plan.valid_from or data.check_out > plan.valid_until:
        raise ValueError(
            f"خطة الأسعار '{plan.name}' سارية فقط من {plan.valid_from} إلى {plan.valid_until}"
        )
    if nights < plan.min_nights:
        raise ValueError(f"خطة الأسعار '{plan.name}' تتطلب حجز {plan.min_nights} ليالٍ على الأقل")
    return plan


def _room_rate_for(
    room_type: "RoomType | None",
    plan: "RatePlan | None",
    room_type_id: int,
) -> Decimal | None:
    """السعر اليومي الفعلي لغرفة معيّنة: سعر الخطة (override أو multiplier)
    لو الخطة سارية وعامة (room_type_id=None) أو مطابقة لنوع الغرفة دي بالظبط،
    وإلا السعر الأساسي الخام لنوع الغرفة."""
    base = room_type.base_rate if room_type else None
    if plan and (plan.room_type_id is None or plan.room_type_id == room_type_id):
        if plan.base_rate_override is not None:
            return plan.base_rate_override
        if base is None:
            return None
        return (base * plan.rate_multiplier).quantize(Decimal("0.01"))
    return base


def _validate_rate_plan_dates(valid_from: date, valid_until: date) -> None:
    if valid_until <= valid_from:
        raise ValueError("valid_until يجب أن يكون بعد valid_from")


def _validate_room_type_branch(
    db: Session,
    room_type_id: Optional[int],
    branch_id: int,
) -> Optional[RoomType]:
    """Reject cross-branch room-type links before a row is written."""
    if room_type_id is None:
        return None
    room_type = crud.get_room_type(db, room_type_id)
    if not room_type or room_type.branch_id != branch_id:
        raise ValueError("نوع الغرفة لا ينتمي لهذا الفرع")
    return room_type


def create_rate_plan(db: Session, data: RatePlanCreate) -> RatePlan:
    """إنشاء خطة أسعار موسمية — راجع models.RatePlan/_resolve_rate_plan
    للتفاصيل الكاملة عن كيفية تأثيرها على سعر الحجز الفعلي."""
    _validate_rate_plan_dates(data.valid_from, data.valid_until)
    _validate_room_type_branch(db, data.room_type_id, data.branch_id)
    plan = crud.create_rate_plan(db, data)
    db.commit()
    db.refresh(plan)
    return plan


def update_rate_plan(db: Session, plan_id: int, data: RatePlanUpdate) -> RatePlan:
    """تعديل خطة أسعار موجودة — بما في ذلك إلغاء تفعيلها (is_active=False).
    التحقق من valid_from/valid_until بيراعي القيم الجديدة المرسلة *أو* القيم
    الحالية لو الحقل مش متضمّن في الطلب (تحديث جزئي)."""
    plan = crud.get_rate_plan(db, plan_id)
    if not plan:
        raise ValueError(f"خطة الأسعار {plan_id} غير موجودة")

    new_valid_from = data.valid_from if data.valid_from is not None else plan.valid_from
    new_valid_until = data.valid_until if data.valid_until is not None else plan.valid_until
    _validate_rate_plan_dates(new_valid_from, new_valid_until)
    if "room_type_id" in data.model_fields_set:
        _validate_room_type_branch(db, data.room_type_id, plan.branch_id)

    plan = crud.update_rate_plan(db, plan, data)
    db.commit()
    db.refresh(plan)
    return plan


def create_booking(db: Session, data: BookingCreate) -> Booking:
    # التحقق من التواريخ
    if data.check_out <= data.check_in:
        raise ValueError("check_out يجب أن يكون بعد check_in")

    nights = (data.check_out - data.check_in).days

    if data.customer_id is not None:
        from app.modules.crm.models import Customer  # noqa: PLC0415

        customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
        if not customer or customer.branch_id != data.branch_id:
            raise ValueError("العميل لا ينتمي لهذا الفرع")

    # تحقق من خطة الأسعار (لو اتبعتت) قبل أي قفل غرف
    rate_plan = _resolve_rate_plan(db, data, nights)

    # ترتيب ثابت لقفل الغرف — يمنع deadlock بين حجزين متزامنين بنفس الغرف
    # بترتيب مختلف
    ordered_room_ids = sorted(set(data.room_ids))

    # SELECT FOR UPDATE NOWAIT على كل غرفة قبل أي تحقق — لو غرفة تانية
    # ماسكاها transaction شغالة دلوقتي، تطلع OperationalError فوراً بدل
    # ما الاتنين يعدّوا التحقق وين يتصادموا على الـ INSERT (race condition
    # كلاسيكي بين SELECT availability والـ INSERT).
    locked_rooms = {}
    for room_id in ordered_room_ids:
        try:
            locked = crud.lock_room_for_booking(db, room_id)
        except OperationalError:
            db.rollback()
            raise BookingConflictError(f"الغرفة {room_id} مقفولة الآن من عملية حجز أخرى — حاول مرة أخرى")
        if not locked:
            raise ValueError(f"الغرفة {room_id} غير موجودة")
        locked_rooms[room_id] = locked

    # التحقق من الغرف والتوفر — بعد القفل، فمفيش حد تاني يقدر يحجز نفس
    # الغرفة لحد ما الـ transaction دي تخلص (commit/rollback). available_ids
    # و room_type cache متجهزين مرة واحدة برّه الحلقة — كانوا بيتعادوا لكل
    # غرفة (نفس الاستعلام بالظبط لـ get_available_rooms، وget_room_type
    # ممكن يتكرر لو أكتر من غرفة نفس النوع).
    available_ids = {
        r.id for r in crud.get_available_rooms(db, data.branch_id, data.check_in, data.check_out)
    }
    room_type_cache: dict[int, RoomType] = {}
    room_rates: list[tuple[int, Decimal, int, Optional[int]]] = []
    for room_id in ordered_room_ids:
        room = locked_rooms[room_id]
        if room.branch_id != data.branch_id:
            raise ValueError(f"الغرفة {room_id} لا تنتمي لهذا الفرع")

        if room_id not in available_ids:
            raise BookingConflictError(f"الغرفة {room.name} غير متاحة في هذه الفترة")

        room_type = room_type_cache.get(room.room_type_id)
        if room_type is None:
            room_type = crud.get_room_type(db, room.room_type_id)
            if room_type:
                room_type_cache[room.room_type_id] = room_type
        if not room_type or room_type.branch_id != data.branch_id:
            raise ValueError(f"نوع الغرفة المرتبط بالغرفة {room_id} لا ينتمي لهذا الفرع")
        applies = rate_plan and (rate_plan.room_type_id is None or rate_plan.room_type_id == room.room_type_id)
        daily_rate = _room_rate_for(room_type, rate_plan, room.room_type_id)
        if daily_rate is None:
            raise ValueError(
                f"لم يتم تحديد سعر للغرفة {room.name}؛ اعتمد سعر النوع أو خطة سعر قبل الحجز"
            )
        room_rates.append((room_id, daily_rate, nights, rate_plan.id if applies else None))

    booking_number = crud.generate_booking_number(db, data.branch_id)
    booking = crud.create_booking(db, booking_number, data, room_rates)

    # تحديث حالة الغرف → reserved — بنستخدم locked_rooms الموجودة بالفعل
    # (نفس الصفوف المقفولة فوق) بدل ما نعيد نداء get_room لكل غرفة تاني.
    for room_id, _, _, _ in room_rates:
        crud.update_room_status(db, locked_rooms[room_id], "reserved")

    db.commit()
    db.refresh(booking)
    return booking


def checkin_booking(
    db: Session,
    booking_id: int,
    id_number: Optional[str] = None,
    payment_method: Optional[str] = None,
) -> Booking:
    booking = get_booking_or_404(db, booking_id)
    if booking.status != "confirmed":
        raise ValueError(f"لا يمكن تسجيل الدخول لحجز بحالة '{booking.status}'")

    booking = crud.update_booking_status(db, booking, "checked_in")

    # حفظ رقم الهوية لو موجود (EncryptedString — بيتخزن مشفّر)
    if id_number:
        booking.guest_national_id = id_number

    # حفظ طريقة الدفع المتوقعة للمحاسبة
    if payment_method:
        booking.payment_method = payment_method

    # تحديث حالة الغرف → occupied
    for br in booking.rooms:
        room = crud.get_room(db, br.room_id)
        if room:
            crud.update_room_status(db, room, "occupied")

    # فتح Folio للحجز لو مفيش واحد بالفعل — ده اللي بيسمح للضيف "يحمّل على
    # حسابه" مشتريات من موديولات تانية (مطعم/شاطئ/كافيه) طول إقامته، وتتحاسب
    # كلها مع بعض وقت الخروج بدل ما كل قسم ياخد كاش منفصل (Charge to Room).
    if not booking.folio_id:
        from app.modules.finance.crud import create_folio  # noqa: PLC0415
        from app.modules.finance.schemas import FolioCreate  # noqa: PLC0415
        folio = create_folio(db, FolioCreate(
            branch_id=booking.branch_id,
            guest_name=booking.guest_name,
            check_in=datetime.combine(booking.check_in, datetime.min.time()),
            check_out=datetime.combine(booking.check_out, datetime.min.time()),
        ))
        booking.folio_id = folio.id

    # ⚠️ مقصودًا مفيش قيد إيراد هنا عند check-in. الإيراد بيتسجّل تدريجيًا
    # يوميًا في run_night_audit (Dr.1150/Cr.4100 لكل ليلة إقامة فعلية) —
    # ده هو الاعتراف المحاسبي الوحيد بالإيراد. قيد check-in منفصل كان بيسجّل
    # نفس المبلغ مرتين (باج حقيقي اتصلح 2026-07-26: كان بيحط total_rate
    # كامل هنا **زيادة** على ما يسجّله Night Audit يوميًا، فإيراد الغرف كان
    # بيتضاعف تقريبًا لأي إقامة بتعدّي دورة Night Audit واحدة على الأقل،
    # وذمم الفوليو 1150 كانت بتفضل عندها رصيد متبقي دايم بعد كل checkout
    # لأن checkout_booking بيسوّي بس قيمة total_rate مرة واحدة). راجع §18
    # في CLAUDE.md — التصميم النهائي (تمييز إيراد التايم شير عن إيراد
    # الحجز الفندقي في نفس الحساب) لسه محتاج مراجعة صريحة مع Mohamed.

    db.commit()
    db.refresh(booking)
    return booking


def find_active_folio_for_room(db: Session, branch_id: int, room_id: int) -> Optional[int]:
    """يرجّع folio_id الحجز الـ checked_in حاليًا في الغرفة دي، لو موجود —
    الأساس اللي بتقوم عليه "الدفع على حساب الغرفة" في موديولات تانية (مطعم/
    شاطئ/كافيه): الموظف يديله رقم الغرفة، والنظام يلاقي فوليو الضيف المقيم
    فيها ويحمّل عليه بدل ما ياخد كاش فورًا."""
    from app.modules.pms.models import BookingRoom  # noqa: PLC0415
    booking = (
        db.query(Booking)
        .join(BookingRoom, BookingRoom.booking_id == Booking.id)
        .filter(
            Booking.branch_id == branch_id,
            Booking.status == "checked_in",
            BookingRoom.room_id == room_id,
        )
        .first()
    )
    return booking.folio_id if booking else None


def checkout_booking(db: Session, booking_id: int) -> Booking:
    booking = get_booking_or_404(db, booking_id)
    if booking.status != "checked_in":
        raise ValueError(f"لا يمكن تسجيل الخروج — الحجز يجب أن يكون checked_in (الحالة الحالية: '{booking.status}')")

    booking = crud.update_booking_status(db, booking, "checked_out")

    # تحديث حالة الغرف → checkout_pending ثم HousekeepingTask
    for br in booking.rooms:
        room = crud.get_room(db, br.room_id)
        if room:
            crud.update_room_status(db, room, "checkout_pending")
            crud.create_housekeeping_task(db, {
                "branch_id": booking.branch_id,
                "room_id":   room.id,
                "task_type": "checkout_clean",
                "status":    "dirty",
                "priority":  "high",
            })

    # Revenue Journal Entry + تحديث إحصائيات العميل (لو مربوط بعميل CRM)
    _post_checkout_journal(db, booking)
    if booking.customer_id:
        from app.modules.crm.services import record_customer_visit  # noqa: PLC0415
        record_customer_visit(db, booking.customer_id, booking.total_rate, booking.check_out)

    # ⚠️ باج "الموديل موجود، الـ API صفر" حقيقي كان هنا: GuestProfile
    # (ملف ضيف مجمّع بالهاتف عبر كل الإقامات) كان عنده crud كامل موصوف بالتعليق
    # "يُحدَّث عند كل checkout" — بس checkout_booking (هنا بالظبط) عمرها ما
    # كانت بتنادي عليه، يعني الجدول كان فاضي 100% من أول ما اتعمل الموديل.
    if booking.guest_phone:
        from app.modules.crm.crud import (  # noqa: PLC0415
            get_or_create_guest_profile, update_guest_profile_on_checkout,
        )
        get_or_create_guest_profile(db, booking.branch_id, booking.guest_phone, {
            "full_name":   booking.guest_name,
            "email":       booking.guest_email,
            "national_id": booking.guest_national_id,
        })
        update_guest_profile_on_checkout(db, booking.branch_id, booking.guest_phone, booking.total_rate or Decimal("0"))

    db.commit()
    db.refresh(booking)
    return booking


def _post_checkout_journal(db: "Session", booking: "Booking") -> None:
    """تسوية الذمة عند مغادرة الضيف: Dr. كاش/بنك (1100/1110) / Cr. ذمم الفوليو (1150).

    الإيراد (Cr. 4100) يُسجَّل يومياً في Night Audit بـ Dr.1150/Cr.4100.
    checkout_booking يُسوّي الذمة فقط — بيسدد ما سبق تسجيله تراكمياً
    طوال الإقامة. ده هو السلوك الصح في أي PMS (Opera/Mews/Cloudbeds).

    حساب الخصم يتحدد من booking.payment_method (كاش→1100، كارت→1110،
    حوالة→1120). لو مش محدد أو غير معروف: 1100 كافتراضي.

    ⚠️ باج حقيقي اتصلح (2026-08-09، تأكيد صريح من محمد: "الاستقبال بيحصّل
    كل حاجة مرة واحدة وقت الخروج"): كانت التسوية بتقفل بس `booking.
    total_rate` (سعر الغرفة + أي رسوم وصول مبكر/مغادرة متأخرة، اللي
    request_early_late بتضيفها لنفس الحقل مباشرة) — أي "شحن على حساب
    الغرفة" من الشاطئ/الدايننج (`FolioCharge.charge_type` = beach/dining،
    كل واحد منها عنده قيد إيراد منفصل خاص بيه اتسجّل وقت الشحن نفسه) كان
    بيفضل قايم في حساب 1150 للأبد بعد الـcheckout، بصمت. دلوقتي بنجمع أي
    شحنة beach/dining لسه مش settled على فوليو الحجز ونضيفها لمبلغ
    التسوية، ونقفل الفوليو (`is_settled`/`status=closed`) عشان يعكس إن كل
    حاجة اتحصّلت فعليًا. **مفيش استدعاء لـ finance.services.settle_folio**
    عمدًا — `can_checkout` فيها بترفض أي فوليو عليه شحنة أصلاً (unsettled_
    amount>0 قبل ما أي حاجة تتسوّى)، يعني الدالة دي مش موصولة بأي مسار
    حقيقي فعليًا (فجوة منفصلة تمامًا، برّه نطاق الإصلاح ده).
    """
    from decimal import Decimal as _D  # noqa: PLC0415
    from app.core.config import settings  # noqa: PLC0415
    from app.modules.finance import crud as finance_crud  # noqa: PLC0415
    from app.modules.finance.models import FolioCharge  # noqa: PLC0415
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415
    from app.resort_os.timezone_utils import local_today  # noqa: PLC0415

    extra_folio_charges_total = _D("0")
    if booking.folio_id:
        # lock_folio_for_update بلوكينج (مش NOWAIT) — نفس القفل اللي
        # add_folio_charge بتاخده قبل أي شحنة جديدة (beach/dining "charge
        # to room"). لو شحنة شغالة دلوقتي بالظبط، الـcheckout هنا بينتظرها
        # تخلص الأول بدل ما ياخد صورة ناقصة للفوليو ويقفله فوقها.
        folio = finance_crud.lock_folio_for_update(db, booking.folio_id)
        if folio:
            unsettled = (
                db.query(FolioCharge)
                .filter(FolioCharge.folio_id == folio.id, FolioCharge.is_settled.is_(False))
                .all()
            )
            for charge in unsettled:
                if charge.charge_type in ("beach", "dining"):
                    extra_folio_charges_total += (
                        charge.amount + (charge.vat_amount or _D("0")) + (charge.service_charge or _D("0"))
                    )
                # room_extra متضمّن بالفعل في booking.total_rate — مش بيتضاف
                # تاني هنا، بس بيتعلّم settled زي باقي الشحنات.
                charge.is_settled = True
            finance_crud.close_folio(db, folio)

    total_amount = (booking.total_rate or _D("0")) + extra_folio_charges_total

    # اختيار حساب القبض حسب طريقة دفع الضيف المسجّلة عند check-in
    _METHOD_TO_ACCOUNT = {
        "cash":          "1100",
        "card":          "1110",
        "bank_transfer": "1110",  # حوالة بنكية → نفس حساب البنك/كارت
        "room":          "1150",  # edge-case: محمّل على فوليو تاني
    }
    debit_code = _METHOD_TO_ACCOUNT.get(booking.payment_method or "cash", "1100")

    description = f"تسوية فوليو — {booking.booking_number}"
    if extra_folio_charges_total > 0:
        description += f" (شامل {extra_folio_charges_total:.2f} ج شحن على الغرفة)"

    post_simple_revenue_journal(
        db, booking.branch_id, local_today(settings.TIMEZONE),
        debit_account_code=debit_code,
        credit_account_code="1150",   # Cr. ذمم الفوليو — تسوية ما سبق تسجيله
        amount=total_amount,
        reference=f"CHK-{booking.booking_number}",
        description=description,
        source="pms", source_id=booking.id,
        cost_center_code="ROOM",
    )


def request_early_late(db: Session, booking_id: int, data: "EarlyLateRequest") -> Booking:
    """تسجيل وصول مبكر أو مغادرة متأخرة.

    - بيحفظ early_checkin_at / late_checkout_at على الحجز
    - لو data.charge > 0: بيضيف FolioCharge على فوليو الضيف تلقائياً
      حتى تُحاسَب مع باقي مصاريف إقامته وقت الـ checkout
    - بيسمح بالاستدعاء أكثر من مرة (update) — آخر قيمة تفوز
    """
    booking = get_booking_or_404(db, booking_id)
    if booking.status not in ("confirmed", "checked_in"):
        raise ValueError(f"لا يمكن تعديل مواعيد حجز بحالة '{booking.status}'")

    if data.early_checkin_at:
        booking.early_checkin_at = data.early_checkin_at
    if data.late_checkout_at:
        booking.late_checkout_at = data.late_checkout_at

    if data.charge and data.charge > 0:
        booking.extra_charge = (booking.extra_charge or Decimal("0")) + data.charge
        booking.total_rate   = (booking.total_rate   or Decimal("0")) + data.charge

        # أضف شحنة على الفوليو لو مفتوح
        if booking.folio_id:
            from app.modules.finance import services as finance_services  # noqa: PLC0415
            from app.modules.finance.schemas import FolioChargeCreate  # noqa: PLC0415
            label_parts = []
            if data.early_checkin_at:
                label_parts.append(f"وصول مبكر {data.early_checkin_at.strftime('%H:%M')}")
            if data.late_checkout_at:
                label_parts.append(f"مغادرة متأخرة {data.late_checkout_at.strftime('%H:%M')}")
            label = " + ".join(label_parts) or "رسوم إضافية"
            # add_folio_charge بتقفل صف الفوليو (blocking) قبل الإدخال
            # وتعيد حساب الإجمالي من قراءة طازة — راجع Gate 1B.
            # ⚠️ مراجعة Codex الثانية: كان فيه except Exception يبتلع الفشل
            # بعد ما يسجّله بس — يعني تعديل الحجز (extra_charge/total_rate)
            # كان بيتسجّل ويتقفل بـcommit حتى لو الفوليو مقفول/فشلت الشحنة،
            # يعني رسوم إضافية على الحجز من غير أي شحنة فوليو مقابلة. دلوقتي
            # fail-closed **مع rollback صريح**: مجرد عدم عمل commit مش كافي
            # (الصفوف المعدّلة/flushed بتفضل مرئية على أي جلسة تانية على
            # نفس الـconnection لحد rollback حقيقي — اتكشف فعليًا وقت كتابة
            # اختبار الأثر الجانبي)، فلازم rollback صريح هنا.
            try:
                # ⚠️ باج حقيقي مستقل اتكشف هنا (مراجعة Codex الثانية، Gate
                # 1B): posted_at كان غايب تمامًا من النداء ده — يعني
                # FolioChargeCreate كانت بترفض بـ ValidationError في **كل**
                # مرة، بس الـexcept القديم (اللي كان بيبتلع الفشل بعد
                # التسجيل بس) كان بيغطي الفشل ده تمامًا. النتيجة: مفيش أي
                # رسوم وصول مبكر/مغادرة متأخرة اتسجّلت كـFolioCharge حقيقية
                # في الإنتاج من أول ما الميزة دي اتعملت — الحجز كان بيتحدّث
                # (extra_charge/total_rate) لكن الفوليو نفسه كان يفضل زي ما
                # هو. اتصلح بإضافة posted_at (نفس نمط beach/dining).
                finance_services.add_folio_charge(db, booking.folio_id, FolioChargeCreate(
                    description=label,
                    amount=data.charge,
                    charge_type="room_extra",
                    posted_at=datetime.utcnow(),
                    ref_order_id=None,
                ))
            except Exception:
                db.rollback()
                raise

    if data.notes and booking.notes:
        booking.notes = booking.notes + "\n" + data.notes
    elif data.notes:
        booking.notes = data.notes

    db.commit()
    db.refresh(booking)
    return booking


def cancel_booking(db: Session, booking_id: int, cancelled_by: int) -> Booking:
    booking = get_booking_or_404(db, booking_id)
    if booking.status in ("checked_out", "cancelled"):
        raise ValueError(f"لا يمكن إلغاء حجز بحالة '{booking.status}'")

    booking = crud.update_booking_status(db, booking, "cancelled", cancelled_by=cancelled_by)

    # إعادة الغرف للحالة available
    for br in booking.rooms:
        room = crud.get_room(db, br.room_id)
        if room and room.status in ("reserved", "occupied"):
            crud.update_room_status(db, room, "available")

    db.commit()
    db.refresh(booking)
    return booking


def update_housekeeping_task_status(
    db: Session, task_id: int, new_status: str,
    notes: Optional[str] = None, assigned_to: Optional[int] = None,
):
    """يحدّث حالة مهمة تنظيف — dirty → cleaning → inspecting → available.
    لما توصل available، بيرجّع الغرفة نفسها لـ available تلقائياً (خلصت
    من دورة checkout_pending اللي بدأت في checkout_booking). assigned_to
    (wagdy.md P-12) بيتحدّث بشكل مستقل عن status لو اتبعت — تعيين موظف
    مش لازم يترافق مع تغيير حالة."""
    task = crud.get_housekeeping_task(db, task_id)
    if not task:
        raise ValueError(f"مهمة التنظيف {task_id} غير موجودة")

    room = crud.get_room(db, task.room_id)
    if not room or room.branch_id != task.branch_id:
        raise ValueError("الغرفة المرتبطة بمهمة التنظيف لا تنتمي لنفس الفرع")

    if assigned_to is not None:
        from app.modules.hr.models import Employee  # noqa: PLC0415

        employee = db.query(Employee).filter(Employee.id == assigned_to).first()
        if not employee or employee.branch_id != task.branch_id:
            raise ValueError("الموظف المعيّن لا ينتمي لفرع مهمة التنظيف")

    update_data: dict = {"status": new_status}
    if notes is not None:
        update_data["notes"] = notes
    if assigned_to is not None:
        update_data["assigned_to"] = assigned_to
    if new_status == "cleaning" and not task.started_at:
        update_data["started_at"] = datetime.utcnow()
    if new_status == "available":
        update_data["completed_at"] = datetime.utcnow()

    task = crud.update_housekeeping_task(db, task, update_data)

    if new_status == "available":
        if room.status in ("checkout_pending", "maintenance"):
            crud.update_room_status(db, room, "available")

    db.commit()
    db.refresh(task)
    return task


def run_night_audit(db: Session, branch_id: int, audit_date: date) -> NightAuditLog:
    """
    Night Audit — يُشغَّل تلقائياً عند 00:01 بواسطة Celery.
    يمكن استدعاؤه يدوياً من الـ API.
    """
    existing = crud.get_night_audit(db, branch_id, audit_date)
    if existing and existing.status == "completed":
        raise ValueError(f"Night Audit ليوم {audit_date} مكتمل مسبقاً")

    stats = crud.get_bookings_for_night_audit(db, branch_id, audit_date)
    total_rooms = crud.count_rooms(db, branch_id)
    occupancy_pct = (
        Decimal(str(stats["occupied_rooms"])) / Decimal(str(total_rooms)) * 100
        if total_rooms > 0 else Decimal("0")
    ).quantize(Decimal("0.01"))

    data = {
        **stats,
        "total_rooms":   total_rooms,
        "occupancy_pct": occupancy_pct,
        "status":        "completed",
        "completed_at":  datetime.utcnow(),
        "summary_json":  json.dumps(
                             {**{k: float(v) if isinstance(v, Decimal) else v
                                 for k, v in stats.items()},
                              "total_rooms": total_rooms,
                              "occupancy_pct": float(occupancy_pct)},
                             ensure_ascii=False),
    }

    if existing:
        log = crud.update_night_audit(db, existing, data)
    else:
        log = crud.create_night_audit(db, branch_id, audit_date, data)

    # mark no-shows
    if stats["no_shows"] > 0:
        _mark_no_shows(db, branch_id, audit_date)

    # ── Room Revenue Posting ─────────────────────────────────────────────
    # Night Audit يُثبّت إيراد الغرف لليوم المنتهي (Dr. AR Guests 1150 /
    # Cr. Room Revenue 4100) لكل حجز checked_in — ده القيد المحاسبي اليومي
    # الأساسي في أي PMS (يقابل "Room Revenue Post" في Opera/Mews/Cloudbeds).
    # ⚠️ بيستخدم بيانات BookingRoom.daily_rate المخزّنة — نفس الأرقام اللي
    # حسبها get_bookings_for_night_audit (stats["room_revenue"]) — ومش ينشئ
    # نسخة تانية من نفس القيد لو run_night_audit اتعمل مرتين بالغلط
    # (مضمون بـ "Night Audit ليوم X مكتمل مسبقاً" فوق).
    _post_room_revenue_for_night_audit(db, branch_id, audit_date, stats["room_revenue"])

    db.commit()
    db.refresh(log)
    return log


def _mark_no_shows(db: Session, branch_id: int, check_in_date: date) -> None:
    """يُحوّل الحجوزات التي لم تصل في يوم الدخول إلى no_show."""
    rows = (
        db.query(Booking)
        .filter(
            Booking.branch_id == branch_id,
            Booking.check_in == check_in_date,
            Booking.status == "confirmed",
        )
        .all()
    )
    for booking in rows:
        crud.update_booking_status(db, booking, "no_show")
        for br in booking.rooms:
            room = crud.get_room(db, br.room_id)
            if room:
                crud.update_room_status(db, room, "available")
    if rows:
        db.flush()


def _post_room_revenue_for_night_audit(
    db: Session, branch_id: int, audit_date: "date", total_revenue: Decimal
) -> None:
    """يُسجّل قيد إيراد الغرف اليومي وقت Night Audit.

    Dr. ذمم الضيوف (1150) / Cr. إيراد الغرف (4100)
    المبلغ = مجموع daily_rate لكل الحجوزات checked_in في audit_date.
    لو مفيش إيراد (لا توجد غرف مشغولة) مش بيسجّل قيد فارغ.
    بيبتلع الأخطاء عمدًا عشان فشل القيد ميمنعش إتمام الـ Night Audit —
    لكن بيسجّل error في الـ log عشان المحاسب يعرف ويصحح يدوياً.
    """
    if not total_revenue or total_revenue <= 0:
        return
    try:
        from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415
        post_simple_revenue_journal(
            db, branch_id, audit_date,
            debit_account_code="1150", credit_account_code="4100",
            amount=total_revenue,
            reference=f"AUDIT-{audit_date.strftime('%Y%m%d')}",
            description=f"إيراد غرف — Night Audit {audit_date}",
            source="pms_night_audit", source_id=None,
            cost_center_code="ROOM",
        )
    except Exception:
        logger.error(
            "_post_room_revenue_for_night_audit فشل — branch=%s date=%s revenue=%.2f — القيد يحتاج تسجيل يدوي",
            branch_id, audit_date, float(total_revenue), exc_info=True,
        )
