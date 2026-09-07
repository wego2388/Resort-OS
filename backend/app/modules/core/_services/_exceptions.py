"""
app/modules/core/_services/_exceptions.py
Extracted from app/modules/core/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations


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
