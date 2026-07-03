"""
app/core/kernel/whatsapp.py
WhatsApp notifications — Twilio sandbox + Meta Cloud API production.
Uses env vars read at call time (not import time) for reliable .env support.
"""

import os
from loguru import logger

WHATSAPP_API_URL = "https://graph.facebook.com/v18.0"

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
    """Send via Twilio (sync — for schedulers and Celery tasks)."""
    try:
        client = _get_twilio_client()
        from_number = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
        if not client:
            logger.info(f"[WhatsApp dev] → {phone}: {message[:80]}")
            return True
        to = f"whatsapp:{phone}" if not phone.startswith("whatsapp:") else phone
        msg = client.messages.create(body=message, from_=from_number, to=to)
        logger.info(f"[WhatsApp] sent: {msg.sid}")
        return True
    except Exception as e:
        logger.error(f"[WhatsApp] Twilio error: {e}")
        return False


async def send_whatsapp(phone: str, message: str) -> bool:
    """Send via Meta Cloud API (async — preferred in production)."""
    phone_id = os.getenv("WHATSAPP_PHONE_ID", "")
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    if phone_id and access_token:
        phone_clean = phone.replace("+", "").replace(" ", "").replace("-", "")
        url = f"{WHATSAPP_API_URL}/{phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_clean,
            "type": "text",
            "text": {"body": message},
        }
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, headers=headers, timeout=10)
                return resp.status_code == 200
        except Exception as e:
            logger.error(f"[WhatsApp] Meta API error: {e}")
    return send_whatsapp_message(phone, message)


def notify_admin(message: str) -> bool:
    """Send a notification message to the admin phone (ADMIN_PHONE env var)."""
    admin_phone = os.getenv("ADMIN_PHONE", "")
    if not admin_phone:
        logger.warning("[WhatsApp] ADMIN_PHONE not set")
        return False
    return send_whatsapp_message(admin_phone, message)
