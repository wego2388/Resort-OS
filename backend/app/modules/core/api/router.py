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
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from typing import Optional

from fastapi import (
    APIRouter, Depends, HTTPException, Query, Request, WebSocket,
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
    GuestAlertRead,
    GuestAlertStatusUpdate,
    NotificationRead,
    PaginatedResponse,
    PermissionCatalogEntryRead,
    PinCredentialRead,
    PinSetRequest,
    PinSwitchRequest,
    PinSwitchResponse,
    SettingRead,
    SettingUpdate,
    UserPermissionGrantRequest,
    UserPermissionRead,
    UserRead,
    UserRoleUpdate,
)

router = APIRouter(tags=["core"])


# ── WebSocket Guest-Alerts Manager ─────────────────────────────────────
# نفس نمط restaurant_manager (app/modules/restaurant/api/router.py) —
# بث بسيط بالفرع، من غير أي بروتوكول ثنائي الاتجاه حقيقي.

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
async def guest_alerts_websocket(ws: WebSocket, branch_id: int):
    """اتصال WebSocket لطاقم الخدمة (نادل/كاشير) — بث تنبيهات الضيوف الجديدة
    وتحديثات حالتها لحظيًا. بيرد بـ pong كـ heartbeat فقط، زي restaurant KDS."""
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
    _user=Depends(get_admin_user),
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
    db: DbDep,
    user=Depends(get_super_admin_user),
):
    try:
        services.revoke_permission(db, permission_id, revoked_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ══════════════════════════════════════════════════════════════════════
# Guest Alerts — قناة تنبيه يبدأها الضيف بدون تسجيل دخول
# ══════════════════════════════════════════════════════════════════════
# ⚠️ POST /public/alerts بدون authentication عمداً — نفس نمط
#    /restaurant/public/orders بالظبط:
#      - rate limited بالـ middleware (app.core.rate_limit، "public" bucket)
#      - لا يوجد تعديل أو حذف من الـ public endpoint — إنشاء فقط
#      - status دايمًا "open" عند الإنشاء (الضيف مش بيحدده)
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
async def create_guest_alert(data: GuestAlertCreate, db: DbDep):
    """
    Public endpoint — لا يحتاج login.
    الضيف بيبعت تنبيه من شاشة الطلب (طاولة مطعم/كافيه، أو أي سياق تاني
    مستقبلاً) — بيتبث فورًا لأي شاشة طاقم خدمة متصلة على نفس الفرع.
    """
    try:
        alert = services.create_guest_alert(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    await alerts_manager.broadcast(str(alert.branch_id), {
        "type": "new_alert",
        "alert": GuestAlertRead.model_validate(alert).model_dump(mode="json"),
    })

    return GuestAlertAck(
        alert_id=alert.id,
        status=alert.status,
        message="تم إرسال طلبك — سيصل إليك أحد أفراد الطاقم فورًا 🙌"
        if alert.alert_type != "request_bill"
        else "تم طلب الفاتورة — سيتم إحضارها فورًا 🧾",
    )


@router.get(
    "/alerts",
    response_model=PaginatedResponse,
)
def list_guest_alerts(
    db: DbDep,
    _user=Depends(get_waiter_user),
    branch_id: int = Query(...),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """التنبيهات اللي لسه محتاجة رد فعل (open أو acknowledged) — طاقم الخدمة
    بيتابعها لحظيًا عبر WebSocket، الـ endpoint ده fallback/تحميل أولي."""
    skip = (page - 1) * size
    items, total = crud.list_active_alerts(db, branch_id, skip=skip, limit=size)
    return PaginatedResponse(
        total=total, page=page, size=size,
        items=[GuestAlertRead.model_validate(a) for a in items],
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
    """طاقم الخدمة يأكد استلامه (acknowledged) أو يقفله بعد التنفيذ (resolved)."""
    try:
        alert = services.update_alert_status(db, alert_id, data.status, resolved_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    await alerts_manager.broadcast(str(alert.branch_id), {
        "type": "alert_status_changed",
        "alert": GuestAlertRead.model_validate(alert).model_dump(mode="json"),
    })
    return GuestAlertRead.model_validate(alert)


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
