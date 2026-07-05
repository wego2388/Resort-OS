"""app/resort_os/timezone_utils.py — تحويل تاريخ محلي (توقيت المنتجع) لمدى UTC.

كل الأعمدة الزمنية بالداتابيز (created_at وغيرها) مخزّنة UTC naive
(server_default=func.now()). فلترة "طلبات اليوم" بمقارنة date.today() المحلي
مباشرة مع created_at كان بيفشل فعليًا لمدة ~3 ساعات كل يوم (نافذة ما بين
منتصف ليل UTC ومنتصف ليل توقيت القاهرة، UTC+3) — طلب اتعمل الساعة 00:30
بتوقيت القاهرة كان created_at بتاعه لسه اليوم اللي فات بتوقيت UTC، فمرشّح
"اليوم" كان بيرجّع صفر نتائج له. Pure Python، بدون FastAPI/SQLAlchemy.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo


def business_today(tz_name: str) -> date:
    """تاريخ "النهاردة" بتوقيت المنتجع (tz_name)، مش توقيت نظام تشغيل السيرفر.

    `date.today()` العادية بترجع تاريخ اليوم بتوقيت السيرفر المحلي — لو السيرفر
    شغّال بتوقيت مختلف عن توقيت المنتجع (Africa/Cairo)، بيبقى فيه نافذة كل يوم
    (بمقدار فرق التوقيتين، عادةً 2-3 ساعات) بيرجع فيها تاريخ غلط بيوم كامل. نفس
    فئة الباج اللي ظهرت في تذاكر المطبخ (KDS) — هنا بتأثّر على "الأيام المتبقية
    للزيارة القادمة"، تحديد القسط "المتأخر"، وتوقيت تذكيرات الواتساب."""
    return datetime.now(ZoneInfo(tz_name)).date()


def local_date_to_utc_range(local_date: date, tz_name: str) -> tuple[datetime, datetime]:
    """يرجّع (بداية، نهاية) اليوم المحلي بتوقيت tz_name، محوّلين لـ UTC naive —
    نفس تمثيل created_at المخزّن بالداتابيز.

    مثال: توقيت Africa/Cairo (UTC+3)، local_date=2026-07-05 → المدى الناتج
    يبدأ 2026-07-04 21:00:00 UTC (= منتصف ليل القاهرة) لحد
    2026-07-05 20:59:59.999999 UTC.
    """
    tz = ZoneInfo(tz_name)
    start_local = datetime.combine(local_date, time.min, tzinfo=tz)
    end_local = datetime.combine(local_date, time.max, tzinfo=tz)
    start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, end_utc


def local_now(tz_name: str) -> datetime:
    """اللحظة الحالية بتوقيت المنتجع (tz_name) — بديل عن datetime.utcnow()/
    datetime.now() اللي بترجع توقيت السيرفر (UTC غالبًا في الإنتاج). استخدمها
    أي مكان بيحتاج يعرف الساعة المحلية الحقيقية (مثال: مقارنة "وصل الساعة كام
    بتوقيت القاهرة" قبل ما نعتبر حجز no-show)."""
    return datetime.now(ZoneInfo(tz_name))


def local_today(tz_name: str) -> date:
    """تاريخ اليوم بتوقيت المنتجع (tz_name) — بديل عن date.today() اللي بترجع
    تاريخ السيرفر (UTC غالبًا في الإنتاج). نفس فئة الباج ظهرت في أكتر من مكان
    مستقل: Night Audit وقيد إيراد الغرف عند الخروج وكشف الحجوزات no-show
    (PMS)، وحضور/انصراف الموظفين (HR) — موظف بيسجّل حضور الساعة 00:30 بتوقيت
    القاهرة (يعني 21:30-22:30 UTC اليوم اللي فات) كان بيتسجّل على تاريخ اليوم
    اللي فات لو السيرفر UTC، يوم كامل غلط في سجل الحضور ومينفعش يتصحح غير
    يدويًا. الحل: احسب "النهاردة" دايمًا من توقيت المنتجع الصريح
    (settings.TIMEZONE)، مش من توقيت نظام تشغيل السيرفر."""
    return local_now(tz_name).date()
