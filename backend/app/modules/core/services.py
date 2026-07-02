"""
app/modules/core/services.py
═══════════════════════════════════════════════════════════════════════
Business Logic للـ Core Module

القاعدة:
  - يستدعي crud.py للـ DB operations
  - يستدعي module_loader للـ toggle logic
  - يرمي ValueError/PermissionError فقط (لا HTTPException)
  - الـ router يترجم الأخطاء
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import json
from typing import Optional

import redis as redis_lib
from sqlalchemy.orm import Session

from app.core.module_loader import (
    MODULE_REGISTRY,
    get_enabled_modules,
    toggle_module,
)
from app.modules.core import crud
from app.modules.core.models import Branch, Notification
from app.modules.core.schemas import (
    AuditLogCreate,
    BranchCreate,
    BranchUpdate,
    ModuleRead,
    ModuleToggleResult,
    NotificationCreate,
    SettingRead,
)


# ─────────────────────── Branch ──────────────────────────────────────

def get_branch_or_404(db: Session, branch_id: int) -> Branch:
    branch = crud.get_branch(db, branch_id)
    if not branch:
        raise ValueError(f"الفرع {branch_id} غير موجود")
    return branch


def create_branch(
    db: Session,
    data: BranchCreate,
    created_by: Optional[int] = None,
) -> Branch:
    # تحقق من تفرد الـ code
    if crud.get_branch_by_code(db, data.code):
        raise ValueError(f"كود الفرع '{data.code}' مستخدم مسبقاً")

    branch = crud.create_branch(db, data)

    # audit log
    crud.create_audit_log(db, AuditLogCreate(
        user_id=created_by,
        action="create",
        entity_type="branch",
        entity_id=branch.id,
        new_data=json.dumps({"name": branch.name, "code": branch.code}),
    ))

    db.commit()
    db.refresh(branch)
    return branch


def update_branch(
    db: Session,
    branch_id: int,
    data: BranchUpdate,
    updated_by: Optional[int] = None,
) -> Branch:
    branch = get_branch_or_404(db, branch_id)

    old_data = {"name": branch.name, "is_active": branch.is_active}
    branch = crud.update_branch(db, branch, data)

    crud.create_audit_log(db, AuditLogCreate(
        user_id=updated_by,
        entity_type="branch",
        entity_id=branch.id,
        action="update",
        old_data=json.dumps(old_data),
        new_data=json.dumps(data.model_dump(exclude_unset=True)),
    ))

    db.commit()
    db.refresh(branch)
    return branch


def delete_branch(
    db: Session,
    branch_id: int,
    deleted_by: Optional[int] = None,
) -> None:
    branch = get_branch_or_404(db, branch_id)

    crud.create_audit_log(db, AuditLogCreate(
        user_id=deleted_by,
        action="delete",
        entity_type="branch",
        entity_id=branch.id,
        old_data=json.dumps({"name": branch.name, "code": branch.code}),
    ))

    crud.delete_branch(db, branch)
    db.commit()


# ─────────────────────── Users ───────────────────────────────────────

def update_user_role(
    db: Session,
    user_id: int,
    role: Optional[str],
    is_active: Optional[bool],
    updated_by: int,
):
    """super_admin فقط. أي تغيير في role أو is_active يُبطل التوكنات الحالية
    للمستخدم فوراً (revoke_user_tokens) — وإلا يستمر بصلاحياته القديمة حتى
    انتهاء التوكن طبيعياً."""
    from app.core.deps import revoke_user_tokens  # noqa: PLC0415

    user = crud.get_user(db, user_id)
    if not user:
        raise ValueError(f"المستخدم {user_id} غير موجود")

    old_data = {"role": user.role, "is_active": user.is_active}
    changed = False

    if role is not None and role != user.role:
        user.role = role
        changed = True
    if is_active is not None and is_active != user.is_active:
        user.is_active = is_active
        changed = True

    if changed:
        crud.create_audit_log(db, AuditLogCreate(
            user_id=updated_by,
            entity_type="user",
            entity_id=user.id,
            action="update_role",
            old_data=json.dumps(old_data),
            new_data=json.dumps({"role": role, "is_active": is_active}),
        ))
        revoke_user_tokens(user.id)

    db.commit()
    db.refresh(user)
    return user


# ─────────────────────── Settings ────────────────────────────────────

def get_setting_value(
    db: Session,
    key: str,
    branch_id: Optional[int] = None,
    default: Optional[str] = None,
) -> Optional[str]:
    """يُرجع القيمة مباشرة أو الـ default"""
    row = crud.get_setting(db, key, branch_id)
    return row.value if row else default


def upsert_setting(
    db: Session,
    key: str,
    value: str,
    branch_id: Optional[int] = None,
    updated_by: Optional[int] = None,
) -> SettingRead:
    old_row = crud.get_setting(db, key, branch_id)
    old_value = old_row.value if old_row else None

    row = crud.upsert_setting(db, key, value, branch_id)

    crud.create_audit_log(db, AuditLogCreate(
        user_id=updated_by,
        branch_id=branch_id,
        action="update",
        entity_type="setting",
        entity_id=row.id,
        old_data=json.dumps({"value": old_value}),
        new_data=json.dumps({"value": value}),
    ))

    db.commit()
    db.refresh(row)
    return SettingRead.model_validate(row)


# ─────────────────────── Module Toggle ───────────────────────────────

def get_all_modules(
    db: Session,
    redis_client: redis_lib.Redis,
    branch_id: Optional[int] = None,
) -> list[ModuleRead]:
    """
    يُرجع كل الـ modules مع حالتها.
    يدمج MODULE_REGISTRY (تعريف) + DB (حالة) + Redis cache.
    """
    enabled_set = get_enabled_modules(db, redis_client, branch_id)

    result = []
    for key, defn in sorted(MODULE_REGISTRY.items(), key=lambda x: x[1].nav_order):
        result.append(ModuleRead(
            key=key,
            name_ar=defn.name_ar,
            name_en=defn.name_en,
            always_on=defn.always_on,
            enabled=key in enabled_set,
            default_enabled=defn.default_enabled,
            depends_on=list(defn.depends_on),
            icon=defn.icon,
            nav_order=defn.nav_order,
        ))
    return result


def toggle_module_state(
    db: Session,
    redis_client: redis_lib.Redis,
    module_key: str,
    enable: bool,
    branch_id: Optional[int] = None,
    changed_by: Optional[int] = None,
) -> ModuleToggleResult:
    """
    يفعّل/يعطّل module.
    يرمي ValueError إذا:
      - الـ module غير موجود
      - always_on
      - تعطيل module يعتمد عليه modules أخرى مفعّلة
    """
    result = toggle_module(
        key=module_key,
        enable=enable,
        db=db,
        redis_client=redis_client,
        branch_id=branch_id,
        changed_by=changed_by,
    )

    # audit log
    crud.create_audit_log(db, AuditLogCreate(
        user_id=changed_by,
        branch_id=branch_id,
        action="toggle",
        entity_type="module",
        new_data=json.dumps({"module": module_key, "enabled": enable}),
    ))

    return ModuleToggleResult(**result)


# ─────────────────────── Notification ────────────────────────────────

def create_notification(
    db: Session,
    data: NotificationCreate,
) -> Notification:
    notif = crud.create_notification(db, data)
    db.commit()
    db.refresh(notif)
    return notif


def mark_notification_read(
    db: Session,
    notification_id: int,
    requesting_user_id: int,
) -> Notification:
    """يتحقق أن المستخدم يملك الإشعار"""
    notif = crud.get_notification(db, notification_id)
    if not notif:
        raise ValueError(f"الإشعار {notification_id} غير موجود")
    if notif.user_id != requesting_user_id:
        raise PermissionError("لا يمكنك تعديل إشعار لمستخدم آخر")

    notif = crud.mark_notification_read(db, notif)
    db.commit()
    db.refresh(notif)
    return notif


def mark_all_read(
    db: Session,
    user_id: int,
    branch_id: Optional[int] = None,
) -> int:
    count = crud.mark_all_notifications_read(db, user_id, branch_id)
    db.commit()
    return count
