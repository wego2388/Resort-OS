"""
app/modules/core/api/router.py
═══════════════════════════════════════════════════════════════════════
Core Module API Router — always_on

Endpoints:
  GET    /api/v1/branches
  POST   /api/v1/branches
  GET    /api/v1/branches/{id}
  PATCH  /api/v1/branches/{id}
  DELETE /api/v1/branches/{id}

  GET    /api/v1/settings
  GET    /api/v1/settings/{key}
  PUT    /api/v1/settings/{key}

  GET    /api/v1/modules
  POST   /api/v1/modules/{key}/toggle

  GET    /api/v1/notifications
  PATCH  /api/v1/notifications/{id}/read
  POST   /api/v1/notifications/read-all

  GET    /api/v1/audit-logs

  GET    /api/v1/users
  GET    /api/v1/users/{id}
  PATCH  /api/v1/users/{id}/role
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from typing import Annotated, Optional

import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import (
    DbDep,
    RedisDep,
    get_admin_user,
    get_current_active_user,
    get_manager_user,
    get_super_admin_user,
    require_module,
)
from app.modules.core import crud, services
from app.modules.core.schemas import (
    AuditLogRead,
    BranchCreate,
    BranchRead,
    BranchUpdate,
    ModuleRead,
    ModuleToggle,
    ModuleToggleResult,
    NotificationCreate,
    NotificationRead,
    PaginatedResponse,
    SettingRead,
    SettingUpdate,
    UserRead,
    UserRoleUpdate,
)

router = APIRouter(tags=["core"])

# core هو always_on — require_module يمر فوراً بدون DB check
_module_guard = Depends(require_module("core"))


# ─────────────────────── Branches ────────────────────────────────────

@router.get(
    "/branches",
    response_model=PaginatedResponse,
    dependencies=[_module_guard],
)
def list_branches(
    db: DbDep,
    _user=Depends(get_current_active_user),
    active_only: bool = Query(False),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    skip = (page - 1) * size
    items, total = crud.list_branches(db, active_only=active_only, skip=skip, limit=size)
    return PaginatedResponse(
        total=total,
        page=page,
        size=size,
        items=[BranchRead.model_validate(b) for b in items],
    )


@router.post(
    "/branches",
    response_model=BranchRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_module_guard],
)
def create_branch(
    data: BranchCreate,
    request: Request,
    db: DbDep,
    user=Depends(get_admin_user),
):
    try:
        return services.create_branch(db, data, created_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get(
    "/branches/{branch_id}",
    response_model=BranchRead,
    dependencies=[_module_guard],
)
def get_branch(
    branch_id: int,
    db: DbDep,
    _user=Depends(get_current_active_user),
):
    branch = crud.get_branch(db, branch_id)
    if not branch:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"الفرع {branch_id} غير موجود")
    return branch


@router.patch(
    "/branches/{branch_id}",
    response_model=BranchRead,
    dependencies=[_module_guard],
)
def update_branch(
    branch_id: int,
    data: BranchUpdate,
    db: DbDep,
    user=Depends(get_manager_user),
):
    try:
        return services.update_branch(db, branch_id, data, updated_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.delete(
    "/branches/{branch_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_module_guard],
)
def delete_branch(
    branch_id: int,
    db: DbDep,
    user=Depends(get_super_admin_user),
):
    try:
        services.delete_branch(db, branch_id, deleted_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ─────────────────────── Settings ────────────────────────────────────

@router.get(
    "/settings",
    response_model=list[SettingRead],
    dependencies=[_module_guard],
)
def list_settings(
    db: DbDep,
    user=Depends(get_manager_user),
    branch_id: Optional[int] = Query(None),
):
    rows = crud.list_settings(db, branch_id=branch_id)
    return [SettingRead.model_validate(r) for r in rows]


@router.get(
    "/settings/{key}",
    response_model=SettingRead,
    dependencies=[_module_guard],
)
def get_setting(
    key: str,
    db: DbDep,
    _user=Depends(get_current_active_user),
    branch_id: Optional[int] = Query(None),
):
    row = crud.get_setting(db, key, branch_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Setting '{key}' غير موجود")
    return SettingRead.model_validate(row)


@router.put(
    "/settings/{key}",
    response_model=SettingRead,
    dependencies=[_module_guard],
)
def upsert_setting(
    key: str,
    data: SettingUpdate,
    db: DbDep,
    user=Depends(get_admin_user),
    branch_id: Optional[int] = Query(None),
):
    return services.upsert_setting(db, key, data.value, branch_id, updated_by=user.id)


# ─────────────────────── Modules ─────────────────────────────────────

@router.get(
    "/modules",
    response_model=list[ModuleRead],
    dependencies=[_module_guard],
)
def list_modules(
    db: DbDep,
    redis_client: RedisDep,
    _user=Depends(get_current_active_user),
    branch_id: Optional[int] = Query(None),
):
    return services.get_all_modules(db, redis_client, branch_id)


@router.post(
    "/modules/{module_key}/toggle",
    response_model=ModuleToggleResult,
    dependencies=[_module_guard],
)
def toggle_module(
    module_key: str,
    data: ModuleToggle,
    db: DbDep,
    redis_client: RedisDep,
    user=Depends(get_super_admin_user),
):
    try:
        return services.toggle_module_state(
            db=db,
            redis_client=redis_client,
            module_key=module_key,
            enable=data.enable,
            branch_id=data.branch_id,
            changed_by=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ─────────────────────── Notifications ───────────────────────────────

@router.get(
    "/notifications",
    response_model=PaginatedResponse,
    dependencies=[_module_guard],
)
def list_notifications(
    db: DbDep,
    user=Depends(get_current_active_user),
    unread_only: bool = Query(False),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    skip = (page - 1) * size
    items, total = crud.list_notifications(
        db,
        user_id=user.id,
        unread_only=unread_only,
        skip=skip,
        limit=size,
    )
    return PaginatedResponse(
        total=total,
        page=page,
        size=size,
        items=[NotificationRead.model_validate(n) for n in items],
    )


@router.patch(
    "/notifications/{notification_id}/read",
    response_model=NotificationRead,
    dependencies=[_module_guard],
)
def mark_notification_read(
    notification_id: int,
    db: DbDep,
    user=Depends(get_current_active_user),
):
    try:
        notif = services.mark_notification_read(db, notification_id, user.id)
        return NotificationRead.model_validate(notif)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))


@router.post(
    "/notifications/read-all",
    dependencies=[_module_guard],
)
def mark_all_notifications_read(
    db: DbDep,
    user=Depends(get_current_active_user),
    branch_id: Optional[int] = Query(None),
):
    count = services.mark_all_read(db, user.id, branch_id)
    return {"marked_read": count}


# ─────────────────────── Audit Logs ──────────────────────────────────

@router.get(
    "/audit-logs",
    response_model=PaginatedResponse,
    dependencies=[_module_guard],
)
def list_audit_logs(
    db: DbDep,
    _user=Depends(get_manager_user),
    branch_id: Optional[int] = Query(None),
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    skip = (page - 1) * size
    items, total = crud.list_audit_logs(
        db,
        branch_id=branch_id,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        action=action,
        skip=skip,
        limit=size,
    )
    return PaginatedResponse(
        total=total,
        page=page,
        size=size,
        items=[AuditLogRead.model_validate(log) for log in items],
    )


# ─────────────────────── Users ───────────────────────────────────────
# super_admin فقط — تغيير role/is_active يُبطل توكنات المستخدم فوراً
# (revoke_user_tokens في services.update_user_role).

@router.get(
    "/users",
    response_model=PaginatedResponse,
    dependencies=[_module_guard],
)
def list_users(
    db: DbDep,
    _user=Depends(get_super_admin_user),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    skip = (page - 1) * size
    items, total = crud.list_users(db, skip=skip, limit=size)
    return PaginatedResponse(
        total=total,
        page=page,
        size=size,
        items=[UserRead.model_validate(u) for u in items],
    )


@router.get(
    "/users/{user_id}",
    response_model=UserRead,
    dependencies=[_module_guard],
)
def get_user(
    user_id: int,
    db: DbDep,
    _user=Depends(get_super_admin_user),
):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"المستخدم {user_id} غير موجود")
    return UserRead.model_validate(user)


@router.patch(
    "/users/{user_id}/role",
    response_model=UserRead,
    dependencies=[_module_guard],
)
def update_user_role(
    user_id: int,
    data: UserRoleUpdate,
    db: DbDep,
    user=Depends(get_super_admin_user),
):
    try:
        updated = services.update_user_role(
            db, user_id, role=data.role, is_active=data.is_active, updated_by=user.id,
        )
        return UserRead.model_validate(updated)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
