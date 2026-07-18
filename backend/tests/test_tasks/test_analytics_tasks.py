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

    def test_beach_revenue_and_visitors_reflect_real_transactions(self, db):
        """باج حقيقي (اتصلح): _build_stats كان بيقرا BeachTransaction.visit_date
        و t.total_paid — حقلين مش موجودين خالص في الموديل الحقيقي (الأسماء
        الصح tx_date و total_amount+vat_amount). الاستعلام كان بيرمي
        AttributeError عند بناء الـ filter، وده كان بيتبلع بصمت بـ
        except Exception، يعني beach_visitors/beach_revenue في كل DailyStats
        كانوا صفر ثابت من أول يوم — بغض النظر عن أي مبيعات شاطئ حقيقية. تست
        ده بيتأكد إن الرقم بيتحسب صح من معاملة شاطئ حقيقية مدفوعة (مستبعد
        منها العملية الملغاة)."""
        from app.modules.analytics.models import DailyStats
        from app.modules.beach import services as beach_services
        from app.modules.beach.schemas import BeachSellRequest
        from tests.test_api.test_pms import make_branch

        branch = make_branch(db)
        stat_date = date.today()

        tx1 = beach_services.sell_ticket(
            db, branch.id,
            BeachSellRequest(tx_type="entry", quantity=1),
            tx_date=stat_date,
        )
        tx2 = beach_services.sell_ticket(
            db, branch.id,
            BeachSellRequest(tx_type="entry", quantity=1),
            tx_date=stat_date,
        )
        # معاملة ملغاة — لازم تُستبعد من الإيراد والعدد (زي أي مكان تاني بيحسب
        # إيراد الشاطئ في النظام)
        voided = beach_services.sell_ticket(
            db, branch.id,
            BeachSellRequest(tx_type="entry", quantity=1),
            tx_date=stat_date,
        )
        beach_services.void_transaction(db, voided.id, voided_by=1, reason="اختبار")

        expected_revenue = (tx1.total_amount + tx1.vat_amount) + (tx2.total_amount + tx2.vat_amount)

        _build_stats(db, branch.id, stat_date)

        row = db.query(DailyStats).filter(
            DailyStats.branch_id == branch.id,
            DailyStats.stat_date == stat_date,
        ).first()
        assert row.beach_visitors == 2  # مش 0، ومش 3 (الملغاة مستبعدة)
        assert row.beach_revenue == expected_revenue

    def test_restaurant_revenue_captures_early_morning_cairo_order(self, db):
        """باج حقيقي (اتصلح): day_start/day_end كانوا بيتبنوا بـ
        datetime.combine ساذج من stat_date مباشرة (كأنه يوم UTC)، لكن
        DiningOrder.created_at متخزّن UTC فعليًا بينما stat_date تاريخ محلي
        (Africa/Cairo، +3). النتيجة: طلب اتعمل الساعة 00:30 بتوقيت القاهرة
        (created_at UTC = 21:30 اليوم اللي فات) كان بيقع بره حدود يوم
        DailyStats الصح (لأن الحدود الساذجة كانت بتبدأ من منتصف ليل UTC، مش
        منتصف ليل القاهرة) — يعني إيراد الصبح الباكر كان بيضيع من إحصائية
        اليوم الصح. تست ده بيبني الطلب بتوقيت 00:30 القاهرة صراحة (بدل ما
        يعتمد على وقت تشغيل التست الفعلي) عشان يثبت الحدود بقت صح دايمًا.

        راجع DINING_CUTOVER_PLAN.md D-05 — _build_stats بقى بيقرا من
        dining.DiningOrder بدل restaurant.Order مباشرة."""
        from datetime import datetime, timedelta as _td
        from zoneinfo import ZoneInfo
        from app.modules.analytics.models import DailyStats
        from app.modules.dining import services
        from app.modules.dining.models import DiningOrder
        from tests.test_api.test_dining import make_branch, make_finance_accounts, make_item, make_order, make_outlet

        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item)
        services.update_order_status(db, order.id, "in_kitchen")
        services.update_order_status(db, order.id, "paid")

        # الطلب "فعليًا" اتعمل الساعة 00:30 بتوقيت القاهرة يوم stat_date —
        # بمعنى created_at (UTC) لازم يبقى 21:30 يوم stat_date - 1
        stat_date = date.today()
        cairo_early_morning = datetime.combine(stat_date, datetime.min.time(), tzinfo=ZoneInfo("Africa/Cairo")) + _td(minutes=30)
        db.query(DiningOrder).filter(DiningOrder.id == order.id).update({
            "created_at": cairo_early_morning.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
        })
        db.commit()

        _build_stats(db, branch.id, stat_date)

        row = db.query(DailyStats).filter(
            DailyStats.branch_id == branch.id,
            DailyStats.stat_date == stat_date,
        ).first()
        assert row.restaurant_revenue == order.total  # مش 0 — الطلب لازم يتحسب في يومه الصح بتوقيت القاهرة

    def test_restaurant_covers_reflects_real_guest_counts(self, db):
        """باج حقيقي (اتصلح 2026-07-05): كان بيقرأ Order.covers (حقل مش
        موجود — الاسم الصح guests_count) فـ restaurant_covers كان صفر ثابت
        دايمًا بغض النظر عن عدد الضيوف الحقيقي في الطلبات المدفوعة. تست ده
        بيتأكد إن الرقم بيتحسب صح من guests_count الفعلي.

        ⚠️ باج تاني في التست ده نفسه اتكشف 2026-07-08: كان بيستخدم
        datetime.utcnow().date() لـ stat_date، بس _build_stats الحالية
        بتبني حدود اليوم بـ local_date_to_utc_range(stat_date, TIMEZONE) —
        يعني بتتعامل مع stat_date على إنه يوم محلي (القاهرة)، مش يوم UTC.
        تمرير تاريخ UTC هنا كان بيعمل إزاحة 3 ساعات غلط قرب منتصف الليل
        بتوقيت القاهرة (~21:00-24:00 UTC) — بالظبط الوقت اللي الباج اتكشف
        فيه فعليًا وقت تشغيل الجلسة دي. الحل: local_today(TIMEZONE)، نفس
        التحويل اللي _build_stats بتتوقعه فعليًا (راجع §13 CLAUDE.md).

        راجع DINING_CUTOVER_PLAN.md D-05 — dining.DiningOrder.guests_count
        بدل restaurant.Order.guests_count."""
        from app.modules.analytics.models import DailyStats
        from app.core.config import settings
        from app.resort_os.timezone_utils import local_today
        from app.modules.dining import services
        from tests.test_api.test_dining import make_branch, make_finance_accounts, make_item, make_order, make_outlet

        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        item = make_item(db, branch, outlet)

        order1 = make_order(db, branch, outlet, item)  # guests_count=2 (helper default)
        order2 = make_order(db, branch, outlet, item)  # guests_count=2
        services.update_order_status(db, order1.id, "in_kitchen")
        services.update_order_status(db, order1.id, "paid")
        services.update_order_status(db, order2.id, "in_kitchen")
        services.update_order_status(db, order2.id, "paid")

        stat_date = local_today(settings.TIMEZONE)
        _build_stats(db, branch.id, stat_date)

        row = db.query(DailyStats).filter(
            DailyStats.branch_id == branch.id,
            DailyStats.stat_date == stat_date,
        ).first()
        assert row.restaurant_covers == 4  # 2 + 2, not 0
