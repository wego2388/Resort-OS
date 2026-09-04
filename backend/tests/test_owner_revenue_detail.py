"""
tests/test_owner_revenue_detail.py
═══════════════════════════════════════════════════════════════════════
Owner Intelligence Cockpit — Revenue breakdown/detail (2026-08-17).

طلب Mohamed الصريح بعد تجربة تطبيق المالك: الضغط على كارت "إيراد اليوم"
لازم يوريه من أنهي حساب جه الرقم ده، وبعدين يقدر ينزل لقيود اليومية
الفعلية. جانب المصروف (expense-analytics/expense-detail) كان موجود
بالفعل بدون أي تست خالص — هذا الملف يغطي النظير الجديد على جانب الإيراد،
مبني على نفس نمط test_owner_phase3.py/test_owner_phase6.py.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from jose import jwt


# ══════════════════════════════════════════════════════════════════════
# Helpers (نفس نمط test_owner_phase3.py/test_owner_phase6.py)
# ══════════════════════════════════════════════════════════════════════

def _tok(email: str, branch_id: int = 1) -> str:
    secret = os.environ["SECRET_KEY"]
    now = datetime.utcnow()
    return jwt.encode(
        {"sub": email, "iat": now, "exp": now + timedelta(hours=1), "bid": branch_id},
        secret, algorithm="HS256",
    )


def _branch(db):
    from app.modules.core.models import Branch
    code = f"REV-{uuid.uuid4().hex[:6].upper()}"
    b = Branch(name="Revenue Detail Branch", name_ar="فرع اختبار الإيراد", code=code, gm_phone="+201000000000")
    db.add(b); db.flush()
    return b


def _owner(db, email: str, branch_id: int):
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    from app.modules.core.models import UserBranchMembership
    u = User(email=email, password_hash=get_password_hash("pw"),
             full_name="Owner Revenue Detail", role="owner", is_active=True, two_factor_enabled=True)
    db.add(u); db.flush()
    db.add(UserBranchMembership(user_id=u.id, branch_id=branch_id, is_active=True))
    db.commit(); db.refresh(u); return u


def _manager(db, email: str, branch_id: int):
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    from app.modules.core.models import UserBranchMembership
    u = User(email=email, password_hash=get_password_hash("pw"),
             full_name="Manager", role="manager", is_active=True, two_factor_enabled=True)
    db.add(u); db.flush()
    db.add(UserBranchMembership(user_id=u.id, branch_id=branch_id, is_active=True))
    db.commit(); db.refresh(u); return u


def _post_revenue(db, branch_id, *, credit_code: str, credit_name: str, amount: Decimal,
                   entry_date: date, reference: str, source: str, source_id: int):
    """يزرع قيد إيراد حقيقي متوازن عبر post_simple_revenue_journal — نفس
    الدالة المشتركة اللي كل موديول حقيقي (دايننج/شاطئ/PMS/ملكية جزئية)
    بيرحّل بيها، مش SQL خام."""
    from app.modules.finance import crud as finance_crud, services as finance_services
    from app.modules.finance.schemas import AccountCreate

    finance_crud.create_account(db, AccountCreate(
        branch_id=branch_id, code="1100", name="Cash", account_type="asset",
    )) if not finance_crud.get_account_by_code(db, branch_id, "1100") else None
    finance_crud.create_account(db, AccountCreate(
        branch_id=branch_id, code=credit_code, name=credit_name, account_type="revenue",
    )) if not finance_crud.get_account_by_code(db, branch_id, credit_code) else None
    db.commit()

    entry = finance_services.post_simple_revenue_journal(
        db, branch_id, entry_date,
        debit_account_code="1100", credit_account_code=credit_code,
        amount=amount, reference=reference, description=f"اختبار — {credit_name}",
        source=source, source_id=source_id,
    )
    assert entry is not None, "post_simple_revenue_journal رجع None — الحساب غير موجود/غير نشط"
    return entry


# ══════════════════════════════════════════════════════════════════════
# GET /owner/revenue-breakdown
# ══════════════════════════════════════════════════════════════════════

def test_revenue_breakdown_matches_income_statement(client, db, setup_db):
    """revenue_lines لازم يطابق get_income_statement بالحرف — نفس مصدر
    الحقيقة المستخدم لأي رقم مالي أساسي تاني (Decision 0004)."""
    from app.modules.finance.services import get_income_statement

    branch = _branch(db)
    owner = _owner(db, "revbreak1@test.local", branch.id)
    today = date.today()

    _post_revenue(db, branch.id, credit_code="4100", credit_name="Room Revenue",
                  amount=Decimal("500.00"), entry_date=today,
                  reference="REV-BRK-1", source="test_revenue_breakdown", source_id=1)
    _post_revenue(db, branch.id, credit_code="4600", credit_name="Timeshare Installments",
                  amount=Decimal("250.00"), entry_date=today,
                  reference="REV-BRK-2", source="test_revenue_breakdown", source_id=2)

    stmt = get_income_statement(db, branch.id, today, today)

    resp = client.get(
        "/api/v1/owner/revenue-breakdown",
        params={"date_from": today.isoformat(), "date_to": today.isoformat()},
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert Decimal(data["total_revenue"]) == stmt.total_revenue
    by_code = {line["account_code"]: Decimal(line["amount"]) for line in data["revenue_lines"]}
    for line in stmt.revenue_lines:
        assert by_code[line.account_code] == line.amount

    # مرتّبة تنازليًا حسب المبلغ — أهم حساب أولاً
    amounts = [Decimal(line["amount"]) for line in data["revenue_lines"]]
    assert amounts == sorted(amounts, reverse=True)


def test_revenue_breakdown_defaults_to_current_month(client, db, setup_db):
    """من غير date_from/date_to → نفس _default_range المستخدم في كل مكان تاني."""
    branch = _branch(db)
    owner = _owner(db, "revbreak2@test.local", branch.id)

    resp = client.get(
        "/api/v1/owner/revenue-breakdown",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    today = date.today()
    assert data["period_from"] == today.replace(day=1).isoformat()
    assert data["period_to"] == today.isoformat()


def test_revenue_breakdown_rejects_manager(client, db, setup_db):
    """get_owner_reader — owner أو super_admin بس، مش manager."""
    branch = _branch(db)
    manager = _manager(db, "revbreak3@test.local", branch.id)

    resp = client.get(
        "/api/v1/owner/revenue-breakdown",
        headers={"Authorization": f"Bearer {_tok(manager.email, branch.id)}"},
    )
    assert resp.status_code == 403


def test_revenue_breakdown_cache_control_no_store(client, db, setup_db):
    branch = _branch(db)
    owner = _owner(db, "revbreak4@test.local", branch.id)

    resp = client.get(
        "/api/v1/owner/revenue-breakdown",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("cache-control", "")


# ══════════════════════════════════════════════════════════════════════
# GET /owner/revenue-detail
# ══════════════════════════════════════════════════════════════════════

def test_revenue_detail_returns_journal_lines_for_account(client, db, setup_db):
    """كل سطر دائن حقيقي داخل الحساب المطلوب — مش سطور المدين (الكاش) ولا
    حسابات تانية."""
    branch = _branch(db)
    owner = _owner(db, "revdet1@test.local", branch.id)
    today = date.today()

    entry = _post_revenue(db, branch.id, credit_code="4100", credit_name="Room Revenue",
                           amount=Decimal("777.25"), entry_date=today,
                           reference="REV-DET-1", source="test_revenue_detail", source_id=10)
    # حساب إيراد تاني — مايجيش في نتيجة 4100
    _post_revenue(db, branch.id, credit_code="4600", credit_name="Timeshare Installments",
                  amount=Decimal("999.00"), entry_date=today,
                  reference="REV-DET-2", source="test_revenue_detail", source_id=11)

    resp = client.get(
        "/api/v1/owner/revenue-detail",
        params={"account_code": "4100", "date_from": today.isoformat(), "date_to": today.isoformat()},
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["account_code"] == "4100"
    assert data["account_name"] == "Room Revenue"
    assert Decimal(data["total_amount"]) == Decimal("777.25")
    assert len(data["lines"]) == 1
    line = data["lines"][0]
    assert line["entry_id"] == entry.id
    assert line["reference"] == "REV-DET-1"
    assert Decimal(line["amount"]) == Decimal("777.25")
    assert line["source"] == "test_revenue_detail"


def test_revenue_detail_unknown_account_returns_empty(client, db, setup_db):
    """كود حساب مش موجود — استجابة فاضية سليمة البنية، مش 500/404."""
    branch = _branch(db)
    owner = _owner(db, "revdet2@test.local", branch.id)

    resp = client.get(
        "/api/v1/owner/revenue-detail",
        params={"account_code": "9999-NOPE"},
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["lines"] == []
    assert Decimal(data["total_amount"]) == Decimal("0")
    assert data["total_items"] == 0


def test_revenue_detail_pagination(client, db, setup_db):
    """size=1 يرجّع سطر واحد بس، مع total_items/total_pages صح."""
    branch = _branch(db)
    owner = _owner(db, "revdet3@test.local", branch.id)
    today = date.today()

    for i in range(3):
        _post_revenue(db, branch.id, credit_code="4100", credit_name="Room Revenue",
                      amount=Decimal("100.00"), entry_date=today,
                      reference=f"REV-PAGE-{i}", source="test_revenue_detail_page", source_id=100 + i)

    resp = client.get(
        "/api/v1/owner/revenue-detail",
        params={"account_code": "4100", "page": 1, "size": 1,
                "date_from": today.isoformat(), "date_to": today.isoformat()},
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["lines"]) == 1
    assert data["total_items"] == 3
    assert data["total_pages"] == 3
    assert Decimal(data["total_amount"]) == Decimal("300.00")


def test_revenue_detail_rejects_manager(client, db, setup_db):
    branch = _branch(db)
    manager = _manager(db, "revdet4@test.local", branch.id)

    resp = client.get(
        "/api/v1/owner/revenue-detail",
        params={"account_code": "4100"},
        headers={"Authorization": f"Bearer {_tok(manager.email, branch.id)}"},
    )
    assert resp.status_code == 403


def test_revenue_detail_scoped_to_branch(client, db, setup_db):
    """قيد إيراد في فرع تاني — ما يظهرش في تفاصيل حساب بنفس الكود في فرعك."""
    branch_a = _branch(db)
    branch_b = _branch(db)
    owner_a = _owner(db, "revdet5@test.local", branch_a.id)
    today = date.today()

    _post_revenue(db, branch_b.id, credit_code="4100", credit_name="Room Revenue",
                  amount=Decimal("5000.00"), entry_date=today,
                  reference="REV-OTHER-BRANCH", source="test_revenue_detail_branch", source_id=1)

    resp = client.get(
        "/api/v1/owner/revenue-detail",
        params={"account_code": "4100", "date_from": today.isoformat(), "date_to": today.isoformat()},
        headers={"Authorization": f"Bearer {_tok(owner_a.email, branch_a.id)}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["lines"] == []
    assert Decimal(data["total_amount"]) == Decimal("0")
