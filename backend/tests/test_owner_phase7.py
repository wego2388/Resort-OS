"""
tests/test_owner_phase7.py
═══════════════════════════════════════════════════════════════════════
Owner Intelligence Cockpit — Phase 7 Tests (Decision 0004).

المرحلة 7: Shift Monitoring + Exceptions Engine
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
    secret = os.environ["SECRET_KEY"]
    now = datetime.utcnow()
    return jwt.encode(
        {"sub": email, "iat": now, "exp": now + timedelta(hours=1), "bid": branch_id},
        secret, algorithm="HS256",
    )


import uuid

def _branch(db):
    from app.modules.core.models import Branch
    code = f"T7-{uuid.uuid4().hex[:6].upper()}"
    b = Branch(name="Branch7", name_ar="فرع7", code=code, gm_phone="+201000000000")
    db.add(b); db.flush(); return b


def _owner(db, email: str, branch_id: int):
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    from app.modules.core.models import UserBranchMembership
    u = User(email=email, password_hash=get_password_hash("pw"),
             full_name="Owner7", role="owner", is_active=True, two_factor_enabled=True)
    db.add(u); db.flush()
    db.add(UserBranchMembership(user_id=u.id, branch_id=branch_id, is_active=True))
    db.commit(); db.refresh(u); return u


def _cashier_user(db, email: str):
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    u = User(email=email, password_hash=get_password_hash("pw"),
             full_name=f"كاشير {email[:8]}", role="cashier", is_active=True)
    db.add(u); db.flush(); return u


# ══════════════════════════════════════════════════════════════════════
# owner_analytics_engine — Phase 7 unit tests
# ══════════════════════════════════════════════════════════════════════

class TestScoreShiftVariance:
    def test_critical_large_variance(self):
        from app.resort_os.owner_analytics_engine import score_shift_variance
        r = score_shift_variance(1, 10, "كاشير", Decimal("-500"), is_closed=True)
        assert r.tier == "critical"

    def test_attention_medium_variance(self):
        from app.resort_os.owner_analytics_engine import score_shift_variance
        r = score_shift_variance(1, 10, "كاشير", Decimal("-80"), is_closed=True)
        assert r.tier == "attention"

    def test_normal_small_variance(self):
        from app.resort_os.owner_analytics_engine import score_shift_variance
        r = score_shift_variance(1, 10, "كاشير", Decimal("-10"), is_closed=True)
        assert r.tier == "normal"

    def test_open_shift_always_normal(self):
        """وردية مفتوحة → tier=normal بغض النظر عن variance."""
        from app.resort_os.owner_analytics_engine import score_shift_variance
        r = score_shift_variance(1, 10, "كاشير", None, is_closed=False)
        assert r.tier == "normal"

    def test_positive_variance_also_flagged(self):
        """فائض كبير أيضاً يُعتبر critical."""
        from app.resort_os.owner_analytics_engine import score_shift_variance
        r = score_shift_variance(1, 10, "كاشير", Decimal("+300"), is_closed=True)
        assert r.tier == "critical"


class TestRankExceptions:
    def test_critical_before_attention_before_watch(self):
        from app.resort_os.owner_analytics_engine import rank_exceptions, OwnerException
        exceptions = [
            OwnerException("w:1","watch","test","W","d",None,None,Decimal("1000"),Decimal("1"),"realized","src"),
            OwnerException("c:1","critical","test","C","d",None,None,Decimal("1"),Decimal("0.1"),"realized","src"),
            OwnerException("a:1","attention","test","A","d",None,None,Decimal("500"),Decimal("1"),"realized","src"),
        ]
        ranked = rank_exceptions(exceptions)
        assert ranked[0].tier == "critical"
        assert ranked[1].tier == "attention"
        assert ranked[2].tier == "watch"

    def test_within_tier_sorted_by_score(self):
        """داخل نفس الـ tier: impact×confidence تنازلي."""
        from app.resort_os.owner_analytics_engine import rank_exceptions, OwnerException
        exceptions = [
            OwnerException("c:1","critical","test","Low","d",None,None,Decimal("100"),Decimal("0.5"),"realized","src"),
            OwnerException("c:2","critical","test","High","d",None,None,Decimal("500"),Decimal("1.0"),"realized","src"),
        ]
        ranked = rank_exceptions(exceptions)
        # High: 500×1=500 > Low: 100×0.5=50
        assert ranked[0].exception_id == "c:2"

    def test_empty_list(self):
        from app.resort_os.owner_analytics_engine import rank_exceptions
        assert rank_exceptions([]) == []


class TestBuildFraudExceptions:
    def test_fraud_signal_becomes_critical(self):
        from app.resort_os.owner_analytics_engine import build_fraud_exceptions
        from app.tasks.fraud_tasks import FraudSignal
        signals = [FraudSignal(
            user_id=5, user_name="أحمد", rule="void_count",
            count=10, threshold=5, window_minutes=60,
            message="⚠️ أحمد: 10 إلغاء",
        )]
        result = build_fraud_exceptions(signals)
        assert len(result) == 1
        assert result[0].tier == "critical"
        assert result[0].category == "fraud"
        assert result[0].entity_id == 5

    def test_empty_signals(self):
        from app.resort_os.owner_analytics_engine import build_fraud_exceptions
        assert build_fraud_exceptions([]) == []


class TestBuildShiftVarianceExceptions:
    def test_critical_shift_becomes_exception(self):
        from app.resort_os.owner_analytics_engine import (
            build_shift_variance_exceptions, ShiftVarianceResult
        )
        results = [ShiftVarianceResult(
            shift_id=1, cashier_id=10, cashier_name="محمد",
            variance=Decimal("-300"), abs_variance=Decimal("300"),
            tier="critical", is_closed=True,
        )]
        exceptions = build_shift_variance_exceptions(results)
        assert len(exceptions) == 1
        assert exceptions[0].tier == "critical"
        assert exceptions[0].status == "realized"

    def test_normal_shift_not_included(self):
        from app.resort_os.owner_analytics_engine import (
            build_shift_variance_exceptions, ShiftVarianceResult
        )
        results = [ShiftVarianceResult(
            shift_id=1, cashier_id=10, cashier_name="محمد",
            variance=Decimal("-5"), abs_variance=Decimal("5"),
            tier="normal", is_closed=True,
        )]
        exceptions = build_shift_variance_exceptions(results)
        assert exceptions == []


# ══════════════════════════════════════════════════════════════════════
# HTTP API Tests — Shifts
# ══════════════════════════════════════════════════════════════════════

def test_owner_shifts_returns_200(client, db, setup_db):
    """GET /owner/shifts يعيد 200 مع البنية الصحيحة."""
    branch = _branch(db)
    owner  = _owner(db, "shifts1@test.local", branch.id)

    resp = client.get(
        "/api/v1/owner/shifts",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "shifts" in data
    assert "open_count" in data
    assert "computed_at" in data
    assert isinstance(data["shifts"], list)


def test_owner_shifts_shows_open_shifts(client, db, setup_db):
    """وردية مفتوحة تظهر في النتائج."""
    branch  = _branch(db)
    cashier = _cashier_user(db, f"csh_open_{uuid.uuid4().hex[:6]}@test.local")
    owner   = _owner(db, f"sho2_{uuid.uuid4().hex[:6]}@test.local", branch.id)

    from app.modules.finance.models import CashierShift
    shift = CashierShift(
        branch_id=branch.id, cashier_id=cashier.id, opened_by=cashier.id,
        opening_float=Decimal("500"), status="open", opened_at=datetime.utcnow(),
    )
    db.add(shift); db.commit()

    resp = client.get(
        "/api/v1/owner/shifts",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["open_count"] >= 1
    shift_ids = [s["shift_id"] for s in data["shifts"]]
    assert shift.id in shift_ids


def test_owner_shifts_has_cash_movements(client, db, setup_db):
    """حركات الكاش تظهر داخل الوردية."""
    branch  = _branch(db)
    cashier = _cashier_user(db, f"csh_mv_{uuid.uuid4().hex[:6]}@test.local")
    owner   = _owner(db, f"shmv_{uuid.uuid4().hex[:6]}@test.local", branch.id)

    from app.modules.finance.models import CashierShift, CashMovement
    shift = CashierShift(
        branch_id=branch.id, cashier_id=cashier.id, opened_by=cashier.id,
        opening_float=Decimal("300"), status="open", opened_at=datetime.utcnow(),
    )
    db.add(shift); db.flush()

    mv = CashMovement(
        branch_id=branch.id, shift_id=shift.id,
        movement_type="safe_drop", amount=Decimal("200"),
        reason="إيداع خزينة", performed_by=cashier.id,
    )
    db.add(mv); db.commit()

    resp = client.get(
        "/api/v1/owner/shifts",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    my_shift = next((s for s in data["shifts"] if s["shift_id"] == shift.id), None)
    assert my_shift is not None
    assert len(my_shift["cash_movements"]) >= 1
    assert my_shift["cash_movements"][0]["movement_type"] == "safe_drop"


def test_owner_shifts_no_write_allowed(client, db, setup_db):
    """لا endpoint كتابة على الورديات — المالك يقرأ فقط."""
    branch = _branch(db)
    owner  = _owner(db, f"shrd_{uuid.uuid4().hex[:6]}@test.local", branch.id)

    # محاولة POST على shifts → 405 أو 403 (لا يوجد route)
    resp = client.post(
        "/api/v1/owner/shifts",
        json={},
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code in (404, 405)


def test_owner_shifts_rejects_manager(client, db, setup_db):
    """manager يُرفض من /owner/shifts."""
    branch = _branch(db)
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    mgr = User(email=f"mgr_sh_{uuid.uuid4().hex[:6]}@t.l",
               password_hash=get_password_hash("pw"), full_name="M", role="manager", is_active=True)
    db.add(mgr); db.commit()
    resp = client.get("/api/v1/owner/shifts",
                      headers={"Authorization": f"Bearer {_tok(mgr.email, branch.id)}"})
    assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════════
# HTTP API Tests — Exceptions
# ══════════════════════════════════════════════════════════════════════

def test_owner_exceptions_returns_200(client, db, setup_db):
    """GET /owner/exceptions يعيد 200 مع البنية الصحيحة."""
    branch = _branch(db)
    owner  = _owner(db, f"exc1_{uuid.uuid4().hex[:6]}@test.local", branch.id)

    resp = client.get(
        "/api/v1/owner/exceptions",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "exceptions" in data
    assert "critical_count" in data
    assert "attention_count" in data
    assert "watch_count" in data
    assert isinstance(data["exceptions"], list)


def test_owner_exceptions_critical_before_attention(client, db, setup_db):
    """استثناء critical يجيء قبل attention في القائمة."""
    branch  = _branch(db)
    cashier = _cashier_user(db, f"csh_exc_{uuid.uuid4().hex[:6]}@test.local")
    owner   = _owner(db, f"exc2_{uuid.uuid4().hex[:6]}@test.local", branch.id)

    # وردية مغلقة بفرق كبير (critical)
    from app.modules.finance.models import CashierShift
    shift = CashierShift(
        branch_id=branch.id, cashier_id=cashier.id, opened_by=cashier.id,
        opening_float=Decimal("500"), status="closed",
        opened_at=datetime.utcnow() - timedelta(hours=2),
        closed_at=datetime.utcnow() - timedelta(hours=1),
        variance=Decimal("-500"),
    )
    db.add(shift)

    # B2B overdue (attention)
    from app.modules.beach.models import B2BContract
    contract = B2BContract(
        branch_id=branch.id, hotel_name="فندق المتأخر",
        daily_quota=30, entry_price=Decimal("80"),
        valid_from=date(2026, 1, 1), valid_until=date(2026, 12, 31),
        is_active=True, is_overdue=True,
    )
    db.add(contract); db.commit()

    resp = client.get(
        "/api/v1/owner/exceptions",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    exceptions = data["exceptions"]

    if len(exceptions) >= 2:
        tier_order = {"critical": 0, "attention": 1, "watch": 2}
        for i in range(len(exceptions) - 1):
            assert tier_order[exceptions[i]["tier"]] <= tier_order[exceptions[i+1]["tier"]]


def test_owner_exceptions_b2b_overdue_appears(client, db, setup_db):
    """B2B overdue → يظهر كاستثناء attention."""
    branch = _branch(db)
    owner  = _owner(db, f"exc3_{uuid.uuid4().hex[:6]}@test.local", branch.id)

    from app.modules.beach.models import B2BContract
    contract = B2BContract(
        branch_id=branch.id, hotel_name="فندق الاختبار",
        daily_quota=20, entry_price=Decimal("100"),
        valid_from=date(2026, 1, 1), valid_until=date(2026, 12, 31),
        is_active=True, is_overdue=True,
    )
    db.add(contract); db.commit()

    resp = client.get(
        "/api/v1/owner/exceptions",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    b2b_exceptions = [e for e in data["exceptions"] if e["category"] == "b2b_overdue"]
    assert any(e["entity_id"] == contract.id for e in b2b_exceptions)


def test_owner_exceptions_long_shift_watch(client, db, setup_db):
    """وردية مفتوحة أكثر من 12 ساعة → watch tier."""
    branch  = _branch(db)
    cashier = _cashier_user(db, f"csh_lng_{uuid.uuid4().hex[:6]}@test.local")
    owner   = _owner(db, f"exc4_{uuid.uuid4().hex[:6]}@test.local", branch.id)

    from app.modules.finance.models import CashierShift
    shift = CashierShift(
        branch_id=branch.id, cashier_id=cashier.id, opened_by=cashier.id,
        opening_float=Decimal("200"), status="open",
        opened_at=datetime.utcnow() - timedelta(hours=14),  # 14 ساعة مفتوحة
    )
    db.add(shift); db.commit()

    resp = client.get(
        "/api/v1/owner/exceptions",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    long_shifts = [e for e in data["exceptions"] if e["category"] == "long_open_shift"]
    assert any(e["tier"] == "watch" for e in long_shifts)


def test_owner_exceptions_rejects_cashier(client, db, setup_db):
    """cashier يُرفض من /owner/exceptions."""
    branch = _branch(db)
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    u = User(email=f"csh_excr_{uuid.uuid4().hex[:6]}@t.l",
             password_hash=get_password_hash("pw"), full_name="C", role="cashier", is_active=True)
    db.add(u); db.commit()
    resp = client.get("/api/v1/owner/exceptions",
                      headers={"Authorization": f"Bearer {_tok(u.email, branch.id)}"})
    assert resp.status_code == 403


def test_owner_exceptions_cache_control(client, db, setup_db):
    """Cache-Control: no-store على /owner/exceptions."""
    branch = _branch(db)
    owner  = _owner(db, f"exccc_{uuid.uuid4().hex[:6]}@test.local", branch.id)

    resp = client.get(
        "/api/v1/owner/exceptions",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("cache-control", "")


def test_owner_shifts_cache_control(client, db, setup_db):
    """Cache-Control: no-store على /owner/shifts."""
    branch = _branch(db)
    owner  = _owner(db, f"shcc_{uuid.uuid4().hex[:6]}@test.local", branch.id)

    resp = client.get(
        "/api/v1/owner/shifts",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("cache-control", "")
