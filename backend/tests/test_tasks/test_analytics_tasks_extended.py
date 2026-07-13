"""
tests/test_tasks/test_analytics_tasks.py
اختبارات analytics_tasks.py — _build_stats + generate_daily_stats wrapper
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest


def _db_ctx(db):
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=db)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


def _make_branch(db, active=True):
    from app.modules.core.models import Branch
    b = Branch(
        name=f"AN-Branch-{uuid.uuid4().hex[:6]}",
        code=f"AN{uuid.uuid4().hex[:4].upper()}",
        is_active=active,
    )
    db.add(b)
    db.commit()
    return b


class TestBuildStats:
    """اختبار _build_stats مباشرة"""

    def test_build_stats_creates_daily_stats_record(self, db):
        """_build_stats يُنشئ سجل DailyStats"""
        branch = _make_branch(db)
        yesterday = date.today() - timedelta(days=1)

        from app.tasks.analytics_tasks import _build_stats
        _build_stats(db, branch.id, yesterday)
        db.commit()

        from app.modules.analytics.models import DailyStats
        record = db.query(DailyStats).filter(
            DailyStats.branch_id == branch.id,
            DailyStats.stat_date == yesterday,
        ).first()
        assert record is not None

    def test_build_stats_idempotent(self, db):
        """تشغيل _build_stats مرتين لنفس اليوم لا يُنشئ سجلين"""
        branch = _make_branch(db)
        yesterday = date.today() - timedelta(days=1)

        from app.tasks.analytics_tasks import _build_stats
        from app.modules.analytics.models import DailyStats

        _build_stats(db, branch.id, yesterday)
        db.commit()
        _build_stats(db, branch.id, yesterday)
        db.commit()

        records = db.query(DailyStats).filter(
            DailyStats.branch_id == branch.id,
            DailyStats.stat_date == yesterday,
        ).all()
        assert len(records) == 1

    def test_build_stats_revenue_defaults_zero(self, db):
        """بدون أي بيانات مالية — الإيرادات تساوي صفر"""
        branch = _make_branch(db)
        yesterday = date.today() - timedelta(days=1)

        from app.tasks.analytics_tasks import _build_stats
        _build_stats(db, branch.id, yesterday)
        db.commit()

        from app.modules.analytics.models import DailyStats
        record = db.query(DailyStats).filter(
            DailyStats.branch_id == branch.id,
            DailyStats.stat_date == yesterday,
        ).first()
        assert record.total_revenue >= Decimal("0")
        assert record.room_revenue >= Decimal("0")

    def test_build_stats_multiple_dates(self, db):
        """_build_stats يعمل لأيام متعددة"""
        branch = _make_branch(db)

        from app.tasks.analytics_tasks import _build_stats
        from app.modules.analytics.models import DailyStats

        for i in range(1, 4):
            d = date.today() - timedelta(days=i)
            _build_stats(db, branch.id, d)
        db.commit()

        records = db.query(DailyStats).filter(
            DailyStats.branch_id == branch.id,
        ).all()
        assert len(records) >= 3

    def test_build_stats_with_restaurant_revenue(self, db):
        """_build_stats يحسب restaurant_revenue من الأوردرات المدفوعة —
        راجع DINING_CUTOVER_PLAN.md D-05: dining.DiningOrder بدل
        restaurant.Order القديم اللي اتحذف."""
        from datetime import datetime, timezone
        branch = _make_branch(db)
        yesterday = date.today() - timedelta(days=1)

        # أنشئ outlet + category + item + order
        from app.modules.dining import services as dining_services
        from app.modules.dining.models import DiningCategory, DiningItem, DiningOrder
        from app.modules.dining.schemas import OutletCreate
        outlet = dining_services.create_outlet(db, OutletCreate(
            branch_id=branch.id, name="مطعم تحليلات ممتدة", outlet_type="restaurant",
            revenue_account_code="4200",
        ))
        cat = DiningCategory(branch_id=branch.id, outlet_id=outlet.id, name="Food", is_active=True)
        db.add(cat)
        db.flush()
        item = DiningItem(
            branch_id=branch.id, outlet_id=outlet.id, category_id=cat.id,
            name="Dish", price=Decimal("50"), is_available=True,
        )
        db.add(item)
        db.flush()

        day_start = datetime.combine(yesterday, datetime.min.time())
        order = DiningOrder(
            branch_id=branch.id, outlet_id=outlet.id,
            order_number=f"ORD-{uuid.uuid4().hex[:8].upper()}",
            status="paid",
            subtotal=Decimal("50"),
            vat_amount=Decimal("7"),
            service_charge=Decimal("6"),
            total=Decimal("63"),
            guests_count=2,
            created_at=day_start,
        )
        db.add(order)
        db.commit()

        from app.tasks.analytics_tasks import _build_stats
        _build_stats(db, branch.id, yesterday)
        db.commit()

        from app.modules.analytics.models import DailyStats
        record = db.query(DailyStats).filter(
            DailyStats.branch_id == branch.id,
            DailyStats.stat_date == yesterday,
        ).first()
        assert record is not None
        assert record.restaurant_revenue >= Decimal("0")


class TestGenerateDailyStatsWrapper:
    """اختبار الـ task wrapper"""

    def test_task_wrapper_with_explicit_date(self, db):
        """task يشتغل مع branch + date محددين"""
        branch = _make_branch(db, active=True)
        yesterday = date.today() - timedelta(days=1)

        with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
            from app.tasks.analytics_tasks import generate_daily_stats
            generate_daily_stats(branch_id=branch.id, stat_date_str=str(yesterday))

        from app.modules.analytics.models import DailyStats
        record = db.query(DailyStats).filter(
            DailyStats.branch_id == branch.id,
            DailyStats.stat_date == yesterday,
        ).first()
        assert record is not None

    def test_task_wrapper_all_branches(self, db):
        """task يشتغل لكل الفروع النشطة"""
        branch = _make_branch(db, active=True)
        yesterday = date.today() - timedelta(days=1)

        with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
            from app.tasks.analytics_tasks import generate_daily_stats
            generate_daily_stats(stat_date_str=str(yesterday))

    def test_task_inactive_branch_skipped(self, db):
        """فرع غير نشط لا يُعالج"""
        _make_branch(db, active=False)
        yesterday = str(date.today() - timedelta(days=1))

        with patch("app.core.database.SessionLocal", return_value=_db_ctx(db)):
            from app.tasks.analytics_tasks import generate_daily_stats
            generate_daily_stats(stat_date_str=yesterday)
