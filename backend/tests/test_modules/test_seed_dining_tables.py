"""tests/test_modules/test_seed_dining_tables.py

Regression test for a real bug found during live acceptance testing of the
restaurant/cafe POS flow (2026-07-05): `dining_tables` and `cafe_tables` were
never seeded at all (0 rows), so a waiter opening the "Tables" screen always
saw an empty state ("لا توجد طاولات مسجّلة لهذا الفرع") and could never place
a real dine_in order tied to an actual table — the exact same class of bug as
the previously-empty `rooms` table (PMS).

راجع DINING_CUTOVER_PLAN.md Batch 6 — _seed_dining_tables بقى بيزرع
dining.models.VenueTable بدل restaurant.DiningTable/cafe.CafeTable القديمين
اللي اتحذفوا.

2026-07-21: الطاولة بقت مشتركة بين كل منافذ الفرع (مش outlet_id خاص بيها
بعد كده) — راجع migration 9b4e1a2c7f30 و VenueTable's docstring. الدالة
بقت بتزرع مجموعة واحدة بس (12 طاولة) بدل مجموعتين مكررتين.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.modules.core.models import Branch
from app.modules.dining.models import VenueTable
from app.seed import _seed_dining_tables


def _make_branch(db: Session) -> Branch:
    """فرع مخصّص للتست ده بس — مش `_seed_branch` (اللي بيعتمد على 'أول فرع في
    الداتابيز' وده مش مضمون يكون معزول لما تستات تانية HTTP بتعمل commit
    حقيقي لفروع تانية في نفس الـ session-scoped SQLite)."""
    b = Branch(name="Seed Test Branch", name_ar="فرع اختبار",
               code=f"SEED-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def _tables_for(db: Session, branch_id: int) -> list[VenueTable]:
    return db.query(VenueTable).filter(VenueTable.branch_id == branch_id).all()


def test_seed_dining_tables_creates_one_shared_set(db: Session):
    branch = _make_branch(db)
    _seed_dining_tables(db, branch_id=branch.id)
    db.commit()

    tables = _tables_for(db, branch.id)

    assert len(tables) == 12
    # every seeded table must start "available" so a waiter can actually pick it
    assert all(t.status == "available" for t in tables)
    # numbers must be unique per branch (shared across outlets, not duplicated)
    assert len({t.table_number for t in tables}) == 12


def test_seed_dining_tables_is_idempotent(db: Session):
    branch = _make_branch(db)
    _seed_dining_tables(db, branch_id=branch.id)
    _seed_dining_tables(db, branch_id=branch.id)  # running twice must not duplicate rows
    db.commit()

    assert len(_tables_for(db, branch.id)) == 12
