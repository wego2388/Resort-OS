"""
app/core/kernel/config.py
Base settings class — owned by resort-os, no external package.

The project's real Settings class (app/core/config.py) subclasses this and
adds resort-specific fields.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class CoreSettings(BaseSettings):
    # ── Core ──────────────────────────────────────────────────────────────
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ENVIRONMENT: str = "development"
    REDIS_URL: Optional[str] = None
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # ── App Identity ──────────────────────────────────────────────────────
    APP_NAME: str = "Resort OS"
    APP_URL: str = ""
    ADMIN_PHONE: str = ""

    # ── Security Headers ──────────────────────────────────────────────────
    SECURITY_FRAME_OPTIONS: str = "DENY"
    SECURITY_REFERRER_POLICY: str = "strict-origin-when-cross-origin"
    SECURITY_PERMISSIONS_POLICY: str = "geolocation=(), microphone=(), camera=(), payment=()"
    SECURITY_CSP: str = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:; "
        "connect-src 'self'"
    )
    SECURITY_HSTS_MAX_AGE: int = 31536000
    SECURITY_HSTS_PRELOAD: bool = False

    # ── WhatsApp (Twilio) ───────────────────────────────────────────────────
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_WHATSAPP_NUMBER: str = "whatsapp:+14155238886"
    WHATSAPP_PHONE_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""

    # ── Email (optional, SendGrid) ──────────────────────────────────────────
    SENDGRID_API_KEY: Optional[str] = None
    SENDGRID_FROM_EMAIL: str = "noreply@resortos.local"

    # ── Sentry ───────────────────────────────────────────────────────────────
    SENTRY_DSN: Optional[str] = None
    SENTRY_ENVIRONMENT: Optional[str] = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

    # ── Celery ───────────────────────────────────────────────────────────────
    CELERY_BROKER_URL: Optional[str] = None

    # ── Auth lockout ───────────────────────────────────────────────────────
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_MINUTES: int = 30

    # ── Login-time 2FA ─────────────────────────────────────────────────────
    # When True, a 2FA-enabled account must submit a valid TOTP code at /login
    # (otp_code) — making 2FA a real second factor, not just an enrollment flag.
    # Enable in lockstep with the frontend collecting the code at login.
    LOGIN_2FA_ENFORCED: bool = False

    model_config = {"extra": "allow", "env_file": ".env"}
