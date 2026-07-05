"""
app/modules/core/models.py
═══════════════════════════════════════════════════════════════════════
Core Module Models
جداول: users, roles, branches, settings, audit_logs, notifications
═══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.kernel.models.mixins import TimestampMixin
from app.core.database import Base

if TYPE_CHECKING:
    pass


# ────────────────────────── Branch ───────────────────────────────────

class Branch(Base, TimestampMixin):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    name_ar: Mapped[str | None] = mapped_column(String(100))
    code: Mapped[str] = mapped_column(String(20), unique=True)  # BRN-001
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    timezone: Mapped[str] = mapped_column(String(50), default="Africa/Cairo")
    phone: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)
    gm_phone: Mapped[str | None] = mapped_column(String(20))  # للـ Night Audit WhatsApp


# ────────────────────────── Settings ─────────────────────────────────

class Setting(Base, TimestampMixin):
    __tablename__ = "settings"
    __table_args__ = (UniqueConstraint("key", "branch_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100))
    value: Mapped[str] = mapped_column(Text)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    # branch_id=NULL → global setting
    # branch_id=X   → per-branch override


# ────────────────────────── Notification ─────────────────────────────

class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    # list_notifications() always filters by user_id (and often is_read) then
    # sorts by created_at — every one of those was a full table scan with no
    # index at all beyond the primary key.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(20), default="info")  # info|warning|alert
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    related_entity_type: Mapped[str | None] = mapped_column(String(50))
    related_entity_id: Mapped[int | None] = mapped_column(Integer)


# ────────────────────────── AuditLog ─────────────────────────────────

class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # list_audit_logs() (GET /audit-logs) filters on any combination of these
    # four plus a created_at sort — this table only grows (audit logs are
    # never pruned) and had zero indexes beyond the primary key, so every
    # admin query became a slower full table scan as the log grew.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)   # create|update|delete|login|logout
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, index=True)
    old_data: Mapped[str | None] = mapped_column(Text)  # JSON
    new_data: Mapped[str | None] = mapped_column(Text)  # JSON
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(500))


# ────────────────────────── UserPermission ───────────────────────────
# Permission-matrix layer — additive على نظام الـ ROLE_LEVELS الموجود
# (app/core/deps.py). الفكرة:
#   - النظام الافتراضي يبقى role level (waiter=30, cashier=40, ...)
#   - أي مستخدم ممكن ياخد استثناء صريح: منح (allowed=True) أو منع
#     (allowed=False) لـ resource.action معيّن — بيكسب الـ role تماماً
#   - resource = "<module_key>.<sub_area>" (زي "finance.void_payment"،
#     "restaurant.void_item") — نفس أسماء الموديولات المستخدمة في
#     app/main.py::_MODULE_KEYS عشان يفضل introspectable ومتسق
#   - action  = "view"|"create"|"edit"|"delete"|"void"|"approve"|"execute"...
#   - branch_id=NULL → المنحة/المنع سارية على كل الفروع
#     branch_id=X   → سارية على فرع محدد فقط

class UserPermission(Base, TimestampMixin):
    __tablename__ = "user_permissions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "resource", "action", "branch_id",
            name="uq_user_permission_scope",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    resource: Mapped[str] = mapped_column(String(100), index=True)   # e.g. "finance.void_payment"
    action: Mapped[str] = mapped_column(String(30))                  # e.g. "execute"
    allowed: Mapped[bool] = mapped_column(Boolean, default=True)      # True=منح صريح، False=منع صريح
    branch_id: Mapped[int | None] = mapped_column(
        ForeignKey("branches.id"), nullable=True, index=True
    )
    granted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
