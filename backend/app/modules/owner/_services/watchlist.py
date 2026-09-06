"""
app/modules/owner/_services/watchlist.py
Extracted from app/modules/owner/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from decimal import Decimal
from sqlalchemy.orm import Session
from app.modules.owner import crud
from app.modules.owner.models import OwnerAllocationRule, OwnerWatchlist
from app.modules.owner.schemas import (
    AllocationRuleDraftCreate,
    AllocationRuleDraftUpdate,
    OwnerWatchlistCreate,
)


# Phase 2 — OwnerWatchlist
# ══════════════════════════════════════════════════════════════════════

def get_watchlist(db: Session, owner_user_id: int, branch_id: int) -> list[OwnerWatchlist]:
    return crud.list_watchlist(db, owner_user_id, branch_id)


def add_watchlist_item(
    db: Session, data: OwnerWatchlistCreate, owner_user_id: int,
) -> OwnerWatchlist:
    """يضيف metric للـ watchlist — يرفض التكرار."""
    existing = (
        db.query(OwnerWatchlist)
        .filter(
            OwnerWatchlist.owner_user_id == owner_user_id,
            OwnerWatchlist.metric_key == data.metric_key,
            OwnerWatchlist.branch_id == data.branch_id,
        )
        .first()
    )
    if existing:
        raise ValueError(f"المقياس '{data.metric_key}' موجود بالفعل في قائمة المراقبة")

    item = crud.create_watchlist_item(db, data, owner_user_id)
    db.commit()
    db.refresh(item)
    return item


def remove_watchlist_item(db: Session, item_id: int, owner_user_id: int, branch_id: int) -> None:
    item = crud.get_watchlist_item(db, item_id, owner_user_id, branch_id)
    if not item:
        raise ValueError(f"العنصر {item_id} غير موجود أو لا تملك صلاحية حذفه")
    crud.delete_watchlist_item(db, item)
    db.commit()


# ══════════════════════════════════════════════════════════════════════
# Phase 2 — OwnerAllocationRule
# ══════════════════════════════════════════════════════════════════════

def list_allocation_rules(db: Session, branch_id: int) -> list[OwnerAllocationRule]:
    return crud.list_allocation_rules(db, branch_id)


def create_draft(
    db: Session, data: AllocationRuleDraftCreate, owner_user_id: int,
) -> OwnerAllocationRule:
    rule = crud.create_allocation_rule_draft(db, data, created_by=owner_user_id)
    db.commit()
    db.refresh(rule)
    return rule


def update_draft(
    db: Session, rule_id: int, data: AllocationRuleDraftUpdate, owner_user_id: int,
    branch_id: int,
) -> OwnerAllocationRule:
    rule = crud.get_allocation_rule(db, rule_id)
    # ⚠️ 2026-08-11: نفس رسالة "غير موجودة" لقاعدة موجودة فعليًا بس في فرع
    # تاني — عمدًا، عشان مانسربش حتى وجود الـid ده لفرع owner مالوش وصول
    # له (نفس منطق 404-not-403 المعتاد في IDOR-sensitive lookups).
    if not rule or rule.branch_id != branch_id:
        raise ValueError(f"قاعدة التخصيص {rule_id} غير موجودة")
    if rule.status != "draft":
        raise ValueError("لا يمكن تعديل قاعدة منشورة — أنشئ مسودة جديدة")

    # ⚠️ 2026-08-11: التحقق القديم (AllocationRuleDraftCreate's field_validator)
    # كان بيشتغل بس وقت الإنشاء — PATCH جزئي (زي pct_rooms=45 لوحده) كان
    # بيتقبل من غير أي تحقق من المجموع النهائي الحقيقي (القديم + الجديد)،
    # يعني ممكن يتخطى 100% بسهولة (تست test_owner_allocation_rule_draft_crud
    # كان بيثبت السيناريو ده فعليًا: 45+30+20+10=105% كان بينجح). التحقق
    # هنا لازم يحسب المجموع النهائي المدموج، مش بس الحقول المُرسلة في نفس
    # الطلب.
    final_rooms = data.pct_rooms if data.pct_rooms is not None else rule.pct_rooms
    final_beach = data.pct_beach if data.pct_beach is not None else rule.pct_beach
    final_dining = data.pct_dining if data.pct_dining is not None else rule.pct_dining
    final_timeshare = data.pct_timeshare if data.pct_timeshare is not None else rule.pct_timeshare
    if final_rooms + final_beach + final_dining + final_timeshare > Decimal("100"):
        raise ValueError("مجموع نسب التخصيص يتجاوز 100%")

    rule = crud.update_allocation_rule_draft(db, rule, data)
    db.commit()
    db.refresh(rule)
    return rule


def delete_draft(db: Session, rule_id: int, owner_user_id: int, branch_id: int) -> None:
    rule = crud.get_allocation_rule(db, rule_id)
    if not rule or rule.branch_id != branch_id:
        raise ValueError(f"قاعدة التخصيص {rule_id} غير موجودة")
    if rule.status != "draft":
        raise ValueError("لا يمكن حذف قاعدة منشورة")
    crud.delete_allocation_rule_draft(db, rule)
    db.commit()
