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
import logging
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

logger = logging.getLogger(__name__)


# ─────────────────────── Super Admin invariants (Gate 2A) ─────────────
# راجع docs/decisions/0003-super-admin-control-plane.md وGate 2 report —
# نفس نمط الـ Exception classes البسيطة (مش ValueError) المستخدمة في
# dining.services لـ Gate 1B: الراوتر بيمسكهم صراحةً بأكواد HTTP دقيقة
# قبل أي `except ValueError` عام، عشان ميتحولوش لـ404/500 مضللين.

class UserNotFoundError(Exception):
    """المستخدم المستهدف غير موجود (أو محذوف) — 404 USER_NOT_FOUND."""


class SuperAdminPermissionOverrideForbiddenError(Exception):
    """محاولة إنشاء/تعديل UserPermission صريح يستهدف حساب super_admin — 409
    SUPER_ADMIN_PERMISSION_OVERRIDE_FORBIDDEN. صلاحية super_admin الكاملة
    محمية دايمًا (Decision 0003 invariants #1/#2) ومش قابلة للتقييد بمنح/
    منع فردي، بصرف النظر عن حالة is_active للحساب المستهدف — حتى super_
    admin غير نشط برضو محمي من إنشاء override جديد عليه (الحذف/التنظيف
    لـoverrides قديمة يفضل مسموح، راجع revoke_permission تحت)."""


class SuperAdminSelfLockoutForbiddenError(Exception):
    """super_admin بيحاول يخفّض دوره أو يعطّل حسابه هو نفسه عبر هذا الـ
    endpoint الروتيني — 409 SUPER_ADMIN_SELF_LOCKOUT_FORBIDDEN (Decision
    0003 invariant #3). تغيير بلا أثر فعلي (no-op) مش مرفوض."""


class LastActiveSuperAdminRequiredError(Exception):
    """التعديل المطلوب هيسيب النظام بدون أي super_admin نشط — 409
    LAST_ACTIVE_SUPER_ADMIN_REQUIRED (Decision 0003 invariant #4)."""


class ActorSuperAdminPrivilegesChangedError(Exception):
    """المنفّذ نفسه (updated_by) بقى مش super_admin نشط لحظة التنفيذ
    الفعلي تحت القفل — حصل تغيير متزامن على حسابه في نفس اللحظة (سباق
    حقيقي بين مُنفّذين، اتحقق منه بـPostgres حي). 409
    ACTOR_SUPER_ADMIN_PRIVILEGES_CHANGED — العميل لازم يعيد تحميل حالته
    ويحاول تاني، مش مجرد إعادة إرسال نفس الطلب."""


class ActorAuthorizationChangedError(Exception):
    """المنفّذ (actor) بقى مش مؤهّل لتنفيذ العملية دي لحظة التنفيذ الفعلي
    تحت القفل — تغيّر دوره أو حالة نشاطه أو فرعه في نفس اللحظة (سباق
    حقيقي بين مُنفّذين). 409 ACTOR_AUTHORIZATION_CHANGED — العميل لازم
    يعيد تحميل حالته ويحاول تاني، مش مجرد إعادة إرسال نفس الطلب.

    Gate 2B3A TOCTOU fix (مراجعة Codex المستقلة، 2026-07-18): step-up
    بيضيف رحلة شبكة/commit كاملة (POST /auth/step-up) بين لحظة ما
    FastAPI dependency يتحقق من دور المنفّذ ولحظة تنفيذ الـmutation
    الفعلي — بيوسّع نافذة السباق اللي كانت أضيق قبل الشريحة دي. نفس
    المشكلة اللي ActorSuperAdminPrivilegesChangedError بتحلّها لـ
    update_user_role (Gate 2A)، لكن أعم (بتشمل admin مش super_admin
    بس، لعمليات زي تعديل إعدادات الفرع)."""


class MandatoryTwoFactorEnrollmentRequiredError(Exception):
    """An active account cannot enter a mandatory-2FA role before enrollment.

    This keeps role promotion from manufacturing a password-only privileged
    account after Gate 2B2. The user may enroll voluntarily first, then be
    promoted through the normal Gate 2A control plane.
    """


# ─────────────────────── Gate 2B3A — step-up audit context ─────────────
# مشترك بين الأربعة mutations المحمية بـstep-up (role update، permission
# grant/revoke، setting upsert) — نفس شكل new_data الإضافي، مكان واحد.
# مفيش عمود جديد على AuditLog (Gate 2B3A ممنوع تنشئ جدول/schema تدقيق
# موازٍ) — كل حاجة إضافية بتتحط جوه new_data JSON الموجود بالفعل.

def _step_up_audit_context(
    *,
    reason: Optional[str] = None,
    step_up_public_reference: Optional[str] = None,
    assurance_method: Optional[str] = None,
) -> dict:
    from app.core.kernel.correlation import get_request_id  # noqa: PLC0415

    context: dict = {}
    if reason is not None:
        context["reason"] = reason
    if step_up_public_reference is not None:
        context["step_up_public_reference"] = step_up_public_reference
    if assurance_method is not None:
        context["assurance_method"] = assurance_method
    request_id = get_request_id()
    if request_id:
        context["request_id"] = request_id
    return context


def _commit_rejected_control_plane_audit(
    db: Session,
    *,
    actor_id: int,
    action: str,
    target_user_id: Optional[int],
    reason_code: str,
    reason: Optional[str] = None,
    step_up_public_reference: Optional[str] = None,
    assurance_method: Optional[str] = None,
    branch_id: Optional[int] = None,
    details: Optional[dict] = None,
) -> None:
    """Persist an attributable, secret-free audit row for a rejected
    super-admin control-plane mutation before raising its domain exception.

    Gate 2A deliberately logged these attempts only to the process logger;
    Gate 2B3B closes that deferred gap in the existing unified ``AuditLog``.
    No business mutation has happened at these call sites, so the commit
    contains only the rejection record and releases any ordered row locks.
    """
    payload = {
        "reason_code": reason_code,
        **(details or {}),
        **_step_up_audit_context(
            reason=reason,
            step_up_public_reference=step_up_public_reference,
            assurance_method=assurance_method,
        ),
    }
    crud.create_audit_log(db, AuditLogCreate(
        user_id=actor_id,
        branch_id=branch_id,
        action=action,
        entity_type="user" if target_user_id is not None else "security_control_plane",
        entity_id=target_user_id,
        new_data=json.dumps(payload, ensure_ascii=False, sort_keys=True),
    ))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


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


# سقف الأدوار المسموح لها تتبدّل عبر PIN — موظفي الشغل الميداني بس
# (نادل حتى مدير). أدوار إدارية/مالية حساسة (accountant/hr_manager/admin/
# super_admin) مستبعدة عمدًا: PIN تشغيلي (4-6 أرقام) أضعف بكتير من
# email+password+2FA الإلزامي على الأدوار دي (§11 CLAUDE.md)، فسماح PIN
# switch عليها كان هيبقى تحايل حقيقي على الـ 2FA الإلزامي.
PIN_SWITCH_MAX_ROLE_LEVEL = 60


def pin_switch_login(db: Session, target_user_id: int, pin: str) -> dict:
    """تبديل هوية المشغّل على جهاز كاشير واحد بدون logout/login كامل — نفس
    الـ JWT infra الموجودة بالظبط (create_access_token)، مش نظام مصادقة
    مواز. **لازم caller يكون مسجّل دخوله فعليًا بالفعل** (الـ router بيحطّه
    خلف get_waiter_user) — الـ endpoint ده مش نقطة دخول أولى للنظام، بس
    وسيلة أسرع لتحديد "مين قاعد على الكاشير دلوقتي" جوه terminal session
    شغالة بالفعل. معرفة PIN الشخص هي إثبات هويته لهذا الغرض بالظبط، زي أي
    نظام POS حقيقي (Foodics/Square/Toast)."""
    from app.core.config import get_settings  # noqa: PLC0415
    from app.core.deps import user_level  # noqa: PLC0415
    from app.core.kernel.models.user import User  # noqa: PLC0415
    from app.core.kernel.security import create_access_token  # noqa: PLC0415
    from datetime import timedelta  # noqa: PLC0415

    target = db.query(User).filter(User.id == target_user_id).first()
    if not target:
        raise ValueError("المستخدم غير موجود")
    if not target.is_active:
        raise ValueError("الحساب غير نشط")
    if user_level(target) > PIN_SWITCH_MAX_ROLE_LEVEL:
        raise ValueError("الحساب ده محتاج تسجيل دخول كامل (إيميل/كلمة سر) — مش عبر PIN")

    if not verify_pin(db, target_user_id, pin):
        raise ValueError("رقم PIN غلط أو الحساب مقفول مؤقتًا بعد محاولات فاشلة")

    settings = get_settings()
    token = create_access_token(
        data={"sub": target.email},
        secret_key=settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": token, "token_type": "bearer", "user": target}


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
    reason: Optional[str] = None,
    step_up_public_reference: Optional[str] = None,
    assurance_method: Optional[str] = None,
):
    """super_admin فقط. أي تغيير فعلي في role أو is_active يُبطل التوكنات
    الحالية للمستخدم فوراً (revoke_user_tokens) — وإلا يستمر بصلاحياته
    القديمة حتى انتهاء التوكن طبيعياً.

    Gate 2A — يحمي 3 ثوابت من Decision 0003 تحت تزامن حقيقي، بترتيب قفل
    ثابت يمنع deadlock (اتأكد بـPostgres حي، راجع
    tests/test_super_admin_concurrency.py):
      1) يقفل كل super_admin النشطين (ORDER BY id) أولاً.
      2) يعيد التحقق إن المنفّذ (updated_by) لسه ضمنهم — مش بس وقت مرور
         get_super_admin_user في بداية الـrequest، لأن حالته ممكن تتغيّر
         في نفس اللحظة من معاملة متزامنة تانية.
      3) يقفل/يجيب المستخدم الهدف بقيمة طازة (بعد قفل المجموعة، مش قبلها
         — نفس الترتيب في كل استدعاء).
      4) يحسب الحالة النهائية الفعلية (role/is_active) من الحالة الحالية
         + الـpayload، لا من الـpayload وحده.
      5) يرفض self-demotion/self-deactivation الفعليين فقط (no-op مسموح)،
         وأي تغيير هيسيب النظام بدون super_admin نشط.
      6) التنفيذ + AuditLog + commit كوحدة واحدة.
    كل رفض بيسجّل تحذير أمني منظم (structured log، بدون أسرار) — كتابة
    AuditLog لمحاولة *مرفوضة* مؤجَّلة عمدًا لمرحلة audit/step-up القادمة
    (Gate 2B+)، عشان معاملة الرفض تفضل قراءة فقط بدون commit مستقل."""
    from app.core.deps import revoke_user_tokens  # noqa: PLC0415
    from app.core.kernel.auth.repository import (  # noqa: PLC0415
        delete_refresh_tokens_for_user,
    )

    active_super_admins = crud.lock_active_super_admins(db)
    active_super_admin_ids = {u.id for u in active_super_admins}

    if updated_by not in active_super_admin_ids:
        logger.warning(
            "gate2a.role_update_rejected actor_not_active_super_admin "
            "updated_by=%s target_user_id=%s",
            updated_by, user_id,
        )
        _commit_rejected_control_plane_audit(
            db,
            actor_id=updated_by,
            action="role_update_rejected",
            target_user_id=user_id,
            reason_code="ACTOR_SUPER_ADMIN_PRIVILEGES_CHANGED",
            reason=reason,
            step_up_public_reference=step_up_public_reference,
            assurance_method=assurance_method,
            details={"requested_role": role, "requested_is_active": is_active},
        )
        raise ActorSuperAdminPrivilegesChangedError(
            "صلاحيتك تغيّرت في نفس اللحظة من عملية أخرى — أعد تحميل حالتك وحاول تاني"
        )

    user = crud.lock_user_for_update(db, user_id)
    if not user:
        raise UserNotFoundError(f"المستخدم {user_id} غير موجود")

    final_role = role if role is not None else user.role
    final_is_active = is_active if is_active is not None else user.is_active

    role_changing = role is not None and role != user.role
    is_active_changing = is_active is not None and is_active != user.is_active
    self_deactivating = is_active_changing and is_active is False

    from app.core.deps import MANDATORY_2FA_ROLES  # noqa: PLC0415

    if (
        final_is_active
        and final_role in MANDATORY_2FA_ROLES
        and not user.two_factor_enabled
    ):
        raise MandatoryTwoFactorEnrollmentRequiredError(
            "يجب تفعيل التحقق بخطوتين على الحساب قبل منحه أو إعادة تفعيل "
            "دور super_admin/accountant"
        )

    if updated_by == user_id and (role_changing or self_deactivating):
        logger.warning(
            "gate2a.role_update_rejected self_lockout_attempt "
            "user_id=%s requested_role=%s requested_is_active=%s",
            user_id, role, is_active,
        )
        _commit_rejected_control_plane_audit(
            db,
            actor_id=updated_by,
            action="role_update_rejected",
            target_user_id=user_id,
            reason_code="SUPER_ADMIN_SELF_LOCKOUT_FORBIDDEN",
            reason=reason,
            step_up_public_reference=step_up_public_reference,
            assurance_method=assurance_method,
            details={"requested_role": role, "requested_is_active": is_active},
        )
        raise SuperAdminSelfLockoutForbiddenError(
            "لا يمكنك تعديل دورك أو تعطيل حسابك بنفسك عبر هذا المسار — "
            "اطلب من super_admin آخر تنفيذ هذا التغيير"
        )

    target_is_active_super_admin = user_id in active_super_admin_ids
    target_leaving_active_super_admin_set = target_is_active_super_admin and (
        final_role != "super_admin" or not final_is_active
    )
    if target_leaving_active_super_admin_set and len(active_super_admin_ids) <= 1:
        logger.warning(
            "gate2a.role_update_rejected last_active_super_admin "
            "updated_by=%s target_user_id=%s",
            updated_by, user_id,
        )
        _commit_rejected_control_plane_audit(
            db,
            actor_id=updated_by,
            action="role_update_rejected",
            target_user_id=user_id,
            reason_code="LAST_ACTIVE_SUPER_ADMIN_REQUIRED",
            reason=reason,
            step_up_public_reference=step_up_public_reference,
            assurance_method=assurance_method,
            details={"requested_role": role, "requested_is_active": is_active},
        )
        raise LastActiveSuperAdminRequiredError(
            "لازم يفضل يوجد super_admin نشط واحد على الأقل — "
            "فعّل أو رقّي حساب super_admin تاني قبل تنفيذ هذا التغيير"
        )

    old_data = {"role": user.role, "is_active": user.is_active}
    changed = role_changing or is_active_changing

    if changed:
        user.role = final_role
        user.is_active = final_is_active
        crud.create_audit_log(db, AuditLogCreate(
            user_id=updated_by,
            entity_type="user",
            entity_id=user.id,
            action="update_role",
            old_data=json.dumps(old_data),
            new_data=json.dumps({
                "role": final_role,
                "is_active": final_is_active,
                **_step_up_audit_context(
                    reason=reason,
                    step_up_public_reference=step_up_public_reference,
                    assurance_method=assurance_method,
                ),
            }),
        ))
        # Refresh sessions are database state and therefore belong to the same
        # transaction as the role/status mutation. The access-token cutoff is
        # a cache side effect and is published only after the commit succeeds.
        delete_refresh_tokens_for_user(db, user.id)

    db.commit()
    if changed:
        revoke_user_tokens(user.id)
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
    reason: Optional[str] = None,
    step_up_public_reference: Optional[str] = None,
    assurance_method: Optional[str] = None,
) -> SettingRead:
    """**تصحيحان (مراجعة Codex المستقلة لـGate 2B3A، 2026-07-18):**

    1. TOCTOU: نفس نمط grant_permission/revoke_permission — لو updated_by
       متوفر (المسار الحقيقي عبر HTTP دايمًا بيوفّره)، بنقفل صف المنفّذ
       ونتأكد إنه لسه نشط وبمستوى الدور المطلوب (super_admin للإعدادات
       العامة، admin+ للفرعية) + عزل الفرع الحقيقي، قبل أي تعديل. مسارات
       داخلية/seed بدون updated_by (None) بتتخطى الفحص ده زي ما كانت.
    2. تسريب القيمة العامة في سجل التدقيق: old_value كان بيُحسب عبر
       crud.get_setting() اللي بترجع fallback للعام لو مفيش صف للفرع —
       يعني "القيمة القديمة" في AuditLog كانت ممكن تظهر قيمة إعداد عام
       لمدير فرع مالوش صف أصلاً، بدل ما توضح إنه إنشاء جديد فعليًا.
       get_setting_exact() (بدون fallback) هي المصدر الصحيح هنا.
    """
    if updated_by is not None:
        from app.core.deps import user_level  # noqa: PLC0415

        actor = crud.lock_user_for_update(db, updated_by)
        required_level = 100 if branch_id is None else 80
        if not actor or not actor.is_active or user_level(actor) < required_level:
            raise ActorAuthorizationChangedError(
                "صلاحيتك تغيّرت في نفس اللحظة من عملية أخرى — أعد تحميل حالتك وحاول تاني"
            )
        if branch_id is not None and user_level(actor) < 100:
            assert_branch_access(db, actor, branch_id, "تعديل إعدادات هذا الفرع")

    old_row = crud.get_setting_exact(db, key, branch_id)
    old_value = old_row.value if old_row else None

    row = crud.upsert_setting(db, key, value, branch_id)

    crud.create_audit_log(db, AuditLogCreate(
        user_id=updated_by,
        branch_id=branch_id,
        action="update",
        entity_type="setting",
        entity_id=row.id,
        old_data=json.dumps({"value": old_value}),
        new_data=json.dumps({
            "value": value,
            **_step_up_audit_context(
                reason=reason,
                step_up_public_reference=step_up_public_reference,
                assurance_method=assurance_method,
            ),
        }),
    ))

    db.commit()
    db.refresh(row)
    return SettingRead.model_validate(row)


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

    effective_branch_id = branch_id if branch_id is not None else getattr(user, "branch_id", None)
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


def get_effective_permissions(db: Session, user) -> list[EffectivePermission]:
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
            getattr(user, "branch_id", None), role_fallback=role_fallback,
        )
        result.append(EffectivePermission(
            resource=entry["resource"], action=entry["action"],
            label_ar=entry["label_ar"], module=entry["module"],
            allowed=allowed, source=source,
        ))
    return result


# ─────────────────────── Branch Access (Gate 1 containment) ───────────
# جذر المشكلة (اتأكد منه بالبحث قبل الكتابة): User (app.core.kernel.
# models.user) معندوش عمود branch_id خالص — الطريق الوحيد الموجود فعليًا
# لمعرفة فرع المستخدم هو HR.Employee.branch_id عبر Employee.user_id
# (اختياري/nullable، ومش مستخدم في app.core.deps خالص لحد دلوقتي).
# نمط المقارنة (fetch resource → قارن owner/branch field → PermissionError
# يترجمها الـ router لـ 403) مستوحى من finance.services.build_shift_end_report،
# لكن التخطي الكامل هنا مقصور على super_admin فقط (Decision 0003) — راجع
# تصحيح assert_branch_access تحت لسبب الاختلاف عن سابقة build_shift_end_report.

def get_user_branch_id(db: Session, user) -> Optional[int]:
    """فرع المستخدم الفعلي عبر HR.Employee.user_id — None لو مفيش سجل
    Employee مرتبط (حسابات super_admin/admin التجريبية مثلاً)."""
    from app.modules.hr.models import Employee  # noqa: PLC0415

    employee = db.query(Employee).filter(Employee.user_id == user.id).first()
    return employee.branch_id if employee else None


def assert_branch_access(db: Session, user, target_branch_id: int, action_desc: str) -> None:
    """يمنع مستخدم من فرع تنفيذ إجراء حسّاس على مورد فرع تاني.

    **تصحيح (جولة مراجعة Codex الثانية، 2026-07-17):** النسخة الأولى كانت
    بتدّي أي level>=60 (manager/accountant/hr_manager) تخطي الفحص كامل،
    بالقياس الخاطئ على build_shift_end_report's owner-check bypass — ده
    فحص ملكية سجل (مين الكاشير) مالوش أي بعد فرع أصلًا، مش سابقة لثقة
    عبر الفروع. القرار المعتمد الوحيد لتخطي كامل عبر الفروع هو
    super_admin حصريًا (docs/decisions/0003-super-admin-control-plane.md).
    أي دور تاني (بما فيه manager) لازم يطابق Employee.branch_id فعليًا،
    أو صلاحية صريحة موثّقة عبر has_permission/UserPermission لاحقًا — مفيش
    استثناء ضمني لمستوى الدور بس. حساب بلا Employee مرتبط بيتمنع صراحةً
    (fail-closed) بدل ما يتسمحله ضمنيًا."""
    from app.core.deps import user_level  # noqa: PLC0415

    if user_level(user) >= 100:  # super_admin حصريًا — Decision 0003
        return
    acting_branch_id = get_user_branch_id(db, user)
    if acting_branch_id is None:
        raise PermissionError(f"حسابك غير مرتبط بفرع — تواصل مع الإدارة قبل {action_desc}")
    if acting_branch_id != target_branch_id:
        raise PermissionError(f"لا يمكنك {action_desc} في فرع آخر")


def list_guest_alerts(
    db: Session, branch_id: int, requesting_user, skip: int = 0, limit: int = 20,
) -> tuple[list[GuestAlert], int]:
    """راجع docstring GET /alerts (core/api/router.py) — كانت بتنادي
    crud.list_active_alerts مباشرة من الـ router (تجاوز طبقة service)، وكانت
    بتثق في branch_id من العميل من غير أي تحقق ملكية. اتصلح الاتنين مع بعض."""
    assert_branch_access(db, requesting_user, branch_id, "عرض تنبيهات")
    return crud.list_active_alerts(db, branch_id, skip=skip, limit=limit)


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

def assert_guest_alerts_enabled(db: Session, branch_id: int) -> None:
    """Gate 1 containment (جولة مراجعة Codex الثانية، 2026-07-17): هذا
    الـ endpoint عام تمامًا بدون auth، context_id مش FK حقيقي (راجع
    GuestAlert docstring)، ومفيش أي تحقق إن context_id ينتمي فعليًا
    لـbranch_id. الـcontext_type mismatch (`dining_table` مش ضمن الـenum
    الحالي) بيوقف مسار المطعم/الكافيه بالصدفة بس — context_type زي
    `room`/`beach_location`/`other` لسه شغالين اليوم بلا أي تحقق حقيقي.
    عمدًا **لا نصلح** الـenum mismatch هنا (ده يفتح باب Gate 8 قبل وقته)
    — بدل كده نقفل الـendpoint كله.

    **تصحيح (جولة مراجعة Codex الثالثة):** AGENTS.md بيمنع الاعتماد على
    core.Setting (حر، قابل للتعديل عبر API الإعدادات) كبوابة أمان لوحدها.
    لازم الاتنين معًا: settings.GUEST_ALERTS_ENABLED (typed،
    deployment-level) + core.Setting الخاص بالفرع (core.guest_alerts_enabled)."""
    from app.core.config import settings  # noqa: PLC0415

    if not settings.GUEST_ALERTS_ENABLED:
        raise ValueError("نداء الضيف غير متاح حاليًا")

    raw_value = get_setting_value(
        db, "core.guest_alerts_enabled", branch_id=branch_id, default="false",
    )
    enabled = str(raw_value).strip().lower() in ("1", "true", "yes", "y", "نعم")
    if not enabled:
        raise ValueError("نداء الضيف غير متاح حاليًا")


def create_guest_alert(db: Session, data: GuestAlertCreate) -> GuestAlert:
    if not crud.get_branch(db, data.branch_id):
        raise ValueError(f"الفرع {data.branch_id} غير موجود")
    assert_guest_alerts_enabled(db, data.branch_id)

    alert = crud.create_guest_alert(db, data)
    db.commit()
    db.refresh(alert)
    return alert


def update_alert_status(
    db: Session,
    alert_id: int,
    new_status: str,
    resolved_by: int,
    requesting_user,
) -> GuestAlert:
    """Gate 1 containment (جولة تصحيح ثانية، 2026-07-17): كان بيقبل
    alert_id من أي نادل+ من غير أي تحقق فرع، تمامًا زي باج GET /alerts
    الأصلي — نادل من فرع تاني كان يقدر يقفل/يأكد تنبيه فرع مختلف تمامًا.
    requesting_user إجباري (مش Optional) عمدًا — الـ caller الوحيد هو
    الـ router ومعاه دايمًا مستخدم مصادَق عليه حقيقي؛ مفيش سبب مشروع
    يسمح بتخطي الفحص هنا (نفس نمط check_in_reservation بعد جولة مراجعة
    Codex الثالثة، اللي شالت أي باب تخطٍ اختباري منها بالكامل برضو)."""
    alert = crud.get_guest_alert(db, alert_id)
    if not alert:
        raise ValueError(f"التنبيه {alert_id} غير موجود")
    assert_branch_access(db, requesting_user, alert.branch_id, "تحديث حالة تنبيه")
    if alert.status == "resolved":
        raise ValueError("التنبيه مُتعامَل معه بالفعل")

    alert = crud.update_alert_status(db, alert, new_status, resolved_by=resolved_by)
    db.commit()
    db.refresh(alert)
    return alert
