"""tests/test_modules/test_seed_beach_locations.py

Regression test for the same class of "model exists, zero rows out of the
box" gap already fixed for rooms/dining_tables/b2b_contracts: beach_locations
was a brand-new table with no seed data at all, so the new live beach map
screen (/pos/beach-map) would open completely empty on first run. Verifies
_seed_beach_locations creates a realistic illustrative set (umbrellas +
pergolas) with a couple of them actually checked in (real transactions via
services.checkin_location, not just rows inserted directly) so the screen is
demoable immediately.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.kernel.models.user import User
from app.core.kernel.security import get_password_hash
from app.modules.beach.models import BeachLocation, BeachTransaction
from app.modules.core.models import Branch
from app.seed import _seed_beach_locations


def _make_branch(db: Session) -> Branch:
    """فرع مخصّص للتست ده بس — نفس نمط test_seed_dining_tables.py (مش
    الاعتماد على 'أول فرع في الداتابيز')."""
    b = Branch(name="Seed Beach Locations Branch", name_ar="فرع اختبار",
               code=f"SEED-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def _make_cashier(db: Session) -> User:
    """_seed_beach_locations بيدوّر على cashier@resortos.local عشان يستخدمه
    كـ cashier_id للتشيك-إن التوضيحي — مش شرط للنجاح (cashier_id nullable)
    بس بيغطي المسار الحقيقي المتوقع في seed_all(). idempotent عشان الـ
    users table مش معزولة بالفرع (unique على email عبر كل الـ session)،
    وده الـ commit بتاع services.checkin_location بيفضل موجود بين تستات
    الملف ده (rollback في `db` fixture مبيرجعش commits سابقة فعليًا)."""
    existing = db.query(User).filter(User.email == "cashier@resortos.local").first()
    if existing:
        return existing
    u = User(
        email="cashier@resortos.local", password_hash=get_password_hash("x"),
        full_name="كاشير تجريبي", role="cashier", is_active=True,
    )
    db.add(u)
    db.commit()
    return u


def test_seed_beach_locations_creates_umbrellas_and_pergolas_with_demo_checkins(db: Session):
    branch = _make_branch(db)
    _make_cashier(db)

    _seed_beach_locations(db, branch_id=branch.id)
    db.commit()

    locations = db.query(BeachLocation).filter(BeachLocation.branch_id == branch.id).all()
    umbrellas = [loc for loc in locations if loc.location_type == "umbrella"]
    pergolas = [loc for loc in locations if loc.location_type == "pergola"]

    assert len(umbrellas) == 12
    assert len(pergolas) == 6

    occupied = [loc for loc in locations if loc.status == "occupied"]
    available = [loc for loc in locations if loc.status == "available"]
    assert len(occupied) == 2
    assert len(available) == len(locations) - 2

    # كل موقع مشغول لازم يكون مربوط بعملية بيع حقيقية، مش تعليم status بس
    for loc in occupied:
        assert loc.current_transaction_id is not None
        tx = db.query(BeachTransaction).filter(BeachTransaction.id == loc.current_transaction_id).first()
        assert tx is not None
        assert tx.location_id == loc.id
        assert tx.total_amount > 0


def test_seed_beach_locations_is_idempotent(db: Session):
    branch = _make_branch(db)
    _make_cashier(db)

    _seed_beach_locations(db, branch_id=branch.id)
    _seed_beach_locations(db, branch_id=branch.id)  # second call must be a pure no-op (guard is "any row exists")
    db.commit()

    assert db.query(BeachLocation).filter(BeachLocation.branch_id == branch.id).count() == 18
