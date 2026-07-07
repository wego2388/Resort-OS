"""
app/modules/core/services.py
═══════════════════════════════════════════════════════════════════════
Business Logic للـ Core Module

القاعدة:
  - يستدعي crud.py للـ DB operations
  - يرمي ValueError/PermissionError فقط (لا HTTPException)
  - الـ router يترجم الأخطاء
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.modules.core import crud
from app.modules.core.models import Branch, GuestAlert, Notification, PinCredential, UserPermission
from app.modules.core.permission_catalog import PERMISSION_CATALOG
from app.modules.core.schemas import (
    AuditLogCreate,
    BranchCreate,
    BranchUpdate,
    EffectivePermission,
    GuestAlertCreate,
    NotificationCreate,
    SettingRead,
    UserPermissionCreate,
)

# ─────────────────────── PIN Credentials ──────────────────────────────
# راجع PinCredential (models.py) للسياق الكامل — PIN تشغيلي منفصل عن
# JWT، مُستخدم لموافقة مدير سريعة على إجراء حسّاس (إلغاء/مرتجع) لما
# المنفّذ الفعلي أقل من المستوى المطلوب.

PIN_MAX_ATTEMPTS = 3       # 3 محاولات غلط = قفل
PIN_LOCKOUT_SECONDS = 60   # دقيقة واحدة


def set_pin(db: Session, user_id: int, pin: str, created_by: int) -> PinCredential:
    """ضبط/تجديد PIN — الـ Field(pattern=r"^\\d{4,6}$") في PinSetRequest هو
    الحارس الوحيد على الشكل؛ هنا بس hashing + تخزين. commit صريح — دي
    نقطة نهاية العملية (مش جزء من transaction أكبر زي resolve_pin_approval
    وقت استخدامها جوه void/refund)."""
    from app.core.kernel.security import get_password_hash  # noqa: PLC0415

    pin_hash = get_password_hash(pin)
    cred = crud.upsert_pin_credential(db, user_id, pin_hash, created_by)
    db.commit()
    db.refresh(cred)
    return cred


def get_pin_status(db: Session, user_id: int) -> Optional[PinCredential]:
    return crud.get_pin_credential(db, user_id)


def list_eligible_approvers(db: Session, min_level: int = 60) -> list:
    """المستخدمين النشطين اللي مستواهم >= min_level — لقائمة "اختر المدير"
    في شاشة موافقة PIN بالفرونت إند. مش endpoint إدارة مستخدمين (مفيش
    email/بيانات حساسة في الرد — راجع core.schemas.ApproverOption)."""
    from app.core.deps import ROLE_LEVELS  # noqa: PLC0415

    roles = [role for role, level in ROLE_LEVELS.items() if level >= min_level]
    return crud.list_users_by_roles(db, roles)


def verify_pin(db: Session, user_id: int, pin: str) -> bool:
    """True لو الـ PIN صح ومفيش قفل نشط — بيسجّل محاولة فاشلة ويقفل بعد
    PIN_MAX_ATTEMPTS (زي lockout الحساب العادي في kernel.auth.service، بس
    بمدة أقصر لأنها إجراء نقطة بيع لحظي مش تسجيل دخول)."""
    from datetime import datetime, timedelta  # noqa: PLC0415

    from app.core.kernel.security import verify_password  # noqa: PLC0415

    cred = crud.get_pin_credential(db, user_id)
    if not cred:
        return False

    now = datetime.utcnow()
    if cred.locked_until and cred.locked_until > now:
        return False

    if verify_password(pin, cred.pin_hash):
        crud.reset_pin_failures(db, cred)
        return True

    next_attempts = cred.failed_attempts + 1
    locked_until = now + timedelta(seconds=PIN_LOCKOUT_SECONDS) if next_attempts >= PIN_MAX_ATTEMPTS else None
    crud.record_pin_failure(db, cred, locked_until)
    return False


def resolve_pin_approval(
    db: Session,
    acting_user_level: int,
    approver_user_id: Optional[int],
    approver_pin: Optional[str],
    *,
    min_approver_level: int = 60,
) -> Optional[int]:
    """البوابة المركزية اللي كل إجراء حسّاس (إلغاء صنف، مرتجع...) بينادي
    عليها بدل ما يعيد نفس المنطق. بترجع ``approved_by`` (user.id بتاع
    المعتمِد) لو الموافقة حصلت فعلاً، أو ``None`` لو المنفّذ نفسه كان
    مؤهّل أصلاً (مفيش "معتمِد" منفصل يستاهل يتسجل).

    ``acting_user_level`` رقم مباشر (مش user object) عمدًا — الـ caller
    (عادة restaurant/cafe.services) بيحسبه مرة واحدة من ``user_level(user)``
    قبل ما ينادي هنا، فمفيش تبعية بين core.services وأي user object محدد.

    قرار معماري متعمد: لو مستوى المنفّذ نفسه >= min_approver_level (هو
    أصلاً مدير أو فوق)، **مفيش موافقة PIN مطلوبة خالص** — طلب موافقة مدير
    من نفسه مسرحية أمان بدون قيمة حقيقية، وبتبطّئ شغله من غير داعي.
    """
    if acting_user_level >= min_approver_level:
        return None

    if not approver_user_id or not approver_pin:
        raise ValueError("الإجراء ده محتاج موافقة مدير بالـ PIN — اختر المدير وأدخل رقمه")

    from app.core.deps import user_level  # noqa: PLC0415 — تجنّب circular import مع core.services
    from app.core.kernel.models.user import User  # noqa: PLC0415

    approver = db.query(User).filter(User.id == approver_user_id).first()
    if not approver:
        raise ValueError("المستخدم المعتمِد غير موجود")
    if not approver.is_active:
        raise ValueError("حساب المعتمِد غير نشط")
    if user_level(approver) < min_approver_level:
        raise ValueError("المستخدم ده مش عنده صلاحية كافية للموافقة على هذا الإجراء")

    if not verify_pin(db, approver_user_id, approver_pin):
        raise ValueError("رقم PIN غلط أو الحساب مقفول مؤقتًا بعد محاولات فاشلة")

    return approver_user_id


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


# ─────────────────────── Permission Matrix ───────────────────────────
# طبقة إضافية فوق ROLE_LEVELS (app/core/deps.py) — لا تكسرها.
#
# القاعدة:
#   1. لو فيه صف UserPermission صريح لـ user+resource+action (branch-scoped
#      أو global) → هو الحاكم. سواء منح (allowed=True) أو منع (allowed=False)
#      — بيكسب الـ role level تماماً.
#   2. لو مفيش صف صريح → يرجع لسلوك الـ role القديم (fallback) بدون تغيير.
#      الـ caller هو المسؤول عن تمرير الـ role fallback (عادة "المستخدم
#      يحقق الحد الأدنى من role level للـ endpoint ده أصلاً").

def has_permission(
    db: Session,
    user,
    resource: str,
    action: str,
    branch_id: Optional[int] = None,
    *,
    role_fallback: bool = True,
) -> bool:
    """
    القرار:
      1. استثناء صريح موجود (منح أو منع) → هو الحاكم، يكسب أي حاجة تانية.
      2. مفيش استثناء → يرجع role_fallback كما هو.

    role_fallback هي نتيجة تقييم الـ role القديم (مرّرها الـ caller —
    عادة app.core.deps.require_permission بيحسبها من user_level(user) مقابل
    حد أدنى معيّن لل resource/action ده). القيمة الافتراضية True فقط
    للاستخدام المباشر بدون role context (مثلاً من داخل service tests).
    """
    effective_branch_id = branch_id if branch_id is not None else getattr(user, "branch_id", None)

    explicit = crud.find_explicit_permission(
        db, user.id, resource, action, effective_branch_id,
    )
    if explicit is not None:
        return explicit.allowed

    return role_fallback


def list_user_permissions(db: Session, user_id: int) -> list[UserPermission]:
    return crud.list_user_permissions(db, user_id)


def get_effective_permissions(db: Session, user) -> list[EffectivePermission]:
    """
    يحسب كل صف من كتالوج الصلاحيات (PERMISSION_CATALOG) للمستخدم الحالي —
    دمج role fallback (user_level >= min_role_level) مع أي استثناء صريح.
    الفرونت إند بيستخدمها لإخفاء/إظهار أزرار من غير ما يكرر منطق role level.
    """
    from app.core.deps import user_level  # noqa: PLC0415

    result: list[EffectivePermission] = []
    for entry in PERMISSION_CATALOG:
        role_fallback = user_level(user) >= entry["min_role_level"]
        explicit = crud.find_explicit_permission(
            db, user.id, entry["resource"], entry["action"],
            getattr(user, "branch_id", None),
        )
        if explicit is not None:
            allowed, source = explicit.allowed, "explicit"
        else:
            allowed, source = role_fallback, "role"
        result.append(EffectivePermission(
            resource=entry["resource"], action=entry["action"],
            label_ar=entry["label_ar"], module=entry["module"],
            allowed=allowed, source=source,
        ))
    return result


def grant_permission(
    db: Session,
    user_id: int,
    data: UserPermissionCreate,
    granted_by: int,
) -> UserPermission:
    """منح أو منع صريح — upsert على نفس resource+action+branch."""
    perm = crud.upsert_user_permission(db, user_id, data, granted_by=granted_by)

    crud.create_audit_log(db, AuditLogCreate(
        user_id=granted_by,
        branch_id=data.branch_id,
        action="grant_permission" if data.allowed else "deny_permission",
        entity_type="user_permission",
        entity_id=perm.id,
        new_data=json.dumps({
            "target_user_id": user_id,
            "resource": data.resource,
            "action": data.action,
            "allowed": data.allowed,
        }),
    ))

    db.commit()
    db.refresh(perm)
    return perm


def revoke_permission(
    db: Session,
    permission_id: int,
    revoked_by: int,
) -> None:
    """يحذف الاستثناء الصريح تماماً — المستخدم يرجع لسلوك role fallback."""
    perm = crud.get_user_permission(db, permission_id)
    if not perm:
        raise ValueError(f"الصلاحية {permission_id} غير موجودة")

    crud.create_audit_log(db, AuditLogCreate(
        user_id=revoked_by,
        branch_id=perm.branch_id,
        action="revoke_permission",
        entity_type="user_permission",
        entity_id=perm.id,
        old_data=json.dumps({
            "target_user_id": perm.user_id,
            "resource": perm.resource,
            "action": perm.action,
            "allowed": perm.allowed,
        }),
    ))

    crud.delete_user_permission(db, perm)
    db.commit()


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


# ─────────────────────── GuestAlert ──────────────────────────────────
# راجع app/modules/core/models.py::GuestAlert — قناة تنبيه يبدأها الضيف
# بدون auth (نادِ الجرسون/هات الفاتورة)، وطاقم الخدمة بيتابعها لحظيًا عبر
# WebSocket (app/modules/core/api/router.py::alerts_manager).

def create_guest_alert(db: Session, data: GuestAlertCreate) -> GuestAlert:
    if not crud.get_branch(db, data.branch_id):
        raise ValueError(f"الفرع {data.branch_id} غير موجود")

    alert = crud.create_guest_alert(db, data)
    db.commit()
    db.refresh(alert)
    return alert


def update_alert_status(
    db: Session,
    alert_id: int,
    new_status: str,
    resolved_by: int,
) -> GuestAlert:
    alert = crud.get_guest_alert(db, alert_id)
    if not alert:
        raise ValueError(f"التنبيه {alert_id} غير موجود")
    if alert.status == "resolved":
        raise ValueError("التنبيه مُتعامَل معه بالفعل")

    alert = crud.update_alert_status(db, alert, new_status, resolved_by=resolved_by)
    db.commit()
    db.refresh(alert)
    return alert
