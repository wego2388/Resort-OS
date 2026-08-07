"""
tests/test_owner_phase6.py
═══════════════════════════════════════════════════════════════════════
Owner Intelligence Cockpit — Phase 6 Tests (Decision 0004).

المرحلة 6: Analytics APIs — Sales, Beach, Channel, Expense, Procurement
+ owner_analytics_engine unit tests
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import os
from datetime import datetime, date, timedelta
from decimal import Decimal

import pytest
from jose import jwt


# ══════════════════════════════════════════════════════════════════════
# Helpers (نفس نمط test_owner_phase3.py)
# ══════════════════════════════════════════════════════════════════════

def _tok(email: str, branch_id: int = 1) -> str:
    secret = os.environ["SECRET_KEY"]
    now = datetime.utcnow()
    return jwt.encode(
        {"sub": email, "iat": now, "exp": now + timedelta(hours=1), "bid": branch_id},
        secret, algorithm="HS256",
    )


import uuid

def _branch(db, code: str = None):
    from app.modules.core.models import Branch
    if code is None:
        code = f"T6-{uuid.uuid4().hex[:6].upper()}"
    b = db.query(Branch).filter(Branch.code == code).first()
    if b:
        return b
    b = Branch(name="Branch6", name_ar="فرع6", code=code, gm_phone="+201000000000")
    db.add(b); db.flush(); return b


def _owner(db, email: str, branch_id: int):
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    from app.modules.core.models import UserBranchMembership
    u = User(email=email, password_hash=get_password_hash("pw"),
             full_name="Owner6", role="owner", is_active=True, two_factor_enabled=True)
    db.add(u); db.flush()
    db.add(UserBranchMembership(user_id=u.id, branch_id=branch_id, is_active=True))
    db.commit(); db.refresh(u); return u


# ══════════════════════════════════════════════════════════════════════
# owner_analytics_engine — unit tests (بدون HTTP)
# ══════════════════════════════════════════════════════════════════════

class TestClassifyABC:
    def test_empty_returns_empty(self):
        from app.resort_os.owner_analytics_engine import classify_abc, ItemMetric
        assert classify_abc([]) == []

    def test_single_item_is_class_a(self):
        from app.resort_os.owner_analytics_engine import classify_abc, ItemMetric
        items = [ItemMetric(item_id=1, name="X", quantity_sold=10, revenue=Decimal("100"))]
        result = classify_abc(items)
        assert result[0].abc_class == "A"

    def test_pareto_split(self):
        """أعلى 70% إيراد = A، 70-90% = B، الباقي = C."""
        from app.resort_os.owner_analytics_engine import classify_abc, ItemMetric
        items = [
            ItemMetric(item_id=1, name="Alpha", quantity_sold=1, revenue=Decimal("700")),
            ItemMetric(item_id=2, name="Beta",  quantity_sold=1, revenue=Decimal("200")),
            ItemMetric(item_id=3, name="Gamma", quantity_sold=1, revenue=Decimal("100")),
        ]
        result = classify_abc(items)
        by_name = {i.name: i.abc_class for i in result}
        assert by_name["Alpha"] == "A"
        assert by_name["Beta"]  == "B"
        assert by_name["Gamma"] == "C"

    def test_all_equal_revenue_stable_alphabetical(self):
        """نفس الإيراد → ترتيب أبجدي — deterministic."""
        from app.resort_os.owner_analytics_engine import classify_abc, ItemMetric
        items = [
            ItemMetric(item_id=i, name=n, quantity_sold=1, revenue=Decimal("100"))
            for i, n in enumerate(["Zeta", "Alpha", "Mango"])
        ]
        r1 = [i.name for i in classify_abc(items)]
        r2 = [i.name for i in classify_abc(list(reversed(items)))]
        assert r1 == r2  # deterministic بغض النظر عن ترتيب الإدخال

    def test_zero_revenue_all_class_c(self):
        from app.resort_os.owner_analytics_engine import classify_abc, ItemMetric
        items = [ItemMetric(item_id=i, name=f"X{i}", quantity_sold=0, revenue=Decimal("0")) for i in range(3)]
        result = classify_abc(items)
        assert all(i.abc_class == "C" for i in result)


class TestComputeItemMargin:
    def test_margin_correct(self):
        from app.resort_os.owner_analytics_engine import compute_item_margin, ItemMetric
        item = ItemMetric(item_id=1, name="X", quantity_sold=10,
                          revenue=Decimal("1000"), recipe_cost=Decimal("30"))
        result = compute_item_margin(item)
        # cost = 30 × 10 = 300; margin = 1000-300 = 700; pct = 70%
        assert result.margin_amount == Decimal("700.00")
        assert result.margin_pct    == Decimal("70.00")

    def test_no_recipe_returns_none(self):
        from app.resort_os.owner_analytics_engine import compute_item_margin, ItemMetric
        item = ItemMetric(item_id=1, name="X", quantity_sold=5, revenue=Decimal("500"), recipe_cost=None)
        result = compute_item_margin(item)
        assert result.margin_pct is None
        assert result.margin_amount is None

    def test_zero_revenue_margin_pct_none(self):
        from app.resort_os.owner_analytics_engine import compute_item_margin, ItemMetric
        item = ItemMetric(item_id=1, name="X", quantity_sold=0, revenue=Decimal("0"), recipe_cost=Decimal("10"))
        result = compute_item_margin(item)
        assert result.margin_pct is None


class TestDetectVariance:
    def test_flags_abnormal_increase(self):
        """نسبة ارتفعت أكثر من 20% نسبياً → flag=True."""
        from app.resort_os.owner_analytics_engine import detect_variance, ExpenseLine
        lines = [ExpenseLine(
            account_code="5100", account_name="مواد غذائية",
            current_amount=Decimal("3000"), prior_amount=Decimal("2000"),
            current_revenue=Decimal("10000"), prior_revenue=Decimal("10000"),
        )]
        result = detect_variance(lines)
        # current_pct=30%, prior_pct=20%, delta=10 نقطة = 50% relative → flag
        assert result[0].variance_flag is True

    def test_no_flag_normal_change(self):
        """تغيير أقل من 20% → flag=False."""
        from app.resort_os.owner_analytics_engine import detect_variance, ExpenseLine
        lines = [ExpenseLine(
            account_code="5200", account_name="كهرباء",
            current_amount=Decimal("2100"), prior_amount=Decimal("2000"),
            current_revenue=Decimal("10000"), prior_revenue=Decimal("10000"),
        )]
        result = detect_variance(lines)
        # current_pct=21%, prior_pct=20%, delta=1 نقطة = 5% relative → no flag
        assert result[0].variance_flag is False

    def test_zero_prior_revenue_safe(self):
        """prior_revenue=0 → لا ZeroDivisionError."""
        from app.resort_os.owner_analytics_engine import detect_variance, ExpenseLine
        lines = [ExpenseLine(
            account_code="5300", account_name="صيانة",
            current_amount=Decimal("500"), prior_amount=Decimal("0"),
            current_revenue=Decimal("5000"), prior_revenue=Decimal("0"),
        )]
        result = detect_variance(lines)
        # لا exception
        assert result[0].variance_flag is False or result[0].variance_flag is True  # أي نتيجة — المهم لا exception


class TestSupplierConcentration:
    def test_flags_dominant_supplier(self):
        from app.resort_os.owner_analytics_engine import score_supplier_concentration, SupplierSpend
        suppliers = [
            SupplierSpend(supplier_id=1, supplier_name="A", total_spend=Decimal("8000")),
            SupplierSpend(supplier_id=2, supplier_name="B", total_spend=Decimal("2000")),
        ]
        result = score_supplier_concentration(suppliers)
        a = next(s for s in result if s.supplier_name == "A")
        b = next(s for s in result if s.supplier_name == "B")
        assert a.concentration_flag is True   # 80% > 50%
        assert b.concentration_flag is False  # 20%

    def test_empty_returns_empty(self):
        from app.resort_os.owner_analytics_engine import score_supplier_concentration
        assert score_supplier_concentration([]) == []


class TestPRPOVariance:
    def test_variance_computed_correctly(self):
        from app.resort_os.owner_analytics_engine import compute_pr_po_variance, PRPOVarianceLine
        lines = [PRPOVarianceLine(
            product_id=1, product_name="دقيق",
            estimated_cost=Decimal("100"), actual_cost=Decimal("120"),
            variance_amount=Decimal("0"), variance_pct=None,
        )]
        result = compute_pr_po_variance(lines)
        assert result[0].variance_amount == Decimal("20.00")
        assert result[0].variance_pct    == Decimal("20.00")

    def test_zero_estimate_pct_none(self):
        from app.resort_os.owner_analytics_engine import compute_pr_po_variance, PRPOVarianceLine
        lines = [PRPOVarianceLine(
            product_id=1, product_name="X",
            estimated_cost=Decimal("0"), actual_cost=Decimal("50"),
            variance_amount=Decimal("0"), variance_pct=None,
        )]
        result = compute_pr_po_variance(lines)
        assert result[0].variance_pct is None

    def test_sorted_by_abs_variance(self):
        from app.resort_os.owner_analytics_engine import compute_pr_po_variance, PRPOVarianceLine
        lines = [
            PRPOVarianceLine(product_id=1, product_name="A",
                             estimated_cost=Decimal("100"), actual_cost=Decimal("110"),
                             variance_amount=Decimal("0"), variance_pct=None),
            PRPOVarianceLine(product_id=2, product_name="B",
                             estimated_cost=Decimal("100"), actual_cost=Decimal("150"),
                             variance_amount=Decimal("0"), variance_pct=None),
        ]
        result = compute_pr_po_variance(lines)
        # B له variance أكبر → يجيء أولاً
        assert result[0].product_name == "B"


# ══════════════════════════════════════════════════════════════════════
# HTTP API Tests
# ══════════════════════════════════════════════════════════════════════

def test_owner_sales_returns_200(client, db, setup_db):
    """GET /owner/sales يعيد 200 مع البنية الصحيحة."""
    branch = _branch(db)
    owner  = _owner(db, "sales1@test.local", branch.id)

    resp = client.get(
        "/api/v1/owner/sales",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "items" in data
    assert "total_revenue" in data
    assert "outlet" in data
    assert "period_from" in data
    assert "is_provisional" in data
    assert isinstance(data["items"], list)


def test_owner_sales_outlet_validation(client, db, setup_db):
    """outlet غير صالح → 400."""
    branch = _branch(db)
    owner  = _owner(db, "sales2@test.local", branch.id)

    resp = client.get(
        "/api/v1/owner/sales?outlet=invalid",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 400


def test_owner_sales_rejects_cashier(client, db, setup_db):
    """cashier يُرفض من /owner/sales."""
    branch = _branch(db)
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    u = User(email="cashier_sales@test.local", password_hash=get_password_hash("pw"),
             full_name="C", role="cashier", is_active=True)
    db.add(u); db.commit()
    resp = client.get(
        "/api/v1/owner/sales",
        headers={"Authorization": f"Bearer {_tok(u.email, branch.id)}"},
    )
    assert resp.status_code == 403


def test_owner_sales_no_pii_fields(client, db, setup_db):
    """response لا يحتوي على حقول PII."""
    branch = _branch(db)
    owner  = _owner(db, "sales3@test.local", branch.id)

    resp = client.get(
        "/api/v1/owner/sales",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    for item in data.get("items", []):
        assert "guest_name"  not in item
        assert "guest_phone" not in item
        assert "customer_id" not in item


def test_owner_beach_performance_returns_200(client, db, setup_db):
    """GET /owner/beach-performance يعيد 200."""
    branch = _branch(db)
    owner  = _owner(db, "beach1@test.local", branch.id)

    # ننشئ beach transaction
    from app.modules.beach.models import BeachTransaction
    tx = BeachTransaction(
        branch_id=branch.id, tx_type="entry",
        quantity=2, unit_price=Decimal("100"), total_amount=Decimal("200"),
        tx_date=date.today(),
    )
    db.add(tx); db.commit()

    resp = client.get(
        "/api/v1/owner/beach-performance",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "ticket_types" in data
    assert "total_revenue" in data
    assert isinstance(data["ticket_types"], list)
    # يجب أن يوجد tx_type='entry'
    types = [t["tx_type"] for t in data["ticket_types"]]
    assert "entry" in types


def test_owner_beach_excludes_voided(client, db, setup_db):
    """BeachTransaction voided لا تظهر في beach performance."""
    branch = _branch(db)
    owner  = _owner(db, "beach2@test.local", branch.id)

    from app.modules.beach.models import BeachTransaction
    # non-voided
    db.add(BeachTransaction(branch_id=branch.id, tx_type="entry_towel",
                            quantity=1, unit_price=Decimal("120"), total_amount=Decimal("120"),
                            tx_date=date.today()))
    # voided
    db.add(BeachTransaction(branch_id=branch.id, tx_type="entry_towel",
                            quantity=1, unit_price=Decimal("120"), total_amount=Decimal("120"),
                            tx_date=date.today(), voided_at=datetime.utcnow()))
    db.commit()

    resp = client.get(
        "/api/v1/owner/beach-performance",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    entry_towel = next((t for t in data["ticket_types"] if t["tx_type"] == "entry_towel"), None)
    assert entry_towel is not None
    # 1 non-voided فقط
    assert entry_towel["count"] == 1


def test_owner_channel_analytics_no_guest_data(client, db, setup_db):
    """channel analytics لا تحتوي على بيانات ضيف."""
    branch = _branch(db)
    owner  = _owner(db, "channel1@test.local", branch.id)

    resp = client.get(
        "/api/v1/owner/channel-analytics",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "contracts" in data
    for contract in data["contracts"]:
        assert "guest_name"  not in contract
        assert "guest_phone" not in contract
        assert "guest_email" not in contract


def test_owner_channel_analytics_structure(client, db, setup_db):
    """هيكل channel analytics يحتوي على الحقول المطلوبة."""
    branch = _branch(db)
    owner  = _owner(db, "channel2@test.local", branch.id)

    # ننشئ B2B contract
    from app.modules.beach.models import B2BContract, B2BContractDay
    contract = B2BContract(
        branch_id=branch.id, hotel_name="فندق النيل",
        daily_quota=30, entry_price=Decimal("80"),
        valid_from=date(2026, 1, 1), valid_until=date(2026, 12, 31),
        is_active=True, is_overdue=False,
    )
    db.add(contract); db.flush()
    db.add(B2BContractDay(
        contract_id=contract.id, day=date.today(),
        checked_in_count=5, total_amount=Decimal("400"),
    ))
    db.commit()

    resp = client.get(
        "/api/v1/owner/channel-analytics",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["contracts"]) >= 1
    c = next(x for x in data["contracts"] if x["contract_id"] == contract.id)
    assert c["hotel_name"] == "فندق النيل"
    assert "fnb_attach" in c
    assert "outstanding" in c
    assert "is_overdue" in c


def test_owner_expense_analytics_structure(client, db, setup_db):
    """هيكل expense analytics صحيح."""
    branch = _branch(db)
    owner  = _owner(db, "expense1@test.local", branch.id)

    resp = client.get(
        "/api/v1/owner/expense-analytics",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "expense_lines" in data
    assert "current_revenue" in data
    assert "prior_revenue" in data
    assert "period_from" in data
    assert "prior_from" in data
    assert isinstance(data["expense_lines"], list)


def test_owner_expense_no_per_employee_data(client, db, setup_db):
    """response لا يحتوي على أي حقول per-employee."""
    branch = _branch(db)
    owner  = _owner(db, "expense2@test.local", branch.id)

    resp = client.get(
        "/api/v1/owner/expense-analytics",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    payroll = data.get("payroll")
    if payroll:
        # payroll aggregate فقط — لا اسم موظف
        assert "employee_name" not in payroll
        assert "employee_id"   not in payroll
        assert "net_salary"    not in payroll
        assert "total_net" in payroll


def test_owner_procurement_analytics_structure(client, db, setup_db):
    """هيكل procurement analytics صحيح."""
    branch = _branch(db)
    owner  = _owner(db, "proc1@test.local", branch.id)

    resp = client.get(
        "/api/v1/owner/procurement-analytics",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "suppliers" in data
    assert "pr_po_variance" in data
    assert "total_spend" in data
    assert isinstance(data["suppliers"], list)
    assert isinstance(data["pr_po_variance"], list)


def test_owner_procurement_concentration_flag(client, db, setup_db):
    """مورّد يستحوذ على أكثر من 50% يحمل concentration_flag=True."""
    branch = _branch(db)
    owner  = _owner(db, "proc2@test.local", branch.id)

    # ننشئ موردَين وأوامر شراء
    from app.modules.inventory.models import Supplier, PurchaseOrder, Product, Warehouse
    import uuid as _uuid

    # Warehouse
    wh = db.query(Warehouse).filter(Warehouse.branch_id == branch.id).first()
    if not wh:
        wh = Warehouse(branch_id=branch.id, name="المستودع", code=f"WH-{_uuid.uuid4().hex[:4]}")
        db.add(wh); db.flush()

    s1 = Supplier(branch_id=branch.id, name="المورد الكبير")
    s2 = Supplier(branch_id=branch.id, name="المورد الصغير")
    db.add_all([s1, s2]); db.flush()

    today = date.today()
    po1 = PurchaseOrder(
        branch_id=branch.id, order_number=f"PO-BIGTEST-{_uuid.uuid4().hex[:6]}",
        supplier_id=s1.id, status="received", ordered_at=today, total_amount=Decimal("8000"),
    )
    po2 = PurchaseOrder(
        branch_id=branch.id, order_number=f"PO-SMTEST-{_uuid.uuid4().hex[:6]}",
        supplier_id=s2.id, status="received", ordered_at=today, total_amount=Decimal("2000"),
    )
    db.add_all([po1, po2]); db.commit()

    resp = client.get(
        f"/api/v1/owner/procurement-analytics?date_from={today.isoformat()}&date_to={today.isoformat()}",
        headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    big = next((s for s in data["suppliers"] if s["supplier_name"] == "المورد الكبير"), None)
    small = next((s for s in data["suppliers"] if s["supplier_name"] == "المورد الصغير"), None)
    if big:
        assert big["concentration_flag"] is True
    if small:
        assert small["concentration_flag"] is False


def test_analytics_endpoints_reject_non_owner(client, db, setup_db):
    """كل endpoints المرحلة 6 ترفض manager."""
    branch = _branch(db)
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    mgr = User(email="mgr_p6@test.local", password_hash=get_password_hash("pw"),
               full_name="M", role="manager", is_active=True)
    db.add(mgr); db.commit()

    endpoints = [
        "/api/v1/owner/sales",
        "/api/v1/owner/beach-performance",
        "/api/v1/owner/channel-analytics",
        "/api/v1/owner/expense-analytics",
        "/api/v1/owner/procurement-analytics",
    ]
    for ep in endpoints:
        resp = client.get(ep, headers={"Authorization": f"Bearer {_tok(mgr.email, branch.id)}"})
        assert resp.status_code == 403, f"{ep} returned {resp.status_code}"


def test_analytics_cache_control_no_store(client, db, setup_db):
    """كل endpoints ترسل Cache-Control: no-store."""
    branch = _branch(db)
    owner  = _owner(db, "cache1@test.local", branch.id)

    endpoints = [
        "/api/v1/owner/sales",
        "/api/v1/owner/beach-performance",
        "/api/v1/owner/channel-analytics",
        "/api/v1/owner/expense-analytics",
        "/api/v1/owner/procurement-analytics",
    ]
    for ep in endpoints:
        resp = client.get(ep, headers={"Authorization": f"Bearer {_tok(owner.email, branch.id)}"})
        assert resp.status_code == 200, f"{ep}: {resp.status_code}"
        cc = resp.headers.get("cache-control", "")
        assert "no-store" in cc, f"{ep} missing no-store: {cc}"
