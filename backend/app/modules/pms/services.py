"""app/modules/pms/services.py — Business logic"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.modules.pms import crud
from app.modules.pms.models import Booking, NightAuditLog
from app.modules.pms.schemas import BookingCreate


class BookingConflictError(Exception):
    """غرفة محجوزة فعلاً أو ماسكاها transaction تانية الآن — 409، مش 400."""


def get_booking_or_404(db: Session, booking_id: int) -> Booking:
    b = crud.get_booking(db, booking_id)
    if not b:
        raise ValueError(f"الحجز {booking_id} غير موجود")
    return b


def create_booking(db: Session, data: BookingCreate) -> Booking:
    # التحقق من التواريخ
    if data.check_out <= data.check_in:
        raise ValueError("check_out يجب أن يكون بعد check_in")

    nights = (data.check_out - data.check_in).days

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
    # الغرفة لحد ما الـ transaction دي تخلص (commit/rollback)
    room_rates: list[tuple[int, Decimal, int]] = []
    for room_id in ordered_room_ids:
        room = locked_rooms[room_id]
        if room.branch_id != data.branch_id:
            raise ValueError(f"الغرفة {room_id} لا تنتمي لهذا الفرع")

        available = crud.get_available_rooms(db, data.branch_id, data.check_in, data.check_out)
        if room_id not in [r.id for r in available]:
            raise BookingConflictError(f"الغرفة {room.name} غير متاحة في هذه الفترة")

        room_type = crud.get_room_type(db, room.room_type_id)
        daily_rate = room_type.base_rate if room_type else Decimal("0")
        room_rates.append((room_id, daily_rate, nights))

    booking_number = crud.generate_booking_number(db, data.branch_id)
    booking = crud.create_booking(db, booking_number, data, room_rates)

    # تحديث حالة الغرف → reserved
    for room_id, _, _ in room_rates:
        room = crud.get_room(db, room_id)
        if room:
            crud.update_room_status(db, room, "reserved")

    db.commit()
    db.refresh(booking)
    return booking


def checkin_booking(db: Session, booking_id: int) -> Booking:
    booking = get_booking_or_404(db, booking_id)
    if booking.status != "confirmed":
        raise ValueError(f"لا يمكن تسجيل الدخول لحجز بحالة '{booking.status}'")

    booking = crud.update_booking_status(db, booking, "checked_in")

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
    """Dr. Cash (1100) / Cr. Room Revenue (4100)."""
    from datetime import date as _date  # noqa: PLC0415
    from decimal import Decimal as _D  # noqa: PLC0415
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415

    post_simple_revenue_journal(
        db, booking.branch_id, _date.today(),
        debit_account_code="1100", credit_account_code="4100",
        amount=booking.total_rate or _D("0"),
        reference=f"CHK-{booking.booking_number}",
        description=f"إيرادات غرف — {booking.booking_number}",
        source="pms", source_id=booking.id,
    )


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


def update_housekeeping_task_status(db: Session, task_id: int, new_status: str, notes: Optional[str] = None):
    """يحدّث حالة مهمة تنظيف — dirty → cleaning → inspecting → available.
    لما توصل available، بيرجّع الغرفة نفسها لـ available تلقائياً (خلصت
    من دورة checkout_pending اللي بدأت في checkout_booking)."""
    task = crud.get_housekeeping_task(db, task_id)
    if not task:
        raise ValueError(f"مهمة التنظيف {task_id} غير موجودة")

    update_data: dict = {"status": new_status}
    if notes is not None:
        update_data["notes"] = notes
    if new_status == "cleaning" and not task.started_at:
        update_data["started_at"] = datetime.utcnow()
    if new_status == "available":
        update_data["completed_at"] = datetime.utcnow()

    task = crud.update_housekeeping_task(db, task, update_data)

    if new_status == "available":
        room = crud.get_room(db, task.room_id)
        if room and room.status in ("checkout_pending", "maintenance"):
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
