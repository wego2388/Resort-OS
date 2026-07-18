"""
app/core/config.py
Settings للمشروع — يرث WegoSettings ويضيف حقول Resort OS
"""
from functools import lru_cache
from typing import Optional

from pydantic import Field, model_validator
from cryptography.fernet import Fernet

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

    # ── Gate 1 containment kill switches (جولة مراجعة Codex الثالثة) ───
    # AGENTS.md بيمنع صراحةً الاعتماد على core.Setting (key/value حر في
    # الداتابيز) كبوابة أمان لوحدها. الطلب الذاتي وتنبيهات الضيف كلاهما
    # مسارات غير آمنة قبل Gate 8 (Service Location/QR token/guest session
    # — راجع docs/decisions/0001-qr-guest-service-mode.md) — لازم الاتنين
    # معًا: الـflag المكتوب هنا (deployment-level، مش قابل للتغيير من
    # الـAPI) + core.Setting الخاص بالفرع (dining.self_order_enabled /
    # core.guest_alerts_enabled). أي واحد بس متفعّل مش كافي. راجع
    # _validate_containment_switches تحت — production ترفض تشغّل لو أي
    # واحد منهم True، مش تحذير بس.
    DINING_SELF_ORDER_ENABLED: bool = False
    GUEST_ALERTS_ENABLED: bool = False

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
    AUTH_REFRESH_RATE_LIMIT_MAX: int = 60
    AUTH_REFRESH_RATE_LIMIT_WINDOW_SECONDS: int = 60
    AUTH_SENSITIVE_RATE_LIMIT_MAX: int = 10
    AUTH_SENSITIVE_RATE_LIMIT_WINDOW_SECONDS: int = 300
    PASSWORD_RESET_REQUEST_RATE_LIMIT_MAX: int = 10
    PASSWORD_RESET_REQUEST_RATE_LIMIT_WINDOW_SECONDS: int = 900
    PASSWORD_RESET_ACCOUNT_RATE_LIMIT_MAX: int = 3
    PASSWORD_RESET_ACCOUNT_RATE_LIMIT_WINDOW_SECONDS: int = 900
    TWO_FACTOR_ENROLLMENT_TOKEN_TTL_MINUTES: int = Field(30, ge=5, le=1440)
    # Gate 2B3A — deliberately much shorter than ACCESS_TOKEN_EXPIRE_MINUTES
    # (30 in production): a step-up grant proves the session holder recently
    # re-entered their password (and TOTP/recovery code where 2FA is on),
    # not just that their access token hasn't expired yet.
    STEP_UP_TOKEN_TTL_SECONDS: int = Field(180, ge=60, le=300)

    # ── Rate limiting: trusted reverse-proxy hop count (Codex security
    # review، 2026-07-17) ───────────────────────────────────────────────
    # app.core.rate_limit._client_ip كان بيثق في أول قيمة (leftmost) في
    # X-Forwarded-For بلا أي تحقق — قيمة العميل نفسه بتتقدّم بدون تعديل
    # عبر كل الطبقتين (edge nginx وfrontend nginx، الاتنين بيستخدموا
    # $proxy_add_x_forwarded_for اللي بيضيف على القيمة الجاية مش يستبدلها،
    # راجع deploy/nginx/edge.conf وfrontend/nginx.spa.conf)، يعني أي عميل
    # يقدر يزوّر مفتاح الـrate-limit في Redis ويهرب من أي حد فعليًا.
    # الافتراضي 0 = محلي/بدون reverse proxy، يتجاهل X-Forwarded-For كليًا
    # ويستخدم request.client.host مباشرة. production خلف edge+frontend
    # nginx لازم 2 (راجع docker-compose.prod.yml). حد أقصى 10 دفاعي — مفيش
    # سيناريو حقيقي في المشروع ده محتاج سلسلة reverse proxy أطول من كده.
    RATE_LIMIT_TRUSTED_PROXY_HOPS: int = Field(0, ge=0, le=10)

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

    @model_validator(mode="after")
    def _validate_containment_switches(self) -> "Settings":
        """Gate 1 containment: DINING_SELF_ORDER_ENABLED/GUEST_ALERTS_ENABLED
        لازم يفضلوا False في أي بيئة غير معروفة صراحةً كآمنة — فشل صريح
        وقت الإقلاع، مش قبول صامت.

        **تصحيح (جولة مراجعة Codex الرابعة): fail-closed حقيقي، مش
        blacklist.** النسخة الأولى كانت بترفض `ENVIRONMENT == "production"`
        بس (مطابقة حرفية) — يعني "Production" بحرف كبير، "staging"، أو أي
        قيمة تانية غير متوقعة (typo، بيئة جديدة محدش عرّفها هنا) كانت
        بتعدّي من غير أي فحص خالص. دلوقتي allow-list صريح
        (development/test/testing بعد strip().lower()) هو الوحيد المسموح
        فيه تفعيل أي من الاثنين — أي حاجة تانية (بما فيها production بأي
        حروف، staging، أو قيمة غير معروفة) بترفض لو أي واحد منهم True."""
        _SAFE_ENVIRONMENTS = {"development", "test", "testing"}
        normalized_env = (self.ENVIRONMENT or "").strip().lower()
        if normalized_env not in _SAFE_ENVIRONMENTS:
            unsafe = [
                name for name, value in (
                    ("DINING_SELF_ORDER_ENABLED", self.DINING_SELF_ORDER_ENABLED),
                    ("GUEST_ALERTS_ENABLED", self.GUEST_ALERTS_ENABLED),
                ) if value
            ]
            if unsafe:
                raise ValueError(
                    "لا يجوز تفعيل " + "، ".join(unsafe) + f" في بيئة '{self.ENVIRONMENT}' "
                    "قبل اكتمال Gate 8 (Service Location/QR token/guest session) — "
                    "مسموح فقط في development/test/testing. راجع "
                    "docs/decisions/0001-qr-guest-service-mode.md"
                )
        return self

    @model_validator(mode="after")
    def _validate_production_authentication(self) -> "Settings":
        """Fail closed anywhere that is not an explicitly safe local/test env.

        TOTP login enforcement without a valid field-encryption key is not a
        usable production configuration: the application either accepts a
        password-only privileged login or cannot safely persist/read the TOTP
        seed.  Unknown environment names are treated like production rather
        than silently weakening authentication because of a typo.
        """
        normalized_env = (self.ENVIRONMENT or "").strip().lower()
        if normalized_env in {"development", "test", "testing"}:
            return self
        if not self.LOGIN_2FA_ENFORCED:
            raise ValueError(
                "LOGIN_2FA_ENFORCED must be true outside development/test/testing; "
                "privileged accounts may not use password-only login."
            )
        if not self.FIELD_ENCRYPTION_KEY:
            raise ValueError(
                "FIELD_ENCRYPTION_KEY is required outside development/test/testing "
                "to encrypt TOTP secrets at rest."
            )
        try:
            Fernet(self.FIELD_ENCRYPTION_KEY.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise ValueError(
                "FIELD_ENCRYPTION_KEY must be a valid Fernet key outside "
                "development/test/testing."
            ) from exc
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
