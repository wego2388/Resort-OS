"""
app/modules/core/models.py
═══════════════════════════════════════════════════════════════════════
Core Module Models — always_on
جداول: users, roles, branches, settings, audit_logs, module_states, notifications
═══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wego_core.models.mixins import TimestampMixin
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


# ─────────────────────── ModuleState ─────────────────────────────────

class ModuleState(Base, TimestampMixin):
    """
    Per-branch module state مع fallback لـ global.

    branch_id=NULL → global default (يؤثر على كل الفروع)
    branch_id=X   → per-branch override (يكسب global)

    مثال:
      global:   pms=True  → كل الفروع عندها PMS
      branch:1  pms=False → الفرع 1 بدون PMS رغم global
    """
    __tablename__ = "module_states"
    __table_args__ = (
        UniqueConstraint("module_key", "branch_id", name="uq_module_branch"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    module_key: Mapped[str] = mapped_column(String(50))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    branch_id: Mapped[int | None] = mapped_column(
        ForeignKey("branches.id"), nullable=True, index=True
    )
    changed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )


# ────────────────────────── Notification ─────────────────────────────

class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(20), default="info")  # info|warning|alert
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    related_entity_type: Mapped[str | None] = mapped_column(String(50))
    related_entity_id: Mapped[int | None] = mapped_column(Integer)


# ────────────────────────── AuditLog ─────────────────────────────────

class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100))   # create|update|delete|login|logout
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    old_data: Mapped[str | None] = mapped_column(Text)  # JSON
    new_data: Mapped[str | None] = mapped_column(Text)  # JSON
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(500))
