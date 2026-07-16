"""
tests/test_api/test_timeshare_calendar_visits.py
اختبارات لـ:
- GET /timeshare/calendar — يشمل الزيارات الفعلية والعقود العائمة
- GET /timeshare/available-weeks — الأسابيع المتاحة للبيع
- send_visit_reminders — تذكيرات العقود العائمة
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient


# ── helpers ─────────────────────────────────────────────────────────────────

def _make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(
        name=f"Cal-Branch-{uuid.uuid4().hex[:6]}",
        code=f"CB{uuid.uuid4().hex[:4].upper()}",
    )
    db.add(b)
    db.commit()
    return b


def _make_contract(db, branch_id, week_number=None, status="active", room_type="2R"):
    """ينشئ عقداً مع تسجيل signed_by = 0 (لا يحتاج مستخدم حقيقي في هذه الاختبارات)."""
    from app.modules.timeshare import crud as ts_crud
    from app.modules.timeshare.schemas import TimeshareContractCreate
    today = date.today()
    data = TimeshareContractCreate(
        branch_id=branch_id,
        customer_name=f"عميل-{uuid.uuid4().hex[:4]}",
        customer_phone=f"010{uuid.uuid4().int % 100000000:08d}",
        room_type=room_type,
        total_value=Decimal("60000"),
        down_payment=Decimal("10000"),
        installments=12,
        installment_period=1,
        first_installment_date=today + timedelta(days=30),
        start_date=today,
        season="high",
        week_number=week_number,
    )
    contract = ts_crud.create_contract(db, data, signed_by=0)
    if status != "active":
        contract.status = status
    db.commit()
    return contract


def _make_visit(db, contract, branch_id, check_in, check_out, status="scheduled"):
    from app.modules.timeshare.models import TimeshareVisit
    v = TimeshareVisit(
        branch_id=branch_id,
        contract_id=contract.id,
        check_in=check_in,
        check_out=check_out,
        nights=(check_out - check_in).days,
        status=status,
    )
    db.add(v)
    db.commit()
    return v


# ── GET /timeshare/calendar ───────────────────────────────────────────────────

class TestCalendarIncludesVisits:
    """الكالندر يعرض الزيارات الفعلية بجانب العقود الثابتة."""

    def test_fixed_contract_appears_in_calendar(self, client: TestClient, db, fake_redis, manager_headers):
        """عقد ثابت (week_number=15) يظهر في الكالندر بـ source=contract."""
        branch = _make_branch(db)
        contract = _make_contract(db, branch.id, week_number=15)
        year = date.today().year

        resp = client.get(
            "/api/v1/timeshare/calendar",
            params={"branch_id": branch.id, "year": year},
            headers=manager_headers,
        )
        assert resp.status_code == 200
        data = resp.json()

        all_entries = [
            entry
            for month in data["calendar"]
            for week in month["weeks"]
            for entry in week["contracts"]
        ]
        contract_entries = [e for e in all_entries if e.get("source") == "contract"]
        assert any(e["id"] == contract.id for e in contract_entries), \
            "العقد الثابت لم يظهر بـ source=contract في الكالندر"

    def test_floating_visit_appears_in_calendar(self, client: TestClient, db, fake_redis, manager_headers):
        """زيارة فعلية (عقد عائم) تظهر في الكالندر بـ source=visit."""
        branch = _make_branch(db)
        contract = _make_contract(db, branch.id, week_number=None)  # عائم
        year = date.today().year

        # زيارة في أسبوع محدد
        check_in = date.fromisocalendar(year, 20, 1)  # بداية أسبوع 20
        check_out = check_in + timedelta(days=7)
        _make_visit(db, contract, branch.id, check_in, check_out)

        resp = client.get(
            "/api/v1/timeshare/calendar",
            params={"branch_id": branch.id, "year": year},
            headers=manager_headers,
        )
        assert resp.status_code == 200
        data = resp.json()

        all_entries = [
            entry
            for month in data["calendar"]
            for week in month["weeks"]
            for entry in week["contracts"]
        ]
        visit_entries = [e for e in all_entries if e.get("source") == "visit"]
        assert len(visit_entries) >= 1, "الزيارة الفعلية لم تظهر في الكالندر"
        assert visit_entries[0]["visit_id"] is not None

    def test_calendar_entry_has_booking_frozen_flag(self, client: TestClient, db, fake_redis, manager_headers):
        """العقد المجمَّد يظهر بـ booking_frozen=True في الكالندر."""
        branch = _make_branch(db)
        contract = _make_contract(db, branch.id, week_number=30)
        contract.booking_frozen = True
        db.commit()
        year = date.today().year

        resp = client.get(
            "/api/v1/timeshare/calendar",
            params={"branch_id": branch.id, "year": year},
            headers=manager_headers,
        )
        assert resp.status_code == 200
        data = resp.json()

        all_entries = [
            entry
            for month in data["calendar"]
            for week in month["weeks"]
            for entry in week["contracts"]
        ]
        frozen_entries = [e for e in all_entries if e.get("id") == contract.id]
        assert frozen_entries, "العقد لم يظهر في الكالندر"
        assert frozen_entries[0]["booking_frozen"] is True

    def test_calendar_visit_source_has_visit_status(self, client: TestClient, db, fake_redis, manager_headers):
        """زيارة بـ status=completed تظهر في الكالندر بـ visit_status=completed."""
        branch = _make_branch(db)
        contract = _make_contract(db, branch.id, week_number=None)
        year = date.today().year
        check_in = date.fromisocalendar(year, 25, 1)
        check_out = check_in + timedelta(days=7)
        _make_visit(db, contract, branch.id, check_in, check_out, status="completed")

        resp = client.get(
            "/api/v1/timeshare/calendar",
            params={"branch_id": branch.id, "year": year},
            headers=manager_headers,
        )
        assert resp.status_code == 200
        data = resp.json()

        all_entries = [
            entry
            for month in data["calendar"]
            for week in month["weeks"]
            for entry in week["contracts"]
        ]
        visit_entries = [e for e in all_entries if e.get("source") == "visit"]
        assert any(e["visit_status"] == "completed" for e in visit_entries)

    def test_cancelled_visit_excluded_from_calendar(self, client: TestClient, db, fake_redis, manager_headers):
        """زيارة ملغاة لا تظهر في الكالندر."""
        branch = _make_branch(db)
        contract = _make_contract(db, branch.id, week_number=None)
        year = date.today().year
        check_in = date.fromisocalendar(year, 35, 1)
        check_out = check_in + timedelta(days=7)
        visit = _make_visit(db, contract, branch.id, check_in, check_out, status="cancelled")

        resp = client.get(
            "/api/v1/timeshare/calendar",
            params={"branch_id": branch.id, "year": year},
            headers=manager_headers,
        )
        assert resp.status_code == 200
        data = resp.json()

        all_entries = [
            entry
            for month in data["calendar"]
            for week in month["weeks"]
            for entry in week["contracts"]
        ]
        assert not any(e.get("visit_id") == visit.id for e in all_entries), \
            "زيارة ملغاة ظهرت في الكالندر"

    def test_calendar_other_branch_isolated(self, client: TestClient, db, fake_redis, manager_headers):
        """زيارات فرع آخر لا تظهر في الكالندر."""
        branch_a = _make_branch(db)
        branch_b = _make_branch(db)
        contract_b = _make_contract(db, branch_b.id, week_number=None)
        year = date.today().year
        check_in = date.fromisocalendar(year, 40, 1)
        _make_visit(db, contract_b, branch_b.id, check_in, check_in + timedelta(days=7))

        resp = client.get(
            "/api/v1/timeshare/calendar",
            params={"branch_id": branch_a.id, "year": year},
            headers=manager_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        all_entries = [
            entry
            for month in data["calendar"]
            for week in month["weeks"]
            for entry in week["contracts"]
        ]
        assert not any(e.get("id") == contract_b.id for e in all_entries)


# ── GET /timeshare/available-weeks ───────────────────────────────────────────

class TestAvailableWeeks:
    """الأسابيع المتاحة للبيع = 52 - محجوزة بعقود ثابتة - محجوزة بزيارات فعلية."""

    def test_empty_branch_all_weeks_available(self, client: TestClient, db, fake_redis, manager_headers):
        """فرع بدون عقود → كل الأسابيع متاحة."""
        branch = _make_branch(db)
        year = date.today().year

        resp = client.get(
            "/api/v1/timeshare/available-weeks",
            params={"branch_id": branch.id, "year": year},
            headers=manager_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_booked"] == 0
        assert data["total_available"] >= 52

    def test_fixed_contract_reduces_available(self, client: TestClient, db, fake_redis, manager_headers):
        """عقد ثابت في الأسبوع 10 يُقلّل الأسابيع المتاحة."""
        branch = _make_branch(db)
        _make_contract(db, branch.id, week_number=10)
        year = date.today().year

        resp = client.get(
            "/api/v1/timeshare/available-weeks",
            params={"branch_id": branch.id, "year": year},
            headers=manager_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_booked"] >= 1
        week_nums = [w["week"] for w in data["available_weeks"]]
        assert 10 not in week_nums

    def test_floating_visit_reduces_available(self, client: TestClient, db, fake_redis, manager_headers):
        """زيارة مجدولة (عقد عائم) تُقلّل الأسابيع المتاحة."""
        branch = _make_branch(db)
        contract = _make_contract(db, branch.id, week_number=None)
        year = date.today().year
        check_in = date.fromisocalendar(year, 22, 1)
        _make_visit(db, contract, branch.id, check_in, check_in + timedelta(days=7))

        resp = client.get(
            "/api/v1/timeshare/available-weeks",
            params={"branch_id": branch.id, "year": year},
            headers=manager_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        week_nums = [w["week"] for w in data["available_weeks"]]
        assert 22 not in week_nums

    def test_room_type_filter(self, client: TestClient, db, fake_redis, manager_headers):
        """فلتر room_type يعزل النتائج — عقد 2R لا يؤثر على متاح 4R."""
        branch = _make_branch(db)
        _make_contract(db, branch.id, week_number=5, room_type="2R")
        year = date.today().year

        resp_2r = client.get(
            "/api/v1/timeshare/available-weeks",
            params={"branch_id": branch.id, "year": year, "room_type": "2R"},
            headers=manager_headers,
        )
        resp_4r = client.get(
            "/api/v1/timeshare/available-weeks",
            params={"branch_id": branch.id, "year": year, "room_type": "4R"},
            headers=manager_headers,
        )
        assert resp_2r.status_code == 200
        assert resp_4r.status_code == 200

        avail_2r = [w["week"] for w in resp_2r.json()["available_weeks"]]
        avail_4r = [w["week"] for w in resp_4r.json()["available_weeks"]]
        assert 5 not in avail_2r, "الأسبوع 5 يجب أن يكون محجوزاً في 2R"
        assert 5 in avail_4r, "الأسبوع 5 يجب أن يكون متاحاً في 4R"

    def test_invalid_room_type_rejected(self, client: TestClient, db, fake_redis, manager_headers):
        """نوع غرفة غير صالح يُرفض بـ 422."""
        branch = _make_branch(db)
        resp = client.get(
            "/api/v1/timeshare/available-weeks",
            params={"branch_id": branch.id, "year": date.today().year, "room_type": "XXX"},
            headers=manager_headers,
        )
        assert resp.status_code == 422

    def test_response_structure(self, client: TestClient, db, fake_redis, manager_headers):
        """الـ response فيه الحقول المطلوبة كلها."""
        branch = _make_branch(db)
        year = date.today().year
        resp = client.get(
            "/api/v1/timeshare/available-weeks",
            params={"branch_id": branch.id, "year": year},
            headers=manager_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "year" in data
        assert "total_available" in data
        assert "total_booked" in data
        assert "available_weeks" in data
        if data["available_weeks"]:
            w = data["available_weeks"][0]
            assert "week" in w
            assert "start_date" in w
            assert "end_date" in w


# ── send_visit_reminders — عقود عائمة ────────────────────────────────────────

class TestFloatingVisitReminders:
    """تذكيرات الزيارات للعقود العائمة."""

    def test_floating_visit_in_3_days_triggers_reminder(self, db):
        """زيارة عائمة مجدولة بعد 3 أيام تُرسل تذكير واتساب."""
        import app.core.kernel.whatsapp as wa_module
        sent = []
        original = wa_module.send_whatsapp_message
        wa_module.send_whatsapp_message = lambda phone, msg: sent.append(phone)

        try:
            from app.modules.core.models import Branch
            b = Branch(name=f"Rem-{uuid.uuid4().hex[:6]}", code=f"R{uuid.uuid4().hex[:4].upper()}")
            db.add(b)
            db.commit()

            contract = _make_contract(db, b.id, week_number=None)  # عائم
            contract.customer_phone = "01055556666"
            db.commit()

            reminder_day = date.today() + timedelta(days=3)
            _make_visit(db, contract, b.id, reminder_day, reminder_day + timedelta(days=7))

            from app.modules.timeshare.models import TimeshareVisit, TimeshareContract
            floating_visits = (
                db.query(TimeshareVisit)
                .join(TimeshareContract, TimeshareContract.id == TimeshareVisit.contract_id)
                .filter(
                    TimeshareContract.status == "active",
                    TimeshareContract.week_number.is_(None),
                    TimeshareVisit.status == "scheduled",
                    TimeshareVisit.check_in == reminder_day,
                )
                .all()
            )
            for v in floating_visits:
                c = v.contract
                if c and c.customer_phone:
                    wa_module.send_whatsapp_message(c.customer_phone, f"تذكير زيارة {v.check_in}")

            assert "01055556666" in sent

        finally:
            wa_module.send_whatsapp_message = original

    def test_fixed_contract_excluded_from_floating_query(self, db):
        """عقد ثابت (week_number محدد) لا يظهر في استعلام العقود العائمة."""
        from app.modules.core.models import Branch
        b = Branch(name=f"Rem2-{uuid.uuid4().hex[:6]}", code=f"R2{uuid.uuid4().hex[:4].upper()}")
        db.add(b)
        db.commit()

        contract = _make_contract(db, b.id, week_number=10)  # ثابت
        reminder_day = date.today() + timedelta(days=3)
        _make_visit(db, contract, b.id, reminder_day, reminder_day + timedelta(days=7))

        from app.modules.timeshare.models import TimeshareVisit, TimeshareContract
        floating_visits = (
            db.query(TimeshareVisit)
            .join(TimeshareContract, TimeshareContract.id == TimeshareVisit.contract_id)
            .filter(
                TimeshareContract.status == "active",
                TimeshareContract.week_number.is_(None),  # عائمة فقط
                TimeshareVisit.status == "scheduled",
                TimeshareVisit.check_in == reminder_day,
            )
            .all()
        )
        assert contract.id not in [v.contract_id for v in floating_visits]

    def test_reminder_task_runs_without_error(self, db):
        """send_visit_reminders يشتغل بدون exception مع بيانات عائمة."""
        import app.core.kernel.whatsapp as wa_module
        original = wa_module.send_whatsapp_message
        wa_module.send_whatsapp_message = lambda *a, **kw: None
        try:
            from unittest.mock import patch, MagicMock
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=db)
            ctx.__exit__ = MagicMock(return_value=False)
            with patch("app.core.database.SessionLocal", return_value=ctx):
                from app.tasks.timeshare_tasks import send_visit_reminders
                send_visit_reminders()
        finally:
            wa_module.send_whatsapp_message = original


# ── crud.get_booked_week_numbers ──────────────────────────────────────────────

class TestGetBookedWeekNumbers:
    """اختبارات وحدة مباشرة لـ crud.get_booked_week_numbers."""

    def test_fixed_contract_counted_as_booked(self, db):
        """عقد ثابت يُضاف لمجموعة الأسابيع المحجوزة."""
        from app.modules.timeshare import crud as ts_crud
        from app.modules.core.models import Branch
        b = Branch(name=f"Booked-{uuid.uuid4().hex[:6]}", code=f"BK{uuid.uuid4().hex[:4].upper()}")
        db.add(b)
        db.commit()

        _make_contract(db, b.id, week_number=7)
        year = date.today().year
        booked = ts_crud.get_booked_week_numbers(db, b.id, year)
        assert 7 in booked

    def test_floating_scheduled_visit_counted_as_booked(self, db):
        """زيارة مجدولة (عقد عائم) تُضاف لمجموعة الأسابيع المحجوزة."""
        from app.modules.timeshare import crud as ts_crud
        from app.modules.core.models import Branch
        b = Branch(name=f"Booked2-{uuid.uuid4().hex[:6]}", code=f"B2{uuid.uuid4().hex[:4].upper()}")
        db.add(b)
        db.commit()

        contract = _make_contract(db, b.id, week_number=None)
        year = date.today().year
        check_in = date.fromisocalendar(year, 33, 1)
        _make_visit(db, contract, b.id, check_in, check_in + timedelta(days=7))

        booked = ts_crud.get_booked_week_numbers(db, b.id, year)
        assert 33 in booked

    def test_cancelled_visit_not_counted(self, db):
        """زيارة ملغاة لا تُحسب ضمن المحجوز."""
        from app.modules.timeshare import crud as ts_crud
        from app.modules.core.models import Branch
        b = Branch(name=f"Booked3-{uuid.uuid4().hex[:6]}", code=f"B3{uuid.uuid4().hex[:4].upper()}")
        db.add(b)
        db.commit()

        contract = _make_contract(db, b.id, week_number=None)
        year = date.today().year
        check_in = date.fromisocalendar(year, 45, 1)
        _make_visit(db, contract, b.id, check_in, check_in + timedelta(days=7), status="cancelled")

        booked = ts_crud.get_booked_week_numbers(db, b.id, year)
        assert 45 not in booked

    def test_room_type_filter_isolates(self, db):
        """فلتر room_type يعزل العقود بشكل صحيح."""
        from app.modules.timeshare import crud as ts_crud
        from app.modules.core.models import Branch
        b = Branch(name=f"Booked4-{uuid.uuid4().hex[:6]}", code=f"B4{uuid.uuid4().hex[:4].upper()}")
        db.add(b)
        db.commit()

        _make_contract(db, b.id, week_number=12, room_type="2R")
        _make_contract(db, b.id, week_number=15, room_type="4R")
        year = date.today().year

        booked_2r = ts_crud.get_booked_week_numbers(db, b.id, year, room_type="2R")
        booked_4r = ts_crud.get_booked_week_numbers(db, b.id, year, room_type="4R")
        assert 12 in booked_2r
        assert 15 not in booked_2r
        assert 15 in booked_4r
        assert 12 not in booked_4r
