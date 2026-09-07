"""app/modules/timeshare/_services/maintenance.py — annual maintenance
dues: row locking, collection, effective-dated fee rules."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.modules.timeshare import crud
from app.modules.timeshare.models import TimeshareContract, TimeshareMaintenanceDue, TimeshareMaintenanceFeeRule
from app.modules.timeshare.schemas import PayMaintenanceDueRequest

from ._exceptions import PaymentConflictError
from .installments import _PAYMENT_METHOD_DEBIT_ACCOUNT, _has_any_overdue_balance


def _lock_maintenance_due_or_raise(db: Session, due_id: int) -> TimeshareMaintenanceDue:
    """مرآة installments._lock_installment_or_raise — pay_maintenance_due نفس فئة الباج بالظبط."""
    try:
        locked = crud.lock_maintenance_due_for_update(db, due_id)
    except OperationalError as exc:
        db.rollback()
        raise PaymentConflictError(
            "مستحق الصيانة مقفول الآن بعملية تحصيل أخرى — حاول تاني خلال لحظات"
        ) from exc
    if not locked:
        raise ValueError(f"مستحق الصيانة {due_id} غير موجود")
    return locked


def pay_maintenance_due(
    db: Session,
    due_id: int,
    req: PayMaintenanceDueRequest,
    *,
    collected_by: int,
    enforce_cash_shift: bool = True,
) -> TimeshareMaintenanceDue:
    """تحصيل مستحق صيانة سنوي — مرآة كاملة لـ installments.pay_installment (نفس
    تسلسل التحقق بالضبط: موجود؟ مدفوع بالفعل؟ العقد ملغي/منتهي؟ المبلغ زيادة عن
    المتبقي؟) بس على TimeshareMaintenanceDue بدل TimeshareInstallment.

    ⚠️ مراجعة Codex 2026-08-30 (H-05): نفس إصلاح ترتيب الأقفال بتاع
    pay_installment بالظبط — العقد بيتقفل الأول دايمًا (راجع تعليقها)."""
    due_lookup = crud.get_maintenance_due(db, due_id)
    if not due_lookup:
        raise ValueError(f"مستحق الصيانة {due_id} غير موجود")
    contract = crud.lock_contract_for_update(db, due_lookup.contract_id)
    if not contract:
        raise ValueError(f"العقد المرتبط بمستحق الصيانة {due_id} غير موجود")
    due = _lock_maintenance_due_or_raise(db, due_id)
    try:
        if due.status == "paid":
            raise ValueError("مستحق الصيانة مدفوع بالكامل مسبقاً")

        if contract.status == "cancelled":
            raise ValueError(f"العقد {contract.contract_number} ملغي — لا يمكن تحصيل صيانة عليه")
        if contract.status == "expired":
            raise ValueError(f"العقد {contract.contract_number} منتهي — لا يمكن تحصيل صيانة عليه")

        remaining = due.amount - due.paid_amount
        if req.paid_amount > remaining:
            raise ValueError(
                f"المبلغ المُدخَل ({req.paid_amount:,.2f} ج) أكبر من المتبقي على "
                f"مستحق صيانة سنة {due.fee_year} ({remaining:,.2f} ج) — تحقّق من المبلغ قبل التسجيل"
            )

        from app.modules.finance.services import record_external_payment  # noqa: PLC0415
        collection = record_external_payment(
            db,
            branch_id=contract.branch_id,
            amount=req.paid_amount,
            payment_method=req.payment_method,
            collector_id=collected_by,
            reference=f"TS-MAINT-{contract.contract_number}-{due.fee_year}",
            source="timeshare_maintenance",
            source_id=due.id,
            require_cash_shift=enforce_cash_shift,
        )
        obj = crud.pay_maintenance_due(db, due, req)
        # strict=True (2026-08-11) — راجع installments.pay_installment لنفس السبب.
        _post_maintenance_payment_journal(
            db,
            contract,
            req.paid_amount,
            due,
            req.payment_method,
            collection_payment_id=collection.id,
            collected_by=collected_by,
        )
        _audit_maintenance_payment(db, contract, due, req, collected_by)

        if contract.booking_frozen and not _has_any_overdue_balance(contract):
            contract.booking_frozen = False

        db.commit()
        db.refresh(obj)
        return obj
    except Exception:
        db.rollback()
        raise


def _post_maintenance_payment_journal(
    db: "Session",
    contract: "TimeshareContract",
    paid_amount,
    due: "TimeshareMaintenanceDue",
    payment_method: str,
    *,
    collection_payment_id: int,
    collected_by: int,
) -> None:
    """Dr. Cash/Bank/Card (حسب طريقة الدفع الفعلية) / Cr. إيرادات صيانة
    عقود الملكية الجزئية (4650) — حساب منفصل عمدًا عن 4600 (إيراد سعر الشراء):
    إيراد الصيانة رسم خدمة سنوي مرتبط بسنة محدَّدة (fee_year)، مختلف في
    طبيعته المحاسبية عن إيراد بيع العقد لمرة واحدة."""
    from app.core.config import settings  # noqa: PLC0415
    from app.modules.finance.services import post_simple_revenue_journal  # noqa: PLC0415
    from app.resort_os.timezone_utils import business_today  # noqa: PLC0415

    debit_code = _PAYMENT_METHOD_DEBIT_ACCOUNT.get(payment_method or "cash", "1100")
    post_simple_revenue_journal(
        db, contract.branch_id, business_today(settings.TIMEZONE),
        debit_account_code=debit_code, credit_account_code="4650",
        amount=paid_amount,
        reference=f"TS-MAINT-{contract.contract_number}-{due.fee_year}",
        description=f"تحصيل صيانة سنة {due.fee_year} — {contract.contract_number}",
        source="timeshare", source_id=collection_payment_id,
        created_by=collected_by,
        cost_center_code="TS",
        strict=True, commit_cost_centers=False,
    )


def _audit_maintenance_payment(
    db: "Session",
    contract: "TimeshareContract",
    due: "TimeshareMaintenanceDue",
    req: "PayMaintenanceDueRequest",
    collected_by: int,
) -> None:
    """يسجّل AuditLog لكل تحصيل صيانة — مرآة installments._audit_installment_payment."""
    import json as _json  # noqa: PLC0415
    from app.modules.core.crud import create_audit_log  # noqa: PLC0415
    from app.modules.core.schemas import AuditLogCreate  # noqa: PLC0415

    old_data = _json.dumps({
        "status": "pending" if due.status == "partial" else due.status,
        "paid_amount": float(due.paid_amount - req.paid_amount),
    }, ensure_ascii=False)
    new_data = _json.dumps({
        "status": due.status,
        "paid_amount": float(due.paid_amount),
        "payment_method": req.payment_method,
        "receipt_number": req.receipt_number,
        "amount_paid_now": float(req.paid_amount),
    }, ensure_ascii=False)

    create_audit_log(db, AuditLogCreate(
        user_id=collected_by,
        branch_id=contract.branch_id,
        action="pay_maintenance_due",
        entity_type="timeshare_maintenance_due",
        entity_id=due.id,
        old_data=old_data,
        new_data=new_data,
    ))


def list_maintenance_dues_for_branch(
    db: Session, branch_id: int,
    status: Optional[str] = None, contract_id: Optional[int] = None,
    fee_year: Optional[int] = None, search: Optional[str] = None, limit: int = 200,
) -> dict:
    """مرآة installments.list_installments — قايمة مستحقات صيانة عبر الفرع كله
    (لشاشة تاب "الصيانة" الإدارية)، بعكس crud.list_maintenance_dues اللي بتاعة
    عقد واحد بس (مستخدمة في بروفايل العميل)."""
    items = crud.list_all_maintenance_dues(db, branch_id, status, contract_id, fee_year, search, limit)
    return {
        "maintenance_dues": items,
        "total": len(items),
        "summary": crud.maintenance_dues_summary(db, branch_id),
    }


def generate_annual_maintenance_dues(db: Session, branch_id: int, fee_year: int) -> int:
    """نقطة الدخول الوحيدة اللي الـ router بيكلّمها — بتفوّض للمنطق الفعلي
    في app.tasks.timeshare_tasks (نفس مكان _mark_overdue بالظبط، الاتفاقية
    القائمة في الموديول ده) عشان يبقى فيه تنفيذ واحد بس يستخدمه الـ Celery
    task والـ endpoint اليدوي، زي run_night_audit في pms."""
    from app.tasks.timeshare_tasks import _generate_annual_maintenance_dues  # noqa: PLC0415

    created = _generate_annual_maintenance_dues(db, branch_id, fee_year)
    db.commit()
    return created


# ── قواعد صيانة effective-dated/versioned (OPS-DATA-02 §8 نقطة 3) ────────

# تعميم 2026 الرسمي — نسخة أولى تُزرع فعليًا عبر seed_2026_maintenance_fee_rules
# بدل ما تكون dict ثابت مقروء مباشرة من الكود؛ لسه مصدر الأرقام نفسها هنا
# عمدًا (بدل زرعها يدويًا في كل بيئة) — الفرق عن التصميم القديم إن التغيير
# السنوي القادم بيبقى صف جديد في الجدول، مش تعديل الملف ده.
MAINTENANCE_FEES_2026_VERSION = "EG-TIMESHARE-MAINT-2026.v1"
_MAINTENANCE_FEES_2026 = {
    "before_may_2026": (date(2000, 1, 1), {2: Decimal("1750"), 4: Decimal("2000"), 6: Decimal("2500")}),
    "from_may_2026":   (date(2026, 5, 1), {2: Decimal("2000"), 4: Decimal("3000"), 6: Decimal("4000")}),
}


def seed_2026_maintenance_fee_rules(db: Session, branch_id: int, created_by: Optional[int] = None) -> list[TimeshareMaintenanceFeeRule]:
    """idempotent — نفس نمط core.seed.py. تُنشئ 6 صفوف (2 tier × 3 سعات)
    لو مش موجودة بالفعل لنفس (branch_id, fee_year=2026)."""
    from app.modules.timeshare.schemas import TimeshareMaintenanceFeeRuleCreate  # noqa: PLC0415

    existing = {
        (r.contract_tier_from, r.capacity)
        for r in crud.list_maintenance_fee_rules(db, branch_id, fee_year=2026, active_only=False)
    }
    created = []
    for tier_from, capacities in _MAINTENANCE_FEES_2026.values():
        for capacity, fee in capacities.items():
            if (tier_from, capacity) in existing:
                continue
            rule = crud.create_maintenance_fee_rule(db, TimeshareMaintenanceFeeRuleCreate(
                branch_id=branch_id, version=MAINTENANCE_FEES_2026_VERSION, fee_year=2026,
                contract_tier_from=tier_from, capacity=capacity, fee=fee,
            ), created_by=created_by)
            created.append(rule)
    db.commit()
    return created


def get_recommended_maintenance_fee(
    db: Session, branch_id: int, fee_year: int, contract_date: "date", capacity: int,
) -> tuple[Optional[Decimal], Optional[str]]:
    """(المبلغ المقترح، نسخة القاعدة) — للعرض/التحقق فقط، زي ما التعميم
    الأصلي بيقول. None لو مفيش قاعدة سارية للسنة/السعة/تاريخ التعاقد دول."""
    rule = crud.find_maintenance_fee_rule(db, branch_id, fee_year, contract_date, capacity)
    return (rule.fee, rule.version) if rule else (None, None)
