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
  GET    /api/v1/permissions/catalog
  GET    /api/v1/permissions/me

  POST   /api/v1/public/alerts             (بدون auth — الضيف)
  GET    /api/v1/alerts                    (طاقم الخدمة)
  PATCH  /api/v1/alerts/{id}/status        (طاقم الخدمة)
  WS     /api/v1/ws/alerts/{branch_id}     (بث لحظي لطاقم الخدمة)

  POST   /api/v1/service-location-tokens        (مدير+ — توليد/تدوير)
  GET    /api/v1/service-location-tokens        (مدير+ — الرموز الفعّالة لفرع)
  GET    /api/v1/public/service-location        (بدون auth — الضيف يحلّل QR)
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from typing import Optional

from fastapi import (
    APIRouter, Depends, Header, HTTPException, Query, Request, WebSocket,
    WebSocketDisconnect, status,
)

from app.core.deps import (
    DbDep,
    get_admin_user,
    get_cashier_user,
    get_current_active_user,
    get_manager_user,
    get_super_admin_user,
    get_waiter_user,
    get_websocket_user,
    user_level,
)
from app.modules.core import crud, services
from app.modules.core.permission_catalog import PERMISSION_CATALOG
from app.modules.core.schemas import (
    ApproverOption,
    AuditLogRead,
    BranchCreate,
    BranchRead,
    BranchUpdate,
    EffectivePermission,
    GuestAlertAck,
    GuestAlertCreate,
    GuestAlertPublicStatus,
    GuestAlertRead,
    GuestAlertStatusUpdate,
    GuestSessionCreate,
    GuestSessionRead,
    NotificationRead,
    PaginatedResponse,
    PermissionCatalogEntryRead,
    PermissionRevokeRequest,
    PinCredentialRead,
    PinSetRequest,
    PinSwitchRequest,
    PinSwitchResponse,
    ServiceLocationRead,
    ServiceLocationTokenCreate,
    ServiceLocationTokenRead,
    SettingRead,
    SettingUpdate,
    UserPermissionGrantRequest,
    UserPermissionRead,
    UserRead,
    UserRoleUpdate,
)

router = APIRouter(tags=["core"])


# ── Gate 2B3A — step-up consumption helper ──────────────────────────────
# مشترك بين الأربعة endpoints المحمية (PATCH /users/{id}/role، POST
# /permissions، DELETE /permissions/{id}، PUT /settings/{key}). كل endpoint
# لسه هو المسؤول عن بناء الـscope_hash من الـpayload الفعلي بتاعه (مش
# dependency عامة بتعرف الـpurpose بس زي ما طلب محمد صراحة) — الدالة دي
# بس بتستهلك الـtoken وتترجم النتيجة لأكواد HTTP، بعد ما الـendpoint يجهّز
# كل حاجة.

# Gate 4 (جولة مراجعة Codex الأولى — M5a): الدالة دي بقت مشتركة فعليًا
# (finance/dining بقى عندهم أفعال محتاجة step-up برضو) — راجع
# app.modules.core.api.step_up_utils لمنع تكرار نفس منطق الاستهلاك/الترجمة
# لـHTTP في كل موديول بيحتاجه (CLAUDE.md §3.5).
from app.modules.core.api.step_up_utils import consume_step_up_or_raise as _consume_step_up_or_raise  # noqa: E402


def _require_branch_or_global_read(db, user, branch_id: Optional[int], action_desc: str) -> None:
    """Gate 2B3A: قراءة إعدادات فرع تحتاج manager+ وعزل فرع حقيقي server-
    side؛ قراءة الإعدادات العامة (branch_id غير مُرسَل خالص) تحتاج
    super_admin فقط. لا تثق في branch_id القادم من الواجهة — دايمًا
    assert_branch_access بدل مقارنة مباشرة."""
    if branch_id is None:
        if user_level(user) < 100:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "الإعدادات العامة (Global) متاحة فقط لحساب super_admin",
            )
        return
    try:
        services.assert_branch_access(db, user, branch_id, action_desc)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))


def _require_branch_or_global_write(db, user, branch_id: Optional[int], action_desc: str) -> None:
    """نفس فحص القراءة، لكن الكتابة أصلًا محمية بـget_admin_user على
    مستوى الـrouter dependency — الفحص هنا لعزل الفرع نفسه بس، مش تكرار
    فحص الـrole."""
    if branch_id is None:
        if user_level(user) < 100:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "الإعدادات العامة (Global) قابلة للتعديل فقط من super_admin",
            )
        return
    try:
        services.assert_branch_access(db, user, branch_id, action_desc)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))


# ── WebSocket Guest-Alerts Manager ─────────────────────────────────────
# نفس نمط dining_manager (app/modules/dining/api/router.py) —
# بث بسيط بالفرع، من غير أي بروتوكول ثنائي الاتجاه حقيقي. auth بقى موحّد
# عبر get_websocket_user (wagdy.md A-01) — ?token= JWT صالح إجباري.

class AlertConnectionManager:
    def __init__(self):
        self.active: dict[str, list[WebSocket]] = {}  # branch_id → قائمة اتصالات WS

    async def connect(self, ws: WebSocket, branch_id: str):
        await ws.accept()
        self.active.setdefault(branch_id, []).append(ws)

    def disconnect(self, ws: WebSocket, branch_id: str):
        connections = self.active.get(branch_id, [])
        if ws in connections:
            connections.remove(ws)

    async def broadcast(self, branch_id: str, data: dict):
        for ws in list(self.active.get(branch_id, [])):
            try:
                await ws.send_json(data)
            except Exception:
                pass


alerts_manager = AlertConnectionManager()


@router.websocket("/ws/alerts/{branch_id}")
async def guest_alerts_websocket(ws: WebSocket, branch_id: int, db: DbDep):
    """اتصال WebSocket لطاقم الخدمة (نادل/كاشير) — بث تنبيهات الضيوف الجديدة
    وتحديثات حالتها لحظيًا. بيرد بـ pong كـ heartbeat فقط، زي restaurant KDS.
    محتاج ?token= JWT صالح بمستوى نادل+، وبقى (Gate 1 containment، جولة
    تصحيح ثانية) بيتحقق كمان إن الفرع ده فرع المستخدم نفسه — نفس باج
    GET/PATCH /alerts الأصلي، كان أي نادل يقدر يشترك في بث فرع تاني تمامًا."""
    user = await get_websocket_user(ws, db, min_level=30)
    if not user:
        return
    try:
        services.assert_branch_access(db, user, branch_id, "الاشتراك في تنبيهات فرع")
    except PermissionError:
        await ws.close(code=4403)
        return
    await alerts_manager.connect(ws, str(branch_id))
    try:
        while True:
            await ws.receive_text()
            await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        alerts_manager.disconnect(ws, str(branch_id))



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
    """Gate 2B3A: عزل فرع حقيقي server-side بدل الثقة في branch_id القادم
    من الواجهة. branch_id مُرسَل → يطابق فرع المنفّذ الفعلي (Employee
    link) أو super_admin. branch_id مش مُرسَل خالص → الإعدادات العامة
    (Global)، متاحة لـsuper_admin فقط — راجع
    docs/audits/gate-2b3a-step-up-control-plane.md."""
    _require_branch_or_global_read(db, user, branch_id, "عرض إعدادات هذا الفرع")
    rows = crud.list_settings(db, branch_id=branch_id)
    return [SettingRead.model_validate(r) for r in rows]


@router.get(
    "/settings/{key}",
    response_model=SettingRead,
)
def get_setting(
    key: str,
    db: DbDep,
    user=Depends(get_manager_user),
    branch_id: Optional[int] = Query(None),
):
    """كانت مفتوحة لأي مستخدم نشط (get_current_active_user) — بقت
    manager+ زي القائمة، بنفس عزل الفرع.

    **تصحيح (مراجعة Codex المستقلة، 2026-07-18):** النسخة الأولى كانت
    بتستخدم crud.get_setting() (بتعمل fallback ضمني للإعداد العام لو
    مفيش صف خاص بالفرع) — يعني مدير فرع حقيقي بيسأل عن مفتاح مش موجود
    لفرعه كان بياخد صف الإعداد العام (branch_id=null) بصمت، رغم إن فحص
    عزل الفرع فوق كان بيتحقق من الفرع المطلوب مش من مصدر الصف الراجع.
    دلوقتي بتستخدم get_setting_exact() (بدون أي fallback) — مطابقة تامة
    على (key, branch_id) بس. الـfallback الداخلي (تسعير الشاطئ وغيره)
    لسه موجود في get_setting_value()/crud.get_setting() العادية، مش هنا."""
    _require_branch_or_global_read(db, user, branch_id, "عرض إعداد هذا الفرع")
    row = crud.get_setting_exact(db, key, branch_id)
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
    request: Request,
    user=Depends(get_admin_user),
    branch_id: Optional[int] = Query(None),
    x_step_up_token: Optional[str] = Header(default=None, alias="X-Step-Up-Token"),
):
    """Gate 2B3A: عزل فرع حقيقي (زي القراءة) + step-up إجباري + reason
    إجباري (SettingUpdate.reason). الكتابة على الإعدادات العامة
    (branch_id=None) لسه تحتاج super_admin تحديدًا، فوق get_admin_user
    الأساسية."""
    _require_branch_or_global_write(db, user, branch_id, "تعديل إعدادات هذا الفرع")

    from app.core.kernel.auth.step_up import setting_upsert_scope  # noqa: PLC0415

    scope_hash = setting_upsert_scope(
        key=key, branch_id=branch_id, value=data.value, reason=data.reason,
    )
    step_up = _consume_step_up_or_raise(
        db, user, request,
        purpose="setting_upsert", scope_hash=scope_hash, x_step_up_token=x_step_up_token,
    )
    try:
        return services.upsert_setting(
            db, key, data.value, branch_id, updated_by=user.id,
            reason=data.reason,
            step_up_public_reference=step_up["public_reference"],
            assurance_method=step_up["assurance_method"],
        )
    except services.ActorAuthorizationChangedError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"error_code": "ACTOR_AUTHORIZATION_CHANGED", "message": str(exc)},
        )


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
# GET /users مدير+ (شاشة الصلاحيات محتاجة قائمة المستخدمين). تغيير
# role/is_active يفضل super_admin فقط — بيُبطل توكنات المستخدم فوراً
# (revoke_user_tokens في services.update_user_role).

@router.get(
    "/users",
    response_model=PaginatedResponse,
)
def list_users(
    db: DbDep,
    _user=Depends(get_manager_user),
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
    request: Request,
    user=Depends(get_super_admin_user),
    x_step_up_token: Optional[str] = Header(default=None, alias="X-Step-Up-Token"),
):
    """كود الأخطاء الدقيق (Gate 2A، Decision 0003 invariants) موثّق في
    docs/audits/gate-2a-super-admin-invariants.md — كل حالة مربوطة بـ
    exception class مخصصة، مش ValueError عام بيتحول لـ404 بالغلط.

    Gate 2B3A: step-up إجباري (تغيير role/is_active من أخطر عمليات
    التحكم في النظام) + reason إجباري (UserRoleUpdate.reason)."""
    from app.core.kernel.auth.step_up import user_role_update_scope  # noqa: PLC0415

    scope_hash = user_role_update_scope(
        user_id=user_id, role=data.role, is_active=data.is_active, reason=data.reason,
    )
    step_up = _consume_step_up_or_raise(
        db, user, request,
        purpose="user_role_update", scope_hash=scope_hash, x_step_up_token=x_step_up_token,
    )
    try:
        updated = services.update_user_role(
            db, user_id, role=data.role, is_active=data.is_active, updated_by=user.id,
            reason=data.reason,
            step_up_public_reference=step_up["public_reference"],
            assurance_method=step_up["assurance_method"],
        )
        return UserRead.model_validate(updated)
    except services.UserNotFoundError as exc:
        # ملحوظة: الـkernel's global @app.exception_handler(404) (راجع
        # app/core/kernel/errors.py) بيفلطح أي 404 في المشروع كله لـ
        # {"error_code": "not_found", "message": <detail>} — مفيش أي طريقة
        # لعرض error_code مخصص على 404 تحديدًا من غير تعديل هندلر عام يأثر
        # على كل endpoint في التطبيق (خارج نطاق Gate 2A). detail هنا لازم
        # يفضل نص عادي (نفس نمط كل 404 تاني في المشروع)، مش dict.
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except services.SuperAdminSelfLockoutForbiddenError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"error_code": "SUPER_ADMIN_SELF_LOCKOUT_FORBIDDEN", "message": str(exc)},
        )
    except services.LastActiveSuperAdminRequiredError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"error_code": "LAST_ACTIVE_SUPER_ADMIN_REQUIRED", "message": str(exc)},
        )
    except services.ActorSuperAdminPrivilegesChangedError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"error_code": "ACTOR_SUPER_ADMIN_PRIVILEGES_CHANGED", "message": str(exc)},
        )
    except services.MandatoryTwoFactorEnrollmentRequiredError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"error_code": "MANDATORY_2FA_ENROLLMENT_REQUIRED", "message": str(exc)},
        )


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
    request: Request,
    user=Depends(get_super_admin_user),
    x_step_up_token: Optional[str] = Header(default=None, alias="X-Step-Up-Token"),
):
    """Gate 2A: كانت هذه الدالة من غير أي try/except خالص — أي ValueError
    مستقبلي كان هيوصل لـSecureErrorMiddleware ويترجم 500 غامض بدل كود HTTP
    دقيق. دلوقتي بتمسك exceptions محددة (راجع
    docs/audits/gate-2a-super-admin-invariants.md).

    Gate 2B3A: step-up إجباري + reason إجباري
    (UserPermissionGrantRequest.reason)."""
    from app.core.kernel.auth.step_up import permission_override_upsert_scope  # noqa: PLC0415
    from app.modules.core.schemas import UserPermissionCreate  # noqa: PLC0415

    perm_data = UserPermissionCreate(
        resource=data.resource,
        action=data.action,
        allowed=data.allowed,
        branch_id=data.branch_id,
    )
    scope_hash = permission_override_upsert_scope(
        user_id=data.user_id, resource=data.resource, action=data.action,
        allowed=data.allowed, branch_id=data.branch_id, reason=data.reason,
    )
    step_up = _consume_step_up_or_raise(
        db, user, request,
        purpose="permission_override_upsert", scope_hash=scope_hash,
        x_step_up_token=x_step_up_token,
    )
    try:
        perm = services.grant_permission(
            db, data.user_id, perm_data, granted_by=user.id,
            reason=data.reason,
            step_up_public_reference=step_up["public_reference"],
            assurance_method=step_up["assurance_method"],
        )
    except services.UserNotFoundError as exc:
        # ملحوظة: الـkernel's global @app.exception_handler(404) (راجع
        # app/core/kernel/errors.py) بيفلطح أي 404 في المشروع كله لـ
        # {"error_code": "not_found", "message": <detail>} — مفيش أي طريقة
        # لعرض error_code مخصص على 404 تحديدًا من غير تعديل هندلر عام يأثر
        # على كل endpoint في التطبيق (خارج نطاق Gate 2A). detail هنا لازم
        # يفضل نص عادي (نفس نمط كل 404 تاني في المشروع)، مش dict.
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except services.SuperAdminPermissionOverrideForbiddenError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"error_code": "SUPER_ADMIN_PERMISSION_OVERRIDE_FORBIDDEN", "message": str(exc)},
        )
    except services.ActorAuthorizationChangedError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"error_code": "ACTOR_AUTHORIZATION_CHANGED", "message": str(exc)},
        )
    return UserPermissionRead.model_validate(perm)


@router.get(
    "/permissions/catalog",
    response_model=list[PermissionCatalogEntryRead],
)
def get_permission_catalog(_user=Depends(get_manager_user)):
    """كتالوج كل الصلاحيات التفصيلية القابلة للمنح/المنع — الفرونت إند
    بيستخدمه لبناء شاشة إدارة الصلاحيات من غير ما يعرف الـ resource strings
    مقدّمًا. مسجّل قبل /{permission_id} عمداً — نفس سبب restaurant.hold_order."""
    return [PermissionCatalogEntryRead(**entry) for entry in PERMISSION_CATALOG]


@router.get(
    "/permissions/me",
    response_model=list[EffectivePermission],
)
def get_my_effective_permissions(db: DbDep, user=Depends(get_current_active_user)):
    """صلاحيات المستخدم الحالي الفعلية (role fallback + أي استثناء صريح) —
    الفرونت إند بيستخدمها لإخفاء/إظهار أزرار العمليات الحسّاسة."""
    return services.get_effective_permissions(db, user)


@router.delete(
    "/permissions/{permission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_user_permission(
    permission_id: int,
    data: PermissionRevokeRequest,
    db: DbDep,
    request: Request,
    user=Depends(get_super_admin_user),
    x_step_up_token: Optional[str] = Header(default=None, alias="X-Step-Up-Token"),
):
    """Gate 2B3A: DELETE بجسم طلب (مش شائع لكن أنضف مع Axios من custom
    header لـreason حر — راجع PermissionRevokeRequest) + step-up إجباري."""
    from app.core.kernel.auth.step_up import permission_override_revoke_scope  # noqa: PLC0415

    scope_hash = permission_override_revoke_scope(
        permission_id=permission_id, reason=data.reason,
    )
    step_up = _consume_step_up_or_raise(
        db, user, request,
        purpose="permission_override_revoke", scope_hash=scope_hash,
        x_step_up_token=x_step_up_token,
    )
    try:
        services.revoke_permission(
            db, permission_id, revoked_by=user.id,
            reason=data.reason,
            step_up_public_reference=step_up["public_reference"],
            assurance_method=step_up["assurance_method"],
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except services.ActorAuthorizationChangedError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"error_code": "ACTOR_AUTHORIZATION_CHANGED", "message": str(exc)},
        )


# ══════════════════════════════════════════════════════════════════════
# Guest Alerts — قناة تنبيه يبدأها الضيف بدون تسجيل دخول
# ══════════════════════════════════════════════════════════════════════
# Public guest requests do not require an employee account, but Gate 8 requires
# a short-lived X-Guest-Session capability. They are rate-limited and the
# location/status cannot be supplied by the browser.
#
# GET /alerts و PATCH /alerts/{id}/status لطاقم الخدمة (نادل فأعلى — نفس
# مستوى list_held_orders في restaurant، دي حركة تشغيل يومية مش مالية).
# ══════════════════════════════════════════════════════════════════════

@router.post(
    "/public/alerts",
    response_model=GuestAlertAck,
    status_code=status.HTTP_201_CREATED,
    tags=["core-public"],
    summary="تنبيه من الضيف (نادِ الجرسون / هات الفاتورة) — بدون auth",
)
async def create_guest_alert(
    data: GuestAlertCreate,
    db: DbDep,
    x_guest_session: str = Header(..., alias="X-Guest-Session"),
):
    """Compatibility alias; Gate 8 still requires the guest-session header."""
    return await create_guest_request(data, db, x_guest_session)


@router.post(
    "/public/guest-requests",
    response_model=GuestAlertAck,
    status_code=status.HTTP_201_CREATED,
    tags=["core-public"],
    summary="طلب خدمة من جلسة QR صالحة",
)
async def create_guest_request(
    data: GuestAlertCreate,
    db: DbDep,
    x_guest_session: str = Header(..., alias="X-Guest-Session"),
):
    try:
        alert, created = services.create_guest_alert(
            db, x_guest_session, data.alert_type, data.message,
            outlet_id=data.outlet_id, idempotency_key=data.idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    if created:
        await alerts_manager.broadcast(str(alert.branch_id), {
            "type": "new_alert",
            "alert": services.guest_alert_read(db, alert).model_dump(mode="json"),
        })

    return GuestAlertAck(
        public_reference=alert.public_reference,
        status=alert.status,
        message="تم إرسال طلبك — سيصل إليك أحد أفراد الطاقم فورًا 🙌"
        if alert.alert_type != "request_bill"
        else "تم طلب الفاتورة — سيتم إحضارها فورًا 🧾",
        deduplicated=not created,
    )


@router.get(
    "/public/guest-requests/{public_reference}",
    response_model=GuestAlertPublicStatus,
    tags=["core-public"],
)
def get_guest_request_status(
    public_reference: str,
    db: DbDep,
    x_guest_session: str = Header(..., alias="X-Guest-Session"),
):
    try:
        return services.get_guest_alert_public_status(db, public_reference, x_guest_session)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.get(
    "/alerts",
    response_model=PaginatedResponse,
)
def list_guest_alerts(
    db: DbDep,
    user=Depends(get_waiter_user),
    branch_id: int = Query(...),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """التنبيهات اللي لسه محتاجة رد فعل (open أو acknowledged) — طاقم الخدمة
    بيتابعها لحظيًا عبر WebSocket، الـ endpoint ده fallback/تحميل أولي.
    Gate 1 containment (2026-07-17): branch_id كان بيتقبل من العميل بلا أي
    تحقق ملكية — services.list_guest_alerts بقى بيفرض إن الفرع ده فرع
    المستخدم نفسه (أو super_admin حصريًا)، راجع services.assert_branch_access."""
    skip = (page - 1) * size
    try:
        items, total = services.list_guest_alerts(db, branch_id, user, skip=skip, limit=size)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    return PaginatedResponse(
        total=total, page=page, size=size,
        items=[services.guest_alert_read(db, a) for a in items],
    )


@router.patch(
    "/alerts/{alert_id}/status",
    response_model=GuestAlertRead,
)
async def update_guest_alert_status(
    alert_id: int,
    data: GuestAlertStatusUpdate,
    db: DbDep,
    user=Depends(get_waiter_user),
):
    """طاقم الخدمة يأكد استلامه (acknowledged) أو يقفله بعد التنفيذ (resolved).
    Gate 1 containment (جولة تصحيح ثانية): بقى بيفرض تطابق فرع المستخدم."""
    try:
        alert = services.update_alert_status(
            db, alert_id, data.status, resolved_by=user.id, requesting_user=user,
        )
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    await alerts_manager.broadcast(str(alert.branch_id), {
        "type": "alert_status_changed",
        "alert": services.guest_alert_read(db, alert).model_dump(mode="json"),
    })
    return services.guest_alert_read(db, alert)


# ══════════════════════════════════════════════════════════════════════
# Service Location Token — Gate 8 Phase 1 Batch B (راجع
# docs/decisions/0001-qr-guest-service-mode.md بند 5/6). المنطق كامل في
# services.create_or_rotate_service_location_token/
# resolve_service_location_token — الراوتر هنا ترجمة HTTP بس.
# ══════════════════════════════════════════════════════════════════════

@router.post(
    "/service-location-tokens",
    response_model=ServiceLocationTokenRead,
    status_code=status.HTTP_201_CREATED,
)
def create_service_location_token(
    data: ServiceLocationTokenCreate,
    db: DbDep,
    user=Depends(get_manager_user),
):
    """توليد/تدوير رمز موقع خدمة (طاولة/موقع شاطئ/غرفة) — أي رمز نشط سابق
    لنفس الموقع بيتلغي فورًا. مستخدم من شاشة طباعة QR الإدارية."""
    try:
        token = services.create_or_rotate_service_location_token(
            db, data.branch_id, data.location_type, data.location_id, requesting_user=user,
        )
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return ServiceLocationTokenRead.model_validate(token)


@router.get(
    "/service-location-tokens",
    response_model=list[ServiceLocationTokenRead],
)
def list_service_location_tokens(
    db: DbDep,
    user=Depends(get_manager_user),
    branch_id: int = Query(...),
):
    """الرموز الفعّالة حاليًا لفرع معيّن — بيستخدمه admin/QRGeneratorView.vue
    عشان يعرف أي طاولة عندها QR فعّال بالفعل من غير ما يولّد رمز جديد
    (وبالتالي يلغي القديم) في كل مرة يفتح فيها الشاشة."""
    try:
        tokens = services.list_service_location_tokens(db, branch_id, user)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    return [ServiceLocationTokenRead.model_validate(t) for t in tokens]


@router.get(
    "/public/service-location",
    response_model=ServiceLocationRead,
    tags=["core-public"],
)
def resolve_service_location(db: DbDep, token: str = Query(...)):
    """Public — بدون auth. الضيف بيمسح QR فيوصله `/s/{token}`، الفرونت إند
    بينادي هنا يحلّل السياق الحقيقي (فرع/نوع موقع/موقع) قبل عرض أي حاجة —
    الرابط نفسه ميحملش أي ID خام أبدًا (Decision 0001 بند 6)."""
    try:
        return services.resolve_service_location_token(db, token)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.post(
    "/public/guest-sessions",
    response_model=GuestSessionRead,
    status_code=status.HTTP_201_CREATED,
    tags=["core-public"],
)
def create_guest_session(data: GuestSessionCreate, db: DbDep):
    """Exchange a valid QR capability for a short-lived guest session."""
    try:
        return services.create_guest_session(db, data.token)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ══════════════════════════════════════════════════════════════════════
# PIN Credentials — موافقة مدير سريعة على إجراء حسّاس (راجع
# core.services.resolve_pin_approval، PinCredential في models.py)
# ══════════════════════════════════════════════════════════════════════

def _pin_status_response(user_id: int, cred) -> PinCredentialRead:
    from datetime import datetime

    if cred is None:
        return PinCredentialRead(user_id=user_id, has_pin=False, failed_attempts=0, is_locked=False)
    is_locked = bool(cred.locked_until and cred.locked_until > datetime.utcnow())
    return PinCredentialRead(
        user_id=user_id, has_pin=True,
        failed_attempts=cred.failed_attempts, is_locked=is_locked,
    )


@router.get("/pins/me", response_model=PinCredentialRead)
def get_my_pin_status(db: DbDep, user=Depends(get_waiter_user)):
    """حالة الـ PIN بتاعي (موجود؟ مقفول مؤقتًا؟) — أبدًا مش الرقم نفسه."""
    return _pin_status_response(user.id, services.get_pin_status(db, user.id))


@router.get("/pins/approvers", response_model=list[ApproverOption])
def list_pin_approvers(db: DbDep, _user=Depends(get_cashier_user), min_level: int = Query(60, ge=0, le=100)):
    """قائمة "اختر المدير" لشاشة موافقة PIN — كاشير+ يقدر يشوفها (محتاجها
    فعليًا وقت إلغاء صنف)، بس البيانات المُرجعة دنيا (اسم/دور بس، مفيش
    email) عشان مينفعش نستخدمها كـ endpoint إدارة مستخدمين بديل."""
    return [
        ApproverOption.model_validate(u)
        for u in services.list_eligible_approvers(db, min_level)
    ]


@router.post("/pins/me", response_model=PinCredentialRead, status_code=status.HTTP_201_CREATED)
def set_my_pin(data: PinSetRequest, db: DbDep, user=Depends(get_waiter_user)):
    """أي موظف تشغيلي (نادل فأعلى) يقدر يضبط PIN بنفسه — للموافقات اللي
    هو نفسه مؤهّل ليها (مدير+) أو لاستخدام مستقبلي (تبديل مشغّل، Phase 2)."""
    cred = services.set_pin(db, user.id, data.pin, created_by=user.id)
    return _pin_status_response(user.id, cred)


@router.post("/pins/switch", response_model=PinSwitchResponse)
def pin_switch(data: PinSwitchRequest, db: DbDep, _user=Depends(get_waiter_user)):
    """تبديل هوية المشغّل على جهاز كاشير واحد — راجع
    core.services.pin_switch_login للتفاصيل الكاملة. الحد الأدنى
    ``get_waiter_user`` هنا معناه "فيه terminal session شغالة بالفعل"،
    مش صلاحية حقيقية على العملية نفسها (أي حد يعرف PIN شخص تاني بيتحول
    لهويته، زي أي POS حقيقي).

    ⚠️ لازم يتسجّل *قبل* `/pins/{user_id}` تحت — Starlette بيطابق المسارات
    بترتيب التسجيل، ومسار `{user_id}` بيقبل "switch" كـ path segment عادي
    (باج routing حقيقي اتكشف واتصلح هنا: أي طلب لـ /pins/switch كان بيوصل
    فعليًا لـ get_user_pin_status/set_user_pin بدل الـ endpoint ده، برسالة
    403 "يتطلب صلاحية مدير" مضلّلة بدل السلوك الصحيح)."""
    try:
        result = services.pin_switch_login(db, data.user_id, data.pin)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return PinSwitchResponse(
        access_token=result["access_token"], token_type=result["token_type"],
        user=UserRead.model_validate(result["user"]),
    )


@router.get("/pins/{user_id}", response_model=PinCredentialRead)
def get_user_pin_status(user_id: int, db: DbDep, _user=Depends(get_manager_user)):
    """مدير بيشوف حالة PIN موظف تاني (موجود/مقفول) — للتأكد قبل تعيين
    مهمة أو لتشخيص لو موظف بيشتكي إن الـ PIN بتاعه بيترفض دايمًا."""
    return _pin_status_response(user_id, services.get_pin_status(db, user_id))


@router.post("/pins/{user_id}", response_model=PinCredentialRead, status_code=status.HTTP_201_CREATED)
def set_user_pin(user_id: int, data: PinSetRequest, db: DbDep, user=Depends(get_manager_user)):
    """مدير يضبط/يجدّد PIN موظف تاني — أونبوردنج كاشير جديد، أو استعادة
    بعد نسيان/قفل. created_by بيسجّل مين المدير اللي عمل كده."""
    cred = services.set_pin(db, user_id, data.pin, created_by=user.id)
    return _pin_status_response(user_id, cred)
