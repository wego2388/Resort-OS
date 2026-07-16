"""
app/modules/core/policy_engine.py
═══════════════════════════════════════════════════════════════════════
Policy Engine — سجل مركزي واحد لكل "إجراء حسّاس محتاج موافقة PIN مدير"،
زي permission_catalog.py بالظبط بس لسياسات العمل (business policy) مش
صلاحيات الـ endpoint (RBAC). قبل الملف ده، كل موديول (finance، dining)
كان بيكرر نفس الـ pattern بشكل منفصل: يستورد core.services/core.crud،
يقفل الرقم 60 (min_approver_level) inline، ويكتب AuditLog يدويًا بشكله
الخاص — 4 نسخ شبه متطابقة من نفس المنطق.

مبني *فوق* core.services.resolve_pin_approval، مش بديل له — resolve_pin_
approval يفضل المسؤول الوحيد عن التحقق من هوية المعتمِد نفسها (PIN صح،
مستوى كافي، الحساب نشط، lockout). الطبقة دي مسؤولة بس عن حاجتين:
  1. "الإجراء ده محتاج موافقة مين؟" — سجل واحد قابل للمراجعة/التعديل.
  2. كتابة AuditLog بشكل موحّد بدل ما كل call site يبنيه من الصفر.

⚠️ حدود الخصومات (CustomerGroup.discount_percentage، ConditionalDiscount)
عمدًا *مش* هنا — قرار Mohamed (2026-07-16): تفضل قابلة للتعديل من
الداتابيز من غير نشر كود جديد. راجع resort_os/discount_engine.py.

ليه مش جوه app/resort_os/؟ الملفات هناك (discount_engine، beach_engine...)
"pure domain engines" بدون DB/FastAPI عمدًا (راجع header discount_engine.py).
الملف ده بيلمس DB فعليًا (بيكتب AuditLog) — مكانه الطبيعي جوه core/ زي
resolve_pin_approval بالظبط، مش resort_os/.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class SensitiveAction:
    """سياسة إجراء واحد حسّاس — مين أقل مستوى يقدر يوافق عليه."""
    key: str
    label_ar: str
    min_approver_level: int = 60


# ── الكتالوج ────────────────────────────────────────────────────────────────
# المصدر الوحيد لـ "الإجراء ده محتاج موافقة مدير من مستوى قد ايه". غيّر
# min_approver_level هنا لو Mohamed عايز يرفع/يخفّض حد إجراء معيّن — مفيش
# أي رقم 60 (أو غيره) مكرر في أي service.py تاني بعد النقل.
SENSITIVE_ACTIONS: dict[str, SensitiveAction] = {
    a.key: a for a in [
        SensitiveAction("void_order_item", "إلغاء صنف من طلب دايننج"),
        SensitiveAction("apply_order_discount", "تطبيق خصم على طلب دايننج"),
        SensitiveAction("cash_movement", "حركة كاش يدوية (إيداع/سحب/تصحيح/فتح درج)"),
        SensitiveAction("view_other_cashier_shift_invoices", "عرض فواتير وردية كاشير تاني"),
    ]
}


def require_approval(
    db: Session,
    action_key: str,
    *,
    acting_user_level: int,
    approver_user_id: Optional[int],
    approver_pin: Optional[str],
) -> Optional[int]:
    """يتحقق من موافقة PIN لإجراء حسّاس معروف في SENSITIVE_ACTIONS، بقراءة
    min_approver_level من الكتالوج بدل ما الـ caller يقفله inline. بيرجّع
    ``approved_by`` زي resolve_pin_approval بالظبط (None لو المنفّذ نفسه
    كان مؤهّل أصلاً)."""
    policy = SENSITIVE_ACTIONS.get(action_key)
    if not policy:
        raise ValueError(f"إجراء غير معروف في Policy Engine: {action_key}")

    from app.modules.core import services as core_services  # noqa: PLC0415 — تجنّب circular import

    return core_services.resolve_pin_approval(
        db, acting_user_level, approver_user_id, approver_pin,
        min_approver_level=policy.min_approver_level,
    )


def record_policy_audit(
    db: Session,
    action_key: str,
    *,
    user_id: Optional[int],
    approved_by: Optional[int],
    branch_id: int,
    entity_type: str,
    entity_id: int,
    data: Optional[dict] = None,
) -> None:
    """يكتب AuditLog بشكل موحّد بعد require_approval. منفصل عن require_
    approval عمدًا (مش دالة واحدة مدمجة) — بعض الـ call sites (apply_order_
    discount) بتحسب الـ audit payload من نتيجة منطق عمل بعد الموافقة
    بخطوات، مش فورًا. الـ action المسجّل في AuditLog هو ``action_key``
    اللي اتبعت (ممكن يكون مختلف عن مفتاح الكتالوج، زي
    ``cash_movement_{movement_type}``)."""
    from app.modules.core import crud as core_crud  # noqa: PLC0415
    from app.modules.core.schemas import AuditLogCreate  # noqa: PLC0415

    core_crud.create_audit_log(db, AuditLogCreate(
        user_id=user_id, approved_by=approved_by, branch_id=branch_id,
        action=action_key, entity_type=entity_type, entity_id=entity_id,
        new_data=json.dumps(data) if data is not None else None,
    ))
