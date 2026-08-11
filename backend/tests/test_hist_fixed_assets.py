"""tests/test_hist_fixed_assets.py — HIST-01 Fixed Assets/Depreciation
generator (OPS-DATA-02 §10.7).

⚠️ Asset.code فريد عالميًا (نفس منطق منتجع واحد — راجع test_hist_hr.py's
docstring) فالمولّد بيستخدم أكواد ثابتة (HIST-FA-01..13). عشان كده
الاختبارات هنا بتشغّل المولّد **مرة واحدة بس** عبر فيكستشر class-scoped."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.hist_fixed_assets import generate as generate_fixed_assets
from tests.conftest import TestingSessionLocal


class _Ctx:
    def __init__(self, branch_id: int):
        self.branch_id = branch_id
        self.period_year = 2026
        self.period_month = 7
        self.tz_name = "Africa/Cairo"
        self.actor_id = 1


@pytest.fixture(scope="class")
def branch_id(setup_db) -> int:
    from app.modules.core.models import Branch

    db = TestingSessionLocal()
    try:
        b = Branch(name="Test Fixed Assets HIST", name_ar="اختبار أصول ثابتة تاريخية",
                   code=f"HFA-{uuid.uuid4().hex[:6].upper()}")
        db.add(b)
        db.commit()
        generate_fixed_assets(db, _Ctx(b.id))
        db.commit()
        return b.id
    finally:
        db.close()


class TestHistFixedAssetsGenerator:
    def test_creates_thirteen_assets_matching_brief_total_cost(self, db: Session, branch_id: int):
        from app.modules.maintenance.models import Asset

        assets = db.query(Asset).filter(Asset.branch_id == branch_id).all()
        assert len(assets) == 13
        assert sum(a.purchase_cost for a in assets) == Decimal("19670000.00")

    def test_opening_accumulated_depreciation_matches_brief_exactly(self, db: Session, branch_id: int):
        from app.modules.maintenance.models import Asset

        assets = db.query(Asset).filter(Asset.branch_id == branch_id).all()
        land = next(a for a in assets if a.code == "HIST-FA-01")
        assert land.useful_life_years is None
        assert land.accumulated_depreciation == Decimal("0.00")

        # المبلغ الافتتاحي (قبل تشغيل إهلاك يوليو) — بيتاكد من قيمة كل أصل
        # فردي زي ما اتحطت، لأن run_depreciation بيزوّد عليها لاحقًا.
        by_code = {a.code: a for a in assets}
        assert by_code["HIST-FA-02"].accumulated_depreciation - Decimal("31666.67") == Decimal("1330000.00")
        assert by_code["HIST-FA-10"].accumulated_depreciation - Decimal("2976.19") == Decimal("71428.57")

    def test_july_depreciation_posted_matches_brief_target_exactly(self, db: Session, branch_id: int):
        from app.modules.finance.models import AssetDepreciationEntry

        entries = (
            db.query(AssetDepreciationEntry)
            .filter(
                AssetDepreciationEntry.branch_id == branch_id,
                AssetDepreciationEntry.year == 2026, AssetDepreciationEntry.month == 7,
            )
            .all()
        )
        # الأرض مستبعدة (useful_life_years=None) — 12 أصل بس بيدخلوا الإهلاك
        assert len(entries) == 12
        assert sum(e.amount for e in entries) == Decimal("83226.19")

    def test_depreciation_journal_entry_is_balanced(self, db: Session, branch_id: int):
        from app.modules.finance.models import Account, JournalEntry, JournalLine

        entry = (
            db.query(JournalEntry)
            .filter(JournalEntry.branch_id == branch_id, JournalEntry.source == "depreciation")
            .first()
        )
        assert entry is not None
        lines = db.query(JournalLine).filter(JournalLine.entry_id == entry.id).all()
        assert sum(l.debit for l in lines) == sum(l.credit for l in lines)
        assert sum(l.debit for l in lines) == Decimal("83226.19")

        expense_acc = db.query(Account).filter_by(branch_id=branch_id, code="5500").first()
        accum_acc = db.query(Account).filter_by(branch_id=branch_id, code="1590").first()
        assert expense_acc is not None and accum_acc is not None

    def test_asset_accumulated_depreciation_updated_after_july_run(self, db: Session, branch_id: int):
        from app.modules.maintenance.models import Asset

        building = db.query(Asset).filter_by(branch_id=branch_id, code="HIST-FA-02").first()
        assert building.accumulated_depreciation == Decimal("1361666.67")  # 1,330,000 + 31,666.67

    def test_running_depreciation_twice_is_idempotent(self, db: Session, branch_id: int):
        """run_depreciation نفسها idempotent (UniqueConstraint asset_id/year/
        month) — تشغيلها تاني لنفس الشهر لازم ميضيفش قيود جديدة ولا يغيّر
        الإجمالي."""
        from app.modules.finance.models import AssetDepreciationEntry
        from app.modules.finance.services import run_depreciation

        before = db.query(AssetDepreciationEntry).filter(
            AssetDepreciationEntry.year == 2026, AssetDepreciationEntry.month == 7,
        ).count()

        result = run_depreciation(db, branch_id, 2026, 7, user_id=0)
        db.commit()

        after = db.query(AssetDepreciationEntry).filter(
            AssetDepreciationEntry.year == 2026, AssetDepreciationEntry.month == 7,
        ).count()
        assert after == before
        assert len(result.entries) == 0
        assert result.total_amount == Decimal("0")
