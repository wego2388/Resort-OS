"""
app/core/kernel/whatsapp.py
WhatsApp notifications عبر Twilio — قناة الملكية الجزئية الوحيدة
(نطاق أضيق عمدًا 2026-09-06: كانت بتُستخدم كمان لتنبيهات إدارية عامة —
كل تلك الاستدعاءات اتشالت بقرار Mohamed، القناة دي فضلت بس للملكية الجزئية
(OTP دخول بوابة الملاك، موافقة/رفض الزيارة، رد الموظف على تذكرة دعم) لأن
مفيش قناة بديلة موجودة لها. Uses env vars read at call time (not import
time) for reliable .env support.
"""

import os
from loguru import logger

# ── Lazy Twilio client ────────────────────────────────────────────────────────
_twilio_client = None
_twilio_init_attempted = False


def _get_twilio_client():
    global _twilio_client, _twilio_init_attempted
    if _twilio_init_attempted:
        return _twilio_client
    _twilio_init_attempted = True
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    if sid and token:
        try:
            from twilio.rest import Client
            _twilio_client = Client(sid, token)
        except ImportError:
            logger.warning("[WhatsApp] twilio not installed")
    return _twilio_client


def send_whatsapp_message(phone: str, message: str) -> bool:
    """Send via Twilio (sync — for schedulers and Celery tasks).

    مراجعة Codex 2026-08-31 (SEC-13): كانت بترجع ``True`` حتى لو Twilio مش
    مُعدّة خالص — أي caller (فحص احتيال، فشل مهمة، تنبيه تأخر سداد) كان
    بيصدّق إن التنبيه اتبعت فعليًا، بينما هو راح للفراغ بصمت. دلوقتي:
    ``True`` بس في بيئات التطوير/الاختبار (نفس السلوك القديم عمدًا — مفيش
    داعي لإعداد Twilio حقيقي محليًا)؛ في أي بيئة تانية (الإنتاج تحديدًا)
    بترجع ``False`` مع ERROR واضح، عشان الفشل يبان مش يتبلع."""
    try:
        client = _get_twilio_client()
        from_number = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
        if not client:
            from app.core.config import settings  # noqa: PLC0415
            if settings.ENVIRONMENT in ("development", "test", "testing"):
                logger.info(f"[WhatsApp dev] → {phone}: {message[:80]}")
                return True
            logger.error(
                "[WhatsApp] TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN غير مُعدّة — "
                f"تنبيه حقيقي فشل يوصل: {message[:80]}"
            )
            return False
        to = f"whatsapp:{phone}" if not phone.startswith("whatsapp:") else phone
        msg = client.messages.create(body=message, from_=from_number, to=to)
        logger.info(f"[WhatsApp] sent: {msg.sid}")
        return True
    except Exception as e:
        logger.error(f"[WhatsApp] Twilio error: {e}")
        return False
