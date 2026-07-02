"""tests/test_api/test_analytics.py"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from tests.test_api.test_pms import make_branch


class TestDailyStats:

    def test_creates_and_upserts(self, db):
        """_build_stats يُنشئ ثم يُحدِّث صف DailyStats."""
        from app.tasks.analytics_tasks import _build_stats
        from app.modules.analytics.models import DailyStats

        branch = make_branch(db)
        stat_date = date.today() - timedelta(days=5)

        _build_stats(db, branch.id, stat_date)
        count_after_first = db.query(DailyStats).filter(
            DailyStats.branch_id == branch.id, DailyStats.stat_date == stat_date
        ).count()
        assert count_after_first == 1

        _build_stats(db, branch.id, stat_date)
        count_after_second = db.query(DailyStats).filter(
            DailyStats.branch_id == branch.id, DailyStats.stat_date == stat_date
        ).count()
        assert count_after_second == 1  # upsert — ليس صفين

    def test_zero_when_no_module_data(self, db):
        """يُنشئ صفر إذا لا بيانات مشروع."""
        from app.tasks.analytics_tasks import _build_stats
        from app.modules.analytics.models import DailyStats

        branch = make_branch(db)
        stat_date = date(2018, 6, 1)
        _build_stats(db, branch.id, stat_date)

        row = db.query(DailyStats).filter(
            DailyStats.branch_id == branch.id, DailyStats.stat_date == stat_date
        ).first()
        assert row is not None
        assert row.total_revenue == Decimal("0")
        assert row.beach_visitors == 0
        assert row.generated_at is not None


class TestGuestReviews:

    def test_empty_branch_no_reviews(self, db):
        from app.modules.analytics.models import GuestReview
        branch = make_branch(db)
        count = db.query(GuestReview).filter(
            GuestReview.branch_id == branch.id
        ).count()
        assert count == 0

    def test_published_vs_unpublished(self, db):
        from app.modules.analytics.models import GuestReview
        branch = make_branch(db)
        db.add(GuestReview(
            branch_id=branch.id,
            guest_name="أحمد",
            overall_rating=5,
            is_published=True,
            reviewed_at=date.today(),
        ))
        db.add(GuestReview(
            branch_id=branch.id,
            guest_name="مخفي",
            overall_rating=1,
            is_published=False,
            reviewed_at=date.today(),
        ))
        db.commit()

        published = db.query(GuestReview).filter(
            GuestReview.branch_id == branch.id,
            GuestReview.is_published.is_(True),
        ).all()
        assert len(published) == 1
        assert published[0].overall_rating == 5

    def test_avg_rating(self, db):
        from app.modules.analytics.models import GuestReview
        branch = make_branch(db)
        for rating in [3, 4, 5]:
            db.add(GuestReview(
                branch_id=branch.id,
                guest_name=f"ضيف {rating}",
                overall_rating=rating,
                is_published=True,
                reviewed_at=date.today(),
            ))
        db.commit()
        reviews = db.query(GuestReview).filter(
            GuestReview.branch_id == branch.id, GuestReview.is_published.is_(True)
        ).all()
        avg = sum(r.overall_rating for r in reviews) / len(reviews)
        assert avg == 4.0


class TestUtilityReadings:

    def test_create_reading(self, db):
        from app.modules.analytics.models import UtilityReading
        branch = make_branch(db)
        db.add(UtilityReading(
            branch_id=branch.id,
            reading_date=date.today(),
            utility_type="electricity",
            reading_value=Decimal("12345.678"),
            unit="kWh",
        ))
        db.commit()
        row = db.query(UtilityReading).filter(
            UtilityReading.branch_id == branch.id
        ).first()
        assert row is not None
        assert row.reading_value == Decimal("12345.678")
        assert row.utility_type == "electricity"

    def test_multiple_utility_types(self, db):
        from app.modules.analytics.models import UtilityReading
        branch = make_branch(db)
        for ut in ["electricity", "water", "gas"]:
            db.add(UtilityReading(
                branch_id=branch.id,
                reading_date=date.today(),
                utility_type=ut,
                reading_value=Decimal("100"),
                unit="kWh" if ut == "electricity" else "m3",
            ))
        db.commit()
        count = db.query(UtilityReading).filter(
            UtilityReading.branch_id == branch.id
        ).count()
        assert count == 3
