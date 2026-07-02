"""tests/test_api/test_analytics_survey.py"""
from __future__ import annotations
from tests.test_api.test_pms import make_branch


class TestSurveyToken:

    def test_create_and_verify_token(self, db):
        from app.modules.analytics.services import create_survey_token, verify_survey_token
        branch = make_branch(db)
        token = create_survey_token(booking_id=42, branch_id=branch.id)
        assert isinstance(token, str) and len(token) > 20
        payload = verify_survey_token(token)
        assert payload["sub"] == "42"
        assert payload["branch_id"] == branch.id
        assert payload["purpose"] == "guest_survey"

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
