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


def _tok(email: str) -> str:
    """JWT token مطابق لـ _make_token في conftest."""
    secret = os.environ["SECRET_KEY"]
    now = datetime.utcnow()
    return jwt.encode(
        {"sub": email, "iat": now, "exp": now + timedelta(hours=1)},
        secret,
        algorithm="HS256",
    )


def _owner(db, email: str = "owner_ph2@test.local"):
    """ينشئ owner user ويعيده."""
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    u = User(
        email=email,
        password_hash=get_password_hash("pw"),
        full_name="Owner Test",
        role="owner",
        is_active=True,
        two_factor_enabled=True,
    )
    db.add(u)
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
    """POST /crm/customers is not in OWNER_WRITE_ALLOWLIST → must be blocked."""
    from app.modules.owner.owner_policy import OWNER_WRITE_ALLOWLIST
    assert "create_customer" not in OWNER_WRITE_ALLOWLIST  # sanity

    u = _owner(db, "owner_block@test.local")
    resp = client.post(
        "/api/v1/crm/customers",
        json={"name": "Test", "branch_id": 1},
        headers={"Authorization": f"Bearer {_tok(u.email)}"},
    )
    # owner (level=10) passes get_current_active_user,
    # but enforce_owner_write_policy blocks the write → 403
    assert resp.status_code in (403, 422)


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

    svc.remove_watchlist_item(db, item.id, owner_user_id=999)
    assert svc.get_watchlist(db, owner_user_id=999, branch_id=1) == []


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

    updated = svc.update_draft(db, rule.id,
                               AllocationRuleDraftUpdate(pct_rooms=Decimal("45")),
                               owner_user_id=999)
    assert updated.pct_rooms == Decimal("45")

    svc.delete_draft(db, rule.id, owner_user_id=999)
    assert all(r.id != rule.id
               for r in svc.list_allocation_rules(db, branch_id=1))


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
                         owner_user_id=999)


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
