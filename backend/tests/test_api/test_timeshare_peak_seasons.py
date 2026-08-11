"""OPS-DATA-02 §8 نقطة 5 — مواسم الذروة: أسبوع واحد سنويًا + عدم تتابع
الأعياد الرسمية (سياسة سنة فاصلة، مش فجوة 30 يوم) + عدم العد المزدوج."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.modules.timeshare import crud, services
from app.modules.timeshare.schemas import (
    TimeshareContractCreate, TimesharePeakSeasonCreate, TimeshareVisitRequestCreate,
)


@pytest.fixture
def branch(db: Session):
    from app.modules.core.models import Branch
    b = Branch(name="Test", name_ar="اختبار", code=f"TSP-{uuid.uuid4().hex[:6].upper()}")
    db.add(b); db.commit()
    return b


@pytest.fixture
def unit(db: Session, branch):
    """وحدة تايم شير فعلية متاحة — لازمة عشان approve_visit_request
    (بتنادي create_visit) تقدر تخصّص وحدة حقيقية."""
    from app.modules.timeshare.models import TimeshareUnit
    u = TimeshareUnit(branch_id=branch.id, unit_number="A-101", unit_type="Studio")
    db.add(u); db.commit()
    return u


@pytest.fixture
def contract(db: Session, branch, unit):
    # ⚠️ 2026-08-11 (strict=True — راجع §4): من غير 1100/4600، create_contract
    # بيفشل بـ FinancialConfigurationError (قيد الدفعة الأولى).
    from app.modules.finance.models import Account
    db.add_all([
        Account(branch_id=branch.id, code="1100", name="Cash", account_type="asset"),
        Account(branch_id=branch.id, code="4600", name="Timeshare Revenue", account_type="revenue"),
    ])
    db.commit()
    data = TimeshareContractCreate(
        branch_id=branch.id, customer_name="عميل ذروة", customer_phone="01000000010",
        room_type="Studio", unit_capacity=2,
        total_value=Decimal("100000"), down_payment=Decimal("10000"),
        installments=12, installment_period=1,
        first_installment_date=date(2026, 9, 1), start_date=date(2026, 8, 1),
    )
    c = services.create_contract(db, data, signed_by=1)
    return c


def _season(db, branch, name, peak_kind, year, start, end):
    return crud.create_peak_season(db, TimesharePeakSeasonCreate(
        branch_id=branch.id, name=name, peak_kind=peak_kind,
        season_year=year, start_date=start, end_date=end,
    ), created_by=None)


def _request(start, end):
    return TimeshareVisitRequestCreate(
        preferred_start=start, preferred_end=end,
        terms_accepted=True, terms_version="timeshare-terms-2026-08-10.v1",
        booking_rules_accepted=True, booking_rules_version="timeshare-booking-rules-2026-08-10.v1",
    )


class TestNonPeakRequestsUnrestricted:
    def test_request_outside_any_season_always_succeeds(self, db: Session, branch, contract):
        _season(db, branch, "عيد 2026", "official_holiday", 2026, date(2026, 6, 20), date(2026, 6, 27))
        # فترة برّه أي موسم خالص
        req = services.request_visit(db, contract.id, _request(date(2026, 10, 1), date(2026, 10, 8)))
        assert req.status == "pending"


class TestOnePeakWeekPerYear:
    def test_first_peak_request_this_year_succeeds(self, db: Session, branch, contract):
        _season(db, branch, "صيف 2026", "regular", 2026, date(2026, 8, 1), date(2026, 9, 30))
        req = services.request_visit(db, contract.id, _request(date(2026, 8, 10), date(2026, 8, 17)))
        assert req.status == "pending"

    def test_second_peak_request_same_year_rejected_even_if_not_approved_yet(
        self, db: Session, branch, contract,
    ):
        """قاعدة الأسبوع الواحد بتتحقق وقت الطلب نفسه، مش بس وقت الموافقة —
        العميل ميقدرش أصلًا يقدّم طلب ذروة تاني في نفس السنة، حتى لو الأول
        لسه pending."""
        _season(db, branch, "صيف 2026", "regular", 2026, date(2026, 8, 1), date(2026, 9, 30))
        services.request_visit(db, contract.id, _request(date(2026, 8, 10), date(2026, 8, 17)))
        with pytest.raises(ValueError, match="أكثر من أسبوع ذروة واحد"):
            services.request_visit(db, contract.id, _request(date(2026, 9, 1), date(2026, 9, 8)))

    def test_different_years_both_succeed(self, db: Session, branch, contract):
        _season(db, branch, "صيف 2026", "regular", 2026, date(2026, 8, 1), date(2026, 9, 30))
        _season(db, branch, "صيف 2027", "regular", 2027, date(2027, 8, 1), date(2027, 9, 30))
        r1 = services.request_visit(db, contract.id, _request(date(2026, 8, 10), date(2026, 8, 17)))
        r2 = services.request_visit(db, contract.id, _request(date(2027, 8, 10), date(2027, 8, 17)))
        assert r1.status == r2.status == "pending"


class TestHolidayCooldown:
    def test_consecutive_year_official_holiday_rejected(self, db: Session, branch, contract):
        _season(db, branch, "عيد 2026", "official_holiday", 2026, date(2026, 6, 20), date(2026, 6, 27))
        _season(db, branch, "عيد 2027", "official_holiday", 2027, date(2027, 6, 10), date(2027, 6, 17))
        services.request_visit(db, contract.id, _request(date(2026, 6, 21), date(2026, 6, 28)))
        # الطلب الأول approved فعليًا (مش pending) عشان نتأكد الفحص بيشمل
        # approved requests، مش pending بس
        req1 = crud.list_visit_requests_for_contract(db, contract.id)[0]
        services.approve_visit_request(db, req1.id, date(2026, 6, 21), date(2026, 6, 28), approved_by=1)

        with pytest.raises(ValueError, match="سنة فاصلة"):
            services.request_visit(db, contract.id, _request(date(2027, 6, 11), date(2027, 6, 18)))

    def test_after_one_skipped_year_succeeds(self, db: Session, branch, contract):
        _season(db, branch, "عيد 2026", "official_holiday", 2026, date(2026, 6, 20), date(2026, 6, 27))
        _season(db, branch, "عيد 2028", "official_holiday", 2028, date(2028, 6, 1), date(2028, 6, 8))
        req1 = services.request_visit(db, contract.id, _request(date(2026, 6, 21), date(2026, 6, 28)))
        services.approve_visit_request(db, req1.id, date(2026, 6, 21), date(2026, 6, 28), approved_by=1)

        req2 = services.request_visit(db, contract.id, _request(date(2028, 6, 2), date(2028, 6, 9)))
        assert req2.status == "pending"

    def test_regular_season_not_subject_to_holiday_cooldown(self, db: Session, branch, contract):
        """الصيف/الموسم العادي مش عيد — معفى تمامًا من قاعدة التتابع، حتى
        لو نفس العقد استخدم عيد رسمي في السنة اللي قبلها مباشرة."""
        _season(db, branch, "عيد 2026", "official_holiday", 2026, date(2026, 6, 20), date(2026, 6, 27))
        _season(db, branch, "صيف 2027", "regular", 2027, date(2027, 8, 1), date(2027, 9, 30))
        req1 = services.request_visit(db, contract.id, _request(date(2026, 6, 21), date(2026, 6, 28)))
        services.approve_visit_request(db, req1.id, date(2026, 6, 21), date(2026, 6, 28), approved_by=1)

        req2 = services.request_visit(db, contract.id, _request(date(2027, 8, 10), date(2027, 8, 17)))
        assert req2.status == "pending"  # مقبول رغم إنها السنة اللي بعد العيد مباشرة


class TestNoDoubleCounting:
    def test_approved_request_and_resulting_visit_count_as_one_event(self, db: Session, branch, contract):
        """التوثيق بيثبت الحدث الواحد بس مرة واحدة — approve_visit_request
        بينشئ TimeshareVisit عبر services.create_visit ويربطها بـvisit_id،
        فمفروض تتحسب حدث واحد بس رغم وجود صف طلب وصف زيارة منفصلين."""
        _season(db, branch, "صيف 2026", "regular", 2026, date(2026, 8, 1), date(2026, 9, 30))
        req1 = services.request_visit(db, contract.id, _request(date(2026, 8, 10), date(2026, 8, 17)))
        services.approve_visit_request(db, req1.id, date(2026, 8, 10), date(2026, 8, 17), approved_by=1)

        years = services._peak_event_years_for_contract(db, contract)
        assert years == {2026}  # مش {2026, 2026} أو أي تضخيم

        # ولسه ملتزم بحد الأسبوع الواحد — مش اتنين لأن الحدث اتعدّ اتنين
        with pytest.raises(ValueError, match="أكثر من أسبوع ذروة واحد"):
            services.request_visit(db, contract.id, _request(date(2026, 9, 1), date(2026, 9, 8)))


class TestDeactivatedSeasonExcluded:
    def test_deactivated_season_does_not_trigger_peak_rules(self, db: Session, branch, contract):
        season = _season(db, branch, "صيف 2026", "regular", 2026, date(2026, 8, 1), date(2026, 9, 30))
        crud.deactivate_peak_season(db, season)
        db.commit()

        # لأن الموسم بقى معطّل، الفترة دي بقت "مش ذروة" — يقدر يطلب مرتين
        r1 = services.request_visit(db, contract.id, _request(date(2026, 8, 10), date(2026, 8, 17)))
        r2 = services.request_visit(db, contract.id, _request(date(2026, 9, 1), date(2026, 9, 8)))
        assert r1.status == r2.status == "pending"


class TestPeakSeasonHttp:
    def _admin(self, db, branch, timeshare_admin_headers):
        from tests.conftest import assign_test_user_to_branch
        from app.core.kernel.models.user import User
        admin = db.query(User).filter(User.email == "timeshare-admin@test.local").first()
        assign_test_user_to_branch(db, admin.id, branch.id)
        db.commit()
        return admin

    def test_create_list_deactivate_peak_season(self, client, db: Session, branch, timeshare_admin_headers):
        self._admin(db, branch, timeshare_admin_headers)

        create_resp = client.post(
            "/api/v1/timeshare/peak-seasons",
            json={
                "branch_id": branch.id, "name": "Eid 2026", "name_ar": "عيد 2026",
                "peak_kind": "official_holiday", "season_year": 2026,
                "start_date": "2026-06-20", "end_date": "2026-06-27",
            },
            headers=timeshare_admin_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        season_id = create_resp.json()["id"]

        list_resp = client.get(
            "/api/v1/timeshare/peak-seasons", params={"branch_id": branch.id}, headers=timeshare_admin_headers,
        )
        assert list_resp.status_code == 200
        assert any(s["id"] == season_id for s in list_resp.json())

        deactivate_resp = client.post(
            f"/api/v1/timeshare/peak-seasons/{season_id}/deactivate", headers=timeshare_admin_headers,
        )
        assert deactivate_resp.status_code == 200, deactivate_resp.text
        assert deactivate_resp.json()["is_active"] is False

        active_list = client.get(
            "/api/v1/timeshare/peak-seasons", params={"branch_id": branch.id}, headers=timeshare_admin_headers,
        )
        assert season_id not in {s["id"] for s in active_list.json()}
