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

    # ── Cashier Shift Reconciliation (POS Day close) ──────────────────
    # فرق الكاش وقت قفل الوردية = الكاش المعدود فعليًا − الكاش المتوقع (محسوب
    # سيرفر-سايد من المبيعات الفعلية، راجع finance.services.close_shift). فرق
    # صغير (تفكة/تقريب) طبيعي في أي تعامل نقدي يومي — تحذير بس.
    # ملاحظة (2026-07-14، قرار Mohamed): الوردية تُقفل دايماً بغض النظر عن
    # حجم الفرق — الكاشير مش مسؤوليته الاحتجاز، المحاسب هو اللي يراجع.
    # أُلغيت آلية الرفض (REJECT) بالكامل — كل الفروقات بتظهر كـ warning
    # في تفاصيل الوردية للمحاسب ويتسجّل في AuditLog تلقائياً.
    CASH_VARIANCE_WARNING_ABS: float = 50.0     # ج — فوق كده = warning للمحاسب (الوردية تُقفل برضو)

    # ── Fraud Detection (Operations & Control Layer plan §3.5) ────────
    # عتبات حقيقية (مش أرقام توضيحية) لكشف نشاط كاشير مشبوه — كل عتبة "عدد
    # حركات خلال نافذة زمنية دوّارة" per-cashier، مش نسبة مئوية (حساب نسبة
    # حقيقية محتاج مقام "إجمالي الطلبات" وده يفتح افتراضات إضافية Mohamed
    # ما حددهاش — قرار محافظ مبسّط، موثّق في PROJECT_STATUS.md). القيم
    # الافتراضية مبنية على أرقام الخطة نفسها (15 مرتجع/ساعة، 20 فتح درج/يوم)
    # زائد قيم مقابلة معقولة للخصم/الإلغاء بنفس رتبة الحجم — راجع
    # app/tasks/fraud_tasks.py للمنطق الكامل. كل رقم هنا قابل للتعديل من
    # غير أي تغيير كود.
    FRAUD_REFUND_COUNT_THRESHOLD: int = 15        # مرتجع
    FRAUD_REFUND_WINDOW_MINUTES: int = 60
    FRAUD_VOID_COUNT_THRESHOLD: int = 15          # إلغاء صنف
    FRAUD_VOID_WINDOW_MINUTES: int = 60
    FRAUD_DISCOUNT_COUNT_THRESHOLD: int = 10      # محاولة تطبيق خصم (كل مستوى — الكاشير صفر صلاحية أصلاً بعد Batch 1)
    FRAUD_DISCOUNT_WINDOW_MINUTES: int = 60
    FRAUD_DRAWER_OPEN_COUNT_THRESHOLD: int = 20   # فتح الدرج بدون بيع
    FRAUD_DRAWER_OPEN_WINDOW_MINUTES: int = 1440  # 24 ساعة ("في اليوم")
    FRAUD_ALERT_DEDUP_HOURS: int = 24             # ما نبعتش نفس التنبيه (نفس كاشير+قاعدة) أكتر من مرة كل كام ساعة

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

    # ── Rate Limiting (login) ──────────────────────────────────────────
    # الافتراضي (5 محاولات/300 ثانية) هو المعتمد أمنيًا للإنتاج (§15 CLAUDE.md)
    # — ما اتغيّرش هنا. قابل للتوسيع في `.env` المحلي بس (مش القيمة الافتراضية
    # دي) وقت التطوير/الاختبار، لما محتاج تبدّل حسابات تجريبية كتير بسرعة
    # (كل حساب = محاولة تسجيل دخول منفصلة على نفس الـ IP).
    LOGIN_RATE_LIMIT_MAX: int = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 300

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
