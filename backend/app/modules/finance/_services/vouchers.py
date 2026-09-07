"""
app/modules/finance/_services/vouchers.py
Extracted from app/modules/finance/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.modules.finance import crud
from app.modules.finance.models import CashReceipt, Custody, Expense
from app.modules.finance.schemas import (
    CashReceiptCreate,
    CustodyCreate,
    CustodySettleRequest,
    ExpenseCreate,
    ExpensePaymentCreate,
    ExpenseRead,
    JournalEntryCreate,
    JournalLineCreate,
)
from app.modules.finance._services._exceptions import (
    FinancialConfigurationError,
)
from app.modules.finance._services.posting import (
    validate_period_open,
    post_simple_revenue_journal,
)


def record_expense(
    db: Session, branch_id: int, data: ExpenseCreate, recorded_by: int,
    acting_user_level: int = 100,
) -> Expense:
    """سند مصروفات حقيقي (2026-08-16، طلب Mohamed صراحةً) — بديل القيد
    اليدوي العام (بلا فئة/تتبّع) اللي كان الخيار الوحيد قبل كده. الفئة هي
    اختيار expense_account_id نفسه (حساب 5xxx). يرحّل Dr. حساب المصروف /
    Cr. حساب التسوية (كاش/بنك)، بنفس مسار post_simple_revenue_journal
    الموحّد (strict=True — فشل تجهيز الحساب لازم يظهر بوضوح للمحاسب، مش
    يتبلع بصمت زي مسارات البيع التلقائية).

    حد الموافقة (2026-08-19، طلب Mohamed): مبلغ >= EXPENSE_APPROVAL_
    THRESHOLD محتاج موافقة PIN مدير حاضر فعليًا (core.policy_engine،
    نفس نمط إلغاء صنف/تطبيق خصم دايننج بالظبط) — تحت الحد، أي محاسب+
    يسجّله لوحده زي ما كان بالظبط. acting_user_level افتراضيًا 100
    (زي apply_order_discount) عشان استدعاءات الاختبار المباشرة القديمة
    تفضل شغالة من غير تعديل — الـ router الحقيقي دايمًا بيمرر المستوى
    الفعلي (راجع user_level(user))."""
    approved_by = None
    if data.amount >= settings.EXPENSE_APPROVAL_THRESHOLD:
        from app.modules.core import policy_engine  # noqa: PLC0415
        approved_by = policy_engine.require_approval(
            db, "record_expense",
            acting_user_level=acting_user_level,
            approver_user_id=data.approver_user_id, approver_pin=data.approver_pin,
            target_branch_id=branch_id,
        )

    validate_period_open(db, branch_id, data.expense_date)

    expense_account = crud.get_account(db, data.expense_account_id)
    if not expense_account or expense_account.branch_id != branch_id:
        raise ValueError(f"حساب المصروف {data.expense_account_id} غير موجود في هذا الفرع")
    if expense_account.account_type != "expense":
        raise ValueError(f"الحساب «{expense_account.name}» ليس حساب مصروفات")
    if not expense_account.is_active:
        raise ValueError(f"الحساب «{expense_account.name}» معطّل")

    if data.defer_payment:
        # مصروف آجل (2026-08-19، طلب Mohamed) — الحساب الفعلي دايمًا 2180
        # (مصروفات مستحقة)، settlement_account_id من العميل بيتجاهل عمدًا.
        settlement_account = crud.get_account_by_code(db, branch_id, "2180")
        if not settlement_account:
            raise FinancialConfigurationError(
                "حساب المصروفات المستحقة (2180) غير معرَّف لهذا الفرع"
            )
        if settlement_account.account_type != "liability":
            raise FinancialConfigurationError("حساب 2180 لازم يكون حساب التزامات")
    else:
        if not data.settlement_account_id:
            raise ValueError("حساب التسوية مطلوب لسند مصروفات غير آجل")
        settlement_account = crud.get_account(db, data.settlement_account_id)
        if not settlement_account or settlement_account.branch_id != branch_id:
            raise ValueError(f"حساب التسوية {data.settlement_account_id} غير موجود في هذا الفرع")
        if settlement_account.account_type != "asset":
            raise ValueError(f"حساب التسوية «{settlement_account.name}» لازم يكون حساب أصول")
        if not settlement_account.is_active:
            raise ValueError(f"حساب التسوية «{settlement_account.name}» معطّل")

    cost_center_code = None
    if data.cost_center_id:
        cc = crud.get_cost_center(db, data.cost_center_id)
        if not cc or cc.branch_id != branch_id:
            raise ValueError(f"مركز التكلفة {data.cost_center_id} غير موجود في هذا الفرع")
        cost_center_code = cc.code

    entry = post_simple_revenue_journal(
        db, branch_id, data.expense_date,
        debit_account_code=expense_account.code,
        credit_account_code=settlement_account.code,
        amount=data.amount,
        reference=data.reference or f"EXP-{data.expense_date.isoformat()}",
        description=data.description,
        source="manual_expense",
        source_id=None,
        created_by=recorded_by,
        cost_center_code=cost_center_code,
        commit_cost_centers=False,
        strict=True,
    )
    expense = crud.create_expense(
        db, branch_id, data, journal_entry_id=entry.id, recorded_by=recorded_by,
        settlement_account_id=settlement_account.id,
        payment_status="unpaid" if data.defer_payment else "paid",
    )
    if approved_by is not None:
        from app.modules.core import policy_engine  # noqa: PLC0415
        policy_engine.record_policy_audit(
            db, "record_expense", user_id=recorded_by, approved_by=approved_by,
            branch_id=branch_id, entity_type="expense", entity_id=expense.id,
            data={"amount": str(data.amount), "expense_account_id": data.expense_account_id},
        )
    db.commit()
    db.refresh(expense)
    return expense


def void_expense(db: Session, expense_id: int, voided_by: int, reason: str = "voided via API") -> Expense:
    """إلغاء سند مصروفات اتسجّل بالفعل (2026-08-19، طلب Mohamed) — نفس نمط
    void_payment فوق بالظبط (عكس Dr/Cr، سجل تدقيق، commit ذري). مقصور
    عمدًا على سند من غير أي سداد مسجّل عليه بعد (amount_paid == 0) — سند
    آجل (راجع pay_expense لاحقًا) بعد ما يتسدد جزئيًا/كليًا يحتاج مراجعة
    يدوية أوسع (حالة نادرة مؤجَّلة، مش جزء من هذه الدفعة)."""
    expense = crud.get_expense(db, expense_id)
    if not expense:
        raise ValueError(f"سند المصروفات {expense_id} غير موجود")
    if expense.voided_at is not None:
        raise ValueError(f"سند المصروفات {expense_id} ملغى بالفعل")
    if expense.amount_paid and expense.amount_paid > 0:
        raise ValueError(
            f"سند المصروفات {expense_id} عليه سداد مسجّل بالفعل — لا يمكن إلغاؤه مباشرة"
        )
    expense_account = crud.get_account(db, expense.expense_account_id)
    settlement_account = crud.get_account(db, expense.settlement_account_id)
    if not expense_account or not settlement_account:
        raise ValueError(f"حسابات سند المصروفات {expense_id} غير مكتملة")
    try:
        original_amount = expense.amount
        expense = crud.void_expense(db, expense, voided_by)
        crud.create_revenue_audit_log(
            db, branch_id=expense.branch_id, entity_type="expense", entity_id=expense.id,
            old_value=original_amount, new_value=Decimal("0.00"), reason=reason, changed_by=voided_by,
        )
        # عكس القيد اللي record_expense رحّله (Dr.مصروف/Cr.تسوية) — التسوية
        # ترجع لحسابها والمصروف يتصفّر. strict=True زي void_payment بالظبط.
        from app.resort_os.timezone_utils import business_today  # noqa: PLC0415
        post_simple_revenue_journal(
            db, expense.branch_id, business_today(settings.TIMEZONE),
            debit_account_code=settlement_account.code, credit_account_code=expense_account.code,
            amount=original_amount,
            reference=f"EXP-VOID-{expense.id}",
            description=f"إلغاء سند مصروفات #{expense.id}",
            source="expense_void", source_id=expense.id,
            created_by=voided_by,
            strict=True, commit_cost_centers=False,
        )
        db.commit()
        db.refresh(expense)
        return expense
    except Exception:
        db.rollback()
        raise


def pay_expense(
    db: Session, expense_id: int, data: ExpensePaymentCreate, recorded_by: int,
) -> Expense:
    """سداد فعلي لسند مصروفات آجل (2026-08-19، طلب Mohamed) — يقفل حلقة
    2180 (مصروفات مستحقة) اللي record_expense فتحها لما defer_payment=True.
    نفس نمط inventory.services.pay_purchase_order بالظبط (Dr.الحساب
    الآجل/Cr.حساب التسوية لكل دفعة، تحديث amount_paid/payment_status)."""
    expense = crud.get_expense(db, expense_id)
    if not expense:
        raise ValueError(f"سند المصروفات {expense_id} غير موجود")
    if expense.voided_at is not None:
        raise ValueError(f"سند المصروفات {expense_id} ملغى — لا يمكن تسجيل سداد عليه")
    if expense.payment_status == "paid":
        raise ValueError(f"سند المصروفات {expense_id} مسدد بالكامل بالفعل")

    remaining = expense.amount - expense.amount_paid
    if data.amount > remaining + Decimal("0.01"):
        raise ValueError(f"المبلغ ({data.amount}) أكبر من المتبقي على السند ({remaining})")

    settlement_account = crud.get_account(db, data.settlement_account_id)
    if not settlement_account or settlement_account.branch_id != expense.branch_id:
        raise ValueError(f"حساب التسوية {data.settlement_account_id} غير موجود في هذا الفرع")
    if settlement_account.account_type != "asset":
        raise ValueError(f"حساب التسوية «{settlement_account.name}» لازم يكون حساب أصول")
    if not settlement_account.is_active:
        raise ValueError(f"حساب التسوية «{settlement_account.name}» معطّل")

    validate_period_open(db, expense.branch_id, data.paid_at)

    accrued_account = crud.get_account(db, expense.settlement_account_id)
    if not accrued_account:
        raise ValueError(f"حساب المصروفات المستحقة لسند {expense_id} غير موجود")

    entry = post_simple_revenue_journal(
        db, expense.branch_id, data.paid_at,
        debit_account_code=accrued_account.code, credit_account_code=settlement_account.code,
        amount=data.amount,
        reference=data.reference or f"EXP-{expense.id}-PAY",
        description=f"سداد سند مصروفات #{expense.id} — {expense.description}",
        source="expense_payment", source_id=expense.id,
        created_by=recorded_by,
        strict=True,
    )

    crud.create_expense_payment(
        db, expense.branch_id, expense.id, data,
        journal_entry_id=entry.id, recorded_by=recorded_by,
    )
    expense.amount_paid = expense.amount_paid + data.amount
    expense.payment_status = "paid" if expense.amount_paid >= expense.amount - Decimal("0.01") else "partial"
    db.commit()
    db.refresh(expense)
    return expense


def disburse_custody(db: Session, branch_id: int, data: CustodyCreate, disbursed_by: int) -> Custody:
    """صرف عهدة نقدية (2026-08-19، طلب Mohamed) — سلفة لموظف/مقاول لصرف
    بند معيّن (مقاولة/عمالة يومية...). يرحّل Dr.1190 (عهد نقدية تحت
    التسوية) / Cr.حساب المصدر، بنفس نمط record_expense (strict=True)."""
    validate_period_open(db, branch_id, data.disbursed_date)

    source_account = crud.get_account(db, data.source_account_id)
    if not source_account or source_account.branch_id != branch_id:
        raise ValueError(f"حساب المصدر {data.source_account_id} غير موجود في هذا الفرع")
    if source_account.account_type != "asset":
        raise ValueError(f"حساب المصدر «{source_account.name}» لازم يكون حساب أصول")
    if not source_account.is_active:
        raise ValueError(f"حساب المصدر «{source_account.name}» معطّل")

    custody_account = crud.get_account_by_code(db, branch_id, "1190")
    if not custody_account:
        raise FinancialConfigurationError("حساب العهد النقدية تحت التسوية (1190) غير معرَّف لهذا الفرع")
    if custody_account.account_type != "asset":
        raise FinancialConfigurationError("حساب 1190 لازم يكون حساب أصول")

    entry = post_simple_revenue_journal(
        db, branch_id, data.disbursed_date,
        debit_account_code=custody_account.code, credit_account_code=source_account.code,
        amount=data.amount,
        reference=data.reference or f"CUST-{data.disbursed_date.isoformat()}",
        description=f"صرف عهدة نقدية — {data.holder_name} ({data.purpose})",
        source="custody_disbursement", source_id=None,
        created_by=disbursed_by,
        commit_cost_centers=False,
        strict=True,
    )
    custody = crud.create_custody(
        db, branch_id, data, custody_account_id=custody_account.id,
        disbursement_entry_id=entry.id, disbursed_by=disbursed_by,
    )
    db.commit()
    db.refresh(custody)
    return custody


def settle_custody(
    db: Session, custody_id: int, data: CustodySettleRequest, settled_by: int,
) -> Custody:
    """تسوية عهدة (2026-08-19، طلب Mohamed) — توزيع فعلي دفعة واحدة
    (single-shot) لمبلغ العهدة على حسابات مصروفات حقيقية + مرتجع اختياري.
    مجموع lines + returned_amount لازم يساوي مبلغ العهدة بالظبط — تسوية
    جزئية عبر أكتر من جلسة حالة نادرة مؤجَّلة عمدًا.

    بيستخدم crud.create_journal_entry مباشرة (مش post_journal_entry) عشان
    post_journal_entry بتعمل commit داخلي بيكسر الذرّية مع تحديث حالة
    العهدة/بنود التسوية اللي لازم يحصلوا في نفس المعاملة — كل التحقق من
    الحسابات (موجودة/في نفس الفرع/نوعها Expense/مفعّلة) بيتعمل هنا يدويًا
    لأن crud.create_journal_entry نفسها زيرو تحقق (راجع record_expense
    لنفس النمط)."""
    custody = crud.get_custody(db, custody_id)
    if not custody:
        raise ValueError(f"العهدة {custody_id} غير موجودة")
    if custody.voided_at is not None:
        raise ValueError(f"العهدة {custody_id} ملغاة")
    if custody.status != "open":
        raise ValueError(f"العهدة {custody_id} متسواة بالفعل")
    if not data.lines and data.returned_amount <= 0:
        raise ValueError("لازم بند تسوية واحد على الأقل أو مبلغ مرتجع")

    lines_total = sum((line.amount for line in data.lines), Decimal("0"))
    total = lines_total + data.returned_amount
    if abs(total - custody.amount) > Decimal("0.01"):
        raise ValueError(
            f"مجموع بنود التسوية ({lines_total}) + المرتجع ({data.returned_amount}) "
            f"لازم يساوي مبلغ العهدة ({custody.amount}) بالظبط"
        )

    validate_period_open(db, custody.branch_id, data.settlement_date)

    journal_lines: list[JournalLineCreate] = []
    for line in data.lines:
        account = crud.get_account(db, line.expense_account_id)
        if not account or account.branch_id != custody.branch_id:
            raise ValueError(f"حساب المصروف {line.expense_account_id} غير موجود في هذا الفرع")
        if account.account_type != "expense":
            raise ValueError(f"الحساب «{account.name}» ليس حساب مصروفات")
        if not account.is_active:
            raise ValueError(f"الحساب «{account.name}» معطّل")
        if line.cost_center_id:
            cc = crud.get_cost_center(db, line.cost_center_id)
            if not cc or cc.branch_id != custody.branch_id:
                raise ValueError(f"مركز التكلفة {line.cost_center_id} غير موجود في هذا الفرع")
        journal_lines.append(JournalLineCreate(
            account_id=account.id, debit=line.amount, credit=Decimal("0"),
            description=line.description, cost_center_id=line.cost_center_id,
        ))

    if data.returned_amount > 0:
        source_account = crud.get_account(db, custody.source_account_id)
        if not source_account:
            raise ValueError(f"حساب مصدر العهدة {custody_id} غير موجود")
        journal_lines.append(JournalLineCreate(
            account_id=source_account.id, debit=data.returned_amount, credit=Decimal("0"),
            description=f"مرتجع عهدة #{custody.id}",
        ))

    journal_lines.append(JournalLineCreate(
        account_id=custody.custody_account_id, debit=Decimal("0"), credit=custody.amount,
        description=f"تسوية عهدة #{custody.id}",
    ))

    total_debit = sum((ln.debit for ln in journal_lines), Decimal("0"))
    total_credit = sum((ln.credit for ln in journal_lines), Decimal("0"))
    if abs(total_debit - total_credit) > Decimal("0.01"):
        raise ValueError(f"القيد غير متوازن: مدين={total_debit}, دائن={total_credit}")

    entry_data = JournalEntryCreate(
        branch_id=custody.branch_id, entry_date=data.settlement_date,
        reference=f"CUST-{custody.id}-SETTLE",
        description=(f"تسوية عهدة #{custody.id} — {custody.holder_name}")[:500],
        source="custody_settlement", source_id=custody.id,
        lines=journal_lines,
    )

    try:
        entry = crud.create_journal_entry(db, entry_data, settled_by)
        crud.create_custody_settlement_lines(db, custody.id, data.lines)
        custody.settlement_entry_id = entry.id
        custody.returned_amount = data.returned_amount
        custody.status = "settled"
        custody.settled_by = settled_by
        custody.settled_at = datetime.utcnow()
        db.commit()
        db.refresh(custody)
        return custody
    except Exception:
        db.rollback()
        raise


def void_custody(db: Session, custody_id: int, voided_by: int, reason: str = "voided via API") -> Custody:
    """إلغاء عهدة لسه open (لسه من غير أي تسوية) — نفس نمط void_expense
    بالظبط. عهدة متسواة بالفعل حالة نادرة مؤجَّلة (تحتاج مراجعة يدوية
    أوسع، مش إلغاء مباشر)."""
    custody = crud.get_custody(db, custody_id)
    if not custody:
        raise ValueError(f"العهدة {custody_id} غير موجودة")
    if custody.voided_at is not None:
        raise ValueError(f"العهدة {custody_id} ملغاة بالفعل")
    if custody.status != "open":
        raise ValueError(f"العهدة {custody_id} متسواة بالفعل — لا يمكن إلغاؤها مباشرة")

    source_account = crud.get_account(db, custody.source_account_id)
    custody_account = crud.get_account(db, custody.custody_account_id)
    if not source_account or not custody_account:
        raise ValueError(f"حسابات العهدة {custody_id} غير مكتملة")

    try:
        original_amount = custody.amount
        custody = crud.void_custody(db, custody, voided_by)
        crud.create_revenue_audit_log(
            db, branch_id=custody.branch_id, entity_type="custody", entity_id=custody.id,
            old_value=original_amount, new_value=Decimal("0.00"), reason=reason, changed_by=voided_by,
        )
        from app.resort_os.timezone_utils import business_today  # noqa: PLC0415
        post_simple_revenue_journal(
            db, custody.branch_id, business_today(settings.TIMEZONE),
            debit_account_code=source_account.code, credit_account_code=custody_account.code,
            amount=original_amount,
            reference=f"CUST-VOID-{custody.id}",
            description=f"إلغاء عهدة نقدية #{custody.id} — {custody.holder_name}",
            source="custody_void", source_id=custody.id,
            created_by=voided_by,
            strict=True, commit_cost_centers=False,
        )
        db.commit()
        db.refresh(custody)
        return custody
    except Exception:
        db.rollback()
        raise


def record_cash_receipt(db: Session, branch_id: int, data: CashReceiptCreate, recorded_by: int) -> CashReceipt:
    """إذن قبض عام (2026-08-19، طلب Mohamed) — تحصيل نقدية من مصدر متنوع
    مش مرتبط بمسار بيع قائم (سلفة عائدة، تعويض، إيراد متفرّق...). يرحّل
    Dr.destination_account (كاش/بنك) / Cr.source_account، نفس نمط
    record_expense بالظبط بس مقلوب الاتجاه. مفيش قيد على نوع
    source_account عمدًا (عكس expense_account في سند المصروفات)."""
    validate_period_open(db, branch_id, data.receipt_date)

    destination_account = crud.get_account(db, data.destination_account_id)
    if not destination_account or destination_account.branch_id != branch_id:
        raise ValueError(f"حساب الوجهة {data.destination_account_id} غير موجود في هذا الفرع")
    if destination_account.account_type != "asset":
        raise ValueError(f"حساب الوجهة «{destination_account.name}» لازم يكون حساب أصول (كاش/بنك)")
    if not destination_account.is_active:
        raise ValueError(f"حساب الوجهة «{destination_account.name}» معطّل")

    source_account = crud.get_account(db, data.source_account_id)
    if not source_account or source_account.branch_id != branch_id:
        raise ValueError(f"حساب المصدر {data.source_account_id} غير موجود في هذا الفرع")
    if not source_account.is_active:
        raise ValueError(f"حساب المصدر «{source_account.name}» معطّل")

    cost_center_code = None
    if data.cost_center_id:
        cc = crud.get_cost_center(db, data.cost_center_id)
        if not cc or cc.branch_id != branch_id:
            raise ValueError(f"مركز التكلفة {data.cost_center_id} غير موجود في هذا الفرع")
        cost_center_code = cc.code

    entry = post_simple_revenue_journal(
        db, branch_id, data.receipt_date,
        debit_account_code=destination_account.code, credit_account_code=source_account.code,
        amount=data.amount,
        reference=data.reference or f"RCV-{data.receipt_date.isoformat()}",
        description=data.description,
        source="manual_cash_receipt", source_id=None,
        created_by=recorded_by,
        cost_center_code=cost_center_code,
        commit_cost_centers=False,
        strict=True,
    )
    receipt = crud.create_cash_receipt(db, branch_id, data, journal_entry_id=entry.id, recorded_by=recorded_by)
    db.commit()
    db.refresh(receipt)
    return receipt


def void_cash_receipt(
    db: Session, receipt_id: int, voided_by: int, reason: str = "voided via API",
) -> CashReceipt:
    """إلغاء إذن قبض اتسجّل بالفعل — نفس نمط void_expense بالظبط بس مقلوب
    الاتجاه (Dr.source/Cr.destination بدل العكس)."""
    receipt = crud.get_cash_receipt(db, receipt_id)
    if not receipt:
        raise ValueError(f"إذن القبض {receipt_id} غير موجود")
    if receipt.voided_at is not None:
        raise ValueError(f"إذن القبض {receipt_id} ملغى بالفعل")

    destination_account = crud.get_account(db, receipt.destination_account_id)
    source_account = crud.get_account(db, receipt.source_account_id)
    if not destination_account or not source_account:
        raise ValueError(f"حسابات إذن القبض {receipt_id} غير مكتملة")

    try:
        original_amount = receipt.amount
        receipt = crud.void_cash_receipt(db, receipt, voided_by)
        crud.create_revenue_audit_log(
            db, branch_id=receipt.branch_id, entity_type="cash_receipt", entity_id=receipt.id,
            old_value=original_amount, new_value=Decimal("0.00"), reason=reason, changed_by=voided_by,
        )
        from app.resort_os.timezone_utils import business_today  # noqa: PLC0415
        post_simple_revenue_journal(
            db, receipt.branch_id, business_today(settings.TIMEZONE),
            debit_account_code=source_account.code, credit_account_code=destination_account.code,
            amount=original_amount,
            reference=f"RCV-VOID-{receipt.id}",
            description=f"إلغاء إذن قبض #{receipt.id}",
            source="cash_receipt_void", source_id=receipt.id,
            created_by=voided_by,
            strict=True, commit_cost_centers=False,
        )
        db.commit()
        db.refresh(receipt)
        return receipt
    except Exception:
        db.rollback()
        raise


def list_expenses(
    db: Session, branch_id: int,
    date_from: Optional[date] = None, date_to: Optional[date] = None,
    page: int = 1, size: int = 30,
) -> tuple[list[dict], int]:
    items, total = crud.list_expenses(db, branch_id, date_from, date_to, page, size)
    enriched = []
    for exp in items:
        row = ExpenseRead.model_validate(exp).model_dump()
        row["expense_account_code"] = exp.expense_account.code if exp.expense_account else ""
        row["expense_account_name"] = exp.expense_account.name if exp.expense_account else ""
        row["settlement_account_code"] = exp.settlement_account.code if exp.settlement_account else ""
        enriched.append(row)
    return enriched, total
