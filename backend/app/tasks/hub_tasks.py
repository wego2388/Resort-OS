"""app/tasks/hub_tasks.py — Digital Hub: sitemap refresh + offer expiry"""
from __future__ import annotations

import logging
import os
from datetime import datetime

from app.celery_app import celery_app
from app.core.config import settings
from app.core.kernel.email import send_email
from app.core.kernel.worker import notify_task_failure
from app.resort_os.timezone_utils import local_today

logger = logging.getLogger(__name__)

# قرار Mohamed 2026-09-09: أي حجز/استفسار غرفة يروح لإيميل الحجوزات، وأي
# استفسار عام (نموذج تواصل معنا/تايم شير — purpose="general_inquiry") يروح
# لإيميل الاستعلامات العام. قابلين للتجاوز عبر env var لو الصندوق اتغيّر.
RESERVATION_NOTIFY_EMAIL = os.getenv(
    "RESERVATION_NOTIFY_EMAIL", "reservation@elkheima.com"
)
INFO_NOTIFY_EMAIL = os.getenv("INFO_NOTIFY_EMAIL", "info@elkheima.com")


@celery_app.task(
    name="app.tasks.hub_tasks.purge_expired_public_contact_pii",
    bind=True,
    max_retries=3,
)
def purge_expired_public_contact_pii(self):
    """Daily bounded purge for expired public-contact and public-lead PII."""
    try:
        from app.core.database import SessionLocal  # noqa: PLC0415
        from app.modules.hub.public_contact import (  # noqa: PLC0415
            purge_expired_public_contact_pii as purge_batch,
        )

        totals = {"contacts": 0, "leads": 0}
        with SessionLocal() as db:
            for _ in range(20):  # at most 10,000 rows per daily run
                changed = purge_batch(db, now=datetime.utcnow(), batch_size=500)
                db.commit()
                totals["contacts"] += changed["contacts"]
                totals["leads"] += changed["leads"]
                if changed["contacts"] + changed["leads"] < 500:
                    break
        logger.info(
            "Public-contact PII purge complete: contacts=%s leads=%s",
            totals["contacts"],
            totals["leads"],
        )
        return totals
    except Exception as exc:
        logger.error("public-contact PII purge failed: %s", exc)
        raise self.retry(exc=exc, countdown=600)


@celery_app.task(
    name="app.tasks.hub_tasks.refresh_sitemap",
    bind=True,
    max_retries=3,
)
def refresh_sitemap(self):
    """
    كل يوم 3 صباحاً — يُحدّث سجل الـ sitemap لكل الفروع.
    """
    try:
        from app.core.database import SessionLocal      # noqa: PLC0415
        from app.modules.core.models import Branch      # noqa: PLC0415

        with SessionLocal() as db:
            try:
                from app.modules.hub.services import refresh_sitemap as do_refresh  # noqa: PLC0415

                branches = db.query(Branch).filter(Branch.is_active.is_(True)).all()
                total_pages = 0

                for branch in branches:
                    pages_count = do_refresh(db, branch.id)
                    logger.info(
                        "Sitemap refreshed: branch=%s pages=%s",
                        branch.id, pages_count,
                    )
                    total_pages += pages_count

                logger.info("Sitemap refresh done: total_pages=%s", total_pages)

            except ImportError:
                logger.debug("Hub module not yet built — skipped")

    except Exception as exc:
        logger.error("hub refresh_sitemap failed: %s", exc)
        raise self.retry(exc=exc, countdown=600)


@celery_app.task(
    name="app.tasks.hub_tasks.expire_old_offers",
    bind=True,
)
def expire_old_offers(self):
    """
    كل يوم منتصف الليل — يُعطّل العروض المنتهية الصلاحية.
    """
    try:
        from app.core.database import SessionLocal      # noqa: PLC0415

        today = local_today(settings.TIMEZONE)

        with SessionLocal() as db:
            try:
                from app.modules.hub.models import HubOffer  # noqa: PLC0415

                expired = (
                    db.query(HubOffer)
                    .filter(
                        HubOffer.is_active.is_(True),
                        HubOffer.valid_until < today,
                    )
                    .all()
                )

                for offer in expired:
                    offer.is_active = False
                    logger.info(
                        "Offer expired: id=%s title=%s valid_until=%s",
                        offer.id, offer.title, offer.valid_until,
                    )

                db.commit()
                logger.info("Expired offers deactivated: %s", len(expired))

            except ImportError:
                logger.debug("Hub module not yet built — skipped")

    except Exception as exc:
        logger.error("hub expire_old_offers failed: %s", exc)
        notify_task_failure("app.tasks.hub_tasks.expire_old_offers", exc)


@celery_app.task(
    name="app.tasks.hub_tasks.process_pending_bookings_reminder",
    bind=True,
)
def process_pending_bookings_reminder(self):
    """
    كل يوم 10 صباحاً — تذكير للحجوزات الإلكترونية التي لم تُؤكَّد منذ 24 ساعة.
    """
    try:
        from app.core.database import SessionLocal          # noqa: PLC0415
        from datetime import datetime, timedelta            # noqa: PLC0415

        cutoff = datetime.utcnow() - timedelta(hours=24)

        with SessionLocal() as db:
            try:
                from app.modules.hub.models import HubOnlineBooking  # noqa: PLC0415

                pending = (
                    db.query(HubOnlineBooking)
                    .filter(
                        HubOnlineBooking.status == "pending",
                        HubOnlineBooking.created_at <= cutoff,
                    )
                    .all()
                )

                for booking in pending:
                    logger.info(
                        "Unconfirmed booking: id=%s guest=%s phone=%s date=%s source=%s",
                        booking.id, booking.guest_name,
                        booking.guest_phone, booking.requested_date,
                        booking.source,
                    )

                logger.info("Pending online bookings found: %s", len(pending))

            except ImportError:
                logger.debug("Hub module not yet built — skipped")

    except Exception as exc:
        logger.error("hub process_pending_bookings_reminder failed: %s", exc)
        notify_task_failure("app.tasks.hub_tasks.process_pending_bookings_reminder", exc)


@celery_app.task(
    name="app.tasks.hub_tasks.notify_new_room_booking",
    bind=True,
    max_retries=3,
)
def notify_new_room_booking(self, booking_id: int, language: str = "ar"):
    """طلب حجز غرفة عام جديد (الموقع التسويقي) — إيميل فوري لصندوق الحجوزات،
    وإيميل تأكيد فوري للضيف نفسه لو سجّل إيميله (راجع Mohamed 2026-09-09:
    "الهدف التأكد من المراسلة بالإيميلات شغالة" — مراسلة باتجاهين، مش بس
    تنبيه للموظفين). مُستدعاة مرة واحدة فور إنشاء HubOnlineBooking (راجع
    hub.public_room_booking.submit_public_room_booking)، مش دورية."""
    try:
        from app.core.database import SessionLocal            # noqa: PLC0415
        from app.modules.hub.models import HubOnlineBooking    # noqa: PLC0415

        with SessionLocal() as db:
            booking = db.get(HubOnlineBooking, booking_id)
            if not booking:
                logger.warning("notify_new_room_booking: booking %s not found", booking_id)
                return

            lines = [
                f"مرجع الطلب: {booking.public_reference}",
                f"الاسم: {booking.guest_name}",
                f"الهاتف: {booking.guest_phone}",
            ]
            if booking.guest_email:
                lines.append(f"الإيميل: {booking.guest_email}")
            lines.extend([
                f"تاريخ الوصول: {booking.check_in}",
                f"تاريخ المغادرة: {booking.check_out}",
                f"عدد الكبار: {booking.adults} — عدد الأطفال: {booking.children}",
            ])
            if booking.quoted_total is not None:
                lines.append(
                    f"السعر التقديري: {booking.quoted_total} {booking.quoted_currency}"
                )
            if booking.notes:
                lines.append(f"ملاحظات الضيف: {booking.notes}")

            sent = send_email(
                to=RESERVATION_NOTIFY_EMAIL,
                subject=f"طلب حجز جديد من الموقع — {booking.public_reference}",
                body="\n".join(lines),
            )
            if not sent:
                raise RuntimeError("send_email returned False")

            if booking.guest_email:
                subject, body = _room_booking_guest_reply_text(booking, language)
                guest_sent = send_email(
                    to=booking.guest_email,
                    subject=subject,
                    body=body,
                )
                if not guest_sent:
                    raise RuntimeError("guest confirmation send_email returned False")
    except Exception as exc:
        logger.error("notify_new_room_booking failed: %s", exc)
        raise self.retry(exc=exc, countdown=300)


def _room_booking_guest_reply_text(booking, language: str) -> tuple[str, str]:
    """نص إيميل التأكيد المُرسَل للضيف نفسه — أربع لغات، نفس نبرة رسالة
    النجاح الظاهرة في فورم الحجز على الموقع (Booking.vue/Rooms.vue)."""
    texts = {
        "ar": (
            f"تأكيد استلام طلب حجزك — {booking.public_reference}",
            f"مرحبًا {booking.guest_name}،\n\n"
            f"استلمنا طلب حجزك بمرجع {booking.public_reference} "
            f"من {booking.check_in} إلى {booking.check_out}.\n"
            "فريقنا هيتواصل معاك قريب لتأكيد التفاصيل والدفع.\n\n"
            "شكرًا لاختيارك El Kheima Beach.",
        ),
        "en": (
            f"We received your booking request — {booking.public_reference}",
            f"Hello {booking.guest_name},\n\n"
            f"We received your booking request (reference {booking.public_reference}) "
            f"for {booking.check_in} to {booking.check_out}.\n"
            "Our team will contact you shortly to confirm details and payment.\n\n"
            "Thank you for choosing El Kheima Beach.",
        ),
        "ru": (
            f"Ваш запрос на бронирование получен — {booking.public_reference}",
            f"Здравствуйте, {booking.guest_name}!\n\n"
            f"Мы получили ваш запрос на бронирование (номер {booking.public_reference}) "
            f"с {booking.check_in} по {booking.check_out}.\n"
            "Наша команда свяжется с вами в ближайшее время для подтверждения деталей и оплаты.\n\n"
            "Спасибо, что выбрали El Kheima Beach.",
        ),
        "it": (
            f"Richiesta di prenotazione ricevuta — {booking.public_reference}",
            f"Ciao {booking.guest_name},\n\n"
            f"Abbiamo ricevuto la tua richiesta di prenotazione (riferimento {booking.public_reference}) "
            f"dal {booking.check_in} al {booking.check_out}.\n"
            "Il nostro team ti contatterà a breve per confermare i dettagli e il pagamento.\n\n"
            "Grazie per aver scelto El Kheima Beach.",
        ),
    }
    return texts.get(language, texts["ar"])


@celery_app.task(
    name="app.tasks.hub_tasks.notify_new_contact_form",
    bind=True,
    max_retries=3,
)
def notify_new_contact_form(self, contact_form_id: int):
    """استفسار عام جديد (نموذج تواصل معنا/تايم شير — purpose="general_inquiry")
    من الموقع التسويقي — إيميل فوري لصندوق الاستعلامات العام. استفسارات
    الشاطئ/الأنشطة/الفعاليات (باقي قيم purpose) لسه بتنتظر قناة واتساب
    (محتاجة حساب Twilio حقيقي — راجع core.kernel.whatsapp) قبل ما تتوصّل
    تلقائيًا؛ مُستدعاة مرة واحدة فور إنشاء ContactForm، مش دورية."""
    try:
        from app.core.database import SessionLocal      # noqa: PLC0415
        from app.modules.hub.models import ContactForm   # noqa: PLC0415

        with SessionLocal() as db:
            form = db.get(ContactForm, contact_form_id)
            if not form:
                logger.warning("notify_new_contact_form: contact %s not found", contact_form_id)
                return
            if form.purpose != "general_inquiry":
                return

            lines = [
                f"مرجع الطلب: {form.public_reference}",
                f"الاسم: {form.full_name}",
                f"الهاتف: {form.phone}",
            ]
            if form.email:
                lines.append(f"الإيميل: {form.email}")
            if form.subject:
                lines.append(f"الموضوع: {form.subject}")
            lines.append(f"الرسالة: {form.message}")

            sent = send_email(
                to=INFO_NOTIFY_EMAIL,
                subject=f"استفسار جديد من الموقع — {form.public_reference}",
                body="\n".join(lines),
            )
            if not sent:
                raise RuntimeError("send_email returned False")
    except Exception as exc:
        logger.error("notify_new_contact_form failed: %s", exc)
        raise self.retry(exc=exc, countdown=300)
