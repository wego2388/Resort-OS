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

from pydantic import BaseModel, ConfigDict, Field


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


# ─────────────────────── Pagination ──────────────────────────────────

class PaginatedResponse(BaseModel):
    """Generic pagination wrapper"""
    total:   int
    page:    int
    size:    int
    items:   list  # يُستبدل بـ Generic في Python 3.12+
