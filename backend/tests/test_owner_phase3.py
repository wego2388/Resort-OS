"""
tests/test_owner_phase3.py
═══════════════════════════════════════════════════════════════════════
Owner Intelligence Cockpit — Phase 3 Tests (Decision 0004).

المرحلة 3: Aggregation APIs — /owner/now + /owner/performance
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import os
from datetime import datetime, date, timedelta
from decimal import Decimal

import pytest
from jose import jwt


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _tok(email: str, branch_id: int = 1) -> str:
    """JWT token مطابق لـ _make_token في conftest.
    branch_id يُمرَّر كـ `bid` claim ليُعيَّن على user._active_branch_id
    بواسطة _resolve_user_from_token في deps.py (نمط CX-02C)."""
    secret = os.environ["SECRET_KEY"]
    now = datetime.utcnow()
    return jwt.encode(
        {"sub": email, "iat": now, "exp": now + timedelta(hours=1), "bid": branch_id},
        secret,
        algorithm="HS256",
    )


import uuid

def _get_or_create_branch(db, code: str = None):
    """يجيب أو ينشئ branch اختبارية — يتجنّب UNIQUE conflict عند تكرار الـ code."""
    from app.modules.core.models import Branch
    if code is None:
        code = f"TST-{uuid.uuid4().hex[:6].upper()}"
    existing = db.query(Branch).filter(Branch.code == code).first()
    if existing:
        return existing
    branch = Branch(
        name="Test Branch",
        name_ar="الفرع الاختباري",
        code=code,
        gm_phone="+201000000000",
    )
    db.add(branch)
    db.flush()
    return branch


def _create_owner(db, email: str = "owner_ph3@test.local", branch_id: int = 1):
    """ينشئ owner user + UserBranchMembership ويعيده.

    الـ owner (level=10) يحتاج صف UserBranchMembership ليتمكّن من الوصول
    للـ branch — _can_enter_branch في core/services.py بيتحقق منه.
    """
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    from app.modules.core.models import UserBranchMembership

    u = User(
        email=email,
        password_hash=get_password_hash("pw"),
        full_name="Owner Phase3",
        role="owner",
        is_active=True,
        two_factor_enabled=True,
    )
    db.add(u)
    db.flush()

    membership = UserBranchMembership(
        user_id=u.id,
        branch_id=branch_id,
        is_active=True,
    )
    db.add(membership)
    db.commit()
    db.refresh(u)
    return u


# ══════════════════════════════════════════════════════════════════════
# Tests: GET /owner/now
# ══════════════════════════════════════════════════════════════════════

def test_owner_now_returns_all_seven_metrics(client, db, setup_db):
    """يتحقق من أن /owner/now يعيد كل المقاييس السبعة (A-1 → A-7) بالبنية الصحيحة."""
    branch = _get_or_create_branch(db)
    owner = _create_owner(db, "now1@test.local", branch.id)

    resp = client.get(
        "/api/v1/owner/now",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # التحقق من المقاييس المالية الأساسية
    assert "revenue_today" in data
    assert isinstance(data["revenue_today"], (int, float, str))  # Decimal → JSON
    assert "cash_in_drawers" in data
    assert "expense_today" in data

    # التحقق من ذمم B2B (A-4)
    assert "b2b_receivables" in data
    assert isinstance(data["b2b_receivables"], list)
    assert "b2b_total_outstanding" in data

    # التحقق من ذمم ملكية جزئية (A-5)
    assert "timeshare_receivables" in data
    assert isinstance(data["timeshare_receivables"], list)
    assert "timeshare_total_overdue" in data

    # التحقق من إشغال الغرف (A-6)
    assert "occupancy" in data
    occ = data["occupancy"]
    assert "occupied_rooms" in occ
    assert "total_rooms" in occ
    assert "occupancy_pct" in occ

    # التحقق من سعة الشاطئ (A-7)
    assert "beach_capacity" in data
    beach = data["beach_capacity"]
    assert "capacity_used" in beach
    assert "capacity_max" in beach
    assert "utilisation_pct" in beach
    assert "note" in beach

    # التحقق من ميتاداتا الفترة
    assert "period" in data
    period = data["period"]
    assert "date_from" in period
    assert "date_to" in period
    assert "is_provisional" in period
    assert period["is_provisional"] is True  # اليوم دايماً provisional
    assert "computed_at" in period

    # عدد الورديات المفتوحة
    assert "open_shift_count" in data
    assert isinstance(data["open_shift_count"], int)


def test_owner_now_revenue_equals_income_statement(client, db, setup_db):
    """يتحقق من أن A-1 (revenue_today) مساوٍ بالضبط لـ get_income_statement."""
    branch = _get_or_create_branch(db)
    from app.modules.finance.services import get_income_statement
    from app.resort_os.timezone_utils import business_today
    from app.core.config import get_settings

    owner = _create_owner(db, "now2@test.local", branch.id)
    today = business_today(get_settings().TIMEZONE)

    # نقرأ الإيراد مباشرةً من finance
    stmt = get_income_statement(db, branch.id, today, today)
    expected_revenue = stmt.total_revenue

    resp = client.get(
        "/api/v1/owner/now",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    # Decimal equality — يُسمح بـ ±0.01 rounding
    actual = Decimal(str(data["revenue_today"]))
    assert abs(actual - expected_revenue) <= Decimal("0.01")


def test_owner_now_cash_in_drawers_equals_active_shifts(client, db, setup_db):
    """يتحقق من أن A-2 (cash_in_drawers) مساوٍ لمجموع expected_cash على كل الورديات المفتوحة."""
    branch = _get_or_create_branch(db)
    from app.modules.finance.services import build_active_shifts_response
    from app.modules.finance.models import CashierShift
    from app.modules.owner import services
    from decimal import Decimal

    owner = _create_owner(db, "now3@test.local", branch.id)

    # نفتح وردية واحدة
    shift = CashierShift(
        branch_id=branch.id,
        cashier_id=owner.id,
        opened_at=datetime.utcnow(),
        opened_by=owner.id,
        opening_float=Decimal("500"),
        status="open",
    )
    db.add(shift)
    db.commit()

    # نقرأ من finance مباشرةً
    shifts_resp = build_active_shifts_response(db, branch.id)
    expected_cash = sum((s.expected_cash for s in shifts_resp.shifts), Decimal("0"))

    resp = client.get(
        "/api/v1/owner/now",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    actual = Decimal(str(data["cash_in_drawers"]))
    assert abs(actual - expected_cash) <= Decimal("0.01")


def test_owner_now_b2b_receivables_per_contract_no_guest_data(client, db, setup_db):
    """يتحقق من A-4: ذمم B2B مجمّعة per contract — لا تحتوي على بيانات ضيف."""
    branch = _get_or_create_branch(db)
    from app.modules.beach.models import B2BContract, B2BContractDay
    from datetime import date

    owner = _create_owner(db, "now4@test.local", branch.id)

    # ننشئ عقد B2B نشط
    contract = B2BContract(
        branch_id=branch.id,
        hotel_name="فندق الاختبار",
        hotel_name_ar="فندق الاختبار",
        daily_quota=50,
        entry_price=Decimal("100"),
        towel_price=Decimal("20"),
        valid_from=date(2026, 1, 1),
        valid_until=date(2026, 12, 31),
        is_active=True,
        credit_limit=Decimal("5000"),
        is_overdue=False,
        last_settled_at=date(2026, 7, 1),
    )
    db.add(contract)
    db.commit()

    # نضيف يوم استخدام بعد last_settled_at
    day = B2BContractDay(
        contract_id=contract.id,
        day=date(2026, 7, 5),
        checked_in_count=10,
        total_amount=Decimal("1000"),
    )
    db.add(day)
    db.commit()

    resp = client.get(
        "/api/v1/owner/now",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    # التحقق من عدم وجود أي بيانات ضيف
    b2b = data["b2b_receivables"]
    assert len(b2b) == 1
    item = b2b[0]
    assert "contract_id" in item
    assert "hotel_name" in item
    assert item["hotel_name"] == "فندق الاختبار"
    assert "outstanding" in item
    assert Decimal(str(item["outstanding"])) == Decimal("1000")

    # لا يوجد guest_name أو phone أو أي بيانات شخصية
    assert "guest_name" not in item
    assert "guest_phone" not in item
    assert "guest_email" not in item


def test_owner_now_occupancy_excludes_maintenance_rooms(client, db, setup_db):
    """يتحقق من A-6: إشغال الغرف يستثني maintenance/out_of_order من المقام."""
    branch = _get_or_create_branch(db)
    from app.modules.pms.models import Room, RoomType

    owner = _create_owner(db, "now5@test.local", branch.id)

    # ننشئ room type
    rt = RoomType(
        branch_id=branch.id,
        name="Standard",
        base_rate=Decimal("500"),
        max_occupancy=2,
    )
    db.add(rt)
    db.commit()

    # ننشئ 5 غرف: 2 occupied، 1 available، 2 maintenance
    for i, status in enumerate(["occupied", "occupied", "available", "maintenance", "maintenance"], start=1):
        r = Room(
            branch_id=branch.id,
            room_type_id=rt.id,
            name=f"10{i}",
            floor=1,
            status=status,
        )
        db.add(r)
    db.commit()

    resp = client.get(
        "/api/v1/owner/now",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    occ = data["occupancy"]
    assert occ["occupied_rooms"] == 2
    # المقام: 5 - 2 maintenance = 3
    assert occ["total_rooms"] == 3
    # النسبة: 2/3 * 100 = 66.7%
    assert Decimal(str(occ["occupancy_pct"])) == Decimal("66.7")


def test_owner_now_beach_capacity_cumulative_warning(client, db, setup_db):
    """يتحقق من A-7: capacity_used عدّاد تراكمي + note تحذيري."""
    branch = _get_or_create_branch(db)
    from app.modules.beach.models import BeachInventory
    from datetime import date

    owner = _create_owner(db, "now6@test.local", branch.id)

    today = date.today()
    inv = BeachInventory(
        branch_id=branch.id,
        inventory_date=today,
        capacity_max=200,
        capacity_used=150,  # عدّاد تراكمي
        towels_total=200,
        towels_available=100,
        towels_used=100,
    )
    db.add(inv)
    db.commit()

    resp = client.get(
        "/api/v1/owner/now",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    beach = data["beach_capacity"]
    assert beach["capacity_used"] == 150
    assert beach["capacity_max"] == 200
    assert Decimal(str(beach["utilisation_pct"])) == Decimal("75.0")
    # التحقق من Note التحذيري
    assert "تذاكر مباعة اليوم" in beach["note"]
    assert "تراكمي" in beach["note"]


# ══════════════════════════════════════════════════════════════════════
# Tests: GET /owner/performance
# ══════════════════════════════════════════════════════════════════════

def test_owner_performance_returns_three_comparisons(client, db, setup_db):
    """يتحقق من أن /owner/performance يعيد المقارنات الثلاث: يوم/أسبوع/شهر."""
    branch = _get_or_create_branch(db)
    owner = _create_owner(db, "perf1@test.local", branch.id)

    resp = client.get(
        "/api/v1/owner/performance",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # التحقق من المقارنات الثلاث
    assert "today_vs_yesterday" in data
    assert "week_vs_prior_week" in data
    assert "month_vs_prior_month" in data
    assert "computed_at" in data

    # كل مقارنة تحتوي على current + prior + deltas
    for comp_key in ["today_vs_yesterday", "week_vs_prior_week", "month_vs_prior_month"]:
        comp = data[comp_key]
        assert "current" in comp
        assert "prior" in comp
        assert "revenue_delta" in comp
        assert "expense_delta" in comp
        assert "net_income_delta" in comp

        # كل snapshot يحتوي على الحقول المطلوبة
        for snap in [comp["current"], comp["prior"]]:
            assert "date_from" in snap
            assert "date_to" in snap
            assert "label" in snap
            assert "total_revenue" in snap
            assert "total_expense" in snap
            assert "net_income" in snap
            assert "is_provisional" in snap


def test_owner_performance_delta_computed_correctly(client, db, setup_db):
    """يتحقق من أن الـ delta والنسب محسوبة صح (اليوم vs أمس)."""
    branch = _get_or_create_branch(db)
    from app.modules.finance.services import get_income_statement
    from app.resort_os.timezone_utils import business_today
    from app.core.config import get_settings

    owner = _create_owner(db, "perf2@test.local", branch.id)
    
    today = business_today(get_settings().TIMEZONE)
    yesterday = today - timedelta(days=1)

    # نقرأ الإيراد مباشرةً
    stmt_today = get_income_statement(db, branch.id, today, today)
    stmt_yesterday = get_income_statement(db, branch.id, yesterday, yesterday)

    expected_delta = stmt_today.total_revenue - stmt_yesterday.total_revenue

    resp = client.get(
        "/api/v1/owner/performance",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    comp = data["today_vs_yesterday"]
    actual_delta = Decimal(str(comp["revenue_delta"]))
    assert abs(actual_delta - expected_delta) <= Decimal("0.01")


def test_owner_performance_handles_zero_prior_revenue(client, db, setup_db):
    """يتحقق من أن revenue_pct = None لو prior كان صفراً (تجنّب ZeroDivisionError)."""
    branch = _get_or_create_branch(db)
    owner = _create_owner(db, "perf3@test.local", branch.id)

    resp = client.get(
        "/api/v1/owner/performance",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    # في بيئة اختبار فارغة، prior revenue دايماً صفر
    comp = data["today_vs_yesterday"]
    # لو prior كان صفراً، revenue_pct يكون None (مش inf/nan)
    if Decimal(str(comp["prior"]["total_revenue"])) == Decimal("0"):
        assert comp["revenue_pct"] is None
    else:
        # لو فيه قيمة، لازم تكون رقم
        assert isinstance(comp["revenue_pct"], (int, float, str))


# ══════════════════════════════════════════════════════════════════════
# Tests: Authorization
# ══════════════════════════════════════════════════════════════════════

def test_owner_now_rejects_cashier(client, db, setup_db):
    """cashier (level 40) يُرفض من /owner/now."""
    branch = _get_or_create_branch(db)
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash

    u = User(
        email="cashier_now@test.local",
        password_hash=get_password_hash("pw"),
        full_name="Cashier",
        role="cashier",
        is_active=True,
    )
    db.add(u)
    db.commit()

    resp = client.get(
        "/api/v1/owner/now",
        headers={"Authorization": f"Bearer {_tok(u.email, branch.id)}"},
    )
    assert resp.status_code == 403


def test_owner_performance_rejects_manager(client, db, setup_db):
    """manager (level 60) يُرفض من /owner/performance."""
    branch = _get_or_create_branch(db)
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash

    u = User(
        email="mgr_perf@test.local",
        password_hash=get_password_hash("pw"),
        full_name="Manager",
        role="manager",
        is_active=True,
    )
    db.add(u)
    db.commit()

    resp = client.get(
        "/api/v1/owner/performance",
        headers={"Authorization": f"Bearer {_tok(u.email, branch.id)}"},
    )
    assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════════
# Tests: branch_id server-side derivation
# ══════════════════════════════════════════════════════════════════════

def test_owner_now_ignores_client_branch_id(client, db, setup_db):
    """يتحقق من أن branch_id من الـ client مُتجاهل تماماً."""
    branch = _get_or_create_branch(db)
    owner = _create_owner(db, "branch_test@test.local", branch.id)

    # نرسل branch_id=9999 في الـ query string — يجب أن يُتجاهل
    resp = client.get(
        "/api/v1/owner/now?branch_id=9999",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    # يجب أن ينجح (200) لأن branch_id يُشتق من الـ session
    # ويعود بـ branch_id الصحيح من الـ session
    assert resp.status_code == 200


def test_owner_performance_ignores_client_branch_id(client, db, setup_db):
    """يتحقق من أن branch_id من الـ client مُتجاهل في /owner/performance."""
    branch = _get_or_create_branch(db)
    owner = _create_owner(db, "branch_test2@test.local", branch.id)

    resp = client.get(
        "/api/v1/owner/performance?branch_id=9999",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════════
# Tests: OwnerNow schema validation (unit, بدون HTTP)
# ══════════════════════════════════════════════════════════════════════

def test_period_meta_provisional_for_open_period():
    """PeriodMeta.is_provisional يحمل True لفترة مفتوحة."""
    from app.modules.owner.schemas import PeriodMeta

    meta = PeriodMeta(
        date_from=date.today(),
        date_to=date.today(),
        is_provisional=True,
        computed_at=datetime.utcnow(),
    )
    assert meta.is_provisional is True


def test_period_comparison_pct_none_when_denominator_zero():
    """_safe_pct يعيد None لو المقام صفر."""
    from app.modules.owner.services import _safe_pct

    result = _safe_pct(Decimal("100"), Decimal("0"))
    assert result is None


def test_period_comparison_pct_correct():
    """_safe_pct يعيد النسبة الصحيحة."""
    from app.modules.owner.services import _safe_pct

    # 120 مقارنة بـ 100 = +20%
    result = _safe_pct(Decimal("120"), Decimal("100"))
    assert result == Decimal("20.00")


def test_b2b_receivable_item_no_pii_fields():
    """B2BReceivableItem لا يحتوي على أي حقل بيانات شخصية (PII)."""
    from app.modules.owner.schemas import B2BReceivableItem
    import inspect

    fields = set(B2BReceivableItem.model_fields.keys())
    pii_field_names = {"guest_name", "guest_phone", "guest_email", "customer_name",
                       "phone", "email", "national_id", "passport"}
    assert fields.isdisjoint(pii_field_names), f"B2BReceivableItem يحتوي على حقول PII: {fields & pii_field_names}"


def test_owner_now_response_has_period_meta():
    """OwnerNowResponse تحتوي على period field لازمة."""
    from app.modules.owner.schemas import OwnerNowResponse
    assert "period" in OwnerNowResponse.model_fields
    assert "open_shift_count" in OwnerNowResponse.model_fields


def test_owner_performance_response_has_three_comparisons():
    """OwnerPerformanceResponse تحتوي على الثلاث مقارنات المطلوبة."""
    from app.modules.owner.schemas import OwnerPerformanceResponse
    fields = set(OwnerPerformanceResponse.model_fields.keys())
    assert "today_vs_yesterday" in fields
    assert "week_vs_prior_week" in fields
    assert "month_vs_prior_month" in fields
    assert "computed_at" in fields
