"""
tests/test_engines/test_timezone_utils.py
اختبارات app/resort_os/timezone_utils.py — كانت 0% تغطية بالكامل رغم استخدامها
فعليًا في restaurant/cafe/analytics (فلترة "طلبات اليوم"، local_date_to_utc_range).

business_today() أضيفت في التايم شير (حساب "اليوم" للوحة CS، تحديد الأقساط
المتأخرة، وتذكيرات الواتساب) — نفس فئة باج توقيت تذاكر المطبخ (KDS).

local_today() أضيفت بعد باج حقيقي حي (2026-07-05): HR attendance (punch-in/
punch-out) كان بيستخدم date.today() مباشرة، اللي بيثق في توقيت نظام تشغيل
السيرفر مش توقيت المنتجع (Africa/Cairo) الصريح — سيرفر UTC هيسجّل حضور
موظف بعد منتصف الليل بتوقيت القاهرة على تاريخ اليوم اللي فات.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.resort_os import timezone_utils as tzu
from app.resort_os.timezone_utils import business_today, local_date_to_utc_range, utc_naive_to_local_date


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

    def test_cairo_midday_maps_to_expected_utc_window(self):
        start, end = tzu.local_date_to_utc_range(date(2026, 7, 5), "Africa/Cairo")
        # Africa/Cairo = UTC+3 في الصيف (EEST) — منتصف ليل القاهرة = 21:00 UTC اليوم السابق
        assert start == datetime(2026, 7, 4, 21, 0, 0)
        assert end.date() == date(2026, 7, 5)
        assert start < end


class TestUtcNaiveToLocalDate:

    def test_round_trips_with_local_date_to_utc_range(self):
        """تحويل يوم محلي → UTC ثم رجوع لنفس اليوم المحلي لازم يطابق تمامًا،
        لأي نقطة داخل مدى اليوم (بداية، منتصف، نهاية)."""
        start, end = local_date_to_utc_range(date(2026, 7, 5), "Africa/Cairo")
        assert utc_naive_to_local_date(start, "Africa/Cairo") == date(2026, 7, 5)
        assert utc_naive_to_local_date(end, "Africa/Cairo") == date(2026, 7, 5)

    def test_utc_evening_maps_to_next_cairo_day(self):
        # 21:30 UTC = 00:30 بتوقيت القاهرة (UTC+3) اليوم التالي
        utc_dt = datetime(2026, 7, 5, 21, 30)
        assert utc_naive_to_local_date(utc_dt, "Africa/Cairo") == date(2026, 7, 6)

    def test_utc_morning_stays_same_cairo_day(self):
        utc_dt = datetime(2026, 7, 5, 10, 0)
        assert utc_naive_to_local_date(utc_dt, "Africa/Cairo") == date(2026, 7, 5)


class TestLocalToday:

    def test_local_today_matches_tz_aware_now(self):
        """تحقق أساسي: النتيجة تطابق التاريخ الفعلي بتوقيت المنطقة المطلوبة."""
        expected = datetime.now(ZoneInfo("Africa/Cairo")).date()
        assert tzu.local_today("Africa/Cairo") == expected

    def test_local_today_uses_cairo_calendar_day_not_utc(self, monkeypatch):
        """⚠️ السيناريو الحقيقي اللي كشف الباج: الساعة 23:30 UTC يوم 2026-07-05
        هي بالظبط 02:30 بتوقيت القاهرة (UTC+3 صيفًا) يوم 2026-07-06 — يوم
        تقويمي جديد فعلاً بتوقيت المنتجع. local_today لازم يرجّع 2026-07-06
        (اليوم القاهري الصحيح)، مش 2026-07-05 (لو اعتمدنا على UTC/توقيت سيرفر
        غير مضبوط على Africa/Cairo)."""
        fixed_utc = datetime(2026, 7, 5, 23, 30, tzinfo=timezone.utc)

        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_utc.astimezone(tz) if tz else fixed_utc

        monkeypatch.setattr(tzu, "datetime", FixedDateTime)
        assert tzu.local_today("Africa/Cairo") == date(2026, 7, 6)

    def test_local_today_just_before_cairo_midnight_stays_previous_day(self, monkeypatch):
        """تحقق من الاتجاه العكسي: لحظة قبل منتصف ليل القاهرة بشوية لازم تفضل
        نفس اليوم القديم، مش تقفز لليوم الجديد قبل وقتها."""
        # 2026-07-05 20:59 UTC = 2026-07-05 23:59 Africa/Cairo — لسه نفس اليوم
        fixed_utc = datetime(2026, 7, 5, 20, 59, tzinfo=timezone.utc)

        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_utc.astimezone(tz) if tz else fixed_utc

        monkeypatch.setattr(tzu, "datetime", FixedDateTime)
        assert tzu.local_today("Africa/Cairo") == date(2026, 7, 5)
