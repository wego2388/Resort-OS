"""app/tasks/timeshare_tasks.py — Timeshare overdue + visit reminders

⚠️ كل الـ 3 tasks هنا كانت بتستخدم date.today() (توقيت السيرفر المحلي) بدل
توقيت المنتجع (Africa/Cairo) — نفس فئة باج توقيت تذاكر المطبخ (KDS). لو
السيرفر شغّال بتوقيت مختلف (مثلاً UTC)، فيه نافذة كل يوم (~2-3 ساعات) كان
ممكن يعتبر فيها قسط مستحق "النهاردة" لسه مش متأخر، أو يبعت تذكير زيارة بيوم
غلط. بقى بيستخدم business_today(settings.TIMEZONE)."""
from __future__ import annotations

import logging
from datetime import date

from app.celery_app import celery_app
from app.core.config import settings
from app.core.kernel.worker import notify_task_failure
from app.resort_os.timezone_utils import business_today

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.timeshare_tasks.mark_overdue", bind=True, max_retries=3)
def mark_overdue(self):
    """
    كل يوم 2 صباحاً — يُحدّث الأقساط المتأخرة ويُجمّد حقوق الحجز.
    """
    try:
        from app.core.database import SessionLocal  # noqa: PLC0415
        today = business_today(settings.TIMEZONE)

        with SessionLocal() as db:
            try:
                overdue_count = _mark_overdue(db, today)
                db.commit()
                logger.info("Timeshare overdue processed: count=%s", overdue_count)
            except ImportError:
                logger.debug("Timeshare module not yet built — skipped")

    except Exception as exc:
        logger.error("timeshare mark_overdue failed: %s", exc)
        raise self.retry(exc=exc, countdown=600)


def _mark_overdue(db, today: date) -> int:
    """
    الجزء القابل للاختبار: يُحدِّث حالة الأقساط ومستحقات الصيانة المتأخرة إلى
    overdue ثم يُجمِّد حق الحجز (booking_frozen) لأي عقد نشط عنده أي متأخرات
    من النوعين — نفس آلية should_freeze_booking الموجودة، بس على رصيد مجمّع
    من الأقساط + الصيانة مع بعض بدل الأقساط لوحدها.

    ⚠️ لا تستخدم `contract.installments` هنا — ده عمود عدد الأقساط (int)،
    العلاقة الصحيحة هي `contract.installments_list`.
    """
    from app.modules.timeshare.models import (  # noqa: PLC0415
        TimeshareInstallment, TimeshareMaintenanceDue, TimeshareContract,
    )
    from app.resort_os.timeshare_engine import should_freeze_booking  # noqa: PLC0415
    from decimal import Decimal  # noqa: PLC0415

    # تحديث الأقساط المتأخرة — بما فيها اللي سُدِّدت جزئياً (partial) ولسه متأخرة،
    # وإلا القسط ده مش هيتحسب أبداً في overdue_total تحت (اللي بيفلتر status=="overdue"
    # بس)، فعقد فيه قسط مدفوع جزئياً ومتأخر ميتجمّدش حقه في الحجز رغم إنه متأخر فعلاً.
    overdue_insts = (
        db.query(TimeshareInstallment)
        .filter(
            TimeshareInstallment.due_date < today,
            TimeshareInstallment.status.in_(["pending", "partial"]),
        )
        .all()
    )
    for inst in overdue_insts:
        inst.status = "overdue"

    # نفس المنطق بالظبط على مستحقات الصيانة السنوية
    overdue_dues = (
        db.query(TimeshareMaintenanceDue)
        .filter(
            TimeshareMaintenanceDue.due_date < today,
            TimeshareMaintenanceDue.status.in_(["pending", "partial"]),
        )
        .all()
    )
    for due in overdue_dues:
        due.status = "overdue"

    # حساب المبالغ المتأخرة (أقساط + صيانة) لكل عقد وتجميد الحجز
    contracts = db.query(TimeshareContract).filter(
        TimeshareContract.status == "active"
    ).all()
    for contract in contracts:
        overdue_total = (
            sum((i.amount for i in contract.installments_list if i.status == "overdue"), Decimal("0"))
            + sum((d.amount for d in contract.maintenance_dues_list if d.status == "overdue"), Decimal("0"))
        )
        if should_freeze_booking(overdue_total):
            contract.booking_frozen = True

    return len(overdue_insts) + len(overdue_dues)


@celery_app.task(name="app.tasks.timeshare_tasks.generate_annual_maintenance_dues", bind=True, max_retries=3)
def generate_annual_maintenance_dues(self):
    """
    كل 1 يناير — يولّد مستحق صيانة واحد لكل عقد نشط عنده maintenance_fee > 0
    للسنة التقويمية الجديدة (fee_year = السنة الحالية بتوقيت المنتجع). قابل
    لإعادة التشغيل يدويًا من POST /timeshare/maintenance-dues/generate (نفس
    نمط run_night_audit في PMS).
    """
    try:
        from app.core.database import SessionLocal  # noqa: PLC0415
        today = business_today(settings.TIMEZONE)

        with SessionLocal() as db:
            try:
                from app.modules.core.models import Branch  # noqa: PLC0415
                created_total = 0
                for (branch_id,) in db.query(Branch.id).all():
                    created_total += _generate_annual_maintenance_dues(db, branch_id, today.year)
                db.commit()
                logger.info(
                    "Annual maintenance dues generated: fee_year=%s created=%s",
                    today.year, created_total,
                )
            except ImportError:
                logger.debug("Timeshare module not yet built — skipped")

    except Exception as exc:
        logger.error("generate_annual_maintenance_dues failed: %s", exc)
        notify_task_failure("app.tasks.timeshare_tasks.generate_annual_maintenance_dues", exc)
        raise self.retry(exc=exc, countdown=600)


def _generate_annual_maintenance_dues(db, branch_id: int, fee_year: int) -> int:
    """الجزء القابل للاختبار والقابل لإعادة الاستخدام من services.
    generate_annual_maintenance_dues — لكل عقد active بـ maintenance_fee > 0
    في الفرع ده: يولّد مستحق واحد لسنة fee_year لو مش موجود بالفعل
    (idempotent — UniqueConstraint(contract_id, fee_year) هي الحارس النهائي،
    الفحص هنا بيتفادى IntegrityError مزعج في اللوج عند إعادة التشغيل)."""
    from decimal import Decimal  # noqa: PLC0415
    from app.modules.timeshare.models import TimeshareContract, TimeshareMaintenanceDue  # noqa: PLC0415

    contracts = db.query(TimeshareContract).filter(
        TimeshareContract.branch_id == branch_id,
        TimeshareContract.status == "active",
        TimeshareContract.maintenance_fee > Decimal("0"),
    ).all()

    existing_pairs = {
        contract_id for (contract_id,) in db.query(TimeshareMaintenanceDue.contract_id).filter(
            TimeshareMaintenanceDue.fee_year == fee_year,
            TimeshareMaintenanceDue.contract_id.in_([c.id for c in contracts]),
        ).all()
    }

    created = 0
    for contract in contracts:
        if contract.id in existing_pairs:
            continue
        due = TimeshareMaintenanceDue(
            contract_id=contract.id, fee_year=fee_year,
            due_date=date(fee_year, 1, 1),
            amount=contract.maintenance_fee,
        )
        db.add(due)
        created += 1
    db.flush()
    return created


@celery_app.task(name="app.tasks.timeshare_tasks.send_visit_reminders", bind=True)
def send_visit_reminders(self):
    """
    كل يوم 9 صباحاً — يُرسل تذكير للزيارات القادمة خلال 3 أيام.

    مصدران للزيارات:
    ① عقود ثابتة (week_number محدد) — النافذة محسوبة رياضياً من timeshare_engine.
    ② عقود عائمة — زيارات مسجّلة فعلاً في timeshare_visits بـ status="scheduled"
       وcheck_in بعد 3 أيام بالضبط. كانت مستبعدة قبلاً بفلتر week_number.isnot(None)
       رغم إنها هي الأكثر احتياجاً للتذكير (موعدها مش ثابت كل سنة).
    """
    try:
        from app.core.database import SessionLocal  # noqa: PLC0415
        from datetime import timedelta              # noqa: PLC0415
        today = business_today(settings.TIMEZONE)
        reminder_day = today + timedelta(days=3)

        with SessionLocal() as db:
            try:
                from app.modules.timeshare.models import TimeshareContract, TimeshareVisit  # noqa: PLC0415
                from app.resort_os.timeshare_engine import (  # noqa: PLC0415
                    find_next_visit, should_send_visit_reminder,
                )
                from app.core.kernel.whatsapp import send_whatsapp_message  # noqa: PLC0415

                reminders_sent = 0

                # ① عقود ثابتة — النافذة المحسوبة رياضياً
                fixed_contracts = db.query(TimeshareContract).filter(
                    TimeshareContract.status == "active",
                    TimeshareContract.week_number.isnot(None),
                ).all()
                for c in fixed_contracts:
                    visit = find_next_visit(c.week_number, c.nights_per_year, today)
                    if visit and should_send_visit_reminder(visit):
                        logger.info(
                            "Visit reminder (fixed): contract=%s guest=%s visit_start=%s",
                            c.id, c.customer_name, visit.visit_start,
                        )
                        if c.customer_phone:
                            send_whatsapp_message(
                                c.customer_phone,
                                f"تذكير: زيارتك القادمة في الخيمة بيتش تبدأ يوم {visit.visit_start:%Y-%m-%d} — نتشرف باستقبالك.",
                            )
                        reminders_sent += 1

                # ② عقود عائمة — زيارات مسجّلة في قاعدة البيانات
                floating_visits = (
                    db.query(TimeshareVisit)
                    .join(TimeshareContract, TimeshareContract.id == TimeshareVisit.contract_id)
                    .filter(
                        TimeshareContract.status == "active",
                        TimeshareContract.week_number.is_(None),  # عائمة فقط
                        TimeshareVisit.status == "scheduled",
                        TimeshareVisit.check_in == reminder_day,
                    )
                    .all()
                )
                for v in floating_visits:
                    contract = v.contract
                    if contract is None:
                        continue
                    logger.info(
                        "Visit reminder (floating): visit=%s contract=%s guest=%s check_in=%s",
                        v.id, contract.id, contract.customer_name, v.check_in,
                    )
                    if contract.customer_phone:
                        send_whatsapp_message(
                            contract.customer_phone,
                            f"تذكير: زيارتك القادمة في الخيمة بيتش تبدأ يوم {v.check_in:%Y-%m-%d} — نتشرف باستقبالك.",
                        )
                    reminders_sent += 1

                logger.info("Visit reminders sent: fixed=%s floating=%s total=%s",
                            len(fixed_contracts), len(floating_visits), reminders_sent)

            except ImportError:
                logger.debug("Timeshare module not yet built — skipped")

    except Exception as exc:
        logger.error("send_visit_reminders failed: %s", exc)
        notify_task_failure("app.tasks.timeshare_tasks.send_visit_reminders", exc)


@celery_app.task(name="app.tasks.timeshare_tasks.send_installment_reminders", bind=True)
def send_installment_reminders(self):
    """
    كل يوم 9 صباحاً — تذكير الأقساط المستحقة خلال 7 أيام.
    """
    try:
        from app.core.database import SessionLocal  # noqa: PLC0415
        from datetime import timedelta              # noqa: PLC0415
        today = business_today(settings.TIMEZONE)
        remind_date = today + timedelta(days=7)

        with SessionLocal() as db:
            try:
                from app.modules.timeshare.models import TimeshareInstallment  # noqa: PLC0415

                from app.modules.timeshare.models import TimeshareContract  # noqa: PLC0415
                from app.core.kernel.whatsapp import send_whatsapp_message  # noqa: PLC0415

                due_soon = (
                    db.query(TimeshareInstallment)
                    .filter(
                        TimeshareInstallment.due_date == remind_date,
                        TimeshareInstallment.status == "pending",
                    )
                    .all()
                )
                for inst in due_soon:
                    logger.info(
                        "Installment reminder: id=%s amount=%s due=%s",
                        inst.id, inst.amount, inst.due_date,
                    )
                    contract = db.query(TimeshareContract).filter(
                        TimeshareContract.id == inst.contract_id
                    ).first()
                    if contract and contract.customer_phone:
                        send_whatsapp_message(
                            contract.customer_phone,
                            f"تذكير: قسط بقيمة {inst.amount:,.2f} ج.م مستحق يوم {inst.due_date:%Y-%m-%d} — عقد رقم {contract.contract_number}.",
                        )

            except ImportError:
                pass

    except Exception as exc:
        logger.error("send_installment_reminders failed: %s", exc)
        notify_task_failure("app.tasks.timeshare_tasks.send_installment_reminders", exc)


@celery_app.task(name="app.tasks.timeshare_tasks.send_maintenance_due_reminders", bind=True)
def send_maintenance_due_reminders(self):
    """
    كل يوم 9:30 صباحاً — تذكير رسوم الصيانة السنوية المستحقة خلال 7 أيام.

    ⚠️ فجوة حقيقية كانت هنا (2026-08-03): الأقساط ليها تذكير واتساب قبل
    الاستحقاق بـ7 أيام (send_installment_reminders فوق)، لكن رسوم الصيانة
    (اللي بتجمّد حق الحجز فعليًا لو اتأخرت — راجع mark_overdue) مالهاش أي
    تذكير قبلي خالص — أول تواصل مع العميل كان بيحصل بعد التجميد فعليًا،
    مش قبله. نفس شكل send_installment_reminders بالظبط.
    """
    try:
        from app.core.database import SessionLocal  # noqa: PLC0415
        from datetime import timedelta              # noqa: PLC0415
        today = business_today(settings.TIMEZONE)
        remind_date = today + timedelta(days=7)

        with SessionLocal() as db:
            try:
                from app.modules.timeshare.models import TimeshareMaintenanceDue  # noqa: PLC0415
                from app.modules.timeshare.models import TimeshareContract  # noqa: PLC0415
                from app.core.kernel.whatsapp import send_whatsapp_message  # noqa: PLC0415

                due_soon = (
                    db.query(TimeshareMaintenanceDue)
                    .filter(
                        TimeshareMaintenanceDue.due_date == remind_date,
                        TimeshareMaintenanceDue.status == "pending",
                    )
                    .all()
                )
                for due in due_soon:
                    logger.info(
                        "Maintenance due reminder: id=%s amount=%s due=%s",
                        due.id, due.amount, due.due_date,
                    )
                    contract = db.query(TimeshareContract).filter(
                        TimeshareContract.id == due.contract_id
                    ).first()
                    if contract and contract.customer_phone:
                        send_whatsapp_message(
                            contract.customer_phone,
                            f"تذكير: رسوم صيانة بقيمة {due.amount:,.2f} ج.م مستحقة يوم {due.due_date:%Y-%m-%d} "
                            f"— عقد رقم {contract.contract_number}. سدادها في الموعد يحافظ على حقك في الحجز.",
                        )

            except ImportError:
                pass

    except Exception as exc:
        logger.error("send_maintenance_due_reminders failed: %s", exc)
        notify_task_failure("app.tasks.timeshare_tasks.send_maintenance_due_reminders", exc)


@celery_app.task(name="app.tasks.timeshare_tasks.send_contract_expiry_reminders", bind=True)
def send_contract_expiry_reminders(self):
    """
    كل يوم 9:45 صباحاً — تذكير قبل انتهاء مدة العقد بـ30 يوم.

    مقصور عمدًا على عقود end_date مضبوط صراحة — years_count الافتراضي 99
    سنة (ملكية شبه دائمة) يعني end_date فاضي غالبًا لمعظم العقود، ومفيش
    داعي لتنبيه انتهاء لعقد زي ده. نفس شكل التذكيرات التانية بالظبط —
    مطابقة تاريخ واحد بالظبط (end_date == اليوم+30) عشان الرسالة تتبعت
    مرة واحدة بس، مش كل يوم طول الشهر الأخير.
    """
    try:
        from app.core.database import SessionLocal  # noqa: PLC0415
        from datetime import timedelta              # noqa: PLC0415
        today = business_today(settings.TIMEZONE)
        remind_date = today + timedelta(days=30)

        with SessionLocal() as db:
            try:
                from app.modules.timeshare.models import TimeshareContract  # noqa: PLC0415
                from app.core.kernel.whatsapp import send_whatsapp_message  # noqa: PLC0415

                expiring_soon = (
                    db.query(TimeshareContract)
                    .filter(
                        TimeshareContract.end_date == remind_date,
                        TimeshareContract.status == "active",
                    )
                    .all()
                )
                for contract in expiring_soon:
                    logger.info(
                        "Contract expiry reminder: id=%s end_date=%s",
                        contract.id, contract.end_date,
                    )
                    if contract.customer_phone:
                        send_whatsapp_message(
                            contract.customer_phone,
                            f"تنبيه: مدة عقد الملكية الجزئية رقم {contract.contract_number} بتنتهي يوم "
                            f"{contract.end_date:%Y-%m-%d} — كلّم خدمة العملاء لمناقشة التجديد أو أي استفسار.",
                        )

            except ImportError:
                pass

    except Exception as exc:
        logger.error("send_contract_expiry_reminders failed: %s", exc)
        notify_task_failure("app.tasks.timeshare_tasks.send_contract_expiry_reminders", exc)


@celery_app.task(name="app.tasks.timeshare_tasks.send_visit_survey", bind=True, max_retries=3)
def send_visit_survey(self, visit_id: int, branch_id: int):
    """
    يُستدعى عند الطلب (مش scheduled) من POST
    /analytics/reviews/survey-token/timeshare/{visit_id}/send — بيولّد
    survey token حقيقي (create_survey_token) ويبعته لصاحب الملكية الجزئية عبر
    واتساب. قبل الـ endpoint/task ده، الـ token كان بيتولّد فقط عن طريق
    GET .../survey-token/timeshare/{visit_id} من غير أي طريقة حقيقية توصّله
    للضيف — يعني الاستبيان كان عمليًا غير قابل للاستخدام رغم إن الباك إند
    والفرونت إند (SurveyView.vue) كانوا شغالين بالكامل.
    """
    try:
        from app.core.database import SessionLocal  # noqa: PLC0415

        with SessionLocal() as db:
            from app.modules.timeshare.models import TimeshareVisit  # noqa: PLC0415
            from app.modules.analytics.services import create_survey_token  # noqa: PLC0415
            from app.core.kernel.whatsapp import send_whatsapp_message  # noqa: PLC0415

            visit = db.query(TimeshareVisit).filter(TimeshareVisit.id == visit_id).first()
            if not visit:
                logger.warning("send_visit_survey: visit %s not found", visit_id)
                return
            contract = visit.contract
            if not contract or not contract.customer_phone:
                logger.info("send_visit_survey: visit %s has no customer phone — skipped", visit_id)
                return

            token = create_survey_token(branch_id=branch_id, timeshare_visit_id=visit_id)
            base_url = settings.PUBLIC_SITE_URL.rstrip("/") if settings.PUBLIC_SITE_URL else ""
            link = f"{base_url}/survey/{token}" if base_url else token
            send_whatsapp_message(
                contract.customer_phone,
                f"أهلاً {contract.customer_name} 🏝️ — نتمنى إنك استمتعت بزيارتك للخيمة. "
                f"شاركنا رأيك في أقل من دقيقة: {link}",
            )
            logger.info("send_visit_survey: sent to visit=%s contract=%s", visit_id, contract.id)

    except Exception as exc:
        logger.error("send_visit_survey failed: %s", exc)
        notify_task_failure(
            "app.tasks.timeshare_tasks.send_visit_survey", exc,
            extra={"visit_id": visit_id, "branch_id": branch_id},
        )


@celery_app.task(name="app.tasks.timeshare_tasks.process_waitlist", bind=True)
def process_waitlist(self):
    """
    كل يوم 10 صباحاً — قائمة الانتظار (TimeshareWaitlist) كانت موديل +
    endpoints بدون أي معالجة فعلية خالص: عميل يتسجّل فيها ويفضل عليها
    للأبد من غير أي حد يعرف إن وحدة اتفضت أو إن مهلة الرد فاتت.

    خطوتان في نفس الـtask (نفس نمط mark_overdue's multi-concern pass):
    ① notified فات معاد ردها (expires_at < دلوقتي) → expired، عشان الفرصة
       تروح للتالي في الطابور من غير ما حد يحتاج يتابعها يدويًا.
    ② waiting لسه معلّقة → فحص فعلي (find_available_unit، نفس منطق
       create_visit) لو فيه وحدة من نوع العقد متاحة للفترة المطلوبة، وإن
       وُجدت: notified + مهلة 48 ساعة للرد + تنبيه واتساب حقيقي.
    """
    try:
        from app.core.database import SessionLocal  # noqa: PLC0415
        from datetime import datetime, timedelta      # noqa: PLC0415

        with SessionLocal() as db:
            try:
                from app.modules.timeshare.crud import find_available_unit  # noqa: PLC0415
                from app.modules.timeshare.models import (  # noqa: PLC0415
                    TimeshareContract, TimeshareWaitlist,
                )
                from app.core.kernel.whatsapp import send_whatsapp_message  # noqa: PLC0415

                now = datetime.utcnow()

                expired = (
                    db.query(TimeshareWaitlist)
                    .filter(TimeshareWaitlist.status == "notified", TimeshareWaitlist.expires_at < now)
                    .all()
                )
                for entry in expired:
                    entry.status = "expired"

                waiting = (
                    db.query(TimeshareWaitlist)
                    .filter(TimeshareWaitlist.status == "waiting")
                    .order_by(TimeshareWaitlist.position)
                    .all()
                )
                notified_count = 0
                for entry in waiting:
                    contract = db.query(TimeshareContract).filter(
                        TimeshareContract.id == entry.contract_id
                    ).first()
                    if not contract:
                        continue
                    unit = find_available_unit(
                        db, entry.branch_id, contract.room_type,
                        entry.requested_start, entry.requested_end,
                    )
                    if not unit:
                        continue
                    entry.status = "notified"
                    entry.notified_at = now
                    entry.expires_at = now + timedelta(hours=48)
                    if contract.customer_phone:
                        send_whatsapp_message(
                            contract.customer_phone,
                            f"خبر سار! توفّرت وحدة {contract.room_type} في الخيمة بيتش للفترة "
                            f"من {entry.requested_start:%Y-%m-%d} إلى {entry.requested_end:%Y-%m-%d} — "
                            f"كلّم خدمة العملاء خلال 48 ساعة لتأكيد الحجز، وإلا هتتاح للتالي في قائمة الانتظار.",
                        )
                    notified_count += 1

                db.commit()
                logger.info(
                    "Waitlist processed: expired=%s notified=%s", len(expired), notified_count,
                )
            except ImportError:
                logger.debug("Timeshare module not yet built — skipped")

    except Exception as exc:
        logger.error("process_waitlist failed: %s", exc)
        notify_task_failure("app.tasks.timeshare_tasks.process_waitlist", exc)
