"""Gate 2B3A — canonical step-up scope builder.

A step-up grant (``app.core.kernel.models.user.StepUpGrant``) is issued for
one exact operation and must be consumed for that exact operation, never a
different one. "Exact" is defined here, once, as a deterministic JSON
document (sorted keys, no whitespace) hashed with SHA-256 — both the issuing
endpoint (``POST /auth/step-up``) and every consuming endpoint call the same
purpose-specific builder function below, so the two sides can never drift
apart by one of them forgetting a field the other checks.

Nothing sensitive goes into the scope in the clear: a free-text ``reason``
or a new setting ``value`` is hashed with :func:`_sha256_text` *before* it
enters the scope document, so the scope itself (and therefore anything
derived from it) never reveals the underlying secret/business text — only
that a specific hash of it was what the operator confirmed.
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional


def sha256_text(value: Optional[str]) -> str:
    """SHA-256 of free text, using the same "empty string for None" rule
    everywhere a reason/value might legitimately be blank at the type level
    but must still hash deterministically."""
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def build_step_up_scope(purpose: str, intent: dict) -> str:
    """SHA-256 of a deterministic JSON document — the single source of
    truth for "does this proof match this operation". ``intent`` must only
    contain non-secret identifiers and digests (see module docstring), never
    a raw secret, password, TOTP code, or business free-text value."""
    canonical = json.dumps(
        {"purpose": purpose, **intent},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── Per-purpose scope builders ──────────────────────────────────────────
# One function per purpose so the issuing endpoint and the consuming
# endpoint import the exact same builder — never hand-roll the intent dict
# at either call site.

def user_provision_scope(
    *,
    email: str,
    full_name: str,
    phone: Optional[str],
    employee_id: Optional[int],
    role: str,
    preferred_language: str,
    reason: str,
) -> str:
    """Bind account creation to the exact normalized staff identity.

    Email, name, phone, and reason are personal/free text, so only their
    digests enter the canonical scope document.
    """
    return build_step_up_scope("user_provision", {
        "email_sha256": sha256_text(email.strip().casefold()),
        "full_name_sha256": sha256_text(full_name.strip()),
        "phone_sha256": sha256_text((phone or "").strip()),
        "employee_id": employee_id,
        "role": role,
        "preferred_language": preferred_language,
        "reason_sha256": sha256_text(reason),
    })


def user_role_update_scope(
    *, user_id: int, role: Optional[str], is_active: Optional[bool], reason: str,
) -> str:
    return build_step_up_scope("user_role_update", {
        "user_id": user_id,
        "role": role,
        "is_active": is_active,
        "reason_sha256": sha256_text(reason),
    })


def user_unlock_scope(*, user_id: int) -> str:
    """2026-08-03: فك قفل حساب بعد محاولات دخول فاشلة متكررة — عملية
    ضيّقة (بترجّع failed_login_attempts/account_locked_until للصفر بس،
    مش مثل user_role_update اللي بتغيّر role/is_active)، فبروفها مربوط
    بالمستخدم الهدف بس، بلا حاجة لـreason (نفس مستوى session_revoke)."""
    return build_step_up_scope("user_unlock", {"user_id": user_id})


def user_force_2fa_reset_scope(*, user_id: int, reason: str) -> str:
    """2026-08-03: إعادة ضبط 2FA لموظف فقد جهازه/أكواده الاحتياطية —
    بيمسح two_factor_enabled/secret فقط (مش زي admin_bootstrap recover
    الـCLI اللي بيعمل reset كامل للهوية+كلمة السر). الموظف بيدخل بكلمة
    السر الحالية بتاعته ويعيد التسجيل عبر /2fa/setup العادي (current_
    password، مش enrollment token)."""
    return build_step_up_scope("user_force_2fa_reset", {
        "user_id": user_id,
        "reason_sha256": sha256_text(reason),
    })


def staff_credentials_reset_scope(*, user_id: int, reason: str) -> str:
    """2026-08-16: باسورد+2FA مؤقتين جداد لموظف عادي نسي/غلط بيانات
    دخوله — بديل ويب لـ`admin_bootstrap recover` الـCLI (اللي فضل
    الطريقة الوحيدة قبل كده، محتاج SSH فعلي على السيرفر). أوسع من
    user_force_2fa_reset (بتلمس الباسورد كمان مش الـ2FA بس)، فمحتاجة
    نفس مستوى reason+step-up، وservices.reset_staff_credentials بترفض
    super_admin/owner صراحةً بغض النظر عن نتيجة الـstep-up."""
    return build_step_up_scope("staff_credentials_reset", {
        "user_id": user_id,
        "reason_sha256": sha256_text(reason),
    })


def permission_override_upsert_scope(
    *,
    user_id: int,
    resource: str,
    action: str,
    allowed: bool,
    branch_id: Optional[int],
    reason: str,
) -> str:
    return build_step_up_scope("permission_override_upsert", {
        "user_id": user_id,
        "resource": resource,
        "action": action,
        "allowed": allowed,
        "branch_id": branch_id,
        "reason_sha256": sha256_text(reason),
    })


def permission_override_revoke_scope(*, permission_id: int, reason: str) -> str:
    return build_step_up_scope("permission_override_revoke", {
        "permission_id": permission_id,
        "reason_sha256": sha256_text(reason),
    })


def setting_upsert_scope(
    *, key: str, branch_id: Optional[int], value: str, reason: str,
) -> str:
    return build_step_up_scope("setting_upsert", {
        "key": key,
        "branch_id": branch_id,
        "value_sha256": sha256_text(value),
        "reason_sha256": sha256_text(reason),
    })


def admin_session_revoke_scope(*, target_user_id: int, session_ref: str) -> str:
    """2026-08-03: نسخة إدارية من session_revoke — super_admin بينهي جلسة
    مستخدم تاني (مش جلسته هو)، بدل التعطيل الكامل للحساب زي ما كان
    الوحيد المتاح قبل كده. مربوط بالمستخدم الهدف + مرجع الجلسة معًا،
    عشان proof اتاخد لإنهاء جلسة مستخدم A مايشتغلش لمستخدم B."""
    return build_step_up_scope("admin_session_revoke", {
        "target_user_id": target_user_id, "session_ref": session_ref,
    })


def session_revoke_scope(*, session_ref: str) -> str:
    """Gate 2B3B — bind a step-up proof to revoking exactly one session
    (family) by its public reference, so a proof minted to revoke session A
    can never be replayed to revoke session B."""
    return build_step_up_scope("session_revoke", {"session_ref": session_ref})


def other_sessions_revoke_scope(*, keep_session_ref: str) -> str:
    """Gate 2B3B — bind a step-up proof to the "revoke every session except
    this one" operation. ``keep_session_ref`` is the caller's *current*
    session (proven server-side from the refresh cookie), so a proof cannot
    be reused after the current session itself has changed."""
    return build_step_up_scope("other_sessions_revoke", {"keep_session_ref": keep_session_ref})


def payment_void_scope(*, payment_id: int, reason: str) -> str:
    """Gate 4 (جولة مراجعة Codex الأولى — M5a): يعكس دفعة اتسجّلت بالفعل في
    الدفاتر (finance.void_payment) — أعلى خطورة من إلغاء صنف قبل الدفع (ده
    لسه محمي بـPIN موافقة مدير بس، مقصود — راجع الـbrief §2.4: step-up
    للأفعال الأعلى خطورة، لا لكل ضغطة POS). مربوط بنفس الدفعة والسبب
    بالظبط — proof اتاخد لعكس دفعة #5 مايشتغلش لدفعة #6."""
    return build_step_up_scope("payment_void", {
        "payment_id": payment_id,
        "reason_sha256": sha256_text(reason),
    })


def dining_refund_scope(*, order_id: int, item_id: int, reason: str) -> str:
    """Gate 4 (جولة مراجعة Codex الأولى — M5a): مرتجع بعد الدفع
    (dining.refund_order_item) — عكس مالي حقيقي لصنف اتحصّل فعليًا، مش نفس
    إلغاء صنف قبل الدفع. مربوط بالطلب/الصنف/السبب بالظبط."""
    return build_step_up_scope("dining_refund", {
        "order_id": order_id,
        "item_id": item_id,
        "reason_sha256": sha256_text(reason),
    })


def expense_void_scope(*, expense_id: int, reason: str) -> str:
    """2026-08-19 (طلب Mohamed — إلغاء سند مصروفات) — نفس فئة خطورة
    payment_void_scope فوق بالظبط: بيعكس قيد رحّل فعليًا في الدفاتر
    (Dr.5xxx/Cr.تسوية) بعد إتمامه، مش قبل الحفظ. مربوط بنفس السند والسبب."""
    return build_step_up_scope("expense_void", {
        "expense_id": expense_id,
        "reason_sha256": sha256_text(reason),
    })


def custody_void_scope(*, custody_id: int, reason: str) -> str:
    """2026-08-19 (طلب Mohamed — إلغاء عهدة نقدية لسه open) — نفس فئة
    خطورة expense_void_scope فوق بالظبط: بيعكس Dr.مصدر/Cr.1190 اتسجّل
    فعليًا. مربوط بنفس العهدة والسبب."""
    return build_step_up_scope("custody_void", {
        "custody_id": custody_id,
        "reason_sha256": sha256_text(reason),
    })


def cash_receipt_void_scope(*, receipt_id: int, reason: str) -> str:
    """2026-08-19 (طلب Mohamed — إلغاء إذن قبض عام) — نفس فئة خطورة
    expense_void_scope فوق بالظبط. مربوط بنفس الإذن والسبب."""
    return build_step_up_scope("cash_receipt_void", {
        "receipt_id": receipt_id,
        "reason_sha256": sha256_text(reason),
    })


def supplier_payment_void_scope(*, payment_id: int, reason: str) -> str:
    """2026-08-19 (طلب Mohamed — إلغاء سند دفع مورد) — نفس فئة خطورة
    payment_void_scope فوق بالظبط: بيعكس Dr.2200/Cr.تسوية اتسجّل فعليًا،
    وبيقلّل amount_paid على أمر الشراء. مربوط بنفس السند والسبب."""
    return build_step_up_scope("supplier_payment_void", {
        "payment_id": payment_id,
        "reason_sha256": sha256_text(reason),
    })


def access_token_hash_from_request(request) -> str:
    """Hash of the current request's bearer token — binds a step-up grant
    (at issuance) or its consumption to the exact browser session that
    holds it, using the same SHA-256-of-token scheme as refresh tokens and
    the access-token blacklist. Returns the hash of an empty string if no
    bearer token is present (never matches a real grant, fails closed)."""
    from app.core.kernel.auth.service import AuthService  # noqa: PLC0415

    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ") if auth_header.startswith("Bearer ") else ""
    return AuthService._hash_token(token)
