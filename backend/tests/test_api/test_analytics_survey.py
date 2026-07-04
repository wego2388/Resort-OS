"""tests/test_api/test_analytics_survey.py"""
from __future__ import annotations
from datetime import date

from tests.test_api.test_pms import make_branch


def _make_timeshare_visit(db, branch):
    """عقد تايم شير + وحدة + زيارة حقيقية — لاختبار ربط التقييم بزيارة
    تايم شير بدل حجز فندقي (بدل ما نضطر نستخدم booking_id مزيّف)."""
    from decimal import Decimal
    from app.modules.timeshare.models import TimeshareUnit
    from app.modules.timeshare.schemas import TimeshareContractCreate, TimeshareVisitCreate
    from app.modules.timeshare import services as ts_services

    unit = TimeshareUnit(branch_id=branch.id, unit_number="A-101", unit_type="2R")
    db.add(unit); db.flush()

    contract = ts_services.create_contract(db, TimeshareContractCreate(
        branch_id=branch.id, customer_name="عميل تايم شير", room_type="2R",
        total_value=Decimal("120000"), down_payment=Decimal("20000"),
        installments=12, installment_period=1,
        first_installment_date=date(2026, 8, 1),
        partner_share_pct=Decimal("0"), start_date=date(2026, 7, 1),
    ), signed_by=1)

    visit = ts_services.create_visit(db, TimeshareVisitCreate(
        branch_id=branch.id, contract_id=contract.id,
        check_in=date(2026, 8, 1), check_out=date(2026, 8, 8),
    ))
    return visit


class TestSurveyToken:

    def test_create_and_verify_token(self, db):
        from app.modules.analytics.services import create_survey_token, verify_survey_token
        branch = make_branch(db)
        token = create_survey_token(branch_id=branch.id, booking_id=42)
        assert isinstance(token, str) and len(token) > 20
        payload = verify_survey_token(token)
        assert payload["sub"] == "42"
        assert payload["branch_id"] == branch.id
        assert payload["purpose"] == "guest_survey"
        assert payload["ref_type"] == "booking"

    def test_create_token_requires_exactly_one_ref(self, db):
        from app.modules.analytics.services import create_survey_token
        import pytest
        branch = make_branch(db)
        with pytest.raises(ValueError):
            create_survey_token(branch_id=branch.id)  # لا booking ولا زيارة
        with pytest.raises(ValueError):
            create_survey_token(branch_id=branch.id, booking_id=1, timeshare_visit_id=2)  # الاثنين معًا

    def test_create_and_verify_timeshare_visit_token(self, db):
        """توكن استبيان لزيارة تايم شير — ref_type لازم يبقى timeshare_visit،
        مش booking (المسار الجديد بجانب مسار الحجز الفندقي القديم)."""
        from app.modules.analytics.services import create_survey_token, verify_survey_token
        branch = make_branch(db)
        visit = _make_timeshare_visit(db, branch)

        token = create_survey_token(branch_id=branch.id, timeshare_visit_id=visit.id)
        payload = verify_survey_token(token)
        assert payload["sub"] == str(visit.id)
        assert payload["ref_type"] == "timeshare_visit"

    def test_submit_review_for_timeshare_visit(self, db):
        """تقديم تقييم مرتبط بزيارة تايم شير (مش حجز فندقي) — لازم يتسجّل
        بـ timeshare_visit_id ومن غير booking_id."""
        from app.modules.analytics.services import submit_review
        branch = make_branch(db)
        visit = _make_timeshare_visit(db, branch)

        review = submit_review(db, branch.id, booking_id=None, data={
            "guest_name": "عميل تايم شير",
            "overall_rating": 5,
            "comment": "إقامة ممتازة",
        }, timeshare_visit_id=visit.id)

        assert review.booking_id is None
        assert review.timeshare_visit_id == visit.id

    def test_invalid_token_raises(self, db):
        from app.modules.analytics.services import verify_survey_token
        from fastapi import HTTPException
        import pytest
        with pytest.raises(HTTPException):
            verify_survey_token("invalid.token.here")

    def test_submit_review_high_rating(self, db):
        from app.modules.analytics.services import submit_review
        from app.modules.analytics.models import GuestReview
        branch = make_branch(db)
        review = submit_review(db, branch.id, booking_id=None, data={
            "guest_name": "أحمد",
            "overall_rating": 5,
            "comment": "رائع جداً",
            "categories": [
                {"category": "service", "rating": 5},
                {"category": "cleanliness", "rating": 4},
            ],
        })
        assert review.id is not None
        assert review.overall_rating == 5
        assert review.is_published is True

    def test_submit_review_low_rating_creates_complaint(self, db):
        from app.modules.analytics.services import submit_review
        from app.modules.crm.models import Activity
        branch = make_branch(db)
        before = db.query(Activity).filter(Activity.branch_id == branch.id).count()
        submit_review(db, branch.id, booking_id=None, data={
            "guest_name": "ضيف غير راضٍ",
            "overall_rating": 1,
        })
        after = db.query(Activity).filter(
            Activity.branch_id == branch.id,
            Activity.activity_type == "complaint",
        ).count()
        assert after > before  # تُنشئ complaint activity تلقائياً
