"""
app/modules/finance/_services/checks.py
Extracted from app/modules/finance/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session
from app.modules.finance import crud
from app.modules.finance.models import Check
from app.modules.finance.schemas import (
    CheckCreate,
)


# ── Checks ────────────────────────────────────────────────────────────
# ⚠️ باج معماري حقيقي كان هنا: الـ router كان بينادي crud.create_check/
# move_check_status مباشرة (بما فيه db.commit() جوه crud نفسها) من غير أي
# services.py function خالص — كسر Architecture rule (§4/§7: router لا يكلّم
# crud مباشرة، والـ commit بتاع الـ business transaction مسؤولية services
# مش crud). اتصلح بنفس نمط void_payment فوق بالظبط: crud بقت DB عمليات خالص
# (flush بس، من غير commit)، والـ commit/refresh + "الشيك غير موجود"
# (ValueError → 404 في الـ router) بقوا هنا.

def create_check(db: Session, data: CheckCreate, created_by: int) -> Check:
    """يسجّل شيك بنكي جديد (وارد من عميل/مورد)."""
    payload = data.model_dump()
    payload["created_by"] = created_by
    check = crud.create_check(db, payload)
    db.commit()
    db.refresh(check)
    return check


class CheckStatusTransitionError(Exception):
    """انتقال حالة شيك غير منطقي (مثلاً تصفية شيك مرتجع مباشرة، أو التراجع عن
    شيك مُحصَّل). لا ترث من ValueError عمدًا عشان الـ router يقدر يميّزها عن
    "الشيك غير موجود" ويرجّع 400 (طلب خاطئ) مش 404."""


# خريطة الانتقالات المسموحة فعليًا لدورة حياة شيك بنكي حقيقي — كانت مفقودة
# بالكامل قبل كده (باج حقيقي اتكشف أثناء اختبار قبول حقيقي): move_check_status
# كانت بتقبل أي to_status من الأربعة المسموحين في الـ schema بغض النظر عن
# الحالة الحالية، يعني مدير (حتى بحسن نية تحت ضغط) كان يقدر يرجّع شيك
# "cleared" لـ "received"، أو يصفّي (cleared) شيك "bounced" مباشرة من غير ما
# يعدي بمرحلة إعادة إيداع حقيقية — كله كان بينفّذ من غير أي رفض.
CHECK_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "received":  {"deposited", "bounced"},
    "deposited": {"cleared", "bounced"},
    "cleared":   set(),  # حالة نهائية — شيك اتحصّل فعليًا، ملوش رجوع
    "bounced":   set(),  # حالة نهائية — شيك ارتد؛ أي متابعة (إعادة إيداع) شيك/سجل جديد
}


def move_check_status(
    db: Session, check_id: int, to_status: str, moved_by: int, notes: Optional[str] = None,
) -> Check:
    """ينقل حالة شيك (received → deposited → cleared/bounced) ويسجّل الحركة
    في CheckMovement. يرفض أي انتقال مش موجود في CHECK_STATUS_TRANSITIONS —
    راجع الملاحظة فوق."""
    check_obj = crud.get_check(db, check_id)
    if not check_obj:
        raise ValueError(f"الشيك {check_id} غير موجود")

    allowed = CHECK_STATUS_TRANSITIONS.get(check_obj.status, set())
    if to_status not in allowed:
        if check_obj.status == to_status:
            reason = "الشيك بالفعل في هذه الحالة"
        elif not allowed:
            reason = f"'{check_obj.status}' حالة نهائية — لا يمكن تغييرها"
        else:
            reason = f"المسموح فقط: {', '.join(sorted(allowed))}"
        raise CheckStatusTransitionError(
            f"لا يمكن نقل الشيك من '{check_obj.status}' إلى '{to_status}' — {reason}"
        )

    updated = crud.move_check_status(db, check_obj, to_status, moved_by, notes)
    db.commit()
    db.refresh(updated)
    return updated


# ── Cashier Shift / Safe (POS Day) ──────────────────────────────────────
