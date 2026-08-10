"""OPS-DATA-02 §8 نقطة 3 — قواعد صيانة effective-dated/versioned."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.modules.timeshare import crud, services


@pytest.fixture
def branch(db: Session):
    from app.modules.core.models import Branch
    b = Branch(name="Test", name_ar="اختبار", code=f"TSF-{uuid.uuid4().hex[:6].upper()}")
    db.add(b); db.commit()
    return b


class TestSeed2026MaintenanceFeeRules:
    def test_creates_six_rows(self, db: Session, branch):
        rules = services.seed_2026_maintenance_fee_rules(db, branch.id)
        assert len(rules) == 6
        capacities = {(r.contract_tier_from, r.capacity) for r in rules}
        assert len(capacities) == 6

    def test_idempotent_on_second_call(self, db: Session, branch):
        services.seed_2026_maintenance_fee_rules(db, branch.id)
        second = services.seed_2026_maintenance_fee_rules(db, branch.id)
        assert second == []
        assert len(crud.list_maintenance_fee_rules(db, branch.id, fee_year=2026, active_only=False)) == 6


class TestGetRecommendedMaintenanceFee:
    def test_before_may_tier(self, db: Session, branch):
        services.seed_2026_maintenance_fee_rules(db, branch.id)
        fee, version = services.get_recommended_maintenance_fee(
            db, branch.id, 2026, date(2026, 3, 15), capacity=4,
        )
        assert fee == Decimal("2000")
        assert version == services.MAINTENANCE_FEES_2026_VERSION

    def test_from_may_tier(self, db: Session, branch):
        services.seed_2026_maintenance_fee_rules(db, branch.id)
        fee, _ = services.get_recommended_maintenance_fee(
            db, branch.id, 2026, date(2026, 6, 1), capacity=4,
        )
        assert fee == Decimal("3000")

    def test_exactly_on_tier_boundary_uses_new_tier(self, db: Session, branch):
        services.seed_2026_maintenance_fee_rules(db, branch.id)
        fee, _ = services.get_recommended_maintenance_fee(
            db, branch.id, 2026, date(2026, 5, 1), capacity=2,
        )
        assert fee == Decimal("2000")  # tier "from_may_2026", مش "before"

    def test_capacity_6_studio_family_compound(self, db: Session, branch):
        services.seed_2026_maintenance_fee_rules(db, branch.id)
        fee, _ = services.get_recommended_maintenance_fee(
            db, branch.id, 2026, date(2026, 1, 1), capacity=6,
        )
        assert fee == Decimal("2500")

    def test_no_rule_returns_none_not_zero(self, db: Session, branch):
        """مفيش قواعد اتزرعت خالص — None صريح، مش صفر ملغّم (نفس فلسفة
        RoomType.base_rate=None في pms)."""
        fee, version = services.get_recommended_maintenance_fee(
            db, branch.id, 2026, date(2026, 1, 1), capacity=4,
        )
        assert fee is None
        assert version is None

    def test_unknown_year_returns_none(self, db: Session, branch):
        services.seed_2026_maintenance_fee_rules(db, branch.id)
        fee, _ = services.get_recommended_maintenance_fee(
            db, branch.id, 2027, date(2027, 1, 1), capacity=4,
        )
        assert fee is None


class TestDeactivateMaintenanceFeeRule:
    def test_soft_deactivate_not_hard_delete(self, db: Session, branch):
        rules = services.seed_2026_maintenance_fee_rules(db, branch.id)
        rule = rules[0]
        crud.deactivate_maintenance_fee_rule(db, rule)
        db.commit()

        assert crud.get_maintenance_fee_rule(db, rule.id) is not None  # لسه موجود
        assert crud.get_maintenance_fee_rule(db, rule.id).is_active is False
        # مش ظاهر في القائمة النشطة الافتراضية
        active = crud.list_maintenance_fee_rules(db, branch.id, fee_year=2026, active_only=True)
        assert rule.id not in {r.id for r in active}
        # لكن لسه ظاهر لو طلبت الكل صراحةً
        all_rules = crud.list_maintenance_fee_rules(db, branch.id, fee_year=2026, active_only=False)
        assert rule.id in {r.id for r in all_rules}

    def test_deactivated_rule_excluded_from_recommendation(self, db: Session, branch):
        rules = services.seed_2026_maintenance_fee_rules(db, branch.id)
        target = next(r for r in rules if r.capacity == 4 and r.contract_tier_from == date(2000, 1, 1))
        crud.deactivate_maintenance_fee_rule(db, target)
        db.commit()

        fee, _ = services.get_recommended_maintenance_fee(
            db, branch.id, 2026, date(2026, 3, 1), capacity=4,
        )
        assert fee is None  # القاعدة الوحيدة اللي كانت هتنطبق بقت معطّلة


class TestMaintenanceFeeSuggestionHttp:
    def test_suggestion_endpoint_returns_recommended_fee(
        self, client, db: Session, branch, timeshare_admin_headers,
    ):
        from tests.conftest import assign_test_user_to_branch
        from app.core.kernel.models.user import User
        admin = db.query(User).filter(User.email == "timeshare-admin@test.local").first()
        assign_test_user_to_branch(db, admin.id, branch.id)
        db.commit()

        services.seed_2026_maintenance_fee_rules(db, branch.id)
        resp = client.get(
            "/api/v1/timeshare/maintenance-fee-suggestion",
            params={
                "branch_id": branch.id, "contract_date": "2026-06-01",
                "unit_capacity": 4, "fee_year": 2026,
            },
            headers=timeshare_admin_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert Decimal(str(body["suggested_fee"])) == Decimal("3000")
        assert body["rule_version"] == services.MAINTENANCE_FEES_2026_VERSION

    def test_seed_endpoint_creates_six_rows(self, client, db: Session, branch, timeshare_admin_headers):
        from tests.conftest import assign_test_user_to_branch
        from app.core.kernel.models.user import User
        admin = db.query(User).filter(User.email == "timeshare-admin@test.local").first()
        assign_test_user_to_branch(db, admin.id, branch.id)
        db.commit()

        resp = client.post(
            "/api/v1/timeshare/maintenance-fee-rules/seed-2026",
            params={"branch_id": branch.id}, headers=timeshare_admin_headers,
        )
        assert resp.status_code == 200, resp.text
        assert len(resp.json()) == 6
        # الـidempotency الفعلية (نداء تاني برجّع [] فاضية) متغطّية عند
        # services.seed_2026_maintenance_fee_rules مباشرة فوق
        # (TestSeed2026MaintenanceFeeRules::test_idempotent_on_second_call)
        # — مفيش داعي نكررها هنا عبر HTTP.
