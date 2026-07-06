"""
app/core/config.py
Settings للمشروع — يرث WegoSettings ويضيف حقول Resort OS
"""
from functools import lru_cache
from typing import Optional

from pydantic import model_validator

from app.core.kernel.config import CoreSettings

# Placeholder/example values that must never reach a production deployment.
# A guessable SECRET_KEY lets anyone forge JWTs for any account (incl. super_admin).
_WEAK_SECRET_MARKERS = ("change_me", "changeme", "example", "secret", "test", "xxx")


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

    # ── Survey Token (مفتاح منفصل لعزل الأمان) ───────────────────────
    SURVEY_TOKEN_SECRET: str = ""

    # ── Public guest site (لبناء روابط /order, /survey, /beach/checkin
    # المُرسَلة فعليًا للضيف عبر واتساب — بدون / في الآخر) ─────────────
    PUBLIC_SITE_URL: str = ""

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

    @model_validator(mode="after")
    def _validate_secret_key(self) -> "Settings":
        """رفض مفتاح SECRET_KEY ضعيف/افتراضي في الإنتاج — وإلا يمكن تزوير JWT.
        Fails hard in production; warns (doesn't block) in dev/test so local
        setups with placeholder keys still boot."""
        key = self.SECRET_KEY or ""
        lowered = key.lower()
        weak = (
            len(key) < 32
            or any(marker in lowered for marker in _WEAK_SECRET_MARKERS)
        )
        if weak:
            msg = (
                "SECRET_KEY ضعيف أو افتراضي — لازم يكون 32 حرف عشوائي على الأقل "
                "وخالي من كلمات زي CHANGE_ME/example/secret. ولّده بـ: "
                "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
            if self.ENVIRONMENT == "production":
                raise ValueError(msg)
            import warnings  # noqa: PLC0415
            warnings.warn(f"[config] {msg}", stacklevel=2)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
