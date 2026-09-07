"""
app/modules/core/_services/accounts.py
Extracted from app/modules/core/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.modules.core import crud
from app.modules.core.schemas import (
    AuditLogCreate,
    UserCreate,
    normalize_staff_language,
)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.core.kernel.models.user import User  # noqa: F401
from app.modules.core._services._exceptions import (
    UserNotFoundError,
    SuperAdminSelfLockoutForbiddenError,
    LastActiveSuperAdminRequiredError,
    ActorSuperAdminPrivilegesChangedError,
    MandatoryTwoFactorEnrollmentRequiredError,
)
from app.modules.core._services._audit_helpers import (
    _step_up_audit_context,
    _commit_rejected_control_plane_audit,
)
import logging
logger = logging.getLogger(__name__)


def update_user_preferences(
    db: Session,
    *,
    user: "User",
    preferred_language: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> "User":
    """Persist the authenticated user's personal display language.

    The HTTP layer derives ``user`` from the access token and the schema has
    already constrained ``preferred_language`` to the staff ``ar|en`` policy.
    Keeping the real-change decision, audit write, and commit here preserves
    the repository's router -> service -> CRUD transaction boundary.
    """
    old_raw = user.preferred_language
    if (
        normalize_staff_language(old_raw) == preferred_language
        and old_raw == preferred_language
    ):
        return user

    user.preferred_language = preferred_language
    crud.create_audit_log(db, AuditLogCreate(
        user_id=user.id,
        action="user.preferences.language_changed",
        entity_type="user",
        entity_id=user.id,
        old_data=json.dumps({"preferred_language": old_raw}),
        new_data=json.dumps({"preferred_language": preferred_language}),
        ip_address=ip_address,
        user_agent=user_agent,
    ))
    db.commit()
    db.refresh(user)
    return user


def create_staff_account(
    db: Session,
    data: "UserCreate",
    created_by: int,
) -> "User":
    """super_admin فقط — إنشاء حساب موظف جديد بباسورد مؤقت.

    - يستخدم kernel's AuthService.register() لـ password hashing/validation.
    - يضبط role + must_change_password=True بعد الإنشاء فوراً داخل نفس الـ transaction.
    - يسجّل AuditLog كامل ثم يعمل commit وحيد.
    - لا ينشئ super_admin — schema.UserCreate.role validator يرفضه بـ 422.
    """
    from app.core.config import get_settings  # noqa: PLC0415
    from app.core.kernel.auth.service import AuthService  # noqa: PLC0415
    from app.core.kernel.models.user import User  # noqa: PLC0415

    settings = get_settings()

    # تحقق من تفرّد الإيميل (AuthService.register بيفحصها بالفعل لكن
    # يرمي HTTPException مباشرة — نفحص هنا قبله بـ ValueError لعدم تسريب
    # كود HTTP من طبقة service)
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise ValueError(f"البريد الإلكتروني '{data.email}' مستخدم مسبقاً")

    auth_svc = AuthService(db, User, settings)
    user = auth_svc.register(
        email=data.email,
        password=data.password,
        full_name=data.full_name,
        phone=data.phone,
    )

    # ضبط role + must_change_password داخل نفس الـ session قبل الـ commit
    user.role = data.role
    user.must_change_password = True
    db.add(user)

    crud.create_audit_log(db, AuditLogCreate(
        user_id=created_by,
        action="user.created",
        entity_type="user",
        entity_id=user.id,
        new_data=json.dumps({
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "must_change_password": True,
        }),
    ))

    db.commit()
    db.refresh(user)
    return user


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


# ─────────────────────── Account Recovery (Gate 2B3A) ─────────────────
# 2026-08-03: كانت auth/service.py's login lockout و2FA بتضبط
# failed_login_attempts/account_locked_until/two_factor_enabled فعليًا،
# بس مفيش أي endpoint إداري كان بيقدر يعكسهم — موظف غلط كلمة السر
# 5 مرات كان لازم يستنى LOCKOUT_MINUTES كاملة بلا أي تجاوز، وموظف فقد
# جهاز/أكواد الـ2FA بتاعته كان عالق للأبد إلا لو حد يدخل السيرفر بنفسه
# (admin_bootstrap recover، أداة CLI فقط). الدالتان دول أضيق عمدًا من
# admin_bootstrap recover — مبيلمسوش كلمة السر ولا الهوية، بس نفس
# الفحص (super_admin + step-up) زي أي عملية تانية في الـcontrol plane.

def unlock_user_account(
    db: Session, user_id: int, unlocked_by: int,
    step_up_public_reference: Optional[str] = None,
    assurance_method: Optional[str] = None,
) -> "User":
    """يفك قفل حساب بعد محاولات دخول فاشلة متكررة — عملية ضيّقة، مبتلمسش
    role/is_active/password/2FA خالص."""
    user = crud.lock_user_for_update(db, user_id)
    if not user:
        raise UserNotFoundError(f"المستخدم {user_id} غير موجود")

    was_locked = bool(user.account_locked_until)
    user.account_locked_until = None
    user.failed_login_attempts = 0

    from app.modules.core.crud import create_audit_log  # noqa: PLC0415
    from app.modules.core.schemas import AuditLogCreate  # noqa: PLC0415
    create_audit_log(db, AuditLogCreate(
        user_id=unlocked_by, branch_id=None, action="unlock_user_account",
        entity_type="user", entity_id=user.id,
        old_data=json.dumps({"was_locked": was_locked}),
        new_data=json.dumps({
            "unlocked": True,
            **_step_up_audit_context(
                step_up_public_reference=step_up_public_reference,
                assurance_method=assurance_method,
            ),
        }),
    ))
    db.commit()
    db.refresh(user)
    return user


def force_reset_2fa(
    db: Session, user_id: int, reset_by: int, reason: str,
    step_up_public_reference: Optional[str] = None,
    assurance_method: Optional[str] = None,
) -> dict:
    """Reset a lost 2FA device without stranding the account.

    Roles whose 2FA is mandatory receive a fresh, short-lived enrollment
    token returned once to the super-admin. Optional roles have every stale
    bootstrap marker cleared and can continue with their existing password.
    Password/identity/active state are deliberately preserved.
    """
    from app.core.deps import revoke_user_tokens  # noqa: PLC0415
    from app.core.deps import MANDATORY_2FA_ROLES  # noqa: PLC0415
    from app.core.kernel.auth.repository import delete_refresh_tokens_for_user  # noqa: PLC0415
    from app.core.kernel.models.user import TwoFactorRecoveryCode  # noqa: PLC0415

    user = crud.lock_user_for_update(db, user_id)
    if not user:
        raise UserNotFoundError(f"المستخدم {user_id} غير موجود")

    user.two_factor_enabled = False
    user.two_factor_secret = None
    user.two_factor_last_used_step = None
    requires_enrollment = user.role in MANDATORY_2FA_ROLES
    enrollment_token = secrets.token_urlsafe(32) if requires_enrollment else None
    enrollment_expires_at = (
        datetime.now(timezone.utc) + timedelta(
            minutes=settings.TWO_FACTOR_ENROLLMENT_TOKEN_TTL_MINUTES,
        )
        if requires_enrollment else None
    )
    user.two_factor_bootstrap_required = requires_enrollment
    user.two_factor_enrollment_token_hash = (
        hashlib.sha256(enrollment_token.encode()).hexdigest()
        if enrollment_token else None
    )
    user.two_factor_enrollment_expires_at = enrollment_expires_at
    db.query(TwoFactorRecoveryCode).filter(
        TwoFactorRecoveryCode.user_id == user.id,
    ).delete(synchronize_session=False)
    delete_refresh_tokens_for_user(db, user.id)

    from app.modules.core.crud import create_audit_log  # noqa: PLC0415
    from app.modules.core.schemas import AuditLogCreate  # noqa: PLC0415
    create_audit_log(db, AuditLogCreate(
        user_id=reset_by, branch_id=None, action="force_reset_2fa",
        entity_type="user", entity_id=user.id,
        new_data=json.dumps({
            "requires_2fa_enrollment": requires_enrollment,
            "enrollment_expires_at": (
                enrollment_expires_at.isoformat() if enrollment_expires_at else None
            ),
            **_step_up_audit_context(
                reason=reason,
                step_up_public_reference=step_up_public_reference,
                assurance_method=assurance_method,
            ),
        }),
    ))
    db.commit()
    # التوكنات الحالية لازم تتجدد بعد تغيير أمني زي ده — نفس نمط أي
    # تغيير role/is_active (راجع update_user_role فوق).
    revoke_user_tokens(user.id)
    db.refresh(user)
    return {
        "user": user,
        "enrollment_token": enrollment_token,
        "enrollment_expires_at": enrollment_expires_at,
    }


def reset_staff_credentials(
    db: Session, user_id: int, reset_by: int, reason: str,
    step_up_public_reference: Optional[str] = None,
    assurance_method: Optional[str] = None,
) -> dict:
    """يولّد باسورد مؤقت جديد + رابط تفعيل 2FA جديد لموظف عادي نسي/غلط
    بيانات دخوله — بديل ويب آمن لـ`admin_bootstrap recover` الـCLI، اللي
    كان قبل كده الطريقة الوحيدة (لازم SSH على السيرفر فعليًا). مقصور
    عمدًا على الأدوار العادية: super_admin/owner يفضلوا CLI-only بنفس
    القيد اللي `provision_account_bootstrap`'s `create` بيفرضه فعليًا
    (`BOOTSTRAP_CREATABLE_ROLES`) — جلسة سوبر أدمن مخترقة على الويب
    ميتقدرش تولّد بيانات دخول لحساب سوبر أدمن/مالك تاني."""
    from app.core.deps import revoke_user_tokens  # noqa: PLC0415
    from app.core.deps import MANDATORY_2FA_ROLES  # noqa: PLC0415
    from app.core.kernel.auth.repository import delete_refresh_tokens_for_user  # noqa: PLC0415
    from app.core.kernel.auth.service import AuthService, BOOTSTRAP_CREATABLE_ROLES  # noqa: PLC0415
    from app.core.kernel.models.user import TwoFactorRecoveryCode  # noqa: PLC0415
    from app.core.kernel.security import get_password_hash  # noqa: PLC0415

    user = crud.lock_user_for_update(db, user_id)
    if not user:
        raise UserNotFoundError(f"المستخدم {user_id} غير موجود")
    if user.role in BOOTSTRAP_CREATABLE_ROLES:
        raise PermissionError(
            "حسابات super_admin/owner لا تُعاد تعيينها عبر الويب — "
            "استخدم `python -m app.admin_bootstrap recover` من على "
            "السيرفر مباشرة."
        )

    temporary_password = AuthService._new_temporary_password()
    requires_enrollment = user.role in MANDATORY_2FA_ROLES
    enrollment_token = secrets.token_urlsafe(32) if requires_enrollment else None
    enrollment_expires_at = (
        datetime.now(timezone.utc) + timedelta(
            minutes=settings.TWO_FACTOR_ENROLLMENT_TOKEN_TTL_MINUTES,
        )
        if requires_enrollment else None
    )

    user.password_hash = get_password_hash(temporary_password)
    user.must_change_password = True
    user.failed_login_attempts = 0
    user.account_locked_until = None
    user.two_factor_enabled = False
    user.two_factor_secret = None
    user.two_factor_last_used_step = None
    user.two_factor_bootstrap_required = requires_enrollment
    user.two_factor_enrollment_token_hash = (
        hashlib.sha256(enrollment_token.encode()).hexdigest()
        if enrollment_token else None
    )
    user.two_factor_enrollment_expires_at = enrollment_expires_at
    db.query(TwoFactorRecoveryCode).filter(
        TwoFactorRecoveryCode.user_id == user.id,
    ).delete(synchronize_session=False)
    delete_refresh_tokens_for_user(db, user.id)

    from app.modules.core.crud import create_audit_log  # noqa: PLC0415
    from app.modules.core.schemas import AuditLogCreate  # noqa: PLC0415
    create_audit_log(db, AuditLogCreate(
        user_id=reset_by, branch_id=None, action="reset_staff_credentials",
        entity_type="user", entity_id=user.id,
        new_data=json.dumps({
            "requires_2fa_enrollment": requires_enrollment,
            **_step_up_audit_context(
                reason=reason,
                step_up_public_reference=step_up_public_reference,
                assurance_method=assurance_method,
            ),
        }),
    ))
    db.commit()
    # التوكنات الحالية لازم تتجدد بعد تغيير أمني زي ده — نفس نمط
    # force_reset_2fa/update_user_role.
    revoke_user_tokens(user.id)
    db.refresh(user)
    return {
        "user": user,
        "temporary_password": temporary_password,
        "enrollment_token": enrollment_token,
        "enrollment_expires_at": enrollment_expires_at,
    }


# ─────────────────────── Settings ────────────────────────────────────
