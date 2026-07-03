"""
app/celery_app.py
Celery worker — يستخدم app.core.kernel.worker.make_celery مباشرة
"""
from celery.schedules import crontab
from app.core.kernel.worker import make_celery

from app.core.config import settings

celery_app = make_celery(settings, app_name="resort_os")

# ── Periodic Tasks (Beat Schedule) ────────────────────────────────────────────
celery_app.conf.beat_schedule = {

    # ─── PMS ──────────────────────────────────────────────────────────
    "night-audit": {
        "task": "app.tasks.pms_tasks.run_night_audit",
        "schedule": crontab(hour=0, minute=1),       # كل يوم 00:01
    },
    "no-show-check": {
        "task": "app.tasks.pms_tasks.process_no_shows",
        "schedule": crontab(minute=0),               # كل ساعة
    },

    # ─── Finance ──────────────────────────────────────────────────────
    "check-due-reminders": {
        "task": "app.tasks.finance_tasks.check_due_reminders",
        "schedule": crontab(hour=9, minute=0),       # كل يوم 9 صباحاً
    },

    # ─── Timeshare ────────────────────────────────────────────────────
    "timeshare-mark-overdue": {
        "task": "app.tasks.timeshare_tasks.mark_overdue",
        "schedule": crontab(hour=2, minute=0),       # كل يوم 2 صباحاً
    },
    "timeshare-visit-reminders": {
        "task": "app.tasks.timeshare_tasks.send_visit_reminders",
        "schedule": crontab(hour=9, minute=0),
    },
    "timeshare-installment-reminders": {
        "task": "app.tasks.timeshare_tasks.send_installment_reminders",
        "schedule": crontab(hour=9, minute=15),
    },

    # ─── Leasing ──────────────────────────────────────────────────────
    "leasing-mark-overdue": {
        "task": "app.tasks.leasing_tasks.mark_overdue",
        "schedule": crontab(hour=2, minute=30),
    },
    "leasing-due-reminders": {
        "task": "app.tasks.leasing_tasks.send_due_reminders",
        "schedule": crontab(hour=9, minute=0),
    },

    # ─── Inventory ────────────────────────────────────────────────────
    "inventory-low-stock": {
        "task": "app.tasks.inventory_tasks.check_low_stock",
        "schedule": crontab(hour=7, minute=0),
    },

    # ─── Beach ────────────────────────────────────────────────────────
    "beach-reservation-no-show": {
        "task": "app.tasks.beach_tasks.process_reservation_no_shows",
        "schedule": crontab(hour=11, minute=5),      # بعد 11 صباحاً
    },

    # ─── HR ───────────────────────────────────────────────────────────
    "hr-mark-absent": {
        "task": "app.tasks.hr_tasks.mark_attendance_absent",
        "schedule": crontab(hour=23, minute=59),     # آخر اليوم
    },
    "hr-payroll-reminder": {
        "task": "app.tasks.hr_tasks.payroll_reminder",
        "schedule": crontab(hour=10, minute=0, day_of_month="28-31"),
    },
    "hr-accrue-leave": {
        "task": "app.tasks.hr_tasks.accrue_leave_balances",
        "schedule": crontab(hour=0, minute=1, month_of_year=1, day_of_month=1),
    },
    "hr-weekly-rota": {
        "task": "app.tasks.hr_tasks.generate_weekly_rota",
        "schedule": crontab(hour=8, minute=0, day_of_week=5),  # الجمعة
    },

    # ─── Maintenance ──────────────────────────────────────────────────
    "maintenance-preventive": {
        "task": "app.tasks.maintenance_tasks.generate_preventive_tasks",
        "schedule": crontab(hour=6, minute=0),
    },
    "maintenance-overdue-alert": {
        "task": "app.tasks.maintenance_tasks.notify_overdue_work_orders",
        "schedule": crontab(hour=8, minute=0),
    },

    # ─── CRM ──────────────────────────────────────────────────────────
    "crm-activity-reminders": {
        "task": "app.tasks.crm_tasks.activity_reminders",
        "schedule": crontab(hour=9, minute=0),
    },
    "crm-overdue-activities": {
        "task": "app.tasks.crm_tasks.overdue_activities_alert",
        "schedule": crontab(hour=10, minute=0),
    },
    "crm-birthday-greetings": {
        "task": "app.tasks.crm_tasks.birthday_greetings",
        "schedule": crontab(hour=8, minute=0),
    },

    # ─── Analytics ────────────────────────────────────────────────────
    "analytics-daily-stats": {
        "task": "app.tasks.analytics_tasks.generate_daily_stats",
        "schedule": crontab(hour=1, minute=0),           # كل يوم 01:00 بعد Night Audit
    },

    # ─── Hub ──────────────────────────────────────────────────────────
    "sitemap-refresh": {
        "task": "app.tasks.hub_tasks.refresh_sitemap",
        "schedule": crontab(hour=3, minute=0),
    },
    "hub-expire-offers": {
        "task": "app.tasks.hub_tasks.expire_old_offers",
        "schedule": crontab(hour=0, minute=5),
    },
    "hub-pending-bookings-reminder": {
        "task": "app.tasks.hub_tasks.process_pending_bookings_reminder",
        "schedule": crontab(hour=10, minute=0),
    },
}

celery_app.conf.timezone = settings.TIMEZONE

# ── Task Registration ─────────────────────────────────────────────────────────
# app/tasks/__init__.py auto-imports every *_tasks.py module in the package via
# pkgutil, so every @celery_app.task registers itself — no manual per-file
# import to remember when adding a new task module.
import app.tasks  # noqa: F401,E402
