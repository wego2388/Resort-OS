"""
tests/test_engines/test_timezone_utils.py
اختبارات app/resort_os/timezone_utils.py — كانت 0% تغطية بالكامل رغم استخدامها
فعليًا في restaurant/cafe (فلترة "طلبات اليوم"). أضيفت هنا كأثر جانبي لإضافة
business_today() (نفس فئة باج توقيت تذاكر المطبخ — استُخدم في التايم شير
لحساب "اليوم" في لوحة CS، تحديد الأقساط المتأخرة، وتذكيرات الواتساب).
"""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.resort_os.timezone_utils import business_today, local_date_to_utc_range


class TestBusinessToday:

    def test_returns_a_date(self):
        assert isinstance(business_today("Africa/Cairo"), date)

    def test_differs_from_utc_near_midnight_boundary(self):
        """اللحظة الحرجة: 00:30 بتوقيت القاهرة (UTC+2/+3) بتوافق لسه يوم أمس
        بتوقيت UTC — business_today لازم يرجّع تاريخ القاهرة (اليوم الجديد)،
        مش تاريخ UTC (اللي لسه اليوم القديم)."""
        # 2026-07-06 00:30 بتوقيت القاهرة = 2026-07-05 21:30 أو 22:30 UTC
        cairo_midnight_thirty = datetime(2026, 7, 6, 0, 30, tzinfo=ZoneInfo("Africa/Cairo"))
        utc_equivalent = cairo_midnight_thirty.astimezone(ZoneInfo("UTC"))
        assert utc_equivalent.date() == date(2026, 7, 5)  # UTC لسه في اليوم القديم

        with patch("app.resort_os.timezone_utils.datetime") as mock_dt:
            mock_dt.now.return_value = cairo_midnight_thirty
            result = business_today("Africa/Cairo")
        assert result == date(2026, 7, 6)  # القاهرة دخلت اليوم الجديد فعليًا


class TestLocalDateToUtcRange:

    def test_range_covers_full_local_day(self):
        start, end = local_date_to_utc_range(date(2026, 7, 5), "Africa/Cairo")
        assert start < end
        assert (end - start).total_seconds() < 24 * 3600 + 1

    def test_range_is_naive_utc(self):
        start, end = local_date_to_utc_range(date(2026, 7, 5), "Africa/Cairo")
        assert start.tzinfo is None
        assert end.tzinfo is None
