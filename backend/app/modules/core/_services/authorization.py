"""
app/modules/core/_services/authorization.py
Extracted from app/modules/core/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.modules.core import crud
from app.modules.core.permission_catalog import PERMISSION_CATALOG
from app.modules.core.models import Branch, UserBranchMembership, UserPermission
from app.modules.core.schemas import (
    AuditLogCreate,
    AllowedBranchRead,
    AuthBootstrapRead,
    EffectivePermission,
    UserPermissionCreate,
)
from app.modules.core._services._exceptions import (
    UserNotFoundError,
    SuperAdminPermissionOverrideForbiddenError,
    ActorAuthorizationChangedError,
)
from app.modules.core._services._audit_helpers import (
    _step_up_audit_context,
    _commit_rejected_control_plane_audit,
)
import logging
logger = logging.getLogger(__name__)


# ─────────────────────── Permission Matrix ───────────────────────────
# طبقة إضافية فوق ROLE_LEVELS (app/core/deps.py) — لا تكسرها.
#
# القاعدة (بعد Gate 2A — راجع _resolve_permission تحت للتفصيل الكامل):
#   0. super_admin نشط ينجح دايمًا، بصرف النظر عن أي صف UserPermission —
#      باقي كل المستخدمين التانيين (بما فيهم super_admin غير نشط) بيحكمهم
#      الاستثناء الصريح لو موجود.
#   1. لو فيه صف UserPermission صريح لـ user+resource+action (branch-scoped
#      أو global) → هو الحاكم. سواء منح (allowed=True) أو منع (allowed=False)
#      — بيكسب الـ role level تماماً.
#   2. لو مفيش صف صريح → يرجع لسلوك الـ role القديم (fallback) بدون تغيير.
#      الـ caller هو المسؤول عن تمرير الـ role fallback (عادة "المستخدم
#      يحقق الحد الأدنى من role level للـ endpoint ده أصلاً").

def _resolve_permission(
    db: Session,
    user,
    resource: str,
    action: str,
    branch_id: Optional[int] = None,
    *,
    role_fallback: bool = True,
) -> tuple[bool, str]:
    """
    القرار المركزي الوحيد لصلاحية resource+action لمستخدم معيّن — has_
    permission() وget_effective_permissions() بينادوا عليه بدل ما كل واحد
    يعيد بناء نفس شجرة القرار (كان ده الوضع قبل Gate 2A: get_effective_
    permissions كانت بتكرر منطق explicit override بنفسها من غير المرور
    على has_permission، فأي إصلاح كان لازم يتكرر مرتين ويقدر يتفوت في
    واحدة منهم — بالظبط زي ما حصل مع استثناء super_admin أول مرة).

    الترتيب:
      1. super_admin **نشط** (is_active=True) ينجح دايمًا، بصرف النظر عن
         أي UserPermission صريح — أي منع مسجّل يفضل موجود في الداتابيز
         (مش بيتحذف تلقائيًا) لكنه "inert" (بلا أثر) طول ما الحساب
         super_admin ونشط. Decision 0003 invariant #1. super_admin غير
         نشط **ما بياخدش** الاستثناء ده — المفروض أصلاً يترفض قبل كده من
         get_current_active_user's is_active check، لكن الفحص هنا صريح
         دفاعًا في العمق (defense in depth) مش اعتمادًا على طبقة واحدة.
      2. استثناء صريح موجود (منح أو منع) → هو الحاكم.
      3. مفيش استثناء → role_fallback.

    بيرجع (allowed, source) — source بتاخد "super_admin"/"explicit"/"role"
    لعرضها في /permissions/me.
    """
    if user.role == "super_admin" and user.is_active:
        return True, "super_admin"

    # User نفسه لا يملك branch_id؛ فرع الموظف الحالي موجود في
    # HR.Employee.user_id. الاعتماد القديم على getattr كان يرجّع None دائمًا،
    # وبالتالي أي UserPermission مقيّد بفرع لم يكن يُطبّق فعليًا عبر
    # require_permission — الـglobal override فقط هو الذي يعمل. نستخدم مصدر
    # العضوية الحقيقي الحالي إلى أن يكتمل جدول user_branch_memberships
    # الإضافي في الحزمة التالية.
    effective_branch_id = (
        branch_id if branch_id is not None else get_user_branch_id(db, user)
    )
    explicit = crud.find_explicit_permission(
        db, user.id, resource, action, effective_branch_id,
    )
    if explicit is not None:
        return explicit.allowed, "explicit"

    return role_fallback, "role"


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
    role_fallback هي نتيجة تقييم الـ role القديم (مرّرها الـ caller —
    عادة app.core.deps.require_permission بيحسبها من user_level(user) مقابل
    حد أدنى معيّن لل resource/action ده). القيمة الافتراضية True فقط
    للاستخدام المباشر بدون role context (مثلاً من داخل service tests).
    راجع _resolve_permission() فوق لشجرة القرار الكاملة.
    """
    allowed, _source = _resolve_permission(
        db, user, resource, action, branch_id, role_fallback=role_fallback,
    )
    return allowed


def list_user_permissions(db: Session, user_id: int) -> list[UserPermission]:
    return crud.list_user_permissions(db, user_id)


def get_effective_permissions(
    db: Session,
    user,
    branch_id: Optional[int] = None,
) -> list[EffectivePermission]:
    """
    يحسب كل صف من كتالوج الصلاحيات (PERMISSION_CATALOG) للمستخدم الحالي —
    عبر _resolve_permission() المركزية (نفس القرار اللي has_permission()
    بيستخدمه بالظبط، بدل ما تعيد بناء شجرة القرار بنفسها زي قبل Gate 2A).
    الفرونت إند بيستخدمها لإخفاء/إظهار أزرار من غير ما يكرر منطق role level.
    super_admin نشط بيظهر هنا كـallowed=True/source="super_admin" على كل
    صف في الكتالوج، حتى لو فيه UserPermission صريح بمنع مسجّل له.
    """
    from app.core.deps import user_level  # noqa: PLC0415

    result: list[EffectivePermission] = []
    for entry in PERMISSION_CATALOG:
        role_fallback = user_level(user) >= entry["min_role_level"]
        allowed, source = _resolve_permission(
            db, user, entry["resource"], entry["action"],
            branch_id=branch_id,
            role_fallback=role_fallback,
        )
        result.append(EffectivePermission(
            resource=entry["resource"], action=entry["action"],
            label_ar=entry["label_ar"], module=entry["module"],
            allowed=allowed, source=source,
        ))
    return result


# ─────────────────────── Branch authorization (CX-02C) ───────────────

class BranchAccessDeniedError(PermissionError):
    """The requested branch is not inside the caller's live authorization."""


class BranchContextRequiredError(PermissionError):
    """A branch choice is ambiguous or no live branch context exists."""


class SessionChangedError(PermissionError):
    """The access token's refresh family is no longer live."""


def _active_memberships(db: Session, user_id: int) -> list[UserBranchMembership]:
    """Return memberships that are live *and* point at a live branch."""
    return (
        db.query(UserBranchMembership)
        .join(Branch, Branch.id == UserBranchMembership.branch_id)
        .filter(
            UserBranchMembership.user_id == user_id,
            UserBranchMembership.is_active.is_(True),
            Branch.is_active.is_(True),
        )
        .order_by(UserBranchMembership.branch_id)
        .all()
    )


def get_allowed_branches(db: Session, user) -> list[AllowedBranchRead]:
    """Return the non-enumerating branch directory visible to this user."""
    from app.core.deps import user_level  # noqa: PLC0415

    if user_level(user) >= 100:
        rows = (
            db.query(Branch)
            .filter(Branch.is_active.is_(True))
            .order_by(Branch.id)
            .all()
        )
        return [
            AllowedBranchRead(
                id=row.id,
                code=row.code,
                name=row.name,
                name_ar=row.name_ar,
                timezone=row.timezone,
                is_default=False,
            )
            for row in rows
        ]

    memberships = _active_memberships(db, user.id)
    branches = {
        row.id: row
        for row in db.query(Branch)
        .filter(Branch.id.in_([m.branch_id for m in memberships]))
        .all()
    } if memberships else {}
    return [
        AllowedBranchRead(
            id=branch.id,
            code=branch.code,
            name=branch.name,
            name_ar=branch.name_ar,
            timezone=branch.timezone,
            is_default=membership.is_default,
        )
        for membership in memberships
        if (branch := branches.get(membership.branch_id)) is not None
    ]


def get_default_branch_id(db: Session, user) -> Optional[int]:
    """Resolve an unambiguous account preference; never pick the first id."""
    allowed = get_allowed_branches(db, user)
    defaults = [branch.id for branch in allowed if branch.is_default]
    if len(defaults) == 1:
        return defaults[0]
    if len(allowed) == 1:
        return allowed[0].id
    return None


def get_user_branch_id(db: Session, user) -> Optional[int]:
    """Return the server-resolved active branch.

    Auth dependencies attach ``_active_branch_id`` from a live refresh family
    (or a validated PIN ``bid``).  A direct service invocation can only derive
    a branch when the membership/default choice is unambiguous.  HR Employee
    is deliberately never consulted.
    """
    if hasattr(user, "_active_branch_id"):
        return user._active_branch_id
    return get_default_branch_id(db, user)


def _can_enter_branch(db: Session, user, branch_id: int) -> bool:
    from app.core.deps import user_level  # noqa: PLC0415

    branch = db.query(Branch).filter(
        Branch.id == branch_id,
        Branch.is_active.is_(True),
    ).first()
    if branch is None:
        return False
    if user_level(user) >= 100:
        return True
    return (
        db.query(UserBranchMembership.id)
        .filter(
            UserBranchMembership.user_id == user.id,
            UserBranchMembership.branch_id == branch_id,
            UserBranchMembership.is_active.is_(True),
        )
        .first()
        is not None
    )


def assert_branch_access(db: Session, user, target_branch_id: int, action_desc: str) -> None:
    """Require the target to equal the live session/PIN branch.

    Even super-admin must select a live active context first; its bypass is
    membership-only, not context-free access.  This prevents a client-supplied
    branch id from silently becoming the active authorization scope.
    """
    acting_branch_id = get_user_branch_id(db, user)
    if acting_branch_id is None:
        raise BranchContextRequiredError(
            f"اختر فرعًا نشطًا قبل {action_desc}"
        )
    if acting_branch_id != target_branch_id:
        raise BranchAccessDeniedError(f"لا يمكنك {action_desc} في فرع غير الجلسة الحالية")
    if not _can_enter_branch(db, user, target_branch_id):
        raise BranchAccessDeniedError(f"لا يمكنك {action_desc} في هذا الفرع")


def build_auth_bootstrap(db: Session, user) -> AuthBootstrapRead:
    """Build the complete staff auth contract from live database state."""
    from app.modules.hr.crud import get_employee_by_user_id  # noqa: PLC0415

    allowed = get_allowed_branches(db, user)
    allowed_ids = [branch.id for branch in allowed]
    default_branch_id = get_default_branch_id(db, user)
    active_branch_id = get_user_branch_id(db, user)
    if active_branch_id not in allowed_ids:
        active_branch_id = None
    employee = get_employee_by_user_id(db, user.id)
    return AuthBootstrapRead(
        user=user,
        branches=allowed,
        allowed_branch_ids=allowed_ids,
        default_branch_id=default_branch_id,
        active_branch_id=active_branch_id,
        requires_branch_selection=active_branch_id is None and bool(allowed_ids),
        effective_permissions=(
            get_effective_permissions(db, user, branch_id=active_branch_id)
            if active_branch_id is not None
            else []
        ),
        employee_id=employee.id if employee else None,
    )


def switch_active_branch(
    db: Session,
    user,
    branch_id: int,
    *,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuthBootstrapRead:
    """Atomically update only the caller's live refresh family context."""
    from datetime import timezone  # noqa: PLC0415
    from app.core.kernel.models.user import RefreshToken, User  # noqa: PLC0415

    session_ref = getattr(user, "_auth_session_ref", None)
    if not session_ref:
        raise BranchContextRequiredError(
            "تبديل الفرع متاح فقط من جلسة تسجيل دخول قابلة للتحديث"
        )
    if not _can_enter_branch(db, user, branch_id):
        raise BranchAccessDeniedError("الفرع غير متاح لهذا الحساب")

    # Same lock order as refresh rotation: User first, then the live family.
    db.query(User.id).filter(User.id == user.id).with_for_update().first()
    session = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.user_id == user.id,
            RefreshToken.family_public_id == session_ref,
            RefreshToken.consumed_at.is_(None),
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
        .with_for_update()
        .first()
    )
    if session is None:
        db.rollback()
        raise SessionChangedError("الجلسة تغيّرت أو انتهت؛ سجّل الدخول مجددًا")

    old_branch_id = session.active_branch_id
    if old_branch_id != branch_id:
        session.active_branch_id = branch_id
        crud.create_audit_log(db, AuditLogCreate(
            user_id=user.id,
            branch_id=branch_id,
            action="active_branch_switched",
            entity_type="refresh_session",
            entity_id=session.id,
            old_data=json.dumps({
                "active_branch_id": old_branch_id,
                "session_ref": session_ref,
            }),
            new_data=json.dumps({
                "active_branch_id": branch_id,
                "session_ref": session_ref,
            }),
            ip_address=ip_address,
            user_agent=(user_agent or "")[:500] or None,
        ))
        db.commit()
    user._active_branch_id = branch_id
    return build_auth_bootstrap(db, user)


def grant_permission(
    db: Session,
    user_id: int,
    data: UserPermissionCreate,
    granted_by: int,
    reason: Optional[str] = None,
    step_up_public_reference: Optional[str] = None,
    assurance_method: Optional[str] = None,
) -> UserPermission:
    """منح أو منع صريح — upsert على نفس resource+action+branch.

    Gate 2A: بيجيب المستخدم المستهدف أولاً (404 صريح لو مش موجود، بدل ما
    الـFK constraint يفشل بغموض وقت الـinsert)، ويرفض أي محاولة تستهدف
    حساب role="super_admin" — نشط أو غير نشط، Decision 0003 invariant #2.
    الرفض بيسجّل تحذير أمني منظم (بدون كتابة AuditLog لمحاولة مرفوضة —
    ده مؤجَّل عمدًا لمرحلة audit/step-up القادمة، راجع خطة Gate 2A) ولا
    يعدّل أي صف في الداتابيز.

    **تصحيح TOCTOU (مراجعة Codex المستقلة لـGate 2B3A، 2026-07-18):**
    الراوتر بيتحقق من دور المنفّذ (granted_by) عبر get_super_admin_user
    قبل استهلاك step-up token — بينهم رحلة شبكة/commit كاملة. من غير
    إعادة قفل وفحص هنا، معاملة متزامنة تقدر تخفّض المنفّذ (أو ترقّي
    الهدف لـsuper_admin) في نفس اللحظة والعملية دي تكمل وكأن حالته وقت
    بداية الطلب لسه صحيحة. نفس نمط lock_active_super_admins/
    lock_user_for_update اللي update_user_role بيستخدمه بالظبط (ترتيب
    قفل ثابت يمنع deadlock: مجموعة super_admin النشطين أولاً، بعدين
    الهدف)."""
    active_super_admins = crud.lock_active_super_admins(db)
    if granted_by not in {u.id for u in active_super_admins}:
        raise ActorAuthorizationChangedError(
            "صلاحيتك تغيّرت في نفس اللحظة من عملية أخرى — أعد تحميل حالتك وحاول تاني"
        )

    target = crud.lock_user_for_update(db, user_id)
    if not target:
        raise UserNotFoundError(f"المستخدم {user_id} غير موجود")
    if target.role == "super_admin":
        logger.warning(
            "gate2a.permission_override_rejected target_super_admin "
            "target_user_id=%s resource=%s action=%s granted_by=%s",
            user_id, data.resource, data.action, granted_by,
        )
        _commit_rejected_control_plane_audit(
            db,
            actor_id=granted_by,
            action="permission_override_rejected",
            target_user_id=user_id,
            reason_code="SUPER_ADMIN_PERMISSION_OVERRIDE_FORBIDDEN",
            reason=reason,
            step_up_public_reference=step_up_public_reference,
            assurance_method=assurance_method,
            branch_id=data.branch_id,
            details={
                "resource": data.resource,
                "action": data.action,
                "allowed": data.allowed,
            },
        )
        raise SuperAdminPermissionOverrideForbiddenError(
            "لا يمكن إنشاء أو تعديل صلاحية صريحة تستهدف حساب super_admin — "
            "صلاحيته الكاملة محمية دايمًا ولا تُقيَّد بمنح/منع فردي"
        )

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
            **_step_up_audit_context(
                reason=reason,
                step_up_public_reference=step_up_public_reference,
                assurance_method=assurance_method,
            ),
        }),
    ))

    db.commit()
    db.refresh(perm)
    return perm


def revoke_permission(
    db: Session,
    permission_id: int,
    revoked_by: int,
    reason: Optional[str] = None,
    step_up_public_reference: Optional[str] = None,
    assurance_method: Optional[str] = None,
) -> None:
    """يحذف الاستثناء الصريح تماماً — المستخدم يرجع لسلوك role fallback.

    **تصحيح TOCTOU (مراجعة Codex المستقلة لـGate 2B3A، 2026-07-18):**
    نفس السبب الموثّق في grant_permission — إعادة قفل مجموعة super_admin
    النشطين والتأكد إن المنفّذ (revoked_by) لسه فيها، قبل أي تعديل."""
    active_super_admins = crud.lock_active_super_admins(db)
    if revoked_by not in {u.id for u in active_super_admins}:
        raise ActorAuthorizationChangedError(
            "صلاحيتك تغيّرت في نفس اللحظة من عملية أخرى — أعد تحميل حالتك وحاول تاني"
        )

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
        new_data=json.dumps(_step_up_audit_context(
            reason=reason,
            step_up_public_reference=step_up_public_reference,
            assurance_method=assurance_method,
        )) if reason is not None else None,
    ))

    crud.delete_user_permission(db, perm)
    db.commit()
