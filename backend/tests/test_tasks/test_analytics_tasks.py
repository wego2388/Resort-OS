"""tests/test_tasks/test_analytics_tasks.py"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.tasks.analytics_tasks import _build_stats


class TestBuildStats:
    """اختبارات توليد DailyStats."""

    def test_creates_daily_stats_row(self, db):
        """يُنشئ صف DailyStats للتاريخ المطلوب."""
        from app.modules.analytics.models import DailyStats
        from tests.test_api.test_pms import make_branch

        branch = make_branch(db)
        stat_date = date.today() - timedelta(days=1)
        _build_stats(db, branch.id, stat_date)

        row = db.query(DailyStats).filter(
            DailyStats.branch_id == branch.id,
            DailyStats.stat_date == stat_date,
        ).first()
        assert row is not None
        assert row.generated_at is not None

    def test_upsert_overwrites_existing(self, db):
        """يُحدِّث الصف عند استدعاء _build_stats مرتين لنفس اليوم."""
        from app.modules.analytics.models import DailyStats
        from tests.test_api.test_pms import make_branch

        branch = make_branch(db)
        stat_date = date.today() - timedelta(days=2)

        _build_stats(db, branch.id, stat_date)
        _build_stats(db, branch.id, stat_date)

        count = db.query(DailyStats).filter(
            DailyStats.branch_id == branch.id,
            DailyStats.stat_date == stat_date,
        ).count()
        assert count == 1   # upsert — لا صفين

    def test_zero_values_when_no_data(self, db):
        """يُنشئ صفراً لكل المؤشرات إذا لا يوجد بيانات."""
        from app.modules.analytics.models import DailyStats
        from tests.test_api.test_pms import make_branch

        branch = make_branch(db)
        stat_date = date(2020, 1, 1)
        _build_stats(db, branch.id, stat_date)

        row = db.query(DailyStats).filter(
            DailyStats.branch_id == branch.id,
            DailyStats.stat_date == stat_date,
        ).first()
        assert row.total_revenue == Decimal("0")
        assert row.beach_visitors == 0
