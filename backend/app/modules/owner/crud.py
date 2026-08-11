"""
app/modules/owner/crud.py
═══════════════════════════════════════════════════════════════════════
Owner Intelligence Cockpit — CRUD (Decision 0004, Phase 2).

قاعدة: DB operations فقط — لا HTTPException، لا business logic.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.modules.owner.models import OwnerAllocationRule, OwnerWatchlist
from app.modules.owner.schemas import (
    AllocationRuleDraftCreate,
    AllocationRuleDraftUpdate,
    OwnerWatchlistCreate,
)


# ── OwnerWatchlist ────────────────────────────────────────────────────

def list_watchlist(db: Session, owner_user_id: int, branch_id: int) -> list[OwnerWatchlist]:
    return (
        db.query(OwnerWatchlist)
        .filter(
            OwnerWatchlist.owner_user_id == owner_user_id,
            OwnerWatchlist.branch_id == branch_id,
        )
        .order_by(OwnerWatchlist.display_order)
        .all()
    )


def get_watchlist_item(
    db: Session, item_id: int, owner_user_id: int, branch_id: int,
) -> Optional[OwnerWatchlist]:
    # ⚠️ 2026-08-11: كان بيتحقق من owner_user_id بس، من غير branch_id —
    # نفس فئة الباج بتاعة allocation rules (IDOR عبر id بس).
    return (
        db.query(OwnerWatchlist)
        .filter(
            OwnerWatchlist.id == item_id,
            OwnerWatchlist.owner_user_id == owner_user_id,
            OwnerWatchlist.branch_id == branch_id,
        )
        .first()
    )


def create_watchlist_item(db: Session, data: OwnerWatchlistCreate, owner_user_id: int) -> OwnerWatchlist:
    item = OwnerWatchlist(
        owner_user_id=owner_user_id,
        metric_key=data.metric_key,
        display_order=data.display_order,
        label_override=data.label_override,
        branch_id=data.branch_id,
    )
    db.add(item)
    db.flush()
    return item


def delete_watchlist_item(db: Session, item: OwnerWatchlist) -> None:
    db.delete(item)
    db.flush()


# ── OwnerAllocationRule ───────────────────────────────────────────────

def list_allocation_rules(
    db: Session, branch_id: int, status: Optional[str] = None,
) -> list[OwnerAllocationRule]:
    q = db.query(OwnerAllocationRule).filter(OwnerAllocationRule.branch_id == branch_id)
    if status:
        q = q.filter(OwnerAllocationRule.status == status)
    return q.order_by(OwnerAllocationRule.id.desc()).all()


def get_allocation_rule(db: Session, rule_id: int) -> Optional[OwnerAllocationRule]:
    return db.query(OwnerAllocationRule).filter(OwnerAllocationRule.id == rule_id).first()


def create_allocation_rule_draft(
    db: Session, data: AllocationRuleDraftCreate, created_by: int,
) -> OwnerAllocationRule:
    # version: أعلى version موجود + 1 لنفس الفرع.
    # ⚠️ 2026-08-11: MAX(version)+1 من غير أي قفل كان عنده سباق حقيقي —
    # طلبين متزامنين لنفس الفرع يقدروا يقروا نفس الـMAX ويحسبوا نفس
    # next_version. نفس نمط SELECT FOR UPDATE المُتّبع في المشروع كله
    # (راجع CLAUDE.md §13 بند ⓫) — بنقفل صفوف الفرع ده الموجودة فعليًا
    # قبل حساب الـmax، فأي معاملة تانية بتحاول تعمل نفس الحاجة لازم
    # تستنى لحد ما المعاملة دي تعمل commit/rollback. الـunique constraint
    # (migration 90f2a4c81b3e) هو خط الدفاع الثاني لو حالة أول مسودة لفرع
    # (مفيش صفوف تتقفل أصلاً) حصل فيها سباق برضو.
    from sqlalchemy import func as sa_func  # noqa: PLC0415
    db.query(OwnerAllocationRule.id).filter(
        OwnerAllocationRule.branch_id == data.branch_id,
    ).with_for_update().all()
    max_version_row = (
        db.query(sa_func.max(OwnerAllocationRule.version))
        .filter(OwnerAllocationRule.branch_id == data.branch_id)
        .scalar()
    )
    next_version = (max_version_row or 0) + 1
    rule = OwnerAllocationRule(
        branch_id=data.branch_id,
        version=next_version,
        status="draft",
        pct_rooms=data.pct_rooms,
        pct_beach=data.pct_beach,
        pct_dining=data.pct_dining,
        pct_timeshare=data.pct_timeshare,
        notes=data.notes,
        created_by=created_by,
    )
    db.add(rule)
    db.flush()
    return rule


def update_allocation_rule_draft(
    db: Session, rule: OwnerAllocationRule, data: AllocationRuleDraftUpdate,
) -> OwnerAllocationRule:
    if data.pct_rooms is not None:
        rule.pct_rooms = data.pct_rooms
    if data.pct_beach is not None:
        rule.pct_beach = data.pct_beach
    if data.pct_dining is not None:
        rule.pct_dining = data.pct_dining
    if data.pct_timeshare is not None:
        rule.pct_timeshare = data.pct_timeshare
    if data.notes is not None:
        rule.notes = data.notes
    db.flush()
    return rule


def delete_allocation_rule_draft(db: Session, rule: OwnerAllocationRule) -> None:
    db.delete(rule)
    db.flush()
