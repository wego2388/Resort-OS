"""tests/test_modules/test_seed_dining_tables.py

Regression test for a real bug found during live acceptance testing of the
restaurant/cafe POS flow (2026-07-05): `dining_tables` and `cafe_tables` were
never seeded at all (0 rows), so a waiter opening the "Tables" screen always
saw an empty state ("لا توجد طاولات مسجّلة لهذا الفرع") and could never place
a real dine_in order tied to an actual table — the exact same class of bug as
the previously-empty `rooms` table (PMS).
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.modules.cafe.models import CafeTable
from app.modules.core.models import Branch
from app.modules.restaurant.models import DiningTable
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


def test_seed_dining_tables_creates_restaurant_and_cafe_tables(db: Session):
    branch = _make_branch(db)
    _seed_dining_tables(db, branch_id=branch.id)
    db.commit()

    restaurant_tables = db.query(DiningTable).filter(DiningTable.branch_id == branch.id).all()
    cafe_tables = db.query(CafeTable).filter(CafeTable.branch_id == branch.id).all()

    assert len(restaurant_tables) == 12
    assert len(cafe_tables) == 8
    # every seeded table must start "available" so a waiter can actually pick it
    assert all(t.status == "available" for t in restaurant_tables)
    assert all(t.status == "available" for t in cafe_tables)


def test_seed_dining_tables_is_idempotent(db: Session):
    branch = _make_branch(db)
    _seed_dining_tables(db, branch_id=branch.id)
    _seed_dining_tables(db, branch_id=branch.id)  # running twice must not duplicate rows
    db.commit()

    assert db.query(DiningTable).filter(DiningTable.branch_id == branch.id).count() == 12
    assert db.query(CafeTable).filter(CafeTable.branch_id == branch.id).count() == 8
