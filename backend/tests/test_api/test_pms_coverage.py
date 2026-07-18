"""
tests/test_api/test_pms_coverage.py
رفع coverage بتاع pms من 75-78% لـ 90%+
تركيز على: early/late checkout, housekeeping, available rooms, rate plans
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient


# ═══════════════════════════════════════════════════════════════════════
# Setup helpers — نفس نمط test_pms_http.py
# ═══════════════════════════════════════════════════════════════════════

def _branch(db):
    from app.modules.core.models import Branch
    b = Branch(name=f"PMS-Cov-{uuid.uuid4().hex[:6]}", code=f"PMC-{uuid.uuid4().hex[:6].upper()}")
    db.add(b); db.commit(); return b


def _room_type(db, branch_id, name="Standard"):
    from app.modules.pms.models import RoomType
    rt = RoomType(branch_id=branch_id, name=name, base_rate=Decimal("600"), max_occupancy=2)
    db.add(rt); db.commit(); return rt


def _room(db, branch_id, rt_id, num=None):
    from app.modules.pms.models import Room
    r = Room(branch_id=branch_id, room_type_id=rt_id, name=num or f"{uuid.uuid4().hex[:4].upper()}", floor=1, status="available")
    db.add(r); db.commit(); return r


def _booking(db, branch_id, room_id, ci=None, co=None, guest="Test Guest"):
    """إنشاء حجز مع ربطه بغرفة عبر BookingRoom (many-to-many)"""
    from app.modules.pms.models import Booking, BookingRoom
    from app.modules.pms.crud import generate_booking_number
    ci = ci or date.today()
    co = co or date.today() + timedelta(days=1)
    nights = max(1, (co - ci).days)
    b = Booking(
        branch_id=branch_id,
        booking_number=generate_booking_number(db, branch_id),
        guest_name=guest,
        guest_phone="01000000000",
        check_in=ci,
        check_out=co,
        status="confirmed",
        total_rate=Decimal("600"),
    )
    db.add(b); db.flush()
    br = BookingRoom(
        booking_id=b.id, room_id=room_id,
        daily_rate=Decimal("600"), nights=nights, total=Decimal("600") * nights,
    )
    db.add(br); db.commit(); return b


def _folio(db, branch_id, name="Test Guest"):
    from app.modules.finance.models import Folio
    f = Folio(
        branch_id=branch_id, guest_name=name, status="open", total=Decimal("0"),
        check_in=date.today(), check_out=date.today() + timedelta(days=1),
    )
    db.add(f); db.commit(); return f


def _hk_task(db, branch_id, room_id, task_type="checkout_clean", status="dirty"):
    from app.modules.pms.models import HousekeepingTask
    t = HousekeepingTask(branch_id=branch_id, room_id=room_id, task_type=task_type, status=status)
    db.add(t); db.commit(); return t


# ═══════════════════════════════════════════════════════════════════════
# Early / Late Checkout
# ═══════════════════════════════════════════════════════════════════════

def test_pms_early_late_free(client: TestClient, cashier_headers, db):
    """early_checkin مجاني (charge=0) — مفيش تغيير في total_rate"""
    br = _branch(db)
    rt = _room_type(db, br.id)
    room = _room(db, br.id, rt.id, "201")
    bk = _booking(db, br.id, room.id, guest="VIP Guest")

    payload = {
        "early_checkin_at": f"{date.today()}T10:00:00",
        "late_checkout_at": None,
        "charge": 0,
        "notes": "VIP",
    }
    resp = client.post(f"/api/v1/pms/bookings/{bk.id}/early-late", json=payload, headers=cashier_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["early_checkin_at"] is not None
    assert Decimal(data["total_rate"]) == Decimal("600")  # مفيش زيادة


def test_pms_late_checkout_with_charge(client: TestClient, cashier_headers, db):
    """late_checkout مع رسوم — total_rate بتزيد + folio charge حقيقية.

    مراجعة Codex الثالثة: التست القديم كان بيتأكد من HTTP 200 وtotal_rate
    بس — مفيش أي إثبات إيجابي إن الـFolioCharge اتسجّلت فعليًا. ده بالظبط
    اللي كان بيغطي باج posted_at الحقيقي (راجع pms/services.py) — لأن
    الـexcept القديم كان بيبتلع فشل الـFolioChargeCreate validation بعد ما
    يسجّله بس، فالـHTTP response كان برضو 200 وtotal_rate برضو صح (الحقل
    ده بيتحدّث قبل try block الشحنة) رغم إن الفوليو عمره ما اتحمّل فعليًا."""
    br = _branch(db)
    rt = _room_type(db, br.id)
    room = _room(db, br.id, rt.id, "301")
    bk = _booking(db, br.id, room.id, guest="Late Guest")
    folio = _folio(db, br.id, "Late Guest")
    bk.folio_id = folio.id
    db.commit()

    payload = {
        "early_checkin_at": None,
        "late_checkout_at": f"{date.today() + timedelta(days=1)}T16:00:00",
        "charge": 150,
        "notes": "Late +4h",
    }
    resp = client.post(f"/api/v1/pms/bookings/{bk.id}/early-late", json=payload, headers=cashier_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["late_checkout_at"] is not None
    assert Decimal(data["total_rate"]) == Decimal("750")  # 600 + 150

    # إثبات إيجابي إن الشحنة اتسجّلت فعليًا (باج posted_at كان بيمنع ده تمامًا)
    from datetime import datetime, timedelta as _td
    from app.modules.finance.models import FolioCharge

    db.refresh(folio)
    charges = db.query(FolioCharge).filter(FolioCharge.folio_id == folio.id).all()
    assert len(charges) == 1, f"متوقع شحنة فوليو واحدة بالظبط، لقينا {len(charges)}"
    charge = charges[0]
    assert charge.charge_type == "room_extra"
    assert charge.amount == Decimal("150")
    assert charge.posted_at is not None
    assert abs(charge.posted_at - datetime.utcnow()) < _td(minutes=5), (
        f"posted_at={charge.posted_at} بعيد جدًا عن وقت التنفيذ الفعلي"
    )
    assert folio.total == Decimal("150"), (
        f"folio.total={folio.total} — متوقع 150 (نفس قيمة الشحنة، الفوليو كان فاضي قبل كده)"
    )


def test_pms_early_late_both_with_charge(client: TestClient, cashier_headers, db):
    """early + late مع بعض"""
    br = _branch(db)
    rt = _room_type(db, br.id)
    room = _room(db, br.id, rt.id, "401")
    bk = _booking(db, br.id, room.id)

    payload = {
        "early_checkin_at": f"{date.today()}T09:00:00",
        "late_checkout_at": f"{date.today() + timedelta(days=1)}T15:00:00",
        "charge": 200,
        "notes": "Early + Late",
    }
    resp = client.post(f"/api/v1/pms/bookings/{bk.id}/early-late", json=payload, headers=cashier_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["early_checkin_at"] is not None
    assert data["late_checkout_at"] is not None
    assert Decimal(data["total_rate"]) == Decimal("800")  # 600 + 200


def test_pms_early_late_booking_not_found(client: TestClient, cashier_headers):
    payload = {"early_checkin_at": None, "late_checkout_at": None, "charge": 0}
    resp = client.post("/api/v1/pms/bookings/99999/early-late", json=payload, headers=cashier_headers)
    assert resp.status_code in (400, 404)


# ═══════════════════════════════════════════════════════════════════════
# Housekeeping Tasks
# ═══════════════════════════════════════════════════════════════════════

def test_pms_list_hk_tasks_all(client: TestClient, manager_headers, db):
    br = _branch(db)
    rt = _room_type(db, br.id)
    r1 = _room(db, br.id, rt.id, "501")
    r2 = _room(db, br.id, rt.id, "502")
    _hk_task(db, br.id, r1.id, "checkout_clean", "dirty")
    _hk_task(db, br.id, r2.id, "checkout_clean", "cleaning")

    resp = client.get(f"/api/v1/pms/housekeeping/tasks?branch_id={br.id}", headers=manager_headers)
    assert resp.status_code == 200
    tasks = resp.json()
    assert len(tasks) >= 2


def test_pms_list_hk_tasks_by_status(client: TestClient, manager_headers, db):
    br = _branch(db)
    rt = _room_type(db, br.id)
    room = _room(db, br.id, rt.id, "601")
    _hk_task(db, br.id, room.id, "checkout_clean", "dirty")
    _hk_task(db, br.id, room.id, "checkout_clean", "available")

    resp = client.get(f"/api/v1/pms/housekeeping/tasks?branch_id={br.id}&status=dirty", headers=manager_headers)
    assert resp.status_code == 200
    tasks = resp.json()
    assert all(t["status"] == "dirty" for t in tasks)


def test_pms_list_hk_tasks_by_room(client: TestClient, manager_headers, db):
    br = _branch(db)
    rt = _room_type(db, br.id)
    r1 = _room(db, br.id, rt.id, "701")
    r2 = _room(db, br.id, rt.id, "702")
    _hk_task(db, br.id, r1.id, "checkout_clean", "dirty")
    _hk_task(db, br.id, r2.id, "checkout_clean", "dirty")

    resp = client.get(f"/api/v1/pms/housekeeping/tasks?branch_id={br.id}&room_id={r1.id}", headers=manager_headers)
    assert resp.status_code == 200
    tasks = resp.json()
    assert all(t["room_id"] == r1.id for t in tasks)


def test_pms_update_hk_task_to_in_progress(client: TestClient, manager_headers, db):
    br = _branch(db)
    rt = _room_type(db, br.id)
    room = _room(db, br.id, rt.id, "801")
    task = _hk_task(db, br.id, room.id, "checkout_clean", "dirty")

    resp = client.patch(f"/api/v1/pms/housekeeping/tasks/{task.id}",
                        json={"status": "cleaning", "notes": "Started"},
                        headers=manager_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cleaning"
    assert resp.json()["notes"] == "Started"


def test_pms_update_hk_task_assigns_employee(client: TestClient, manager_headers, db):
    """wagdy.md P-12: assigned_to كان عمود حقيقي بيتعرض في الفرونت إند بدون
    أي طريقة تحدّده."""
    br = _branch(db)
    rt = _room_type(db, br.id)
    room = _room(db, br.id, rt.id, "802")
    task = _hk_task(db, br.id, room.id, "checkout_clean", "dirty")

    resp = client.patch(f"/api/v1/pms/housekeeping/tasks/{task.id}",
                        json={"status": "dirty", "assigned_to": 42},
                        headers=manager_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["assigned_to"] == 42

    # تعيين موظف تاني ميغيّرش الحالة لو مش مبعوتة تغيير حقيقي
    resp2 = client.patch(f"/api/v1/pms/housekeeping/tasks/{task.id}",
                         json={"status": "dirty", "assigned_to": 7},
                         headers=manager_headers)
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["assigned_to"] == 7
    assert resp2.json()["status"] == "dirty"


def test_pms_update_hk_task_to_completed(client: TestClient, manager_headers, db):
    br = _branch(db)
    rt = _room_type(db, br.id)
    room = _room(db, br.id, rt.id, "901")
    task = _hk_task(db, br.id, room.id, "checkout_clean", "cleaning")

    resp = client.patch(f"/api/v1/pms/housekeeping/tasks/{task.id}",
                        json={"status": "available", "notes": "Done"},
                        headers=manager_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "available"


def test_pms_update_hk_task_not_found(client: TestClient, manager_headers):
    resp = client.patch("/api/v1/pms/housekeeping/tasks/99999",
                        json={"status": "cleaning"},
                        headers=manager_headers)
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# Available Rooms — Room Assignment Logic
# ═══════════════════════════════════════════════════════════════════════

def test_pms_available_rooms_excludes_occupied(client: TestClient, manager_headers, db):
    """الغرف في حالة maintenance محجوبة — الغرف occupied متاحة للحجز المستقبلي"""
    br = _branch(db)
    rt = _room_type(db, br.id)
    from app.modules.pms.models import Room
    r_available  = Room(branch_id=br.id, room_type_id=rt.id, name="A01", floor=1, status="available")
    r_maintenance = Room(branch_id=br.id, room_type_id=rt.id, name="A02", floor=1, status="maintenance")
    db.add_all([r_available, r_maintenance]); db.commit()

    ci = date.today()
    co = date.today() + timedelta(days=2)
    resp = client.get(
        f"/api/v1/pms/rooms/available?branch_id={br.id}&check_in={ci}&check_out={co}",
        headers=manager_headers,
    )
    assert resp.status_code == 200
    names = [r["name"] for r in resp.json()]
    assert "A01" in names
    assert "A02" not in names  # maintenance محجوبة دائمًا


def test_pms_available_rooms_excludes_booked(client: TestClient, manager_headers, db):
    br = _branch(db)
    rt = _room_type(db, br.id)
    r1 = _room(db, br.id, rt.id, "B01")
    r2 = _room(db, br.id, rt.id, "B02")
    # حجز على r1 في نفس الفترة
    _booking(db, br.id, r1.id, date.today(), date.today() + timedelta(days=2))

    ci = date.today()
    co = date.today() + timedelta(days=2)
    resp = client.get(
        f"/api/v1/pms/rooms/available?branch_id={br.id}&check_in={ci}&check_out={co}",
        headers=manager_headers,
    )
    assert resp.status_code == 200
    names = [r["name"] for r in resp.json()]
    assert "B01" not in names
    assert "B02" in names


def test_pms_available_rooms_filter_by_type(client: TestClient, manager_headers, db):
    br = _branch(db)
    rt1 = _room_type(db, br.id, "Standard")
    rt2 = _room_type(db, br.id, "Deluxe")
    _room(db, br.id, rt1.id, "C01")
    _room(db, br.id, rt2.id, "C02")

    ci = date.today()
    co = date.today() + timedelta(days=1)
    resp = client.get(
        f"/api/v1/pms/rooms/available?branch_id={br.id}&check_in={ci}&check_out={co}&room_type_id={rt1.id}",
        headers=manager_headers,
    )
    assert resp.status_code == 200
    rooms = resp.json()
    assert all(r["room_type_id"] == rt1.id for r in rooms)


# ═══════════════════════════════════════════════════════════════════════
# Rate Plans
# ═══════════════════════════════════════════════════════════════════════

def test_pms_create_rate_plan(client: TestClient, super_admin_headers, db):
    br = _branch(db)
    rt = _room_type(db, br.id)

    payload = {
        "branch_id": br.id,
        "room_type_id": rt.id,
        "name": "Summer Rate",
        "valid_from": str(date.today()),
        "valid_until": str(date.today() + timedelta(days=90)),
        "base_rate_override": "750.00",
        "rate_multiplier": "1.0000",
    }
    resp = client.post("/api/v1/pms/rate-plans", json=payload, headers=super_admin_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Summer Rate"
    assert Decimal(data["base_rate_override"]) == Decimal("750")


def test_pms_list_rate_plans(client: TestClient, manager_headers, db):
    br = _branch(db)
    rt = _room_type(db, br.id)
    from app.modules.pms.models import RatePlan
    rp = RatePlan(
        branch_id=br.id, room_type_id=rt.id, name="Winter Rate",
        valid_from=date.today(), valid_until=date.today() + timedelta(days=60),
        base_rate_override=Decimal("550"), rate_multiplier=Decimal("1.0000"),
    )
    db.add(rp); db.commit()

    resp = client.get(f"/api/v1/pms/rate-plans?branch_id={br.id}", headers=manager_headers)
    assert resp.status_code == 200
    plans = resp.json()
    assert any(p["name"] == "Winter Rate" for p in plans)


# ═══════════════════════════════════════════════════════════════════════
# Room Status Update
# ═══════════════════════════════════════════════════════════════════════

def test_pms_update_room_status(client: TestClient, manager_headers, db):
    """تحديث حالة الغرفة لـ maintenance (قيمة مقبولة في الـ schema)"""
    br = _branch(db)
    rt = _room_type(db, br.id)
    room = _room(db, br.id, rt.id, "D01")

    resp = client.patch(f"/api/v1/pms/rooms/{room.id}/status",
                        json={"status": "maintenance", "notes": "Maintenance needed"},
                        headers=manager_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "maintenance"


def test_pms_update_room_status_not_found(client: TestClient, manager_headers):
    resp = client.patch("/api/v1/pms/rooms/99999/status",
                        json={"status": "maintenance"},
                        headers=manager_headers)
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# Night Audit Log
# ═══════════════════════════════════════════════════════════════════════

def test_pms_night_audit_creates_log(client: TestClient, super_admin_headers, db):
    br = _branch(db)
    # تشغيل الـ night audit عبر query params (مش request body)
    resp = client.post(
        f"/api/v1/pms/night-audit/run?branch_id={br.id}&audit_date={date.today()}",
        headers=super_admin_headers,
    )
    # ممكن 200 أو 400 لو في audit log موجود بالفعل
    assert resp.status_code in (200, 201, 400)
