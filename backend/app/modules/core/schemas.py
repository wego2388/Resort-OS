"""
app/modules/core/schemas.py
═══════════════════════════════════════════════════════════════════════
Pydantic v2 schemas للـ Core Module

الاستخدام:
  - *Base   → الحقول المشتركة
  - *Create → ما يرسله الـ client عند الإنشاء
  - *Update → ما يرسله الـ client عند التعديل (كل الحقول Optional)
  - *Read   → ما يُرجعه الـ API (with from_attributes=True)
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ─────────────────────── Gate 2B3A — mandatory reason ──────────────────
# مشترك بين كل mutation محمي بـstep-up (role update، permission grant/
# revoke، setting upsert) — نفس القاعدة، مكان واحد.

_REASON_MIN_LENGTH = 3
_REASON_MAX_LENGTH = 500


def _validate_reason(value: str) -> str:
    trimmed = (value or "").strip()
    if len(trimmed) < _REASON_MIN_LENGTH:
        raise ValueError(
            f"السبب مطلوب ({_REASON_MIN_LENGTH} أحرف على الأقل بعد إزالة المسافات الزائدة)"
        )
    return trimmed


# ─────────────────────── Branch ──────────────────────────────────────

class BranchBase(BaseModel):
    name:     str       = Field(..., min_length=2, max_length=100)
    name_ar:  Optional[str] = Field(None, max_length=100)
    code:     str       = Field(..., pattern=r"^[A-Z0-9\-]{3,20}$",
                                description="مثال: BRN-001")
    is_active: bool     = True
    timezone:  str      = Field("Africa/Cairo", max_length=50)
    phone:     Optional[str] = Field(None, max_length=20)
    address:   Optional[str] = None
    gm_phone:  Optional[str] = Field(None, max_length=20,
                                     description="رقم المدير العام للـ WhatsApp")


class BranchCreate(BranchBase):
    pass


class BranchUpdate(BaseModel):
    """كل الحقول Optional — PATCH semantics"""
    name:      Optional[str] = Field(None, min_length=2, max_length=100)
    name_ar:   Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None
    timezone:  Optional[str] = Field(None, max_length=50)
    phone:     Optional[str] = Field(None, max_length=20)
    address:   Optional[str] = None
    gm_phone:  Optional[str] = Field(None, max_length=20)


class BranchRead(BranchBase):
    model_config = ConfigDict(from_attributes=True)

    id:         int
    created_at: datetime
    updated_at: datetime


# ─────────────────────── Setting ─────────────────────────────────────

class SettingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:        int
    key:       str
    value:     str
    branch_id: Optional[int]
    updated_at: datetime


class SettingUpdate(BaseModel):
    """تحديث قيمة setting — يُنشئ إذا لم يكن موجوداً (upsert). Gate 2B3A:
    reason إجباري ومحمي بـstep-up (راجع core/api/router.py::upsert_setting)."""
    value:  str = Field(..., min_length=0)
    reason: str = Field(..., max_length=_REASON_MAX_LENGTH)

    @field_validator("reason")
    @classmethod
    def _reason_must_be_real_text(cls, v: str) -> str:
        return _validate_reason(v)


# ─────────────────────── Notification ────────────────────────────────

class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                  int
    user_id:             int
    branch_id:           Optional[int]
    title:               str
    body:                str
    type:                str
    is_read:             bool
    related_entity_type: Optional[str]
    related_entity_id:   Optional[int]
    created_at:          datetime


class NotificationCreate(BaseModel):
    """للاستخدام الداخلي من الـ services"""
    user_id:             int
    branch_id:           Optional[int] = None
    title:               str = Field(..., max_length=200)
    body:                str
    type:                str = Field("info", pattern=r"^(info|warning|alert)$")
    related_entity_type: Optional[str] = Field(None, max_length=50)
    related_entity_id:   Optional[int] = None


# ─────────────────────── AuditLog ────────────────────────────────────

class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:          int
    user_id:     Optional[int]
    branch_id:   Optional[int]
    action:      str
    entity_type: str
    entity_id:   Optional[int]
    old_data:    Optional[str]
    new_data:    Optional[str]
    ip_address:  Optional[str]
    user_agent:  Optional[str]
    # ⚠️ باج حقيقي كان هنا: AuditLog.approved_by (مين وافق بالـ PIN على
    # إجراء حسّاس — إلغاء صنف، تخطي حد فرق كاش...) موجود كعمود DB فعلي
    # (راجع models.py) ومُمرَّر من كل مكان بينادي create_audit_log، لكن
    # AuditLogRead ماكانتش بترجّعه خالص — يعني GET /audit-logs كان مستحيل
    # يوريك مين المدير اللي وافق فعليًا، رغم إن العمود اتسجّل صح في
    # الداتابيز من أول يوم PIN approval اتعمل (2026-07-07). اتكشف أثناء
    # كتابة تست S-06 (وردية بفرق كبير + تخطي بموافقة مدير).
    approved_by: Optional[int] = None
    created_at:  datetime


class AuditLogCreate(BaseModel):
    """للاستخدام الداخلي من الـ services"""
    user_id:     Optional[int] = None
    branch_id:   Optional[int] = None
    action:      str = Field(..., max_length=100)
    entity_type: str = Field(..., max_length=50)
    entity_id:   Optional[int] = None
    old_data:    Optional[str] = None   # JSON string
    new_data:    Optional[str] = None   # JSON string
    ip_address:  Optional[str] = Field(None, max_length=45)
    user_agent:  Optional[str] = Field(None, max_length=500)
    approved_by: Optional[int] = None  # راجع PinCredential — موافقة PIN لإجراء حسّاس


# ─────────────────────── Users ───────────────────────────────────────

# ─────────────────── Staff-app language policy (Gate 3A) ───────────────
# The staff application (frontend/apps/el-kheima) is Arabic/English only —
# Decision 0002. The public guest app keeps its own independent locale list
# (ar/en/ru/it) and is unaffected by this allow-list. Language is a personal
# display preference: it never changes currency, prices, tax, or any
# financial/business configuration.
STAFF_LANGUAGES: tuple[str, ...] = ("ar", "en")
DEFAULT_STAFF_LANGUAGE = "ar"


def normalize_staff_language(value: Optional[str]) -> str:
    """Coerce a stored/legacy ``preferred_language`` into the staff allow-list.

    Old rows may hold ``None`` or a public-only language (``ru``/``it``) that
    the staff app cannot render. The safest, reversible default is Arabic —
    the resort's primary operating language — and it never touches money.
    """
    if not value:
        return DEFAULT_STAFF_LANGUAGE
    candidate = value.strip().lower()
    return candidate if candidate in STAFF_LANGUAGES else DEFAULT_STAFF_LANGUAGE


class UserPreferencesUpdate(BaseModel):
    """Self-service personal preferences (Gate 3A).

    Only the authenticated user's own preferences — the endpoint derives the
    target user from the auth token, so there is deliberately no ``user_id``
    field here. ``extra="forbid"`` rejects mass-assignment / unknown fields
    (e.g. an attempt to smuggle ``role`` or ``is_active``) with HTTP 422.
    """
    model_config = ConfigDict(extra="forbid")

    preferred_language: str = Field(..., max_length=10)

    @field_validator("preferred_language")
    @classmethod
    def _language_must_be_supported(cls, v: str) -> str:
        candidate = v.strip().lower()
        if candidate not in STAFF_LANGUAGES:
            raise ValueError(
                "preferred_language غير مدعومة: لازم تكون واحدة من "
                f"{', '.join(STAFF_LANGUAGES)}"
            )
        return candidate


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                 int
    email:              str
    full_name:          str
    phone:              Optional[str]
    role:               str
    is_active:          bool
    two_factor_enabled: bool
    must_change_password: bool
    two_factor_bootstrap_required: bool
    preferred_language: str
    created_at:          datetime

    @field_validator("preferred_language", mode="before")
    @classmethod
    def _normalize_language(cls, v: Optional[str]) -> str:
        # The current-user contract always reports a staff-renderable language
        # so the frontend can apply it directly; legacy null/public values
        # normalize to the safe default rather than leaking to the UI.
        return normalize_staff_language(v)


class UserCreate(BaseModel):
    """super_admin فقط — إنشاء حساب موظف جديد بدور محدد. الباسورد مؤقت
    (must_change_password=True) بالإجبار — الموظف لازم يغيّره عند أول تسجيل
    دخول. super_admin مش مسموح ينشئه من هنا (Gate: Decision 0003 invariant —
    الحسابات الإدارية تُنشأ بـ admin_bootstrap يدويًا)."""
    email:        str  = Field(..., min_length=5, max_length=255)
    full_name:    str  = Field(..., min_length=2, max_length=255)
    phone:        Optional[str] = Field(None, max_length=50)
    role:         str  = Field(..., max_length=30)
    password:     str  = Field(..., min_length=8, max_length=128,
                                description="باسورد مؤقت — يُجبر على تغييره عند أول دخول")

    @field_validator("role")
    @classmethod
    def _role_must_be_staff(cls, v: str) -> str:
        from app.core.deps import ROLE_LEVELS  # noqa: PLC0415
        if v not in ROLE_LEVELS:
            raise ValueError(
                f"role غير معروف: '{v}' — لازم يكون واحد من: {', '.join(sorted(ROLE_LEVELS))}"
            )
        # super_admin لا يُنشأ من هذا الـ endpoint — يُنشأ يدويًا بـ admin_bootstrap
        if v == "super_admin":
            raise ValueError(
                "لا يمكن إنشاء حساب super_admin من هنا — استخدم admin_bootstrap"
            )
        return v

    @field_validator("email")
    @classmethod
    def _email_format(cls, v: str) -> str:
        from app.core.kernel.security import validate_email_format  # noqa: PLC0415
        if not validate_email_format(v.strip()):
            raise ValueError("صيغة البريد الإلكتروني غير صالحة")
        return v.strip().lower()
class StaffUserCreate(BaseModel):
    """Super-admin-only staff provisioning request.

    ``extra=forbid`` prevents role-adjacent mass assignment. In particular,
    callers cannot supply ``is_active``, password hashes, 2FA state, or a
    super-admin role.
    """
    model_config = ConfigDict(extra="forbid")

    email: str = Field(..., min_length=3, max_length=320)
    full_name: str = Field(..., min_length=3, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    employee_id: Optional[int] = Field(None, gt=0)
    role: Literal[
        "admin", "accountant", "hr_manager", "manager", "supervisor",
        "receptionist", "cashier", "waiter", "chef", "kitchen", "employee",
    ]
    preferred_language: Literal["ar", "en"] = "ar"
    reason: str = Field(..., max_length=_REASON_MAX_LENGTH)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        from app.core.kernel.security import validate_email_format  # noqa: PLC0415

        normalized = value.strip().casefold()
        if not validate_email_format(normalized):
            raise ValueError("صيغة البريد الإلكتروني غير صحيحة")
        return normalized

    @field_validator("full_name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("الاسم الكامل مطلوب")
        return normalized

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, value: Optional[str]) -> Optional[str]:
        normalized = (value or "").strip()
        return normalized or None

    @field_validator("reason")
    @classmethod
    def _reason_must_be_real_text(cls, value: str) -> str:
        return _validate_reason(value)


class StaffUserProvisioned(BaseModel):
    user: UserRead
    temporary_password: str
    enrollment_token: str
    enrollment_expires_at: datetime


class UserRoleUpdate(BaseModel):
    """super_admin فقط — تغيير role و/أو is_active لمستخدم. Gate 2B3A:
    reason إجباري ومحمي بـstep-up (راجع
    docs/audits/gate-2b3a-step-up-control-plane.md)."""
    role:      Optional[str] = Field(None, max_length=30)
    is_active: Optional[bool] = None
    reason:    str = Field(..., max_length=_REASON_MAX_LENGTH)

    @field_validator("reason")
    @classmethod
    def _reason_must_be_real_text(cls, v: str) -> str:
        return _validate_reason(v)

    @field_validator("role")
    @classmethod
    def _role_must_be_known(cls, v: Optional[str]) -> Optional[str]:
        """⚠️ باج حقيقي كان هنا: مفيش أي تحقق إن الـ role المُرسل موجود فعلاً
        في ROLE_LEVELS — أي غلطة إملائية بسيطة (مثلاً "manger" بدل "manager")
        كانت بتتقبل بصمت (200 OK)، والمستخدم يتقفل فعليًا من كل حاجة (
        ROLE_LEVELS.get(user.role, 0) بترجع مستوى 0 لأي endpoint) من غير أي
        رسالة خطأ توضح السبب. اتصلح بتحقق عند استقبال الطلب مباشرة (422) بدل
        قبوله بصمت."""
        if v is not None:
            from app.core.deps import ROLE_LEVELS  # noqa: PLC0415 — تجنب دورة استيراد

            if v not in ROLE_LEVELS:
                raise ValueError(
                    f"role غير معروف: '{v}' — لازم يكون واحد من: {', '.join(sorted(ROLE_LEVELS))}"
                )
        return v


# ─────────────────────── UserPermission ──────────────────────────────
# انظر app/modules/core/models.py::UserPermission للشرح الكامل عن
# resource/action naming scheme و branch scoping.

class UserPermissionBase(BaseModel):
    resource:  str  = Field(..., max_length=100,
                             description='مثال: "finance.void_payment"، "restaurant.void_item"')
    action:    str  = Field(..., max_length=30,
                             pattern=r"^(view|create|edit|delete|void|approve|execute)$")
    allowed:   bool = Field(True, description="True=منح صريح، False=منع صريح")
    branch_id: Optional[int] = Field(None, description="None = كل الفروع")


class UserPermissionCreate(UserPermissionBase):
    pass


class UserPermissionRead(UserPermissionBase):
    model_config = ConfigDict(from_attributes=True)

    id:          int
    user_id:     int
    granted_by:  Optional[int]
    created_at:  datetime


class UserPermissionGrantRequest(UserPermissionBase):
    """للاستخدام من POST /core/permissions — بيحدد المستخدم المستهدف صراحةً.
    Gate 2B3A: reason إجباري ومحمي بـstep-up."""
    user_id: int
    reason:  str = Field(..., max_length=_REASON_MAX_LENGTH)

    @field_validator("reason")
    @classmethod
    def _reason_must_be_real_text(cls, v: str) -> str:
        return _validate_reason(v)


class PermissionRevokeRequest(BaseModel):
    """جسم اختياري لـDELETE /permissions/{id} — DELETE بجسم مش شائع، لكن
    Gate 2B3A محتاج reason إجباري لأي حذف override، وaxios بيدعم body مع
    DELETE عبر {data: {...}}."""
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(..., max_length=_REASON_MAX_LENGTH)

    @field_validator("reason")
    @classmethod
    def _reason_must_be_real_text(cls, v: str) -> str:
        return _validate_reason(v)


class PermissionCatalogEntryRead(BaseModel):
    """صف واحد من كتالوج الصلاحيات — انظر app/modules/core/permission_catalog.py."""
    resource:       str
    action:         str
    label_ar:       str
    label_en:       str
    module:         str
    min_role_level: int
    endpoint:       str


class EffectivePermission(BaseModel):
    """صلاحية واحدة فعلية للمستخدم الحالي — دمج role fallback + أي استثناء
    صريح + استثناء super_admin النشط (Gate 2A، لا يُسقطه أي منع صريح)."""
    resource:       str
    action:         str
    label_ar:       str
    module:         str
    allowed:        bool
    source:         str  # "role" | "explicit" (فيه استثناء صريح) | "super_admin" (نشط، يعدّي أي منع)


# ─────────────────────── GuestAlert ──────────────────────────────────
# راجع app/modules/core/models.py::GuestAlert للشرح الكامل عن ليه context
# generic (مفيش FK).
#
# Gate 8 Phase 1 (2026-07-21): كان الـpattern لسه بيحتوي restaurant_table/
# cafe_table القديمين — الموديولين دول اتحذفوا نهائيًا 2026-07-13 (dining
# حلّ محلهم)، وapps/public's OrderView.vue كان فعليًا بيبعت context_type=
# "dining_table" من الأساس (مش ضمن الـpattern القديم خالص) — يعني أي نداء
# ضيف من طاولة دايننج كان يترفض 422 بصمت طول الوقت، حتى لو GUEST_ALERTS_
# ENABLED اتفعّل. راجع docs/decisions/0001-qr-guest-service-mode.md's
# "known current gaps" — نفس الباج الموثّق هناك، دلوقتي مُصلَّح فعليًا.
_CONTEXT_TYPE_PATTERN = r"^(dining_table|beach_location|room|other)$"
_ALERT_TYPE_PATTERN = r"^(call_waiter|ready_to_order|assistance|request_bill|other)$"


class GuestAlertCreate(BaseModel):
    """Guest request body. Location comes exclusively from X-Guest-Session."""
    model_config = ConfigDict(extra="forbid")

    alert_type: str = Field(..., pattern=_ALERT_TYPE_PATTERN)
    message:    Optional[str] = Field(None, max_length=300)
    outlet_id:  Optional[int] = Field(None, ge=1)
    idempotency_key: Optional[str] = Field(None, min_length=8, max_length=64)


class GuestAlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:           int
    branch_id:    int
    context_type: str
    context_id:   int
    alert_type:   str
    message:      Optional[str]
    status:       str
    public_reference: Optional[str] = None
    location_label: Optional[str] = None
    outlet_id: Optional[int] = None
    outlet_name: Optional[str] = None
    outlet_name_ar: Optional[str] = None
    order_id: Optional[int] = None
    assigned_to: Optional[int] = None
    acknowledged_at: Optional[datetime] = None
    arrived_at: Optional[datetime] = None
    resolved_by:  Optional[int]
    resolved_at:  Optional[datetime]
    created_at:   datetime


class GuestAlertAck(BaseModel):
    """رد التأكيد للضيف بعد إرسال التنبيه — رسالة ودّية زي GuestOrderRead."""
    public_reference: str
    status:   str
    message:  str
    deduplicated: bool = False


class GuestAlertPublicStatus(BaseModel):
    public_reference: str
    alert_type: str
    status: str
    message: Optional[str]
    created_at: datetime
    acknowledged_at: Optional[datetime]
    arrived_at: Optional[datetime]
    resolved_at: Optional[datetime]


class GuestAlertStatusUpdate(BaseModel):
    """طاقم الخدمة بس — الضيف مش بيقدر يحدد status عند الإنشاء (دايمًا open)."""
    status: str = Field(..., pattern=r"^(acknowledged|arrived|resolved)$")


# ─────────────────────── ServiceLocationToken ──────────────────────────
# راجع app/modules/core/models.py::ServiceLocationToken للشرح الكامل.

_LOCATION_TYPE_PATTERN = r"^(dining_table|beach_location|room)$"


class ServiceLocationTokenCreate(BaseModel):
    """للاستخدام من POST /service-location-tokens — موظف مصرَّح له بس
    (manager+، راجع الـrouter)."""
    branch_id:     int
    location_type: str = Field(..., pattern=_LOCATION_TYPE_PATTERN)
    location_id:   int


class ServiceLocationTokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:            int
    token:         str
    branch_id:     int
    location_type: str
    location_id:   int
    is_active:     bool
    created_at:    datetime


class GuestServiceOutletRead(BaseModel):
    id: int
    name: str
    name_ar: Optional[str]
    outlet_type: str


class ServiceLocationRead(BaseModel):
    """رد GET /public/service-location?token=... — السياق المُشتَق من الرمز
    بس، بدون أي بيانات داخلية حسّاسة (لا token تاني، لا created_by، لا
    أي IDs غير location_id نفسه اللي الرمز أصلاً بيمثّله)."""
    location_type: str
    location_label: str
    service_mode: str
    alerts_enabled: bool
    self_order_enabled: bool
    outlets: list[GuestServiceOutletRead] = Field(default_factory=list)


class GuestSessionCreate(BaseModel):
    token: str = Field(..., min_length=20, max_length=64)


class GuestSessionRead(ServiceLocationRead):
    session_token: str
    expires_at: datetime


# ─────────────────────── PIN Credentials ──────────────────────────────

class PinSetRequest(BaseModel):
    """ضبط/تجديد PIN — 4 لـ 6 أرقام بس (زي أي POS حقيقي)."""
    pin: str = Field(..., pattern=r"^\d{4,6}$", description="4-6 أرقام")


class PinCredentialRead(BaseModel):
    """حالة الـ PIN بس — أبدًا مش الـ hash أو الرقم نفسه."""
    model_config = ConfigDict(from_attributes=True)
    user_id:         int
    has_pin:         bool = True
    failed_attempts: int
    is_locked:       bool


class PinSwitchRequest(BaseModel):
    """تبديل هوية المشغّل — راجع core.services.pin_switch_login."""
    user_id: int
    pin:     str = Field(..., pattern=r"^\d{4,6}$")


class PinSwitchResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    user:         UserRead


class ApproverOption(BaseModel):
    """خيار في قائمة "اختر المدير" وقت موافقة PIN — بيانات دنيا، مفيش
    email/PII خالص (مش endpoint إدارة مستخدمين)."""
    model_config = ConfigDict(from_attributes=True)
    id:        int
    full_name: str
    role:      str


# ─────────────────────── Pagination ──────────────────────────────────

class PaginatedResponse(BaseModel):
    """Generic pagination wrapper"""
    total:   int
    page:    int
    size:    int
    items:   list  # يُستبدل بـ Generic في Python 3.12+
