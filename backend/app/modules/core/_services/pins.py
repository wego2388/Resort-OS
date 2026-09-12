"""
app/modules/core/_services/pins.py
Extracted from app/modules/core/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session
from app.modules.core import crud
from app.modules.core.models import PinCredential, UserBranchMembership
from app.modules.core._services.authorization import (
    BranchAccessDeniedError,
    BranchContextRequiredError,
    get_user_branch_id,
    _can_enter_branch,
)


# ─────────────────────── PIN Credentials ──────────────────────────────
# راجع PinCredential (models.py) للسياق الكامل — PIN تشغيلي منفصل عن
# JWT، مُستخدم لموافقة مدير سريعة على إجراء حسّاس (إلغاء/مرتجع) لما
# المنفّذ الفعلي أقل من المستوى المطلوب.

PIN_MAX_ATTEMPTS = 3       # 3 محاولات غلط = قفل
PIN_LOCKOUT_SECONDS = 60   # دقيقة واحدة
TERMINAL_OPERATOR_ROLES = ("waiter", "cashier", "supervisor", "manager")


def assert_can_manage_target_pin(db: Session, actor, target_user_id: int, action_desc: str) -> None:
    """⚠️ باج حقيقي كان هنا (مراجعة Codex 2026-08-30، M-02): أي مدير كان
    يقدر يقرا أو يعيد ضبط PIN أي user_id — بدون تحقق من وجود الهدف، فرعه،
    أو مستواه النسبي. النتيجة: مدير يقدر يعيد ضبط PIN مدير نظير (أو حتى
    أعلى) في فرع تاني تمامًا، بعدها ينتحل هويته على أي terminal مؤهّل أو
    يزوّر attribution موافقة PIN — نفس فئة الخطر (مصادقة بديلة موازية
    للـJWT، راجع resolve_pin_approval) لازم تتحمي بنفس الجدية.

    القاعدة: نفس الفرع النشط للفاعل + target أدنى من الفاعل صراحةً (يمنع
    peers/higher تمامًا) — مطبّقة حتى على super_admin (100) عشان تفضل
    متسقة مع فلسفة assert_branch_access (سياق فرع نشط حقيقي، مش تجاوز
    مطلق) ومع القاعدة نفسها بتمنع مدير يعيد ضبط PIN مدير تاني بنفس
    مستواه بالظبط."""
    from app.core.deps import user_level as _user_level  # noqa: PLC0415
    from app.core.kernel.models.user import User  # noqa: PLC0415

    target = db.query(User).filter(User.id == target_user_id).first()
    if not target:
        raise ValueError(f"المستخدم {target_user_id} غير موجود")

    actor_branch_id = get_user_branch_id(db, actor)
    if actor_branch_id is None:
        raise BranchContextRequiredError(f"اختر فرعًا نشطًا قبل {action_desc}")

    target_in_branch = (
        db.query(UserBranchMembership.id)
        .filter(
            UserBranchMembership.user_id == target.id,
            UserBranchMembership.branch_id == actor_branch_id,
            UserBranchMembership.is_active.is_(True),
        )
        .first()
        is not None
    )
    if not target_in_branch:
        raise BranchAccessDeniedError(f"لا يمكنك {action_desc} لمستخدم خارج فرعك الحالي")

    if _user_level(target) >= _user_level(actor):
        raise PermissionError(f"لا يمكنك {action_desc} لمستخدم بنفس مستواك أو أعلى")


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


def list_terminal_operators(db: Session, branch_id: int) -> list:
    """مشغّلو POS القابلون للتبديل بالـPIN داخل الفرع النشط فقط.

    تختلف عمدًا عن ``list_eligible_approvers``: تلك قائمة موافقات للكاشير
    حسب مستوى أدنى، أما هذه فقائمة تشغيل waiter↔cashier لا تعرض موظفًا بلا
    PIN ولا دورًا خارج تشغيل الصالة، وتفرض عضوية الفرع قبل كشف الاسم.
    """
    from app.core.kernel.models.user import User  # noqa: PLC0415

    return (
        db.query(User)
        .join(UserBranchMembership, UserBranchMembership.user_id == User.id)
        .join(PinCredential, PinCredential.user_id == User.id)
        .filter(
            User.role.in_(TERMINAL_OPERATOR_ROLES),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
            UserBranchMembership.branch_id == branch_id,
            UserBranchMembership.is_active.is_(True),
        )
        .order_by(User.full_name)
        .all()
    )


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
    target_branch_id: int,
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

    ⚠️ مراجعة Codex 2026-08-31 (SEC-07): قبل كده الدالة دي كانت بتتحقق من
    دور المعتمِد وPIN بس — **من غير أي تحقق فرع خالص**. مدير فرع A كان
    يقدر PIN بتاعه يوافق على إلغاء/خصم/حركة كاش في فرع B بمجرد ما الكاشير
    يعرف/يخمّن user_id بتاعه. ``target_branch_id`` بقى إجباري — نفس
    الفحص المستخدم في ``pin_switch_login`` (``_can_enter_branch``:
    super_admin بس بيتخطّى، وإلا لازم عضوية فرع فعّالة حقيقية).
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
    if not _can_enter_branch(db, approver, target_branch_id):
        raise ValueError("المعتمِد غير مصرح له بهذا الفرع")

    if not verify_pin(db, approver_user_id, approver_pin):
        raise ValueError("رقم PIN غلط أو الحساب مقفول مؤقتًا بعد محاولات فاشلة")

    return approver_user_id


# سقف الأدوار المسموح لها تتبدّل عبر PIN — موظفي الشغل الميداني بس
# (نادل حتى مدير). أدوار إدارية/مالية حساسة (accountant/hr_manager/admin/
# super_admin) مستبعدة عمدًا: PIN تشغيلي (4-6 أرقام) أضعف بكتير من
# email+password+2FA الإلزامي على الأدوار دي (§11 CLAUDE.md)، فسماح PIN
# switch عليها كان هيبقى تحايل حقيقي على الـ 2FA الإلزامي.
PIN_SWITCH_MAX_ROLE_LEVEL = 60


class PinBranchMismatchError(ValueError):
    """The requested POS identity is not authorized in the terminal branch."""


def pin_switch_login(
    db: Session,
    target_user_id: int,
    pin: str,
    *,
    active_branch_id: Optional[int],
) -> dict:
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
    if active_branch_id is None:
        raise ValueError("اختر فرعًا نشطًا قبل تبديل المشغّل")
    if not _can_enter_branch(db, target, active_branch_id):
        raise PinBranchMismatchError(
            "المستخدم المطلوب غير مصرح له بالفرع النشط على الجهاز"
        )

    if not verify_pin(db, target_user_id, pin):
        raise ValueError("رقم PIN غلط أو الحساب مقفول مؤقتًا بعد محاولات فاشلة")

    settings = get_settings()
    token = create_access_token(
        data={"sub": target.email, "bid": active_branch_id},
        secret_key=settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": token, "token_type": "bearer", "user": target}


# ─────────────────────── Branch ──────────────────────────────────────
