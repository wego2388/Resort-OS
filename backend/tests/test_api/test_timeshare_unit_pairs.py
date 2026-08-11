"""OPS-DATA-02 §8 نقطة 11 — عقود سعة 6 (Family Compound entitlement): شاليه
+ استوديو مقترنين في زيارة استحقاق واحدة ذرّية، بدون أي رسم ليلة جديد."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.modules.timeshare import crud, services
from app.modules.timeshare.schemas import (
    TimeshareContractCreate, TimeshareUnitPairCreate, TimeshareVisitCreate,
)


@pytest.fixture
def branch(db: Session):
    from app.modules.core.models import Branch
    b = Branch(name="Test", name_ar="اختبار", code=f"TUP-{uuid.uuid4().hex[:6].upper()}")
    db.add(b); db.commit()
    return b


@pytest.fixture
def chalet(db: Session, branch):
    from app.modules.timeshare.models import TimeshareUnit
    u = TimeshareUnit(branch_id=branch.id, unit_number="102-C", unit_type="Chalet")
    db.add(u); db.commit()
    return u


@pytest.fixture
def studio(db: Session, branch):
    from app.modules.timeshare.models import TimeshareUnit
    u = TimeshareUnit(branch_id=branch.id, unit_number="102-S", unit_type="Studio")
    db.add(u); db.commit()
    return u


@pytest.fixture
def pair(db: Session, branch, chalet, studio):
    return services.create_unit_pair(db, TimeshareUnitPairCreate(
        branch_id=branch.id, chalet_unit_id=chalet.id, studio_unit_id=studio.id,
    ))


def _seed_finance_accounts(db, branch) -> None:
    """⚠️ 2026-08-11 (strict=True — راجع §4): من غير 1100/4600، إنشاء أي عقد
    بدفعة أولى غير صفرية بيفشل بـ FinancialConfigurationError."""
    from app.modules.finance.models import Account
    if db.query(Account).filter_by(branch_id=branch.id, code="1100").first():
        return
    db.add_all([
        Account(branch_id=branch.id, code="1100", name="Cash", account_type="asset"),
        Account(branch_id=branch.id, code="4600", name="Timeshare Revenue", account_type="revenue"),
    ])
    db.commit()


def _contract(db, branch, unit_id=None, capacity=6):
    _seed_finance_accounts(db, branch)
    data = TimeshareContractCreate(
        branch_id=branch.id, customer_name="عميل Family Compound", customer_phone="01000000020",
        room_type="Chalet", unit_capacity=capacity, unit_id=unit_id,
        total_value=Decimal("300000"), down_payment=Decimal("30000"),
        installments=12, installment_period=1,
        first_installment_date=date(2026, 9, 1), start_date=date(2026, 8, 1),
    )
    return services.create_contract(db, data, signed_by=1)


class TestCreateUnitPair:
    def test_creates_pair(self, db: Session, branch, chalet, studio):
        p = services.create_unit_pair(db, TimeshareUnitPairCreate(
            branch_id=branch.id, chalet_unit_id=chalet.id, studio_unit_id=studio.id,
        ))
        assert p.chalet_unit_id == chalet.id
        assert p.studio_unit_id == studio.id
        assert p.is_active is True

    def test_rejects_wrong_unit_type(self, db: Session, branch, chalet, studio):
        with pytest.raises(ValueError, match="ليست من نوع Chalet"):
            services.create_unit_pair(db, TimeshareUnitPairCreate(
                branch_id=branch.id, chalet_unit_id=studio.id, studio_unit_id=chalet.id,
            ))

    def test_rejects_duplicate_chalet(self, db: Session, branch, chalet, studio, pair):
        from app.modules.timeshare.models import TimeshareUnit
        studio2 = TimeshareUnit(branch_id=branch.id, unit_number="102-S2", unit_type="Studio")
        db.add(studio2); db.commit()
        with pytest.raises(ValueError, match="مرتبطة بالفعل"):
            services.create_unit_pair(db, TimeshareUnitPairCreate(
                branch_id=branch.id, chalet_unit_id=chalet.id, studio_unit_id=studio2.id,
            ))


class TestEntitlementVisitFixedUnit:
    def test_creates_visit_on_both_units(self, db: Session, branch, chalet, studio, pair):
        contract = _contract(db, branch, unit_id=chalet.id)
        visit = services.create_visit(db, TimeshareVisitCreate(
            branch_id=branch.id, contract_id=contract.id,
            check_in=date(2026, 8, 10), check_out=date(2026, 8, 17),
        ))
        assert visit.unit_id == chalet.id
        assert visit.paired_unit_id == studio.id
        assert visit.entitlement_visit is True
        # مفيش أي حجز PMS اتعمل — راجع docstring TimeshareVisit.entitlement_visit
        assert visit.booking_id is None

    def test_no_pair_configured_rejected(self, db: Session, branch, chalet):
        contract = _contract(db, branch, unit_id=chalet.id)
        with pytest.raises(ValueError, match="مالهاش زوج معتمد"):
            services.create_visit(db, TimeshareVisitCreate(
                branch_id=branch.id, contract_id=contract.id,
                check_in=date(2026, 8, 10), check_out=date(2026, 8, 17),
            ))

    def test_conflict_on_either_unit_rejected(self, db: Session, branch, chalet, studio, pair):
        contract = _contract(db, branch, unit_id=chalet.id)
        services.create_visit(db, TimeshareVisitCreate(
            branch_id=branch.id, contract_id=contract.id,
            check_in=date(2026, 8, 10), check_out=date(2026, 8, 17),
        ))
        contract2 = _contract(db, branch, unit_id=chalet.id)
        with pytest.raises(ValueError, match="محجوزة بالفعل"):
            services.create_visit(db, TimeshareVisitCreate(
                branch_id=branch.id, contract_id=contract2.id,
                check_in=date(2026, 8, 14), check_out=date(2026, 8, 20),
            ))

    def test_studio_alone_now_shows_as_booked(self, db: Session, branch, chalet, studio, pair):
        """التعارض لازم يتكشف حتى لو الوحدة التانية استُخدمت بس كـpaired_unit
        (مش unit_id مباشر) في زيارة تانية — راجع has_overlapping_visit."""
        contract = _contract(db, branch, unit_id=chalet.id)
        services.create_visit(db, TimeshareVisitCreate(
            branch_id=branch.id, contract_id=contract.id,
            check_in=date(2026, 8, 10), check_out=date(2026, 8, 17),
        ))
        assert crud.has_overlapping_visit(db, studio.id, date(2026, 8, 12), date(2026, 8, 15)) is True


class TestEntitlementVisitFloatingContract:
    def test_finds_available_pair(self, db: Session, branch, chalet, studio, pair):
        contract = _contract(db, branch, unit_id=None)
        visit = services.create_visit(db, TimeshareVisitCreate(
            branch_id=branch.id, contract_id=contract.id,
            check_in=date(2026, 8, 10), check_out=date(2026, 8, 17),
        ))
        assert visit.unit_id == chalet.id
        assert visit.paired_unit_id == studio.id

    def test_no_pair_available_rejected(self, db: Session, branch):
        contract = _contract(db, branch, unit_id=None)
        with pytest.raises(ValueError, match="لا يوجد زوج وحدات"):
            services.create_visit(db, TimeshareVisitCreate(
                branch_id=branch.id, contract_id=contract.id,
                check_in=date(2026, 8, 10), check_out=date(2026, 8, 17),
            ))


class TestRegularCapacityUnaffected:
    def test_capacity_4_uses_single_unit_flow(self, db: Session, branch, chalet):
        """عقد سعة 4 (شاليه عادي، مش Family Compound) لازم يفضل يستخدم
        create_visit العادية (وحدة واحدة، entitlement_visit=False) — التفرّع
        الجديد بيتفعّل بس لما unit_capacity == 6 بالظبط."""
        contract = _contract(db, branch, unit_id=chalet.id, capacity=4)
        visit = services.create_visit(db, TimeshareVisitCreate(
            branch_id=branch.id, contract_id=contract.id,
            check_in=date(2026, 8, 10), check_out=date(2026, 8, 17),
        ))
        assert visit.unit_id == chalet.id
        assert visit.paired_unit_id is None
        assert visit.entitlement_visit is False


class TestUnitPairHttp:
    def _admin(self, db, branch, timeshare_admin_headers):
        from tests.conftest import assign_test_user_to_branch
        from app.core.kernel.models.user import User
        admin = db.query(User).filter(User.email == "timeshare-admin@test.local").first()
        assign_test_user_to_branch(db, admin.id, branch.id)
        db.commit()
        return admin

    def test_create_list_deactivate_unit_pair(self, client, db: Session, branch, chalet, studio, timeshare_admin_headers):
        self._admin(db, branch, timeshare_admin_headers)

        create_resp = client.post(
            "/api/v1/timeshare/unit-pairs",
            json={"branch_id": branch.id, "chalet_unit_id": chalet.id, "studio_unit_id": studio.id},
            headers=timeshare_admin_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        pair_id = create_resp.json()["id"]

        list_resp = client.get(
            "/api/v1/timeshare/unit-pairs", params={"branch_id": branch.id}, headers=timeshare_admin_headers,
        )
        assert list_resp.status_code == 200
        assert any(p["id"] == pair_id for p in list_resp.json())

        deactivate_resp = client.post(
            f"/api/v1/timeshare/unit-pairs/{pair_id}/deactivate", headers=timeshare_admin_headers,
        )
        assert deactivate_resp.status_code == 200, deactivate_resp.text
        assert deactivate_resp.json()["is_active"] is False

        active_list = client.get(
            "/api/v1/timeshare/unit-pairs", params={"branch_id": branch.id}, headers=timeshare_admin_headers,
        )
        assert pair_id not in {p["id"] for p in active_list.json()}
