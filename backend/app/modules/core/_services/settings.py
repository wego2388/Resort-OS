"""
app/modules/core/_services/settings.py
Extracted from app/modules/core/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.modules.core import crud
from app.modules.core.schemas import (
    AuditLogCreate,
    SettingRead,
)
from app.modules.core._services._exceptions import (
    ActorAuthorizationChangedError,
)
from app.modules.core._services._audit_helpers import (
    _step_up_audit_context,
)
from app.modules.core._services.authorization import (
    assert_branch_access,
)


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

    # Typed operational settings must be validated before they can become a
    # misleading saved value.  The Settings table is intentionally generic,
    # so domain-specific parsing stays in the pure domain engine.
    if key == "beach.capacity_max":
        from app.resort_os.beach_engine import parse_beach_capacity_max  # noqa: PLC0415

        value = str(parse_beach_capacity_max(value))

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


def _effective_percentage_setting(
    db: Session, key: str, branch_id: Optional[int], env_default: float,
) -> Decimal:
    """Helper مشترك لـget_effective_vat_percentage/get_effective_service_charge_percentage
    (2026-08-03) — ⚠️ باج مالي صامت حقيقي كان هنا: شاشة الإعدادات (`PUT
    /settings/vat_percentage` وغيرها) كانت بتكتب صف Setting حقيقي في
    قاعدة البيانات، لكن dining/beach/eta_service كانوا بيقروا
    settings.VAT_PERCENTAGE/SERVICE_CHARGE_PERCENTAGE من الـ env مباشرة —
    يعني تعديل مدير للنسبة من الواجهة مالوش أي أثر فعلي على أي معاملة
    حقيقية، بصمت تمامًا (لا خطأ، لا تحذير). القيمة الآن مقروءة من
    get_setting_value() (نفس fallback الموجود أصلاً: صف الفرع → الصف
    العام branch_id=None → env القديم)، مع تحقق سلامة (رقم صالح، ضمن
    [0, 100]) يرفض أي قيمة تالفة أو خطأ إدخال بدل ما يكسر حساب فاتورة حي.
    """
    raw = get_setting_value(db, key, branch_id, default=str(env_default))
    try:
        value = Decimal(raw if raw is not None else str(env_default))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(str(env_default))
    if value < 0 or value > 100:
        return Decimal(str(env_default))
    return value


def get_effective_vat_percentage(db: Session, branch_id: Optional[int]) -> Decimal:
    """نسبة الضريبة الفعلية — راجع _effective_percentage_setting."""
    return _effective_percentage_setting(db, "vat_percentage", branch_id, settings.VAT_PERCENTAGE)


def get_effective_service_charge_percentage(db: Session, branch_id: Optional[int]) -> Decimal:
    """نسبة رسم الخدمة العامة الفعلية (fallback بعد override المنفذ/القناة
    — راجع dining.services._service_charge_pct) — راجع
    _effective_percentage_setting."""
    return _effective_percentage_setting(
        db, "service_charge_percentage", branch_id, settings.SERVICE_CHARGE_PERCENTAGE,
    )
