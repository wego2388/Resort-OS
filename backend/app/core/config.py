"""
app/core/config.py
Settings للمشروع — يرث WegoSettings ويضيف حقول Resort OS
"""
from functools import lru_cache
from typing import Optional

from app.core.kernel.config import CoreSettings


class Settings(CoreSettings):
    # ── Resort Identity ───────────────────────────────────────────────
    RESORT_NAME: str = "Resort OS"
    DEFAULT_CURRENCY: str = "EGP"
    SUPPORTED_CURRENCIES: str = "EGP,USD,EUR,SAR"
    VAT_PERCENTAGE: float = 14.0
    SERVICE_CHARGE_PERCENTAGE: float = 12.0
    TIMEZONE: str = "Africa/Cairo"

    # ── API ───────────────────────────────────────────────────────────
    API_PREFIX: str = "/api/v1"

    # ── Auth extras ───────────────────────────────────────────────────
    ACCOUNT_LOCKOUT_ATTEMPTS: int = 5
    ACCOUNT_LOCKOUT_MINUTES: int = 15

    # ── Survey Token (مفتاح منفصل لعزل الأمان) ───────────────────────
    SURVEY_TOKEN_SECRET: str = ""

    # ── Field Encryption (national_id, passport) ──────────────────────
    FIELD_ENCRYPTION_KEY: Optional[str] = None

    # ── E-Invoice Egypt (ETA) ─────────────────────────────────────────
    ETA_ENABLED: bool = False
    ETA_CLIENT_ID: Optional[str] = None
    ETA_CLIENT_SECRET: Optional[str] = None
    ETA_TAXPAYER_RIN: Optional[str] = None       # Tax Registration Number المسجَّل في ETA
    ETA_TAXPAYER_NAME: Optional[str] = None
    ETA_BRANCH_CODE: str = "0"                   # كود الفرع عند ETA — "0" للفرع الرئيسي

    # ── Infrastructure ports (for reference) ──────────────────────────
    # Backend: 8005 | Frontend: 5175 | PostgreSQL: 5436 | Redis: 6381

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
