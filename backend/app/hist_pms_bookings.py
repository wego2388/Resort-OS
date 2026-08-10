"""HIST-01 — مولّد بيانات PMS التاريخية ليوليو 2026 (OPS-DATA-02 §10.2).

بيستخدم services الحقيقية بس (create_booking/create_bundle_booking/
checkin_booking/checkout_booking/cancel_booking/run_night_audit/
update_room_status/update_housekeeping_task_status/request_early_late) —
صفر SQL مباشر، مطابق للقاعدة الصريحة "لا SQL patches bypassing services".

الـfixture الثابت من §10.2 (وليس random بلا seed):
- 70 Studio nights منفردة + 75 Chalet nights منفردة + 25 Family Compound
  nights (= 50 physical unit-nights) → إشغال 195/(14×31) = 44.93%.
- صافي room revenue قبل VAT/service = 70×2500 + 75×3500 + 25×4500 = 550,000.
- 38 حجزًا إجمالًا: 5 باقة + 1 عابر لنهاية الشهر (Chalet) + 1 multi-room
  (Chalet، غرفتين) + 27 مفردة (13 Chalet + 14 Studio) + 2 ملغاة + 2 no-show.
  75 = 3 (الجزء اللي جوه يوليو من الحجز العابر) + 8 (multi-room) + 64
  (13 حجز مفرد: 12×5 + 1×4). 70 = 14 حجز مفرد × 5 ليالٍ بالظبط.
- تعبر نهاية الشهر (29 يوليو → 3 أغسطس)، وحجز multi-room (غرفتين شاليه)،
  وحالة early check-in وحالة late checkout برسوم فعلية على الفوليو،
  وغرفة maintenance توقف عن الحجز فعليًا (تحقّق حي عبر get_available_rooms،
  مش افتراض)، وHousekeeping checkout بيتحول dirty→cleaning→inspecting→
  available فعليًا (مش مجرد إنشاء الصف).
- Night Audit بيتشغّل 31 مرة (يوم بيوم)، بما فيهم يوم بلا إشغال (1 يوليو،
  قبل أي check-in) ويوم مرتفع الإشغال (منتصف الشهر تقريبًا).
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from app.resort_os.clock import scenario_clock

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.operational_history_seed import ScenarioContext

# عدد الليالي المطلوبة لكل حجز مفرد Chalet (13 حجز، مجموعها 64 ليلة —
# الباقي من 75 بعد خصم 3 (العابر لنهاية الشهر) + 8 (multi-room)).
_CHALET_GENERIC_STAYS: list[int] = [5] * 12 + [4]
# 14 حجز Studio مفرد، 5 ليالٍ لكل واحد = 70 بالظبط.
_STUDIO_GENERIC_STAYS: list[int] = [5] * 14

_SOURCE_CYCLE: list[str] = ["direct", "online", "phone", "b2b"]


def _free(occupied: dict[int, list[tuple[date, date]]], room_id: int, start: date, end_ex: date) -> bool:
    for s, e in occupied[room_id]:
        if start < e and s < end_ex:
            return False
    return True


def _reserve(occupied: dict[int, list[tuple[date, date]]], room_id: int, start: date, end_ex: date) -> None:
    occupied[room_id].append((start, end_ex))


def generate(db: "Session", ctx: "ScenarioContext") -> dict:
    from app.modules.core.models import AuditLog
    from app.modules.pms.crud import (
        get_available_rooms, list_housekeeping_tasks, update_room_status,
    )
    from app.modules.pms.models import Booking, Room, RoomBundle, RoomType
    from app.modules.pms.schemas import BookingCreate, BundleBookingCreate, EarlyLateRequest
    from app.modules.pms.services import (
        cancel_booking, checkin_booking, checkout_booking,
        create_booking, create_bundle_booking, request_early_late,
        run_night_audit, update_housekeeping_task_status,
    )

    branch_id = ctx.branch_id
    year, month = ctx.period_year, ctx.period_month
    tz = ZoneInfo(ctx.tz_name)
    month_start = date(year, month, 1)
    days_in_month = calendar.monthrange(year, month)[1]
    month_end_exclusive = month_start + timedelta(days=days_in_month)

    rooms = (
        db.query(Room)
        .join(RoomType, Room.room_type_id == RoomType.id)
        .filter(Room.branch_id == branch_id)
        .order_by(Room.id)
        .all()
    )
    chalet_rooms = [r for r in rooms if r.room_type.name == "Chalet"]
    studio_rooms = [r for r in rooms if r.room_type.name == "Studio"]
    if len(chalet_rooms) + len(studio_rooms) != 14:
        raise RuntimeError(
            f"HIST-01 §10.2 fixture assumes exactly 14 rooms (8 Chalet + 6 Studio); "
            f"found {len(chalet_rooms)} Chalet + {len(studio_rooms)} Studio for branch {branch_id}"
        )

    bundles = (
        db.query(RoomBundle)
        .filter(RoomBundle.branch_id == branch_id, RoomBundle.is_active.is_(True))
        .order_by(RoomBundle.id)
        .all()
    )
    if len(bundles) != 5:
        raise RuntimeError(
            f"HIST-01 §10.2 fixture assumes exactly 5 active room bundles; found {len(bundles)} "
            f"for branch {branch_id} — run app.approved_room_pricing first"
        )

    pair_chalet_ids = {b.chalet_room_id for b in bundles}
    pair_studio_ids = {b.studio_room_id for b in bundles}
    standalone_chalets = [r for r in chalet_rooms if r.id not in pair_chalet_ids]
    standalone_studios = [r for r in studio_rooms if r.id not in pair_studio_ids]
    # الغرف المستقلة أولًا (مفيش نافذة باقة تحجب جزء من الشهر)، بعدين غرف
    # الأزواج — نافذة الباقة الخاصة بكل واحدة منهم متسجّلة في `occupied`
    # قبل أي حجز مفرد، فالـpacker تحت بيتخطاها تلقائيًا.
    chalet_pool = standalone_chalets + [r for r in chalet_rooms if r.id in pair_chalet_ids]
    studio_pool = standalone_studios + [r for r in studio_rooms if r.id in pair_studio_ids]

    occupied: dict[int, list[tuple[date, date]]] = {r.id: [] for r in rooms}
    counts = {"direct": 0, "online": 0, "phone": 0, "b2b": 0}
    booking_ids: list[int] = []
    no_show_booking_ids: set[int] = set()
    guest_seq = 0

    def _next_source() -> str:
        nonlocal guest_seq
        return _SOURCE_CYCLE[guest_seq % len(_SOURCE_CYCLE)]

    # ── 1) Family Compound bundles (5 × 5 ليالٍ = 25) ───────────────────
    bundle_starts = [2, 9, 12, 16, 19]  # يوم-في-الشهر (0-indexed) لكل باقة
    for i, bundle in enumerate(bundles):
        start = month_start + timedelta(days=bundle_starts[i])
        end_ex = start + timedelta(days=5)
        guest_seq += 1
        source = _next_source()
        booking = create_bundle_booking(db, BundleBookingCreate(
            branch_id=branch_id, bundle_id=bundle.id,
            guest_name=f"عائلة HIST-{i + 1:02d}", check_in=start, check_out=end_ex,
            source=source,
        ))
        db.flush()
        _reserve(occupied, bundle.chalet_room_id, start, end_ex)
        _reserve(occupied, bundle.studio_room_id, start, end_ex)
        counts[source] += 1
        booking_ids.append(booking.id)

    # ── 2) حجز عابر لنهاية الشهر (Chalet، 29 يوليو → 3 أغسطس) ───────────
    # 5 ليالٍ إجمالًا، منها 3 بس جوه يوليو (29,30,31) — بتتحسب في Night
    # Audit تلقائيًا من غير أي منطق خاص، لأن الحلقة تحت بتشتغل ليوليو بس.
    crossing_room = chalet_pool[0]
    crossing_start = month_start + timedelta(days=days_in_month - 3)  # 29 يوليو
    crossing_end_ex = crossing_start + timedelta(days=5)  # 3 أغسطس
    guest_seq += 1
    source = _next_source()
    crossing_booking = create_booking(db, BookingCreate(
        branch_id=branch_id, guest_name="ضيف HIST-عابر-الشهر",
        check_in=crossing_start, check_out=crossing_end_ex,
        room_ids=[crossing_room.id], source=source,
    ))
    db.flush()
    _reserve(occupied, crossing_room.id, crossing_start, crossing_end_ex)
    counts[source] += 1
    booking_ids.append(crossing_booking.id)

    # ── 3) Multi-room booking واحد (نفس الضيف، غرفتين Chalet، 4 ليالٍ) ──
    multi_rooms = [chalet_pool[1], chalet_pool[2]]
    multi_start = month_start + timedelta(days=6)
    multi_end_ex = multi_start + timedelta(days=4)
    guest_seq += 1
    source = _next_source()
    multi_booking = create_booking(db, BookingCreate(
        branch_id=branch_id, guest_name="عائلة HIST-متعددة-الغرف",
        check_in=multi_start, check_out=multi_end_ex,
        room_ids=[r.id for r in multi_rooms], source=source,
    ))
    db.flush()
    for r in multi_rooms:
        _reserve(occupied, r.id, multi_start, multi_end_ex)
    counts[source] += 1
    booking_ids.append(multi_booking.id)

    # ── 4) حجوزات مفردة عادية (packer محدَّد، round-robin + first-fit) ──
    def _pack(rooms_pool, stays: list[int], label: str) -> list[int]:
        nonlocal guest_seq
        created: list[int] = []
        room_idx = 0
        for nights in stays:
            placed = False
            for _attempt in range(len(rooms_pool) * (days_in_month + 1)):
                room = rooms_pool[room_idx % len(rooms_pool)]
                room_idx += 1
                for offset in range(days_in_month - nights + 1):
                    start = month_start + timedelta(days=offset)
                    end_ex = start + timedelta(days=nights)
                    if end_ex > month_end_exclusive:
                        break
                    if _free(occupied, room.id, start, end_ex):
                        guest_seq += 1
                        src = _next_source()
                        booking = create_booking(db, BookingCreate(
                            branch_id=branch_id, guest_name=f"ضيف HIST-{label}-{guest_seq:03d}",
                            check_in=start, check_out=end_ex, room_ids=[room.id], source=src,
                        ))
                        db.flush()
                        _reserve(occupied, room.id, start, end_ex)
                        counts[src] += 1
                        created.append(booking.id)
                        placed = True
                        break
                if placed:
                    break
            if not placed:
                raise RuntimeError(f"HIST-01: تعذّر إيجاد فسحة لحجز {label} بطول {nights} ليالٍ")
        return created

    chalet_generic_ids = _pack(chalet_pool, _CHALET_GENERIC_STAYS, "Chalet")
    studio_generic_ids = _pack(studio_pool, _STUDIO_GENERIC_STAYS, "Studio")
    booking_ids += chalet_generic_ids + studio_generic_ids

    # ── 5) ملغاة (2) + no-show (2) — على فسحات فاضية، صفر إيراد ─────────
    cancelled_ids: list[int] = []
    for i in range(2):
        room = chalet_pool[-1] if i == 0 else studio_pool[-1]
        placed = False
        for offset in range(days_in_month - 1):
            start = month_start + timedelta(days=offset)
            end_ex = start + timedelta(days=2)
            if end_ex <= month_end_exclusive and _free(occupied, room.id, start, end_ex):
                guest_seq += 1
                src = _next_source()
                b = create_booking(db, BookingCreate(
                    branch_id=branch_id, guest_name=f"ضيف HIST-ملغى-{i + 1}",
                    check_in=start, check_out=end_ex, room_ids=[room.id], source=src,
                ))
                db.flush()
                _reserve(occupied, room.id, start, end_ex)
                counts[src] += 1
                cancelled_ids.append(b.id)
                booking_ids.append(b.id)
                placed = True
                break
        if not placed:
            raise RuntimeError("HIST-01: تعذّر إيجاد فسحة لحجز ملغى")
    for booking_id in cancelled_ids:
        cancel_booking(db, booking_id, cancelled_by=0)

    for i in range(2):
        room = chalet_pool[0] if i == 0 else studio_pool[0]
        placed = False
        # اليوم 15-28 عشان يبقى جوه نطاق حلقة الأيام تحت، مش أول/آخر الشهر
        for offset in range(14, days_in_month - 2):
            start = month_start + timedelta(days=offset)
            end_ex = start + timedelta(days=2)
            if end_ex <= month_end_exclusive and _free(occupied, room.id, start, end_ex):
                guest_seq += 1
                src = _next_source()
                b = create_booking(db, BookingCreate(
                    branch_id=branch_id, guest_name=f"ضيف HIST-noshow-{i + 1}",
                    check_in=start, check_out=end_ex, room_ids=[room.id], source=src,
                ))
                db.flush()
                _reserve(occupied, room.id, start, end_ex)
                counts[src] += 1
                no_show_booking_ids.add(b.id)
                booking_ids.append(b.id)
                placed = True
                break
        if not placed:
            raise RuntimeError("HIST-01: تعذّر إيجاد فسحة لحجز no-show")

    # حجزين هياخدوا رسوم وصول مبكر/مغادرة متأخرة فعلية وقت الـcheck-in —
    # لازم يتنفّذوا وهما لسه checked_in (فوليو مفتوح)، مش بعد checkout.
    early_checkin_booking_id = chalet_generic_ids[1]
    late_checkout_booking_id = studio_generic_ids[1]

    # ── 6) رحلة الشهر يوم بيوم: checkout → checkin → Night Audit ────────
    # الترتيب مهم: checkout الصبح (يحرر الغرفة)، checkin (يشغل الغرفة لليلة
    # النهاردة) مع تطبيق رسوم الوصول المبكر/المغادرة المتأخرة لحظة الدخول،
    # وأخيرًا Night Audit (بيحسب الإيراد لكل حجز لسه checked_in الليلة دي
    # بالظبط، وبيحوّل أي حجز confirmed لسه بتاريخ check_in النهاردة ومحدش
    # سجّله دخول إلى no_show تلقائيًا — راجع services.run_night_audit).
    # كل يوم بيتنفّذ جوه scenario_clock خاص بيه (مش وقت ثابت واحد للشهر
    # كله) — عشان local_today() جوه _post_checkout_journal (تاريخ قيد
    # تسوية الفوليو) يعكس يوم الحدث الفعلي، مش يوم بداية السيناريو الثابت.
    # راجع OPS-DATA-02 §9.2 "journal entry_date... تعكس وقت السيناريو".
    night_audit_logs = 0
    for offset in range(days_in_month):
        day = month_start + timedelta(days=offset)
        with scenario_clock(datetime.combine(day, time(20, 0), tzinfo=tz)):
            for b in db.query(Booking).filter(
                Booking.branch_id == branch_id, Booking.status == "checked_in", Booking.check_out == day,
            ).all():
                checkout_booking(db, b.id)

            for b in db.query(Booking).filter(
                Booking.branch_id == branch_id, Booking.status == "confirmed", Booking.check_in == day,
            ).all():
                if b.id in no_show_booking_ids:
                    continue  # سيبها confirmed — Night Audit هيحوّلها no_show تلقائيًا
                checkin_booking(db, b.id)
                if b.id == early_checkin_booking_id:
                    request_early_late(db, b.id, EarlyLateRequest(
                        early_checkin_at=datetime.combine(day, time(10, 0), tzinfo=tz),
                        charge=Decimal("150.00"), notes="وصول مبكر HIST-01",
                    ))
                elif b.id == late_checkout_booking_id:
                    request_early_late(db, b.id, EarlyLateRequest(
                        late_checkout_at=datetime.combine(day, time(15, 0), tzinfo=tz),
                        charge=Decimal("100.00"), notes="مغادرة متأخرة HIST-01",
                    ))

            run_night_audit(db, branch_id, day)
            night_audit_logs += 1

    # ── 7) Housekeeping: تدوير مهمة تنظيف حقيقية بعد checkout ───────────
    housekeeping_cycled = 0
    tasks = list_housekeeping_tasks(db, branch_id, status=None)
    if tasks:
        task = tasks[0]
        update_housekeeping_task_status(db, task.id, "cleaning")
        update_housekeeping_task_status(db, task.id, "inspecting")
        update_housekeeping_task_status(db, task.id, "available")
        housekeeping_cycled = 1

    # ── 8) غرفة maintenance توقف الحجز فعليًا (تحقّق حي، مش افتراض) ─────
    maintenance_room = studio_pool[-1]
    update_room_status(db, maintenance_room, "maintenance", notes="HIST-01: صيانة دورية")
    maintenance_check_start = month_start + timedelta(days=days_in_month - 1)
    available_ids_after = {
        r.id for r in get_available_rooms(db, branch_id, maintenance_check_start, month_end_exclusive)
    }
    if maintenance_room.id in available_ids_after:
        raise RuntimeError(
            f"HIST-01: الغرفة {maintenance_room.name} بقت status=maintenance لكن لسه ظاهرة "
            "كمتاحة — تحقّق فشل من get_available_rooms"
        )
    update_room_status(db, maintenance_room, "available", notes="HIST-01: انتهت الصيانة")

    db.add(AuditLog(
        user_id=None, branch_id=branch_id,
        action="hist01_pms_bookings_generated", entity_type="pms_scenario", entity_id=branch_id,
        new_data=None, ip_address="127.0.0.1", user_agent="app.hist_pms_bookings",
    ))
    db.flush()

    return {
        "counts": {
            **counts,
            "bookings_total": len(booking_ids),
            "bundle": len(bundles),
            "cancelled": len(cancelled_ids),
            "no_show": len(no_show_booking_ids),
            "night_audit_logs": night_audit_logs,
            "housekeeping_cycled": housekeeping_cycled,
        },
        "totals": {
            "room_nights": {"studio": 70, "chalet": 75, "bundle": 25},
        },
    }
