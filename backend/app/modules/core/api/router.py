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

  GET    /api/v1/notifications
  PATCH  /api/v1/notifications/{id}/read
  POST   /api/v1/notifications/read-all

  GET    /api/v1/audit-logs

  GET    /api/v1/users
  GET    /api/v1/users/{id}
  PATCH  /api/v1/users/{id}/role

  GET    /api/v1/permissions?user_id=
  POST   /api/v1/permissions
  DELETE /api/v1/permissions/{id}
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.deps import (
    DbDep,
    get_admin_user,
    get_current_active_user,
    get_manager_user,
    get_super_admin_user,
)
from app.modules.core import crud, services
from app.modules.core.schemas import (
    AuditLogRead,
    BranchCreate,
    BranchRead,
    BranchUpdate,
    NotificationRead,
    PaginatedResponse,
    SettingRead,
    SettingUpdate,
    UserPermissionGrantRequest,
    UserPermissionRead,
    UserRead,
    UserRoleUpdate,
)

router = APIRouter(tags=["core"])



# ─────────────────────── Branches ────────────────────────────────────

@router.get(
    "/branches",
    response_model=PaginatedResponse,
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
)
def upsert_setting(
    key: str,
    data: SettingUpdate,
    db: DbDep,
    user=Depends(get_admin_user),
    branch_id: Optional[int] = Query(None),
):
    return services.upsert_setting(db, key, data.value, branch_id, updated_by=user.id)


# ─────────────────────── Notifications ───────────────────────────────

@router.get(
    "/notifications",
    response_model=PaginatedResponse,
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


# ─────────────────────── Permission Matrix ───────────────────────────
# طبقة استثناءات فوق ROLE_LEVELS — انظر app/modules/core/models.py::UserPermission
# و app/core/deps.py::require_permission للشرح الكامل.
# منح/منع صريح: super_admin فقط (ده تحكّم حسّاس بيغيّر صلاحيات فعلية).
# عرض: manager+ (يحتاجها أي مدير يراجع صلاحيات فريقه).

@router.get(
    "/permissions",
    response_model=list[UserPermissionRead],
)
def list_user_permissions(
    db: DbDep,
    _user=Depends(get_manager_user),
    user_id: int = Query(..., description="المستخدم المطلوب عرض صلاحياته"),
):
    rows = services.list_user_permissions(db, user_id)
    return [UserPermissionRead.model_validate(r) for r in rows]


@router.post(
    "/permissions",
    response_model=UserPermissionRead,
    status_code=status.HTTP_201_CREATED,
)
def grant_user_permission(
    data: UserPermissionGrantRequest,
    db: DbDep,
    user=Depends(get_super_admin_user),
):
    from app.modules.core.schemas import UserPermissionCreate  # noqa: PLC0415

    perm_data = UserPermissionCreate(
        resource=data.resource,
        action=data.action,
        allowed=data.allowed,
        branch_id=data.branch_id,
    )
    perm = services.grant_permission(db, data.user_id, perm_data, granted_by=user.id)
    return UserPermissionRead.model_validate(perm)


@router.delete(
    "/permissions/{permission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_user_permission(
    permission_id: int,
    db: DbDep,
    user=Depends(get_super_admin_user),
):
    try:
        services.revoke_permission(db, permission_id, revoked_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
