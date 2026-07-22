"""
app/modules/core/crud.py
═══════════════════════════════════════════════════════════════════════
CRUD خالص للـ Core Module — لا HTTPException، لا business logic

القاعدة: هذا الملف يتكلم مع DB فقط.
كل الـ business decisions في services.py
كل الـ HTTP translations في router.py
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.modules.core.models import (
    AuditLog,
    Branch,
    GuestAlert,
    GuestSession,
    Notification,
    PinCredential,
    ServiceLocationToken,
    Setting,
    UserPermission,
)
from app.modules.core.schemas import (
    AuditLogCreate,
    BranchCreate,
    BranchUpdate,
    NotificationCreate,
    UserPermissionCreate,
)


# ─────────────────────── Branch ──────────────────────────────────────

def get_branch(db: Session, branch_id: int) -> Optional[Branch]:
    return db.query(Branch).filter(Branch.id == branch_id).first()


def get_branch_by_code(db: Session, code: str) -> Optional[Branch]:
    return db.query(Branch).filter(Branch.code == code).first()


def list_branches(
    db: Session,
    active_only: bool = False,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Branch], int]:
    """يُرجع (items, total)"""
    q = db.query(Branch)
    if active_only:
        q = q.filter(Branch.is_active.is_(True))
    total = q.count()
    items = q.order_by(Branch.id).offset(skip).limit(limit).all()
    return items, total


def create_branch(db: Session, data: BranchCreate) -> Branch:
    branch = Branch(**data.model_dump())
    db.add(branch)
    db.flush()  # يُعطي الـ id بدون commit — الـ service يعمل commit
    return branch


def update_branch(
    db: Session,
    branch: Branch,
    data: BranchUpdate,
) -> Branch:
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(branch, field, value)
    db.flush()
    return branch


def delete_branch(db: Session, branch: Branch) -> None:
    db.delete(branch)
    db.flush()


# ─────────────────────── Setting ─────────────────────────────────────

def get_setting_exact(
    db: Session,
    key: str,
    branch_id: Optional[int] = None,
) -> Optional[Setting]:
    """مطابقة تامة على (key, branch_id) — بدون أي fallback للعام. هي
    المصدر الوحيد المسموح له الـHTTP admin path (core/api/router.py::
    get_setting) يستخدمه: مراجعة Codex المستقلة لـGate 2B3A (2026-07-18)
    اكتشفت إن get_setting() القديمة (تحت) كانت بترجع صف الإعداد العام
    ضمنيًا لمدير فرع طلب مفتاح مش موجود لفرعه — تسريب قيمة إعداد عام
    لغير super_admin رغم فحص عزل الفرع في الراوتر، لأن الفحص كان بيتحقق
    من الفرع المطلوب (صحيح) لكن مش من مصدر الصف الراجع فعليًا (fallback
    ضمني). لا تستخدمها بدل get_setting() للاستخدام الداخلي (تسعير الشاطئ
    وغيره) — دي بتحتاج fallback القيمة العامة فعليًا."""
    return (
        db.query(Setting)
        .filter(Setting.key == key, Setting.branch_id == branch_id)
        .first()
    )


def get_setting(
    db: Session,
    key: str,
    branch_id: Optional[int] = None,
) -> Optional[Setting]:
    """
    يبحث بالـ key + branch_id.
    لو branch_id محدد ولم يجد → يبحث عن global (branch_id=None).

    ⚠️ الاستخدام الداخلي فقط (get_setting_value() وما شابه) — الـHTTP
    admin path (GET /settings/{key}) لازم يستخدم get_setting_exact()
    فوق بدل الدالة دي، عشان مايرجعش صف عام ضمنيًا لطلب فرع صريح. راجع
    docstring get_setting_exact() للسياق الكامل.
    """
    row = (
        db.query(Setting)
        .filter(Setting.key == key, Setting.branch_id == branch_id)
        .first()
    )
    if row is None and branch_id is not None:
        # fallback to global
        row = (
            db.query(Setting)
            .filter(Setting.key == key, Setting.branch_id.is_(None))
            .first()
        )
    return row


def list_settings(
    db: Session,
    branch_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
) -> list[Setting]:
    return (
        db.query(Setting)
        .filter(Setting.branch_id == branch_id)
        .order_by(Setting.key)
        .offset(skip)
        .limit(limit)
        .all()
    )


def upsert_setting(
    db: Session,
    key: str,
    value: str,
    branch_id: Optional[int] = None,
) -> Setting:
    """يُحدّث إذا موجود، يُنشئ إذا لم يكن — لا commit هنا"""
    row = (
        db.query(Setting)
        .filter(Setting.key == key, Setting.branch_id == branch_id)
        .first()
    )
    if row:
        row.value = value
    else:
        row = Setting(key=key, value=value, branch_id=branch_id)
        db.add(row)
    db.flush()
    return row


# ─────────────────────── Notification ────────────────────────────────

def get_notification(db: Session, notification_id: int) -> Optional[Notification]:
    return db.query(Notification).filter(Notification.id == notification_id).first()


def list_notifications(
    db: Session,
    user_id: int,
    branch_id: Optional[int] = None,
    unread_only: bool = False,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Notification], int]:
    q = db.query(Notification).filter(Notification.user_id == user_id)
    if branch_id is not None:
        q = q.filter(Notification.branch_id == branch_id)
    if unread_only:
        q = q.filter(Notification.is_read.is_(False))
    total = q.count()
    items = (
        q.order_by(Notification.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return items, total


def create_notification(db: Session, data: NotificationCreate) -> Notification:
    notif = Notification(**data.model_dump())
    db.add(notif)
    db.flush()
    return notif


def mark_notification_read(
    db: Session,
    notification: Notification,
) -> Notification:
    notification.is_read = True
    db.flush()
    return notification


def mark_all_notifications_read(
    db: Session,
    user_id: int,
    branch_id: Optional[int] = None,
) -> int:
    """يُرجع عدد الـ rows المُحدَّثة"""
    q = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read.is_(False),
    )
    if branch_id is not None:
        q = q.filter(Notification.branch_id == branch_id)
    count = q.count()
    q.update({"is_read": True}, synchronize_session=False)
    db.flush()
    return count


# ─────────────────────── Users ───────────────────────────────────────
# User itself lives in app.core.kernel.models.user — imported lazily to avoid a
# hard import-order dependency between core and the shared auth model.

def list_users(db: Session, skip: int = 0, limit: int = 20):
    from app.core.kernel.models.user import User  # noqa: PLC0415
    q = db.query(User).filter(User.deleted_at.is_(None))
    total = q.count()
    items = q.order_by(User.id).offset(skip).limit(limit).all()
    return items, total


def get_user(db: Session, user_id: int):
    from app.core.kernel.models.user import User  # noqa: PLC0415
    return db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()


def lock_active_super_admins(db: Session) -> list:
    """يقفل كل صفوف super_admin النشطين بترتيب ثابت (ORDER BY id) —
    SELECT ... FOR UPDATE بلوكينج، عمدًا مش NOWAIT (زي finance.
    lock_folio_for_update: طلبين متزامنين على حسابين super_admin مختلفين
    المفروض يتسلسلوا ويعاد تقييم الحالة تحت كل واحد فيهم بدل ما يترفضوا
    فورًا بتضارب قفل). الترتيب الثابت (ORDER BY id) بيمنع deadlock لو
    معاملتين مختلفتين حاولوا يقفلوا نفس المجموعة في نفس اللحظة — كل
    الاستدعاءات (services.update_user_role) بتقفل المجموعة دي أولاً قبل
    أي قفل تاني على جدول users (Gate 2A، تصحيح محمد بعد تقرير Claude
    الأول). populate_existing() إجباري (راجع CLAUDE.md §13 بند ⓫)."""
    from app.core.kernel.models.user import User  # noqa: PLC0415
    return (
        db.query(User)
        .filter(User.role == "super_admin", User.is_active.is_(True), User.deleted_at.is_(None))
        .order_by(User.id)
        .populate_existing()
        .with_for_update()
        .all()
    )


def lock_user_for_update(db: Session, user_id: int):
    """يقفل صف مستخدم هدف واحد — لازم يُنادى **بعد** lock_active_super_
    admins() في كل الاستدعاءات (ترتيب ثابت يمنع deadlock، راجع docstring
    فوق). آمن حتى لو الهدف أصلاً جزء من المجموعة المقفولة فوق — نفس الصف
    في نفس الـtransaction، Postgres مايرفضش إعادة قفل صف مقفول بالفعل من
    نفس المعاملة. populate_existing() إجباري (CLAUDE.md §13 بند ⓫)."""
    from app.core.kernel.models.user import User  # noqa: PLC0415
    return (
        db.query(User)
        .filter(User.id == user_id, User.deleted_at.is_(None))
        .populate_existing()
        .with_for_update()
        .first()
    )


def list_users_by_roles(db: Session, roles: list[str]):
    """يجيب مستخدمين نشطين من أدوار معيّنة — مُستخدم لقائمة "المعتمِدين
    المؤهّلين" (PIN approval picker)، مش endpoint إدارة مستخدمين كامل، فمفيش
    داعي لصلاحية super_admin زي list_users."""
    from app.core.kernel.models.user import User  # noqa: PLC0415
    return (
        db.query(User)
        .filter(User.role.in_(roles), User.is_active.is_(True), User.deleted_at.is_(None))
        .order_by(User.full_name)
        .all()
    )


# ─────────────────────── UserPermission ──────────────────────────────

def get_user_permission(
    db: Session,
    permission_id: int,
) -> Optional[UserPermission]:
    return db.query(UserPermission).filter(UserPermission.id == permission_id).first()


def find_explicit_permission(
    db: Session,
    user_id: int,
    resource: str,
    action: str,
    branch_id: Optional[int] = None,
) -> Optional[UserPermission]:
    """
    يبحث عن استثناء صريح (منح أو منع) لـ user+resource+action.
    الأولوية: تطابق branch محدد أولاً، ثم global (branch_id=NULL).
    ده هو الـ lookup اللي بيستخدمه has_permission() في services.py.
    """
    if branch_id is not None:
        row = (
            db.query(UserPermission)
            .filter(
                UserPermission.user_id == user_id,
                UserPermission.resource == resource,
                UserPermission.action == action,
                UserPermission.branch_id == branch_id,
            )
            .first()
        )
        if row is not None:
            return row

    return (
        db.query(UserPermission)
        .filter(
            UserPermission.user_id == user_id,
            UserPermission.resource == resource,
            UserPermission.action == action,
            UserPermission.branch_id.is_(None),
        )
        .first()
    )


def list_user_permissions(
    db: Session,
    user_id: int,
) -> list[UserPermission]:
    return (
        db.query(UserPermission)
        .filter(UserPermission.user_id == user_id)
        .order_by(UserPermission.resource, UserPermission.action)
        .all()
    )


def create_user_permission(
    db: Session,
    user_id: int,
    data: UserPermissionCreate,
    granted_by: Optional[int] = None,
) -> UserPermission:
    perm = UserPermission(
        user_id=user_id,
        granted_by=granted_by,
        **data.model_dump(),
    )
    db.add(perm)
    db.flush()
    return perm


def upsert_user_permission(
    db: Session,
    user_id: int,
    data: UserPermissionCreate,
    granted_by: Optional[int] = None,
) -> UserPermission:
    """منح/منع لنفس الـ resource+action+branch يُحدّث الصف الموجود بدل تكرار."""
    row = (
        db.query(UserPermission)
        .filter(
            UserPermission.user_id == user_id,
            UserPermission.resource == data.resource,
            UserPermission.action == data.action,
            UserPermission.branch_id == data.branch_id,
        )
        .first()
    )
    if row:
        row.allowed = data.allowed
        row.granted_by = granted_by
        db.flush()
        return row
    return create_user_permission(db, user_id, data, granted_by)


def delete_user_permission(db: Session, permission: UserPermission) -> None:
    db.delete(permission)
    db.flush()


# ─────────────────────── AuditLog ────────────────────────────────────

def create_audit_log(db: Session, data: AuditLogCreate) -> AuditLog:
    if data.user_id is not None:
        from app.core.kernel.models.user import User  # noqa: PLC0415
        if not db.query(User).filter(User.id == data.user_id).first():
            raise ValueError(f"المستخدم {data.user_id} غير موجود لتسجيل التدقيق")
    if data.approved_by is not None:
        from app.core.kernel.models.user import User as AuditUser  # noqa: PLC0415
        if not db.query(AuditUser).filter(AuditUser.id == data.approved_by).first():
            raise ValueError(f"المستخدم المعتمد {data.approved_by} غير موجود لتسجيل التدقيق")
    if data.branch_id is not None:
        if not db.query(Branch).filter(Branch.id == data.branch_id).first():
            raise ValueError(f"الفرع {data.branch_id} غير موجود لتسجيل التدقيق")
    log = AuditLog(**data.model_dump())
    db.add(log)
    db.flush()
    return log


def list_audit_logs(
    db: Session,
    branch_id: Optional[int] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[AuditLog], int]:
    q = db.query(AuditLog)
    if branch_id is not None:
        q = q.filter(AuditLog.branch_id == branch_id)
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        q = q.filter(AuditLog.entity_id == entity_id)
    if user_id is not None:
        q = q.filter(AuditLog.user_id == user_id)
    if action:
        q = q.filter(AuditLog.action == action)

    total = q.count()
    items = (
        q.order_by(AuditLog.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return items, total


# ─────────────────────── GuestAlert ──────────────────────────────────

def create_guest_alert(
    db: Session, *, branch_id: int, context_type: str, context_id: int,
    alert_type: str, message: Optional[str], public_reference: str | None = None,
    guest_session_id: int | None = None, outlet_id: int | None = None,
    order_id: int | None = None, idempotency_key: str | None = None,
) -> GuestAlert:
    """Persist only server-derived location fields from a guest session."""
    alert = GuestAlert(
        branch_id=branch_id, context_type=context_type, context_id=context_id,
        alert_type=alert_type, message=message, status="open",
        public_reference=public_reference, guest_session_id=guest_session_id,
        outlet_id=outlet_id, order_id=order_id, idempotency_key=idempotency_key,
    )
    db.add(alert)
    db.flush()
    return alert


def get_guest_alert(db: Session, alert_id: int) -> Optional[GuestAlert]:
    return db.query(GuestAlert).filter(GuestAlert.id == alert_id).first()


def get_guest_alert_for_update(db: Session, alert_id: int) -> Optional[GuestAlert]:
    return (
        db.query(GuestAlert)
        .filter(GuestAlert.id == alert_id)
        .with_for_update()
        .populate_existing()
        .first()
    )


def get_active_guest_alert(
    db: Session, *, branch_id: int, context_type: str, context_id: int,
    alert_type: str,
) -> Optional[GuestAlert]:
    return (
        db.query(GuestAlert)
        .filter(
            GuestAlert.branch_id == branch_id,
            GuestAlert.context_type == context_type,
            GuestAlert.context_id == context_id,
            GuestAlert.alert_type == alert_type,
            GuestAlert.status.in_(("open", "acknowledged", "arrived")),
        )
        .order_by(GuestAlert.created_at.desc())
        .first()
    )


def expire_stale_guest_alerts(
    db: Session, cutoff: datetime, branch_id: int | None = None,
) -> int:
    query = db.query(GuestAlert).filter(
        GuestAlert.status.in_(("open", "acknowledged", "arrived")),
        GuestAlert.created_at < cutoff,
    )
    if branch_id is not None:
        query = query.filter(GuestAlert.branch_id == branch_id)
    count = query.update({"status": "expired"}, synchronize_session=False)
    db.flush()
    return count


def get_guest_alert_by_public_reference(
    db: Session, public_reference: str,
) -> Optional[GuestAlert]:
    return db.query(GuestAlert).filter(GuestAlert.public_reference == public_reference).first()


def get_guest_alert_by_idempotency_key(
    db: Session, guest_session_id: int, idempotency_key: str,
) -> Optional[GuestAlert]:
    return (
        db.query(GuestAlert)
        .filter(
            GuestAlert.guest_session_id == guest_session_id,
            GuestAlert.idempotency_key == idempotency_key,
        )
        .first()
    )


def list_active_bill_alerts_for_order(
    db: Session, *, order_id: int, branch_id: int, context_id: int | None,
    guest_session_id: int | None, outlet_id: int,
) -> list[GuestAlert]:
    link_filter = GuestAlert.order_id == order_id
    if guest_session_id is not None:
        link_filter = link_filter | (
            (GuestAlert.guest_session_id == guest_session_id)
            & (GuestAlert.outlet_id == outlet_id)
        )
    query = db.query(GuestAlert).filter(
        GuestAlert.branch_id == branch_id,
        GuestAlert.alert_type == "request_bill",
        GuestAlert.status.in_(("open", "acknowledged", "arrived")),
        link_filter,
    )
    if context_id is not None:
        query = query.filter(
            GuestAlert.context_type == "dining_table",
            GuestAlert.context_id == context_id,
        )
    return query.with_for_update().all()


def list_active_alerts(
    db: Session,
    branch_id: int,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[GuestAlert], int]:
    """التنبيهات اللي لسه محتاجة رد فعل (مش resolved) — أقدم واحد الأول
    (FIFO) عشان طاقم الخدمة يرد على الأقدم أولاً، مش يغرق في أحدث تنبيه."""
    q = db.query(GuestAlert).filter(
        GuestAlert.branch_id == branch_id,
        GuestAlert.status.in_(("open", "acknowledged", "arrived")),
    )
    total = q.count()
    items = q.order_by(GuestAlert.created_at.asc()).offset(skip).limit(limit).all()
    return items, total


def update_alert_status(
    db: Session,
    alert: GuestAlert,
    new_status: str,
    resolved_by: Optional[int] = None,
) -> GuestAlert:
    alert.status = new_status
    if new_status == "acknowledged":
        alert.assigned_to = resolved_by
        alert.acknowledged_at = datetime.utcnow()
    elif new_status == "arrived":
        alert.assigned_to = resolved_by
        alert.acknowledged_at = alert.acknowledged_at or datetime.utcnow()
        alert.arrived_at = datetime.utcnow()
    if new_status == "resolved":
        alert.assigned_to = alert.assigned_to or resolved_by
        alert.resolved_by = resolved_by
        alert.resolved_at = datetime.utcnow()
    db.flush()
    return alert


# ─────────────────────── PinCredential ────────────────────────────────

def get_pin_credential(db: Session, user_id: int) -> Optional[PinCredential]:
    return db.query(PinCredential).filter(PinCredential.user_id == user_id).first()


def upsert_pin_credential(
    db: Session, user_id: int, pin_hash: str, created_by: int,
) -> PinCredential:
    """ضبط PIN جديد أو استبدال القديم بالكامل — بيصفّر أي قفل/محاولات فاشلة
    سابقة (PIN جديد يستاهل بداية نظيفة)."""
    cred = get_pin_credential(db, user_id)
    if cred:
        cred.pin_hash = pin_hash
        cred.created_by = created_by
        cred.failed_attempts = 0
        cred.locked_until = None
    else:
        cred = PinCredential(
            user_id=user_id, pin_hash=pin_hash, created_by=created_by,
        )
        db.add(cred)
    db.flush()
    return cred


def record_pin_failure(db: Session, cred: PinCredential, locked_until: Optional[datetime]) -> PinCredential:
    cred.failed_attempts += 1
    if locked_until is not None:
        cred.locked_until = locked_until
    db.flush()
    return cred


def reset_pin_failures(db: Session, cred: PinCredential) -> PinCredential:
    cred.failed_attempts = 0
    cred.locked_until = None
    db.flush()
    return cred


# ─────────────────────── ServiceLocationToken ─────────────────────────

def create_guest_session(
    db: Session, *, public_reference: str, token_hash: str,
    service_location_token_id: int, expires_at: datetime,
) -> GuestSession:
    now = datetime.utcnow()
    row = GuestSession(
        public_reference=public_reference,
        token_hash=token_hash,
        service_location_token_id=service_location_token_id,
        expires_at=expires_at,
        last_seen_at=now,
    )
    db.add(row)
    db.flush()
    return row


def get_guest_session_by_hash(db: Session, token_hash: str) -> Optional[GuestSession]:
    return db.query(GuestSession).filter(GuestSession.token_hash == token_hash).first()


def get_service_location_token_by_id(
    db: Session, token_id: int,
) -> Optional[ServiceLocationToken]:
    return db.query(ServiceLocationToken).filter(ServiceLocationToken.id == token_id).first()

def create_service_location_token(
    db: Session, *, token: str, branch_id: int, location_type: str,
    location_id: int, created_by: int | None,
) -> ServiceLocationToken:
    row = ServiceLocationToken(
        token=token, branch_id=branch_id, location_type=location_type,
        location_id=location_id, created_by=created_by,
    )
    db.add(row)
    db.flush()
    return row


def deactivate_service_location_tokens(
    db: Session, branch_id: int, location_type: str, location_id: int,
) -> None:
    (
        db.query(ServiceLocationToken)
        .filter(
            ServiceLocationToken.branch_id == branch_id,
            ServiceLocationToken.location_type == location_type,
            ServiceLocationToken.location_id == location_id,
            ServiceLocationToken.is_active.is_(True),
        )
        .update({"is_active": False}, synchronize_session=False)
    )
    db.flush()


def get_active_service_location_token(db: Session, token: str) -> Optional[ServiceLocationToken]:
    return (
        db.query(ServiceLocationToken)
        .filter(
            ServiceLocationToken.token == token,
            ServiceLocationToken.is_active.is_(True),
        )
        .first()
    )


def list_active_service_location_tokens(db: Session, branch_id: int) -> list[ServiceLocationToken]:
    """يُستخدم من admin/QRGeneratorView.vue عشان يعرف أي طاولة عندها رمز
    فعّال بالفعل (يعرض QR-ها مباشرة) وأي طاولة محتاجة توليد لأول مرة —
    بدون round-trip منفصل لكل طاولة."""
    return (
        db.query(ServiceLocationToken)
        .filter(
            ServiceLocationToken.branch_id == branch_id,
            ServiceLocationToken.is_active.is_(True),
        )
        .all()
    )
