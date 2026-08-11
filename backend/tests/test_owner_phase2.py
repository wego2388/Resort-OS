"""
tests/test_owner_phase2.py
═══════════════════════════════════════════════════════════════════════
Owner Intelligence Cockpit — Phase 2 Tests (Decision 0004).
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from jose import jwt


def _tok(email: str, branch_id: int = 1) -> str:
    """JWT token مطابق لـ _make_token في conftest.

    ``bid`` إجباري هنا فعليًا — owner endpoints بترفض بـ400 من غير فرع
    نشط في الجلسة (راجع router.py's _get_branch: watchlist GET/POST كانت
    قبل كده بتاخد branch_id كـquery param مباشر من العميل، باج أمني حقيقي
    اتصلح — كل endpoint تاني في الموديول ده أصلاً بيشتق branch_id من هنا)."""
    secret = os.environ["SECRET_KEY"]
    now = datetime.utcnow()
    return jwt.encode(
        {"sub": email, "iat": now, "exp": now + timedelta(hours=1), "bid": branch_id},
        secret,
        algorithm="HS256",
    )


def _owner(db, email: str = "owner_ph2@test.local", branch_id: int = 1):
    """ينشئ owner user ويعيده — مع عضوية فرع نشطة (نفس نمط test_owner_
    phase10.py's _owner). لازم فعليًا: get_current_user's branch resolution
    بيرفض أي bid في التوكن مالوش UserBranchMembership حقيقية مطابقة —
    مجرد claim في التوكن مش كافي (باج حقيقي اتصلح هنا: التست القديم كان
    شغال بالصدفة بس لأن /owner/watchlist كان قبل كده بياخد branch_id من
    query param مباشر، مش من الجلسة زي كل endpoint owner تاني)."""
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    from app.modules.core.models import Branch, UserBranchMembership
    if not db.get(Branch, branch_id):
        db.add(Branch(
            id=branch_id, name="Owner Test Branch", name_ar="فرع اختباري",
            code=f"OWN-PH2-{branch_id}", gm_phone="+201000000000",
        ))
        db.flush()
    u = User(
        email=email,
        password_hash=get_password_hash("pw"),
        full_name="Owner Test",
        role="owner",
        is_active=True,
        two_factor_enabled=True,
    )
    db.add(u)
    db.flush()
    db.add(UserBranchMembership(user_id=u.id, branch_id=branch_id, is_active=True))
    db.commit()
    db.refresh(u)
    return u


# ── 1. Role & 2FA metadata ─────────────────────────────────────────────

def test_owner_role_in_role_levels():
    from app.core.deps import ROLE_LEVELS
    assert ROLE_LEVELS["owner"] == 10
    assert ROLE_LEVELS["owner"] < ROLE_LEVELS["employee"]


def test_owner_in_mandatory_2fa():
    from app.core.deps import MANDATORY_2FA_ROLES
    assert "owner" in MANDATORY_2FA_ROLES


def test_owner_level_below_all_operational_roles():
    from app.core.deps import ROLE_LEVELS
    lvl = ROLE_LEVELS["owner"]
    skip = {"customer", "guest", "owner"}
    for role, rl in ROLE_LEVELS.items():
        if role not in skip:
            assert lvl < rl, f"owner({lvl}) should be < {role}({rl})"


# ── 2. get_owner_reader dependency ────────────────────────────────────

def test_get_owner_reader_accepts_owner(client, db, setup_db):
    u = _owner(db)
    resp = client.get("/api/v1/owner/watchlist?branch_id=1",
                      headers={"Authorization": f"Bearer {_tok(u.email)}"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_owner_reader_rejects_cashier(client, db, setup_db):
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    u = User(email="cashier_ph2@test.local", password_hash=get_password_hash("pw"),
             full_name="Cashier", role="cashier", is_active=True)
    db.add(u); db.commit()
    resp = client.get("/api/v1/owner/watchlist?branch_id=1",
                      headers={"Authorization": f"Bearer {_tok(u.email)}"})
    assert resp.status_code == 403
    assert "المالك" in resp.json().get("detail", "")


def test_get_owner_reader_rejects_manager(client, db, setup_db):
    """Manager (level 60) must also be rejected — not just cashier."""
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    u = User(email="mgr_ph2@test.local", password_hash=get_password_hash("pw"),
             full_name="Manager", role="manager", is_active=True)
    db.add(u); db.commit()
    resp = client.get("/api/v1/owner/watchlist?branch_id=1",
                      headers={"Authorization": f"Bearer {_tok(u.email)}"})
    assert resp.status_code == 403


# ── 3. Central write-block — fail-closed ──────────────────────────────

def test_owner_write_block_non_allowlisted_route(client, db, setup_db):
    """POST /crm/customers is not in OWNER_WRITE_ALLOWLIST → must be blocked.

    ⚠️ 2026-08-11: the payload here used to be `{"name": ..., "branch_id": ...}`
    which is NOT a valid CustomerCreate (the real required field is
    `full_name`) — the request failed Pydantic validation with 422 before
    ever reaching the policy layer, and the assertion accepted 422 as a
    pass. That made this test green even while
    enforce_owner_access_policy had zero call sites anywhere in the app
    (confirmed live: a genuinely valid payload succeeded and created a
    real customer). Fixed: a real valid payload, and only 403 passes.
    """
    from app.modules.owner.owner_policy import OWNER_WRITE_ALLOWLIST
    assert "create_customer" not in OWNER_WRITE_ALLOWLIST  # sanity

    u = _owner(db, "owner_block@test.local")
    resp = client.post(
        "/api/v1/crm/customers",
        json={"branch_id": 1, "full_name": "Should Be Blocked"},
        headers={"Authorization": f"Bearer {_tok(u.email)}"},
    )
    # owner (level=10) passes get_current_active_user,
    # but enforce_owner_access_policy blocks the write → 403, never 422
    # (the request itself is valid) and never 201 (the real vulnerability).
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "OWNER_WRITE_BLOCKED"


def test_owner_allowlist_does_not_contain_activate(setup_db):
    """activate_owner_allocation_rule must never appear in the allowlist."""
    from app.modules.owner.owner_policy import OWNER_WRITE_ALLOWLIST
    assert "activate_owner_allocation_rule" not in OWNER_WRITE_ALLOWLIST


# ── 4. OwnerWatchlist CRUD ────────────────────────────────────────────

def test_owner_watchlist_crud(db, setup_db):
    from app.modules.owner import services as svc
    from app.modules.owner.schemas import OwnerWatchlistCreate

    data = OwnerWatchlistCreate(metric_key="revenue_today", display_order=1,
                                 label_override="إيراد اليوم", branch_id=1)
    item = svc.add_watchlist_item(db, data, owner_user_id=999)
    assert item.id is not None
    assert item.metric_key == "revenue_today"

    items = svc.get_watchlist(db, owner_user_id=999, branch_id=1)
    assert len(items) == 1

    with pytest.raises(ValueError, match="موجود بالفعل"):
        svc.add_watchlist_item(db, data, owner_user_id=999)

    svc.remove_watchlist_item(db, item.id, owner_user_id=999, branch_id=1)
    assert svc.get_watchlist(db, owner_user_id=999, branch_id=1) == []


def test_owner_watchlist_delete_checks_branch(db, setup_db):
    """حذف عنصر watchlist من فرع تاني (حتى لو نفس owner_user_id) لازم
    يترفض — نفس فئة IDOR بتاعة allocation rules، اتصلحت هنا كمان
    2026-08-11 (get_watchlist_item كان بيتحقق من owner_user_id بس)."""
    from app.modules.owner import services as svc
    from app.modules.owner.schemas import OwnerWatchlistCreate

    item = svc.add_watchlist_item(
        db, OwnerWatchlistCreate(metric_key="revenue_today", branch_id=1),
        owner_user_id=999,
    )
    with pytest.raises(ValueError, match="غير موجود"):
        svc.remove_watchlist_item(db, item.id, owner_user_id=999, branch_id=2)
    # لسه موجود — الحذف اللي اترفض ماأثرش على الصف الحقيقي
    assert len(svc.get_watchlist(db, owner_user_id=999, branch_id=1)) == 1


# ── 5. OwnerAllocationRule draft CRUD ─────────────────────────────────

def test_owner_allocation_rule_draft_crud(db, setup_db):
    from app.modules.owner import services as svc
    from app.modules.owner.schemas import AllocationRuleDraftCreate, AllocationRuleDraftUpdate

    rule = svc.create_draft(db, AllocationRuleDraftCreate(
        branch_id=1, pct_rooms=Decimal("40"), pct_beach=Decimal("30"),
        pct_dining=Decimal("20"), pct_timeshare=Decimal("10"), notes="تجربة",
    ), owner_user_id=999)
    assert rule.status == "draft"
    assert rule.pct_rooms == Decimal("40")

    # 35+30+20+10=95 — لسه صالح بعد الدمج مع القيم الموجودة (راجع
    # test_allocation_rule_patch_rejects_total_over_100 للسيناريو العكسي).
    updated = svc.update_draft(db, rule.id,
                               AllocationRuleDraftUpdate(pct_rooms=Decimal("35")),
                               owner_user_id=999, branch_id=1)
    assert updated.pct_rooms == Decimal("35")

    svc.delete_draft(db, rule.id, owner_user_id=999, branch_id=1)
    assert all(r.id != rule.id
               for r in svc.list_allocation_rules(db, branch_id=1))


def test_allocation_rule_patch_rejects_total_over_100(db, setup_db):
    """⚠️ 2026-08-11: باج حقيقي كان هنا — PATCH جزئي كان بيتحقق بس من
    الحقول المُرسلة في نفس الطلب، مش من المجموع النهائي المدموج مع
    القيم الموجودة. rooms=40+beach=30+dining=20+timeshare=10=100 (صالح
    عند الإنشاء)، وبعدين PATCH يرفع rooms لـ45 لوحده كان بينجح من غير
    أي رفض رغم إن المجموع الحقيقي بقى 105% — الاختبار ده بيثبت الرفض
    دلوقتي فعليًا."""
    from app.modules.owner import services as svc
    from app.modules.owner.schemas import AllocationRuleDraftCreate, AllocationRuleDraftUpdate

    rule = svc.create_draft(db, AllocationRuleDraftCreate(
        branch_id=1, pct_rooms=Decimal("40"), pct_beach=Decimal("30"),
        pct_dining=Decimal("20"), pct_timeshare=Decimal("10"),
    ), owner_user_id=999)

    with pytest.raises(ValueError, match="100%"):
        svc.update_draft(db, rule.id,
                         AllocationRuleDraftUpdate(pct_rooms=Decimal("45")),
                         owner_user_id=999, branch_id=1)

    # القاعدة لازم تفضل زي ما هي — الرفض مايسّبش partial write
    from app.modules.owner import crud
    unchanged = crud.get_allocation_rule(db, rule.id)
    assert unchanged.pct_rooms == Decimal("40")


def test_allocation_rule_update_delete_checks_branch(db, setup_db):
    """PATCH/DELETE على مسودة فرع تاني لازم يترفض — نفس فئة IDOR بتاعة
    2026-08-11 (كانت get_allocation_rule بتتحقق من rule_id بس)."""
    from app.modules.owner import services as svc
    from app.modules.owner.schemas import AllocationRuleDraftCreate, AllocationRuleDraftUpdate

    rule = svc.create_draft(
        db, AllocationRuleDraftCreate(branch_id=1, pct_rooms=Decimal("40")),
        owner_user_id=999,
    )
    with pytest.raises(ValueError, match="غير موجودة"):
        svc.update_draft(db, rule.id, AllocationRuleDraftUpdate(pct_rooms=Decimal("10")),
                         owner_user_id=999, branch_id=2)
    with pytest.raises(ValueError, match="غير موجودة"):
        svc.delete_draft(db, rule.id, owner_user_id=999, branch_id=2)
    # لسه موجودة وبنفس القيمة — محاولات فرع تاني ماأثّرتش عليها
    from app.modules.owner import crud
    unchanged = crud.get_allocation_rule(db, rule.id)
    assert unchanged is not None and unchanged.pct_rooms == Decimal("40")


def test_allocation_rule_total_validation():
    from app.modules.owner.schemas import AllocationRuleDraftCreate
    with pytest.raises(Exception, match="100%"):
        AllocationRuleDraftCreate(
            branch_id=1, pct_rooms=Decimal("50"), pct_beach=Decimal("40"),
            pct_dining=Decimal("30"), pct_timeshare=Decimal("0"),
        )


def test_published_rule_immutable(db, setup_db):
    from app.modules.owner import services as svc
    from app.modules.owner.schemas import AllocationRuleDraftCreate, AllocationRuleDraftUpdate

    rule = svc.create_draft(db, AllocationRuleDraftCreate(
        branch_id=1, pct_rooms=Decimal("50")), owner_user_id=999)
    rule.status = "published"
    db.commit()

    with pytest.raises(ValueError, match="منشورة"):
        svc.update_draft(db, rule.id,
                         AllocationRuleDraftUpdate(pct_rooms=Decimal("60")),
                         owner_user_id=999, branch_id=1)


# ── 6. E-2 fix: source_request_id stored on PO ────────────────────────

def test_pr_to_po_stores_source_request_id(db, setup_db, sample_branch):
    from app.modules.inventory import services as inv_svc, crud as inv_crud
    from app.modules.inventory.schemas import (
        SupplierCreate, PurchaseRequestCreate,
        PurchaseRequestItemCreate, ProductCreate,
    )

    product = inv_crud.create_product(db, ProductCreate(
        branch_id=sample_branch.id, name="E2 Product",
        sku="E2-TST-001", category="test", unit="kg",
    ))
    db.commit()

    supplier = inv_crud.create_supplier(
        db, SupplierCreate(branch_id=sample_branch.id, name="E2 Supplier"))
    db.commit()

    pr = inv_svc.create_purchase_request(db, PurchaseRequestCreate(
        branch_id=sample_branch.id,
        requester_id=1,
        department="kitchen",
        items=[PurchaseRequestItemCreate(
            product_id=product.id, quantity_requested=Decimal("10"),
            unit="kg", estimated_unit_cost=Decimal("50"),
        )],
    ))

    inv_svc.approve_purchase_request(db, pr.id, approver_id=1, level="dept")
    inv_svc.approve_purchase_request(db, pr.id, approver_id=1, level="finance")
    po = inv_svc.convert_to_purchase_order(db, pr.id, supplier.id)

    db.refresh(po)
    assert po.source_request_id == pr.id
