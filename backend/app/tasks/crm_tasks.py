"""app/tasks/crm_tasks.py — CRM activity reminders + follow-ups"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.crm_tasks.activity_reminders",
    bind=True,
    max_retries=3,
)
def activity_reminders(self):
    """
    كل يوم 9 صباحاً — تذكير بالأنشطة المستحقة اليوم وغداً.
    """
    try:
        from app.core.database import SessionLocal          # noqa: PLC0415

        today = date.today()
        tomorrow = today + timedelta(days=1)

        with SessionLocal() as db:
            try:
                from app.modules.crm.models import Activity  # noqa: PLC0415
                from app.modules.hr.models import Employee  # noqa: PLC0415
                from wego_core.whatsapp.service import send_whatsapp_message  # noqa: PLC0415

                due_activities = (
                    db.query(Activity)
                    .filter(
                        Activity.due_date.in_([today, tomorrow]),
                        Activity.status == "pending",
                    )
                    .all()
                )

                for act in due_activities:
                    urgency = "اليوم" if act.due_date == today else "غداً"
                    logger.info(
                        "CRM activity reminder: id=%s type=%s customer=%s due=%s assigned=%s urgency=%s",
                        act.id, act.activity_type, act.customer_id,
                        act.due_date, act.assigned_to, urgency,
                    )
                    if act.assigned_to:
                        emp = db.query(Employee).filter(Employee.id == act.assigned_to).first()
                        if emp and emp.phone:
                            send_whatsapp_message(
                                emp.phone,
                                f"تذكير: نشاط CRM ({act.activity_type}) مستحق {urgency} — عميل #{act.customer_id}.",
                            )

                logger.info("CRM reminders sent: %s", len(due_activities))

            except ImportError:
                logger.debug("CRM module not yet built — skipped")

    except Exception as exc:
        logger.error("crm activity_reminders failed: %s", exc)
        raise self.retry(exc=exc, countdown=300)


@celery_app.task(
    name="app.tasks.crm_tasks.overdue_activities_alert",
    bind=True,
)
def overdue_activities_alert(self):
    """
    كل يوم 10 صباحاً — تنبيه بالأنشطة المتأخرة للمديرين.
    """
    try:
        from app.core.database import SessionLocal          # noqa: PLC0415

        today = date.today()

        with SessionLocal() as db:
            try:
                from app.modules.crm.models import Activity  # noqa: PLC0415

                overdue = (
                    db.query(Activity)
                    .filter(
                        Activity.due_date < today,
                        Activity.status == "pending",
                    )
                    .all()
                )

                if overdue:
                    logger.warning(
                        "CRM overdue activities: count=%s",
                        len(overdue),
                    )
                    for act in overdue:
                        logger.info(
                            "Overdue: id=%s type=%s customer=%s due=%s assigned=%s",
                            act.id, act.activity_type, act.customer_id,
                            act.due_date, act.assigned_to,
                        )
                    from wego_core.whatsapp.service import notify_admin  # noqa: PLC0415
                    notify_admin(f"تنبيه CRM: فيه {len(overdue)} نشاط متأخر محتاج متابعة.")

            except ImportError:
                logger.debug("CRM module not yet built — skipped")

    except Exception as exc:
        logger.error("crm overdue_activities_alert failed: %s", exc)


@celery_app.task(
    name="app.tasks.crm_tasks.birthday_greetings",
    bind=True,
)
def birthday_greetings(self):
    """
    كل يوم 8 صباحاً — يُرسل تهاني أعياد الميلاد للعملاء.
    """
    try:
        from app.core.database import SessionLocal          # noqa: PLC0415

        today = date.today()

        with SessionLocal() as db:
            try:
                from app.modules.crm.models import Customer  # noqa: PLC0415
                from wego_core.whatsapp.service import send_whatsapp_message  # noqa: PLC0415

                birthdays = (
                    db.query(Customer)
                    .filter(
                        Customer.is_active.is_(True),
                        Customer.blacklisted.is_(False),
                        # مقارنة الشهر واليوم فقط
                        Customer.birthday.isnot(None),
                    )
                    .all()
                )

                sent = 0
                for customer in birthdays:
                    if (
                        customer.birthday
                        and customer.birthday.month == today.month
                        and customer.birthday.day == today.day
                    ):
                        logger.info(
                            "Birthday greeting: customer=%s name=%s phone=%s",
                            customer.id, customer.full_name, customer.phone,
                        )
                        if customer.phone:
                            send_whatsapp_message(
                                customer.phone,
                                f"عيد ميلاد سعيد يا {customer.full_name}! 🎉 كل سنة وحضرتك طيب من كل أسرة الخيمة بيتش.",
                            )
                        sent += 1

                logger.info("Birthday greetings sent: %s", sent)

            except ImportError:
                logger.debug("CRM module not yet built — skipped")

    except Exception as exc:
        logger.error("crm birthday_greetings failed: %s", exc)
