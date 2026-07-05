"""tests/test_tasks/test_analytics_tasks.py"""
from __future__ import annotations

from datetime import date, datetime, timedelta
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

    def test_restaurant_covers_reflects_real_guest_counts(self, db):
        """باج حقيقي (اتصلح 2026-07-05): كان بيقرأ Order.covers (حقل مش
        موجود — الاسم الصح guests_count) فـ restaurant_covers كان صفر ثابت
        دايمًا بغض النظر عن عدد الضيوف الحقيقي في الطلبات المدفوعة. تست ده
        بيتأكد إن الرقم بيتحسب صح من guests_count الفعلي.

        ⚠️ استخدم datetime.utcnow().date() مش date.today(): Order.created_at
        بيتخزن بتوقيت UTC ساذج، و_build_stats بيبني حدود اليوم مباشرة من
        stat_date على إنه يوم UTC. date.today() بيرجع تاريخ التوقيت المحلي
        لنظام التشغيل (هنا Africa/Cairo، +3) — قرب منتصف الليل بتوقيت
        القاهرة، اليوم المحلي بيبقى مختلف عن يوم الـ UTC فعليًا، فالطلب
        اللي اتعمل دلوقتي (created_at بتوقيت UTC) يقع بره حدود اليوم اللي
        الاختبار بيسأل عنه (اليوم المحلي). ده باج في الاختبار نفسه، مش في
        الكود المُختبَر — اتكشف فعليًا لما الوقت عدّى منتصف الليل بتوقيت
        القاهرة أثناء تشغيل هذه الجلسة."""
        from app.modules.analytics.models import DailyStats
        from tests.test_api.test_pms import make_branch
        from tests.test_api.test_restaurant import make_menu_item, make_order
        from app.modules.restaurant import services

        branch = make_branch(db)
        item = make_menu_item(db, branch)

        order1 = make_order(db, branch, item)  # guests_count=2 (helper default)
        order2 = make_order(db, branch, item)  # guests_count=2
        services.update_order_status(db, order1.id, "in_kitchen")
        services.update_order_status(db, order1.id, "paid")
        services.update_order_status(db, order2.id, "in_kitchen")
        services.update_order_status(db, order2.id, "paid")

        stat_date = datetime.utcnow().date()
        _build_stats(db, branch.id, stat_date)

        row = db.query(DailyStats).filter(
            DailyStats.branch_id == branch.id,
            DailyStats.stat_date == stat_date,
        ).first()
        assert row.restaurant_covers == 4  # 2 + 2, not 0
