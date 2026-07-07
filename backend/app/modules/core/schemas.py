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
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    """تحديث قيمة setting — يُنشئ إذا لم يكن موجوداً (upsert)"""
    value: str = Field(..., min_length=0)


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

class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                 int
    email:              str
    full_name:          str
    phone:              Optional[str]
    role:               str
    is_active:          bool
    two_factor_enabled: bool
    created_at:          datetime


class UserRoleUpdate(BaseModel):
    """super_admin فقط — تغيير role و/أو is_active لمستخدم."""
    role:      Optional[str] = Field(None, max_length=30)
    is_active: Optional[bool] = None

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
    """للاستخدام من POST /core/permissions — بيحدد المستخدم المستهدف صراحةً."""
    user_id: int


class PermissionCatalogEntryRead(BaseModel):
    """صف واحد من كتالوج الصلاحيات — انظر app/modules/core/permission_catalog.py."""
    resource:       str
    action:         str
    label_ar:       str
    module:         str
    min_role_level: int
    endpoint:       str


class EffectivePermission(BaseModel):
    """صلاحية واحدة فعلية للمستخدم الحالي — دمج role fallback + أي استثناء صريح."""
    resource:       str
    action:         str
    label_ar:       str
    module:         str
    allowed:        bool
    source:         str  # "role" (سلوك افتراضي) أو "explicit" (فيه استثناء صريح)


# ─────────────────────── GuestAlert ──────────────────────────────────
# راجع app/modules/core/models.py::GuestAlert للشرح الكامل عن ليه context
# generic (مفيش FK) وليه context_type بيفرّق بين restaurant_table/cafe_table.

_CONTEXT_TYPE_PATTERN = r"^(restaurant_table|cafe_table|beach_location|room|other)$"
_ALERT_TYPE_PATTERN = r"^(call_waiter|request_bill|other)$"


class GuestAlertCreate(BaseModel):
    """للاستخدام من POST /public/alerts — الضيف بيبعتها بدون auth."""
    branch_id:    int
    context_type: str = Field(..., pattern=_CONTEXT_TYPE_PATTERN)
    context_id:   int
    alert_type:   str = Field(..., pattern=_ALERT_TYPE_PATTERN)
    message:      Optional[str] = Field(None, max_length=300)


class GuestAlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:           int
    branch_id:    int
    context_type: str
    context_id:   int
    alert_type:   str
    message:      Optional[str]
    status:       str
    resolved_by:  Optional[int]
    resolved_at:  Optional[datetime]
    created_at:   datetime


class GuestAlertAck(BaseModel):
    """رد التأكيد للضيف بعد إرسال التنبيه — رسالة ودّية زي GuestOrderRead."""
    alert_id: int
    status:   str
    message:  str


class GuestAlertStatusUpdate(BaseModel):
    """طاقم الخدمة بس — الضيف مش بيقدر يحدد status عند الإنشاء (دايمًا open)."""
    status: str = Field(..., pattern=r"^(acknowledged|resolved)$")


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
