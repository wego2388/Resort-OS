"""
app/core/kernel/email.py
إشعارات إيميل عبر SMTP — قناة استفسارات الموقع العام (قرار Mohamed
2026-09-09: صناديق بريد حقيقية بالفعل عند مزوّد الاستضافة، لا حاجة لمزوّد
SaaS خارجي زي SendGrid). Uses env vars read at call time (not import
time), نفس نمط whatsapp.py بالظبط — بما فيه سلوك fail-closed في الإنتاج
(SEC-13: ``True`` وهمي لما القناة مش مُعدّة كان بيخفي فشل حقيقي).
"""

import os
import smtplib
import ssl
from email.message import EmailMessage

from loguru import logger


def send_email(to: str, subject: str, body: str) -> bool:
    """Send a plain-text email via SMTP (sync — for Celery tasks).

    ``True`` بس لو الإرسال نجح فعليًا (أو في بيئة تطوير/اختبار بدون إعداد
    حقيقي). في أي بيئة تانية بدون SMTP_HOST/USER/PASSWORD مُعدّين، بترجع
    ``False`` مع ERROR واضح — نفس سياسة ``send_whatsapp_message`` بالظبط،
    عشان فشل إرسال حقيقي يبان مش يتبلع بصمت."""
    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    port = int(os.getenv("SMTP_PORT", "465"))
    from_addr = os.getenv("SMTP_FROM") or user

    if not (host and user and password):
        from app.core.config import settings  # noqa: PLC0415
        if settings.ENVIRONMENT in ("development", "test", "testing"):
            logger.info(f"[Email dev] → {to}: {subject}")
            return True
        logger.error(
            "[Email] SMTP_HOST/SMTP_USER/SMTP_PASSWORD غير مُعدّة — "
            f"إيميل حقيقي فشل يوصل: {subject}"
        )
        return False

    try:
        message = EmailMessage()
        message["From"] = from_addr
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=15) as server:
                server.login(user, password)
                server.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.starttls(context=ssl.create_default_context())
                server.login(user, password)
                server.send_message(message)
        logger.info(f"[Email] sent → {to}: {subject}")
        return True
    except Exception as e:
        logger.error(f"[Email] SMTP error: {e}")
        return False
